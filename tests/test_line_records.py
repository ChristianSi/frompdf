import unittest
from typing import cast

from pdftext.schema import Char as PdfTextChar
from pdftext.schema import Line as PdfTextLine
from pdftext.schema import Page
from pdftext.schema import Span as PdfTextSpan

from frompdf.lines import (
    effective_span_font_size,
    glyph_font_size,
    iter_lines,
    line_words,
    second_word_x1,
)
from frompdf.models import Word


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


class LineWordTests(unittest.TestCase):
    def test_words_span_their_characters_across_spans_after_leading_whitespace(self) -> None:
        def chars(text: str, x1: float) -> list[dict[str, object]]:
            return [
                {'char': char, 'bbox': [x1 + 5.0 * index, 0.0, x1 + 5.0 * index + 4.0, 8.0]}
                for index, char in enumerate(text)
            ]

        line_dict = {
            'bbox': [0.0, 0.0, 200.0, 8.0],
            'spans': [
                {'text': ' CEA 0.', 'chars': chars(' CEA 0.', 95.0)},
                {'text': '9 x', 'chars': chars('9 x', 200.0)},
            ],
        }

        self.assertEqual(
            line_words(cast(PdfTextLine, line_dict), 1),
            (Word(0, 3, 100.0, 114.0), Word(4, 7, 120.0, 204.0), Word(8, 9, 210.0, 214.0)),
        )

    def test_words_without_positioned_characters_are_omitted(self) -> None:
        line_dict = {'bbox': [0.0, 0.0, 20.0, 8.0], 'spans': [{'text': 'ab', 'chars': []}]}

        self.assertEqual(line_words(cast(PdfTextLine, line_dict), 0), ())


if __name__ == '__main__':
    unittest.main()


def placeholder_span(bbox: list[float], rotation: float) -> PdfTextSpan:
    """Build a span whose font reports the placeholder size 1.0."""
    return cast(
        PdfTextSpan,
        {'text': '(mdeg.)', 'bbox': bbox, 'rotation': rotation, 'font': {'size': 1.0}},
    )


class PlaceholderFontSizeTests(unittest.TestCase):
    def test_vertical_span_measures_its_bbox_width(self) -> None:
        # An axis label read bottom to top, as in nature's figures.
        span = placeholder_span([251.2, 544.0, 259.2, 572.6], 4.7124)

        self.assertAlmostEqual(effective_span_font_size(span) or 0.0, 8.0, places=1)

    def test_span_turned_the_other_way_measures_its_bbox_width(self) -> None:
        span = placeholder_span([251.2, 544.0, 259.2, 572.6], 1.5708)

        self.assertAlmostEqual(effective_span_font_size(span) or 0.0, 8.0, places=1)

    def test_horizontal_span_measures_its_bbox_height(self) -> None:
        for rotation in (0.0, 3.1416):
            span = placeholder_span([251.2, 544.0, 279.8, 552.0], rotation)

            self.assertAlmostEqual(effective_span_font_size(span) or 0.0, 8.0, places=1)

    def test_obliquely_turned_span_keeps_measuring_its_bbox_height(self) -> None:
        span = placeholder_span([0.0, 0.0, 30.0, 20.0], 0.6)

        self.assertAlmostEqual(effective_span_font_size(span) or 0.0, 20.0, places=1)

    def test_reported_size_is_kept_for_vertical_span(self) -> None:
        span = placeholder_span([251.2, 544.0, 259.2, 572.6], 4.7124)
        span['font'] = {'size': 7.5}

        self.assertEqual(effective_span_font_size(span), 7.5)

    def test_vertical_glyph_measures_its_bbox_width(self) -> None:
        char = cast(
            PdfTextChar,
            {
                'char': '(',
                'bbox': [251.2, 570.6, 259.2, 572.6],
                'rotation': 4.7124,
                'font': {'size': 1.0},
            },
        )

        self.assertAlmostEqual(glyph_font_size(char) or 0.0, 8.0, places=1)


def span_with_glyphs(glyphs: list[tuple[str, float, float]]) -> PdfTextSpan:
    """Build a placeholder-size span from glyphs given as text, bottom, and height."""
    chars = [
        {
            'char': text,
            'bbox': [5.0 * index, bottom - height, 5.0 * index + 4.0, bottom],
            'font': {'size': 1.0},
        }
        for index, (text, bottom, height) in enumerate(glyphs)
    ]
    boxes = [char['bbox'] for char in chars]
    bbox = [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]
    return cast(
        PdfTextSpan,
        {
            'text': ''.join(text for text, _, _ in glyphs),
            'bbox': bbox,
            'font': {'size': 1.0},
            'chars': chars,
        },
    )


class PlaceholderGlyphSizeTests(unittest.TestCase):
    def test_lowered_subscripts_do_not_stretch_the_span_size(self) -> None:
        # GaV₄S₈ in nature: subscripts end 0.7 below the baseline.
        span = span_with_glyphs(
            [('G', 722.2, 9.1), ('a', 722.2, 9.1), ('V', 722.2, 9.1), ('4', 722.9, 6.07)]
            + [('S', 722.2, 9.1), ('8', 722.9, 6.07)]
        )

        self.assertAlmostEqual(effective_span_font_size(span) or 0.0, 9.1, places=2)

    def test_large_glyphs_keep_their_size(self) -> None:
        # The number of graf's "CHAPTER 10" is set much larger than the word.
        span = span_with_glyphs(
            [(char, 94.2, 12.6) for char in 'CHAPTER'] + [('1', 102.6, 34.35), ('0', 102.6, 34.35)]
        )

        self.assertAlmostEqual(effective_span_font_size(span) or 0.0, 34.35, places=2)

    def test_whitespace_glyphs_are_ignored(self) -> None:
        span = span_with_glyphs([('a', 20.0, 9.1), (' ', 30.0, 20.0), ('b', 20.0, 9.1)])

        self.assertAlmostEqual(effective_span_font_size(span) or 0.0, 9.1, places=2)
