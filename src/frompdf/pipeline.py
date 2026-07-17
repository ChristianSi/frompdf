from pathlib import Path

from pdftext.extraction import dictionary_output

from frompdf.blocks import lines_to_markdown_blocks
from frompdf.lines import iter_lines
from frompdf.models import Block
from frompdf.output import (
    build_csv_output_path,
    build_pagenos_output_path,
    dump_csv,
    dump_page_numbers,
)
from frompdf.page_edges import build_page_number_map, remove_headers_and_footers


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
