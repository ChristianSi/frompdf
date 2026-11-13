"""Recognize the pictures of a document and the text shown as part of them.

Photos, plots, and diagrams are drawn: as images, as vector paths, or as both.
Their labels, such as tick values, axis titles, and legends, are often text,
which would turn into scattered paragraphs and headings in the flow of the
document. Instead, each picture is cut out of its page as an image, together
with the text lying within it, which is left out of the flow. The text of a
document is never part of a picture: drawings with running text set on them
are backgrounds or frames, and the text below a picture, such as its caption,
ends it.

Pictures are recognized from the drawings alone, not from the wording of
their captions, so they do not depend on the language of a document.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from frompdf.line_features import close_font_size, ends_sentence, is_prose_line, is_textual_line
from frompdf.models import Line
from frompdf.page_context import (
    MAX_FIRST_LINE_INDENT_EM,
    dominant_page_font_size,
    established_left_edges,
)
from frompdf.rules import Drawing, DrawingBox
from frompdf.tables import TableLayout

# Drawings closer than this, in points, form one region, such as the frame,
# curves, and ticks of one plot.
DRAWING_JOIN_GAP = 3.0
# Drawings at most this thick, in points, are rules, such as the axes and
# ticks of a plot, but also underlines and the rules beside or between texts.
# They join a region only where they stay near it, at most this far beyond
# it in body ems, so a rule next to a picture does not extend it over text.
MAX_RULE_THICKNESS = 2.5
RULE_REACH_EM = 2.0
# A region is a panel of a picture if its longer side measures at least this
# many body ems, its area is at least that of a square of this size, and its
# shorter side measures at least the smaller value, as that of a wide strip
# cut from a screenshot. Smaller regions are ornaments, icons, or pieces of
# formulas.
MIN_PANEL_SIZE_EM = 4.0
MIN_PANEL_WIDTH_EM = 1.0
# The vector paths of a panel without an image have at least this many curves
# and diagonal segments. Rules and rectangles alone frame or shade text, as
# in boxes and tables.
MIN_PICTURE_DETAIL = 8
# A drawing or region with at least this many lines of running text on it is
# a background or frame of the text. Running text is body text, or prose of
# at least this many letters in lines set directly below each other, unlike
# the short entries of a legend.
MIN_RUNNING_LINES = 2
MIN_RUNNING_LETTERS = 24
# An image covering at least this share of its page is a background if there
# is any text on it, as the scan below the text layer of a page read by OCR.
PAGE_IMAGE_SHARE = 0.8
# A picture without a caption covers at least this many square points
# (12 cm²). Smaller ones are logos, icons, and other ornaments; captioned
# pictures only need to be panels, as thin strips cut from screenshots.
MIN_UNCAPTIONED_AREA = 12 * (72 / 2.54) ** 2
# Drawings at the same place on at least this many pages are page furniture,
# such as logos and rules in headers. Places are compared on a grid of points.
MIN_FURNITURE_PAGES = 3
FURNITURE_GRID = 2.0
# Labels lie around the drawings of a panel, up to this far from them in
# body ems, as tick values and axis titles beside or below a plot, which
# reach about four ems beyond the frame of a plot in nature. Pictures closer
# than this are parts of one figure.
LABEL_MARGIN_EM = 4.5
# A picture extends over drawings touching it that reach at most this far
# beyond it, in body ems, as the frame of a plot around its labels.
DRAWING_REACH_EM = 2.0
# A font is a figure font if it sets text within the panels of the document
# and at most this share of its text away from all panels.
MAX_FIGURE_FONT_AWAY_SHARE = 0.1
# A line belongs to a picture or to a drawing if more than this share of its
# box lies within it.
MIN_INSIDE_SHARE = 0.5

# A caption starts at most this far below its picture, in body ems, and
# reaches at most this far into it.
MAX_CAPTION_GAP_EM = 3.5
MAX_CAPTION_OVERLAP_EM = 0.5
# Characters that may start a caption besides letters, as in "(a) …".
CAPTION_OPENERS = '([{"\'«‹„“‚‘'
# A caption continues in lines directly below its previous line, separated by
# less than this in ems of its size. It ends after a sentence ending this
# far, in ems, short of the right edge of its lines.
CAPTION_CONTINUATION_GAP_EM = 1.0
CAPTION_SHORT_LINE_EM = 2.0
# The pieces of one line of a caption are at most this far apart, in ems.
# Text further right on the same line is that of a picture beside it.
CAPTION_PIECE_GAP_EM = 2.0

# A line continues the line above it at most this far below, in ems, about
# the line spacing of body text.
MAX_BODY_ADVANCE_EM = 1.6

# Labels whose box is this much taller than wide, relative to the font size,
# run vertically, as axis titles beside a plot.
VERTICAL_MIN_HEIGHT_EM = 2.0


@dataclass(frozen=True)
class Panel:
    """A region of drawings forming a picture or a part of one, and the drawings within it."""

    box: DrawingBox
    drawings: tuple[Drawing, ...] = ()


@dataclass(eq=False)
class FigureLayout:
    """A picture on a page: its box, the lines of text within it, and its caption.

    The lines are shown by the image cut from the box and left out of the
    text. resolution is that of a picture consisting of images only, which is
    lossy if all of them are; pictures with vector drawings or text have none.
    image is the path of the image written for the picture, if any.
    """

    page_no: int
    box: DrawingBox
    lines: list[Line]
    caption_lines: list[Line]
    resolution: float | None = None
    lossy: bool = False
    image: str | None = None

    @property
    def frame(self) -> DrawingBox:
        """Return the box enclosing the picture and its caption."""
        frame = self.box
        for box in map(line_box, self.caption_lines):
            if box is not None:
                frame = union_box(frame, box)
        return frame

    @property
    def top(self) -> float:
        """Return the top of the picture and its caption."""
        return self.frame[1]

    @property
    def bottom(self) -> float:
        """Return the bottom of the picture and its caption."""
        return self.frame[3]


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


def expanded(box: DrawingBox, margin: float) -> DrawingBox:
    """Return a box grown by a margin on all sides."""
    return (box[0] - margin, box[1] - margin, box[2] + margin, box[3] + margin)


def box_area(box: DrawingBox) -> float:
    """Return the area of a box."""
    return max(box[2] - box[0], 0.0) * max(box[3] - box[1], 0.0)


def overlap_area(first: DrawingBox, second: DrawingBox) -> float:
    """Return the area shared by two boxes."""
    return box_area(
        (
            max(first[0], second[0]),
            max(first[1], second[1]),
            min(first[2], second[2]),
            min(first[3], second[3]),
        )
    )


def box_distance(first: DrawingBox, second: DrawingBox) -> float:
    """Return the largest of the horizontal and vertical gaps between two boxes."""
    return max(
        first[0] - second[2], second[0] - first[2], first[1] - second[3], second[1] - first[3], 0.0
    )


def lies_within(inner: DrawingBox, outer: DrawingBox) -> bool:
    """Return whether most of a box lies within another, or its center if it has no area."""
    area = box_area(inner)
    if area <= 0.0:
        center = ((inner[0] + inner[2]) / 2, (inner[1] + inner[3]) / 2)
        return outer[0] <= center[0] <= outer[2] and outer[1] <= center[1] <= outer[3]
    return overlap_area(inner, outer) > MIN_INSIDE_SHARE * area


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


def line_box(line: Line) -> DrawingBox | None:
    """Return the box of a line, if fully known."""
    if line.x1 is None or line.y1 is None or line.x2 is None or line.y2 is None:
        return None
    return line.x1, line.y1, line.x2, line.y2


def is_vertical(line: Line) -> bool:
    """Return whether a line runs vertically, being much taller than wide."""
    box = line_box(line)
    if box is None or len(line.text.strip()) < 2:
        return False
    font_size = line.font_size or 1.0
    height = box[3] - box[1]
    return height >= font_size * VERTICAL_MIN_HEIGHT_EM and height > 2 * (box[2] - box[0])


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


def furniture_key(drawing: Drawing) -> tuple[str, tuple[int, ...]]:
    """Return a key shared by drawings of the same kind at the same place on their pages."""
    return drawing.kind, tuple(round(value / FURNITURE_GRID) for value in drawing.box)


def find_furniture(
    drawings_by_page: dict[int, list[Drawing]],
) -> set[tuple[str, tuple[int, ...]]]:
    """Return the keys of drawings repeated at the same place on several pages."""
    pages_of_key: Counter[tuple[str, tuple[int, ...]]] = Counter()
    for drawings in drawings_by_page.values():
        pages_of_key.update({furniture_key(drawing) for drawing in drawings})
    return {key for key, count in pages_of_key.items() if count >= MIN_FURNITURE_PAGES}


def is_rule(drawing: Drawing) -> bool:
    """Return whether a drawing is thin, as a rule or a tick."""
    box = drawing.box
    return min(box[2] - box[0], box[3] - box[1]) <= MAX_RULE_THICKNESS


def is_long_prose(line: Line) -> bool:
    """Return whether a line has as many letters as lines of running text usually do."""
    return sum(character.isalpha() for character in line.text) >= MIN_RUNNING_LETTERS


def running_lines(box: DrawingBox, page_lines: Sequence[Line], body_lines: set[int]) -> int:
    """Return the number of lines of running text within a box.

    These are body lines and long lines of prose set directly below each
    other, as those of a paragraph, unlike the short labels of a picture.
    """
    within = [
        line
        for line in page_lines
        if (bounds := line_box(line)) is not None
        and not is_vertical(line)
        and lies_within(bounds, box)
    ]
    long_lines = [line for line in within if is_long_prose(line)]
    return sum(
        id(line) in body_lines
        or any(
            continues_line(other, line) or continues_line(line, other)
            for other in long_lines
            if other is not line
        )
        for line in within
        if id(line) in body_lines or is_long_prose(line)
    )


def is_background(
    drawing: Drawing,
    page_lines: Sequence[Line],
    body_lines: set[int],
    page_size: tuple[float, float] | None,
) -> bool:
    """Return whether a drawing lies behind or around the text of its page.

    An image or shading covering its page is a background if there is any
    text on it, as on covers and pages read by OCR. Other drawings are
    backgrounds or frames if running text is set on them.
    """
    if is_rule(drawing):
        return False
    if (
        drawing.kind != 'path'
        and page_size is not None
        and box_area(drawing.box) >= PAGE_IMAGE_SHARE * page_size[0] * page_size[1]
        and any(
            is_textual_line(line)
            and (bounds := line_box(line)) is not None
            # The image may extend beyond the page.
            and lies_within(bounds, drawing.box)
            for line in page_lines
        )
    ):
        return True
    return running_lines(drawing.box, page_lines, body_lines) >= MIN_RUNNING_LINES


def visible_drawings(
    drawings: Sequence[Drawing],
    page_lines: Sequence[Line],
    body_lines: set[int],
    page_size: tuple[float, float] | None = None,
) -> list[Drawing]:
    """Return the drawings of a page that are no backgrounds or frames of its text."""
    return [
        drawing
        for drawing in drawings
        if not is_background(drawing, page_lines, body_lines, page_size)
    ]


def page_panels(
    drawings: Sequence[Drawing],
    page_lines: Sequence[Line],
    body_lines: set[int],
    body_size: float,
    table_boxes: Sequence[DrawingBox] = (),
) -> list[Panel]:
    """Return the regions of drawings that are pictures or parts of them.

    The drawings form regions where they are close together; rules join the
    regions they stay near. A region is a panel if it is large enough and
    holds an image or detailed paths, but neither running text nor a table.
    """
    rules = [drawing.box for drawing in drawings if is_rule(drawing)]
    reach = body_size * RULE_REACH_EM
    regions: list[DrawingBox] = []
    for region in join_boxes(
        [drawing.box for drawing in drawings if not is_rule(drawing)], DRAWING_JOIN_GAP
    ):
        limit = expanded(region, reach)
        for rule in rules:
            if contains(limit, rule) and boxes_near(region, rule, DRAWING_JOIN_GAP):
                region = union_box(region, rule)
        regions.append(region)

    min_size = body_size * MIN_PANEL_SIZE_EM
    panels: list[Panel] = []
    for region in join_boxes(regions, DRAWING_JOIN_GAP):
        width, height = region[2] - region[0], region[3] - region[1]
        if (
            max(width, height) < min_size
            or width * height < min_size**2
            or min(width, height) < body_size * MIN_PANEL_WIDTH_EM
            or any(boxes_near(region, table_box, 0.0) for table_box in table_boxes)
        ):
            continue
        members = tuple(drawing for drawing in drawings if boxes_near(region, drawing.box, 0.0))
        if (
            all(drawing.kind == 'path' for drawing in members)
            and sum(drawing.detail for drawing in members) < MIN_PICTURE_DETAIL
        ):
            continue
        if running_lines(region, page_lines, body_lines) >= MIN_RUNNING_LINES:
            continue
        panels.append(Panel(region, members))
    return panels


def near_panel(box: DrawingBox, panels: Sequence[Panel], margin: float) -> bool:
    """Return whether a box lies within a margin around a panel."""
    return any(box_distance(box, panel.box) <= margin for panel in panels)


def find_figure_fonts(
    lines_by_page: dict[int, list[Line]], panels_by_page: dict[int, list[Panel]], margin: float
) -> set[str]:
    """Return the names of fonts that set the text of pictures only.

    Such a font sets text within the panels of the document, and hardly any
    text away from all of them. Text around a panel may belong to it, as an
    axis title, or to the document, as a caption.
    """
    inside: Counter[str] = Counter()
    away: Counter[str] = Counter()
    total: Counter[str] = Counter()
    for page_no, page_lines in lines_by_page.items():
        panels = panels_by_page.get(page_no, [])
        for line in page_lines:
            box = line_box(line)
            if box is None or not line.font_name:
                continue
            weight = len(line.text.strip())
            total[line.font_name] += weight
            if any(lies_within(box, panel.box) for panel in panels):
                inside[line.font_name] += weight
            elif not near_panel(box, panels, margin):
                away[line.font_name] += weight
    return {
        font_name
        for font_name in inside
        if away[font_name] <= MAX_FIGURE_FONT_AWAY_SHARE * total[font_name]
    }


def continues_line(previous: Line, line: Line) -> bool:
    """Return whether a line is set directly below another in the same font, overlapping it."""
    if (
        previous.x1 is None
        or previous.x2 is None
        or previous.y1 is None
        or line.x1 is None
        or line.x2 is None
        or line.y1 is None
        or previous.font_name != line.font_name
        or not close_font_size(previous.font_size, line.font_size)
    ):
        return False
    font_size = previous.font_size or 1.0
    return (
        0 < line.y1 - previous.y1 <= font_size * MAX_BODY_ADVANCE_EM
        and line.x1 < previous.x2
        and previous.x1 < line.x2
    )


def find_label_lines(
    page_lines: Sequence[Line],
    panels: Sequence[Panel],
    body_lines: set[int],
    figure_fonts: set[str],
    body_size: float,
) -> set[int]:
    """Return the IDs of lines that are labels of pictures, not text of the document.

    Lines within a panel are labels, as are lines set in a figure font.
    Around a panel, lines are labels if they run vertically. Lines without
    letters, such as tick values, and short lines in small type are labels
    unless they continue text of the document directly above them, as the
    last word of a caption. All other lines are text, which no picture may
    cover.
    """
    margin = body_size * LABEL_MARGIN_EM
    labels: set[int] = set()
    text: list[Line] = []
    for line in page_lines:
        box = line_box(line)
        if box is None:
            continue
        if any(lies_within(box, panel.box) for panel in panels):
            labels.add(id(line))
            continue
        if id(line) in body_lines:
            text.append(line)
            continue
        if line.font_name in figure_fonts:
            labels.add(id(line))
            continue
        if not near_panel(box, panels, margin):
            text.append(line)
            continue
        if is_vertical(line):
            labels.add(id(line))
            continue
        small = (
            line.font_size is not None
            and line.font_size < body_size
            and not close_font_size(line.font_size, body_size)
        )
        weak = not any(character.isalpha() for character in line.text) or (
            small and not is_prose_line(line)
        )
        if weak and not any(continues_line(previous, line) for previous in text):
            labels.add(id(line))
        else:
            text.append(line)
    return labels


def picture_boxes(
    page_lines: Sequence[Line],
    panels: Sequence[Panel],
    labels: set[int],
    body_size: float,
    table_boxes: Sequence[DrawingBox] = (),
    drawings: Sequence[Drawing] = (),
) -> list[DrawingBox]:
    """Return the boxes of the pictures formed by panels and the labels around them.

    Each panel grows by the labels within the margin around it, nearest
    first, and by the drawings touching it that reach little beyond it, such
    as the axes of a plot. Pictures closer than the margin are joined, as the
    panels of one figure. A box never grows over text of the document or a
    table.
    """
    margin = body_size * LABEL_MARGIN_EM
    reach = body_size * DRAWING_REACH_EM
    boxed = [(line, box) for line in page_lines if (box := line_box(line)) is not None]
    text_boxes = [box for line, box in boxed if id(line) not in labels]
    label_boxes = [box for line, box in boxed if id(line) in labels]
    drawing_boxes = [drawing.box for drawing in drawings]

    def is_clear(box: DrawingBox) -> bool:
        return not any(lies_within(text_box, box) for text_box in text_boxes) and not any(
            boxes_near(box, table_box, 0.0) for table_box in table_boxes
        )

    def grow(picture: DrawingBox) -> DrawingBox:
        grew = True
        while grew:
            grew = False
            near = [
                box
                for box in label_boxes
                if not contains(picture, box) and box_distance(box, picture) <= margin
            ]
            for box in sorted(near, key=lambda box, picture=picture: box_distance(box, picture)):
                grown = union_box(picture, box)
                if is_clear(grown):
                    picture = grown
                    grew = True
            limit = expanded(picture, reach)
            for box in drawing_boxes:
                if (
                    not contains(picture, box)
                    and contains(limit, box)
                    and boxes_near(picture, box, DRAWING_JOIN_GAP)
                    and is_clear(union_box(picture, box))
                ):
                    picture = union_box(picture, box)
                    grew = True
        return picture

    pictures = [grow(panel.box) for panel in panels]
    joined = True
    while joined:
        joined = False
        for first in range(len(pictures)):
            for second in range(first + 1, len(pictures)):
                union = union_box(pictures[first], pictures[second])
                if boxes_near(pictures[first], pictures[second], margin) and is_clear(union):
                    pictures[first] = grow(union)
                    del pictures[second]
                    joined = True
                    break
            if joined:
                break
    return pictures


def starts_emphasized(line: Line) -> bool:
    """Return whether the text of a line starts in bold or italics."""
    start = len(line.text) - len(line.text.lstrip())
    return any(
        text_range.kind in ('bold', 'italic') and text_range.start <= start < text_range.end
        for text_range in line.ranges
    )


def is_caption_start(line: Line, body_size: float) -> bool:
    """Return whether a line below a picture is set as the start of a caption.

    A caption is set smaller than the body, or starts in bold or italics at
    body size. It starts with a letter or an opening mark, unlike footnotes.
    """
    first = line.text.lstrip()[:1]
    if not (first.isalpha() or (first and first in CAPTION_OPENERS)) or is_vertical(line):
        return False
    if close_font_size(line.font_size, body_size):
        return starts_emphasized(line)
    return line.font_size is not None and line.font_size < body_size


def find_caption(
    picture: DrawingBox, page_lines: Sequence[Line], used: set[int], body_size: float
) -> Line | None:
    """Return the first line of the caption of a picture, if it has one.

    This is the unused line starting nearest below the picture, shortly below
    its bottom and below a part of it, if it is set as a caption.
    """
    nearest: tuple[float, float, Line] | None = None
    for line in page_lines:
        box = line_box(line)
        if (
            box is None
            or id(line) in used
            or box[2] <= picture[0]
            or picture[2] <= box[0]
            or not -body_size * MAX_CAPTION_OVERLAP_EM
            <= box[1] - picture[3]
            <= body_size * MAX_CAPTION_GAP_EM
        ):
            continue
        if nearest is None or (box[1], box[0]) < nearest[:2]:
            nearest = (box[1], box[0], line)
    if nearest is None or not is_caption_start(nearest[2], body_size):
        return None
    return nearest[2]


def continues_caption(caption: Sequence[Line], line: Line) -> bool:
    """Return whether a line continues a caption, given its lines so far.

    It continues the visual line of the last one closely, or starts directly
    below it in the same size, unless that line ended a sentence short of the
    right edge of the caption, as the last line of a paragraph.
    """
    last = caption[-1]
    if (
        line.page_no != last.page_no
        or last.y1 is None
        or last.y2 is None
        or line.y1 is None
        or line.y2 is None
        or not close_font_size(line.font_size, last.font_size)
    ):
        return False
    font_size = last.font_size or 0.0
    if line.y1 < last.y2 and last.y1 < line.y2:
        return (
            line.x1 is None
            or last.x2 is None
            or line.x1 - last.x2 <= font_size * CAPTION_PIECE_GAP_EM
        )
    right_edge = max(previous.x2 for previous in caption if previous.x2 is not None)
    if (
        last.x2 is not None
        and last.x2 < right_edge - font_size * CAPTION_SHORT_LINE_EM
        and ends_sentence(last.text.strip())
    ):
        return False
    return 0 <= line.y1 - last.y2 <= font_size * CAPTION_CONTINUATION_GAP_EM


def caption_lines(first: Line, page_lines: Sequence[Line], used: set[int]) -> list[Line]:
    """Return the lines of the caption starting with first, following it in reading order."""
    start = next(index for index, line in enumerate(page_lines) if line is first)
    lines = [first]
    for line in page_lines[start + 1 :]:
        if id(line) in used or not continues_caption(lines, line):
            break
        lines.append(line)
    return lines


def picture_resolution(
    picture: DrawingBox, drawings: Sequence[Drawing], has_text: bool
) -> tuple[float | None, bool]:
    """Return the resolution of a picture consisting of images only, and whether it is lossy.

    Such a picture has no text and no vector drawings but rules and plain
    rectangles, as frames. Its resolution is the highest one of its images.
    """
    shown = [drawing for drawing in drawings if overlap_area(drawing.box, picture) > 0.0]
    images = [drawing for drawing in shown if drawing.kind == 'image']
    resolutions = [image.resolution for image in images if image.resolution is not None]
    if (
        has_text
        or not resolutions
        or len(resolutions) < len(images)
        or any(drawing.kind == 'shading' or drawing.detail for drawing in shown)
    ):
        return None, False
    return max(resolutions), all(image.lossy for image in images)


def page_figures(
    page_no: int,
    page_lines: Sequence[Line],
    panels: Sequence[Panel],
    body_lines: set[int],
    figure_fonts: set[str],
    body_size: float,
    table_boxes: Sequence[DrawingBox] = (),
    drawings: Sequence[Drawing] = (),
) -> list[FigureLayout]:
    """Return the pictures of a page in reading order, with their lines and captions.

    drawings are the visible drawings of the page, which pictures may extend
    over. Small pictures without a caption are left out, and their text is
    left in the flow.
    """
    labels = find_label_lines(page_lines, panels, body_lines, figure_fonts, body_size)
    pictures = picture_boxes(page_lines, panels, labels, body_size, table_boxes, drawings)
    figures = [
        FigureLayout(
            page_no,
            picture,
            [
                line
                for line in page_lines
                if (box := line_box(line)) is not None and lies_within(box, picture)
            ],
            [],
        )
        for picture in pictures
    ]
    figures.sort(
        key=lambda figure: (reading_position(figure, page_lines), figure.box[1], figure.box[0])
    )
    used = {id(line) for figure in figures for line in figure.lines}
    for figure in figures:
        caption = find_caption(figure.box, page_lines, used, body_size)
        if caption is not None:
            figure.caption_lines = caption_lines(caption, page_lines, used)
            used.update(id(line) for line in figure.caption_lines)
        figure.resolution, figure.lossy = picture_resolution(
            figure.box, drawings, bool(figure.lines)
        )
    return [
        figure
        for figure in figures
        if figure.caption_lines or box_area(figure.box) >= MIN_UNCAPTIONED_AREA
    ]


def find_figures(
    lines: Sequence[Line],
    drawings_by_page: dict[int, list[Drawing]],
    tables: Sequence[TableLayout] = (),
    page_sizes: dict[int, tuple[float, float]] | None = None,
) -> list[FigureLayout]:
    """Return the pictures of a document in page order, with the text shown by them.

    Drawings repeated at the same place on several pages are page furniture.
    Lines of tables are no text of pictures, and no picture overlaps a table.
    page_sizes gives the width and height of pages, by page number.
    """
    body_size = dominant_page_font_size(list(lines))
    margin = body_size * LABEL_MARGIN_EM
    table_lines = {id(line) for table in tables for line in table.lines}
    furniture = find_furniture(drawings_by_page)
    lines_by_page: dict[int, list[Line]] = {page_no: [] for page_no in drawings_by_page}
    for line in lines:
        if id(line) not in table_lines:
            lines_by_page.setdefault(line.page_no, []).append(line)
    table_boxes_by_page: dict[int, list[DrawingBox]] = {}
    for table in tables:
        for frame in table.frames:
            table_boxes_by_page.setdefault(frame.page_no, []).append(
                (0.0, frame.top, float('inf'), frame.bottom)
            )

    body_lines_by_page: dict[int, set[int]] = {}
    drawings_of_page: dict[int, list[Drawing]] = {}
    panels_by_page: dict[int, list[Panel]] = {}
    for page_no in sorted(drawings_by_page):
        page_lines = lines_by_page[page_no]
        body_lines_by_page[page_no] = find_body_lines(page_lines, body_size)
        drawings_of_page[page_no] = visible_drawings(
            [
                drawing
                for drawing in drawings_by_page[page_no]
                if furniture_key(drawing) not in furniture
            ],
            page_lines,
            body_lines_by_page[page_no],
            (page_sizes or {}).get(page_no),
        )
        panels_by_page[page_no] = page_panels(
            drawings_of_page[page_no],
            page_lines,
            body_lines_by_page[page_no],
            body_size,
            table_boxes_by_page.get(page_no, []),
        )
    figure_fonts = find_figure_fonts(lines_by_page, panels_by_page, margin)

    figures: list[FigureLayout] = []
    for page_no, panels in panels_by_page.items():
        if panels:
            figures.extend(
                page_figures(
                    page_no,
                    lines_by_page[page_no],
                    panels,
                    body_lines_by_page[page_no],
                    figure_fonts,
                    body_size,
                    table_boxes_by_page.get(page_no, []),
                    drawings_of_page[page_no],
                )
            )
    return figures


def reading_position(figure: FigureLayout, lines: Sequence[Line]) -> float:
    """Return where a picture belongs among lines in reading order.

    The position lies half a line before the index of the first line below
    the picture on its page, or else after that of the last line above it,
    preferring lines of its column. On a page without lines, it precedes the
    first line of a later page.
    """
    on_page = [
        (index, box)
        for index, line in enumerate(lines)
        if line.page_no == figure.page_no and (box := line_box(line)) is not None
    ]
    left, top, right, bottom = figure.box
    middle = (top + bottom) / 2
    for in_column in (True, False):
        candidates = [
            (index, box)
            for index, box in on_page
            if not in_column or (box[0] < right and left < box[2])
        ]
        below = [index for index, box in candidates if box[1] >= middle]
        if below:
            return min(below) - 0.5
        above = [index for index, box in candidates if box[1] < middle]
        if above:
            return max(above) + 0.5
    later = [index for index, line in enumerate(lines) if line.page_no > figure.page_no]
    return (min(later) if later else len(lines)) - 0.5
