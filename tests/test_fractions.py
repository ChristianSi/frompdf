import unittest
from collections import Counter
from typing import cast

from pdftext.schema import Page

from frompdf.continuations import build_page_fragments, join_fragments
from frompdf.lines import iter_lines, merge_split_denominators
from frompdf.models import PageNumber
from frompdf.scripts import render_scripts


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


def positioned_span(
    text: str, x: float, top: float, size: float, height: float | None = None
) -> dict:
    """Build a span of glyphs 4 units wide, with a bbox, starting at x with the given top edge."""
    height = size * 0.9 if height is None else height
    chars = [
        {
            'char': char,
            'bbox': [x + index * 4, top, x + (index + 1) * 4, top + height],
            'font': {'size': size},
            'rotation': 0,
        }
        for index, char in enumerate(text)
    ]
    return {
        'text': text,
        'bbox': [x, top, x + len(text) * 4, top + height],
        'font': {'size': size},
        'chars': chars,
    }


def spans_record(*spans: dict) -> dict:
    """Build a pdftext line from positioned spans."""
    boxes = [span['bbox'] for span in spans]
    return {
        'bbox': [
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        ],
        'spans': list(spans),
    }


def rendered(*records: dict) -> str:
    """Return the block text, with scripts, assembled from line records of one page."""
    page = cast(Page, {'blocks': [{'lines': list(records)}]})
    merge_split_denominators([page])
    lines = iter_lines([page])
    fragments = build_page_fragments(lines, {1: PageNumber(1, None)}, Counter(), set(), set())
    value = join_fragments(fragments)
    return render_scripts(value.text, value.ranges)


def radical_fraction(gap: float = 0.0) -> list[dict]:
    """Build `= s/√(s²−f²). Then` as in lipics-64, with the denominator in three records."""
    return [
        spans_record(
            positioned_span('=', 0, 100, 10),
            positioned_span(' ', 4, 100, 10),
            positioned_span('√', 8, 100, 10, height=17),
            positioned_span(' ', 12, 100, 10),
            positioned_span('s', 18, 97, 7),
        ),
        spans_record(positioned_span('s', 12, 107, 7)),
        spans_record(
            positioned_span('2', 16 + gap, 106, 5), positioned_span('−f', 20 + gap, 107, 7)
        ),
        spans_record(positioned_span('2', 28 + gap, 106, 5)),
        spans_record(positioned_span('. Then', 33 + gap, 100, 10)),
    ]


def limits(shift: float = 0.0) -> list[dict]:
    """Build `PBA ≜ argmax` with two rows of limits centered below `argmax`, then its argument."""
    return [
        spans_record(positioned_span('PBA ≜ argmax', 0, 100, 10)),
        spans_record(
            positioned_span('r∈R', 28 + shift, 110, 7), positioned_span('s', 40 + shift, 109, 5)
        ),
        spans_record(
            positioned_span('x∈X', 28 + shift, 117, 7), positioned_span('n', 40 + shift, 116, 5)
        ),
        spans_record(positioned_span('P(x)', 50, 100, 10)),
    ]


class StackedMathTextTests(unittest.TestCase):
    def test_denominator_split_into_records_follows_its_radical(self) -> None:
        self.assertEqual(rendered(*radical_fraction()), '= s/√(s<sup>2</sup>−f<sup>2</sup>). Then')

    def test_denominator_pieces_apart_are_not_merged(self) -> None:
        self.assertIn('\n', rendered(*radical_fraction(gap=3.0)))

    def test_limits_below_the_last_word_become_its_subscript(self) -> None:
        self.assertEqual(
            rendered(*limits()), 'PBA ≜ argmax<sub>r∈R<sup>s</sup>, x∈X<sup>n</sup></sub> P(x)'
        )

    def test_records_off_center_below_the_last_word_are_no_limits(self) -> None:
        self.assertNotIn('<sub>', rendered(*limits(shift=4.0)))


class FractionTextTests(unittest.TestCase):
    def test_fraction_is_joined_with_a_slash_on_the_numerator_line(self) -> None:
        self.assertEqual(assembled(*fraction('1', '2')), 'even when < 1/2 of the samples')

    def test_compound_denominator_is_parenthesized(self) -> None:
        self.assertEqual(
            assembled(*fraction('s', '2s − f')), 'even when < s/(2s − f) of the samples'
        )


if __name__ == '__main__':
    unittest.main()
