"""Recognize the items of bulleted and numbered lists among body lines.

An item starts with a marker at the start of a line and may continue on
following lines indented past the marker. Unambiguous bullet glyphs mark items
on their own. Dashes, asterisks, and numbers also start ordinary lines, as
when a parenthetical dash or a date wraps to the next line, so they need
several aligned items, consecutive numbers, and a deliberate break before the
first item.
"""

import re
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Literal

from frompdf.models import Line
from frompdf.segmentation import (
    PageContext,
    build_page_context,
    column_for_line,
    has_normal_advance,
    line_is_full,
    same_physical_line,
    visibly_different_font_sizes,
)

STRONG_BULLETS = '•◦▪▫●○■□‣⁃➢❖✓'
WEAK_BULLETS = '-–—*'
LIST_MARKER_PATTERN = re.compile(
    rf'(?P<bullet>[{re.escape(STRONG_BULLETS + WEAK_BULLETS)}])\s+'
    r'|\((?P<parenthesized>\d{1,3})\)\s+'
    r'|(?P<number>\d{1,3})(?P<delimiter>[.)]?)\s+'
)

# Item markers align within this many ems, allowing for right-aligned numbers
# such as 9 and 10 in lipics-51's references.
MARKER_ALIGNMENT_EM = 1.0
# Continuation lines start at least this many ems right of the marker.
MIN_CONTINUATION_INDENT_EM = 0.5
# Continuation lines of one list align within this many ems.
CONTINUATION_ALIGNMENT_EM = 0.25
MIN_CONTINUATION_ALIGNMENT = 2.0
# Lines starting with punctuation may protrude into the margin by up to this
# many ems, as the quote mark starting `’20)` in lipics-64's references.
MAX_PUNCTUATION_PROTRUSION_EM = 0.5
# Lists marked by dashes or numbers need several items. Numbers without a
# delimiter label the entries of reference lists, but also the lines of
# algorithms, such as lipics-51's Algorithm 1. Most reference entries wrap
# onto hanging-indented continuation lines, unlike numbered lines of code.
MIN_WEAK_ITEMS = 2
MIN_BARE_NUMBER_ITEMS = 3
MIN_BARE_NUMBER_WRAPPED_SHARE = 0.5

MarkerKind = Literal['strong', 'weak', 'ordered', 'bare']


@dataclass(frozen=True)
class ListMarker:
    """A list marker starting a line, with the Markdown marker that replaces it."""

    kind: MarkerKind
    # The bullet glyph, or the delimiter following a number.
    glyph: str
    number: int | None
    # The length of the marker and the whitespace following it.
    length: int

    @property
    def markdown(self) -> str:
        """Return the Markdown marker, keeping the number and `)` delimiter of ordered items."""
        if self.number is None:
            return '-'
        return f'{self.number}{")" if self.glyph in {")", "()"} else "."}'


@dataclass
class ListItems:
    """Recognized list items.

    item_of_line maps the ID of each line within an item to the ID of the
    item's first line, and markers maps the ID of each first line to its marker.
    """

    item_of_line: dict[int, int] = field(default_factory=dict)
    markers: dict[int, ListMarker] = field(default_factory=dict)


@dataclass
class ListRun:
    """Consecutive candidate items of one list, before it is accepted."""

    marker: ListMarker
    marker_offset: float
    font_size: float
    set_off: bool
    items: list[list[Line]]
    markers: list[ListMarker]
    continuation_offset: float | None = None


def parse_list_marker(text: str) -> ListMarker | None:
    """Return the list marker starting text, if it is followed by item text."""
    match = LIST_MARKER_PATTERN.match(text)
    if match is None or not any(char.isalnum() for char in text[match.end() :]):
        return None
    bullet = match.group('bullet')
    if bullet is not None:
        kind: MarkerKind = 'strong' if bullet in STRONG_BULLETS else 'weak'
        return ListMarker(kind, bullet, None, match.end())
    parenthesized = match.group('parenthesized')
    if parenthesized is not None:
        return ListMarker('ordered', '()', int(parenthesized), match.end())
    delimiter = match.group('delimiter')
    kind = 'ordered' if delimiter else 'bare'
    return ListMarker(kind, delimiter, int(match.group('number')), match.end())


def column_offset(line_obj: Line, context: PageContext) -> float | None:
    """Return a line's distance from the left edge of its page column."""
    column = column_for_line(line_obj, context)
    if column is None or line_obj.x1 is None:
        return None
    return line_obj.x1 - column.left


def is_set_off(
    previous: Line | None, current: Line, context: PageContext, heading_lines: dict[int, int]
) -> bool:
    """Return whether a line starts after a deliberate break, not as a wrapped line."""
    if (
        previous is None
        or previous.page_no != current.page_no
        or previous.block_no != current.block_no
        or id(previous) in heading_lines
        or previous.text.rstrip().endswith(':')
        or not has_normal_advance(previous, current, context)
    ):
        return True
    column = column_for_line(previous, context)
    font_size = previous.font_size or context.font_size
    return column is None or not line_is_full(previous, column, font_size)


def aligns_with_continuation(run: ListRun, line_obj: Line, offset: float) -> bool:
    """Return whether a line aligns with the continuation lines seen so far."""
    if run.continuation_offset is None:
        return True
    font_size = line_obj.font_size or run.font_size
    tolerance = max(MIN_CONTINUATION_ALIGNMENT, font_size * CONTINUATION_ALIGNMENT_EM)
    protrusion = (
        font_size * MAX_PUNCTUATION_PROTRUSION_EM
        if line_obj.text and not line_obj.text[0].isalnum()
        else 0.0
    )
    return -tolerance - protrusion <= offset - run.continuation_offset <= tolerance


def continues_marker(run: ListRun, marker: ListMarker) -> bool:
    """Return whether a marker can start the next item of a run."""
    last = run.markers[-1]
    if marker.kind != last.kind or marker.glyph != last.glyph:
        return False
    return last.number is None or marker.number == last.number + 1


def wraps(item: list[Line]) -> bool:
    """Return whether an item continues on another line than its first."""
    return any(not same_physical_line(left, right) for left, right in pairwise(item))


def accepted(run: ListRun) -> bool:
    """Return whether a run has enough evidence for a list."""
    kind = run.marker.kind
    if kind == 'strong':
        return True
    if not run.set_off:
        return False
    if kind == 'bare':
        wrapped = sum(wraps(item) for item in run.items)
        return (
            len(run.items) >= MIN_BARE_NUMBER_ITEMS
            and wrapped > len(run.items) * MIN_BARE_NUMBER_WRAPPED_SHARE
        )
    return len(run.items) >= MIN_WEAK_ITEMS


def find_list_items(line_list: list[Line], heading_lines: dict[int, int]) -> ListItems:
    """Find list items among ordered body lines, which may span pages.

    Positions are compared relative to the page column, so items continue
    across pages with different margins. Lines of headings never belong to
    items.
    """
    contexts: dict[int, PageContext] = {}
    lines_by_page: dict[int, list[Line]] = {}
    for line_obj in line_list:
        lines_by_page.setdefault(line_obj.page_no, []).append(line_obj)
    for page_no, page_lines in lines_by_page.items():
        contexts[page_no] = build_page_context(page_lines)

    result = ListItems()
    run: ListRun | None = None

    def close_run() -> None:
        if run is not None and accepted(run):
            for item, marker in zip(run.items, run.markers, strict=True):
                result.markers[id(item[0])] = marker
                for line_obj in item:
                    result.item_of_line[id(line_obj)] = id(item[0])

    for index, line_obj in enumerate(line_list):
        previous = line_list[index - 1] if index else None
        context = contexts[line_obj.page_no]
        offset = column_offset(line_obj, context)
        font_size = line_obj.font_size or context.font_size
        heading = id(line_obj) in heading_lines
        same_line = previous is not None and same_physical_line(previous, line_obj)

        marker = None
        if not heading and not same_line and offset is not None:
            marker = parse_list_marker(line_obj.text)

        if run is not None and not heading and offset is not None:
            aligned = abs(offset - run.marker_offset) <= font_size * MARKER_ALIGNMENT_EM
            if marker is not None and aligned and continues_marker(run, marker):
                run.items.append([line_obj])
                run.markers.append(marker)
                continue
            if same_line and previous is run.items[-1][-1]:
                run.items[-1].append(line_obj)
                continue
            if (
                not visibly_different_font_sizes(line_obj.font_size, run.font_size)
                and offset >= run.marker_offset + font_size * MIN_CONTINUATION_INDENT_EM
                and aligns_with_continuation(run, line_obj, offset)
                and (
                    previous is None
                    or previous.page_no != line_obj.page_no
                    or has_normal_advance(previous, line_obj, context)
                )
            ):
                if run.continuation_offset is None:
                    run.continuation_offset = offset
                run.items[-1].append(line_obj)
                continue

        close_run()
        run = None
        # Larger text, such as a numbered heading, does not start a list.
        larger = font_size > context.font_size and visibly_different_font_sizes(
            font_size, context.font_size
        )
        if marker is not None and offset is not None and not larger:
            run = ListRun(
                marker=marker,
                marker_offset=offset,
                font_size=font_size,
                set_off=is_set_off(previous, line_obj, context, heading_lines),
                items=[[line_obj]],
                markers=[marker],
            )
    close_run()
    return result
