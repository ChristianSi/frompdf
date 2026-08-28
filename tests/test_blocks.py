import unittest
from typing import cast

from pdftext.schema import Line as PdfTextLine

from frompdf.blocks import (
    initial_heading_level,
    is_blockquote_block,
    should_boost_heading_font_size,
)
from frompdf.lines import average_font_weight, dominant_font_name
from frompdf.models import Line, PageNumber, Paragraph


def paragraph(text: str, font_size: float, avg_weight: float | None = None) -> Paragraph:
    page_number = PageNumber(raw=1, visible=None)
    return Paragraph(
        text=text,
        start_page=page_number,
        end_page=page_number,
        font_size=font_size,
        avg_weight=avg_weight,
    )


def positioned_line(text: str, x1: float) -> Line:
    return Line(
        text=text,
        page_no=1,
        block_no=1,
        line_no_on_page=1,
        font_size=8.5,
        x1=x1,
        y1=10.0,
        x2=200.0,
        y2=18.5,
        rel_x=None,
        rel_y=None,
        avg_weight=400.0,
        font_name='Body-Italic',
    )


class BlockQuoteDetectionTests(unittest.TestCase):
    def test_indented_attribution_after_blockquote_remains_quoted(self) -> None:
        attribution = positioned_line('Pierre-Joseph Proudhon (1840)1', x1=145.0)

        self.assertTrue(
            is_blockquote_block(
                [attribution],
                default_font_size=10.5,
                body_lefts_by_page={1: [42.5]},
                follows_blockquote=True,
            )
        )

    def test_single_indented_line_without_preceding_blockquote_is_not_quoted(self) -> None:
        ordinary_line = positioned_line('Founded in 1840', x1=60.0)

        self.assertFalse(
            is_blockquote_block(
                [ordinary_line],
                default_font_size=10.5,
                body_lefts_by_page={1: [42.5]},
            )
        )


class HeadingDetectionTests(unittest.TestCase):
    def test_extracts_dominant_font_name_by_visible_text_length(self) -> None:
        line = cast(
            PdfTextLine,
            {
                'spans': [
                    {'text': 'Main text', 'font': {'name': 'Body'}},
                    {'text': '1', 'font': {'name': 'Superscript'}},
                ]
            },
        )

        self.assertEqual(dominant_font_name(line), 'Body')

    def test_infers_bold_weight_from_embedded_font_name(self) -> None:
        line = cast(
            PdfTextLine,
            {
                'spans': [
                    {
                        'text': 'Abstract',
                        'font': {'name': 'AdvTTaf7f9f4f.B', 'weight': 0},
                    }
                ]
            },
        )

        self.assertEqual(average_font_weight(line), 700.0)

    def test_zero_font_weights_do_not_boost_body_text(self) -> None:
        block = paragraph('short ordinary body paragraph', font_size=9.2, avg_weight=0.0)

        self.assertFalse(should_boost_heading_font_size(block, document_median_weight=0.0))
        self.assertIsNone(
            initial_heading_level(block, default_font_size=9.2, document_median_weight=0.0)
        )

    def test_mixed_bold_lead_in_does_not_boost_whole_paragraph(self) -> None:
        block = paragraph(
            'Magnetic properties and phase diagram. Ordinary paragraph text follows.',
            font_size=9.2,
            avg_weight=267.6,
        )

        self.assertFalse(should_boost_heading_font_size(block, document_median_weight=0.0))

    def test_inferred_bold_block_can_be_boosted_with_zero_median(self) -> None:
        block = paragraph('Abstract', font_size=9.2, avg_weight=700.0)

        self.assertTrue(should_boost_heading_font_size(block, document_median_weight=0.0))

    def test_slightly_larger_multiline_metadata_is_not_a_heading(self) -> None:
        block = paragraph(
            'Fabian Keller\nHochschule Harz\nFriedrichstraße 57-59\n'
            '38855 Wernigerode\nfkeller@hs-harz.de',
            font_size=10.0,
            avg_weight=425.0,
        )

        self.assertIsNone(
            initial_heading_level(block, default_font_size=9.0, document_median_weight=370.0)
        )

    def test_clearly_larger_multiline_title_remains_a_heading(self) -> None:
        block = paragraph(
            'Slowdown of photoexcited spin dynamics\nin the non-collinear phases\nin GaV4S8',
            font_size=18.0,
            avg_weight=400.0,
        )

        self.assertIsNotNone(
            initial_heading_level(block, default_font_size=9.0, document_median_weight=400.0)
        )

    def test_three_line_cover_heading_remains_a_heading(self) -> None:
        block = paragraph(
            'Themenschwerpunkt:\nAnarchismus und\nPädagogik',
            font_size=10.0,
            avg_weight=425.0,
        )

        self.assertIsNotNone(
            initial_heading_level(block, default_font_size=9.0, document_median_weight=370.0)
        )


if __name__ == '__main__':
    unittest.main()
