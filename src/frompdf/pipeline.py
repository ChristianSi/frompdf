from pathlib import Path

from pdftext.extraction import dictionary_output

from frompdf.blocks import lines_to_markdown_blocks
from frompdf.detached_scripts import (
    attach_stacked_scripts,
    attach_stray_scripts,
    merge_split_denominators,
)
from frompdf.figures import find_figures
from frompdf.glyph_repairs import (
    decode_double_struck_letters,
    decode_math_extension_glyphs,
    normalize_detached_diacritics,
    remove_icon_glyphs,
    restore_private_use_bullets,
)
from frompdf.images import write_images
from frompdf.lines import drop_dominant_emphasis, iter_lines
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
from frompdf.rules import extract_drawings, extract_rules
from frompdf.tables import find_tables


def extract_markdown(
    input_file_name: str | Path,
    dump_lines: bool = False,
    dump_pagenos: bool = False,
    notes_title: str = 'Notes',
    image_dir: Path | None = None,
) -> list[Block]:
    """Extract Markdown blocks from a PDF.

    The pictures of the document are written as images into image_dir and
    referenced from the blocks. Without it, they are left out, like the text
    shown by them.
    """
    input_path = Path(input_file_name)
    page_list = dictionary_output(str(input_path), sort=True, keep_chars=True)
    normalize_detached_diacritics(page_list)
    remove_icon_glyphs(page_list)
    decode_math_extension_glyphs(page_list)
    decode_double_struck_letters(page_list)
    restore_private_use_bullets(page_list)
    attach_stray_scripts(page_list)
    attach_stacked_scripts(page_list)
    merge_split_denominators(page_list)
    line_list = iter_lines(page_list)
    drop_dominant_emphasis(line_list)

    if dump_lines:
        dump_csv(line_list, build_csv_output_path(input_path))

    # pdftext can report whitespace-only lines, which would otherwise end up as
    # empty blocks or trailing empty lines within blocks.
    line_list = [line_obj for line_obj in line_list if line_obj.text]
    filtered_lines, detected_page_number_list = remove_headers_and_footers(line_list, page_list)
    filtered_lines = order_lines_for_reading(filtered_lines)
    page_number_list = complete_page_numbers(len(page_list), detected_page_number_list)

    if dump_pagenos:
        dump_page_numbers(page_number_list, build_pagenos_output_path(input_path))

    page_number_map = build_page_number_map(len(page_list), page_number_list)
    tables = find_tables(filtered_lines, extract_rules(input_path, page_list))
    page_sizes = {
        page_no: (page['bbox'][2] - page['bbox'][0], page['bbox'][3] - page['bbox'][1])
        for page_no, page in enumerate(page_list, start=1)
    }
    figures = find_figures(
        filtered_lines, extract_drawings(input_path, page_list), tables, page_sizes
    )
    if image_dir is not None:
        write_images(input_path, figures, image_dir)
    return lines_to_markdown_blocks(filtered_lines, page_number_map, notes_title, tables, figures)
