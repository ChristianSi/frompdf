import unittest
from typing import cast

from pdftext.schema import Line as PdfTextLine
from pdftext.schema import Page

from frompdf.lines import iter_lines, second_word_x1


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


class SecondWordTests(unittest.TestCase):
    def test_returns_start_of_text_after_first_word_and_whitespace(self) -> None:
        chars = [
            {'char': char, 'bbox': [x1, 0.0, x1 + 4.0, 8.0]}
            for char, x1 in (('•', 36.0), (' ', 36.3), ('L', 54.0), ('i', 60.3))
        ]
        line_dict = {'bbox': [36.0, 0.0, 64.0, 8.0], 'spans': [{'text': '• Li', 'chars': chars}]}

        self.assertEqual(second_word_x1(cast(PdfTextLine, line_dict)), 54.0)

    def test_returns_none_for_a_single_word(self) -> None:
        chars = [{'char': ' ', 'bbox': [0.0, 0.0, 4.0, 8.0]}, {'char': 'a', 'bbox': [4.0, 0, 8, 8]}]
        line_dict = {'bbox': [0.0, 0.0, 8.0, 8.0], 'spans': [{'text': ' a', 'chars': chars}]}

        self.assertIsNone(second_word_x1(cast(PdfTextLine, line_dict)))


if __name__ == '__main__':
    unittest.main()
