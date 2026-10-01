import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from difflib import SequenceMatcher
from unicodedata import category, name, normalize

from pdftext.schema import (
    Char as PdfTextChar,
)
from pdftext.schema import (
    Line as PdfTextLine,
)
from pdftext.schema import (
    Page,
)
from pdftext.schema import (
    Span as PdfTextSpan,
)

from frompdf.models import Line, ScriptRange
from frompdf.scripts import AnnotatedText

SPACING_TO_COMBINING = {
    '¨': '\u0308',
    '´': '\u0301',
    '`': '\u0300',
    '^': '\u0302',
    '~': '\u0303',
}

BOLD_FONT_NAME_PATTERN = re.compile(
    r'(?:bold|black|heavy|semi[- ]?bold|demi[- ]?bold|[.+_-](?:b|bd|sb)(?:it)?$)',
    flags=re.IGNORECASE,
)


def round_or_none(value: float | int | None, digits: int = 1) -> float | None:
    """Round a numeric value, or return None."""
    if value is None:
        return None
    return round(float(value), digits)


def get_bbox(
    obj: PdfTextChar | PdfTextLine | PdfTextSpan,
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


def composed_diacritic(base_text: str, spacing_accent: str) -> str | None:
    """Return a precomposed Latin letter for a supported base/accent pair."""
    combining_accent = SPACING_TO_COMBINING.get(spacing_accent)
    if len(base_text) != 1 or combining_accent is None:
        return None
    if not base_text.isascii() or category(base_text) not in {'Ll', 'Lu'}:
        return None

    composed = normalize('NFC', base_text + combining_accent)
    if len(composed) != 1 or composed == base_text:
        return None
    return composed


def diacritic_geometry_score(
    accent_char: PdfTextChar, base_char: PdfTextChar
) -> tuple[float, float, float] | None:
    """Score a strongly overlapping accent/base pair, or reject its geometry."""
    if abs(float(accent_char.get('rotation', 0)) - float(base_char.get('rotation', 0))) > 0.1:
        return None

    accent_x1, accent_y1, accent_x2, accent_y2 = get_bbox(accent_char)
    base_x1, base_y1, base_x2, base_y2 = get_bbox(base_char)
    if None in {
        accent_x1,
        accent_y1,
        accent_x2,
        accent_y2,
        base_x1,
        base_y1,
        base_x2,
        base_y2,
    }:
        return None

    # The None check above narrows these values for runtime, but not for basedpyright.
    assert accent_x1 is not None
    assert accent_y1 is not None
    assert accent_x2 is not None
    assert accent_y2 is not None
    assert base_x1 is not None
    assert base_y1 is not None
    assert base_x2 is not None
    assert base_y2 is not None

    accent_width = accent_x2 - accent_x1
    accent_height = accent_y2 - accent_y1
    base_width = base_x2 - base_x1
    base_height = base_y2 - base_y1
    if min(accent_width, accent_height, base_width, base_height) <= 0:
        return None

    horizontal_overlap = max(0.0, min(accent_x2, base_x2) - max(accent_x1, base_x1))
    overlap_ratio = horizontal_overlap / min(accent_width, base_width)
    horizontal_distance = abs((accent_x1 + accent_x2) / 2 - (base_x1 + base_x2) / 2)
    horizontal_ratio = horizontal_distance / base_width

    accent_center_y = (accent_y1 + accent_y2) / 2
    base_center_y = (base_y1 + base_y2) / 2
    vertical_offset = accent_center_y - base_center_y
    vertical_ratio = abs(vertical_offset) / base_height

    # pdftext loose glyph boxes often give a detached TeX accent almost the same
    # vertical extent as its base. Horizontal coincidence is therefore the strongest
    # signal; the vertical bounds allow both loose boxes and a smaller accent above.
    if (
        overlap_ratio < 0.8
        or horizontal_ratio > 0.25
        or vertical_offset < -base_height
        or vertical_offset > base_height * 0.25
    ):
        return None

    return horizontal_ratio, vertical_ratio, -overlap_ratio


def span_char_text_ranges(span_dict: PdfTextSpan) -> dict[int, tuple[int, int]]:
    """Map pdftext character objects to their ranges in the decoded span text."""
    char_list = span_dict.get('chars', [])
    raw_parts: list[str] = []
    raw_ranges: dict[int, tuple[int, int]] = {}
    raw_offset = 0

    for char_index, char_dict in enumerate(char_list):
        char_text = char_dict.get('char', '')
        # pdftext exposes CRLF as two characters but decodes it to one newline in
        # Span.text. Treat the CR as having no textual representation.
        if char_text == '\r' and char_index + 1 < len(char_list):
            if char_list[char_index + 1].get('char') == '\n':
                continue

        raw_parts.append(char_text)
        raw_ranges[id(char_dict)] = (raw_offset, raw_offset + len(char_text))
        raw_offset += len(char_text)

    raw_text = ''.join(raw_parts)
    decoded_text = span_dict.get('text', '')
    text_ranges: dict[int, tuple[int, int]] = {}
    opcodes = SequenceMatcher(None, raw_text, decoded_text, autojunk=False).get_opcodes()

    for char_id, (raw_start, raw_end) in raw_ranges.items():
        for tag, raw_block_start, raw_block_end, text_start, text_end in opcodes:
            if raw_start < raw_block_start or raw_end > raw_block_end:
                continue

            raw_length = raw_block_end - raw_block_start
            text_length = text_end - text_start
            if tag == 'equal' or (tag == 'replace' and raw_length == text_length):
                mapped_start = text_start + raw_start - raw_block_start
                text_ranges[char_id] = (mapped_start, mapped_start + raw_end - raw_start)
            break

    return text_ranges


def spacing_artifact_touches_accent(whitespace_char: PdfTextChar, accent_char: PdfTextChar) -> bool:
    """Return whether a zero-width space was inserted beside an out-of-order accent."""
    whitespace_text = whitespace_char.get('char', '')
    if not whitespace_text.isspace() or whitespace_text in {'\r', '\n'}:
        return False

    whitespace_x1, whitespace_y1, whitespace_x2, whitespace_y2 = get_bbox(whitespace_char)
    accent_x1, accent_y1, accent_x2, accent_y2 = get_bbox(accent_char)
    if None in {
        whitespace_x1,
        whitespace_y1,
        whitespace_x2,
        whitespace_y2,
        accent_x1,
        accent_y1,
        accent_x2,
        accent_y2,
    }:
        return False

    assert whitespace_x1 is not None
    assert whitespace_y1 is not None
    assert whitespace_x2 is not None
    assert whitespace_y2 is not None
    assert accent_x1 is not None
    assert accent_y1 is not None
    assert accent_x2 is not None
    assert accent_y2 is not None

    accent_width = accent_x2 - accent_x1
    accent_height = accent_y2 - accent_y1
    if accent_width <= 0 or accent_height <= 0 or abs(whitespace_x2 - whitespace_x1) > 0.1:
        return False

    edge_distance = min(abs(whitespace_x1 - accent_x1), abs(whitespace_x1 - accent_x2))
    horizontal_tolerance = max(0.5, accent_width * 0.2)
    vertical_tolerance = accent_height * 0.5
    return (
        edge_distance <= horizontal_tolerance
        and accent_y1 - vertical_tolerance <= whitespace_y1 <= accent_y2 + vertical_tolerance
    )


def normalize_detached_diacritics(page_list: Sequence[Page]) -> None:
    """Merge geometrically attached spacing accents into base characters in-place."""
    for page_dict in page_list:
        for block_dict in page_dict.get('blocks', []):
            for line_dict in block_dict.get('lines', []):
                positioned_chars: list[tuple[PdfTextSpan, PdfTextChar]] = []
                for span_dict in line_dict.get('spans', []):
                    positioned_chars.extend(
                        (span_dict, char_dict) for char_dict in span_dict.get('chars', [])
                    )

                accent_chars = [
                    (span_dict, char_dict)
                    for span_dict, char_dict in positioned_chars
                    if char_dict.get('char') in SPACING_TO_COMBINING
                ]
                if not accent_chars:
                    continue

                used_base_ids: set[int] = set()
                span_by_id = {id(span_dict): span_dict for span_dict in line_dict.get('spans', [])}
                text_ranges_by_span_id = {
                    span_id: span_char_text_ranges(span_dict)
                    for span_id, span_dict in span_by_id.items()
                }
                pending_edits: dict[int, dict[int, tuple[PdfTextChar, str]]] = defaultdict(dict)

                for accent_span, accent_char in accent_chars:
                    spacing_accent = accent_char.get('char', '')
                    if spacing_accent not in SPACING_TO_COMBINING:
                        continue

                    candidates: list[
                        tuple[tuple[float, float, float], PdfTextSpan, PdfTextChar, str]
                    ] = []
                    for base_span, base_char in positioned_chars:
                        if base_char is accent_char or id(base_char) in used_base_ids:
                            continue

                        composed = composed_diacritic(base_char.get('char', ''), spacing_accent)
                        if composed is None:
                            continue

                        score = diacritic_geometry_score(accent_char, base_char)
                        if score is not None:
                            candidates.append((score, base_span, base_char, composed))

                    if not candidates:
                        continue

                    _, base_span, base_char, composed = min(candidates, key=lambda item: item[0])
                    accent_span_id = id(accent_span)
                    base_span_id = id(base_span)
                    if (
                        id(accent_char) not in text_ranges_by_span_id[accent_span_id]
                        or id(base_char) not in text_ranges_by_span_id[base_span_id]
                    ):
                        continue

                    pending_edits[base_span_id][id(base_char)] = (base_char, composed)
                    pending_edits[accent_span_id][id(accent_char)] = (accent_char, '')
                    used_base_ids.add(id(base_char))

                    for whitespace_span, whitespace_char in positioned_chars:
                        whitespace_span_id = id(whitespace_span)
                        if (
                            spacing_artifact_touches_accent(whitespace_char, accent_char)
                            and id(whitespace_char) in text_ranges_by_span_id[whitespace_span_id]
                        ):
                            pending_edits[whitespace_span_id][id(whitespace_char)] = (
                                whitespace_char,
                                '',
                            )

                for span_id, edits in pending_edits.items():
                    span_dict = span_by_id[span_id]
                    text_edits = [
                        (*text_ranges_by_span_id[span_id][char_id], replacement)
                        for char_id, (_, replacement) in edits.items()
                    ]
                    text_value = span_dict.get('text', '')
                    for start, end, replacement in sorted(text_edits, reverse=True):
                        text_value = text_value[:start] + replacement + text_value[end:]
                    span_dict['text'] = text_value

                    for char_dict, replacement in edits.values():
                        char_dict['char'] = replacement


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


def dominant_font_name(line_dict: PdfTextLine) -> str | None:
    """Return the font name used for most of the visible text in a line."""
    name_weights: dict[str, int] = defaultdict(int)

    for span_dict in line_dict.get('spans', []):
        text_value = span_dict.get('text', '')
        weight = len(text_value.strip())
        font_name = span_dict.get('font', {}).get('name')
        if not weight or not isinstance(font_name, str) or not font_name:
            continue
        name_weights[font_name] += weight

    if not name_weights:
        return None

    return max(name_weights.items(), key=lambda item: (item[1], item[0]))[0]


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

        # Some embedded fonts report weight 0 for every span even though their
        # names retain a conventional bold marker such as `.B` or `-Bold`.
        font_name = font_dict.get('name')
        if font_weight == 0 and isinstance(font_name, str):
            if BOLD_FONT_NAME_PATTERN.search(font_name):
                font_weight = 700

        weighted_sum += float(font_weight) * weight
        total_weight += weight

    if not total_weight:
        return None

    return round(weighted_sum / total_weight, 1)


# Require at least a 15% size reduction and a center shift of 15% of the
# neighboring ordinary glyph height. Graf's raised markers shift by only 17%;
# Nature's lowered formula digits have a size ratio of about two-thirds.
SCRIPT_MAX_SIZE_RATIO = 0.85
SCRIPT_MIN_CENTER_SHIFT = 0.15
SCRIPT_PUNCTUATION = frozenset('.*,;:+−–-=()[]<>/†‡')


def line_script_ranges(
    line_dict: PdfTextLine, neighbors: Sequence[PdfTextLine] = ()
) -> tuple[ScriptRange, ...]:
    """Recognize small shifted glyphs, including those inside ordinary spans."""
    # Entries retain decoded offsets, not raw character indices: ligatures and
    # CRLF normalization can make those differ. Detached accents are repaired
    # before this function is called.
    glyphs: list[tuple[int, int, PdfTextChar, tuple[float, float, float, float], float]] = []
    offset = 0
    for span in line_dict.get('spans', []):
        ranges = span_char_text_ranges(span)
        for char in span.get('chars', []):
            char_text = char.get('char', '')
            if not char_text or not all(c.isalnum() or c in SCRIPT_PUNCTUATION for c in char_text):
                continue
            if abs(float(char.get('rotation', 0))) > 0.1 or id(char) not in ranges:
                continue
            x1, y1, x2, y2 = get_bbox(char)
            if x1 is None or y1 is None or x2 is None or y2 is None or x2 <= x1 or y2 <= y1:
                continue
            size = float(char.get('font', {}).get('size', 1) or 1)
            start, end = ranges[id(char)]
            glyphs.append((offset + start, offset + end, char, (x1, y1, x2, y2), size))
        offset += len(span.get('text', ''))

    ordinary = [g for g in glyphs if g[2].get('char', '').isalnum()]
    if not ordinary:
        return ()
    # Only use reported sizes when all visible alphanumerics have real sizes.
    # Nature reports size 1.0 even for differently scaled characters.
    real_sizes = all(g[4] > 1 for g in ordinary)
    sizes = Counter(round(g[4] if real_sizes else g[3][3] - g[3][1], 1) for g in ordinary)
    dominant = max(sizes, key=lambda size: (sizes[size], size))
    if dominant <= 0:
        return ()
    references = [
        g
        for g in ordinary
        if abs((g[4] if real_sizes else g[3][3] - g[3][1]) - dominant) <= dominant * 0.08
    ]
    if not references:
        return ()
    runs: list[ScriptRange] = []
    for start, end, char, box, size in glyphs:
        candidate_size = size if real_sizes else box[3] - box[1]
        if candidate_size > dominant * SCRIPT_MAX_SIZE_RATIO:
            continue
        reference = min(
            references,
            key=lambda g: abs((g[3][0] + g[3][2]) / 2 - (box[0] + box[2]) / 2),
        )
        ref_box = reference[3]
        height = ref_box[3] - ref_box[1]
        horizontal_gap = max(0.0, ref_box[0] - box[2], box[0] - ref_box[2])
        if horizontal_gap > height * 6:
            continue
        shift = ((box[1] + box[3]) - (ref_box[1] + ref_box[3])) / (2 * height)
        # A smaller character sitting on the ordinary baseline (e.g. small
        # caps) is not a subscript. Validate direction independently of pdftext
        # flags, which sometimes mislabel lowered C/j as superscripts.
        if (
            -0.8 <= shift <= -SCRIPT_MIN_CENTER_SHIFT
            and box[1] <= ref_box[1] + height * 0.08
            and box[3] < ref_box[3] - height * 0.15
        ):
            kind = 'sup'
        elif (
            SCRIPT_MIN_CENTER_SHIFT <= shift <= 0.8
            and box[3] > ref_box[3] + height * 0.04
            and box[1] > ref_box[1] + height * 0.15
        ):
            kind = 'sub'
        else:
            continue
        # Do not apply another script level to an already encoded script glyph.
        if any('SUPERSCRIPT' in name(c, '') or 'SUBSCRIPT' in name(c, '') for c in char['char']):
            continue
        runs.append(ScriptRange(start, end, kind))
    # A small numerator can look like an inline superscript. Reject only the
    # touching script group when another extraction line is stacked immediately
    # above/below it, preserving unrelated scripts elsewhere on the same line.
    groups: list[list[ScriptRange]] = []
    for run in runs:
        if not groups or groups[-1][-1].end != run.start or groups[-1][-1].kind != run.kind:
            groups.append([])
        groups[-1].append(run)
    kept: list[ScriptRange] = []
    for group in groups:
        boxes = [g[3] for g in glyphs if group[0].start <= g[0] < group[-1].end]
        script_box = (
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        )
        if not has_stacked_text(line_dict, neighbors, script_box, group[0]):
            kept.extend(group)
    return tuple(kept)


def has_stacked_text(
    line: PdfTextLine,
    neighbors: Sequence[PdfTextLine],
    script_box: tuple[float, float, float, float],
    run: ScriptRange,
) -> bool:
    """Avoid interpreting the numerator of a vertically stacked fraction as a script."""
    x1, y1, x2, y2 = get_bbox(line)
    if x1 is None or y1 is None or x2 is None or y2 is None:
        return False
    for neighbor in neighbors:
        if neighbor is line:
            continue
        nx1, ny1, nx2, ny2 = get_bbox(neighbor)
        if nx1 is None or ny1 is None or nx2 is None or ny2 is None:
            continue
        if min(script_box[2], nx2) <= max(script_box[0], nx1):
            continue
        gap = ny1 - script_box[3] if run.kind == 'sup' else script_box[1] - ny2
        if not 0 <= gap <= (y2 - y1) * 0.3:
            continue
        # Numerator/denominator centers are much closer than consecutive prose
        # lines. Ignore nearly identical baselines, which can be split blocks.
        distance = abs((y1 + y2 - ny1 - ny2) / 2)
        if min(y2 - y1, ny2 - ny1) * 0.1 < distance < max(y2 - y1, ny2 - ny1) * 0.6:
            return True
    return False


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

                raw_text = ''.join(
                    span_dict.get('text', '') for span_dict in line_dict.get('spans', [])
                )
                text_value = raw_text.strip()
                scripts = line_script_ranges(line_dict, block_dict.get('lines', []))
                annotated = AnnotatedText(raw_text, scripts).slice(
                    len(raw_text) - len(raw_text.lstrip()), len(raw_text.rstrip())
                )

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
                    font_name=dominant_font_name(line_dict),
                    scripts=annotated.scripts,
                )
                line_list.append(line_obj)

                previous_x1 = x1
                previous_y1 = y1

    return line_list
