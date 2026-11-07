import unittest
from dataclasses import replace
from typing import cast

from pdftext.schema import Line as PdfTextLine

from frompdf.blocks import (
    initial_heading_level,
    is_blockquote_block,
    lines_to_markdown_blocks,
    should_boost_heading_font_size,
)
from frompdf.lines import average_font_weight, dominant_font_name
from frompdf.models import BlockQuote, Line, PageNumber, Paragraph


def paragraph(text: str, font_size: float, avg_weight: float | None = None) -> Paragraph:
    page_number = PageNumber(raw=1, visible=None)
    return Paragraph(
        text=text,
        start_page=page_number,
        end_page=page_number,
        font_size=font_size,
        avg_weight=avg_weight,
    )


def positioned_line(text: str, x1: float, x2: float = 200.0, y1: float = 10.0) -> Line:
    return Line(
        text=text,
        page_no=1,
        block_no=1,
        line_no_on_page=1,
        font_size=8.5,
        x1=x1,
        y1=y1,
        x2=x2,
        y2=y1 + 8.5,
        rel_x=None,
        rel_y=None,
        avg_weight=400.0,
        font_name='Body-Italic',
    )


class MarkerLineBlockTests(unittest.TestCase):
    def blocks_for_marker(self, *pieces: Line) -> list[str]:
        body = [
            positioned_line('The first line of the closing paragraph', 20.0, 220.0, y1=10.0),
            positioned_line('and the second line of that paragraph', 20.0, 220.0, y1=22.0),
            positioned_line('with a short end.', 20.0, 100.0, y1=34.0),
        ]
        blocks = lines_to_markdown_blocks(
            [*body, *pieces], {1: PageNumber(raw=1, visible=None)}, notes_title='Notes'
        )
        self.assertFalse(any(isinstance(block, BlockQuote) for block in blocks))
        self.assertTrue(all(isinstance(block, Paragraph) for block in blocks))
        return [block.text for block in blocks]

    def test_marker_line_of_several_pieces_is_an_unquoted_paragraph(self) -> None:
        pieces = [
            positioned_line('*', 114.0, 118.0, y1=46.0),
            positioned_line('*', 118.0, 122.0, y1=48.0),
            positioned_line('*', 122.0, 126.0, y1=46.0),
        ]

        self.assertEqual(self.blocks_for_marker(*pieces)[-1], '***')

    def test_single_marker_line_is_an_unquoted_paragraph(self) -> None:
        self.assertEqual(
            self.blocks_for_marker(positioned_line('⸟', 117.0, 123.0, y1=44.0))[-1], '⸟'
        )

    def test_marker_line_after_block_quote_is_an_unquoted_paragraph(self) -> None:
        body = [
            positioned_line(f'Line {n} of the paragraph above the quote', 20.0, 220.0, y1=n * 12.0)
            for n in range(5)
        ]
        quote = [
            replace(
                positioned_line(f'Line {n} of the quote', 50.0, 190.0, y1=60.0 + n * 12.0),
                block_no=2,
            )
            for n in range(3)
        ]
        for name, pieces in {
            'single': [positioned_line('⸟', 117.0, 123.0, y1=96.0)],
            'staggered': [
                positioned_line('*', 114.0, 118.0, y1=98.0),
                positioned_line('*', 118.0, 122.0, y1=100.0),
                positioned_line('*', 122.0, 126.0, y1=98.0),
            ],
        }.items():
            with self.subTest(name):
                blocks = lines_to_markdown_blocks(
                    [*body, *quote, *(replace(piece, block_no=2) for piece in pieces)],
                    {1: PageNumber(raw=1, visible=None)},
                )
                self.assertEqual(
                    [type(block) for block in blocks], [Paragraph, BlockQuote, Paragraph]
                )
                self.assertEqual(blocks[-1].text, ''.join(piece.text for piece in pieces))


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

    def test_centered_caption_is_not_quoted(self) -> None:
        caption = [
            positioned_line('Example of a response to a query listing', 60.0, 180.0),
            positioned_line('codes', 108.0, 131.0, y1=20.0),
        ]

        self.assertFalse(
            is_blockquote_block(caption, default_font_size=10.5, body_lefts_by_page={1: [42.5]})
        )

    def test_right_aligned_and_indented_quotes_remain_quoted(self) -> None:
        cases = {
            'right-aligned epigraph': [
                positioned_line('All that is solid melts into air', 120.0),
                positioned_line('Karl Marx and Friedrich Engels', 90.0, y1=20.0),
            ],
            'first-line indent with ragged ending': [
                positioned_line('Quoted text starts with an indent', 70.0),
                positioned_line('and ends early.', 60.0, 140.0, y1=20.0),
            ],
        }

        for name, quote in cases.items():
            with self.subTest(name):
                self.assertTrue(
                    is_blockquote_block(
                        quote, default_font_size=10.5, body_lefts_by_page={1: [42.5]}
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
