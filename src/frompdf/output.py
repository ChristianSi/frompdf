import csv
from dataclasses import asdict
from pathlib import Path
from typing import TextIO

from frompdf.models import Block, BlockQuote, Heading, Line, PageNumber


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
    """Write raw and visible page numbers as CSV with a header row."""
    with output_path.open('w', encoding='utf-8', newline='') as output_file:
        writer = csv.DictWriter(output_file, fieldnames=['raw', 'visible'])
        writer.writeheader()
        for page_number in page_number_list:
            writer.writerow(
                {
                    'raw': page_number.raw,
                    'visible': page_number.visible if page_number.visible is not None else '?',
                }
            )


def format_page_marker(page_number: PageNumber) -> str:
    """Format a Markdown page marker from raw and visible page numbers."""
    visible_suffix = (
        f'|LABEL:{page_number.visible}'
        if page_number.visible is not None and page_number.visible != str(page_number.raw)
        else ''
    )
    return f'<<PAGE:{page_number.raw}{visible_suffix}>>'


def markdown_to_text(
    block_list: list[Block], output_file: TextIO, page_markers: bool = False
) -> None:
    """Write Markdown blocks as readable plain text."""
    previous_page: PageNumber | None = None

    for block_index, block_obj in enumerate(block_list):
        if block_index:
            previous_block = block_list[block_index - 1]
            if isinstance(previous_block, BlockQuote) and isinstance(block_obj, BlockQuote):
                output_file.write('\n>\n')
            else:
                output_file.write('\n\n')

        marker = ''
        if page_markers and (
            previous_page is None or block_obj.start_page.raw != previous_page.raw
        ):
            marker = format_page_marker(block_obj.start_page)

        if isinstance(block_obj, Heading):
            output_file.write(f'{"#" * block_obj.level} {marker}{block_obj.text}')
        elif isinstance(block_obj, BlockQuote):
            quote_lines = block_obj.text.split('\n')
            quote_lines[0] = f'{marker}{quote_lines[0]}'
            output_file.write('\n'.join(f'> {line}' if line else '>' for line in quote_lines))
        else:
            output_file.write(f'{marker}{block_obj.text}')
        previous_page = block_obj.end_page
    output_file.write('\n')


def dump_text(block_list: list[Block], output_path: Path, page_markers: bool = False) -> None:
    """Write Markdown blocks as readable plain text."""
    backup_existing_file(output_path)
    with output_path.open('w', encoding='utf-8') as output_file:
        markdown_to_text(block_list, output_file, page_markers=page_markers)
