"""Extract horizontal and vertical rules, such as table borders, from page drawings.

`pdftext` reports text only, so the vector paths of each page are read with
pypdfium2, the PDF library underlying `pdftext`. Straight path segments and
thin filled rectangles become rules, in the coordinates `pdftext` uses for
text: points from the top left of the page's crop box.
"""

import ctypes
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from pdftext.schema import Page

# pdfium handles of page objects and path segments. Their ctypes pointer
# types are runtime values, which type checkers do not accept as annotations.
PageObject = Any
PathSegment = Any

# An affine matrix (a, b, c, d, e, f), mapping (x, y) to
# (a x + c y + e, b x + d y + f) as in PDF.
Matrix = tuple[float, float, float, float, float, float]
IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

# A clip box (left, bottom, right, top) in PDF page space.
ClipBox = tuple[float, float, float, float]

# Segments deviating less than this from the horizontal or vertical are
# straight rules. Shorter segments are ticks or parts of glyph-like drawings.
MAX_RULE_SKEW = 0.5
MIN_RULE_LENGTH = 3.0

# Filled rectangles at most this thick are drawn as rules, as by Word and
# LibreOffice for table borders.
MAX_FILLED_RULE_THICKNESS = 2.0

# Colors at least this light on all channels are invisible on white paper,
# such as white rules that hide parts of a grid.
MIN_INVISIBLE_CHANNEL = 230

# Collinear pieces within this distance of each other form a single rule.
# Tables drawn cell by cell leave small gaps where borders cross.
RULE_POSITION_TOLERANCE = 1.0
RULE_JOIN_GAP = 3.0


@dataclass(frozen=True)
class Rule:
    """A horizontal or vertical rule on a page, in `pdftext` coordinates.

    position is the y coordinate of a horizontal rule or the x coordinate of a
    vertical one; start and end delimit its extent along the other axis.
    """

    horizontal: bool
    position: float
    start: float
    end: float


def multiply(first: Matrix, second: Matrix) -> Matrix:
    """Return the matrix applying first, then second."""
    a, b, c, d, e, f = first
    a2, b2, c2, d2, e2, f2 = second
    return (
        a * a2 + b * c2,
        a * b2 + b * d2,
        c * a2 + d * c2,
        c * b2 + d * d2,
        e * a2 + f * c2 + e2,
        e * b2 + f * d2 + f2,
    )


def transform(matrix: Matrix, x: float, y: float) -> tuple[float, float]:
    """Apply a matrix to a point."""
    a, b, c, d, e, f = matrix
    return a * x + c * y + e, b * x + d * y + f


def object_matrix(page_object: PageObject) -> Matrix:
    """Return the matrix of a page object, mapping it into its container."""
    matrix = pdfium_c.FS_MATRIX()
    if not pdfium_c.FPDFPageObj_GetMatrix(page_object, matrix):
        return IDENTITY
    return (matrix.a, matrix.b, matrix.c, matrix.d, matrix.e, matrix.f)


def segment_point(segment: PathSegment, matrix: Matrix) -> tuple[float, float]:
    """Return the end point of a path segment, transformed by a matrix."""
    x, y = ctypes.c_float(), ctypes.c_float()
    pdfium_c.FPDFPathSegment_GetPoint(segment, x, y)
    return transform(matrix, x.value, y.value)


def object_clip_box(
    page_object: PageObject, container: Matrix, inherited: ClipBox | None
) -> ClipBox | None:
    """Return the box enclosing the visible area of a page object.

    Clip paths are reported in the coordinates of the object's container. Form
    XObjects clip their content to their bounding box this way, which hides
    the parts of drawings outside, as for tables cropped from larger pages.
    Each clip path is approximated by its bounding box.
    """
    clip_path = pdfium_c.FPDFPageObj_GetClipPath(page_object)
    if not clip_path:
        return inherited
    box = inherited
    for path_index in range(max(pdfium_c.FPDFClipPath_CountPaths(clip_path), 0)):
        points = [
            segment_point(
                pdfium_c.FPDFClipPath_GetPathSegment(clip_path, path_index, index), container
            )
            for index in range(
                max(pdfium_c.FPDFClipPath_CountPathSegments(clip_path, path_index), 0)
            )
        ]
        if not points:
            continue
        xs = [x for x, _ in points]
        ys = [y for _, y in points]
        path_box = (min(xs), min(ys), max(xs), max(ys))
        box = (
            path_box
            if box is None
            else (
                max(box[0], path_box[0]),
                max(box[1], path_box[1]),
                min(box[2], path_box[2]),
                min(box[3], path_box[3]),
            )
        )
    return box


def is_visible_color(page_object: PageObject, stroke: bool) -> bool:
    """Return whether an object's stroke or fill color shows on white paper."""
    red, green, blue, alpha = (ctypes.c_uint() for _ in range(4))
    getter = pdfium_c.FPDFPageObj_GetStrokeColor if stroke else pdfium_c.FPDFPageObj_GetFillColor
    if not getter(page_object, red, green, blue, alpha):
        return True
    return alpha.value > 0 and min(red.value, green.value, blue.value) < MIN_INVISIBLE_CHANNEL


def path_subpaths(
    page_object: PageObject, matrix: Matrix
) -> list[list[tuple[float, float]] | None]:
    """Return the straight subpaths of a path as closed or open point lists.

    Curved subpaths are None. Closing segments are added as explicit points.
    """
    subpaths: list[list[tuple[float, float]] | None] = []
    current: list[tuple[float, float]] | None = None
    for index in range(max(pdfium_c.FPDFPath_CountSegments(page_object), 0)):
        segment = pdfium_c.FPDFPath_GetPathSegment(page_object, index)
        segment_type = pdfium_c.FPDFPathSegment_GetType(segment)
        point = segment_point(segment, matrix)
        if segment_type == pdfium_c.FPDF_SEGMENT_MOVETO or current is None and subpaths == []:
            current = [point]
            subpaths.append(current)
        elif segment_type == pdfium_c.FPDF_SEGMENT_LINETO and current is not None:
            current.append(point)
        else:
            # Curves make the subpath useless for rules.
            if subpaths:
                subpaths[-1] = None
            current = None
            continue
        if (
            current is not None
            and pdfium_c.FPDFPathSegment_GetClose(segment)
            and current[-1] != current[0]
        ):
            current.append(current[0])
    return subpaths


def clipped_segment(
    start: tuple[float, float], end: tuple[float, float], clip: ClipBox | None
) -> tuple[float, float, float, float] | None:
    """Return an axis-aligned segment as (x1, y1, x2, y2) clipped to a box, if visible."""
    x1, x2 = sorted((start[0], end[0]))
    y1, y2 = sorted((start[1], end[1]))
    if clip is not None:
        x1, y1, x2, y2 = max(x1, clip[0]), max(y1, clip[1]), min(x2, clip[2]), min(y2, clip[3])
        if x2 < x1 or y2 < y1:
            return None
    return x1, y1, x2, y2


def stroked_rules(
    subpaths: list[list[tuple[float, float]] | None], clip: ClipBox | None
) -> list[tuple[bool, float, float, float]]:
    """Return the straight horizontal and vertical segments of stroked subpaths.

    Each rule is given as (horizontal, position, start, end) in PDF page space.
    """
    rules: list[tuple[bool, float, float, float]] = []
    for points in subpaths:
        if points is None:
            continue
        for start, end in zip(points, points[1:], strict=False):
            box = clipped_segment(start, end, clip)
            if box is None:
                continue
            x1, y1, x2, y2 = box
            if y2 - y1 <= MAX_RULE_SKEW and x2 - x1 >= MIN_RULE_LENGTH:
                rules.append((True, (y1 + y2) / 2, x1, x2))
            elif x2 - x1 <= MAX_RULE_SKEW and y2 - y1 >= MIN_RULE_LENGTH:
                rules.append((False, (x1 + x2) / 2, y1, y2))
    return rules


def filled_rules(
    subpaths: list[list[tuple[float, float]] | None], clip: ClipBox | None
) -> list[tuple[bool, float, float, float]]:
    """Return thin filled rectangles as rules along their center lines."""
    rules: list[tuple[bool, float, float, float]] = []
    for points in subpaths:
        # A rectangle has four corners, the first repeated at the end when closed.
        if points is None or len(points) not in (4, 5):
            continue
        xs = sorted({round(x, 1) for x, _ in points})
        ys = sorted({round(y, 1) for _, y in points})
        if len(xs) > 2 or len(ys) > 2:
            continue
        box = clipped_segment((xs[0], ys[0]), (xs[-1], ys[-1]), clip)
        if box is None:
            continue
        x1, y1, x2, y2 = box
        if y2 - y1 <= MAX_FILLED_RULE_THICKNESS and x2 - x1 >= MIN_RULE_LENGTH:
            rules.append((True, (y1 + y2) / 2, x1, x2))
        elif x2 - x1 <= MAX_FILLED_RULE_THICKNESS and y2 - y1 >= MIN_RULE_LENGTH:
            rules.append((False, (x1 + x2) / 2, y1, y2))
    return rules


def collect_page_rules(
    page_objects: Sequence[PageObject],
    container: Matrix,
    clip: ClipBox | None,
    rules: list[tuple[bool, float, float, float]],
) -> None:
    """Append the rules drawn by page objects, descending into form XObjects."""
    for page_object in page_objects:
        object_type = pdfium_c.FPDFPageObj_GetType(page_object)
        if object_type not in (pdfium_c.FPDF_PAGEOBJ_FORM, pdfium_c.FPDF_PAGEOBJ_PATH):
            continue
        object_clip = object_clip_box(page_object, container, clip)
        matrix = multiply(object_matrix(page_object), container)
        if object_type == pdfium_c.FPDF_PAGEOBJ_FORM:
            count = max(pdfium_c.FPDFFormObj_CountObjects(page_object), 0)
            children = [
                pdfium_c.FPDFFormObj_GetObject(page_object, index) for index in range(count)
            ]
            collect_page_rules(children, matrix, object_clip, rules)
            continue
        fill_mode, stroke = ctypes.c_int(), ctypes.c_int()
        if not pdfium_c.FPDFPath_GetDrawMode(page_object, fill_mode, stroke):
            continue
        subpaths = path_subpaths(page_object, matrix)
        if stroke.value and is_visible_color(page_object, stroke=True):
            rules.extend(stroked_rules(subpaths, object_clip))
        if fill_mode.value and is_visible_color(page_object, stroke=False):
            rules.extend(filled_rules(subpaths, object_clip))


def join_rules(rules: list[Rule]) -> list[Rule]:
    """Join collinear rules that overlap or nearly touch."""
    joined: list[Rule] = []
    for horizontal in (True, False):
        pending = sorted(
            (rule for rule in rules if rule.horizontal == horizontal),
            key=lambda rule: (rule.position, rule.start),
        )
        lines: list[list[Rule]] = []
        for rule in pending:
            if lines and rule.position - lines[-1][0].position <= RULE_POSITION_TOLERANCE:
                lines[-1].append(rule)
            else:
                lines.append([rule])
        for line in lines:
            position = sum(rule.position for rule in line) / len(line)
            pieces: list[list[float]] = []
            for rule in sorted(line, key=lambda rule: rule.start):
                if pieces and rule.start - pieces[-1][1] <= RULE_JOIN_GAP:
                    pieces[-1][1] = max(pieces[-1][1], rule.end)
                else:
                    pieces.append([rule.start, rule.end])
            joined.extend(
                Rule(horizontal, round(position, 1), round(start, 1), round(end, 1))
                for start, end in pieces
            )
    return joined


def extract_rules(input_path: Path, page_list: Sequence[Page]) -> dict[int, list[Rule]]:
    """Return the rules drawn on each page, by page number starting at 1.

    Rotated pages are skipped, as their coordinates would need rotating like
    `pdftext` does for text.
    """
    rules_by_page: dict[int, list[Rule]] = {}
    pdf = pdfium.PdfDocument(input_path)
    try:
        for page_no, page_dict in enumerate(page_list, start=1):
            if page_dict.get('rotation', 0) or page_no > len(pdf):
                continue
            page = pdf[page_no - 1]
            try:
                # Mirror pdftext's mapping from PDF page space to its coordinates.
                left, bottom, right, top = page.get_bbox()
                height = math.ceil(abs(top - bottom))
                raw_rules: list[tuple[bool, float, float, float]] = []
                count = max(pdfium_c.FPDFPage_CountObjects(page.raw), 0)
                collect_page_rules(
                    [pdfium_c.FPDFPage_GetObject(page.raw, index) for index in range(count)],
                    IDENTITY,
                    None,
                    raw_rules,
                )
            finally:
                page.close()
            rules = [
                Rule(True, height - (position - bottom), start - left, end - left)
                if horizontal
                else Rule(
                    False, position - left, height - (end - bottom), height - (start - bottom)
                )
                for horizontal, position, start, end in raw_rules
            ]
            rules_by_page[page_no] = join_rules(rules)
    finally:
        pdf.close()
    return rules_by_page
