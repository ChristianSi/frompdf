import io
import unittest

from frompdf.models import (
    HARD_LINE_BREAK,
    Block,
    BlockQuote,
    Footnote,
    Heading,
    InlineRange,
    ListItem,
    PageNumber,
    Paragraph,
    StrongParagraph,
    Table,
    TableCell,
    TextFragment,
)
from frompdf.output import markdown_to_text


def page_number(raw: int, visible: str | None = None) -> PageNumber:
    return PageNumber(raw=raw, visible=visible)


class MarkdownOutputTests(unittest.TestCase):
    def test_page_markers_use_existing_page_numbers_and_markdown_prefixes(self) -> None:
        page_one = page_number(1)
        page_two = page_number(2, '51:2')
        page_three = page_number(3, '3')
        blocks = [
            Heading('Title', page_one, page_one, level=2),
            BlockQuote('Quoted\ntext', page_two, page_two),
            Paragraph('More text', page_two, page_two),
            Paragraph('Last page', page_three, page_three),
        ]
        output = io.StringIO()

        markdown_to_text(blocks, output, page_markers=True)

        self.assertEqual(
            output.getvalue(),
            '## [[PAGE:1]]Title\n\n'
            '> [[PAGE:2|VISIBLE:51:2]]Quoted\n'
            '> text\n\n'
            'More text\n\n'
            '[[PAGE:3]]Last page\n',
        )

    def test_page_markers_are_disabled_by_default(self) -> None:
        page = page_number(1, '7')
        blocks = [Paragraph('Text', page, page)]
        output = io.StringIO()

        markdown_to_text(blocks, output)

        self.assertEqual(output.getvalue(), 'Text\n')

    def test_strong_paragraph_keeps_line_breaks_and_page_marker_outside(self) -> None:
        page = page_number(1, '173')
        blocks = [StrongParagraph(f'CHAPTER 10{HARD_LINE_BREAK}\n# Part *one*', page, page)]
        output = io.StringIO()

        markdown_to_text(blocks, output, page_markers=True)

        self.assertEqual(
            output.getvalue(), '[[PAGE:1|VISIBLE:173]]**CHAPTER 10\\\n\\# Part \\*one\\***\n'
        )

    def test_escapes_text_consistently_across_block_types(self) -> None:
        page = page_number(1)
        blocks = [
            Heading('Roy Shadmon #', page, page, level=2),
            Paragraph('# The Author(s) 2021', page, page),
            BlockQuote('> quoted\n- item', page, page),
            Footnote('1. Not a nested list', page, page, label='3'),
        ]
        output = io.StringIO()

        markdown_to_text(blocks, output)

        self.assertEqual(
            output.getvalue(),
            '## Roy Shadmon \\#\n\n'
            '\\# The Author(s) 2021\n\n'
            '> \\> quoted\n'
            '> \\- item\n\n'
            '3. 1\\. Not a nested list\n',
        )

    def test_page_markers_precede_escapes_at_fragment_starts(self) -> None:
        page_one = page_number(1)
        page_two = page_number(2)
        block = Paragraph(
            'ends here\n# continues',
            page_one,
            page_two,
            fragments=[
                TextFragment('ends here', page_one),
                TextFragment('# continues', page_two, '\n'),
            ],
        )
        output = io.StringIO()

        markdown_to_text([block], output, page_markers=True)

        self.assertEqual(output.getvalue(), '[[PAGE:1]]ends here\n[[PAGE:2]]\\# continues\n')

    def test_page_markers_followed_by_parentheses_do_not_form_links(self) -> None:
        page_one = page_number(1)
        page_two = page_number(2, '8')
        block = Paragraph(
            'shown (here)\n(1990) showed',
            page_one,
            page_two,
            fragments=[
                TextFragment('shown (here)', page_one),
                TextFragment('(1990) showed', page_two, '\n'),
            ],
        )
        output = io.StringIO()

        markdown_to_text([block], output, page_markers=True)

        self.assertEqual(
            output.getvalue(), '[[PAGE:1]]shown (here)\n[[PAGE:2|VISIBLE:8]]\\(1990) showed\n'
        )

    def test_opening_markup_separates_page_markers_from_parentheses(self) -> None:
        page = page_number(1)
        block = StrongParagraph('(Author)', page, page)
        output = io.StringIO()

        markdown_to_text([block], output, page_markers=True)

        self.assertEqual(output.getvalue(), '[[PAGE:1]]**(Author)**\n')

    def test_list_items_are_dense_with_indented_continuations(self) -> None:
        page_one = page_number(1)
        page_two = page_number(2)
        blocks = [
            Paragraph('Items:', page_one, page_one),
            ListItem('First item\nwraps', page_one, page_one, marker='9.'),
            ListItem(
                'Second item',
                page_two,
                page_two,
                marker='10.',
                fragments=[TextFragment('Second item', page_two)],
            ),
            Paragraph('After', page_two, page_two),
        ]
        output = io.StringIO()

        markdown_to_text(blocks, output, page_markers=True)

        self.assertEqual(
            output.getvalue(),
            '[[PAGE:1]]Items:\n\n9. First item\n   wraps\n10. [[PAGE:2]]Second item\n\nAfter\n',
        )

    def test_separates_lists_that_would_otherwise_merge(self) -> None:
        page = page_number(1)

        def render(*blocks: ListItem | Footnote) -> str:
            output = io.StringIO()
            markdown_to_text(list(blocks), output)
            return output.getvalue()

        self.assertEqual(
            render(ListItem('a', page, page, marker='1.'), ListItem('b', page, page, marker='1.')),
            '1. a\n\n<!-- -->\n\n1. b\n',
        )
        self.assertEqual(
            render(ListItem('a', page, page, marker='1.'), Footnote('n', page, page, label='5')),
            '1. a\n\n<!-- -->\n\n5. n\n',
        )
        self.assertEqual(
            render(ListItem('a', page, page), ListItem('b', page, page, marker='3.')),
            '- a\n\n3. b\n',
        )

    def test_escapes_list_markers_within_list_items(self) -> None:
        page = page_number(1)
        output = io.StringIO()

        markdown_to_text([ListItem('- nested\n1. more', page, page)], output)

        self.assertEqual(output.getvalue(), '- \\- nested\n  1\\. more\n')

    def test_escapes_around_scripts_without_escaping_their_contents_twice(self) -> None:
        page = page_number(1)
        block = Paragraph('a*b2* c', page, page, ranges=(InlineRange(3, 5, 'sup'),))
        output = io.StringIO()

        markdown_to_text([block], output)

        self.assertEqual(output.getvalue(), 'a\\*b<sup>2&#42;</sup> c\n')


def render_blocks(blocks: list[Block], page_markers: bool = False) -> str:
    output = io.StringIO()
    markdown_to_text(blocks, output, page_markers=page_markers)
    return output.getvalue()


class PipeTableTests(unittest.TestCase):
    def test_header_rows_combine_labels_of_spanning_cells_with_those_below(self) -> None:
        page = page_number(1)
        cells = [
            TableCell(0, 0, row_span=2, text='Benchmark'),
            TableCell(0, 1, column_span=2, text='TSOTSA'),
            TableCell(1, 1, text='F1', ranges=(InlineRange(0, 2, 'bold'),)),
            TableCell(1, 2, text='Pr'),
            TableCell(2, 0, row_span=2, text='Round1', ranges=(InlineRange(0, 6, 'bold'),)),
            TableCell(2, 1, text='0.9'),
            TableCell(2, 2, text='0.8'),
            TableCell(3, 1, text='0.7'),
            TableCell(3, 2, text='0.6'),
        ]
        table = Table('', page, page, row_count=4, column_count=3, header_rows=2, cells=cells)

        self.assertEqual(
            render_blocks([table]),
            '| Benchmark  | TSOTSA F1 | TSOTSA Pr |\n'
            '| ---------- | --------- | --------- |\n'
            '| **Round1** | 0.9       | 0.8       |\n'
            '|            | 0.7       | 0.6       |\n',
        )

    def test_cells_spanning_undivided_columns_fill_their_first_column(self) -> None:
        page = page_number(1)
        cells = [
            TableCell(0, 0, column_span=2, text='Benchmark'),
            TableCell(0, 2, text='Hit@1'),
            TableCell(1, 0, column_span=2, text='All'),
            TableCell(1, 2, text='0.75'),
        ]
        table = Table('', page, page, row_count=2, column_count=3, header_rows=1, cells=cells)

        self.assertEqual(
            render_blocks([table]),
            '| Benchmark |     | Hit@1 |\n'
            '| --------- | --- | ----- |\n'
            '| All       |     | 0.75  |\n',
        )

    def test_cell_text_escapes_pipes_and_breaks_parts_with_html(self) -> None:
        page = page_number(1)
        cells = [
            TableCell(0, 0, text='*n*', ranges=(InlineRange(0, 3, 'italic'),)),
            TableCell(0, 1, text='|x|'),
            TableCell(1, 0, text='- a'),
            TableCell(1, 1, text=f'- b{HARD_LINE_BREAK}- c'),
        ]
        table = Table('', page, page, row_count=2, column_count=2, header_rows=1, cells=cells)

        self.assertEqual(
            render_blocks([table]),
            '| *\\*n\\** | \\|x\\|      |\n| ------- | ---------- |\n| - a     | - b<br>- c |\n',
        )

    def test_page_marker_starts_the_first_header_cell_with_its_pipe_escaped(self) -> None:
        first, second = page_number(1), page_number(2, '12')
        cells = [
            TableCell(0, 0, text='(a)'),
            TableCell(0, 1, text='b'),
            TableCell(1, 0, text='c'),
            TableCell(1, 1, text='d'),
        ]
        table = Table('', second, second, row_count=2, column_count=2, header_rows=1, cells=cells)

        self.assertEqual(
            render_blocks([Paragraph('Text', first, first), table], page_markers=True),
            '[[PAGE:1]]Text\n\n'
            '| [[PAGE:2\\|VISIBLE:12]]\\(a) | b   |\n'
            '| -------------------------- | --- |\n'
            '| c                          | d   |\n',
        )

    def test_wide_tables_are_not_padded(self) -> None:
        page = page_number(1)
        long_text = 'word ' * 30
        cells = [
            TableCell(0, 0, text='Year'),
            TableCell(0, 1, text='Definition'),
            TableCell(1, 0, text='2004'),
            TableCell(1, 1, text=long_text.strip()),
        ]
        table = Table('', page, page, row_count=2, column_count=2, header_rows=1, cells=cells)

        self.assertEqual(
            render_blocks([table]),
            f'| Year | Definition |\n| --- | --- |\n| 2004 | {long_text.strip()} |\n',
        )


if __name__ == '__main__':
    unittest.main()
