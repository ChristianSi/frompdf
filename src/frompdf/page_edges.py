import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pdftext.schema import Page

from frompdf.models import Line, PageNumber

ROMAN_NUMERAL_PATTERN = r'[IVXLCDMivxlcdm]+'
PLAIN_VISIBLE_PAGE_LABEL_PATTERN = rf'(?:\d+|{ROMAN_NUMERAL_PATTERN})'
COMPOUND_VISIBLE_PAGE_LABEL_PATTERN = rf'(?:[A-Za-z]+|\d+)[:-]{PLAIN_VISIBLE_PAGE_LABEL_PATTERN}'
VISIBLE_PAGE_LABEL_PATTERN = (
    rf'(?:{COMPOUND_VISIBLE_PAGE_LABEL_PATTERN}|{PLAIN_VISIBLE_PAGE_LABEL_PATTERN})'
)
VALID_ROMAN_NUMERAL_PATTERN = re.compile(
    r'M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})',
    flags=re.IGNORECASE,
)
ROMAN_NUMERAL_VALUES = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
FOOTER_SUFFIX_NOISE_PATTERN = re.compile(r'(?:\$(?:NUM|ROMAN))+(?:[.)])?|[a-z0-9]{1,4}(?:[.)])?')


@dataclass
class HeaderFooterCandidate:
    """A line that may be part of a repeated header or footer."""

    index: int
    line: Line
    zone: str
    normalized: str


@dataclass
class PageTextSpan:
    """The vertical extent of visible text on one page."""

    top: float
    bottom: float


@dataclass(frozen=True)
class ParsedPageLabel:
    """A visible page label split into its stable prefix and numeric suffix."""

    prefix: str
    number: int
    numeral_system: Literal['arabic', 'roman']
    uppercase: bool = False
    width: int = 1


def roman_to_int(text: str) -> int | None:
    """Return the value of a canonical Roman numeral, ignoring case."""
    if not text or not VALID_ROMAN_NUMERAL_PATTERN.fullmatch(text):
        return None

    total = 0
    previous_value = 0
    for character in reversed(text.upper()):
        value = ROMAN_NUMERAL_VALUES[character]
        if value < previous_value:
            total -= value
        else:
            total += value
            previous_value = value
    return total


def int_to_roman(value: int, uppercase: bool) -> str | None:
    """Return a canonical Roman numeral for a value from 1 through 3999."""
    if value < 1 or value > 3999:
        return None

    parts: list[str] = []
    remainder = value
    for number, numeral in [
        (1000, 'M'),
        (900, 'CM'),
        (500, 'D'),
        (400, 'CD'),
        (100, 'C'),
        (90, 'XC'),
        (50, 'L'),
        (40, 'XL'),
        (10, 'X'),
        (9, 'IX'),
        (5, 'V'),
        (4, 'IV'),
        (1, 'I'),
    ]:
        count, remainder = divmod(remainder, number)
        parts.append(numeral * count)

    result = ''.join(parts)
    return result if uppercase else result.lower()


def parse_visible_page_label(label: str) -> ParsedPageLabel | None:
    """Parse an Arabic or Roman page label, with an optional compound prefix."""
    match = re.fullmatch(
        rf'(?P<prefix>(?:[A-Za-z]+|\d+)[:-])?(?P<number>{PLAIN_VISIBLE_PAGE_LABEL_PATTERN})',
        label,
    )
    if match is None:
        return None

    prefix = match.group('prefix') or ''
    number_text = match.group('number')
    if number_text.isdigit():
        number = int(number_text)
        if number < 1:
            return None
        return ParsedPageLabel(
            prefix=prefix,
            number=number,
            numeral_system='arabic',
            width=len(number_text) if number_text.startswith('0') else 1,
        )

    number = roman_to_int(number_text)
    if number is None:
        return None
    return ParsedPageLabel(
        prefix=prefix,
        number=number,
        numeral_system='roman',
        uppercase=number_text.isupper(),
    )


def format_visible_page_label(label: ParsedPageLabel, number: int) -> str | None:
    """Format a changed numeric suffix using an existing label's style."""
    if number < 1:
        return None

    if label.numeral_system == 'arabic':
        suffix = str(number).zfill(label.width)
    else:
        suffix = int_to_roman(number, label.uppercase)
        if suffix is None:
            return None
    return f'{label.prefix}{suffix}'


def page_label_sequences_match(left: ParsedPageLabel, right: ParsedPageLabel) -> bool:
    """Return whether two labels can safely belong to the same sequence."""
    return left.prefix == right.prefix and left.numeral_system == right.numeral_system


def normalize_header_footer_text(text: str) -> str:
    """Normalize text for detecting repeated headers and footers."""
    normalized = text.strip()
    normalized = re.sub(r'\s+', ' ', normalized)
    normalized = normalized.casefold()

    # Replace Arabic numerals.
    normalized = re.sub(r'\d+', '$NUM', normalized)

    # Replace common Roman numerals, conservatively.
    roman_pattern = r'\b[ivxlcdm]+\b'
    normalized = re.sub(roman_pattern, normalize_roman_numeral, normalized)

    # Normalize repeated punctuation around page numbers.
    normalized = re.sub(r'[–—−-]+', '-', normalized)
    normalized = re.sub(r'\s*([|•·/\\-])\s*', r'\1', normalized)

    return normalized


def normalize_roman_numeral(match: re.Match[str]) -> str:
    """Normalize plausible Roman numerals without rewriting every single letter."""
    text = match.group(0)
    if roman_to_int(text) is None:
        return text
    return '$ROMAN'


def page_text_spans(line_list: list[Line]) -> dict[int, PageTextSpan]:
    """Return the vertical text span on each page."""
    tops_by_page: dict[int, list[float]] = defaultdict(list)
    bottoms_by_page: dict[int, list[float]] = defaultdict(list)

    for line_obj in line_list:
        if not line_obj.text or line_obj.y1 is None or line_obj.y2 is None:
            continue
        tops_by_page[line_obj.page_no].append(min(line_obj.y1, line_obj.y2))
        bottoms_by_page[line_obj.page_no].append(max(line_obj.y1, line_obj.y2))

    return {
        page_no: PageTextSpan(top=min(tops), bottom=max(bottoms))
        for page_no, tops in tops_by_page.items()
        if tops and (bottoms := bottoms_by_page.get(page_no))
    }


def candidate_zone(line_obj: Line, text_span: PageTextSpan) -> str | None:
    """Return the header/footer zone for a line, if it is near the text span edge."""
    if line_obj.y1 is None or line_obj.y2 is None:
        return None

    text_height = text_span.bottom - text_span.top
    if text_height <= 0:
        return None

    edge_zone_size = max(40.0, text_height * 0.08)
    header_end = text_span.top + edge_zone_size
    footer_start = text_span.bottom - edge_zone_size
    in_header_zone = line_obj.y1 <= header_end
    in_footer_zone = line_obj.y2 >= footer_start

    if in_header_zone and in_footer_zone:
        line_center = (line_obj.y1 + line_obj.y2) / 2
        text_center = (text_span.top + text_span.bottom) / 2
        return 'header' if line_center <= text_center else 'footer'

    if in_header_zone:
        return 'header'
    if in_footer_zone:
        return 'footer'
    return None


def iter_header_footer_candidates(line_list: list[Line]) -> list[HeaderFooterCandidate]:
    """Return non-empty lines in likely header and footer zones."""
    text_spans = page_text_spans(line_list)
    candidate_list: list[HeaderFooterCandidate] = []

    for index, line_obj in enumerate(line_list):
        if not line_obj.text:
            continue

        text_span = text_spans.get(line_obj.page_no)
        if text_span is None:
            continue

        zone = candidate_zone(line_obj, text_span)
        if zone is None:
            continue

        candidate_list.append(
            HeaderFooterCandidate(
                index=index,
                line=line_obj,
                zone=zone,
                normalized=normalize_header_footer_text(line_obj.text),
            )
        )

    return candidate_list


def repeated_header_footer_keys(
    candidate_list: list[HeaderFooterCandidate], page_count: int
) -> set[tuple[str, str]]:
    """Return normalized header/footer texts that repeat on enough pages."""
    pages_by_key: dict[tuple[str, str], set[int]] = defaultdict(set)

    for candidate in candidate_list:
        pages_by_key[(candidate.zone, candidate.normalized)].add(candidate.line.page_no)

    repeated_keys: set[tuple[str, str]] = set()
    for key, page_set in pages_by_key.items():
        if len(page_set) < 3:
            continue

        first_page = min(page_set)
        last_page = max(page_set)
        page_span = last_page - first_page + 1

        # Running matter often changes at section boundaries and alternates on
        # recto/verso pages. Measure repetition over the pages where this exact
        # text can plausibly occur instead of over the entire document.
        if all(page_no % 2 == first_page % 2 for page_no in page_set):
            relevant_page_count = (last_page - first_page) // 2 + 1
        else:
            relevant_page_count = page_span

        threshold = max(3, (relevant_page_count + 3) // 4)
        if len(page_set) >= threshold:
            repeated_keys.add(key)

    return repeated_keys


def repeated_footer_text_bases(repeated_keys: set[tuple[str, str]]) -> set[str]:
    """Return stable textual parts of repeated footer lines."""
    bases: set[str] = set()
    for zone, normalized in repeated_keys:
        if zone != 'footer':
            continue

        base = re.sub(r'\s+\$(?:NUM|ROMAN)$', '', normalized)
        # A textual stem prevents the repeated page-number key itself from
        # becoming a family that absorbs unrelated numeric footer lines.
        if re.search(r'[a-z]{3}', base):
            bases.add(base)
    return bases


def matches_repeated_footer_text(candidate: HeaderFooterCandidate, bases: set[str]) -> bool:
    """Return whether a footer is a conservative OCR variant of repeated text."""
    if candidate.zone != 'footer':
        return False

    for base in bases:
        if candidate.normalized == base:
            return True
        prefix = f'{base} '
        if candidate.normalized.startswith(prefix):
            suffix = candidate.normalized[len(prefix) :]
            if FOOTER_SUFFIX_NOISE_PATTERN.fullmatch(suffix):
                return True
    return False


def explicit_visible_page_number(text: str) -> str | None:
    """Extract an explicit page number from common page labels."""
    match = re.match(
        rf'\s*(?:page|página)\s+({VISIBLE_PAGE_LABEL_PATTERN})\b',
        text,
        flags=re.IGNORECASE,
    )
    if match:
        visible = match.group(1)
        if parse_visible_page_label(visible) is not None:
            return visible

    return None


def edge_visible_page_label(text: str, edge: str) -> str | None:
    """Return a visible page label at the requested edge of a line."""
    if edge == 'start':
        compound_match = re.match(rf'\s*({COMPOUND_VISIBLE_PAGE_LABEL_PATTERN})\b', text)
        if compound_match:
            visible = compound_match.group(1)
            if parse_visible_page_label(visible) is not None:
                return visible

        plain_match = re.match(rf'\s*({PLAIN_VISIBLE_PAGE_LABEL_PATTERN})(?=\s|$)', text)
        if plain_match:
            visible = plain_match.group(1)
            if parse_visible_page_label(visible) is not None:
                return visible
        return None

    compound_match = re.search(rf'\b({COMPOUND_VISIBLE_PAGE_LABEL_PATTERN})\s*$', text)
    if compound_match:
        visible = compound_match.group(1)
        if parse_visible_page_label(visible) is not None:
            return visible

    plain_match = re.search(rf'(?:^|\s)({PLAIN_VISIBLE_PAGE_LABEL_PATTERN})\s*$', text)
    if plain_match:
        visible = plain_match.group(1)
        if parse_visible_page_label(visible) is not None:
            return visible
    return None


def infer_repeated_page_numbers(
    candidate_list: list[HeaderFooterCandidate], repeated_keys: set[tuple[str, str]]
) -> dict[int, str]:
    """Infer page numbers embedded in repeated header/footer text."""
    candidates_by_key: dict[tuple[str, str], list[HeaderFooterCandidate]] = defaultdict(list)
    page_numbers: dict[int, str] = {}

    for candidate in candidate_list:
        key = (candidate.zone, candidate.normalized)
        if key in repeated_keys:
            candidates_by_key[key].append(candidate)

    for repeated_candidates in candidates_by_key.values():
        labels_by_position: dict[tuple[int, str], list[tuple[int, str, int]]] = defaultdict(list)
        for candidate in repeated_candidates:
            matches = re.finditer(rf'\b{PLAIN_VISIBLE_PAGE_LABEL_PATTERN}\b', candidate.line.text)
            for position, match in enumerate(matches):
                visible = match.group(0)
                parsed_label = parse_visible_page_label(visible)
                if parsed_label is None:
                    continue
                labels_by_position[(position, parsed_label.numeral_system)].append(
                    (candidate.line.page_no, visible, parsed_label.number)
                )

        for raw_visible_and_number in labels_by_position.values():
            offsets = Counter(number - raw for raw, _, number in raw_visible_and_number)
            if not offsets:
                continue

            offset, offset_count = offsets.most_common(1)[0]
            if offset_count < max(3, len(raw_visible_and_number) * 2 // 3):
                continue

            for raw, visible, number in raw_visible_and_number:
                if number - raw == offset:
                    page_numbers.setdefault(raw, visible)

    return page_numbers


def outermost_edge_candidates(
    candidate_list: list[HeaderFooterCandidate],
) -> list[HeaderFooterCandidate]:
    """Limit layout-based inference to the outermost text row in each zone."""
    edges: dict[tuple[int, str], float] = {}
    for candidate in candidate_list:
        y = candidate.line.y1 if candidate.zone == 'header' else candidate.line.y2
        if y is None:
            continue
        key = (candidate.line.page_no, candidate.zone)
        if key not in edges:
            edges[key] = y
        elif candidate.zone == 'header':
            edges[key] = min(edges[key], y)
        else:
            edges[key] = max(edges[key], y)

    result = []
    for candidate in candidate_list:
        y = candidate.line.y1 if candidate.zone == 'header' else candidate.line.y2
        if y is not None and abs(y - edges[(candidate.line.page_no, candidate.zone)]) <= 3.0:
            result.append(candidate)
    return result


def page_label_layouts_match(left: HeaderFooterCandidate, right: HeaderFooterCandidate) -> bool:
    """Compare running-label rows, allowing scan jitter for number-only lines."""
    if left.zone != right.zone or left.line.y1 is None or right.line.y1 is None:
        return False
    standalone = all(
        re.fullmatch(VISIBLE_PAGE_LABEL_PATTERN, candidate.line.text.strip())
        for candidate in (left, right)
    )
    # Scanned standalone folios have less stable bounding boxes than text
    # headers. Changing header titles must share both a row and a font.
    tolerance = 20.0 if standalone else 3.0
    if abs(left.line.y1 - right.line.y1) > tolerance:
        return False
    return (
        standalone
        or left.line.font_name == right.line.font_name
        or left.line.text.strip().isdigit()
        or right.line.text.strip().isdigit()
    )


def infer_edge_page_numbers(candidate_list: list[HeaderFooterCandidate]) -> dict[int, str]:
    """Recognize local pagination, then retain labels across jumps and duplicates."""
    labels: list[tuple[HeaderFooterCandidate, str, ParsedPageLabel, str]] = []
    labels_by_raw: dict[int, list[tuple[HeaderFooterCandidate, ParsedPageLabel]]] = defaultdict(
        list
    )
    for candidate in outermost_edge_candidates(candidate_list):
        for edge in ['start', 'end']:
            visible = edge_visible_page_label(candidate.line.text, edge)
            parsed = parse_visible_page_label(visible) if visible is not None else None
            if visible is not None and parsed is not None:
                labels.append((candidate, visible, parsed, edge))
                labels_by_raw[candidate.line.page_no].append((candidate, parsed))

    supported: set[int] = set()
    for index, (candidate, _, parsed, _) in enumerate(labels):
        raw = candidate.line.page_no
        agreeing_pages = set()
        for other_raw in range(raw - 8, raw + 9):
            for other, other_label in labels_by_raw.get(other_raw, []):
                if (
                    page_label_sequences_match(parsed, other_label)
                    and other_label.number - other_raw == parsed.number - raw
                    and page_label_layouts_match(candidate, other)
                ):
                    agreeing_pages.add(other_raw)

        # Three distinct pages in an eight-page span establish a local run.
        # Opposite-parity Roman labels retain the existing two-anchor allowance.
        for first in sorted(agreeing_pages):
            window = {page for page in agreeing_pages if first <= page <= first + 8}
            if raw not in window:
                continue
            roman_pair = (
                parsed.numeral_system == 'roman'
                and min(parsed.number + page - raw for page in window) >= 4
                and any(page % 2 != raw % 2 for page in window)
            )
            if len(window) >= 3 or roman_pair:
                supported.add(index)
                break

    recognized = set(supported)
    for index, (candidate, _, parsed, edge) in enumerate(labels):
        if index in supported:
            continue
        # Once a numeric slot in repeated running matter is established, a
        # different offset need not invalidate its readable labels. Use only
        # original anchors here so one accepted outlier cannot grow a family.
        layout_anchors = [
            (other, other_label, other_edge)
            for other_index in supported
            for other, _, other_label, other_edge in [labels[other_index]]
            if page_label_sequences_match(parsed, other_label)
            and page_label_layouts_match(candidate, other)
        ]
        raw = candidate.line.page_no
        family = [
            (other.line.page_no, other_label.number)
            for other, other_label, other_edge in layout_anchors
            if candidate.normalized == other.normalized and edge == other_edge
        ]
        nearby = [
            (other.line.page_no, other_label.number)
            for other, other_label, _ in layout_anchors
            if abs(other.line.page_no - raw) <= 8
        ]
        # Repeated text can support jumps. Changing titles can share nearby
        # layout evidence, but may only advance with page order (or repeat a
        # number on a duplicate page), not introduce an arbitrary jump.
        for anchors, allow_jumps in [(family, True), (nearby, False)]:
            if len({page for page, _ in anchors}) < 3:
                continue
            before = [(page, number) for page, number in anchors if page < raw]
            after = [(page, number) for page, number in anchors if page > raw]
            if before:
                page, number = max(before)
                if parsed.number < number or (
                    not allow_jumps and parsed.number - number > raw - page
                ):
                    continue
            if after:
                page, number = min(after)
                if parsed.number > number or (
                    not allow_jumps and number - parsed.number > page - raw
                ):
                    continue
            recognized.add(index)
            break

    labels_by_page: dict[int, set[str]] = defaultdict(set)
    for index in recognized:
        candidate, visible, _, _ = labels[index]
        labels_by_page[candidate.line.page_no].add(visible)
    return {raw: next(iter(values)) for raw, values in labels_by_page.items() if len(values) == 1}


def has_edge_page_number(text: str, visible: str) -> bool:
    """Return whether a line starts or ends with a known visible page number."""
    return any(edge_visible_page_label(text, edge) == visible for edge in ['start', 'end'])


def recover_ocr_footer_numbers(
    candidate_list: list[HeaderFooterCandidate], visible_by_raw: dict[int, str]
) -> set[int]:
    """Recover isolated OCR folios only when an adjacent Arabic label agrees."""
    standalone_by_page = {
        candidate.line.page_no: candidate
        for candidate in outermost_edge_candidates(candidate_list)
        if candidate.zone == 'footer'
        and candidate.line.text.strip() == visible_by_raw.get(candidate.line.page_no)
        and candidate.line.text.strip().isdigit()
    }
    recovered: set[int] = set()
    for candidate in outermost_edge_candidates(candidate_list):
        raw = candidate.line.page_no
        text = candidate.line.text.strip()
        if (
            candidate.zone != 'footer'
            or raw in visible_by_raw
            or not re.fullmatch(r'[0-9IOilT]{1,6}', text)
            or text.isdigit()
        ):
            continue
        visible = text.translate(str.maketrans({'I': '1', 'O': '0', 'i': '1', 'l': '1', 'T': '1'}))
        if int(visible) < 1:
            continue
        for other_raw in [raw - 1, raw + 1]:
            other = standalone_by_page.get(other_raw)
            if other is None or candidate.line.y1 is None or other.line.y1 is None:
                continue
            x1, x2 = candidate.line.x1, candidate.line.x2
            other_x1, other_x2 = other.line.x1, other.line.x2
            if x1 is None or x2 is None or other_x1 is None or other_x2 is None:
                continue
            # Use the same scan tolerance as standalone readable folios. The
            # substitution must also advance by exactly one from a real label.
            if (
                abs(candidate.line.y1 - other.line.y1) <= 20.0
                and abs((x1 + x2 - other_x1 - other_x2) / 2) <= 20.0
                and candidate.line.font_name == other.line.font_name
                and int(visible) - int(other.line.text.strip()) == raw - other_raw
            ):
                visible_by_raw[raw] = visible
                recovered.add(candidate.index)
                break
    return recovered


def add_same_baseline_footer_companions(
    excluded_indices: set[int], candidate_list: list[HeaderFooterCandidate]
) -> None:
    """Also exclude footer candidates printed on the same baseline as excluded footer text."""
    excluded_footer_y_by_page: dict[int, list[float]] = defaultdict(list)

    for candidate in candidate_list:
        if candidate.index not in excluded_indices or candidate.zone != 'footer':
            continue
        if candidate.line.y1 is not None:
            excluded_footer_y_by_page[candidate.line.page_no].append(candidate.line.y1)

    for candidate in candidate_list:
        if candidate.index in excluded_indices or candidate.zone != 'footer':
            continue
        if candidate.line.y1 is None:
            continue
        if any(
            abs(candidate.line.y1 - excluded_y) <= 3.0
            for excluded_y in excluded_footer_y_by_page[candidate.line.page_no]
        ):
            excluded_indices.add(candidate.index)


def remove_headers_and_footers(
    line_list: list[Line], page_list: Sequence[Page]
) -> tuple[list[Line], list[PageNumber]]:
    """Remove repeated header/footer lines and collect visible page numbers."""
    candidate_list = iter_header_footer_candidates(line_list)
    repeated_keys = repeated_header_footer_keys(candidate_list, len(page_list))
    repeated_footer_bases = repeated_footer_text_bases(repeated_keys)
    outermost_indices = {candidate.index for candidate in outermost_edge_candidates(candidate_list)}
    excluded_indices: set[int] = set()
    visible_by_raw = infer_repeated_page_numbers(candidate_list, repeated_keys)
    visible_by_raw.update(infer_edge_page_numbers(candidate_list))
    excluded_indices.update(recover_ocr_footer_numbers(candidate_list, visible_by_raw))

    for candidate in candidate_list:
        key = (candidate.zone, candidate.normalized)
        explicit_visible = explicit_visible_page_number(candidate.line.text)
        inferred_visible = visible_by_raw.get(candidate.line.page_no)

        if (
            key in repeated_keys
            or matches_repeated_footer_text(candidate, repeated_footer_bases)
            or explicit_visible is not None
        ):
            excluded_indices.add(candidate.index)
        elif (
            candidate.index in outermost_indices
            and inferred_visible is not None
            and has_edge_page_number(candidate.line.text, inferred_visible)
        ):
            excluded_indices.add(candidate.index)

        if explicit_visible is not None:
            visible_by_raw.setdefault(candidate.line.page_no, explicit_visible)

    add_same_baseline_footer_companions(excluded_indices, candidate_list)

    filtered_lines = [
        line_obj for index, line_obj in enumerate(line_list) if index not in excluded_indices
    ]
    page_number_list = [
        PageNumber(raw=raw, visible=visible) for raw, visible in sorted(visible_by_raw.items())
    ]

    return filtered_lines, page_number_list


def complete_page_numbers(
    page_count: int, detected_page_number_list: list[PageNumber]
) -> list[PageNumber]:
    """Return every raw page, filling only unambiguous visible-number gaps."""
    detected_by_raw = {
        page_number.raw: page_number.visible
        for page_number in detected_page_number_list
        if 1 <= page_number.raw <= page_count and page_number.visible is not None
    }
    completed_by_raw: dict[int, str | None] = {
        raw: detected_by_raw.get(raw) for raw in range(1, page_count + 1)
    }
    detected_items = sorted(detected_by_raw.items())

    # Compare adjacent printed anchors: disagreement leaves the whole gap
    # unknown, even if a more distant sequence would supply a plausible label.
    # At document edges only one side supplies evidence. The nearest pair must
    # establish a sequence before we extrapolate it; a lone label is not enough.
    for index, ((left_raw, left_visible), (right_raw, right_visible)) in enumerate(
        zip(detected_items, detected_items[1:], strict=False)
    ):
        left_label = parse_visible_page_label(left_visible)
        right_label = parse_visible_page_label(right_visible)
        if (
            left_label is None
            or right_label is None
            or not page_label_sequences_match(left_label, right_label)
            or right_label.number - left_label.number != right_raw - left_raw
        ):
            continue

        start = 1 if index == 0 else left_raw + 1
        end = page_count + 1 if index == len(detected_items) - 2 else right_raw
        for raw in range(start, end):
            if completed_by_raw[raw] is not None:
                continue
            anchor_raw, anchor_label = (
                (right_raw, right_label) if raw > right_raw else (left_raw, left_label)
            )
            guessed = format_visible_page_label(
                anchor_label, anchor_label.number + (raw - anchor_raw)
            )
            if guessed is not None:
                completed_by_raw[raw] = guessed

    return [PageNumber(raw=raw, visible=completed_by_raw[raw]) for raw in range(1, page_count + 1)]


def build_page_number_map(
    page_count: int, visible_page_number_list: list[PageNumber]
) -> dict[int, PageNumber]:
    """Return PageNumber metadata for every raw page."""
    page_number_map = {raw: PageNumber(raw=raw, visible=None) for raw in range(1, page_count + 1)}

    for page_number in visible_page_number_list:
        page_number_map[page_number.raw] = page_number

    return page_number_map
