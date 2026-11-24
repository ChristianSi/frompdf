import unittest
from typing import Any, cast

from pdftext.schema import Span as PdfTextSpan

from frompdf.surrogate_pairs import combine_surrogates, restore_span_surrogate_pairs

REPLACED = '�'

# The UTF-16 code units of 𝑃 (U+1D443), 𝛼 (U+1D6FC), and 𝑷 (U+1D477).
ITALIC_P = (0xD835, 0xDC43)
ITALIC_ALPHA = (0xD835, 0xDEFC)
BOLD_ITALIC_P = (0xD835, 0xDC77)


def char(text: str, index: int, x: float) -> dict[str, Any]:
    return {'char': text, 'char_idx': index, 'bbox': [x, 10.0, x + 6.0, 20.0], 'rotation': 0.0}


def span(font_name: str, chars: list[dict[str, Any]]) -> PdfTextSpan:
    return cast(
        PdfTextSpan,
        {
            'text': ''.join(item['char'] for item in chars),
            'font': {'name': font_name, 'size': 10.0},
            'chars': chars,
        },
    )


def pair(index: int, x: float) -> list[dict[str, Any]]:
    """Return the two replaced halves of a surrogate pair, sharing the box of their glyph."""
    return [char(REPLACED, index, x), char(REPLACED, index + 1, x)]


def lookup(units: dict[int, int]):
    return lambda index: units.get(index, 0)


class CombineSurrogatesTests(unittest.TestCase):
    def test_pair_is_combined(self) -> None:
        self.assertEqual(combine_surrogates(*ITALIC_P), '\U0001d443')

    def test_units_out_of_order_are_not_a_pair(self) -> None:
        self.assertIsNone(combine_surrogates(ITALIC_P[1], ITALIC_P[0]))
        self.assertIsNone(combine_surrogates(0xFFFD, 0xFFFD))


class RestoreSpanSurrogatePairsTests(unittest.TestCase):
    def test_math_italic_letters_of_math_italic_fonts_become_plain_letters(self) -> None:
        span_dict = span('CMMI10', [*pair(5, 0.0), char(' ', 7, 6.0), *pair(8, 12.0)])
        units = {5: ITALIC_P[0], 6: ITALIC_P[1], 8: ITALIC_ALPHA[0], 9: ITALIC_ALPHA[1]}

        restore_span_surrogate_pairs(span_dict, lookup(units))

        self.assertEqual(span_dict['text'], 'P α')
        self.assertEqual([item['char'] for item in span_dict['chars']], ['P', ' ', 'α'])
        self.assertEqual([item['char_idx'] for item in span_dict['chars']], [5, 7, 8])

    def test_math_italic_letters_of_other_fonts_are_kept(self) -> None:
        # Without a math italic font, no italic emphasis would stand in for them.
        span_dict = span('LatinModernMath-Regular', pair(0, 0.0))

        restore_span_surrogate_pairs(span_dict, lookup({0: ITALIC_P[0], 1: ITALIC_P[1]}))

        self.assertEqual(span_dict['text'], '\U0001d443')

    def test_bold_italic_letters_are_kept(self) -> None:
        span_dict = span('CMMIB10', pair(0, 0.0))

        restore_span_surrogate_pairs(span_dict, lookup({0: BOLD_ITALIC_P[0], 1: BOLD_ITALIC_P[1]}))

        self.assertEqual(span_dict['text'], '\U0001d477')

    def test_replacements_with_separate_boxes_are_kept(self) -> None:
        span_dict = span('CMMI10', [char(REPLACED, 0, 0.0), char(REPLACED, 1, 6.0)])

        restore_span_surrogate_pairs(span_dict, lookup({0: ITALIC_P[0], 1: ITALIC_P[1]}))

        self.assertEqual(span_dict['text'], REPLACED * 2)
        self.assertEqual(len(span_dict['chars']), 2)

    def test_replacements_that_are_no_surrogate_pair_are_kept(self) -> None:
        # Lone surrogates of a broken Unicode mapping stay replaced.
        span_dict = span('CMMI10', pair(0, 0.0))

        restore_span_surrogate_pairs(span_dict, lookup({0: ITALIC_P[0], 1: ITALIC_P[0]}))

        self.assertEqual(span_dict['text'], REPLACED * 2)

    def test_replacements_at_distant_indices_are_kept(self) -> None:
        chars = [char(REPLACED, 0, 0.0), char(REPLACED, 2, 0.0)]
        span_dict = span('CMMI10', chars)

        restore_span_surrogate_pairs(span_dict, lookup({0: ITALIC_P[0], 2: ITALIC_P[1]}))

        self.assertEqual(span_dict['text'], REPLACED * 2)


if __name__ == '__main__':
    unittest.main()
