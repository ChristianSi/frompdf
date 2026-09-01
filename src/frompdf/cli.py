import argparse
from pathlib import Path

from frompdf.output import (
    build_csv_output_path,
    build_pagenos_output_path,
    build_text_output_path,
    dump_text,
)
from frompdf.pipeline import extract_markdown


def main() -> int:
    """Run the command-line interface."""
    parser = argparse.ArgumentParser(description='Convert a PDF document to structured Markdown.')
    parser.add_argument(
        '--dump-lines',
        action='store_true',
        help='Write extracted line records to a CSV file',
    )
    parser.add_argument(
        '--dump-pagenos',
        action='store_true',
        help='Write raw and visible page numbers to a CSV file',
    )
    parser.add_argument(
        '--page-markers',
        action='store_true',
        help='Embed raw and visible page numbers in the Markdown output',
    )
    parser.add_argument('pdf_file', type=Path, help='Path to the input PDF file')
    args = parser.parse_args()

    input_path = args.pdf_file
    if not input_path.exists():
        raise SystemExit(f'File not found: {input_path}')
    if not input_path.is_file():
        raise SystemExit(f'Not a file: {input_path}')

    text_output_path = build_text_output_path(input_path)

    block_list = extract_markdown(
        input_path,
        dump_lines=args.dump_lines,
        dump_pagenos=args.dump_pagenos,
    )
    dump_text(block_list, text_output_path, page_markers=args.page_markers)

    if args.dump_lines:
        print(f'{build_csv_output_path(input_path)} written')
    if args.dump_pagenos:
        print(f'{build_pagenos_output_path(input_path)} written')
    print(f'{text_output_path} written')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
