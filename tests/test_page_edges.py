import csv
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from frompdf.models import Line, PageNumber
from frompdf.output import dump_page_numbers
from frompdf.page_edges import (
    HeaderFooterCandidate,
    complete_page_numbers,
    edge_visible_page_label,
    explicit_visible_page_number,
    has_edge_page_number,
    infer_edge_page_numbers,
    matches_repeated_footer_text,
    normalize_header_footer_text,
    parse_visible_page_label,
    recover_ocr_footer_numbers,
    remove_headers_and_footers,
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

    def test_does_not_extrapolate_backward_from_a_single_anchor(self) -> None:
        self.assertEqual(self.complete(4, (4, '2')), [None, None, None, '2'])

    def test_extrapolates_established_sequence_to_document_edges(self) -> None:
        self.assertEqual(
            self.complete(10, (8, '10'), (9, '11')),
            ['3', '4', '5', '6', '7', '8', '9', '10', '11', '12'],
        )

    def test_infers_opening_page_from_following_labels(self) -> None:
        self.assertEqual(self.complete(4, (2, '26'), (3, '27')), ['25', '26', '27', '28'])

    def test_backward_extrapolation_never_goes_below_one(self) -> None:
        self.assertEqual(self.complete(5, (4, '2'), (5, '3')), [None, None, '1', '2', '3'])

    def test_extrapolates_using_nearest_numeral_style(self) -> None:
        self.assertEqual(self.complete(4, (2, 'IV'), (3, 'v')), ['III', 'IV', 'v', 'vi'])
        self.assertEqual(
            self.complete(4, (2, 'A:02'), (3, 'A:03')), ['A:01', 'A:02', 'A:03', 'A:04']
        )

    def test_extrapolates_separate_edge_sequences_but_keeps_conflicting_gap_unknown(self) -> None:
        self.assertEqual(
            self.complete(8, (2, 'xviii'), (3, 'xix'), (6, '2'), (7, '3')),
            ['xvii', 'xviii', 'xix', None, None, '2', '3', '4'],
        )

    def test_does_not_skip_nearer_conflicting_or_duplicate_anchors_at_edges(self) -> None:
        self.assertEqual(
            self.complete(7, (2, '10'), (3, '23'), (4, '24'), (6, '40')),
            [None, '10', '23', '24', None, '40', None],
        )
        self.assertEqual(
            self.complete(6, (2, '10'), (3, '10'), (4, '11'), (5, '11')),
            [None, '10', '10', '11', '11', None],
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

    def test_does_not_extend_plain_roman_sequence_at_edges(self) -> None:
        self.assertEqual(self.complete(4, (2, 'IV')), [None, 'IV', None, None])
        self.assertEqual(self.complete(4, (4, 'ii')), [None, None, None, 'ii'])

    def test_does_not_mix_roman_and_arabic_labels(self) -> None:
        self.assertEqual(self.complete(3, (1, 'v'), (3, '7')), ['v', None, '7'])

    def test_leaves_unnumbered_pages_between_numbering_systems(self) -> None:
        self.assertEqual(
            self.complete(8, (2, 'XIV'), (5, '1'), (8, '4')),
            [None, 'XIV', None, None, '1', '2', '3', '4'],
        )

    def test_preserves_duplicates_and_fills_only_within_the_new_run(self) -> None:
        self.assertEqual(
            self.complete(5, (1, '10'), (2, '11'), (3, '11'), (5, '13')),
            ['10', '11', '11', '12', '13'],
        )

    def test_fills_long_gaps_when_predictions_agree(self) -> None:
        self.assertEqual(self.complete(12, (1, '10'), (12, '21')), [str(n) for n in range(10, 22)])

    def test_leaves_long_gaps_when_predictions_disagree(self) -> None:
        self.assertEqual(self.complete(12, (1, '10'), (12, '22')), ['10'] + [None] * 10 + ['22'])


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
    def test_keeps_short_excerpts_after_local_pagination_is_established(self) -> None:
        labels = ['10', '23', '24', '25', '63', '64', '65', '99', '100', '116']
        candidates = [candidate(raw, label) for raw, label in enumerate(labels, 1)]
        self.assertEqual(infer_edge_page_numbers(candidates), dict(enumerate(labels, 1)))

    def test_pools_changing_headers_and_retains_duplicate_pages(self) -> None:
        texts = ['2 Permission', 'Dedication 3', '4 Prologue', 'Book i 5', 'Book i 5', '6 Book i']
        candidates = [candidate(raw, text, 'header') for raw, text in enumerate(texts, 1)]
        self.assertEqual(
            infer_edge_page_numbers(candidates), {1: '2', 2: '3', 3: '4', 4: '5', 5: '5', 6: '6'}
        )

    def test_does_not_mix_numeral_systems_or_count_chapter_numbers(self) -> None:
        texts = ['xviii Preface', 'Preface xix', 'xx Preface', '2 Book i', 'Book i 3', '4 Book i']
        candidates = [candidate(raw, text, 'header') for raw, text in enumerate(texts, 1)]
        self.assertEqual(
            infer_edge_page_numbers(candidates),
            {1: 'xviii', 2: 'xix', 3: 'xx', 4: '2', 5: '3', 6: '4'},
        )

    def test_rejects_constant_years_and_chapter_numbers(self) -> None:
        candidates = [candidate(raw, '2025 Book i', 'header') for raw in range(1, 7)]
        self.assertEqual(infer_edge_page_numbers(candidates), {})

    def test_does_not_count_both_ends_or_repeated_lines_as_distinct_pages(self) -> None:
        self.assertEqual(infer_edge_page_numbers([candidate(1, '10')] * 3), {})
        self.assertEqual(infer_edge_page_numbers([candidate(1, '10'), candidate(2, '11')]), {})

    def test_rejects_conflicting_numeric_slots(self) -> None:
        candidates = [candidate(raw, f'{raw} Chapter {raw + 10}') for raw in range(1, 4)]
        self.assertEqual(infer_edge_page_numbers(candidates), {})

    def test_requires_shared_geometry_for_changing_titles(self) -> None:
        candidates = [candidate(raw, f'{raw} Title {chr(65 + raw)}') for raw in range(1, 4)]
        for raw, item in enumerate(candidates):
            item.line.y1 = 500.0 + raw * 20
            item.line.y2 = 510.0 + raw * 20
        self.assertEqual(infer_edge_page_numbers(candidates), {})

    def test_requires_shared_font_for_changing_titles(self) -> None:
        candidates = [candidate(raw, f'{raw} Title {chr(65 + raw)}') for raw in range(1, 4)]
        for raw, item in enumerate(candidates):
            item.line.font_name = str(raw)
        self.assertEqual(infer_edge_page_numbers(candidates), {})

    def test_does_not_learn_a_body_sequence_inside_edge_zones(self) -> None:
        candidates = [candidate(raw, str(raw)) for raw in range(1, 4)]
        for raw in range(1, 4):
            outside = candidate(raw, 'Publisher')
            outside.line.y1 = 610.0
            outside.line.y2 = 620.0
            candidates.append(outside)
        self.assertEqual(infer_edge_page_numbers(candidates), {})

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
    def test_accepts_plain_labels_at_both_edges(self) -> None:
        for visible in ['2', 'xviii', 'A:2']:
            self.assertEqual(edge_visible_page_label(f'{visible} Title', 'start'), visible)
            self.assertEqual(edge_visible_page_label(f'Title {visible}', 'end'), visible)
            self.assertTrue(has_edge_page_number(f'{visible} Title', visible))
            self.assertTrue(has_edge_page_number(f'Title {visible}', visible))

    def test_rejects_numbered_list_punctuation_and_partial_words(self) -> None:
        for text in ['2. A note', '2) A note', '2nd edition', 'civil rights']:
            self.assertIsNone(edge_visible_page_label(text, 'start'))
            self.assertFalse(has_edge_page_number(text, '2'))

    def test_detects_roman_page_labels(self) -> None:
        self.assertEqual(explicit_visible_page_number('Page iv'), 'iv')
        self.assertEqual(edge_visible_page_label('VII', 'start'), 'VII')

    def test_rejects_noncanonical_roman_letter_words(self) -> None:
        self.assertIsNone(parse_visible_page_label('civil'))
        self.assertIsNone(explicit_visible_page_number('Page civil'))


class FooterOCRTests(unittest.TestCase):
    def test_recovers_only_folios_corroborated_by_adjacent_printed_numbers(self) -> None:
        candidates = [candidate(1, '10'), candidate(2, 'IT'), candidate(3, '23')]
        visible = {1: '10', 3: '23'}
        self.assertEqual(recover_ocr_footer_numbers(candidates, visible), {2})
        self.assertEqual(visible, {1: '10', 2: '11', 3: '23'})
        visible = {1: '100'}
        self.assertEqual(
            recover_ocr_footer_numbers([candidate(1, '100'), candidate(2, 'IOI')], visible), {2}
        )
        self.assertEqual(visible[2], '101')

    def test_does_not_chain_ocr_guesses(self) -> None:
        candidates = [candidate(1, '10'), candidate(2, 'II'), candidate(3, 'I2')]
        visible = {1: '10'}
        self.assertEqual(recover_ocr_footer_numbers(candidates, visible), {2})
        self.assertNotIn(3, visible)

    def test_rejects_uncorroborated_or_misaligned_ocr(self) -> None:
        for text, offset in [('IT', 0.0), ('IOI', 100.0), ('Title', 0.0)]:
            damaged = candidate(2, text)
            damaged.line.x1 += offset
            damaged.line.x2 += offset
            visible = {1: '100'}
            self.assertEqual(
                recover_ocr_footer_numbers([candidate(1, '100'), damaged], visible), set()
            )
            self.assertEqual(visible, {1: '100'})


class HeaderFooterRemovalTests(unittest.TestCase):
    def test_keeps_a_note_starting_with_the_page_number(self) -> None:
        lines = []
        for raw in range(1, 4):
            footer = candidate(raw, str(raw)).line
            lines.extend(
                [
                    replace(footer, text=f'Body text {chr(65 + raw)}', y1=100.0, y2=110.0),
                    replace(
                        footer,
                        text=f'{raw} A different reference {chr(65 + raw)}.',
                        y1=550.0,
                        y2=560.0,
                    ),
                    footer,
                ]
            )
        filtered, numbers = remove_headers_and_footers(lines, [])
        self.assertEqual([number.visible for number in numbers], ['1', '2', '3'])
        self.assertEqual(len(filtered), 6)
        self.assertTrue(
            all(line.text.startswith('Body text') or 'reference' in line.text for line in filtered)
        )


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
