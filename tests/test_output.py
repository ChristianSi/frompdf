import io
import unittest

from frompdf.models import BlockQuote, Heading, PageNumber, Paragraph
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
            '> <<PAGE:2|LABEL:51:2>>Quoted\n'
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


if __name__ == '__main__':
    unittest.main()
