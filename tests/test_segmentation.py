import unittest
from dataclasses import replace

from frompdf.models import Line
from frompdf.segmentation import (
    build_page_context,
    normalized_font_family,
    same_physical_line,
    segment_lines,
    visual_line_start,
)


def line(
    text: str,
    line_no: int,
    *,
    block_no: int = 1,
    page_no: int = 1,
    font_size: float = 10.0,
    x1: float = 20.0,
    x2: float | None = 220.0,
    y1: float | None = None,
    avg_weight: float = 400.0,
    font_name: str = 'Body-Regular',
) -> Line:
    """Build a positioned synthetic line for page-local segmentation tests."""
    top = float(line_no * 12) if y1 is None else y1
    return Line(
        text=text,
        page_no=page_no,
        block_no=block_no,
        line_no_on_page=line_no,
        font_size=font_size,
        x1=x1,
        y1=top,
        x2=x2,
        y2=top + font_size,
        rel_x=None,
        rel_y=None,
        avg_weight=avg_weight,
        font_name=font_name,
    )


def group_texts(line_list: list[Line]) -> list[list[str]]:
    """Return segmented line texts without constructing Markdown blocks."""
    return [[line_obj.text for line_obj in group] for group in segment_lines(line_list)]


class ParagraphSegmentationTests(unittest.TestCase):
    def test_font_family_normalization_ignores_face_but_not_family(self) -> None:
        self.assertEqual(normalized_font_family('Calibri-Bold'), 'calibri')
        self.assertEqual(normalized_font_family('Arial-BoldItalicMT'), 'arial')
        self.assertEqual(normalized_font_family('ArialMT'), 'arial')
        self.assertNotEqual(
            normalized_font_family('Arial-BoldMT'),
            normalized_font_family('Times New Roman'),
        )

    def test_merges_spurious_pdftext_break_in_continuous_full_lines(self) -> None:
        lines = [
            line('opening line remains full and', 1),
            line('continuation before false edge', 2),
            line('continues in another parser block', 3, block_no=2),
            line('and keeps the normal rhythm', 4, block_no=2),
            line('until its genuinely short ending.', 5, block_no=2, x2=140.0),
        ]

        self.assertEqual(len(group_texts(lines)), 1)

    def test_preserves_pdftext_break_after_short_completed_line(self) -> None:
        lines = [
            line('first paragraph starts here', 1),
            line('and has a short ending.', 2, x2=100.0),
            line('Second paragraph starts here', 3, block_no=2),
            line('and continues at normal width', 4, block_no=2),
            line('before ending.', 5, block_no=2, x2=110.0),
        ]

        self.assertEqual(len(group_texts(lines)), 2)

    def test_splits_indented_first_line_inside_pdftext_block(self) -> None:
        lines = [
            line('first paragraph starts here', 1),
            line('Done.', 2, x2=105.0),
            line('Second paragraph has a first-line indent', 3, x1=30.0),
            line('then returns to the body margin', 4),
            line('and continues normally.', 5, x2=130.0),
        ]

        groups = group_texts(lines)

        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[1][0], 'Second paragraph has a first-line indent')

    def test_segments_repeated_hanging_indent_paragraphs(self) -> None:
        lines = [
            line('First reference starts at the outer margin', 1, block_no=1),
            line('and continues at the hanging margin', 2, block_no=2, x1=32.0),
            line('2021-06-07.', 3, block_no=3, x1=32.0, x2=80.0),
            line('Retrieved from https://example.test', 4, block_no=4, x1=32.0),
            line('Second reference starts at the outer margin', 5, block_no=4),
            line('and continues at the hanging margin', 6, block_no=4, x1=32.0),
            line('for another continuation line.', 7, block_no=4, x1=32.0, x2=150.0),
            line('Third reference starts at the outer margin', 8, block_no=4),
            line('and ends at the hanging margin.', 9, block_no=4, x1=32.0, x2=150.0),
            line('with one more continuation line.', 10, block_no=4, x1=32.0, x2=150.0),
            line('Fourth reference fits on one line.', 11, block_no=4, x2=140.0),
            line('Fifth reference also fits on one line.', 12, block_no=4, x2=150.0),
        ]

        groups = group_texts(lines)

        self.assertEqual([len(group) for group in groups], [4, 3, 3, 1, 1])
        self.assertEqual(
            [group[0] for group in groups],
            [
                'First reference starts at the outer margin',
                'Second reference starts at the outer margin',
                'Third reference starts at the outer margin',
                'Fourth reference fits on one line.',
                'Fifth reference also fits on one line.',
            ],
        )

    def test_learns_wide_hanging_indent(self) -> None:
        lines = [
            line('10 First reference starts after a wide label', 1),
            line('and continues at the aligned text margin', 2, x1=55.0),
            line('with another continuation line.', 3, x1=55.0, x2=150.0),
            line('11 Second reference starts after a wide label', 4),
            line('and continues at the aligned text margin', 5, x1=55.0),
            line('with another continuation line.', 6, x1=55.0, x2=150.0),
            line('12 Third reference starts after a wide label', 7),
            line('and ends at the aligned text margin.', 8, x1=55.0, x2=150.0),
        ]

        groups = group_texts(lines)

        self.assertEqual([len(group) for group in groups], [3, 3, 2])

    def test_keeps_compatible_hanging_indents_when_label_width_changes(self) -> None:
        lines = [
            line('7 First reference starts after a narrow label', 1, x1=25.0),
            line('and continues at the aligned text margin', 2, x1=55.0),
            line('with another continuation line.', 3, x1=55.0, x2=150.0),
            line('8 Second reference starts after a narrow label', 4, x1=25.0),
            line('and continues at the aligned text margin', 5, x1=55.0),
            line('with another continuation line.', 6, x1=55.0, x2=150.0),
            line('9 Third reference starts after a narrow label', 7, x1=25.0),
            line('and ends at the aligned text margin.', 8, x1=55.0, x2=150.0),
            line('10 Fourth reference starts after a wide label', 9),
            line('and continues at the aligned text margin', 10, x1=55.0),
            line('with another continuation line.', 11, x1=55.0, x2=150.0),
            line('11 Fifth reference starts after a wide label', 12),
            line('and continues at the aligned text margin', 13, x1=55.0),
            line('with another continuation line.', 14, x1=55.0, x2=150.0),
            line('12 Sixth reference starts after a wide label', 15),
            line('and ends at the aligned text margin.', 16, x1=55.0, x2=150.0),
        ]

        groups = group_texts(lines)

        self.assertEqual([len(group) for group in groups], [3, 3, 2, 3, 3, 2])

    def test_does_not_treat_wide_inset_as_first_line_indent(self) -> None:
        lines = [
            line('body opening line', 1),
            line('body ending.', 2, x2=105.0),
            line('wide inset remains in the same paragraph', 3, x1=55.0),
            line('then returns to the body margin', 4),
            line('and continues normally.', 5, x2=140.0),
        ]

        self.assertEqual(len(group_texts(lines)), 1)

    def test_does_not_learn_one_indented_quote_run_as_hanging_indent(self) -> None:
        lines = [
            line('body opening line', 1),
            line('body continuation line', 2),
            line('body ending.', 3, x2=110.0),
            line('quoted opening line', 4, block_no=2, x1=32.0),
            line('quoted continuation one', 5, block_no=2, x1=32.0),
            line('quoted continuation two', 6, block_no=2, x1=32.0),
            line('quoted continuation three', 7, block_no=2, x1=32.0),
            line('quoted continuation four', 8, block_no=2, x1=32.0),
            line('quoted ending.', 9, block_no=2, x1=32.0, x2=150.0),
            line('body resumes here', 10, block_no=3),
            line('body continues normally.', 11, block_no=3, x2=140.0),
        ]

        self.assertEqual(build_page_context(lines).hanging_indents, ())

    def test_limits_hanging_indent_to_reference_region_after_quote(self) -> None:
        lines = [
            line('quoted opening line', 1, block_no=1, x1=32.0),
            line('quoted continuation one', 2, block_no=1, x1=32.0),
            line('quoted continuation two', 3, block_no=1, x1=32.0),
            line('quoted continuation three', 4, block_no=1, x1=32.0),
            line('quoted ending.', 5, block_no=1, x1=32.0, x2=150.0),
            line('References', 6, block_no=2, y1=100.0, font_size=12.0),
            line('First reference at the outer margin', 7, block_no=3, y1=130.0),
            line('first continuation line', 8, block_no=3, y1=142.0, x1=32.0),
            line('another continuation line', 9, block_no=3, y1=154.0, x1=32.0),
            line('Second reference at the outer margin', 10, block_no=3, y1=166.0),
            line('second continuation line', 11, block_no=3, y1=178.0, x1=32.0),
            line('another continuation line', 12, block_no=3, y1=190.0, x1=32.0),
            line('Third reference at the outer margin', 13, block_no=3, y1=202.0),
            line('third continuation line', 14, block_no=3, y1=214.0, x1=32.0),
        ]

        hanging_indents = build_page_context(lines).hanging_indents

        self.assertEqual(len(hanging_indents), 1)
        self.assertGreaterEqual(hanging_indents[0].y_min, 130.0)

    def test_splits_on_unusually_large_vertical_advance(self) -> None:
        lines = [
            line('ordinary first line', 1),
            line('ordinary second line', 2),
            line('ordinary short ending.', 3, x2=105.0),
            line('Dateline after visible spacing', 4, y1=55.0, x2=120.0),
            line('signature follows normally', 5, y1=67.0, x2=130.0),
        ]

        self.assertEqual(len(group_texts(lines)), 2)

    def test_splits_heading_from_body_inside_pdftext_block(self) -> None:
        lines = [
            line('previous body line', 1, font_size=9.0),
            line('previous body ending.', 2, font_size=9.0, x2=110.0),
            line(
                '5. DISPLAY HEADING',
                3,
                block_no=2,
                font_size=12.0,
                avg_weight=700.0,
                font_name='Heading-Bold',
            ),
            line('Indented body opening', 4, block_no=2, font_size=9.0, x1=29.0),
            line('body continuation', 5, block_no=2, font_size=9.0),
            line('body ending.', 6, block_no=2, font_size=9.0, x2=100.0),
        ]

        groups = group_texts(lines)

        self.assertEqual(
            [group[0] for group in groups],
            [
                'previous body line',
                '5. DISPLAY HEADING',
                'Indented body opening',
            ],
        )

    def test_splits_same_size_heading_in_distinct_font_family(self) -> None:
        lines = [
            line('previous body line', 1),
            line(
                'BOLD DISPLAY HEADING',
                2,
                block_no=2,
                avg_weight=700.0,
                font_name='Display-Bold',
            ),
            line('body opening after heading', 3, block_no=2),
            line('body continuation after heading', 4, block_no=2),
            line('body ending.', 5, block_no=2, x2=100.0),
        ]

        groups = group_texts(lines)

        self.assertEqual(groups[1], ['BOLD DISPLAY HEADING'])
        self.assertEqual(groups[2][0], 'body opening after heading')

    def test_does_not_split_bold_title_from_bibliography_continuation(self) -> None:
        lines = [
            line('previous reference opening', 1, block_no=1),
            line('previous reference continuation', 2, block_no=1),
            line('previous reference ending.', 3, block_no=1, x2=110.0),
            line(
                'BESSE, Jean-Marc. Ver a Terra: seis ensaios sobre a paisagem',
                4,
                block_no=2,
                y1=60.0,
                avg_weight=296.1,
                font_name='Calibri-Bold',
            ),
            line(
                'ed. (Tradução Vladimir Bartalini) São Paulo: Perspectiva, 2014.',
                5,
                block_no=2,
                y1=72.0,
                avg_weight=225.0,
                font_name='Calibri',
            ),
            line('next reference opening', 6, block_no=3, y1=96.0),
            line('next reference ending.', 7, block_no=3, y1=108.0, x2=110.0),
        ]

        groups = group_texts(lines)

        self.assertIn(
            [
                'BESSE, Jean-Marc. Ver a Terra: seis ensaios sobre a paisagem',
                'ed. (Tradução Vladimir Bartalini) São Paulo: Perspectiva, 2014.',
            ],
            groups,
        )

    def test_merges_open_right_aligned_run_but_not_its_attribution(self) -> None:
        lines = [
            line('body context one', 1),
            line('body context two', 2),
            line('body context three.', 3, x2=120.0),
            line('quoted opening,', 4, block_no=2, font_size=8.5, x1=100.0),
            line('quoted conclusion.”', 5, block_no=3, font_size=8.5, x1=85.0),
            line('Author (1945)', 6, block_no=4, font_size=8.5, x1=145.0),
        ]

        groups = group_texts(lines)

        self.assertEqual(groups[-2], ['quoted opening,', 'quoted conclusion.”'])
        self.assertEqual(groups[-1], ['Author (1945)'])

    def test_same_baseline_fragment_does_not_create_false_column(self) -> None:
        lines = [
            line('body line before the fragments', 1),
            line('left fragment', 2, x2=150.0),
            line('right fragment', 3, x1=150.0, y1=24.0),
            line('next wrapped line', 4, y1=36.0),
            line('ordinary ending.', 5, y1=48.0, x2=110.0),
        ]

        self.assertEqual(len(group_texts(lines)), 1)

    def test_never_merges_across_pages(self) -> None:
        lines = [
            line('page one continues', 1),
            line('page two begins', 1, page_no=2, block_no=1),
        ]

        self.assertEqual(len(group_texts(lines)), 2)

    def test_missing_geometry_falls_back_to_pdftext_blocks(self) -> None:
        lines = [
            line('first parser block', 1, x2=None),
            line('second parser block', 2, block_no=2, x2=None),
        ]

        self.assertEqual(len(group_texts(lines)), 2)


def body_lines(first_line_no: int, count: int = 6, *, block_no: int = 9) -> list[Line]:
    """Build an ordinary body paragraph establishing the page's rhythm and size."""
    return [
        line(
            f'ordinary body text line number {index} continues',
            first_line_no + index,
            block_no=block_no,
        )
        for index in range(count - 1)
    ] + [line('ordinary body ending.', first_line_no + count - 1, block_no=block_no, x2=110.0)]


def display_line(
    text: str,
    top: float,
    *,
    block_no: int,
    x1: float = 20.0,
    x2: float = 200.0,
    font_size: float = 18.0,
    font_name: str = 'Title-Bold',
) -> Line:
    """Build a display-sized line at an explicit position."""
    return line(
        text,
        int(top),
        block_no=block_no,
        font_size=font_size,
        x1=x1,
        x2=x2,
        y1=top,
        avg_weight=700.0,
        font_name=font_name,
    )


class DisplayLineSegmentationTests(unittest.TestCase):
    def test_joins_ragged_title_lines_across_pdftext_blocks(self) -> None:
        lines = [
            display_line('Brief Announcement:', 0.0, block_no=1, x2=120.0),
            display_line('Proximal Agreement Improved', 22.0, block_no=2, x2=190.0),
            display_line('Datastreams', 44.0, block_no=3, x2=90.0),
            *body_lines(8),
        ]

        groups = group_texts(lines)

        self.assertEqual(
            groups[0], ['Brief Announcement:', 'Proximal Agreement Improved', 'Datastreams']
        )

    def test_joins_centered_title_lines_with_different_left_edges(self) -> None:
        lines = [
            display_line('Interaktives E-Learning-System Im', 0.0, block_no=1, x1=30.0, x2=210.0),
            display_line('Bereich Datenbanken', 21.0, block_no=2, x1=70.0, x2=170.0),
            *body_lines(8),
        ]

        self.assertEqual(
            group_texts(lines)[0], ['Interaktives E-Learning-System Im', 'Bereich Datenbanken']
        )

    def test_keeps_display_lines_apart_in_other_faces_sizes_or_numbering(self) -> None:
        lines = [
            display_line('Main Title of the Paper', 0.0, block_no=1),
            display_line('A Subtitle in Another Face', 22.0, block_no=2, font_name='Title-Regular'),
            display_line('Much Smaller Display Line', 44.0, block_no=3, font_size=13.0),
            display_line('Section Heading Above', 70.0, block_no=4, x2=150.0),
            display_line('2 Numbered Section', 92.0, block_no=5),
            *body_lines(10),
        ]

        groups = group_texts(lines)

        self.assertEqual(
            [group[0] for group in groups[:5]],
            [
                'Main Title of the Paper',
                'A Subtitle in Another Face',
                'Much Smaller Display Line',
                'Section Heading Above',
                '2 Numbered Section',
            ],
        )

    def test_keeps_display_lines_apart_beyond_title_leading(self) -> None:
        lines = [
            display_line('First Display Line', 0.0, block_no=1),
            display_line('Widely Separated Line', 30.0, block_no=2),
            *body_lines(8),
        ]

        self.assertEqual(len(group_texts(lines)[0]), 1)


class FaceChangeSegmentationTests(unittest.TestCase):
    def test_splits_alternating_author_names_and_affiliations(self) -> None:
        name_style = {'font_size': 12.0, 'font_name': 'Roman12-Bold', 'avg_weight': 540.0}
        affiliation_style = {'font_size': 9.0, 'font_name': 'Roman9-Regular', 'avg_weight': 450.0}
        lines = [
            *body_lines(1, block_no=1),
            line('Jane Doe', 8, block_no=2, x2=80.0, **name_style),
            line('University of Somewhere, Country', 9, block_no=2, x2=150.0, **affiliation_style),
            line('John Roe', 10, block_no=2, x2=80.0, **name_style),
            line('Institute of Elsewhere, Country', 11, block_no=2, x2=150.0, **affiliation_style),
        ]

        groups = group_texts(lines)

        self.assertEqual(
            groups[1:],
            [
                ['Jane Doe'],
                ['University of Somewhere, Country'],
                ['John Roe'],
                ['Institute of Elsewhere, Country'],
            ],
        )

    def test_keeps_card_lines_smaller_than_body_or_in_one_face_together(self) -> None:
        lines = [
            *body_lines(1, block_no=1),
            line('Jane Doe', 8, block_no=2, x2=80.0, font_size=12.0, font_name='Sans'),
            line('Hochschule Harz', 9, block_no=2, x2=90.0, font_size=10.0, font_name='Sans'),
            line(
                'jane@example.org', 10, block_no=2, x2=100.0, font_size=8.0, font_name='Sans-Italic'
            ),
            line('ORCID 0000-0001', 11, block_no=2, x2=100.0, font_size=6.5, font_name='Sans'),
        ]

        self.assertEqual(len(group_texts(lines)), 2)


class SameLineFragmentTests(unittest.TestCase):
    def test_joins_same_face_fragments_despite_size_difference(self) -> None:
        lines = [
            *body_lines(1, block_no=1),
            line('Jane Doe and Richard', 8, block_no=2, x2=120.0, font_size=12.0),
            line(
                ', John Roe and Others', 8, block_no=3, x1=120.0, x2=200.0, y1=97.0, font_size=9.5
            ),
        ]

        self.assertEqual(group_texts(lines)[-1], ['Jane Doe and Richard', ', John Roe and Others'])

    def test_keeps_same_line_fragments_in_other_faces_apart(self) -> None:
        lines = [
            *body_lines(1, block_no=1),
            line('Jane Doe and Richard', 8, block_no=2, x2=120.0, font_size=12.0),
            line(
                'Unrelated Label Text',
                8,
                block_no=3,
                x1=120.0,
                x2=200.0,
                y1=97.0,
                font_size=9.5,
                font_name='Label-Sans',
            ),
        ]

        self.assertEqual(len(group_texts(lines)[-1]), 1)

    def test_tall_delimiter_shares_the_line_of_text_centered_on_it(self) -> None:
        delimiter = replace(line('⌉', 8, x1=100.0, x2=105.0, y1=98.7), y2=116.6)
        text = line('and r continues', 8, x1=108.0, x2=200.0, y1=102.7)
        next_line = line('next line', 9, x1=108.0, x2=200.0, y1=114.7)

        self.assertTrue(same_physical_line(delimiter, text))
        self.assertFalse(same_physical_line(delimiter, next_line))

    def test_same_size_text_continues_line_after_label_in_another_face(self) -> None:
        lines = [
            *body_lines(1, block_no=1),
            line('Lemma 2.6 (Agreement). For any', 8, block_no=2, x2=120.0, font_name='Sans'),
            line(') is a subset of all values', 8, block_no=3, x1=121.0, x2=220.0),
            line('which ends the lemma here.', 9, block_no=3, x2=140.0),
        ]

        self.assertEqual(
            group_texts(lines)[-1][:2],
            ['Lemma 2.6 (Agreement). For any', ') is a subset of all values'],
        )

    def fraction_paragraph(self, last_text: str) -> list[Line]:
        """Build a paragraph whose fourth line holds an inline fraction before a parser edge."""
        return [
            line('first line of a paragraph that', 1),
            line('continues on its second line and', 2),
            line('on its third line, then says that', 3),
            line('one must send', 4, x2=120.0),
            line('n log IDmax', 4, x1=121.0, x2=150.0, y1=46.5),
            line('n', 4, x1=140.0, x2=145.0, y1=53.5, font_size=7.0),
            line(last_text, 4, x1=152.0),
            line('originally established and', 5, block_no=2),
            line('continued until its ending.', 6, block_no=2, x2=140.0),
        ]

    def test_visual_line_start_passes_stacked_fraction(self) -> None:
        lines = self.fraction_paragraph('messages. Although')

        self.assertIs(visual_line_start(lines, 6), lines[3])
        self.assertIs(visual_line_start(lines, 3), lines[3])

    def test_parser_edge_after_line_ending_in_fragments_is_overridden(self) -> None:
        self.assertEqual(len(group_texts(self.fraction_paragraph('messages. Although'))), 1)

    def test_parser_edge_after_completed_sentence_ending_in_fragments_is_kept(self) -> None:
        self.assertEqual(len(group_texts(self.fraction_paragraph('messages. Done.'))), 2)


if __name__ == '__main__':
    unittest.main()
