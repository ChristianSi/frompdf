"""Recognize deliberate line breaks within blocks from line geometry and typography."""

import re
from itertools import pairwise
from statistics import median

from frompdf.continuations import PageLayout, begins_lowercase, ends_open_sentence
from frompdf.models import Line
from frompdf.segmentation import (
    MAX_FIRST_LINE_INDENT_EM,
    column_for_line,
    compatible_style,
    ends_word_break_hyphen,
    is_textual_line,
    line_is_short,
    near,
    percentile_90,
    same_physical_line,
    visibly_different_font_sizes,
)

# Room for the inter-word space plus a margin of error, since the next word's
# width is estimated from its line's average character width.
FIT_SLACK_EM = 0.5

# Lines with few letters still carry content, rather than being fragments of
# notation, when they include enough digits, as in dates or postal codes.
MIN_CONTENT_DIGITS = 4

# A line holding nothing but an e-mail address or URL, as in an address card.
LONE_ADDRESS_PATTERN = re.compile(r'^\S*(?:@|://|www\.)\S*$')

# Lines of a list item starting at least this many ems right of the item's
# text, after its marker, are set apart deliberately, as the examples under
# cc-style-guide's items on abbreviations.
MIN_LIST_ITEM_INDENT_EM = 0.5

# A shared center needs at least this many lines to be convincing.
MIN_CENTERED_LINES = 3

# Lines sharing their center are only centered, rather than justified, when
# their widths differ. Given the tolerance for centers, this also excludes
# left- and right-aligned lines.
MIN_CENTERED_WIDTH_SPREAD_EM = 1.0

# Centered prose, such as an abstract, fills most of its column. Cards, verse,
# and other text set line by line stay well short of it.
MAX_CENTERED_LINE_WIDTH_SHARE = 2 / 3


def first_word_width(line_obj: Line) -> float | None:
    """Estimate the width of a line's first word from its average character width."""
    if line_obj.x1 is None or line_obj.x2 is None or not line_obj.text:
        return None
    # Only ordinary spaces allow a line break; no-break spaces join words.
    first_word = line_obj.text.split(' ', 1)[0]
    return (line_obj.x2 - line_obj.x1) * len(first_word) / len(line_obj.text)


def measures_line(other: Line, line_obj: Line) -> bool:
    """Return whether other's extent says something about the measure of line_obj.

    Visibly larger text, such as a title above a narrower abstract, often spans
    a wider measure than the text below it.
    """
    return not (
        other.font_size is not None
        and line_obj.font_size is not None
        and other.font_size > line_obj.font_size
        and visibly_different_font_sizes(other.font_size, line_obj.font_size)
    )


def left_aligned_measure_right(line_obj: Line, layout: PageLayout, font_size: float) -> float:
    """Return the usual right edge of page lines sharing a line's left edge.

    A percentile ignores occasional wider lines, such as a caption that starts
    at the same margin but spans several columns.
    """
    assert line_obj.x1 is not None
    assert line_obj.x2 is not None
    rights = [
        other.x2
        for other in layout.lines
        if other.x2 is not None
        and near(other.x1, line_obj.x1, font_size)
        and measures_line(other, line_obj)
    ]
    return percentile_90(rights) if rights else line_obj.x2


def right_aligned_measure_left(line_obj: Line, layout: PageLayout, font_size: float) -> float:
    """Return the usual left edge of page lines sharing a line's right edge."""
    assert line_obj.x1 is not None
    assert line_obj.x2 is not None
    negated_lefts = [
        -other.x1
        for other in layout.lines
        if other.x1 is not None
        and near(other.x2, line_obj.x2, font_size)
        and measures_line(other, line_obj)
    ]
    return -percentile_90(negated_lefts) if negated_lefts else line_obj.x1


def has_line_content(line_obj: Line) -> bool:
    """Return whether a line holds words or numbers rather than a fragment of notation."""
    return (
        is_textual_line(line_obj)
        or sum(character.isdigit() for character in line_obj.text) >= MIN_CONTENT_DIGITS
    )


def may_break_between(left: Line, right: Line, lone_address_starts_line: bool = False) -> bool:
    """Return whether nothing rules out a deliberate break between two lines.

    Hyphenated words and sentences continuing in lower case are never broken,
    nor are fragments with few letters or digits, such as pieces of
    mathematical notation. With lone_address_starts_line, an e-mail address or
    URL on a line of its own does not count as a continuation.
    """
    return (
        left.page_no == right.page_no
        and not same_physical_line(left, right)
        and has_line_content(left)
        and has_line_content(right)
        and not ends_word_break_hyphen(left.text)
        and not (
            ends_open_sentence(left.text)
            and begins_lowercase(right.text)
            and not (lone_address_starts_line and LONE_ADDRESS_PATTERN.match(right.text))
        )
    )


def is_hard_line_break(left: Line, right: Line, layout: PageLayout) -> bool:
    """Return whether right starts a new line by design rather than by wrapping.

    The clearest evidence is room left on the line: wrapped text breaks only
    when the next word does not fit. This is tested on the open side of left-
    and right-aligned lines. Otherwise, a change of font face, weight, or size
    after a clearly short line also marks a deliberate break.
    """
    if (
        left.x1 is None
        or left.x2 is None
        or right.x1 is None
        or right.x2 is None
        or not may_break_between(left, right)
    ):
        return False

    font_size = left.font_size or layout.context.font_size
    word_width = first_word_width(right)
    if word_width is None:
        return False
    needed_room = word_width + font_size * FIT_SLACK_EM
    if near(right.x1, left.x1, font_size):
        if left_aligned_measure_right(left, layout, font_size) - left.x2 >= needed_room:
            return True
    elif near(right.x2, left.x2, font_size):
        # Both lines must be clearly inset, so the indented first line of a
        # justified paragraph never counts as right-aligned.
        measure_left = right_aligned_measure_left(left, layout, font_size)
        if (
            min(left.x1, right.x1) - measure_left > font_size * MAX_FIRST_LINE_INDENT_EM
            and left.x1 - measure_left >= needed_room
        ):
            return True

    column = column_for_line(left, layout.context)
    return (
        column is not None
        and not compatible_style(left, right)
        and line_is_short(left, column, font_size)
    )


def physical_line_extents(line_list: list[Line]) -> list[tuple[float, float]] | None:
    """Return the left and right edges of each visual line, if all are positioned."""
    extents: list[tuple[float, float]] = []
    for previous, line_obj in zip([None, *line_list], line_list, strict=False):
        if line_obj.x1 is None or line_obj.x2 is None:
            return None
        if previous is not None and same_physical_line(previous, line_obj):
            extents[-1] = (extents[-1][0], line_obj.x2)
        else:
            extents.append((line_obj.x1, line_obj.x2))
    return extents


def is_centered_line_layout(line_list: list[Line], layout: PageLayout) -> bool:
    """Return whether a block consists of short lines centered on a common axis.

    Without an open side, the measure of centered text is unknown, so the room
    left on a line says nothing about wrapping. Lines of differing widths
    sharing a center, all staying well short of their column, suggest text set
    line by line instead, as in address cards.
    """
    if len({line_obj.page_no for line_obj in line_list}) != 1:
        return False
    extents = physical_line_extents(line_list)
    column = column_for_line(line_list[0], layout.context)
    if extents is None or len(extents) < MIN_CENTERED_LINES or column is None:
        return False

    font_size = max(line_obj.font_size or layout.context.font_size for line_obj in line_list)
    centers = [(left + right) / 2 for left, right in extents]
    center = median(centers)
    widths = [right - left for left, right in extents]
    return (
        all(near(line_center, center, font_size) for line_center in centers)
        and max(widths) - min(widths) >= font_size * MIN_CENTERED_WIDTH_SPREAD_EM
        and max(widths) <= column.width * MAX_CENTERED_LINE_WIDTH_SHARE
    )


def starts_right_of_item_text(right: Line, first: Line, item_text_x1: float) -> bool:
    """Return whether a line of a list item starts clearly right of the item's text."""
    font_size = first.font_size or 0.0
    return (
        right.page_no == first.page_no
        and right.x1 is not None
        and right.x1 >= item_text_x1 + font_size * MIN_LIST_ITEM_INDENT_EM
    )


def hard_line_break_ids(
    line_list: list[Line], layouts: dict[int, PageLayout], item_text_x1: float | None = None
) -> set[int]:
    """Return the IDs of a block's lines that are followed by a deliberate line break.

    Once a centered, line-by-line block shows one deliberate break, its other
    line ends are assumed to be deliberate too, unless they are ruled out.
    item_text_x1 is where the text of a list item starts after its marker.
    Wrapped lines never start right of it, so lines that do follow a break.
    """
    hard_break_ids = {
        id(left)
        for left, right in pairwise(line_list)
        if is_hard_line_break(left, right, layouts[left.page_no])
        or (
            item_text_x1 is not None
            and starts_right_of_item_text(right, line_list[0], item_text_x1)
            and may_break_between(left, right)
        )
    }
    if hard_break_ids and is_centered_line_layout(line_list, layouts[line_list[0].page_no]):
        hard_break_ids.update(
            id(left)
            for left, right in pairwise(line_list)
            if may_break_between(left, right, lone_address_starts_line=True)
        )
    return hard_break_ids
