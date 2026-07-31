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
    threshold = max(3, (page_count + 3) // 4)

    for candidate in candidate_list:
        pages_by_key[(candidate.zone, candidate.normalized)].add(candidate.line.page_no)

    return {key for key, page_set in pages_by_key.items() if len(page_set) >= threshold}


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


def visible_page_label_sort_number(label: str) -> int | None:
    """Return the numeric part that should track raw page order."""
    parsed_label = parse_visible_page_label(label)
    return parsed_label.number if parsed_label is not None else None


def is_compound_visible_page_label(label: str) -> bool:
    """Return whether a visible page label has a section/article prefix."""
    return bool(re.fullmatch(COMPOUND_VISIBLE_PAGE_LABEL_PATTERN, label))


def edge_visible_page_label(text: str, edge: str) -> str | None:
    """Return a visible page label at the requested edge of a line."""
    if edge == 'start':
        compound_match = re.match(rf'\s*({COMPOUND_VISIBLE_PAGE_LABEL_PATTERN})\b', text)
        if compound_match:
            visible = compound_match.group(1)
            if parse_visible_page_label(visible) is not None:
                return visible

        plain_match = re.fullmatch(rf'\s*({PLAIN_VISIBLE_PAGE_LABEL_PATTERN})\s*', text)
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


def infer_edge_page_numbers(candidate_list: list[HeaderFooterCandidate]) -> dict[int, str]:
    """Infer visible page numbers printed at the start or end of edge lines."""
    labels_by_page_and_position: dict[tuple[str, str], dict[int, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    page_numbers: dict[int, str] = {}

    for candidate in candidate_list:
        for edge in ['start', 'end']:
            visible = edge_visible_page_label(candidate.line.text, edge)
            if visible is not None:
                labels_by_page_and_position[(candidate.zone, edge)][candidate.line.page_no].add(
                    visible
                )

    for labels_by_page in labels_by_page_and_position.values():
        offsets: Counter[int] = Counter()
        for raw, visible_labels in labels_by_page.items():
            page_offsets = set()
            for visible in visible_labels:
                sort_number = visible_page_label_sort_number(visible)
                if sort_number is not None:
                    page_offsets.add(sort_number - raw)
            offsets.update(page_offsets)
        if not offsets:
            continue

        offset, offset_count = offsets.most_common(1)[0]
        if offset_count < max(3, len(labels_by_page) * 2 // 3):
            continue

        for raw, visible_labels in labels_by_page.items():
            matching_labels = []
            for visible in visible_labels:
                sort_number = visible_page_label_sort_number(visible)
                if sort_number is not None and sort_number - raw == offset:
                    matching_labels.append(visible)
            matching_labels.sort()
            if matching_labels:
                visible = matching_labels[0]
                page_numbers.setdefault(raw, visible)

    return page_numbers


def has_edge_page_number(text: str, visible: str) -> bool:
    """Return whether a line starts or ends with a known visible page number."""
    if is_compound_visible_page_label(visible):
        return bool(re.search(rf'^\s*{re.escape(visible)}\b', text)) or bool(
            re.search(rf'\b{re.escape(visible)}\s*$', text)
        )

    return bool(re.fullmatch(rf'\s*{re.escape(visible)}\s*', text)) or bool(
        re.search(rf'\b{re.escape(visible)}\s*$', text)
    )


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
    excluded_indices: set[int] = set()
    visible_by_raw = infer_repeated_page_numbers(candidate_list, repeated_keys)
    visible_by_raw.update(infer_edge_page_numbers(candidate_list))

    for candidate in candidate_list:
        key = (candidate.zone, candidate.normalized)
        explicit_visible = explicit_visible_page_number(candidate.line.text)
        inferred_visible = visible_by_raw.get(candidate.line.page_no)

        if key in repeated_keys or explicit_visible is not None:
            excluded_indices.add(candidate.index)
        elif inferred_visible is not None and has_edge_page_number(
            candidate.line.text, inferred_visible
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

    if detected_items:
        first_raw, first_visible = detected_items[0]
        first_label = parse_visible_page_label(first_visible)
        if first_label is not None and not first_label.prefix:
            for raw in range(1, first_raw):
                guessed = format_visible_page_label(
                    first_label, first_label.number - (first_raw - raw)
                )
                if guessed is not None:
                    completed_by_raw[raw] = guessed

        last_raw, last_visible = detected_items[-1]
        last_label = parse_visible_page_label(last_visible)
        if last_label is not None and not last_label.prefix:
            for raw in range(last_raw + 1, page_count + 1):
                guessed = format_visible_page_label(
                    last_label, last_label.number + (raw - last_raw)
                )
                if guessed is not None:
                    completed_by_raw[raw] = guessed

    for (left_raw, left_visible), (right_raw, right_visible) in zip(
        detected_items, detected_items[1:], strict=False
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

        for raw in range(left_raw + 1, right_raw):
            guessed = format_visible_page_label(left_label, left_label.number + (raw - left_raw))
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
