import io
import unittest

from frompdf.models import (
    HARD_LINE_BREAK,
    BlockQuote,
    Footnote,
    Heading,
    InlineRange,
    PageNumber,
    Paragraph,
    StrongParagraph,
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
            '## <<PAGE:1>>Title\n\n'
            '> <<PAGE:2|VISIBLE:51:2>>Quoted\n'
            '> text\n\n'
            'More text\n\n'
            '<<PAGE:3>>Last page\n',
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
            output.getvalue(), '<<PAGE:1|VISIBLE:173>>**CHAPTER 10\\\n\\# Part \\*one\\***\n'
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

        self.assertEqual(output.getvalue(), '<<PAGE:1>>ends here\n<<PAGE:2>>\\# continues\n')

    def test_escapes_around_scripts_without_escaping_their_contents_twice(self) -> None:
        page = page_number(1)
        block = Paragraph('a*b2* c', page, page, ranges=(InlineRange(3, 5, 'sup'),))
        output = io.StringIO()

        markdown_to_text([block], output)

        self.assertEqual(output.getvalue(), 'a\\*b<sup>2&#42;</sup> c\n')


if __name__ == '__main__':
    unittest.main()
