"""Take the geometry of OCR text layers from the scans they cover.

Scanned documents carry the text recognized by OCR as an invisible text layer
over the images of their pages. Its geometry is only the OCR engine's
estimate. The font size of a line may be the height of its box, so that
lines without descenders come out a quarter smaller than lines with them,
and the words may be laid out with the metrics of a substitute font, so that
line ends lie up to several ems off the ink of justified columns. Hyphens
ending lines are often dropped from the text, too.

The scan shows all of this as it is. Each line of the text layer is measured
against the dark pixels of its rendered page: its left and right ends, its
baseline, the height of its lowercase letters or capitals, and a hyphen
ending it. Line boxes, sizes, and hyphens of the text layer are then replaced
by these measurements, so that the rest of the pipeline judges indents, line
ends, and type sizes as in any other PDF.

Measured heights vary by a few percent from line to line, as the scan is
slightly skewed and edges are blurred. The sizes of the document are grouped
around their most common values within that precision, so that lines set in
the same size get the same one.

The text layer may also place a line so far from its ink that the baseline
looked for near the text is that of a neighboring line, and quotation marks
or stray marks can mislead the measured height. The OCR engine places the
lines of a document consistently, though: their baselines lie at about the
same distance from the origins of their text, and their measured sizes are
in about the same proportion to the sizes of the text layer. Measurements
far from this typical placement are not trusted. A misplaced line is measured
again where its typical placement expects its baseline, or else placed
there; a line whose height is implausible takes its size from its neighbors.
"""

import ctypes
import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

import numpy as np
import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from numpy.typing import NDArray
from pdftext.schema import Bbox, Page
from pdftext.schema import Char as PdfTextChar
from pdftext.schema import Line as PdfTextLine
from pdftext.schema import Span as PdfTextSpan

# Pages are rendered at this many pixels per inch to be measured, enough to
# tell the height of letters to a few percent and the shape of a hyphen.
SCAN_RESOLUTION = 300.0
# Pixels darker than this gray level are ink.
INK_LEVEL = 128

# The x-height and cap height of text faces in ems, which turn the measured
# heights into font sizes.
X_HEIGHT_EM = 0.5
CAP_HEIGHT_EM = 0.7
# Lines with at least this share of lowercase letters among their letters
# and digits show their x-height as the densest band of ink; lines with at
# most the second share show their cap height. Lines in between show either.
MIN_LOWERCASE_SHARE = 0.75
MAX_CAPITALS_LOWERCASE_SHARE = 0.1
# Line boxes reach this far above and below the baseline, in ems.
LINE_BOX_ASCENT_EM = 0.8
LINE_BOX_DESCENT_EM = 0.2
# Measured sizes within this ratio of a more common size are taken as that
# size. Real steps between sizes of type are larger, while the measured
# heights of lines in the same size scatter by up to about this much.
SIZE_GROUP_RATIO = 1.1

# OCR engines place a line's text near the bottom of its box, either on the
# baseline or below the descenders, and set its size to about the height of
# the box. The baseline is looked for this far above and below the origin of
# the text, and the top of the letters up to this far above the baseline, all
# in units of the OCR size.
BASELINE_SEARCH_ABOVE = 0.6
BASELINE_SEARCH_BELOW = 0.35
LETTER_TOP_SEARCH = 1.2
# The ink of a line starts at most this far left of its text, in units of the
# OCR size, and continues across gaps up to the second size, such as the
# spaces of justified text, but not a gap between columns.
MAX_INK_LEAD = 1.0
MAX_INK_GAP = 1.5
# The x-height of lowercase text is where the ink of a line rises from a
# level below the first share of its densest one by at least the second share
# of the steepest such rise.
MAX_SPARSE_SHARE = 0.5
MIN_RISE_SHARE = 0.5
# Lines are measured in segments about this many times as wide as their OCR
# size, whose baselines lie within the second share of it from that of the
# whole line.
SEGMENT_WIDTH = 4.0
SEGMENT_BASELINE_SHIFT = 0.25
# Other lines overlapping at least this share of a line's height lie on the
# same visual line; the ink of a line ends before that of the next of them
# may start.
SAME_LINE_OVERLAP = 0.5
# The ink of a line is taken from the band from its baseline up to the height
# of capitals, in ems, which neighboring lines do not reach.
INK_BAND_ASCENT_EM = 0.7
INK_BAND_DESCENT_EM = 0.05
# A hyphen is a bar whose bottom is at least the first height above the
# baseline and whose top is at most the second, at most the third high, and
# as wide as the fourth to the fifth, all in ems, and at least the sixth
# times as wide as it is high. The ink ending a line is looked at down to
# the seventh below the baseline, so that commas and descenders are seen.
HYPHEN_MIN_BOTTOM_EM = 0.1
HYPHEN_MAX_TOP_EM = 0.4
HYPHEN_MAX_HEIGHT_EM = 0.15
HYPHEN_MIN_WIDTH_EM = 0.15
HYPHEN_MAX_WIDTH_EM = 0.5
HYPHEN_MIN_ASPECT = 1.5
GLYPH_BAND_DESCENT_EM = 0.25
# The hyphen is looked for in the band up to this height above the baseline,
# below the x-height, which letters overhanging it, like `f`, reach above.
HYPHEN_SEARCH_TOP_EM = 0.45
# The scan of the end of a line is kept this wide and this far above and
# below its baseline, in units of the OCR size, until its size is known.
TAIL_WIDTH = 2.0
TAIL_ABOVE = 1.2
TAIL_BELOW = 0.5
# The typical placement of a kind of line in a document is the median of at
# least this many lines of that kind.
MIN_TYPICAL_LINES = 10
# A measured baseline more than this many OCR sizes from where the typical
# placement expects it is that of another line, or of no line. The baselines
# of a document scatter by about a quarter of that, while a neighboring line
# lies about a whole size away.
BASELINE_TOLERANCE = 0.4
# A misplaced line is measured again with its baseline looked for this many
# OCR sizes above and below where the typical placement expects it, which
# stays clear of the lines above and below.
RETRY_BASELINE_SEARCH = 0.35
# A measured size off by more than this ratio from the typical proportion to
# the OCR size is implausible. Correct ones scatter by up to about 1.25,
# misled ones by 1.5 and more.
SIZE_TOLERANCE = 1.4
# Characters ending a line that already break it like a hyphen.
LINE_END_DASHES = frozenset('-\u00ad\u2010\u2011\u2012\u2013\u2014')

Box = tuple[float, float, float, float]


class Scan:
    """The ink of a rendered page, or of a part of it, addressed in `pdftext` coordinates.

    left and top are the coordinates of the top left of the first pixel.
    `pdftext` measures points from the top left of the page, whose height it
    rounds up, so the top of a rendered page lies at this slack.
    """

    def __init__(
        self, ink: NDArray[np.bool_], scale: float, left: float = 0.0, top: float = 0.0
    ) -> None:
        self.ink = ink
        self.scale = scale
        self.left = left
        self.top = top

    def row(self, y: float) -> int:
        """Return the row of pixels at a `pdftext` y coordinate, within the scan."""
        return min(max(round((y - self.top) * self.scale), 0), self.ink.shape[0])

    def column(self, x: float) -> int:
        """Return the column of pixels at a `pdftext` x coordinate, within the scan."""
        return min(max(round((x - self.left) * self.scale), 0), self.ink.shape[1])

    def y(self, row: float) -> float:
        """Return the `pdftext` y coordinate of the top of a row of pixels."""
        return row / self.scale + self.top

    def x(self, column: float) -> float:
        """Return the `pdftext` x coordinate of the left of a column of pixels."""
        return column / self.scale + self.left

    def region(self, x1: float, y1: float, x2: float, y2: float) -> NDArray[np.bool_]:
        """Return the ink of a box."""
        return self.ink[self.row(y1) : self.row(y2), self.column(x1) : self.column(x2)]

    def crop(self, x1: float, y1: float, x2: float, y2: float) -> 'Scan':
        """Return the scan of a box, kept apart from that of the page."""
        row, column = self.row(y1), self.column(x1)
        return Scan(self.region(x1, y1, x2, y2).copy(), self.scale, self.x(column), self.y(row))


@dataclass(frozen=True)
class InkLine:
    """What the scan shows of a line of the text layer, in `pdftext` coordinates.

    height is the x-height of lowercase lines or the cap height of lines of
    capitals and digits, as told by kind, and None for other lines. tail
    is the scan of the end of the line, where a hyphen that its text lacks
    is looked for once its size is known, unless its text ends in a dash.
    """

    x1: float
    x2: float
    baseline: float
    em: float
    height: float | None
    kind: str
    tail: Scan | None


@dataclass
class OcrLine:
    """A line of the text layer of a page, with its measurement.

    origin is the y coordinate of the origin of its text and ocr_size its
    size in the text layer, box its box there, and right_bound where the
    ink of the next line on the same visual line may start. estimated tells
    that the size of the ink is estimated from the OCR size, as the scan
    does not tell it plausibly.
    """

    page_index: int
    block_index: int
    line: PdfTextLine
    chars: list[PdfTextChar]
    weight: int
    ink: InkLine
    text: str
    box: Box
    origin: float
    ocr_size: float
    right_bound: float
    size: float | None = None
    hyphen: float | None = None
    estimated: bool = False


@dataclass(frozen=True)
class Placement:
    """Where the text layer of a document typically places a kind of line.

    offset is the distance of the measured baseline below the origin of the
    text, and scale the measured size, both in units of the OCR size. scale
    is None for lines whose letters do not tell their height.
    """

    offset: float
    scale: float | None


def letter_kind(text: str) -> str:
    """Return which height the densest band of ink of a line of text shows.

    That is `x` for lines mostly in lowercase letters, `cap` for lines of
    capitals and digits, and `mixed` for lines showing either.
    """
    letters = [char for char in text if char.isalnum()]
    if not letters:
        return 'mixed'
    share = sum(char.islower() for char in letters) / len(letters)
    if share >= MIN_LOWERCASE_SHARE:
        return 'x'
    if share <= MAX_CAPITALS_LOWERCASE_SHARE:
        return 'cap'
    return 'mixed'


def inked_columns(region: NDArray[np.bool_]) -> NDArray[np.bool_]:
    """Return which columns of a region hold ink."""
    return np.asarray(region.any(axis=0), dtype=np.bool_)


def ink_runs(columns: NDArray[np.bool_], max_gap: int) -> list[tuple[int, int]]:
    """Return the runs of inked columns, joined across gaps of up to max_gap columns.

    Each run is given by its first and last column.
    """
    inked = np.flatnonzero(columns)
    if not len(inked):
        return []
    breaks = np.flatnonzero(np.diff(inked) > max_gap + 1)
    starts = [int(inked[0]), *(int(inked[index + 1]) for index in breaks)]
    ends = [*(int(inked[index]) for index in breaks), int(inked[-1])]
    return list(zip(starts, ends, strict=True))


def subpixel_peak(values: NDArray[np.float64], index: int) -> float:
    """Return the position of a peak, interpolated by a parabola through its neighbors."""
    if 0 < index < len(values) - 1:
        left, middle, right = values[index - 1], values[index], values[index + 1]
        curvature = left - 2 * middle + right
        if curvature:
            return index + 0.5 * float(left - right) / float(curvature)
    return float(index)


def dense_band(
    profile: NDArray[np.float64], top: int, bottom: int, max_height: int, capitals: bool = False
) -> tuple[float, float] | None:
    """Return where the densest band of ink of a line starts and ends, in rows.

    The band ends at the baseline, where the ink of a row profile drops the
    most, within rows top to bottom, and starts where it rises the most up to
    max_height rows above it. Edges fall between rows.

    A drop counts by the share of the ink that it ends, as the ink of a
    dash, which is denser than that of the letters around it, ends above the
    baseline, where all ink but that of descenders ends. In capitals and
    digits, the band starts where the ink does, above a dash, so a rise
    likewise counts by the share of the ink that it starts. In lowercase
    text, the band starts at the x-height, the lowest edge where the ink
    rises from the sparse level of ascenders and capitals, below half that
    of the band, as steeply as about anywhere above, even where ascenders
    are frequent enough to rise more steeply.
    """
    smooth = np.convolve(profile, np.ones(3) / 3, mode='same')
    steps = np.diff(smooth)
    top, bottom = max(top, 0), min(bottom, len(steps))
    if bottom - top < 3:
        return None
    with np.errstate(divide='ignore', invalid='ignore'):
        drops = np.nan_to_num(np.where(steps < 0, steps**2 / smooth[:-1], 0.0))
    drops = drops[top:bottom]
    if drops.max() <= 0:
        return None
    base = top + subpixel_peak(drops, int(np.argmax(drops)))
    first = max(int(base) - max_height, 0)
    last = max(int(base), first + 1)
    if capitals:
        with np.errstate(divide='ignore', invalid='ignore'):
            rises = np.nan_to_num(np.where(steps > 0, steps**2 / smooth[1:], 0.0))[first:last]
        if rises.max() <= 0:
            return None
        return first + subpixel_peak(rises, int(np.argmax(rises))) + 1.0, base + 1.0
    sparse = smooth[first:last] <= MAX_SPARSE_SHARE * smooth[first : last + 1].max()
    rises = np.where(sparse & (steps[first:last] > 0), steps[first:last], 0.0)
    if rises.max() <= 0:
        return None
    strong = rises >= MIN_RISE_SHARE * rises.max()
    lowest = max(
        index
        for index in np.flatnonzero(strong)
        if (index == len(rises) - 1 or rises[index] >= rises[index + 1])
        and (index == 0 or rises[index] >= rises[index - 1])
    )
    return first + subpixel_peak(rises, int(lowest)) + 1.0, base + 1.0


def is_hyphen(glyph: NDArray[np.bool_], scan: Scan, top: float, baseline: float, em: float) -> bool:
    """Return whether the ink of the glyph ending a line, in a band from top, is a hyphen."""
    rows = np.flatnonzero(glyph.any(axis=1))
    if not len(rows):
        return False
    glyph_top = scan.y(scan.row(top) + int(rows[0]))
    glyph_bottom = scan.y(scan.row(top) + int(rows[-1]) + 1)
    width = glyph.shape[1] / scan.scale
    height = glyph_bottom - glyph_top
    return (
        baseline - glyph_bottom >= HYPHEN_MIN_BOTTOM_EM * em
        and baseline - glyph_top <= HYPHEN_MAX_TOP_EM * em
        and height <= HYPHEN_MAX_HEIGHT_EM * em
        and HYPHEN_MIN_WIDTH_EM * em <= width <= HYPHEN_MAX_WIDTH_EM * em
        and width >= HYPHEN_MIN_ASPECT * height
    )


def line_end_hyphen(scan: Scan, x1: float, x2: float, baseline: float, em: float) -> float | None:
    """Return where a hyphen ending the ink of a line from x1 to x2 starts, if it ends in one.

    The hyphen is looked for below the x-height, where it is set apart from
    the letter before it even where that letter reaches over it above, as
    the arm of an `f` does. Nothing may follow it at any height.
    """
    full = inked_columns(scan.region(x1, baseline - INK_BAND_ASCENT_EM * em, x2, baseline))
    low_top = baseline - HYPHEN_SEARCH_TOP_EM * em
    low = scan.region(x1, low_top, x2, baseline + GLYPH_BAND_DESCENT_EM * em)
    runs = ink_runs(inked_columns(low), 0)
    inked = np.flatnonzero(full)
    if not runs or not len(inked) or runs[-1][1] < inked[-1] - 1:
        return None
    start, end = runs[-1]
    if not is_hyphen(low[:, start : end + 1], scan, low_top, baseline, em):
        return None
    return scan.x(scan.column(x1) + start)


def letter_band(
    scan: Scan,
    x1: float,
    x2: float,
    baseline_top: float,
    baseline_bottom: float,
    size: float,
    capitals: bool,
) -> tuple[float, float] | None:
    """Return the top and the baseline of the densest band of ink between x1 and x2.

    The baseline is looked for between baseline_top and baseline_bottom, the
    top up to the letter top search above it, in units of the OCR size. The
    top is that of capitals and digits if the text is set in them.
    """
    top = baseline_top - LETTER_TOP_SEARCH * size
    region = scan.region(x1, top, x2, baseline_bottom)
    if not region.any():
        return None
    band = dense_band(
        region.sum(axis=1).astype(np.float64),
        scan.row(baseline_top) - scan.row(top),
        scan.row(baseline_bottom) - scan.row(top),
        round(LETTER_TOP_SEARCH * size * scan.scale),
        capitals,
    )
    if band is None:
        return None
    return scan.y(scan.row(top) + band[0]), scan.y(scan.row(top) + band[1])


def measure_line(
    scan: Scan,
    text: str,
    text_box: Box,
    origin_y: float,
    ocr_size: float,
    right_bound: float,
    baseline_range: tuple[float, float] | None = None,
) -> InkLine | None:
    """Return what the scan shows of a line of the text layer, if it shows ink there.

    text_box is the box that the text layer gives the line, whose left end
    and the origin of the text are close to the ink, unlike its right end.
    Ink of the next line on the same visual line starts at right_bound.
    The baseline is looked for near the origin, or within baseline_range
    where it is given.

    The line is found in its whole length first, then measured in segments,
    whose heights and baselines are less blurred by the skew of the scan.
    """
    x1, _, x2, _ = text_box
    left = x1 - MAX_INK_LEAD * ocr_size
    kind = letter_kind(text)
    if baseline_range is None:
        baseline_range = (
            origin_y - BASELINE_SEARCH_ABOVE * ocr_size,
            origin_y + BASELINE_SEARCH_BELOW * ocr_size,
        )
    rough = letter_band(
        scan,
        left,
        min(max(x2, x1 + ocr_size), right_bound),
        *baseline_range,
        ocr_size,
        kind == 'cap',
    )
    if rough is None or rough[1] <= rough[0]:
        return None
    if kind == 'x':
        em_share = X_HEIGHT_EM
    elif kind == 'cap':
        em_share = CAP_HEIGHT_EM
    else:
        em_share = (X_HEIGHT_EM + CAP_HEIGHT_EM) / 2
    rough_em = (rough[1] - rough[0]) / em_share

    band_top = rough[1] - INK_BAND_ASCENT_EM * rough_em
    band_bottom = rough[1] + INK_BAND_DESCENT_EM * rough_em
    columns = inked_columns(scan.region(left, band_top, right_bound, band_bottom))
    runs = ink_runs(columns, math.floor(MAX_INK_GAP * ocr_size * scan.scale))
    start_column = scan.column(x1) - scan.column(left)
    runs = [run for run in runs if run[1] >= start_column]
    if not runs:
        return None
    first, last = runs[0]
    origin = scan.column(left)
    ink_x1 = scan.x(origin + first)
    ink_x2 = scan.x(origin + last + 1)

    count = max(round((ink_x2 - ink_x1) / (SEGMENT_WIDTH * ocr_size)), 1)
    width = (ink_x2 - ink_x1) / count
    bands = [
        band
        for index in range(count)
        if (
            band := letter_band(
                scan,
                ink_x1 + index * width,
                ink_x1 + (index + 1) * width,
                rough[1] - SEGMENT_BASELINE_SHIFT * ocr_size,
                rough[1] + SEGMENT_BASELINE_SHIFT * ocr_size,
                ocr_size,
                kind == 'cap',
            )
        )
        is not None
        and band[1] > band[0]
    ]
    if bands:
        dense_height = float(np.median([bottom - top for top, bottom in bands]))
        baseline = float(np.median([bottom for _, bottom in bands]))
    else:
        dense_height = rough[1] - rough[0]
        baseline = rough[1]
    em = dense_height / em_share

    tail = None
    if text.rstrip()[-1:] not in LINE_END_DASHES:
        tail = scan.crop(
            max(ink_x1, ink_x2 - TAIL_WIDTH * ocr_size),
            baseline - TAIL_ABOVE * ocr_size,
            ink_x2,
            baseline + TAIL_BELOW * ocr_size,
        )

    return InkLine(
        ink_x1,
        ink_x2,
        baseline,
        em,
        dense_height if kind != 'mixed' else None,
        kind,
        tail,
    )


def group_sizes(sizes: Sequence[tuple[float, int]]) -> list[float]:
    """Return the sizes of the given weighted sizes, grouped around their most common ones.

    The most common size, by the weight of the sizes within the group ratio
    of it, takes all sizes within that ratio, which take the size of their
    weighted median. The group is then gathered again around it, so that it
    takes the sizes on both sides of it. The other sizes are grouped
    likewise, the most common ones first.
    """
    if not sizes:
        return []
    order = np.argsort([size for size, _ in sizes], kind='stable')
    values = np.log([sizes[index][0] for index in order])
    weights = np.array([sizes[index][1] for index in order], dtype=np.float64)
    radius = math.log(SIZE_GROUP_RATIO)
    lows = np.searchsorted(values, values - radius, side='left')
    highs = np.searchsorted(values, values + radius, side='right')
    remaining = np.ones(len(values), dtype=bool)
    grouped = np.zeros(len(values))

    def weighted_median(position: int) -> int:
        members = np.flatnonzero(remaining[lows[position] : highs[position]]) + lows[position]
        cumulative = np.cumsum(weights[members])
        return int(members[np.searchsorted(cumulative, cumulative[-1] / 2)])

    while remaining.any():
        cumulative = np.concatenate(([0.0], np.cumsum(np.where(remaining, weights, 0.0))))
        near = np.where(remaining, cumulative[highs] - cumulative[lows], -1.0)
        middle = weighted_median(weighted_median(int(np.argmax(near))))
        members = slice(lows[middle], highs[middle])
        grouped[members] = np.where(
            remaining[members], round(math.exp(values[middle]), 1), grouped[members]
        )
        remaining[members] = False
    result = [0.0] * len(sizes)
    for position, index in enumerate(order):
        result[int(index)] = float(grouped[position])
    return result


def nearest_group(size: float, groups: Sequence[float]) -> float:
    """Return the group size within the group ratio of a size, or the size itself."""
    near = [group for group in groups if abs(math.log(group / size)) <= math.log(SIZE_GROUP_RATIO)]
    return min(near, key=lambda group: abs(math.log(group / size))) if near else round(size, 1)


def visible_line_chars(line: PdfTextLine) -> list[PdfTextChar]:
    """Return the characters of a line other than whitespace."""
    return [
        char
        for span in line.get('spans', [])
        for char in span.get('chars', [])
        if char.get('char', '').strip()
    ]


def is_invisible(text_page: pdfium.PdfTextPage, char: PdfTextChar) -> bool:
    """Return whether a character is drawn invisibly, as the text layers of scans are."""
    text_object = pdfium_c.FPDFText_GetTextObject(text_page.raw, char['char_idx'])
    return bool(text_object) and (
        pdfium_c.FPDFTextObj_GetTextRenderMode(text_object)
        == pdfium_c.FPDF_TEXTRENDERMODE_INVISIBLE
    )


def char_origin_y(text_page: pdfium.PdfTextPage, char: PdfTextChar, page: Page) -> float | None:
    """Return the y coordinate of a character's origin in `pdftext` coordinates."""
    x = ctypes.c_double()
    y = ctypes.c_double()
    if not pdfium_c.FPDFText_GetCharOrigin(text_page.raw, char['char_idx'], x, y):
        return None
    page_top = page['bbox'][1]
    page_height = math.ceil(abs(page['bbox'][3] - page['bbox'][1]))
    return page_height - (y.value - page_top)


def render_scan(pdf_page: pdfium.PdfPage, page: Page) -> Scan:
    """Render a page and return its ink."""
    scale = SCAN_RESOLUTION / 72.0
    bitmap = pdf_page.render(
        # Annotated as int by pypdfium2, which accepts any number.
        scale=scale,  # pyright: ignore[reportArgumentType]
        grayscale=True,
    )
    pixels = np.asarray(bitmap.to_pil().convert('L'))
    height = pdf_page.get_size()[1]
    return Scan(pixels < INK_LEVEL, scale, top=math.ceil(height) - height)


def overlap_share(box: Box, other: Box) -> float:
    """Return how much of the lower of two boxes their vertical overlap is."""
    overlap = min(box[3], other[3]) - max(box[1], other[1])
    height = min(box[3] - box[1], other[3] - other[1])
    return overlap / height if height > 0 else 0.0


def line_box(line: PdfTextLine) -> Box:
    """Return the box of a line."""
    x1, y1, x2, y2 = line['bbox']
    return x1, y1, x2, y2


def measure_page(
    pdf_page: pdfium.PdfPage,
    text_page: pdfium.PdfTextPage,
    page: Page,
    page_index: int,
) -> list[OcrLine]:
    """Return the lines of a page's invisible text layer that lie over ink, measured."""
    entries = [
        (block_index, line, visible_line_chars(line))
        for block_index, block in enumerate(page.get('blocks', []))
        for line in block.get('lines', [])
    ]
    candidates = [
        entry
        for entry in entries
        if entry[2]
        and not any(char.get('rotation') for char in entry[2])
        and all(is_invisible(text_page, char) for char in entry[2])
    ]
    if not candidates:
        return []
    scan = render_scan(pdf_page, page)
    page_width = scan.x(scan.ink.shape[1])
    boxes = [line_box(line) for _, line, _ in entries]
    measured: list[OcrLine] = []
    for block_index, line, chars in candidates:
        box = line_box(line)
        size = float(chars[0].get('font', {}).get('size') or 0.0)
        origin_y = char_origin_y(text_page, chars[0], page)
        if size <= 0 or origin_y is None:
            continue
        right_bound = min(
            (
                other[0] - MAX_INK_LEAD * size
                for other in boxes
                if other[0] > box[0] + size and overlap_share(box, other) >= SAME_LINE_OVERLAP
            ),
            default=page_width,
        )
        # Span text, unlike character data, shows a hyphen ending the line,
        # which pdfium reports as code 2 in the character data.
        text = ''.join(span.get('text', '') for span in line.get('spans', [])).strip()
        ink = measure_line(scan, text, box, origin_y, size, right_bound)
        if ink is None:
            continue
        measured.append(
            OcrLine(
                page_index,
                block_index,
                line,
                chars,
                len(chars),
                ink,
                text,
                box,
                origin_y,
                size,
                right_bound,
            )
        )
    return measured


def baseline_offset(line: OcrLine) -> float:
    """Return how far the measured baseline of a line lies below its origin, in OCR sizes."""
    return (line.ink.baseline - line.origin) / line.ocr_size


def typical_placements(lines: Sequence[OcrLine]) -> dict[str, Placement]:
    """Return the typical placement of each kind of line with enough lines of its kind."""
    placements: dict[str, Placement] = {}
    for kind in ('x', 'cap', 'mixed'):
        same = [line for line in lines if line.ink.kind == kind]
        if len(same) < MIN_TYPICAL_LINES:
            continue
        scales = [line.ink.em / line.ocr_size for line in same if line.ink.height is not None]
        placements[kind] = Placement(
            float(np.median([baseline_offset(line) for line in same])),
            float(np.median(scales)) if len(scales) >= MIN_TYPICAL_LINES else None,
        )
    return placements


def is_misplaced(line: OcrLine, placements: dict[str, Placement]) -> bool:
    """Return whether the measured baseline of a line is far from its typical placement."""
    placement = placements.get(line.ink.kind)
    return (
        placement is not None and abs(baseline_offset(line) - placement.offset) > BASELINE_TOLERANCE
    )


def has_implausible_size(line: OcrLine, placements: dict[str, Placement]) -> bool:
    """Return whether the measured height of a line is far from its typical proportion."""
    placement = placements.get(line.ink.kind)
    return (
        line.ink.height is not None
        and placement is not None
        and placement.scale is not None
        and abs(math.log(line.ink.em / line.ocr_size / placement.scale)) > math.log(SIZE_TOLERANCE)
    )


def remeasure(scan: Scan, line: OcrLine, placement: Placement) -> None:
    """Measure a misplaced line again where its typical placement expects its baseline.

    Where the scan shows no baseline there either, the line is placed at the
    expected baseline, along the box of the text layer, with its size
    estimated from the OCR size, or else left to its neighbors.
    """
    expected = line.origin + placement.offset * line.ocr_size
    search = RETRY_BASELINE_SEARCH * line.ocr_size
    ink = measure_line(
        scan,
        line.text,
        line.box,
        line.origin,
        line.ocr_size,
        line.right_bound,
        (expected - search, expected + search),
    )
    if ink is None or abs(ink.baseline - expected) > BASELINE_TOLERANCE * line.ocr_size:
        scale = placement.scale if placement.scale is not None else 1.0
        ink = InkLine(
            line.box[0], line.box[2], expected, scale * line.ocr_size, None, line.ink.kind, None
        )
        line.estimated = placement.scale is not None
    line.ink = ink


def estimate_size(line: OcrLine, placement: Placement) -> None:
    """Estimate the size of a line from its OCR size, by the typical proportion of its kind."""
    assert placement.scale is not None
    line.ink = replace(line.ink, em=placement.scale * line.ocr_size, height=None)
    line.estimated = True


def assign_sizes(lines: Sequence[OcrLine]) -> None:
    """Give the measured lines of a document their sizes, grouped around common ones.

    Lines whose size is estimated take the common size nearest to their
    estimate, as their neighbors may be set in another size. Other lines
    whose letters do not tell their height take the size of the nearest
    line of their `pdftext` block that does, or else of the nearest line
    above or below them in their column, or else their own estimate.
    """
    measured = [line for line in lines if line.ink.height is not None]
    for line, size in zip(
        measured,
        group_sizes([(line.ink.em, line.weight) for line in measured]),
        strict=True,
    ):
        line.size = size
    groups = sorted({line.size for line in measured if line.size is not None})
    for index, line in enumerate(lines):
        if line.size is not None:
            continue
        if line.estimated:
            line.size = nearest_group(line.ink.em, groups)
            continue
        same_block = [
            other
            for other in (*reversed(lines[:index]), *lines[index + 1 :])
            if other.ink.height is not None
            and other.page_index == line.page_index
            and other.block_index == line.block_index
        ]
        same_column = sorted(
            (
                other
                for other in measured
                if other.page_index == line.page_index
                and min(other.ink.x2, line.ink.x2) > max(other.ink.x1, line.ink.x1)
            ),
            key=lambda other: abs(other.ink.baseline - line.ink.baseline),
        )
        nearest = [*same_block, *same_column]
        line.size = nearest[0].size if nearest else nearest_group(line.ink.em, groups)


def rewrite_line(line: OcrLine) -> None:
    """Replace the geometry and size of a line of the text layer by its measurement.

    Characters keep their relative positions along the line, which spans
    the ink, short of a hyphen that is added to the end of the line.
    """
    ink = line.ink
    size = line.size or ink.em
    y1 = ink.baseline - LINE_BOX_ASCENT_EM * size
    y2 = ink.baseline + LINE_BOX_DESCENT_EM * size
    old_x1 = min(char['bbox'][0] for char in line.chars)
    old_x2 = max(char['bbox'][2] for char in line.chars)
    text_x2 = line.hyphen if line.hyphen is not None else ink.x2
    factor = (text_x2 - ink.x1) / (old_x2 - old_x1) if old_x2 > old_x1 else 1.0

    def moved(x: float) -> float:
        return ink.x1 + (x - old_x1) * factor

    spans = line.line.get('spans', [])
    last_span: PdfTextSpan | None = None
    for span in spans:
        for char in span.get('chars', []):
            x1, _, x2, _ = char['bbox']
            char['bbox'] = cast(Bbox, [moved(x1), y1, moved(x2), y2])
            char['font'] = {**char.get('font', {}), 'size': size}
        span['font'] = {**span.get('font', {}), 'size': size}
        if span.get('chars') and span.get('text', '').strip():
            last_span = span
    if line.hyphen is not None and last_span is not None:
        add_hyphen(last_span, line.hyphen, ink.x2, y1, y2)
    for span in spans:
        if span.get('chars'):
            span['bbox'] = union_bbox([get_bbox(char) for char in span['chars']])
    line.line['bbox'] = union_bbox([get_bbox(span) for span in spans if span.get('chars')])


def add_hyphen(span: PdfTextSpan, x1: float, x2: float, y1: float, y2: float) -> None:
    """Add a hyphen after the last visible character of a span."""
    chars = span['chars']
    last = max(index for index, char in enumerate(chars) if char.get('char', '').strip())
    hyphen = cast(PdfTextChar, {**chars[last], 'char': '-', 'bbox': [x1, y1, x2, y2]})
    chars.insert(last + 1, hyphen)
    text = span.get('text', '')
    stripped = text.rstrip()
    span['text'] = stripped + '-' + text[len(stripped) :]


def get_bbox(obj: PdfTextChar | PdfTextSpan) -> Box:
    """Return the box of a character or span."""
    x1, y1, x2, y2 = obj['bbox']
    return x1, y1, x2, y2


def union_bbox(boxes: Sequence[Box]) -> Bbox:
    """Return the box around boxes."""
    return cast(
        Bbox,
        [
            min(box[0] for box in boxes),
            min(box[1] for box in boxes),
            max(box[2] for box in boxes),
            max(box[3] for box in boxes),
        ],
    )


def repair_ocr_text_layers(input_path: Path, page_list: Sequence[Page]) -> None:
    """Replace the geometry of invisible text over scans by that of the ink, in place."""
    lines: list[OcrLine] = []
    pdf = pdfium.PdfDocument(input_path)
    try:
        for page_index, page in enumerate(page_list):
            page_no = page.get('page', page_index)
            if page.get('rotation') or not 0 <= page_no < len(pdf):
                continue
            pdf_page = pdf[page_no]
            text_page = pdf_page.get_textpage()
            try:
                lines.extend(measure_page(pdf_page, text_page, page, page_index))
            finally:
                text_page.close()
                pdf_page.close()
        placements = typical_placements(lines)
        misplaced: defaultdict[int, list[OcrLine]] = defaultdict(list)
        for line in lines:
            if is_misplaced(line, placements):
                misplaced[line.page_index].append(line)
        # Pages are rendered again rather than kept, as their scans are large.
        for page_index, page_lines in misplaced.items():
            page = page_list[page_index]
            pdf_page = pdf[page.get('page', page_index)]
            try:
                scan = render_scan(pdf_page, page)
            finally:
                pdf_page.close()
            for line in page_lines:
                remeasure(scan, line, placements[line.ink.kind])
    finally:
        pdf.close()
    if not lines:
        return
    for line in lines:
        if has_implausible_size(line, placements):
            estimate_size(line, placements[line.ink.kind])
    assign_sizes(lines)
    for line in lines:
        tail = line.ink.tail
        if tail is not None:
            line.hyphen = line_end_hyphen(
                tail, tail.left, line.ink.x2, line.ink.baseline, line.size or line.ink.em
            )
        rewrite_line(line)
