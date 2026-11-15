"""Restore the real font sizes of PDFs that set their text at size 1.

Some PDFs, such as those typeset by Advent 3B2, set all text at font size 1
and scale it up by the text matrix. pdftext reports these sizes as 1.0. The
real size of a glyph is its font size multiplied by the vertical scale of the
matrix of its text object, which pdfium reports.
"""

import ctypes
import math
from collections.abc import Sequence
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from pdftext.schema import Char as PdfTextChar
from pdftext.schema import Page

# Sizes up to this are placeholders, not real sizes.
PLACEHOLDER_SIZE = 1.0
# A restored size is trusted if the box of its glyph is at least this share of
# it and at most this many times as high, as a text object nested in a form
# XObject is scaled by the form's matrix too, which pdfium does not include.
MIN_BOX_SHARE = 0.5
MAX_BOX_SHARE = 2.0


def text_object_size(text_page: pdfium.PdfTextPage, char_index: int) -> float | None:
    """Return the real font size of a character of a text page, if pdfium knows it."""
    text_object = pdfium_c.FPDFText_GetTextObject(text_page.raw, char_index)
    if not text_object:
        return None
    size = ctypes.c_float()
    if not pdfium_c.FPDFTextObj_GetFontSize(text_object, ctypes.byref(size)):
        return None
    matrix = pdfium_c.FS_MATRIX()
    if not pdfium_c.FPDFPageObj_GetMatrix(text_object, matrix):
        return None
    real_size = size.value * math.hypot(matrix.c, matrix.d)
    return real_size if real_size > PLACEHOLDER_SIZE else None


def plausible_size(char: PdfTextChar, size: float) -> bool:
    """Return whether a restored size fits the box of its glyph, where it has one."""
    x1, y1, x2, y2 = char.get('bbox', (0.0, 0.0, 0.0, 0.0))
    height = abs(x2 - x1) if char.get('rotation') else abs(y2 - y1)
    if height <= PLACEHOLDER_SIZE:
        return True
    return MIN_BOX_SHARE * size <= height <= MAX_BOX_SHARE * size


def restore_font_sizes(input_path: Path, page_list: Sequence[Page]) -> None:
    """Replace placeholder font sizes of spans and their characters by real sizes, in place.

    A span takes the largest size of its characters, as the box-based
    fallback took its tallest glyph: subscripts set in the same span at a
    smaller size keep their own size, and a large number in a chapter label
    keeps its size.
    """
    pdf: pdfium.PdfDocument | None = None
    try:
        for page_index, page in enumerate(page_list):
            spans = [
                span
                for block in page.get('blocks', [])
                for line in block.get('lines', [])
                for span in line.get('spans', [])
                if float(span.get('font', {}).get('size') or 0.0) <= PLACEHOLDER_SIZE
                and span.get('chars')
            ]
            if not spans:
                continue
            if pdf is None:
                pdf = pdfium.PdfDocument(input_path)
            page_no = page.get('page', page_index)
            if not 0 <= page_no < len(pdf):
                continue
            pdf_page = pdf[page_no]
            text_page = pdf_page.get_textpage()
            try:
                for span in spans:
                    sizes: list[float] = []
                    for char in span['chars']:
                        size = text_object_size(text_page, char['char_idx'])
                        if size is None or not plausible_size(char, size):
                            continue
                        char['font'] = {**char.get('font', {}), 'size': size}
                        if char.get('char', '').strip():
                            sizes.append(round(size, 2))
                    if sizes:
                        span['font'] = {**span['font'], 'size': max(sizes)}
            finally:
                text_page.close()
                pdf_page.close()
    finally:
        if pdf is not None:
            pdf.close()
