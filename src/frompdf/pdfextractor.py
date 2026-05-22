#!/usr/bin/env python3
import argparse
import csv
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TextIO

from pdftext.extraction import dictionary_output


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


def round_or_none(value: float | int | None, digits: int = 1) -> float | None:
    """Round a numeric value, or return None."""
    if value is None:
        return None
    return round(float(value), digits)


def get_bbox(obj: dict) -> tuple[float | None, float | None, float | None, float | None]:
    """Extract a 4-value bbox tuple from an object, if present."""
    bbox = obj.get('bbox')
    if not isinstance(bbox, list | tuple) or len(bbox) != 4:
        return None, None, None, None

    try:
        x1, y1, x2, y2 = bbox
        return float(x1), float(y1), float(x2), float(y2)
    except (TypeError, ValueError):
        return None, None, None, None


def dominant_font_size(line_dict: dict) -> float | None:
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


def iter_lines(page_list: list[dict]) -> list[Line]:
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
    normalized = re.sub(roman_pattern, '$ROMAN', normalized, flags=re.IGNORECASE)

    # Normalize repeated punctuation around page numbers.
    normalized = re.sub(r'[–—−-]+', '-', normalized)
    normalized = re.sub(r'\s*([|•·/\\-])\s*', r'\1', normalized)

    return normalized


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


def build_text_output_path(input_path: Path) -> Path:
    """Return the default Markdown output path."""
    return input_path.with_suffix('.md')


def backup_existing_file(output_path: Path) -> None:
    """Move an existing output file aside before writing."""
    if output_path.exists():
        output_path.replace(output_path.with_name(f'{output_path.name}.bak'))


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


def extract_markdown(input_file_name: str | Path, dump_lines: bool = False) -> list[Block]:
    """Extract Markdown blocks from a PDF."""
    input_path = Path(input_file_name)
    page_list = dictionary_output(str(input_path), sort=True)
    line_list = iter_lines(page_list)

    if dump_lines:
        dump_csv(line_list, build_csv_output_path(input_path))

    return lines_to_markdown_blocks(line_list)


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

    block_list = extract_markdown(input_path, dump_lines=True)
    dump_text(block_list, text_output_path)

    print(csv_output_path)
    print(text_output_path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
