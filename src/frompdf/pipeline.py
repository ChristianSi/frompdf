from pathlib import Path

from pdftext.extraction import dictionary_output

from frompdf.blocks import lines_to_markdown_blocks
from frompdf.lines import iter_lines, normalize_detached_diacritics
from frompdf.models import Block
from frompdf.output import (
    build_csv_output_path,
    build_pagenos_output_path,
    dump_csv,
    dump_page_numbers,
)
from frompdf.page_edges import (
    build_page_number_map,
    complete_page_numbers,
    remove_headers_and_footers,
)
from frompdf.reading_order import order_lines_for_reading


def extract_markdown(
    input_file_name: str | Path, dump_lines: bool = False, dump_pagenos: bool = False
) -> list[Block]:
    """Extract Markdown blocks from a PDF."""
    input_path = Path(input_file_name)
    page_list = dictionary_output(str(input_path), sort=True, keep_chars=True)
    normalize_detached_diacritics(page_list)
    line_list = iter_lines(page_list)

    if dump_lines:
        dump_csv(line_list, build_csv_output_path(input_path))

    filtered_lines, detected_page_number_list = remove_headers_and_footers(line_list, page_list)
    filtered_lines = order_lines_for_reading(filtered_lines)
    page_number_list = complete_page_numbers(len(page_list), detected_page_number_list)

    if dump_pagenos:
        dump_page_numbers(page_number_list, build_pagenos_output_path(input_path))

    page_number_map = build_page_number_map(len(page_list), page_number_list)
    return lines_to_markdown_blocks(filtered_lines, page_number_map)
