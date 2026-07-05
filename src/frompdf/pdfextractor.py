#!/usr/bin/env python3
import argparse
import csv
import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median
from typing import TextIO

from pdftext.extraction import dictionary_output
from pdftext.schema import Line as PdfTextLine
from pdftext.schema import Page
from pdftext.schema import Span as PdfTextSpan

# Treat clearly heavier font weights as slightly larger for heading detection.
HEADING_WEIGHT_FONT_SIZE_MULTIPLIER = 1.08

# A block must be at least 40% heavier than the document median to get the boost.
HEADING_WEIGHT_BOOST_THRESHOLD = 1.4


@dataclass
class Line:
    """A flattened line record extracted from pdftext output."""

    text: str
    page_no: int
    block_no: int
    line_no_on_page: int
    font_size: float | None
    x1: float | None
    y1: float | None
    x2: float | None
    y2: float | None
    rel_x: float | None
    rel_y: float | None
    avg_weight: float | None


@dataclass
class PageNumber:
    """A raw PDF page number with optional visible page label."""

    raw: int
    visible: str | None


@dataclass
class Block:
    """A Markdown block extracted from a PDF."""

    text: str
    start_page: PageNumber
    end_page: PageNumber
    font_size: float | None = None
    avg_weight: float | None = None


@dataclass
class Paragraph(Block):
    """A Markdown paragraph."""


@dataclass
class BlockQuote(Block):
    """A Markdown block quote."""


@dataclass
class Heading(Block):
    """A Markdown heading."""

    level: int = 1


@dataclass
class HeaderFooterCandidate:
    """A line that may be part of a repeated header or footer."""

    index: int
    line: Line
    zone: str
    normalized: str


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


def dump_csv(line_list: list[Line], output_path: Path) -> None:
    """Write line records as CSV with a header row."""
    field_names = list(Line.__dataclass_fields__)
    with output_path.open('w', encoding='utf-8', newline='') as output_file:
        writer = csv.DictWriter(output_file, fieldnames=field_names)
        writer.writeheader()
        for line_obj in line_list:
            writer.writerow(asdict(line_obj))


def build_csv_output_path(input_path: Path) -> Path:
    """Return the default CSV output path for the line dump."""
    return input_path.with_name(f'{input_path.stem}-lines.csv')


def build_pagenos_output_path(input_path: Path) -> Path:
    """Return the default CSV output path for visible page numbers."""
    return input_path.with_name(f'{input_path.stem}-pagenos.csv')


def build_text_output_path(input_path: Path) -> Path:
    """Return the default Markdown output path."""
    return input_path.with_suffix('.md')


def backup_existing_file(output_path: Path) -> None:
    """Move an existing output file aside before writing."""
    if output_path.exists():
        output_path.replace(output_path.with_name(f'{output_path.name}.bak'))


def dump_page_numbers(page_number_list: list[PageNumber], output_path: Path) -> None:
    """Write visible page numbers as CSV with a header row."""
    with output_path.open('w', encoding='utf-8', newline='') as output_file:
        writer = csv.DictWriter(output_file, fieldnames=['raw', 'visible'])
        writer.writeheader()
        for page_number in page_number_list:
            if page_number.visible is not None:
                writer.writerow(asdict(page_number))


def candidate_zone(line_obj: Line, page_height: float) -> str | None:
    """Return the header/footer zone for a line, if it is near a page edge."""
    if line_obj.y1 is None:
        return None

    header_end = max(80.0, page_height * 0.10)
    footer_start = page_height - max(120.0, page_height * 0.15)

    if line_obj.y1 <= header_end:
        return 'header'
    if line_obj.y1 >= footer_start:
        return 'footer'
    return None


def iter_header_footer_candidates(
    line_list: list[Line], page_list: Sequence[Page]
) -> list[HeaderFooterCandidate]:
    """Return non-empty lines in likely header and footer zones."""
    page_heights = {
        page_no: float(page_dict['height']) for page_no, page_dict in enumerate(page_list, start=1)
    }
    candidate_list: list[HeaderFooterCandidate] = []

    for index, line_obj in enumerate(line_list):
        if not line_obj.text:
            continue

        page_height = page_heights.get(line_obj.page_no)
        if page_height is None:
            continue

        zone = candidate_zone(line_obj, page_height)
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


VISIBLE_PAGE_LABEL_PATTERN = r'(?:[A-Za-z]+|\d+)[:-]\d+|\d+'
COMPOUND_VISIBLE_PAGE_LABEL_PATTERN = r'(?:[A-Za-z]+|\d+)[:-]\d+'


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

    plain_match = re.search(r'\b(\d+)\s*$', text)
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
    numbers_by_position: dict[tuple[str, str], list[tuple[int, str]]] = defaultdict(list)
    page_numbers: dict[int, str] = {}

    for candidate in candidate_list:
        for edge in ['start', 'end']:
            visible = edge_visible_page_label(candidate.line.text, edge)
            if visible is not None:
                numbers_by_position[(candidate.zone, edge)].append(
                    (candidate.line.page_no, visible)
                )

    for raw_and_visible in numbers_by_position.values():
        offsets = Counter(
            visible_page_label_sort_number(visible) - raw for raw, visible in raw_and_visible
        )
        if not offsets:
            continue

        offset, offset_count = offsets.most_common(1)[0]
        if offset_count < max(3, len(raw_and_visible) * 2 // 3):
            continue

        for raw, visible in raw_and_visible:
            if visible_page_label_sort_number(visible) - raw == offset:
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
    candidate_list = iter_header_footer_candidates(line_list, page_list)
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


def dominant_document_font_size(line_list: list[Line]) -> float | None:
    """Return the font size most widely used in the document."""
    size_weights: dict[float, int] = defaultdict(int)

    for line_obj in line_list:
        if line_obj.font_size is None or not line_obj.text:
            continue
        size_weights[line_obj.font_size] += max(len(line_obj.text), 1)

    if not size_weights:
        return None

    return max(size_weights.items(), key=lambda item: (item[1], item[0]))[0]


def document_median_avg_weight(line_list: list[Line]) -> float | None:
    """Return the median line average font weight, ignoring lines without usable weight data."""
    weight_list = [line_obj.avg_weight for line_obj in line_list if line_obj.avg_weight is not None]
    if not weight_list:
        return None

    return float(median(weight_list))


def block_font_size(line_list: list[Line]) -> float | None:
    """Return the dominant font size in a Markdown block."""
    size_weights: dict[float, int] = defaultdict(int)

    for line_obj in line_list:
        if line_obj.font_size is None:
            continue
        size_weights[line_obj.font_size] += max(len(line_obj.text), 1)

    if not size_weights:
        return None

    return max(size_weights.items(), key=lambda item: (item[1], item[0]))[0]


def block_avg_weight(line_list: list[Line]) -> float | None:
    """Return the length-weighted average font weight in a Markdown block."""
    weighted_sum = 0.0
    total_weight = 0

    for line_obj in line_list:
        line_weight = len(line_obj.text.strip())
        if not line_weight or line_obj.avg_weight is None:
            continue

        weighted_sum += line_obj.avg_weight * line_weight
        total_weight += line_weight

    if not total_weight:
        return None

    return round(weighted_sum / total_weight, 1)


def build_body_lefts_by_page(
    line_list: list[Line], default_font_size: float | None
) -> dict[int, list[float]]:
    """Return likely body-text left edges for each page."""
    weighted_lefts_by_page: dict[int, dict[float, int]] = defaultdict(lambda: defaultdict(int))

    for line_obj in line_list:
        if (
            line_obj.x1 is None
            or line_obj.font_size is None
            or default_font_size is None
            or not line_obj.text
            or abs(line_obj.font_size - default_font_size) > 0.2
        ):
            continue

        rounded_x1 = round(line_obj.x1, 1)
        weighted_lefts_by_page[line_obj.page_no][rounded_x1] += max(len(line_obj.text), 1)

    body_lefts_by_page: dict[int, list[float]] = {}
    column_gap = max((default_font_size or 1.0) * 4.0, 40.0)

    for page_no, weighted_lefts in weighted_lefts_by_page.items():
        if not weighted_lefts:
            continue

        clusters: list[list[float]] = []
        for x1 in sorted(weighted_lefts):
            if not clusters or x1 - clusters[-1][-1] > column_gap:
                clusters.append([x1])
            else:
                clusters[-1].append(x1)

        body_lefts_by_page[page_no] = [min(cluster) for cluster in clusters]

    return body_lefts_by_page


def is_footnote_like_block(line_list: list[Line]) -> bool:
    """Return whether a small-font block looks like a bottom footnote."""
    if not line_list:
        return False

    first_line = line_list[0]
    return bool(re.match(r'\s*\d+\s+', first_line.text))


def indent_threshold(font_size: float | None) -> float:
    """Return the required indentation in PDF coordinate units."""
    if font_size is None:
        return 6.0

    return max(font_size * 0.8, 6.0)


def is_indented_line(line_obj: Line, body_lefts: list[float], threshold: float) -> bool:
    """Return whether a line is indented from its nearest page or column left edge."""
    if line_obj.x1 is None:
        return False

    if any(abs(line_obj.x1 - body_left) < threshold for body_left in body_lefts):
        return False

    preceding_body_lefts = [
        body_left for body_left in body_lefts if body_left <= line_obj.x1 - threshold
    ]
    if not preceding_body_lefts:
        return False

    return line_obj.x1 - max(preceding_body_lefts) >= threshold


def is_indented_blockquote_block(
    line_list: list[Line],
    body_lefts_by_page: dict[int, list[float]],
    default_font_size: float | None,
    allow_single_line: bool = False,
) -> bool:
    """Return whether a block is consistently inset from its page or column margin."""
    if len(line_list) < 2 and not allow_single_line:
        return False

    font_size = block_font_size(line_list) or default_font_size
    threshold = indent_threshold(font_size)

    for line_obj in line_list:
        body_lefts = body_lefts_by_page.get(line_obj.page_no, [])
        if not body_lefts or not is_indented_line(line_obj, body_lefts, threshold):
            return False

    return True


def is_blockquote_block(
    line_list: list[Line],
    default_font_size: float | None,
    body_lefts_by_page: dict[int, list[float]],
    follows_blockquote: bool = False,
) -> bool:
    """Return whether a group of lines should be rendered as a Markdown block quote."""
    if not line_list or is_footnote_like_block(line_list):
        return False

    font_size = block_font_size(line_list)
    if default_font_size is not None and font_size is not None and font_size > default_font_size:
        return False

    return is_indented_blockquote_block(
        line_list,
        body_lefts_by_page,
        default_font_size,
        allow_single_line=follows_blockquote,
    )


def markdown_block_from_lines(
    line_list: list[Line],
    page_number_map: dict[int, PageNumber],
    default_font_size: float | None,
    body_lefts_by_page: dict[int, list[float]],
    follows_blockquote: bool = False,
) -> Block:
    """Build a Markdown block from grouped line records."""
    block_class: type[Block] = (
        BlockQuote
        if is_blockquote_block(line_list, default_font_size, body_lefts_by_page, follows_blockquote)
        else Paragraph
    )
    font_size = block_font_size(line_list)
    avg_weight = block_avg_weight(line_list)
    start_page = page_number_map[line_list[0].page_no]
    end_page = page_number_map[line_list[-1].page_no]
    return block_class(
        text='\n'.join(line_obj.text for line_obj in line_list),
        start_page=start_page,
        end_page=end_page,
        font_size=font_size,
        avg_weight=avg_weight,
    )


HEADING_LEVEL_THRESHOLDS = [
    # Derived from 105% of the default font size, repeatedly multiplied by 10%,
    # rounded to the nearest full percentage, and capped at 200%.
    (2.00, 1),
    (1.86, 2),
    (1.69, 3),
    (1.54, 4),
    (1.40, 5),
    (1.27, 6),
    (1.16, 7),
    (1.05, 8),
]


def should_boost_heading_font_size(block_obj: Block, document_median_weight: float | None) -> bool:
    """Return whether a block is heavy enough, relative to the document, for a heading boost."""
    return (
        block_obj.avg_weight is not None
        and document_median_weight is not None
        and block_obj.avg_weight >= document_median_weight * HEADING_WEIGHT_BOOST_THRESHOLD
    )


def initial_heading_level(
    block_obj: Block, default_font_size: float | None, document_median_weight: float | None
) -> int | None:
    """Return the initial heading level for a block, if adjusted font-size heuristics match."""
    if (
        not isinstance(block_obj, Paragraph)
        or default_font_size is None
        or block_obj.font_size is None
        or len(block_obj.text) > 250
    ):
        return None

    adjusted_font_size = block_obj.font_size
    if should_boost_heading_font_size(block_obj, document_median_weight):
        adjusted_font_size *= HEADING_WEIGHT_FONT_SIZE_MULTIPLIER

    font_ratio = adjusted_font_size / default_font_size
    for threshold, level in HEADING_LEVEL_THRESHOLDS:
        if font_ratio >= threshold:
            return level

    return None


def compact_unused_heading_levels(block_list: list[Block]) -> None:
    """Remove gaps in heading levels while preserving their relative order."""
    used_levels = sorted(
        {block_obj.level for block_obj in block_list if isinstance(block_obj, Heading)}
    )
    level_map = {old_level: new_level for new_level, old_level in enumerate(used_levels, start=1)}

    for block_obj in block_list:
        if isinstance(block_obj, Heading):
            block_obj.level = level_map[block_obj.level]


def merge_heading_level_pair(block_list: list[Block], kept_level: int) -> None:
    """Merge kept_level + 1 into kept_level and shift deeper levels up."""
    removed_level = kept_level + 1

    for block_obj in block_list:
        if not isinstance(block_obj, Heading):
            continue
        if block_obj.level == removed_level:
            block_obj.level = kept_level
        elif block_obj.level > removed_level:
            block_obj.level -= 1


def merge_extra_heading_levels(block_list: list[Block]) -> None:
    """Merge adjacent heading levels until Markdown's six-level limit is satisfied."""
    while True:
        heading_counts = Counter(
            block_obj.level for block_obj in block_list if isinstance(block_obj, Heading)
        )
        if len(heading_counts) <= 6:
            return

        pairs = [
            (heading_counts[level] + heading_counts[level + 1], -level, level)
            for level in sorted(heading_counts)
            if level >= 2 and level + 1 in heading_counts
        ]
        if not pairs:
            return

        _, _, kept_level = min(pairs)
        merge_heading_level_pair(block_list, kept_level)


def detect_headings(
    block_list: list[Block], default_font_size: float | None, document_median_weight: float | None
) -> list[Block]:
    """Convert paragraph blocks with heading-like adjusted font sizes into Heading blocks."""
    converted_blocks: list[Block] = []

    for block_obj in block_list:
        heading_level = initial_heading_level(block_obj, default_font_size, document_median_weight)
        if heading_level is None:
            converted_blocks.append(block_obj)
            continue

        converted_blocks.append(
            Heading(
                text=re.sub(r'\s+', ' ', block_obj.text).strip(),
                start_page=block_obj.start_page,
                end_page=block_obj.end_page,
                font_size=block_obj.font_size,
                avg_weight=block_obj.avg_weight,
                level=heading_level,
            )
        )

    compact_unused_heading_levels(converted_blocks)
    merge_extra_heading_levels(converted_blocks)
    return converted_blocks


def lines_to_markdown_blocks(
    line_list: list[Line], page_number_map: dict[int, PageNumber]
) -> list[Block]:
    """Convert line records into Markdown blocks."""
    block_list: list[Block] = []
    current_lines: list[Line] = []
    current_page_no: int | None = None
    current_block_no: int | None = None
    default_font_size = dominant_document_font_size(line_list)
    document_median_weight = document_median_avg_weight(line_list)
    body_lefts_by_page = build_body_lefts_by_page(line_list, default_font_size)

    for line_obj in line_list:
        if (
            current_page_no is not None
            and current_block_no is not None
            and (line_obj.page_no != current_page_no or line_obj.block_no != current_block_no)
        ):
            block_list.append(
                markdown_block_from_lines(
                    current_lines,
                    page_number_map,
                    default_font_size,
                    body_lefts_by_page,
                    follows_blockquote=bool(block_list) and isinstance(block_list[-1], BlockQuote),
                )
            )
            current_lines = []

        current_lines.append(line_obj)
        current_page_no = line_obj.page_no
        current_block_no = line_obj.block_no

    if current_lines:
        block_list.append(
            markdown_block_from_lines(
                current_lines,
                page_number_map,
                default_font_size,
                body_lefts_by_page,
                follows_blockquote=bool(block_list) and isinstance(block_list[-1], BlockQuote),
            )
        )

    return detect_headings(block_list, default_font_size, document_median_weight)


def extract_markdown(
    input_file_name: str | Path, dump_lines: bool = False, dump_pagenos: bool = False
) -> list[Block]:
    """Extract Markdown blocks from a PDF."""
    input_path = Path(input_file_name)
    page_list = dictionary_output(str(input_path), sort=True)
    line_list = iter_lines(page_list)

    if dump_lines:
        dump_csv(line_list, build_csv_output_path(input_path))

    filtered_lines, page_number_list = remove_headers_and_footers(line_list, page_list)

    if dump_pagenos and any(page_number.visible is not None for page_number in page_number_list):
        dump_page_numbers(page_number_list, build_pagenos_output_path(input_path))

    page_number_map = build_page_number_map(len(page_list), page_number_list)
    return lines_to_markdown_blocks(filtered_lines, page_number_map)


def markdown_to_text(block_list: list[Block], output_file: TextIO) -> None:
    """Write Markdown blocks as readable plain text."""
    for block_index, block_obj in enumerate(block_list):
        if block_index:
            previous_block = block_list[block_index - 1]
            if isinstance(previous_block, BlockQuote) and isinstance(block_obj, BlockQuote):
                output_file.write('\n>\n')
            else:
                output_file.write('\n\n')

        if isinstance(block_obj, Heading):
            output_file.write(f'{"#" * block_obj.level} {block_obj.text}')
        elif isinstance(block_obj, BlockQuote):
            output_file.write(
                '\n'.join(f'> {line}' if line else '>' for line in block_obj.text.split('\n'))
            )
        else:
            output_file.write(block_obj.text)
    output_file.write('\n')


def dump_text(block_list: list[Block], output_path: Path) -> None:
    """Write Markdown blocks as readable plain text."""
    backup_existing_file(output_path)
    with output_path.open('w', encoding='utf-8') as output_file:
        markdown_to_text(block_list, output_file)


def main() -> int:
    """Run the command-line interface."""
    parser = argparse.ArgumentParser(description='Extract line records from a PDF using pdftext.')
    parser.add_argument('pdf_file', type=Path, help='Path to the input PDF file')
    args = parser.parse_args()

    input_path = args.pdf_file
    if not input_path.exists():
        raise SystemExit(f'File not found: {input_path}')
    if not input_path.is_file():
        raise SystemExit(f'Not a file: {input_path}')

    csv_output_path = build_csv_output_path(input_path)
    text_output_path = build_text_output_path(input_path)

    block_list = extract_markdown(input_path, dump_lines=True, dump_pagenos=True)
    dump_text(block_list, text_output_path)

    print(csv_output_path)
    pagenos_output_path = build_pagenos_output_path(input_path)
    if pagenos_output_path.exists():
        print(pagenos_output_path)
    print(text_output_path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
