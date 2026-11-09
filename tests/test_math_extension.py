import unittest
from typing import cast

from pdftext.schema import Page

from frompdf.glyph_repairs import decode_double_struck_letters, decode_math_extension_glyphs
from frompdf.lines import iter_lines
from frompdf.models import InlineRange

MATH_EXTENSION = 'LMMathExtension10-Regular'


def span(chars: list[tuple[str, float, float]], font_name: str, text: str | None = None) -> dict:
    """Build a span from characters with horizontal extents, and pdftext's text for them."""
    return {
        'text': ''.join(char for char, _, _ in chars if char >= ' ') if text is None else text,
        'font': {'name': font_name, 'size': 10.0},
        'chars': [
            {'char': char, 'bbox': [x1, 0.0, x2, 10.0], 'rotation': 0} for char, x1, x2 in chars
        ],
    }


def decoded_text(*spans: dict) -> str:
    """Return the line text after decoding math extension glyphs."""
    page = cast(Page, {'blocks': [{'lines': [{'bbox': [0, 0, 100, 10], 'spans': list(spans)}]}]})
    decode_math_extension_glyphs([page])
    return iter_lines([page])[0].text


class MathExtensionGlyphTests(unittest.TestCase):
    def test_control_character_codes_become_delimiters(self) -> None:
        self.assertEqual(
            decoded_text(
                span([('Ω', 0, 5)], 'LMRoman10-Regular'),
                span([('\x00', 5, 9)], MATH_EXTENSION),
                span([('n', 9, 14)], 'LMMathItalic10-Regular'),
                span([('\x01', 14, 18)], 'CMEX10'),
            ),
            'Ω(n)',
        )

    def test_letter_codes_become_delimiters_and_operators(self) -> None:
        self.assertEqual(
            decoded_text(span([('l', 0, 5), ('X', 5, 10), ('m', 10, 15)], MATH_EXTENSION)),
            '⌈∑⌉',
        )

    def test_wide_hat_combines_only_with_glyph_below_it(self) -> None:
        base = span([('P', 0, 8)], 'LMMathItalic10-Regular')
        self.assertEqual(decoded_text(base, span([('b', 2, 8)], MATH_EXTENSION)), 'P̂')
        base = span([('P', 0, 8)], 'LMMathItalic10-Regular')
        self.assertEqual(decoded_text(base, span([('b', 12, 18)], MATH_EXTENSION)), 'Pˆ')

    def test_characters_a_unicode_mapping_could_produce_are_kept(self) -> None:
        # Code 0x28 is a large brace, but a mapped big parenthesis also reads `(`.
        self.assertEqual(decoded_text(span([('(', 0, 5), (')', 5, 10)], MATH_EXTENSION)), '()')

    def test_extensible_pieces_and_other_fonts_are_kept(self) -> None:
        # Code 0x30 is the top piece of a tall parenthesis.
        self.assertEqual(decoded_text(span([('0', 0, 5)], MATH_EXTENSION)), '0')
        self.assertEqual(decoded_text(span([('l', 0, 5)], 'LMRoman10-Regular')), 'l')

    def test_span_whose_text_differs_from_its_characters_is_kept(self) -> None:
        self.assertEqual(decoded_text(span([('l', 0, 5)], MATH_EXTENSION, text='lm')), 'lm')

    def test_decoded_wide_hat_is_emphasized_with_its_italic_letter(self) -> None:
        page = cast(
            Page,
            {
                'blocks': [
                    {
                        'lines': [
                            {
                                'bbox': [0, 0, 100, 10],
                                'spans': [
                                    span([('P', 0, 6)], 'LMMathItalic10-Regular'),
                                    span([('b', 0, 6)], MATH_EXTENSION),
                                    span([('(', 6, 9)], 'LMRoman10-Regular'),
                                ],
                            }
                        ]
                    }
                ]
            },
        )
        decode_math_extension_glyphs([page])

        line = iter_lines([page])[0]

        self.assertEqual(line.text, 'P\u0302(')
        self.assertEqual(line.ranges, (InlineRange(0, 2, 'italic'),))


class DoubleStruckLetterTests(unittest.TestCase):
    def decoded_text(self, *spans: dict) -> str:
        page = cast(
            Page, {'blocks': [{'lines': [{'bbox': [0, 0, 100, 10], 'spans': list(spans)}]}]}
        )
        decode_double_struck_letters([page])
        return iter_lines([page])[0].text

    def test_capitals_of_blackboard_bold_fonts_become_double_struck(self) -> None:
        self.assertEqual(
            self.decoded_text(
                span([('R', 0, 5)], 'LMMathItalic10-Regular'),
                span([('⊆', 5, 10)], 'LMMathSymbols10-Regular'),
                span([('R', 10, 15)], 'QDTWCG+MSBM10'),
                span([('N', 15, 20), ('A', 20, 25)], 'MSBM7'),
            ),
            'R⊆ℝℕ𝔸',
        )

    def test_other_glyphs_and_fonts_are_kept(self) -> None:
        self.assertEqual(
            self.decoded_text(
                span([('k', 0, 5), ('7', 5, 10)], 'MSBM10'),
                span([('R', 10, 15)], 'MSAM10'),
                span([('R', 15, 20)], 'LMRoman10-Bold'),
            ),
            'k7RR',
        )


if __name__ == '__main__':
    unittest.main()
