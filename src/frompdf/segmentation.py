import re
from itertools import groupby

from frompdf.line_features import (
    NUMBERED_OR_BULLETED_START_PATTERN,
    close_font_size,
    compatible_style,
    differs_only_by_italics,
    ends_sentence,
    ends_word_break_hyphen,
    has_alphanumeric,
    is_prose_line,
    is_script_sized,
    is_textual_line,
    normalized_font_name,
    same_physical_line,
    same_running_text_line,
    significant_size_change,
    significant_style_change,
    touches_script_fragment,
    visibly_different_font_sizes,
)
from frompdf.models import Line
from frompdf.page_context import (
    MARGIN_TOLERANCE_EM,
    MAX_FIRST_LINE_INDENT_EM,
    MIN_COLUMN_LINES,
    MIN_FIRST_LINE_INDENT_EM,
    MIN_RHYTHM_SAMPLES,
    ColumnContext,
    HangingIndentContext,
    PageContext,
    advance_ratio,
    build_columns,
    build_page_context,
    column_for_line,
    dominant_page_font_size,
    has_blank_line_advance,
    has_large_advance,
    has_normal_advance,
    line_is_full,
    line_is_short,
    near,
    near_left_edge,
    same_flow,
)

# A pdftext block edge may add this much to the leading of the following lines
# without counting as spacing, in multiples of the font size.
UNIFORM_ADVANCE_TOLERANCE_EM = 0.1

# Lines this much larger than the page's body text are display text, such as
# titles. Their own leading, rather than the body rhythm, shows continuation.
# Within such a title, sizes may vary somewhat when they are estimated from
# glyph boxes, as subscripts and descenders enlarge them.
DISPLAY_LINE_MIN_FONT_RATIO = 1.16
DISPLAY_LINE_MAX_SIZE_RATIO = 1.25
DISPLAY_LINE_MAX_ADVANCE_EM = 1.4

# Same-line fragments in one font face with a gap of at most half an em are
# pieces of one run of text, even if superscripts change their extracted size.
MAX_SAME_FACE_FRAGMENT_GAP_EM = 0.5

# A marker line, such as an ornament ending a chapter or separating sections,
# has no letters or digits, is centered in its column within this many ems, and
# takes up at most this share of the column's width. Leading is no evidence, as
# ornaments often sit closer to the text than its lines do to each other.
MARKER_LINE_CENTER_TOLERANCE_EM = 1.0
MARKER_LINE_MAX_COLUMN_SHARE = 0.5

# A line ending a sentence must reach the column's right edge this closely, in
# ems, to count as continued. Real paragraphs rarely happen to end that close to
# the edge, unlike within the tolerance of line_is_full.
CONTINUED_SENTENCE_END_MAX_SHORTFALL_EM = 0.5

# Labels of references, enumerations, and theorems beyond those of
# NUMBERED_OR_BULLETED_START_PATTERN, which start a new item.
ITEM_LABEL_START_PATTERN = re.compile(r'\[\d+\]|\(\d+\)|\d+\)|▶')
# Lower-case letter and roman labels, as `a)`, `(b)`, or `iv.`, which start an
# item rather than continue the text above in lower case.
LOWER_CASE_ITEM_LABEL_START_PATTERN = re.compile(r'\(?[a-z]{1,4}[.)]\s')


def hanging_indents_for_boundary(
    left: Line, right: Line, context: PageContext
) -> tuple[HangingIndentContext, ...]:
    """Return learned hanging-indent patterns shared by two adjacent lines."""
    left_column = column_for_line(left, context)
    right_column = column_for_line(right, context)
    if left_column is None or right_column != left_column:
        return ()
    if left.y1 is None or right.y1 is None:
        return ()
    region_tolerance = context.font_size * 2.5

    return tuple(
        hanging_indent
        for hanging_indent in context.hanging_indents
        if hanging_indent.column_left == left_column.left
        and hanging_indent.y_min - region_tolerance
        <= left.y1
        <= hanging_indent.y_max + region_tolerance
        and hanging_indent.y_min - region_tolerance
        <= right.y1
        <= hanging_indent.y_max + region_tolerance
    )


def continues_hanging_indent_paragraph(previous: Line, current: Line, context: PageContext) -> bool:
    """Return whether current uses a learned hanging continuation margin."""
    if (
        not previous.text.strip()
        or not current.text.strip()
        or significant_size_change(previous, current)
        or not same_flow(previous, current, context)
        or not has_normal_advance(previous, current, context)
    ):
        return False

    font_size = current.font_size or context.font_size
    return any(
        (
            near_left_edge(previous.x1, hanging_indent.start_left, font_size)
            or near_left_edge(previous.x1, hanging_indent.continuation_left, font_size)
        )
        and near_left_edge(current.x1, hanging_indent.continuation_left, font_size)
        for hanging_indent in hanging_indents_for_boundary(previous, current, context)
    )


def begins_hanging_indent_paragraph(previous: Line, current: Line, context: PageContext) -> bool:
    """Return whether an outdented line follows a learned hanging continuation."""
    if (
        not previous.text.strip()
        or not is_prose_line(current)
        or significant_size_change(previous, current)
        or not same_flow(previous, current, context)
    ):
        return False

    font_size = current.font_size or context.font_size
    matching_pattern = any(
        (
            near_left_edge(previous.x1, hanging_indent.start_left, font_size)
            or near_left_edge(previous.x1, hanging_indent.continuation_left, font_size)
        )
        and near_left_edge(current.x1, hanging_indent.start_left, font_size)
        for hanging_indent in hanging_indents_for_boundary(previous, current, context)
    )
    if not matching_pattern:
        return False

    ratio = advance_ratio(previous, current)
    normal = context.normal_advance_ratio
    return ratio is not None and normal is not None and 0 < ratio <= normal + 1.0


def large_advance_supports_break(left: Line, right: Line, context: PageContext) -> bool:
    """Return whether visible spacing separates two paragraphs.

    A gap about as tall as a blank line does so on its own. A smaller one must
    follow a completed or unusually short line, or come with a visible change
    of size, as before a licence notice in small print below a full, open line
    of body text in lipics-64. Shortness is measured against the column of body
    text, so a blank line is the only evidence for smaller print laid out in
    a narrower measure, as in a letterhead.
    """
    if not has_large_advance(left, right, context):
        return False
    if has_blank_line_advance(left, right, context) or significant_size_change(left, right):
        return True
    column = column_for_line(left, context)
    if column is None:
        return False
    font_size = left.font_size or context.font_size
    return line_is_short(left, column, font_size) or ends_sentence(left.text)


def begins_first_line_indent(
    previous: Line,
    current: Line,
    following: Line | None,
    context: PageContext,
    previous_start: Line | None = None,
) -> bool:
    """Return whether current has the transient indent of a new paragraph's first line.

    following starts the next visual line, and previous_start begins the
    visual line ending with previous, if previous is a later piece, such as a
    citation after a formula: `GaV₄S₈²³.` in nature.
    """
    if (
        following is None
        or current.x1 is None
        or not (is_textual_line(previous) or is_textual_line(previous_start or previous))
        or not is_prose_line(current)
        or not is_prose_line(following)
        or not compatible_style(current, following)
    ):
        return False
    column = column_for_line(current, context)
    following_column = column_for_line(following, context)
    if column is None or following_column != column or column.line_count < MIN_COLUMN_LINES:
        return False

    font_size = current.font_size or context.font_size
    indent = current.x1 - column.left
    if not (
        font_size * MIN_FIRST_LINE_INDENT_EM <= indent <= font_size * MAX_FIRST_LINE_INDENT_EM
        and near(following.x1, column.left, font_size)
        and has_normal_advance(current, following, context)
    ):
        return False

    return line_is_short(previous, column, font_size) or ends_sentence(previous.text)


def aligned_open_continuation(left: Line, right: Line, context: PageContext) -> bool:
    """Return whether inset lines continue a right-aligned or centered open passage."""
    if left.x1 is None or right.x1 is None or left.x2 is None or right.x2 is None:
        return False
    column = column_for_line(right, context)
    if column is None:
        return False
    font_size = right.font_size or context.font_size
    both_inset = min(left.x1, right.x1) - column.left > font_size * MAX_FIRST_LINE_INDENT_EM
    right_edges_match = abs(left.x2 - right.x2) <= font_size * MARGIN_TOLERANCE_EM
    return both_inset and right_edges_match and not ends_sentence(left.text)


def aligned_inset_continuation(
    left: Line, right: Line, following: Line | None, context: PageContext
) -> bool:
    """Return whether a pdftext block edge splits an evenly spaced, left-aligned inset passage.

    The lines on both sides of the edge must share the left edge and style of
    the line following right, which pdftext keeps in right's block, and be no
    farther apart than right and following are. This joins the first line of
    a letterhead, such as "MINISTERIO" above "DE AGRICULTURA, PESCA", to the
    lines below it.
    """
    if (
        following is None
        or following.page_no != right.page_no
        or following.block_no != right.block_no
        or left.x1 is None
        or right.x1 is None
        or ends_sentence(left.text)
        or not compatible_style(right, following)
    ):
        return False
    column = column_for_line(right, context)
    if column is None:
        return False
    font_size = right.font_size or context.font_size
    edge_advance = advance_ratio(left, right)
    following_advance = advance_ratio(right, following)
    return (
        min(left.x1, right.x1) - column.left > font_size * MAX_FIRST_LINE_INDENT_EM
        and near(left.x1, right.x1, font_size)
        and near(following.x1, right.x1, font_size)
        and edge_advance is not None
        and following_advance is not None
        and 0 < edge_advance <= following_advance + UNIFORM_ADVANCE_TOLERANCE_EM
    )


def visual_line_start(line_list: list[Line], index: int) -> Line:
    """Return the first piece of the visual line ending with the line at index.

    Pieces share the vertical band of the last one and precede it on the left.
    Unlike chaining same_physical_line, this also passes stacked pieces such
    as the denominator of an inline fraction, which sits lower than the text.
    """
    last = line_list[index]
    start = last
    if last.x1 is None or last.y1 is None or last.y2 is None:
        return start
    font_size = max(last.font_size or 0.0, 1.0)
    for other in reversed(line_list[:index]):
        if (
            other.page_no != last.page_no
            or other.x2 is None
            or other.y1 is None
            or other.y2 is None
            or other.x2 > last.x1 + font_size * 0.25
        ):
            break
        overlap = min(other.y2, last.y2) - max(other.y1, last.y1)
        if overlap < min(other.y2 - other.y1, last.y2 - last.y1) * 0.5:
            break
        start = other
    return start


def next_visual_line(line_list: list[Line], index: int) -> Line | None:
    """Return the first piece of the visual line after the one containing the line at index.

    Later pieces of the same visual line, such as text resuming after inline
    math, follow on the right and share its vertical band, as for
    visual_line_start.
    """
    current = line_list[index]
    piece = current
    for other in line_list[index + 1 :]:
        if (
            other.page_no != current.page_no
            or piece.x2 is None
            or other.x1 is None
            or current.y1 is None
            or current.y2 is None
            or other.y1 is None
            or other.y2 is None
            or other.x1 < piece.x2 - max(current.font_size or 0.0, 1.0) * 0.25
        ):
            return other
        overlap = min(other.y2, current.y2) - max(other.y1, current.y1)
        if overlap < min(other.y2 - other.y1, current.y2 - current.y1) * 0.5:
            return other
        piece = other
    return None


def high_confidence_continuation(
    left: Line,
    right: Line,
    context: PageContext,
    left_start: Line | None = None,
    following: Line | None = None,
) -> bool:
    """Return whether geometry safely overrides a spurious pdftext block edge.

    left_start begins the visual line ending with left, if left is a later
    piece. following is the line after right, if any.
    """
    if (
        context.rhythm_sample_count < MIN_RHYTHM_SAMPLES
        or not is_prose_line(left)
        or not is_prose_line(right)
        or not same_flow(left, right, context)
        or not compatible_style(left, right)
        or not has_normal_advance(left, right, context)
    ):
        return False

    column = column_for_line(right, context)
    if column is None or column.line_count < MIN_COLUMN_LINES:
        return False
    font_size = right.font_size or context.font_size
    left_edges_match = near((left_start or left).x1, right.x1 or column.left, font_size)
    open_full_line = (
        left_edges_match and line_is_full(left, column, font_size) and not ends_sentence(left.text)
    )
    hyphenated_line = left_edges_match and ends_word_break_hyphen(left.text)
    return (
        open_full_line
        or hyphenated_line
        or aligned_open_continuation(left, right, context)
        or aligned_inset_continuation(left, right, following, context)
    )


def continues_running_text(
    previous: Line, current: Line, context: PageContext, previous_start: Line | None = None
) -> bool:
    """Return whether current continues a paragraph, whatever pdftext or the fonts suggest.

    previous_start begins the visual line ending with previous, if different.
    The previous line must fill the column at regular spacing, with current
    starting at the same left edge, or at the margin below an indented first
    line. Indents and gaps marking paragraphs are checked before this, so
    nothing but a pdftext block edge or a font change is left to suggest a break.

    A line ending a sentence must also reach the column's right edge closely,
    be followed by a line at the margin, and share its font: without an indent or
    a gap, real paragraphs are rarely set this way, as in intertrans and folie.
    """
    start = previous_start or previous
    # A visual line ending in a script-sized fragment, such as a formula, is
    # judged by its start, whose type matches the paragraph's.
    reference = start if is_script_sized(previous, start) else previous
    if (
        context.rhythm_sample_count < MIN_RHYTHM_SAMPLES
        or not is_prose_line(reference)
        or not is_prose_line(current)
        or NUMBERED_OR_BULLETED_START_PATTERN.match(current.text)
        or ITEM_LABEL_START_PATTERN.match(current.text)
        or not has_normal_advance(previous, current, context)
        or start.x1 is None
        or previous.x2 is None
        or current.x1 is None
        or current.x2 is None
    ):
        return False
    column = column_for_line(current, context)
    if (
        column is None
        or column.line_count < MIN_COLUMN_LINES
        or column_for_line(start, context) != column
        # The whole visual line must lie above current, not just its last piece.
        or min(previous.x2, current.x2) <= max(start.x1, current.x1)
    ):
        return False

    font_size = current.font_size or context.font_size
    previous_size = reference.font_size or context.font_size
    at_margin = near(current.x1, column.left, font_size)
    below_first_line_indent = (
        at_margin and 0 < start.x1 - column.left <= font_size * MAX_FIRST_LINE_INDENT_EM
    )
    if not line_is_full(previous, column, previous_size) or not (
        near(start.x1, current.x1, font_size) or below_first_line_indent
    ):
        return False
    if ends_sentence(previous.text):
        return (
            at_margin
            and compatible_style(reference, current)
            and column.right - previous.x2
            <= previous_size * CONTINUED_SENTENCE_END_MAX_SHORTFALL_EM
        )
    return compatible_style(reference, current) or differs_only_by_italics(reference, current)


def continues_in_lower_case(
    previous: Line, current: Line, context: PageContext, previous_start: Line | None = None
) -> bool:
    """Return whether current continues the open sentence of previous in lower case.

    previous_start begins the visual line ending with previous, if different.
    Unlike continues_running_text, previous need not fill its column, as in
    the short lines of lipics-64's licence notice: an open line end, a next
    line starting in lower case at the same left edge, the same typography,
    and regular spacing together leave only a pdftext block edge to suggest
    a break.
    """
    start = previous_start or previous
    if start.x1 is None or current.x1 is None:
        return False
    return (
        not ends_sentence(previous.text)
        and current.text[:1].islower()
        and not LOWER_CASE_ITEM_LABEL_START_PATTERN.match(current.text)
        and near(start.x1, current.x1, current.font_size or context.font_size)
        and compatible_style(previous, current)
        and has_normal_advance(previous, current, context)
    )


def continues_display_line(previous: Line, current: Line, context: PageContext) -> bool:
    """Return whether current continues a title or other display text from previous.

    Ragged or centered titles rarely fill their measure, so the usual evidence
    for a continued line is missing. Instead, both lines must be clearly larger
    than body text, share their font face and alignment, and follow the
    title's own tight leading.
    """
    if (
        previous.font_size is None
        or current.font_size is None
        or previous.x1 is None
        or previous.x2 is None
        or current.x1 is None
        or current.x2 is None
        or previous.y1 is None
        or current.y1 is None
        or not is_textual_line(previous)
        or not is_textual_line(current)
        or NUMBERED_OR_BULLETED_START_PATTERN.match(current.text)
    ):
        return False
    smaller = min(previous.font_size, current.font_size)
    larger = max(previous.font_size, current.font_size)
    if (
        smaller < context.font_size * DISPLAY_LINE_MIN_FONT_RATIO
        or larger > smaller * DISPLAY_LINE_MAX_SIZE_RATIO
        or normalized_font_name(previous.font_name) != normalized_font_name(current.font_name)
        or not 0 < current.y1 - previous.y1 <= larger * DISPLAY_LINE_MAX_ADVANCE_EM
    ):
        return False
    previous_center = (previous.x1 + previous.x2) / 2
    current_center = (current.x1 + current.x2) / 2
    return near(previous.x1, current.x1, larger) or near(previous_center, current_center, larger)


def changes_face_after_short_line(previous: Line, current: Line, context: PageContext) -> bool:
    """Return whether a short line is followed by text of a visibly different role.

    A change of both size and face after a deliberately short line separates
    items such as author names and affiliations, or a heading and its text, even
    when each style lasts only one line. One of the lines must be larger than
    body text; changes among smaller lines, as in address cards, are kept.
    """
    if (
        not is_textual_line(previous)
        or not is_textual_line(current)
        or not significant_size_change(previous, current)
        or normalized_font_name(previous.font_name) == normalized_font_name(current.font_name)
    ):
        return False
    larger = max(previous.font_size or 0.0, current.font_size or 0.0)
    if larger < context.font_size or not visibly_different_font_sizes(larger, context.font_size):
        return False
    column = column_for_line(previous, context)
    font_size = previous.font_size or context.font_size
    return column is not None and line_is_short(previous, column, font_size)


def same_face_fragment(previous: Line, current: Line) -> bool:
    """Return whether two same-line fragments adjoin in one font face."""
    if previous.x2 is None or current.x1 is None:
        return False
    font_size = max(previous.font_size or 0.0, current.font_size or 0.0)
    return (
        normalized_font_name(previous.font_name) == normalized_font_name(current.font_name)
        and current.x1 - previous.x2 <= font_size * MAX_SAME_FACE_FRAGMENT_GAP_EM
    )


def should_start_new_group(
    preceding: Line | None,
    previous: Line,
    current: Line,
    following: Line | None,
    context: PageContext,
    previous_start: Line | None = None,
    next_line: Line | None = None,
) -> bool:
    """Decide whether current begins a new page-local Markdown block.

    previous_start begins the visual line ending with previous, if different.
    next_line starts the visual line after current's, if current continues
    in later pieces; following is used otherwise.
    """
    if previous.page_no != current.page_no:
        return True
    pdftext_break = previous.block_no != current.block_no

    # Text continuing the same line at the same size stays in the block even
    # in another face, as after a run-in theorem label in lipics-64.
    if (
        same_running_text_line(previous, current)
        and is_prose_line(previous)
        and is_prose_line(current)
        and close_font_size(previous.font_size, current.font_size)
    ):
        return False
    if touches_script_fragment(previous, current):
        return False
    if same_physical_line(previous, current):
        return pdftext_break and not (
            is_prose_line(previous)
            and is_prose_line(current)
            and (compatible_style(previous, current) or same_face_fragment(previous, current))
        )
    # Display lines may be centered in a different column than they start in.
    if continues_display_line(previous, current, context):
        return False
    if not same_flow(previous, current, context):
        return pdftext_break and not continues_running_text(
            previous, current, context, previous_start
        )

    reliable_context = context.rhythm_sample_count >= MIN_RHYTHM_SAMPLES
    if reliable_context:
        if continues_hanging_indent_paragraph(previous, current, context):
            return False
        if begins_hanging_indent_paragraph(previous, current, context):
            return True

        previous_style_is_stable = preceding is None or compatible_style(preceding, previous)
        previous_starts_pdftext_block = preceding is None or preceding.block_no != previous.block_no
        current_style_is_stable = following is not None and compatible_style(current, following)
        if (
            is_prose_line(previous)
            and is_prose_line(current)
            and significant_style_change(previous, current)
            and current_style_is_stable
            and (previous_style_is_stable or previous_starts_pdftext_block)
            and (
                close_font_size(previous.font_size, context.font_size)
                or close_font_size(current.font_size, context.font_size)
            )
            and not continues_running_text(previous, current, context, previous_start)
        ):
            return True
        if (
            is_prose_line(previous)
            and is_prose_line(current)
            and large_advance_supports_break(previous, current, context)
        ):
            return True
        if begins_first_line_indent(
            previous, current, next_line or following, context, previous_start
        ):
            return True
        if changes_face_after_short_line(previous, current, context):
            return True
    if pdftext_break and (
        high_confidence_continuation(previous, current, context, previous_start, following)
        or continues_running_text(previous, current, context, previous_start)
        or continues_in_lower_case(previous, current, context, previous_start)
    ):
        return False
    return pdftext_break


def is_marker_line(
    pieces: list[Line], columns: tuple[ColumnContext, ...], font_size: float
) -> bool:
    """Return whether the pieces of a visual line form a marker line within a column.

    Replacement characters stand for undecoded glyphs, as in formulas, which
    may well be letters.
    """
    text = ''.join(piece.text for piece in pieces)
    left = pieces[0].x1
    right = pieces[-1].x2
    if (
        not text.strip()
        or has_alphanumeric(text)
        or '\ufffd' in text
        or left is None
        or right is None
    ):
        return False
    center = (left + right) / 2
    return any(
        abs(center - (column.left + column.right) / 2)
        <= font_size * MARKER_LINE_CENTER_TOLERANCE_EM
        and right - left <= column.width * MARKER_LINE_MAX_COLUMN_SHARE
        for column in columns
    )


def find_marker_lines(line_list: list[Line]) -> dict[int, int]:
    """Map the line IDs of marker lines to the first ID of their visual line.

    A visual line may consist of several pieces, such as three asterisks set at
    staggered heights. Columns follow the lines with letters or digits only, as
    the pieces of a marker would otherwise form a column on sparse pages.
    """
    marker_lines: dict[int, int] = {}
    for _, page_group in groupby(line_list, key=lambda line_obj: line_obj.page_no):
        page_lines = list(page_group)
        font_size = dominant_page_font_size(page_lines)
        columns = build_columns(
            [line_obj for line_obj in page_lines if has_alphanumeric(line_obj.text)], font_size
        )
        start = 0
        while start < len(page_lines):
            end = start + 1
            while end < len(page_lines) and same_physical_line(
                page_lines[end - 1], page_lines[end]
            ):
                end += 1
            pieces = page_lines[start:end]
            if is_marker_line(pieces, columns, font_size):
                marker_lines.update((id(piece), id(pieces[0])) for piece in pieces)
            start = end
    return marker_lines


def segment_page(
    line_list: list[Line],
    heading_lines: dict[int, int] | None = None,
    list_item_lines: dict[int, int] | None = None,
    passage_lines: dict[int, int] | None = None,
    marker_lines: dict[int, int] | None = None,
) -> list[list[Line]]:
    """Segment a page; heading_lines maps confirmed line IDs to their title's first ID.

    list_item_lines likewise maps the line IDs of list items to their first
    line's ID, so each item becomes a group of its own. So does passage_lines
    for passages set off line by line, such as quoted verse, and marker_lines
    for marker lines, such as ornaments.
    """
    if not line_list:
        return []
    context = build_page_context(line_list)
    heading_lines = heading_lines or {}
    list_item_lines = list_item_lines or {}
    passage_lines = passage_lines or {}
    marker_lines = marker_lines or {}
    groups: list[list[Line]] = [[line_list[0]]]

    for index, current in enumerate(line_list[1:], start=1):
        preceding = line_list[index - 2] if index >= 2 else None
        previous = line_list[index - 1]
        following = line_list[index + 1] if index + 1 < len(line_list) else None
        previous_heading = heading_lines.get(id(previous))
        current_heading = heading_lines.get(id(current))
        previous_item = list_item_lines.get(id(previous))
        current_item = list_item_lines.get(id(current))
        if previous_heading is not None or current_heading is not None:
            starts_group = previous_heading != current_heading
        elif previous_item is not None or current_item is not None:
            starts_group = previous_item != current_item
        elif id(previous) in passage_lines or id(current) in passage_lines:
            starts_group = passage_lines.get(id(previous)) != passage_lines.get(id(current))
        elif id(previous) in marker_lines or id(current) in marker_lines:
            starts_group = marker_lines.get(id(previous)) != marker_lines.get(id(current))
        else:
            starts_group = should_start_new_group(
                preceding,
                previous,
                current,
                following,
                context,
                visual_line_start(line_list, index - 1),
                next_visual_line(line_list, index),
            )
        if starts_group:
            groups.append([])
        groups[-1].append(current)
    return groups


def segment_lines(
    line_list: list[Line],
    heading_lines: dict[int, int] | None = None,
    list_item_lines: dict[int, int] | None = None,
    passage_lines: dict[int, int] | None = None,
    marker_lines: dict[int, int] | None = None,
) -> list[list[Line]]:
    """Segment ordered lines without ever joining text across page boundaries."""
    groups: list[list[Line]] = []
    current_page: list[Line] = []
    current_page_no: int | None = None

    for line_obj in line_list:
        if current_page_no is not None and line_obj.page_no != current_page_no:
            groups.extend(
                segment_page(
                    current_page, heading_lines, list_item_lines, passage_lines, marker_lines
                )
            )
            current_page = []
        current_page.append(line_obj)
        current_page_no = line_obj.page_no

    groups.extend(
        segment_page(current_page, heading_lines, list_item_lines, passage_lines, marker_lines)
    )
    return groups
