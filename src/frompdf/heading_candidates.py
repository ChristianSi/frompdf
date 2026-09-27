"""Conservative heading evidence that needs the original line geometry."""

import re
from collections import defaultdict

from frompdf.models import Line
from frompdf.segmentation import (
    MIN_COLUMN_LINES,
    MIN_RHYTHM_SAMPLES,
    ColumnContext,
    PageContext,
    build_page_context,
    close_font_size,
    column_for_line,
    normalized_font_name,
)

# Small-cap glyph heights can be about half the body height when a PDF supplies
# placeholder font sizes. Only the guarded small-cap path accepts such sizes.
SMALLCAPS_PATTERN = re.compile(r'small[-_]?caps', re.IGNORECASE)
ITALIC_PATTERN = re.compile(r'italic|oblique|[._-](?:i|it)(?:mt)?$', re.IGNORECASE)
MAX_HEADING_LINES = 3
MAX_HEADING_CHARACTERS = 250
# Allow modest glyph-height variation (notably accented capitals), but do not
# merge adjacent titles of visibly different sizes into one heading.
MAX_HEADING_SIZE_RATIO = 1.25
# Small-cap lines containing a full capital can have taller bounding boxes
# than adjacent all-small-cap lines, despite sharing the same visual style.
MAX_SMALLCAPS_SIZE_RATIO = 1.4


def heading_style(line: Line, body_size: float) -> str | None:
    """Return a possible title style, without treating it alone as evidence."""
    text = line.text.strip()
    if (
        line.font_size is None
        or sum(char.isalpha() for char in text) < 4
        or text.endswith(('.', '!', '?', ':', ';', ',', '-'))
    ):
        return None
    name = line.font_name or ''
    if SMALLCAPS_PATTERN.search(name) and line.font_size >= body_size * 0.5:
        return 'smallcaps'
    # Ordinary caps/italics must remain near body size. Smaller glyphs only
    # qualify through explicit small-cap metadata and the layout checks below.
    if text.isupper() and line.font_size >= body_size * 0.85:
        return 'caps'
    if ITALIC_PATTERN.search(name) and line.font_size >= body_size * 0.9:
        return 'italic'
    return None


def centered_in_column(line: Line, column: ColumnContext, body_size: float) -> bool:
    """Require symmetric insets, not just indentation or a short line."""
    if line.x1 is None or line.x2 is None or line.y1 is None or line.y2 is None:
        return False
    return (
        # A third of a body em allows rounding and slightly asymmetric glyph
        # boxes; a full em of inset excludes nearly full-width prose lines.
        abs((line.x1 + line.x2 - column.left - column.right) / 2) <= body_size * 0.35
        and min(line.x1 - column.left, column.right - line.x2) >= body_size
    )


def starts_body_passage(line: Line, column: ColumnContext, body_size: float) -> bool:
    """Require a substantial line starting at the body or first-line margin."""
    return (
        line.x1 is not None
        and line.x2 is not None
        and column.left - body_size * 0.3 <= line.x1 <= column.left + body_size * 1.5
        and line.x2 >= column.left + column.width * 0.65
        and sum(char.isalpha() for char in line.text) >= 20
        and not line.text.isupper()
    )


def candidate_has_boundaries(
    page: list[Line],
    start: int,
    end: int,
    style: str,
    context: PageContext,
    column: ColumnContext,
) -> bool:
    """Require whitespace and a following passage in the same established column."""
    first, last = page[start], page[end - 1]
    if end == len(page):
        return False
    following = page[end]
    assert first.y1 is not None and last.y2 is not None
    if following.y1 is None or following.y1 <= last.y2:
        return False
    if start:
        previous = page[start - 1]
        # Require more than a blank body-glyph height above an interior title.
        if previous.y2 is None or first.y1 - previous.y2 < context.font_size * 1.25:
            return False

    if style == 'italic':
        # Single short labels above smaller notes/references, not salutations,
        # quotations, captions, or ordinary italic paragraphs.
        return (
            end - start == 1
            and len(first.text) <= 60
            and len(first.text.split()) <= 6
            and first.font_size is not None
            and following.font_size is not None
            and following.font_size <= first.font_size * 0.85
            and starts_body_passage(following, column, context.font_size)
        )

    # Below caps, require visible separation even when the title's small glyphs
    # have already contributed extra whitespace relative to ordinary prose.
    if following.y1 - last.y2 < context.font_size * 0.75:
        return False
    if starts_body_passage(following, column, context.font_size):
        return True

    # A widely separated title may introduce a short centered salutation or
    # byline before the body begins. Do not absorb those lines into the title.
    if following.y1 - last.y2 < context.font_size * 3:
        return False
    for line in page[end : end + 4]:
        if starts_body_passage(line, column, context.font_size):
            return True
        if not centered_in_column(line, column, context.font_size):
            return False
    return False


def page_heading_lines(page: list[Line], context: PageContext) -> dict[int, int]:
    """Map each confirmed heading line's identity to its first line's identity."""
    if context.rhythm_sample_count < MIN_RHYTHM_SAMPLES or context.normal_advance_ratio is None:
        return {}
    # Column estimates alone can describe map labels. Require several actual
    # body-sized prose lines as well before using a column as heading evidence.
    columns = {
        column
        for column in context.columns
        if sum(
            line.font_size is not None
            and close_font_size(line.font_size, context.font_size)
            and starts_body_passage(line, column, context.font_size)
            for line in page
        )
        >= MIN_COLUMN_LINES
    }
    found: dict[int, int] = {}
    start = 0
    while start < len(page):
        first = page[start]
        style = heading_style(first, context.font_size)
        column = column_for_line(first, context)
        if style is None or column not in columns or column is None:
            start += 1
            continue
        if not centered_in_column(first, column, context.font_size):
            start += 1
            continue
        end = start + 1
        assert first.font_size is not None
        # Compare advances to the body rhythm: small-cap glyph heights would
        # otherwise turn ordinary title continuation lines into paragraph gaps.
        max_advance = context.font_size * context.normal_advance_ratio * 1.5
        max_size_ratio = (
            MAX_SMALLCAPS_SIZE_RATIO if style == 'smallcaps' else MAX_HEADING_SIZE_RATIO
        )
        while end < len(page):
            previous, current = page[end - 1], page[end]
            if (
                heading_style(current, context.font_size) != style
                or current.font_size is None
                or max(first.font_size, current.font_size)
                > min(first.font_size, current.font_size) * max_size_ratio
                or normalized_font_name(first.font_name) != normalized_font_name(current.font_name)
                or not centered_in_column(current, column, context.font_size)
                or previous.y1 is None
                or current.y1 is None
                or not 0 < current.y1 - previous.y1 <= max_advance
            ):
                break
            end += 1
        # Examine the whole run, so a long passage cannot qualify via its tail.
        if (
            end - start <= MAX_HEADING_LINES
            and sum(len(line.text) + 1 for line in page[start:end]) - 1 <= MAX_HEADING_CHARACTERS
            and candidate_has_boundaries(page, start, end, style, context, column)
        ):
            found.update((id(line), id(first)) for line in page[start:end])
        start = end
    return found


def find_typographic_heading_lines(line_list: list[Line]) -> dict[int, int]:
    """Find centered headings after page-edge and footnote removal."""
    pages: dict[int, list[Line]] = defaultdict(list)
    for line in line_list:
        pages[line.page_no].append(line)
    found: dict[int, int] = {}
    for page in pages.values():
        found.update(page_heading_lines(page, build_page_context(page)))
    return found
