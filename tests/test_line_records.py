import unittest
from typing import cast

from pdftext.schema import Page

from frompdf.lines import iter_lines


def page_with_lines(texts: list[str]) -> Page:
    """Build a page with one single-span pdftext line per text."""
    lines = [
        {
            'bbox': [0.0, 10.0 * index, 100.0, 10.0 * index + 8.0],
            'spans': [{'text': text, 'font': {'size': 8.0}, 'chars': []}],
        }
        for index, text in enumerate(texts)
    ]
    return cast(Page, {'blocks': [{'lines': lines}]})


class LineWhitespaceTests(unittest.TestCase):
    def test_edge_whitespace_is_recorded_without_line_ends(self) -> None:
        lines = iter_lines([page_with_lines([' I found her \n', ', permitiendo\r\n', 'word\t'])])

        self.assertEqual(
            [(line.text, line.space_before, line.space_after) for line in lines],
            [('I found her', True, True), (', permitiendo', False, False), ('word', False, True)],
        )

    def test_whitespace_only_line_has_no_edge_spaces(self) -> None:
        line = iter_lines([page_with_lines([' \n'])])[0]

        self.assertEqual((line.text, line.space_before, line.space_after), ('', False, False))


if __name__ == '__main__':
    unittest.main()
