"""Insert the spaces between words that a PDF only shows as gaps.

A PDF may set words apart by positioning them, without a space glyph between
them, and `pdftext` then gives no space, as in nature-spin's caption label
`GaV₄S₈. a Magnetic phase diagram`. Such a gap is as wide as the spaces
between the other words of its line, and much wider than the gaps between
the glyphs of a word. Each line is measured by itself, as lines are spaced
differently in justified text and letter-spaced headings.
"""

import math
from collections.abc import Sequence, Set
from itertools import pairwise
from statistics import median
from typing import cast

from pdftext.schema import Char as PdfTextChar
from pdftext.schema import Line as PdfTextLine
from pdftext.schema import Page
from pdftext.schema import Span as PdfTextSpan

from frompdf.lines import get_bbox, span_char_text_ranges

# Two glyphs are separate words where the gap between them is at least the
# first share of the line's median gap between words, and lies at least the
# second share of the way from its median gap between the glyphs of a word
# to that median word gap. Lines with fewer gaps between words than the third
# give no reliable measure.
MIN_WORD_GAP_SHARE = 0.8
MIN_LETTER_TO_WORD_GAP_SHARE = 0.6
MIN_WORD_GAPS = 3
# Glyphs turned by more than this, in radians, run across the line, where
# horizontal gaps say nothing about words.
MAX_ROTATION = 0.01


def insert_missing_word_spaces(page_list: Sequence[Page], skipped_pages: Set[int]) -> None:
    """Insert spaces where glyphs of a line lie a word gap apart, in place.

    skipped_pages are the numbers, starting at 1, of pages whose glyph
    positions are not to be trusted, as those of OCR text layers.
    """
    for page_index, page in enumerate(page_list):
        if page_index + 1 in skipped_pages:
            continue
        for block in page.get('blocks', []):
            for line in block.get('lines', []):
                insert_line_word_spaces(line)


def is_turned(char: PdfTextChar) -> bool:
    """Return whether a glyph does not run along the line."""
    rotation = float(char.get('rotation') or 0.0)
    return abs(math.remainder(rotation, math.tau)) > MAX_ROTATION


def missing_space_gaps(
    line: PdfTextLine,
) -> list[tuple[PdfTextSpan, PdfTextChar, PdfTextChar]]:
    """Return the adjoining glyphs of a line lying a word gap apart without a space.

    Each is given by the span of the glyph before the gap, that glyph, and
    the one after it.
    """
    # Visible glyphs with a width, and whether whitespace precedes them.
    glyphs: list[tuple[PdfTextSpan, PdfTextChar, bool]] = []
    spaced = False
    for span in line.get('spans', []):
        for char in span.get('chars', []):
            if not char.get('char', '').strip():
                spaced = True
                continue
            if is_turned(char):
                return []
            x1, _, x2, _ = get_bbox(char)
            if x1 is None or x2 is None or x2 <= x1:
                continue
            glyphs.append((span, char, spaced))
            spaced = False

    def gap(left: PdfTextChar, right: PdfTextChar) -> float:
        return cast(float, get_bbox(right)[0]) - cast(float, get_bbox(left)[2])

    word_gaps: list[float] = []
    letter_gaps: list[float] = []
    for (_, left, _), (_, right, right_spaced) in pairwise(glyphs):
        (word_gaps if right_spaced else letter_gaps).append(gap(left, right))
    if len(word_gaps) < MIN_WORD_GAPS or not letter_gaps:
        return []
    word_gap = median(word_gaps)
    letter_gap = median(letter_gaps)
    if word_gap <= max(letter_gap, 0.0):
        return []

    def is_occupied(left: PdfTextChar, right: PdfTextChar) -> bool:
        # A glyph coming elsewhere in the line may be set within the gap, as
        # the `t` between nature-spin's parentheses in `m(t)`.
        gap_x1 = cast(float, get_bbox(left)[2])
        gap_x2 = cast(float, get_bbox(right)[0])
        return any(
            cast(float, get_bbox(char)[0]) < gap_x2 and cast(float, get_bbox(char)[2]) > gap_x1
            for _, char, _ in glyphs
            if char is not left and char is not right
        )

    return [
        (left_span, left, right)
        for (left_span, left, _), (_, right, right_spaced) in pairwise(glyphs)
        if not right_spaced
        and gap(left, right) >= MIN_WORD_GAP_SHARE * word_gap
        and gap(left, right) - letter_gap >= MIN_LETTER_TO_WORD_GAP_SHARE * (word_gap - letter_gap)
        and not is_occupied(left, right)
    ]


def insert_line_word_spaces(line: PdfTextLine) -> None:
    """Insert spaces where glyphs of a line lie a word gap apart, in place.

    The space follows the glyph before the gap in its span, and spans the gap.
    """
    for span, left, right in missing_space_gaps(line):
        text_range = span_char_text_ranges(span).get(id(left))
        if text_range is None:
            continue
        chars = span['chars']
        index = next(index for index, char in enumerate(chars) if char is left)
        _, y1, x2, y2 = get_bbox(left)
        space = cast(
            PdfTextChar,
            {**left, 'char': ' ', 'bbox': [x2, y1, get_bbox(right)[0], y2]},
        )
        chars.insert(index + 1, space)
        text = span.get('text', '')
        span['text'] = text[: text_range[1]] + ' ' + text[text_range[1] :]
