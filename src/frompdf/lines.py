from collections import defaultdict
from collections.abc import Sequence

from pdftext.schema import Line as PdfTextLine
from pdftext.schema import Page
from pdftext.schema import Span as PdfTextSpan

from frompdf.models import Line


def round_or_none(value: float | int | None, digits: int = 1) -> float | None:
    """Round a numeric value, or return None."""
    if value is None:
        return None
    return round(float(value), digits)


def get_bbox(
    obj: PdfTextLine | PdfTextSpan,
) -> tuple[float | None, float | None, float | None, float | None]:
    """Extract a 4-value bbox tuple from an object, if present."""
    bbox = obj.get('bbox')
    if not isinstance(bbox, list | tuple) or len(bbox) != 4:
        return None, None, None, None

    try:
        x1, y1, x2, y2 = bbox
        return float(x1), float(y1), float(x2), float(y2)
    except (TypeError, ValueError):
        return None, None, None, None


def bbox_height(obj: PdfTextLine | PdfTextSpan) -> float | None:
    """Return a usable bbox height, if present."""
    _, y1, _, y2 = get_bbox(obj)
    if y1 is None or y2 is None:
        return None

    height = abs(y2 - y1)
    if height <= 1.0:
        return None

    return height


def effective_span_font_size(span_dict: PdfTextSpan) -> float | None:
    """Return reported font size, falling back to bbox height for placeholder size 1.0."""
    font_dict = span_dict.get('font', {})
    size_value = font_dict.get('size')
    if size_value is None:
        return None

    try:
        size_float = float(size_value)
    except (TypeError, ValueError):
        return None

    # Some PDFs report every readable font as size 1.0; in that case bbox height
    # is the better available proxy for the visually rendered size.
    if size_float <= 1.0:
        return bbox_height(span_dict)

    return size_float


def dominant_font_size(line_dict: PdfTextLine) -> float | None:
    """Return the dominant font size for a line, weighted by text length."""
    size_weights: dict[float, int] = defaultdict(int)

    for span_dict in line_dict.get('spans', []):
        text_value = span_dict.get('text', '')
        weight = len(text_value.strip())
        if not weight:
            continue

        size_float = effective_span_font_size(span_dict)
        if size_float is None:
            continue

        size_weights[round(size_float, 1)] += weight

    if not size_weights:
        return None

    return max(size_weights.items(), key=lambda item: (item[1], item[0]))[0]


def average_font_weight(line_dict: PdfTextLine) -> float | None:
    """Return the length-weighted average font weight for visible text in a line."""
    weighted_sum = 0.0
    total_weight = 0

    for span_dict in line_dict.get('spans', []):
        text_value = span_dict.get('text', '')
        weight = len(text_value.strip())
        if not weight:
            continue

        font_dict = span_dict.get('font', {})
        font_weight = font_dict.get('weight')
        if not isinstance(font_weight, int | float) or font_weight < 0:
            continue

        weighted_sum += float(font_weight) * weight
        total_weight += weight

    if not total_weight:
        return None

    return round(weighted_sum / total_weight, 1)


def iter_lines(page_list: Sequence[Page]) -> list[Line]:
    """Flatten pdftext dictionary output into a list of Line records."""
    line_list: list[Line] = []

    for page_index, page_dict in enumerate(page_list, start=1):
        previous_x1: float | None = None
        previous_y1: float | None = None
        line_no_on_page = 0

        for block_index, block_dict in enumerate(page_dict.get('blocks', []), start=1):
            for line_dict in block_dict.get('lines', []):
                line_no_on_page += 1

                text_value = ''.join(
                    span_dict.get('text', '') for span_dict in line_dict.get('spans', [])
                ).strip()

                x1, y1, x2, y2 = get_bbox(line_dict)

                rel_x = None
                rel_y = None
                if previous_x1 is not None and x1 is not None:
                    rel_x = round(x1 - previous_x1, 1)
                if previous_y1 is not None and y1 is not None:
                    rel_y = round(y1 - previous_y1, 1)

                line_obj = Line(
                    text=text_value,
                    page_no=page_index,
                    block_no=block_index,
                    line_no_on_page=line_no_on_page,
                    font_size=dominant_font_size(line_dict),
                    x1=round_or_none(x1),
                    y1=round_or_none(y1),
                    x2=round_or_none(x2),
                    y2=round_or_none(y2),
                    rel_x=rel_x,
                    rel_y=rel_y,
                    avg_weight=average_font_weight(line_dict),
                )
                line_list.append(line_obj)

                previous_x1 = x1
                previous_y1 = y1

    return line_list
