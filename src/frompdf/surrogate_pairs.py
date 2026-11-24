"""Restore characters outside the Basic Multilingual Plane that pdftext lost.

pdfium reports such a character, as a glyph that a font's Unicode mapping
maps to `𝑃` (U+1D443), as the two halves of its UTF-16 surrogate pair at
consecutive character indices, both with the glyph's box. pdftext replaces each
half with U+FFFD, as in ceur-semtab-2024-results, whose CMMI fonts map their
letters to mathematical italic ones. The pair is read again from pdfium and
combined into the character.
"""

from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path
from unicodedata import name, normalize

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from pdftext.schema import Page
from pdftext.schema import Span as PdfTextSpan

from frompdf.lines import get_bbox, is_math_italic_span, span_char_text_ranges

REPLACEMENT_CHARACTER = '�'
HIGH_SURROGATES = range(0xD800, 0xDC00)
LOW_SURROGATES = range(0xDC00, 0xE000)
# Mathematical italic letters stand in for the plain letters of math italic
# fonts, which other documents map to plain letters and render in italics.
# The italic small h is the letterlike PLANCK CONSTANT, a hole in their block.
PLANCK_CONSTANT = 'ℎ'


def combine_surrogates(high: int, low: int) -> str | None:
    """Return the character encoded by a UTF-16 surrogate pair, if the units form one."""
    if high not in HIGH_SURROGATES or low not in LOW_SURROGATES:
        return None
    return chr(0x10000 + ((high - HIGH_SURROGATES.start) << 10) + (low - LOW_SURROGATES.start))


def is_mathematical_italic_letter(char: str) -> bool:
    """Return whether a character is a mathematical italic letter, not bold or sans-serif."""
    return char == PLANCK_CONSTANT or name(char, '').startswith('MATHEMATICAL ITALIC ')


def plain_letter(char: str, math_italic: bool) -> str:
    """Return the plain letter for a mathematical italic letter of a math italic font."""
    if math_italic and is_mathematical_italic_letter(char):
        return normalize('NFKC', char)
    return char


def restore_span_surrogate_pairs(span_dict: PdfTextSpan, code_unit: Callable[[int], int]) -> None:
    """Combine the replaced halves of surrogate pairs in a span's characters and text, in place.

    code_unit returns the UTF-16 code unit that pdfium reports for a character
    index. Both halves must have consecutive indices and the same box.
    """
    chars = span_dict.get('chars', [])
    groups: list[tuple[int, str]] = []
    math_italic = is_math_italic_span(span_dict)
    index = 0
    while index + 1 < len(chars):
        first, second = chars[index], chars[index + 1]
        first_index, second_index = first.get('char_idx'), second.get('char_idx')
        if (
            first.get('char') == REPLACEMENT_CHARACTER
            and second.get('char') == REPLACEMENT_CHARACTER
            and isinstance(first_index, int)
            and second_index == first_index + 1
            and get_bbox(first) == get_bbox(second)
        ):
            combined = combine_surrogates(code_unit(first_index), code_unit(second_index))
            if combined is not None:
                groups.append((index, plain_letter(combined, math_italic)))
                index += 2
                continue
        index += 1
    if not groups:
        return

    text = span_dict.get('text', '')
    text_ranges = span_char_text_ranges(span_dict)
    for start, replacement in reversed(groups):
        ranges = [
            text_ranges[id(char)] for char in chars[start : start + 2] if id(char) in text_ranges
        ]
        if len(ranges) == 2:
            text_start = min(range_start for range_start, _ in ranges)
            text_end = max(range_end for _, range_end in ranges)
            text = text[:text_start] + replacement + text[text_end:]
        chars[start]['char'] = replacement
        del chars[start + 1]
    span_dict['text'] = text


def replaced_spans(page_dict: Page) -> list[PdfTextSpan]:
    """Return the spans of a page with replacement characters among their characters."""
    return [
        span_dict
        for block_dict in page_dict.get('blocks', [])
        for line_dict in block_dict.get('lines', [])
        for span_dict in line_dict.get('spans', [])
        if any(char.get('char') == REPLACEMENT_CHARACTER for char in span_dict.get('chars', []))
    ]


def code_unit(text_page: pdfium.PdfTextPage, char_index: int) -> int:
    """Return the UTF-16 code unit that pdfium reports for a character of a text page."""
    if not 0 <= char_index < text_page.count_chars():
        return 0
    return pdfium_c.FPDFText_GetUnicode(text_page.raw, char_index)


def restore_surrogate_pairs(input_path: Path, page_list: Sequence[Page]) -> None:
    """Restore characters whose surrogate pairs pdftext replaced, in place."""
    pdf: pdfium.PdfDocument | None = None
    try:
        for page_index, page_dict in enumerate(page_list):
            spans = replaced_spans(page_dict)
            if not spans:
                continue
            if pdf is None:
                pdf = pdfium.PdfDocument(input_path)
            page_no = page_dict.get('page', page_index)
            if not 0 <= page_no < len(pdf):
                continue
            pdf_page = pdf[page_no]
            text_page = pdf_page.get_textpage()
            try:
                for span_dict in spans:
                    restore_span_surrogate_pairs(span_dict, partial(code_unit, text_page))
            finally:
                text_page.close()
                pdf_page.close()
    finally:
        if pdf is not None:
            pdf.close()
