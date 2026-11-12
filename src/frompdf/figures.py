"""Recognize the text of captioned figures and lay it out as a grid of characters.

Plots and diagrams are drawn, but their labels, such as tick values, axis
titles, and legends, are often text. In the flow of the document, these
short lines would turn into scattered paragraphs and headings. Instead, the
lines around the drawings of a figure with a caption are taken out of the
flow and laid out at their approximate positions in a block of preformatted
text, which keeps hints of the figure's structure, such as the axes of plots
and their legends.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median

from frompdf.line_features import close_font_size, is_prose_line
from frompdf.models import Line
from frompdf.page_context import (
    MAX_FIRST_LINE_INDENT_EM,
    dominant_page_font_size,
    established_left_edges,
)
from frompdf.rules import DrawingBox
from frompdf.tables import TableLayout

# A caption starts with a figure label and number, as in "Fig. 3",
# "Figure 3:", "Abb. 3", or "Figura 3".
CAPTION_PATTERN = re.compile(r'(?:Fig(?:ure|ura)?|FIG(?:URE)?|Abb(?:ildung)?)\.?\s*\d+\b')

# Drawings closer than this, in points, form one region, such as the frame,
# curves, and ticks of one plot.
DRAWING_JOIN_GAP = 3.0
# A region at least this large in both directions, in body ems, is a panel of
# a figure. Smaller ones are rules, ticks, or ornaments.
MIN_PANEL_SIZE_EM = 3.0
# Labels lie around the drawings of a panel, up to this far from them in
# body ems, as tick values and axis titles beside or below a plot, which
# reach about four ems beyond the frame of a plot in nature.
LABEL_MARGIN_EM = 4.5
# A caption starts at most this far below (or ends this far above) the
# drawings of its figure, in body ems, leaving room for labels in between.
MAX_CAPTION_GAP_EM = 6.0

# A line continues the body line above it at most this far below, in ems,
# about the line spacing of body text.
MAX_BODY_ADVANCE_EM = 1.6

# A caption continues in lines directly below its previous line, separated by
# less than this in ems of its size.
CAPTION_CONTINUATION_GAP_EM = 1.0

# The grid of a figure is at most this many characters wide. Wider figures are
# laid out more coarsely.
MAX_FIGURE_COLUMNS = 100
# Labels whose box is this much taller than wide, relative to the font size,
# run vertically, as axis titles beside a plot.
VERTICAL_MIN_HEIGHT_EM = 2.0
# A label colliding with others moves at most this many rows down or up.
MAX_ROW_SHIFT = 4


@dataclass(frozen=True)
class FigureLayout:
    """A captioned figure: the lines of its text and of its caption.

    A figure drawn without text, as an image, has no lines but its caption.
    top and bottom delimit the figure on its page, including its caption.
    """

    page_no: int
    lines: list[Line]
    caption_lines: list[Line]
    top: float
    bottom: float

    @property
    def caption(self) -> Line:
        """Return the first line of the caption."""
        return self.caption_lines[0]


def boxes_near(first: DrawingBox, second: DrawingBox, gap: float) -> bool:
    """Return whether two boxes overlap or are at most gap apart."""
    return (
        first[0] <= second[2] + gap
        and second[0] <= first[2] + gap
        and first[1] <= second[3] + gap
        and second[1] <= first[3] + gap
    )


def contains(outer: DrawingBox, inner: DrawingBox) -> bool:
    """Return whether a box lies entirely within another."""
    return (
        outer[0] <= inner[0]
        and inner[2] <= outer[2]
        and outer[1] <= inner[1]
        and inner[3] <= outer[3]
    )


def union_box(first: DrawingBox, second: DrawingBox) -> DrawingBox:
    """Return the box enclosing two boxes."""
    return (
        min(first[0], second[0]),
        min(first[1], second[1]),
        max(first[2], second[2]),
        max(first[3], second[3]),
    )


def find_root(parent: list[int], index: int) -> int:
    """Return the root of an index in a union-find forest, halving the path to it."""
    while parent[index] != index:
        parent[index] = parent[parent[index]]
        index = parent[index]
    return index


def join_boxes(boxes: Sequence[DrawingBox], gap: float) -> list[DrawingBox]:
    """Join boxes that overlap or are at most gap apart, until none are.

    Each round sweeps the boxes from left to right, comparing each only with
    those not yet ending left of it, so dense drawings, such as scatter plots
    with many marks, stay fast.
    """
    current = list(boxes)
    while True:
        parent = list(range(len(current)))
        active: list[int] = []
        for index in sorted(range(len(current)), key=lambda index: current[index][0]):
            box = current[index]
            active = [other for other in active if current[other][2] + gap >= box[0]]
            for other in active:
                if boxes_near(box, current[other], gap):
                    parent[find_root(parent, index)] = find_root(parent, other)
            active.append(index)
        components: dict[int, DrawingBox] = {}
        for index, box in enumerate(current):
            key = find_root(parent, index)
            components[key] = union_box(components[key], box) if key in components else box
        if len(components) == len(current):
            return list(components.values())
        current = list(components.values())


def figure_panels(
    drawings: Sequence[DrawingBox], body_size: float, tables: Sequence[TableLayout], page_no: int
) -> list[DrawingBox]:
    """Return the regions of drawings large enough to be panels of figures.

    Regions overlapping a table belong to it, such as its rules.
    """
    min_size = body_size * MIN_PANEL_SIZE_EM
    table_boxes = [
        (0.0, frame.top, float('inf'), frame.bottom)
        for table in tables
        for frame in table.frames
        if frame.page_no == page_no
    ]
    return [
        region
        for region in join_boxes(drawings, DRAWING_JOIN_GAP)
        if region[2] - region[0] >= min_size
        and region[3] - region[1] >= min_size
        and not any(boxes_near(region, table_box, 0.0) for table_box in table_boxes)
    ]


def line_box(line: Line) -> DrawingBox | None:
    """Return the box of a line, if fully known."""
    if line.x1 is None or line.y1 is None or line.x2 is None or line.y2 is None:
        return None
    return line.x1, line.y1, line.x2, line.y2


def is_body_line(line: Line, body_size: float, body_edges: Sequence[float]) -> bool:
    """Return whether a line belongs to the body text, starting at or near a body margin.

    Vertical lines, such as axis titles beside a plot, never do.
    """
    if (
        line.x1 is None
        or is_vertical(line)
        or not is_prose_line(line)
        or not close_font_size(line.font_size, body_size)
    ):
        return False
    indent = (line.font_size or body_size) * MAX_FIRST_LINE_INDENT_EM
    return any(-1.5 <= line.x1 - edge <= indent for edge in body_edges)


def find_caption(figure: DrawingBox, page_lines: Sequence[Line], body_size: float) -> Line | None:
    """Return the first line of the nearest caption below a figure, or else above it.

    The caption must overlap the figure horizontally.
    """
    max_gap = body_size * MAX_CAPTION_GAP_EM
    below: list[tuple[float, Line]] = []
    above: list[tuple[float, Line]] = []
    for line in page_lines:
        box = line_box(line)
        if (
            box is None
            or not CAPTION_PATTERN.match(line.text)
            or box[2] <= figure[0]
            or figure[2] <= box[0]
        ):
            continue
        if -max_gap / 2 <= box[1] - figure[3] <= max_gap:
            below.append((box[1] - figure[3], line))
        elif 0 <= figure[1] - box[3] <= max_gap:
            above.append((figure[1] - box[3], line))
    for candidates in (below, above):
        if candidates:
            return min(candidates, key=lambda item: item[0])[1]
    return None


def assign_captions(
    panels: Sequence[DrawingBox], page_lines: Sequence[Line], body_size: float
) -> dict[DrawingBox, Line]:
    """Return the caption of each panel that has one.

    A panel has the nearest caption within reach below, or else above. Panels
    without one take that of the nearest panel close enough for their labels
    to touch, as the upper panels of a figure whose caption is below the lower
    ones.
    """
    reach = 2 * body_size * LABEL_MARGIN_EM
    captions: dict[DrawingBox, Line] = {}
    for panel in panels:
        caption = find_caption(panel, page_lines, body_size)
        if caption is not None:
            captions[panel] = caption
    changed = True
    while changed:
        changed = False
        for panel in panels:
            if panel in captions:
                continue
            neighbors = [
                other for other in captions if other != panel and boxes_near(panel, other, reach)
            ]
            if neighbors:
                nearest = min(neighbors, key=lambda other: box_distance(panel, other))
                captions[panel] = captions[nearest]
                changed = True
    return captions


def box_distance(first: DrawingBox, second: DrawingBox) -> float:
    """Return the largest of the horizontal and vertical gaps between two boxes."""
    return max(
        first[0] - second[2], second[0] - first[2], first[1] - second[3], second[1] - first[3], 0.0
    )


def find_body_lines(page_lines: Sequence[Line], body_size: float) -> set[int]:
    """Return the IDs of lines of body text on a page.

    These are lines of prose at body size starting at or near a margin, those
    set larger than the body, as headings, and those continuing a body line
    directly above them in reading order, as a short last line of a paragraph.
    """
    edges = established_left_edges(
        [line for line in page_lines if close_font_size(line.font_size, body_size)], body_size
    )
    body: set[int] = set()
    previous: Line | None = None
    for line in page_lines:
        if (
            is_body_line(line, body_size, edges)
            or is_larger_prose(line, body_size)
            or (previous is not None and id(previous) in body and continues_body(previous, line))
        ):
            body.add(id(line))
        previous = line
    return body


def is_larger_prose(line: Line, body_size: float) -> bool:
    """Return whether a line of prose is set larger than the body, as a heading."""
    return (
        is_prose_line(line)
        and not is_vertical(line)
        and line.font_size is not None
        and line.font_size > body_size
        and not close_font_size(line.font_size, body_size)
    )


def continues_body(previous: Line, line: Line) -> bool:
    """Return whether a line continues the body line above it, as the next line of a paragraph."""
    if (
        previous.x1 is None
        or previous.y1 is None
        or line.x1 is None
        or line.y1 is None
        or is_vertical(line)
        or not close_font_size(line.font_size, previous.font_size)
    ):
        return False
    font_size = previous.font_size or 1.0
    return (
        0 < line.y1 - previous.y1 <= font_size * MAX_BODY_ADVANCE_EM
        and abs(line.x1 - previous.x1) <= font_size * MAX_FIRST_LINE_INDENT_EM
    )


def continues_caption(last: Line, line: Line) -> bool:
    """Return whether a line continues a caption whose last line so far is last.

    It continues the visual line of last, or starts directly below it in the
    same size.
    """
    if (
        line.page_no != last.page_no
        or last.y1 is None
        or last.y2 is None
        or line.y1 is None
        or line.y2 is None
        or not close_font_size(line.font_size, last.font_size)
        or CAPTION_PATTERN.match(line.text)
    ):
        return False
    if line.y1 < last.y2 and last.y1 < line.y2:
        return True
    return 0 <= line.y1 - last.y2 <= (last.font_size or 0.0) * CAPTION_CONTINUATION_GAP_EM


def caption_lines(first: Line, page_lines: Sequence[Line]) -> list[Line]:
    """Return the lines of the caption starting with first, following it in reading order."""
    start = next(index for index, line in enumerate(page_lines) if line is first)
    lines = [first]
    for line in page_lines[start + 1 :]:
        if not continues_caption(lines[-1], line):
            break
        lines.append(line)
    return lines


def page_figures(
    page_lines: Sequence[Line],
    drawings: Sequence[DrawingBox],
    body_size: float,
    tables: Sequence[TableLayout],
    used: set[int],
) -> list[FigureLayout]:
    """Return the captioned figures of a page whose lines are not yet used."""
    page_no = page_lines[0].page_no
    margin = body_size * LABEL_MARGIN_EM
    panels = figure_panels(drawings, body_size, tables, page_no)
    by_caption: dict[int, tuple[Line, list[DrawingBox]]] = {}
    for panel, caption in assign_captions(panels, page_lines, body_size).items():
        by_caption.setdefault(id(caption), (caption, []))[1].append(panel)

    body_lines = find_body_lines(page_lines, body_size)
    layouts: list[FigureLayout] = []
    for caption, parts in by_caption.values():
        caption_box = line_box(caption)
        assert caption_box is not None
        # Overlapping areas around panels are joined, so labels spanning
        # panels, as their letters set on one line, lie within one area.
        areas = join_boxes(
            [
                (part[0] - margin, part[1] - margin, part[2] + margin, part[3] + margin)
                for part in parts
            ],
            0.0,
        )
        caption_below = caption_box[1] >= min(part[3] for part in parts) - margin
        lines: list[Line] = []
        for line in page_lines:
            box = line_box(line)
            if (
                box is None
                or id(line) in used
                or CAPTION_PATTERN.match(line.text)
                or id(line) in body_lines
                or (caption_below and box[3] > caption_box[1])
                or (not caption_below and box[1] < caption_box[3])
                or not any(contains(area, box) for area in areas)
            ):
                continue
            lines.append(line)
        captions = caption_lines(caption, page_lines)
        used.update(id(line) for line in [*lines, *captions])
        boxes = [box for box in map(line_box, [*lines, *captions]) if box is not None]
        layouts.append(
            FigureLayout(
                page_no=page_no,
                lines=lines,
                caption_lines=captions,
                top=min([part[1] for part in parts] + [box[1] for box in boxes]),
                bottom=max([part[3] for part in parts] + [box[3] for box in boxes]),
            )
        )
    return layouts


def find_figures(
    lines: Sequence[Line],
    drawings_by_page: dict[int, list[DrawingBox]],
    tables: Sequence[TableLayout] = (),
) -> list[FigureLayout]:
    """Return the captioned figures whose text lies around their drawings, in page order.

    Lines of tables are no figure text.
    """
    body_size = dominant_page_font_size(list(lines))
    table_lines = {id(line) for table in tables for line in table.lines}
    figures: list[FigureLayout] = []
    for page_no in sorted(drawings_by_page):
        page_lines = [
            line for line in lines if line.page_no == page_no and id(line) not in table_lines
        ]
        if not page_lines:
            continue
        used: set[int] = set()
        page_layouts = page_figures(page_lines, drawings_by_page[page_no], body_size, tables, used)
        figures.extend(sorted(page_layouts, key=lambda figure: figure.top))
    return figures


def is_vertical(line: Line) -> bool:
    """Return whether a line runs vertically, being much taller than wide."""
    box = line_box(line)
    if box is None or len(line.text.strip()) < 2:
        return False
    font_size = line.font_size or 1.0
    height = box[3] - box[1]
    return height >= font_size * VERTICAL_MIN_HEIGHT_EM and height > 2 * (box[2] - box[0])


def figure_grid(lines: Sequence[Line]) -> list[str]:
    """Lay out the text of lines at their approximate positions in rows of characters.

    Cells are as wide as the median character and as tall as the median line
    of horizontal text. Vertical text is written horizontally, centered on its
    position. Labels colliding with others move to the nearest free row.
    Leading and trailing blank rows, and repeated blank rows, are dropped.
    """
    placed = [(line, line_box(line)) for line in lines if line.text.strip()]
    placed = [(line, box) for line, box in placed if box is not None]
    if not placed:
        return []
    horizontal = [(line, box) for line, box in placed if not is_vertical(line)]
    widths = [(box[2] - box[0]) / len(line.text) for line, box in horizontal if len(line.text) >= 2]
    heights = [box[3] - box[1] for _, box in horizontal]
    left = min(box[0] for _, box in placed)
    right = max(box[2] for _, box in placed)
    top = min(box[1] for _, box in placed)
    cell_width = max(median(widths) if widths else 4.0, (right - left) / MAX_FIGURE_COLUMNS, 0.1)
    row_height = max(median(heights) if heights else 8.0, 0.1)

    grid: dict[tuple[int, int], str] = {}

    def is_free(row: int, column: int, text: str) -> bool:
        return row >= 0 and all(
            (row, cell) not in grid for cell in range(column - 1, column + len(text) + 1)
        )

    for line, box in sorted(placed, key=lambda item: (item[1][1], item[1][0])):
        text = line.text.strip()
        center_x = (box[0] + box[2]) / 2
        center_y = (box[1] + box[3]) / 2
        if is_vertical(line):
            column = round((center_x - left) / cell_width - len(text) / 2)
        else:
            column = round((box[0] - left) / cell_width)
        column = max(column, 0)
        row = round((center_y - top) / row_height)
        shifts = [0] + [shift for step in range(1, MAX_ROW_SHIFT + 1) for shift in (step, -step)]
        target = next((row + shift for shift in shifts if is_free(row + shift, column, text)), None)
        if target is None:
            target = max(cell_row for cell_row, _ in grid) + 1
        for offset, char in enumerate(text):
            grid[(target, column + offset)] = char

    row_count = max(row for row, _ in grid) + 1
    first_column = min(column for _, column in grid)
    last_column = max(column for _, column in grid)
    rows = [
        ''.join(
            grid.get((row, column), ' ') for column in range(first_column, last_column + 1)
        ).rstrip()
        for row in range(row_count)
    ]
    compact: list[str] = []
    for row in rows:
        if row or (compact and compact[-1]):
            compact.append(row)
    while compact and not compact[-1]:
        compact.pop()
    return compact
