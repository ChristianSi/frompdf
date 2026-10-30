import csv
from dataclasses import asdict
from pathlib import Path
from typing import TextIO

from frompdf.emphasis import render_inline, resolve_emphasis
from frompdf.escaping import escape_markdown, shift_index
from frompdf.models import (
    HARD_LINE_BREAK,
    Block,
    BlockQuote,
    Footnote,
    Heading,
    Line,
    ListItem,
    PageNumber,
    StrongParagraph,
    TextFragment,
)
from frompdf.scripts import AnnotatedText, join_annotated_texts


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
        f'|VISIBLE:{page_number.visible}'
        if page_number.visible is not None and page_number.visible != str(page_number.raw)
        else ''
    )
    return f'[[PAGE:{page_number.raw}{visible_suffix}]]'


def render_fragments(
    block_obj: Block,
    previous_page: PageNumber | None,
    page_markers: bool = False,
    opening: str = '',
) -> str:
    """Render escaped block text, adding page markers where its fragments change pages.

    The opening markup, if any, follows the first page marker, so markers stay
    outside inline markup enclosing the whole block. Emphasis within the block
    is closed before and reopened after later page markers.
    """
    fragments = block_obj.fragments or [
        TextFragment(block_obj.text, block_obj.start_page, ranges=block_obj.ranges)
    ]
    # Escape the whole block at once, as syntax depends on line starts and
    # neighboring characters across fragment boundaries.
    joined = join_annotated_texts(
        AnnotatedText(fragment.separator) + AnnotatedText(fragment.text, fragment.ranges)
        for fragment in fragments
    )
    markers: dict[int, str] = {}
    offset = 0
    for fragment in fragments:
        offset += len(fragment.separator)
        if page_markers and (previous_page is None or fragment.page.raw != previous_page.raw):
            markers[offset] = markers.get(offset, '') + format_page_marker(fragment.page)
        offset += len(fragment.text)
        previous_page = fragment.page
    inserts = dict(markers)
    if opening:
        first = len(fragments[0].separator)
        inserts[first] = inserts.get(first, '') + opening

    heading = isinstance(block_obj, Heading)
    resolved = resolve_emphasis(
        joined,
        markers,
        display=isinstance(block_obj, Heading | StrongParagraph),
        strong=isinstance(block_obj, StrongParagraph),
    )
    escaped, insertions = escape_markdown(
        resolved,
        heading=heading,
        block_line_start=not opening,
        # Opening markup separates the first page marker from the text.
        markers=frozenset(markers.keys() - ({len(fragments[0].separator)} if opening else set())),
    )
    text = render_inline(
        escaped,
        {shift_index(insertions, position): marker for position, marker in inserts.items()},
    )
    # A backslash at the end of a line is CommonMark's portable hard line break.
    return text.replace(HARD_LINE_BREAK, '\\')


def list_family(block_obj: Block) -> str | None:
    """Return the marker type of a list block: `-`, or the delimiter of numbered items."""
    if isinstance(block_obj, Footnote):
        return '.'
    if isinstance(block_obj, ListItem):
        return block_obj.marker[-1] if block_obj.number is not None else '-'
    return None


def continues_list(previous_block: Block, block_obj: Block) -> bool:
    """Return whether a list item continues the list of the preceding item."""
    if not isinstance(previous_block, ListItem) or not isinstance(block_obj, ListItem):
        return False
    if list_family(previous_block) != list_family(block_obj):
        return False
    previous_number = previous_block.number
    return previous_number is None or block_obj.number == previous_number + 1


def block_separator(previous_block: Block, block_obj: Block) -> str:
    """Return the text separating two consecutive blocks."""
    if isinstance(previous_block, BlockQuote) and isinstance(block_obj, BlockQuote):
        return '\n>\n'
    if isinstance(previous_block, Footnote) and isinstance(block_obj, Footnote):
        # Restarted groups may share a Notes section. Separate their
        # lists so Markdown renderers retain the new starting number.
        if int(block_obj.label) <= int(previous_block.label):
            return '\n\n<!-- -->\n\n'
        return '\n'
    if continues_list(previous_block, block_obj):
        return '\n'
    family = list_family(previous_block)
    if family is not None and family == list_family(block_obj):
        # A blank line alone would continue the list, as a loose one.
        return '\n\n<!-- -->\n\n'
    return '\n\n'


def markdown_to_text(
    block_list: list[Block], output_file: TextIO, page_markers: bool = False
) -> None:
    """Write Markdown blocks as readable plain text."""
    previous_page: PageNumber | None = None

    for block_index, block_obj in enumerate(block_list):
        if block_index:
            output_file.write(block_separator(block_list[block_index - 1], block_obj))

        if isinstance(block_obj, StrongParagraph):
            text = render_fragments(block_obj, previous_page, page_markers, opening='**') + '**'
        else:
            text = render_fragments(block_obj, previous_page, page_markers)
        if isinstance(block_obj, Footnote | ListItem):
            prefix = (
                f'{block_obj.label}. '
                if isinstance(block_obj, Footnote)
                else f'{block_obj.marker} '
            )
            text_lines = text.split('\n')
            output_file.write(
                prefix
                + '\n'.join(
                    text_lines[:1]
                    + [' ' * len(prefix) + line if line else line for line in text_lines[1:]]
                )
            )
        elif isinstance(block_obj, Heading):
            output_file.write(f'{"#" * block_obj.level} {text}')
        elif isinstance(block_obj, BlockQuote):
            output_file.write('\n'.join(f'> {line}' if line else '>' for line in text.split('\n')))
        else:
            output_file.write(text)
        previous_page = block_obj.end_page
    output_file.write('\n')


def dump_text(block_list: list[Block], output_path: Path, page_markers: bool = False) -> None:
    """Write Markdown blocks as readable plain text."""
    backup_existing_file(output_path)
    with output_path.open('w', encoding='utf-8') as output_file:
        markdown_to_text(block_list, output_file, page_markers=page_markers)
