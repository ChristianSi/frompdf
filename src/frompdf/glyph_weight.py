"""Recognize bold fonts by the shapes of their glyphs, where their names do not tell.

Some PDFs name their fonts by opaque hashes, as Advent 3B2 does with
`AdvOTcb88df00`, and report no weights. Such a font is bold if its letters are
drawn with much thicker strokes than those of the body font. Fonts with
names telling no style, and no weight reported for them, as Advent's
`AdvPSFTBL`, are judged alike, but need far thicker strokes, as a regular
sans-serif face beside a serif body already measures much thicker strokes
than the body. The stroke width of a glyph is estimated from its outline as
twice its area divided by its perimeter, which is exact for long, thin
strokes.
"""

import ctypes
import math
import re
from collections import Counter
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from pdftext.schema import Page

# Raw pdfium handles, which carry no useful static types.
Font = Any
PageObject = Any

# The letters whose strokes are measured: lowercase letters without
# ascending or descending strokes thinned by their serifs or tails, looked up
# by their character codes in the encoding of a font.
STROKE_LETTERS = 'abcdeghmnopqrsu'
# Fonts with fewer of these letters are not judged.
MIN_STROKE_LETTERS = 3
# Glyph outlines are retrieved at this size; pdfium returns them in ems.
GLYPH_PATH_SIZE = 1.0
# Each Bézier curve of an outline is measured as this many straight segments.
CURVE_STEPS = 8
# A font is bold if its strokes are at least this many times as wide as those
# of the body font. Regular faces in the corpus measure at most 1.4 times the
# stroke width of the body font, bold ones about 1.5 times and more.
BOLD_STROKE_RATIO = 1.4
# Fonts with names telling no style and no reported weight are bold only if
# their strokes are at least this many times as wide as those of the body
# font. Beside a serif body, regular sans-serif faces measure up to about 1.4
# times its stroke width (wiley's AdvPSFT-R, Arial), bold faces up to about
# 1.9 times, and black ones more (wiley's AdvPSFTBL, 2.4 times).
UNNAMED_BOLD_STROKE_RATIO = 2.0
# Only fonts named by an opaque hash are judged by their glyphs: names with a
# run of hexadecimal digits, as `AdvOTcb88df00`. Other names without a style,
# as `Arial`, name regular faces. A subset prefix, as `ABCDEF+`, is ignored.
HASH_PATTERN = re.compile(r'[0-9a-f]{6,}')
SUBSET_PREFIX_PATTERN = re.compile(r'^[A-Z]{6}\+')
# Names telling the weight or style of a font after all, as the suffixes of
# `AdvOTb65e897d.B` and `AdvOT7d6df7ab.I`, or a weight or style word.
NAMED_STYLE_PATTERN = re.compile(
    r'[._-](?:B|Bd|SB|Sb|I|It|BI|BIt)(?:\+\w+)?$'
    r'|(?i:regu|roman|book|normal|plain|light|thin|medi|semi|demi|bold|black|heavy'
    r'|ital|oblique|slant|kursiv|math|symbol)'
)


def has_opaque_name(font_name: str) -> bool:
    """Return whether a font is named by a hash telling nothing about its style."""
    name = SUBSET_PREFIX_PATTERN.sub('', font_name)
    return not NAMED_STYLE_PATTERN.search(name) and any(
        any(char.isdigit() for char in run) for run in HASH_PATTERN.findall(name)
    )


def contour_measures(points: Sequence[tuple[float, float]]) -> tuple[float, float]:
    """Return the signed area and the perimeter of a closed polygon."""
    area = 0.0
    perimeter = 0.0
    for (x1, y1), (x2, y2) in zip(points, [*points[1:], points[0]], strict=True):
        area += x1 * y2 - x2 * y1
        perimeter += math.hypot(x2 - x1, y2 - y1)
    return area / 2.0, perimeter


def cubic_point(
    start: tuple[float, float],
    first: tuple[float, float],
    second: tuple[float, float],
    end: tuple[float, float],
    t: float,
) -> tuple[float, float]:
    """Return the point of a cubic Bézier curve at parameter t."""
    u = 1.0 - t
    return (
        u**3 * start[0] + 3 * u**2 * t * first[0] + 3 * u * t**2 * second[0] + t**3 * end[0],
        u**3 * start[1] + 3 * u**2 * t * first[1] + 3 * u * t**2 * second[1] + t**3 * end[1],
    )


def glyph_contours(font: Font, char_code: int) -> list[list[tuple[float, float]]]:
    """Return the contours of a glyph as polygons, flattening its curves."""
    path = pdfium_c.FPDFFont_GetGlyphPath(font, char_code, ctypes.c_float(GLYPH_PATH_SIZE))
    if not path:
        return []
    contours: list[list[tuple[float, float]]] = []
    curve: list[tuple[float, float]] = []
    x = ctypes.c_float()
    y = ctypes.c_float()
    for index in range(pdfium_c.FPDFGlyphPath_CountGlyphSegments(path)):
        segment = pdfium_c.FPDFGlyphPath_GetGlyphPathSegment(path, index)
        if not pdfium_c.FPDFPathSegment_GetPoint(segment, ctypes.byref(x), ctypes.byref(y)):
            continue
        point = (x.value, y.value)
        kind = pdfium_c.FPDFPathSegment_GetType(segment)
        if kind == pdfium_c.FPDF_SEGMENT_MOVETO or not contours:
            contours.append([point])
            curve = []
        elif kind == pdfium_c.FPDF_SEGMENT_BEZIERTO:
            curve.append(point)
            if len(curve) == 3:
                start = contours[-1][-1]
                contours[-1].extend(
                    cubic_point(start, curve[0], curve[1], curve[2], step / CURVE_STEPS)
                    for step in range(1, CURVE_STEPS + 1)
                )
                curve = []
        else:
            contours[-1].append(point)
    return [contour for contour in contours if len(contour) >= 3]


def glyph_stroke_width(font: Font, char_code: int) -> float | None:
    """Return the estimated stroke width of a glyph in ems, if it has one.

    Counters wind against outer contours, so their areas cancel.
    """
    area = 0.0
    perimeter = 0.0
    for contour in glyph_contours(font, char_code):
        contour_area, contour_perimeter = contour_measures(contour)
        area += contour_area
        perimeter += contour_perimeter
    if perimeter <= 0.0:
        return None
    return 2.0 * abs(area) / perimeter


def font_stroke_width(font: Font) -> float | None:
    """Return the average stroke width of the lowercase letters of a font, if it has enough."""
    widths = [
        width
        for letter in STROKE_LETTERS
        if (width := glyph_stroke_width(font, ord(letter))) is not None
    ]
    if len(widths) < MIN_STROKE_LETTERS:
        return None
    return sum(widths) / len(widths)


def font_name(font: Font) -> str:
    """Return the base name of a font as pdftext reports it, without a subset prefix."""
    length = pdfium_c.FPDFFont_GetBaseFontName(font, None, 0)
    if length <= 1:
        return ''
    buffer = ctypes.create_string_buffer(length)
    pdfium_c.FPDFFont_GetBaseFontName(font, buffer, length)
    return buffer.value.decode('utf-8', errors='replace')


def body_font_name(page_list: Sequence[Page]) -> str | None:
    """Return the name of the font setting most of the visible text of a document."""
    counts: Counter[str] = Counter()
    for page in page_list:
        for block in page.get('blocks', []):
            for line in block.get('lines', []):
                for span in line.get('spans', []):
                    name = span.get('font', {}).get('name')
                    if isinstance(name, str) and name:
                        counts[name] += len(span.get('text', '').strip())
    if not counts:
        return None
    return counts.most_common(1)[0][0]


def text_objects(page_objects: Sequence[PageObject]) -> Iterator[PageObject]:
    """Yield the text objects among page objects, descending into form XObjects."""
    for page_object in page_objects:
        object_type = pdfium_c.FPDFPageObj_GetType(page_object)
        if object_type == pdfium_c.FPDF_PAGEOBJ_TEXT:
            yield page_object
        elif object_type == pdfium_c.FPDF_PAGEOBJ_FORM:
            count = max(pdfium_c.FPDFFormObj_CountObjects(page_object), 0)
            yield from text_objects(
                [pdfium_c.FPDFFormObj_GetObject(page_object, index) for index in range(count)]
            )


def font_stroke_widths(input_path: Path, names: set[str]) -> dict[str, float]:
    """Return the stroke widths of the fonts of a PDF with the given names, where measurable."""
    widths: dict[str, float] = {}
    measured: set[str] = set()
    pdf = pdfium.PdfDocument(input_path)
    try:
        for page in pdf:
            try:
                count = max(pdfium_c.FPDFPage_CountObjects(page.raw), 0)
                page_objects = [
                    pdfium_c.FPDFPage_GetObject(page.raw, index) for index in range(count)
                ]
                for text_object in text_objects(page_objects):
                    font = pdfium_c.FPDFTextObj_GetFont(text_object)
                    if not font:
                        continue
                    name = font_name(font)
                    if name not in names or name in measured:
                        continue
                    measured.add(name)
                    width = font_stroke_width(font)
                    if width is not None:
                        widths[name] = width
            finally:
                page.close()
            if measured == names:
                break
    finally:
        pdf.close()
    return widths


def has_unnamed_style(font_name: str) -> bool:
    """Return whether a font name tells no style, being neither opaque nor naming one."""
    name = SUBSET_PREFIX_PATTERN.sub('', font_name)
    return not NAMED_STYLE_PATTERN.search(name) and not has_opaque_name(font_name)


def find_heavy_fonts(input_path: Path, page_list: Sequence[Page]) -> frozenset[str]:
    """Return the names of fonts recognized as bold by their glyphs.

    These are fonts named by opaque hashes, drawn with strokes much wider
    than those of the body font, and fonts with names telling no style and
    no reported weight, drawn with strokes far wider still.
    """
    body_name = body_font_name(page_list)
    if body_name is None:
        return frozenset()
    names: set[str] = set()
    weighed: set[str] = set()
    for page in page_list:
        for block in page.get('blocks', []):
            for line in block.get('lines', []):
                for span in line.get('spans', []):
                    font = span.get('font', {})
                    name = font.get('name')
                    if isinstance(name, str) and name and name != body_name:
                        names.add(name)
                        if font.get('weight'):
                            weighed.add(name)
    ratios = {name: BOLD_STROKE_RATIO for name in names if has_opaque_name(name)}
    ratios.update(
        (name, UNNAMED_BOLD_STROKE_RATIO) for name in names - weighed if has_unnamed_style(name)
    )
    if not ratios:
        return frozenset()
    widths = font_stroke_widths(input_path, set(ratios) | {body_name})
    body_width = widths.get(body_name)
    if body_width is None:
        return frozenset()
    return frozenset(
        name
        for name, ratio in ratios.items()
        if (width := widths.get(name)) is not None and width >= ratio * body_width
    )
