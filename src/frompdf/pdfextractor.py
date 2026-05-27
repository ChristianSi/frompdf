#!/usr/bin/env python3
import argparse
import csv
import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TextIO

from pdftext.extraction import dictionary_output
from pdftext.schema import Line as PdfTextLine
from pdftext.schema import Page


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


@dataclass
class Block:
    """A Markdown block extracted from a PDF."""

    text: str
    start_page: int
    end_page: int


@dataclass
class Paragraph(Block):
    """A Markdown paragraph."""


@dataclass
class PageNumber:
    """A visible page number found in a header or footer."""

    raw: int
    visible: str


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


def get_bbox(obj: PdfTextLine) -> tuple[float | None, float | None, float | None, float | None]:
    """Extract a 4-value bbox tuple from an object, if present."""
    bbox = obj.get('bbox')
    if not isinstance(bbox, list | tuple) or len(bbox) != 4:
        return None, None, None, None

    try:
        x1, y1, x2, y2 = bbox
        return float(x1), float(y1), float(x2), float(y2)
    except (TypeError, ValueError):
        return None, None, None, None


def dominant_font_size(line_dict: PdfTextLine) -> float | None:
    """Return the dominant font size for a line, weighted by text length."""
    size_weights: dict[float, int] = defaultdict(int)

    for span_dict in line_dict.get('spans', []):
        font_dict = span_dict.get('font', {})
        size_value = font_dict.get('size')
        text_value = span_dict.get('text', '')

        if size_value is None:
            continue

        try:
            size_float = round(float(size_value), 1)
        except (TypeError, ValueError):
            continue

        weight = max(len(text_value), 1)
        size_weights[size_float] += weight

    if not size_weights:
        return None

    return max(size_weights.items(), key=lambda item: (item[1], item[0]))[0]


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
    match = re.match(r'\s*(?:page|página)\s+([0-9ivxlcdm]+)\b', text, flags=re.IGNORECASE)
    if match:
        return match.group(1)

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
        for edge, pattern in [('start', r'^\s*(\d+)\b'), ('end', r'\b(\d+)\s*$')]:
            match = re.search(pattern, candidate.line.text)
            if match:
                numbers_by_position[(candidate.zone, edge)].append(
                    (candidate.line.page_no, match.group(1))
                )

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


def has_edge_page_number(text: str, visible: str) -> bool:
    """Return whether a line starts or ends with a known visible page number."""
    return bool(re.search(rf'^\s*{re.escape(visible)}\b', text)) or bool(
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


def lines_to_markdown_blocks(line_list: list[Line]) -> list[Block]:
    """Convert line records into Markdown blocks."""
    block_list: list[Block] = []
    current_lines: list[str] = []
    current_page_no: int | None = None
    current_block_no: int | None = None

    for line_obj in line_list:
        if (
            current_page_no is not None
            and current_block_no is not None
            and (line_obj.page_no != current_page_no or line_obj.block_no != current_block_no)
        ):
            block_list.append(
                Paragraph(
                    text='\n'.join(current_lines),
                    start_page=current_page_no,
                    end_page=current_page_no,
                )
            )
            current_lines = []

        current_lines.append(line_obj.text)
        current_page_no = line_obj.page_no
        current_block_no = line_obj.block_no

    if current_lines and current_page_no is not None:
        block_list.append(
            Paragraph(
                text='\n'.join(current_lines),
                start_page=current_page_no,
                end_page=current_page_no,
            )
        )

    return block_list


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

    if dump_pagenos and page_number_list:
        dump_page_numbers(page_number_list, build_pagenos_output_path(input_path))

    return lines_to_markdown_blocks(filtered_lines)


def markdown_to_text(block_list: list[Block], output_file: TextIO) -> None:
    """Write Markdown blocks as readable plain text."""
    for block_index, block_obj in enumerate(block_list):
        if block_index:
            output_file.write('\n\n')
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
