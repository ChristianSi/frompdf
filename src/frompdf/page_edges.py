import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from pdftext.schema import Page

from frompdf.models import Line, PageNumber

VISIBLE_PAGE_LABEL_PATTERN = r'(?:[A-Za-z]+|\d+)[:-]\d+|\d+'
COMPOUND_VISIBLE_PAGE_LABEL_PATTERN = r'(?:[A-Za-z]+|\d+)[:-]\d+'


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
    if len(text) == 1 and text not in {'i', 'v', 'x'}:
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
        return match.group(1)

    return None


def visible_page_label_sort_number(label: str) -> int:
    """Return the numeric part that should track raw page order."""
    return int(label.rsplit(':', 1)[-1].rsplit('-', 1)[-1])


def is_compound_visible_page_label(label: str) -> bool:
    """Return whether a visible page label has a section/article prefix."""
    return bool(re.fullmatch(COMPOUND_VISIBLE_PAGE_LABEL_PATTERN, label))


def edge_visible_page_label(text: str, edge: str) -> str | None:
    """Return a visible page label at the requested edge of a line."""
    if edge == 'start':
        compound_match = re.match(rf'\s*({COMPOUND_VISIBLE_PAGE_LABEL_PATTERN})\b', text)
        if compound_match:
            return compound_match.group(1)

        plain_match = re.fullmatch(r'\s*(\d+)\s*', text)
        if plain_match:
            return plain_match.group(1)
        return None

    compound_match = re.search(rf'\b({COMPOUND_VISIBLE_PAGE_LABEL_PATTERN})\s*$', text)
    if compound_match:
        return compound_match.group(1)

    plain_match = re.search(r'(?:^|\s)(\d+)\s*$', text)
    if plain_match:
        return plain_match.group(1)
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
        numbers_by_position: dict[int, list[tuple[int, str]]] = defaultdict(list)
        for candidate in repeated_candidates:
            for position, match in enumerate(re.finditer(r'\d+', candidate.line.text)):
                numbers_by_position[position].append((candidate.line.page_no, match.group(0)))

        for raw_and_visible in numbers_by_position.values():
            offsets = Counter(int(visible) - raw for raw, visible in raw_and_visible)
            if not offsets:
                continue

            offset, offset_count = offsets.most_common(1)[0]
            if offset_count < max(3, len(raw_and_visible) * 2 // 3):
                continue

            for raw, visible in raw_and_visible:
                if int(visible) - raw == offset:
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
            page_offsets = {
                visible_page_label_sort_number(visible) - raw for visible in visible_labels
            }
            offsets.update(page_offsets)
        if not offsets:
            continue

        offset, offset_count = offsets.most_common(1)[0]
        if offset_count < max(3, len(labels_by_page) * 2 // 3):
            continue

        for raw, visible_labels in labels_by_page.items():
            matching_labels = sorted(
                visible
                for visible in visible_labels
                if visible_page_label_sort_number(visible) - raw == offset
            )
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


def build_page_number_map(
    page_count: int, visible_page_number_list: list[PageNumber]
) -> dict[int, PageNumber]:
    """Return PageNumber metadata for every raw page."""
    page_number_map = {raw: PageNumber(raw=raw, visible=None) for raw in range(1, page_count + 1)}

    for page_number in visible_page_number_list:
        page_number_map[page_number.raw] = page_number

    return page_number_map
