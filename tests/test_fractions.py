import unittest
from collections import Counter
from typing import cast

from pdftext.schema import Page

from frompdf.continuations import build_page_fragments, join_fragments
from frompdf.lines import iter_lines
from frompdf.models import PageNumber


def record(text: str, x: float, top: float, size: float = 10.0, width: float = 5.0) -> dict:
    """Build a pdftext line of equally wide glyphs, starting at x with the given top edge."""
    chars = [
        {
            'char': char,
            'bbox': [x + index * width, top, x + (index + 1) * width, top + size * 0.9],
            'font': {'size': size},
            'rotation': 0,
        }
        for index, char in enumerate(text)
    ]
    return {
        'bbox': [x, top, x + len(text) * width, top + size * 0.9],
        'spans': [{'text': text, 'font': {'size': size}, 'chars': chars}],
    }


def flagged(*records: dict) -> list[tuple[str, bool]]:
    """Return the text and fraction flag of each line record of one page."""
    page = cast(Page, {'blocks': [{'lines': list(records)}]})
    return [(line.text, line.fraction_denominator) for line in iter_lines([page])]


def assembled(*records: dict) -> str:
    """Return the block text assembled from line records of one page."""
    page = cast(Page, {'blocks': [{'lines': list(records)}]})
    lines = iter_lines([page])
    fragments = build_page_fragments(lines, {1: PageNumber(1, None)}, Counter(), set(), set())
    return join_fragments(fragments).text


def fraction(numerator: str, denominator: str, following: str = 'of the samples') -> list[dict]:
    """Build text with an inline fraction of small, centered parts, then more text."""
    numerator_x = 60.0
    denominator_x = numerator_x + (len(numerator) - len(denominator)) * 2.5
    end = numerator_x + len(numerator) * 5
    return [
        record('even when <', 0, 100),
        record(numerator, numerator_x, 98, size=7.0),
        record(denominator, denominator_x, 105, size=7.0),
        record(following, end + 5, 100),
    ]


class FractionDetectionTests(unittest.TestCase):
    def test_centered_small_parts_form_a_fraction(self) -> None:
        self.assertEqual(
            [is_denominator for _, is_denominator in flagged(*fraction('1', '2'))],
            [False, False, True, False],
        )

    def test_numerator_may_end_a_record_of_larger_text(self) -> None:
        records = [
            record('n log ', 0, 100),
            record('n', 32.5, 105, size=7.0),
            record(')', 41, 100),
        ]
        # Append a small, raised numerator `ID` to the first record.
        numerator = record('ID', 30.0, 98, size=7.0)
        records[0]['spans'].extend(numerator['spans'])
        records[0]['bbox'] = [0.0, 98.0, 40.0, 109.0]

        self.assertEqual([is_denominator for _, is_denominator in flagged(*records)][1], True)

    def test_left_aligned_stacked_scripts_are_no_fraction(self) -> None:
        base = record(', R', 0, 100)
        superscript = record('i', 15, 98, size=7.0, width=3.0)
        base['spans'].extend(superscript['spans'])
        base['bbox'][2] = 18.0
        subscript = record('∗', 15, 105, size=7.0, width=4.0)

        self.assertFalse(flagged(base, subscript, record(').', 19, 100))[1][1])

    def test_record_below_without_continuation_on_the_line_is_no_fraction(self) -> None:
        records = fraction('1', '2')
        records[3] = record('next line of text', 0, 112)

        self.assertFalse(flagged(*records)[2][1])

    def test_full_size_record_below_is_no_fraction(self) -> None:
        records = fraction('1', '2')
        records[2] = record('2', 60, 105)

        self.assertFalse(flagged(*records)[2][1])


class FractionTextTests(unittest.TestCase):
    def test_fraction_is_joined_with_a_slash_on_the_numerator_line(self) -> None:
        self.assertEqual(assembled(*fraction('1', '2')), 'even when < 1/2 of the samples')

    def test_compound_denominator_is_parenthesized(self) -> None:
        self.assertEqual(
            assembled(*fraction('s', '2s − f')), 'even when < s/(2s − f) of the samples'
        )


if __name__ == '__main__':
    unittest.main()
