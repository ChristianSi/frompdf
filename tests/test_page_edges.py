import csv
import tempfile
import unittest
from pathlib import Path

from frompdf.models import Line, PageNumber
from frompdf.output import dump_page_numbers
from frompdf.page_edges import (
    HeaderFooterCandidate,
    complete_page_numbers,
    edge_visible_page_label,
    explicit_visible_page_number,
    infer_edge_page_numbers,
    matches_repeated_footer_text,
    normalize_header_footer_text,
    parse_visible_page_label,
    repeated_footer_text_bases,
    repeated_header_footer_keys,
)


def candidate(page_no: int, text: str, zone: str = 'footer') -> HeaderFooterCandidate:
    line = Line(
        text=text,
        page_no=page_no,
        block_no=1,
        line_no_on_page=1,
        font_size=8.0,
        x1=10.0,
        y1=580.0,
        x2=500.0,
        y2=590.0,
        rel_x=None,
        rel_y=None,
        avg_weight=400.0,
    )
    return HeaderFooterCandidate(
        index=page_no,
        line=line,
        zone=zone,
        normalized=normalize_header_footer_text(text),
    )


class CompletePageNumbersTests(unittest.TestCase):
    def complete(self, page_count: int, *anchors: tuple[int, str]) -> list[str | None]:
        page_numbers = [PageNumber(raw=raw, visible=visible) for raw, visible in anchors]
        return [
            page_number.visible for page_number in complete_page_numbers(page_count, page_numbers)
        ]

    def test_counts_backward_without_going_below_one(self) -> None:
        self.assertEqual(self.complete(4, (4, '2')), [None, None, '1', '2'])

    def test_counts_forward_to_end_of_document(self) -> None:
        self.assertEqual(
            self.complete(10, (9, '11')), ['3', '4', '5', '6', '7', '8', '9', '10', '11', '12']
        )

    def test_fills_gap_when_both_anchors_agree(self) -> None:
        self.assertEqual(
            self.complete(12, (9, '11'), (12, '14'))[8:],
            ['11', '12', '13', '14'],
        )

    def test_leaves_gap_when_anchors_disagree(self) -> None:
        self.assertEqual(self.complete(3, (1, '11'), (3, '14')), ['11', None, '14'])
        self.assertEqual(
            self.complete(4, (1, '11'), (4, '12')),
            ['11', None, None, '12'],
        )

    def test_fills_compound_gap_with_matching_prefix(self) -> None:
        self.assertEqual(
            self.complete(3, (1, 'A:5'), (3, 'A:7')),
            ['A:5', 'A:6', 'A:7'],
        )
        self.assertEqual(
            self.complete(3, (1, '12-5'), (3, '12-7')),
            ['12-5', '12-6', '12-7'],
        )

    def test_does_not_fill_compound_gap_with_different_prefixes(self) -> None:
        self.assertEqual(
            self.complete(3, (1, 'A:5'), (3, 'B:7')),
            ['A:5', None, 'B:7'],
        )

    def test_does_not_extend_compound_label_from_single_anchor(self) -> None:
        self.assertEqual(self.complete(3, (2, 'A:5')), [None, 'A:5', None])

    def test_fills_roman_gap_while_ignoring_case(self) -> None:
        self.assertEqual(self.complete(3, (1, 'v'), (3, 'VII')), ['v', 'vi', 'VII'])
        self.assertEqual(
            self.complete(3, (1, 'A:v'), (3, 'A:VII')),
            ['A:v', 'A:vi', 'A:VII'],
        )

    def test_extends_plain_roman_sequence_at_edges(self) -> None:
        self.assertEqual(self.complete(4, (2, 'IV')), ['III', 'IV', 'V', 'VI'])
        self.assertEqual(self.complete(4, (4, 'ii')), [None, None, 'i', 'ii'])

    def test_does_not_mix_roman_and_arabic_labels(self) -> None:
        self.assertEqual(self.complete(3, (1, 'v'), (3, '7')), ['v', None, '7'])

    def test_extends_adjacent_unambiguous_numbering_systems(self) -> None:
        self.assertEqual(
            self.complete(8, (2, 'XIV'), (5, '1'), (8, '4')),
            ['XIII', 'XIV', 'XV', 'XVI', '1', '2', '3', '4'],
        )


class RepeatedFooterTests(unittest.TestCase):
    def test_detects_repetition_within_a_local_page_range(self) -> None:
        candidates = [candidate(page, 'Preface') for page in [2, 3, 4]]
        self.assertIn(('footer', 'preface'), repeated_header_footer_keys(candidates, 50))

    def test_detects_recto_verso_repetition_over_relevant_pages(self) -> None:
        candidates = [candidate(page, 'Introduction') for page in [16, 22, 28, 30, 34, 40, 48]]
        self.assertIn(('footer', 'introduction'), repeated_header_footer_keys(candidates, 50))

    def test_rejects_sparse_repetition(self) -> None:
        candidates = [candidate(page, 'Introduction') for page in [2, 24, 48]]
        self.assertNotIn(('footer', 'introduction'), repeated_header_footer_keys(candidates, 50))

    def test_matches_short_ocr_suffix_variants_of_repeated_footer(self) -> None:
        repeated_keys = {('footer', 'why columbus sailed south to the indies $NUM')}
        bases = repeated_footer_text_bases(repeated_keys)

        self.assertTrue(
            matches_repeated_footer_text(
                candidate(23, 'Why Columbus Sailed South to the Indies II'), bases
            )
        )
        self.assertTrue(
            matches_repeated_footer_text(
                candidate(35, 'Why Columbus Sailed South to the Indies De'), bases
            )
        )
        self.assertFalse(
            matches_repeated_footer_text(
                candidate(35, 'Why Columbus Sailed South to the Indies revised edition'), bases
            )
        )

    def test_does_not_make_page_numbers_a_footer_text_family(self) -> None:
        self.assertEqual(repeated_footer_text_bases({('footer', '$NUM')}), set())


class EdgePageNumberInferenceTests(unittest.TestCase):
    def test_pools_nearby_agreeing_roman_labels_across_page_edges(self) -> None:
        candidates = [
            candidate(2, 'iv'),
            candidate(4, 'XVI'),
            candidate(7, 'Acknowledgments XIX'),
            candidate(23, 'Why Columbus Sailed South to the Indies II'),
        ]

        self.assertEqual(infer_edge_page_numbers(candidates), {4: 'XVI', 7: 'XIX'})

    def test_does_not_relax_two_label_rule_for_same_parity(self) -> None:
        candidates = [candidate(4, 'XVI'), candidate(8, 'XX')]
        self.assertEqual(infer_edge_page_numbers(candidates), {})


class PageLabelDetectionTests(unittest.TestCase):
    def test_detects_roman_page_labels(self) -> None:
        self.assertEqual(explicit_visible_page_number('Page iv'), 'iv')
        self.assertEqual(edge_visible_page_label('VII', 'start'), 'VII')

    def test_rejects_noncanonical_roman_letter_words(self) -> None:
        self.assertIsNone(parse_visible_page_label('civil'))
        self.assertIsNone(explicit_visible_page_number('Page civil'))


class DumpPageNumbersTests(unittest.TestCase):
    def test_writes_every_page_and_marks_unknown_labels(self) -> None:
        page_numbers = [
            PageNumber(raw=1, visible=None),
            PageNumber(raw=2, visible='i'),
            PageNumber(raw=3, visible='2'),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / 'pages.csv'
            dump_page_numbers(page_numbers, output_path)
            with output_path.open(encoding='utf-8', newline='') as output_file:
                rows = list(csv.reader(output_file))

        self.assertEqual(
            rows,
            [
                ['raw', 'visible'],
                ['1', '?'],
                ['2', 'i'],
                ['3', '2'],
            ],
        )


if __name__ == '__main__':
    unittest.main()
