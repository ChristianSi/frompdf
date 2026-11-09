"""Recognize deliberate line breaks within blocks from line geometry and typography."""

import re
from dataclasses import replace
from itertools import pairwise
from statistics import median

from frompdf.continuations import PageLayout, begins_lowercase, ends_open_sentence
from frompdf.line_features import (
    close_font_size,
    compatible_style,
    ends_word_break_hyphen,
    is_prose_line,
    is_textual_line,
    same_physical_line,
    visibly_different_font_sizes,
)
from frompdf.models import Line
from frompdf.page_context import (
    MAX_FIRST_LINE_INDENT_EM,
    MIN_FIRST_LINE_INDENT_EM,
    PageContext,
    column_for_line,
    has_normal_advance,
    line_is_short,
    near,
    percentile_90,
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

# A set-off passage, such as quoted verse, has at least this many lines.
MIN_PASSAGE_LINES = 2


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


def may_break_between(
    left: Line,
    right: Line,
    lone_address_starts_line: bool = False,
    set_line_by_line: bool = False,
) -> bool:
    """Return whether nothing rules out a deliberate break between two lines.

    Hyphenated words are never broken, nor are fragments with few letters or
    digits, such as pieces of mathematical notation. Neither are sentences
    continuing in lower case, unless the lines are known to be set line by
    line, as in verse. With lone_address_starts_line, an e-mail address or
    URL on a line of its own does not count as a continuation.
    """
    return (
        left.page_no == right.page_no
        and not same_physical_line(left, right)
        and has_line_content(left)
        and has_line_content(right)
        and not ends_word_break_hyphen(left.text)
        and not (
            not set_line_by_line
            and ends_open_sentence(left.text)
            and begins_lowercase(right.text)
            and not (lone_address_starts_line and LONE_ADDRESS_PATTERN.match(right.text))
        )
    )


def next_word_fits(
    left: Line, right: Line, layout: PageLayout, min_measure_right: float | None = None
) -> bool:
    """Return whether the first word of right would have fit on the open side of left.

    Wrapped text breaks only when the next word does not fit, so room for it
    is the clearest evidence of a deliberate break. This is tested on the
    open side of left- and right-aligned lines. min_measure_right is the
    least right edge of the measure of left-aligned lines, if known.
    """
    if left.x1 is None or left.x2 is None or right.x1 is None or right.x2 is None:
        return False

    font_size = left.font_size or layout.context.font_size
    word_width = first_word_width(right)
    if word_width is None:
        return False
    needed_room = word_width + font_size * FIT_SLACK_EM
    if near(right.x1, left.x1, font_size):
        measure_right = left_aligned_measure_right(left, layout, font_size)
        if min_measure_right is not None:
            measure_right = max(measure_right, min_measure_right)
        return measure_right - left.x2 >= needed_room
    if near(right.x2, left.x2, font_size):
        # Both lines must be clearly inset, so the indented first line of a
        # justified paragraph never counts as right-aligned.
        measure_left = right_aligned_measure_left(left, layout, font_size)
        return (
            min(left.x1, right.x1) - measure_left > font_size * MAX_FIRST_LINE_INDENT_EM
            and left.x1 - measure_left >= needed_room
        )
    return False


def is_hard_line_break(left: Line, right: Line, layout: PageLayout) -> bool:
    """Return whether right starts a new line by design rather than by wrapping.

    The clearest evidence is room left on the line for the next word.
    Otherwise, a change of font face, weight, or size after a clearly short
    line also marks a deliberate break.
    """
    if (
        left.x1 is None
        or left.x2 is None
        or right.x1 is None
        or right.x2 is None
        or not may_break_between(left, right)
    ):
        return False
    if next_word_fits(left, right, layout):
        return True

    font_size = left.font_size or layout.context.font_size
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
    line_list: list[Line],
    layouts: dict[int, PageLayout],
    item_text_x1: float | None = None,
    passage: bool = False,
) -> set[int]:
    """Return the IDs of a block's lines that are followed by a deliberate line break.

    Once a centered, line-by-line block shows one deliberate break, its other
    line ends are assumed to be deliberate too, unless they are ruled out.
    item_text_x1 is where the text of a list item starts after its marker.
    Wrapped lines never start right of it, so lines that do follow a break.
    In a passage set off line by line, such as quoted verse, every line
    leaving room for the next word ends deliberately, even where a sentence
    continues in lower case.
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
    if passage:
        for left_pieces, right_pieces in pairwise(visual_lines(line_list)):
            left, right = left_pieces[-1], right_pieces[0]
            layout = layouts[left.page_no]
            if may_break_between(left, right, set_line_by_line=True) and next_word_fits(
                whole_visual_line(left_pieces),
                whole_visual_line(right_pieces),
                layout,
                passage_measure_right(left_pieces[0], layout.context),
            ):
                hard_break_ids.add(id(left))
    return hard_break_ids


def visual_lines(line_list: list[Line]) -> list[list[Line]]:
    """Group consecutive pieces of the same visual line."""
    grouped: list[list[Line]] = []
    for line_obj in line_list:
        if grouped and same_physical_line(grouped[-1][-1], line_obj):
            grouped[-1].append(line_obj)
        else:
            grouped.append([line_obj])
    return grouped


def whole_visual_line(pieces: list[Line]) -> Line:
    """Return a line record spanning all pieces of a visual line."""
    return replace(pieces[0], text=' '.join(piece.text for piece in pieces), x2=pieces[-1].x2)


def passage_measure_right(line_obj: Line, context: PageContext) -> float | None:
    """Return the least right edge of the measure of a passage set off from its column.

    Quotations are inset on the left and at most as far on the right, which
    matters where no line at their left edge shows how far the measure reaches.
    """
    column = column_for_line(line_obj, context)
    if column is None or line_obj.x1 is None:
        return None
    return column.right - (line_obj.x1 - column.left)


def is_passage_line(line_obj: Line, context: PageContext) -> bool:
    """Return whether a visual line is set off from the body in smaller, inset type."""
    if line_obj.x1 is None or line_obj.font_size is None or not is_prose_line(line_obj):
        return False
    column = column_for_line(line_obj, context)
    return (
        column is not None
        and line_obj.font_size < context.font_size
        and not close_font_size(line_obj.font_size, context.font_size)
        and line_obj.x1 - column.left >= line_obj.font_size * MIN_FIRST_LINE_INDENT_EM
    )


def continues_passage(previous: Line, current: Line, context: PageContext) -> bool:
    """Return whether current continues a set-off passage on the next line."""
    font_size = current.font_size or context.font_size
    return (
        previous.page_no == current.page_no
        and near(current.x1, previous.x1 or 0.0, font_size)
        and compatible_style(previous, current)
        and has_normal_advance(previous, current, context)
    )


def text_resumes_after(whole_lines: list[Line], run: list[int], context: PageContext) -> bool:
    """Return whether body text follows a passage in its column on the same page.

    Quotations are embedded in the text, so it resumes after them, possibly
    after further stanzas at the same left edge. Small inset print ending a
    page, such as unrecognized notes, or above a title, such as a letterhead,
    is not.
    """
    first = whole_lines[run[0]]
    font_size = first.font_size or context.font_size
    for following in whole_lines[run[-1] + 1 :]:
        if is_passage_line(following, context) and near(following.x1, first.x1 or 0.0, font_size):
            continue
        return close_font_size(following.font_size, context.font_size) and column_for_line(
            following, context
        ) == column_for_line(first, context)
    return False


def line_by_line_passages(layouts: dict[int, PageLayout]) -> dict[int, int]:
    """Map the IDs of lines in passages set off line by line to the ID of their first line.

    Such passages, as verse quoted in prose, are set in smaller type, inset
    from the column margin, and evenly spaced at a shared left edge. Most of
    their lines end where the next line's first word would still have fit,
    unlike quoted prose, which wraps, and body text resumes after them.
    pdftext tends to split them into blocks of a line or two, and they need
    not have spacing or indents to separate them from the text around them
    otherwise. A gap, as between stanzas, ends a passage.
    """
    passage_of_line: dict[int, int] = {}
    for layout in layouts.values():
        context = layout.context
        page_lines = visual_lines(list(layout.lines))
        whole_lines = [whole_visual_line(pieces) for pieces in page_lines]
        runs: list[list[int]] = []
        for index, current in enumerate(whole_lines):
            if not is_passage_line(current, context):
                continue
            if not (
                runs
                and runs[-1][-1] == index - 1
                and continues_passage(whole_lines[index - 1], current, context)
            ):
                runs.append([])
            runs[-1].append(index)
        for run in runs:
            measure_right = passage_measure_right(whole_lines[run[0]], context)
            fitting = sum(
                next_word_fits(whole_lines[left], whole_lines[right], layout, measure_right)
                for left, right in pairwise(run)
            )
            if (
                len(run) >= MIN_PASSAGE_LINES
                and fitting * 2 > len(run) - 1
                and text_resumes_after(whole_lines, run, context)
            ):
                passage_of_line.update(
                    (id(piece), id(page_lines[run[0]][0]))
                    for index in run
                    for piece in page_lines[index]
                )
    return passage_of_line
