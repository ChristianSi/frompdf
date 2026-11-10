import unittest
from dataclasses import replace

from frompdf.line_features import normalized_font_family, same_physical_line
from frompdf.models import InlineRange, Line
from frompdf.page_context import build_page_context
from frompdf.segmentation import (
    find_marker_lines,
    next_visual_line,
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

    def test_splits_on_blank_line_gap_after_full_open_line(self) -> None:
        lines = [
            line('ordinary first line', 1),
            line('ordinary second line', 2),
            line('ordinary third line', 3),
            line('full line without an ending', 4),
            line('Next paragraph after a blank line', 5, y1=72.0),
            line('continues normally', 6, y1=84.0),
        ]

        self.assertEqual(len(group_texts(lines)), 2)

    def test_keeps_smaller_gap_after_full_open_line(self) -> None:
        lines = [
            line('ordinary first line', 1),
            line('ordinary second line', 2),
            line('ordinary third line', 3),
            line('full line without an ending', 4),
            line('continuation after some spacing', 5, y1=67.0),
            line('continues normally', 6, y1=79.0),
        ]

        self.assertEqual(len(group_texts(lines)), 1)

    def test_splits_smaller_print_after_smaller_gap_below_full_open_line(self) -> None:
        # The page's dominant size, as of an abstract, matches neither the body
        # text nor the small print, as on the first page of lipics-64.
        abstract = [
            line(f'abstract text in its own size filling line {n}', n, y1=n * 11.0, font_size=9.0)
            for n in range(1, 9)
        ]
        body = [line(f'ordinary body text line {n}', n, y1=100.0 + n * 12.0) for n in range(1, 4)]
        for name, font_size, expected in (
            ('visibly smaller print', 7.0, '© Notice in print after spacing;'),
            ('barely smaller print', 9.8, 'ordinary body text line 1'),
        ):
            with self.subTest(name):
                small_print = [
                    line('© Notice in print after spacing;', 5, y1=155.0, font_size=font_size),
                    line('licensed', 6, y1=163.0, font_size=font_size),
                ]

                self.assertEqual(group_texts([*abstract, *body, *small_print])[-1][0], expected)

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


def inset_line(text: str, block_no: int, y1: float, x2: float = 160.0) -> Line:
    """Build a small-print line inset from the body column, as in a letterhead."""
    return line(text, round(y1), block_no=block_no, font_size=8.0, x1=80.0, x2=x2, y1=y1)


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


class InsetPassageSegmentationTests(unittest.TestCase):
    def test_joins_evenly_spaced_inset_lines_across_pdftext_blocks(self) -> None:
        lines = [
            *body_lines(1, block_no=1),
            inset_line('MINISTERIO', 2, 100.0, x2=120.0),
            inset_line('DE AGRICULTURA, PESCA', 3, 109.5),
            inset_line('Y ALIMENTACION', 3, 119.0),
        ]

        self.assertEqual(
            group_texts(lines)[1:],
            [['MINISTERIO', 'DE AGRICULTURA, PESCA', 'Y ALIMENTACION']],
        )

    def test_keeps_inset_lines_apart_without_evenly_spaced_followers(self) -> None:
        cases = {
            'last line of its block': [
                inset_line('Leibniz International Proceedings', 2, 100.0, x2=180.0),
                inset_line('Schloss Dagstuhl Publishing', 3, 109.5, x2=150.0),
            ],
            'completed sentence': [
                inset_line('Leibniz International Proceedings.', 2, 100.0, x2=180.0),
                inset_line('Schloss Dagstuhl Publishing', 3, 109.5, x2=150.0),
                inset_line('Wadern, Germany', 3, 119.0, x2=130.0),
            ],
            'wider spacing at the block edge': [
                inset_line('Leibniz International Proceedings', 2, 100.0, x2=180.0),
                inset_line('Schloss Dagstuhl Publishing', 3, 111.0, x2=150.0),
                inset_line('Wadern, Germany', 3, 119.0, x2=130.0),
            ],
        }

        for name, inset_lines in cases.items():
            with self.subTest(name):
                self.assertEqual(len(group_texts([*body_lines(1, block_no=1), *inset_lines])), 3)


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

    def script_fragment_line(self, fragment_x1: float, fragment_size: float = 7.0) -> list[Line]:
        """Build a line whose script-sized fragment pdftext puts into the next block."""
        return [
            *body_lines(1, block_no=1),
            line('Definition 2.4. For any set R', 8, block_no=2, x2=120.0),
            line('d', 8, block_no=3, x1=fragment_x1, x2=fragment_x1 + 4.0, font_size=fragment_size),
            line(', |R| > s + f where s > f, define', 8, block_no=3, x1=fragment_x1 + 4.5),
            line('R(f,x) by removing the f elements.', 9, block_no=3, x2=180.0),
        ]

    def test_touching_script_sized_fragment_continues_the_line(self) -> None:
        self.assertEqual(len(group_texts(self.script_fragment_line(120.0))[-1]), 4)

    def test_script_fragment_conservative_negatives(self) -> None:
        for name, fragment_x1, fragment_size in (
            ('gap before the fragment', 126.0, 7.0),
            ('far smaller than a script', 120.0, 3.0),
        ):
            with self.subTest(name):
                lines = self.script_fragment_line(fragment_x1, fragment_size)

                self.assertEqual(group_texts(lines)[-1][0], 'd')

    def fraction_paragraph(self, last_text: str, last_x2: float = 220.0) -> list[Line]:
        """Build a paragraph whose fourth line holds an inline fraction before a parser edge."""
        return [
            line('first line of a paragraph that', 1),
            line('continues on its second line and', 2),
            line('on its third line, then says that', 3),
            line('one must send', 4, x2=120.0),
            line('n log IDmax', 4, x1=121.0, x2=150.0, y1=46.5),
            line('n', 4, x1=140.0, x2=145.0, y1=53.5, font_size=7.0),
            line(last_text, 4, x1=152.0, x2=last_x2),
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
        lines = self.fraction_paragraph('messages. Done.', last_x2=212.0)

        self.assertEqual(len(group_texts(lines)), 2)

    def test_parser_edge_after_sentence_reaching_the_column_edge_is_overridden(self) -> None:
        self.assertEqual(len(group_texts(self.fraction_paragraph('messages. Done.'))), 1)


class RunningTextContinuationTests(unittest.TestCase):
    """Pdftext block edges below a line, in a column from 20 to 220 with 10 pt type."""

    OPEN = 'the end of this line leaves the sentence open and'
    CLOSED = 'the end of this line completes its sentence here.'
    NEXT = 'The following text continues below that line'

    def group_count(self, previous: Line, current: Line) -> int:
        lines = [
            *(line(f'Ordinary body text filling line {n}', n, x1=20.0) for n in range(1, 6)),
            previous,
            current,
            line('and yet another ordinary line of the body text', 8, block_no=current.block_no),
        ]
        return len(group_texts(lines))

    def previous(self, text: str = OPEN, **options) -> Line:
        return line(text, 6, **options)

    def current(self, text: str = NEXT, **options) -> Line:
        return line(text, 7, block_no=2, **options)

    def test_full_line_ending_a_sentence_continues(self) -> None:
        self.assertEqual(self.group_count(self.previous(self.CLOSED), self.current()), 1)

    def test_line_mostly_in_italics_continues(self) -> None:
        current = replace(
            self.current(font_name='Body-Italic'), ranges=(InlineRange(4, 40, 'italic'),)
        )

        self.assertEqual(self.group_count(self.previous(), current), 1)

    def test_italics_do_not_mislead_a_style_change_with_opaque_font_names(self) -> None:
        previous = replace(
            self.previous(font_name='AdvItalic12'), ranges=(InlineRange(0, 40, 'italic'),)
        )
        current = line(self.NEXT, 7, font_name='AdvRoman34')
        following = line('and yet another ordinary line of the text', 8, font_name='AdvRoman34')
        lines = [
            *(
                line(f'Ordinary body text filling line {n}', n, font_name='AdvRoman34')
                for n in range(1, 6)
            ),
            previous,
            current,
            following,
        ]

        self.assertEqual(len(group_texts(lines)), 1)

    def test_break_below_an_indented_first_line_is_overridden(self) -> None:
        self.assertEqual(self.group_count(self.previous(x1=30.0), self.current()), 1)

    def test_visual_line_above_a_short_line_is_compared_as_a_whole(self) -> None:
        lines = [
            *(line(f'Ordinary body text filling line {n}', n) for n in range(1, 6)),
            line('the first piece of this', 6, x2=120.0),
            line('the second piece of it', 6, x1=121.0),
            line('short final line', 7, x2=100.0, block_no=2),
        ]

        self.assertEqual(len(group_texts(lines)), 1)

    def visual_line_ending_in_formula(self, formula_size: float) -> list[Line]:
        """Build a full visual line ending in a formula in smaller type, before a parser edge."""
        return [
            *(line(f'Ordinary body text filling line {n}', n) for n in range(1, 6)),
            line('the first piece of this text', 6, x2=150.0),
            line('= max ri ∈ R(f,Gm(R)) ||ri −', 6, x1=152.0, y1=72.5, font_size=formula_size),
            line('Gm(R)||2 continues the sentence', 7, block_no=2),
            line('and yet another ordinary line of the body text', 8, block_no=2),
        ]

    def test_visual_line_ending_in_script_sized_formula_is_judged_by_its_start(self) -> None:
        self.assertEqual(len(group_texts(self.visual_line_ending_in_formula(5.0))), 1)

    def test_visual_line_ending_in_far_smaller_text_is_not_judged_by_its_start(self) -> None:
        self.assertEqual(len(group_texts(self.visual_line_ending_in_formula(3.0))), 2)

    def test_conservative_negatives(self) -> None:
        for name, previous, current in (
            ('short open line', self.previous(x2=100.0), self.current()),
            (
                'sentence end short of the edge',
                self.previous(self.CLOSED, x2=212.0),
                self.current(),
            ),
            (
                'sentence end above an italic line',
                self.previous(self.CLOSED),
                replace(
                    self.current(font_name='Body-Italic'), ranges=(InlineRange(4, 40, 'italic'),)
                ),
            ),
            (
                'fully italic line',
                self.previous(),
                replace(
                    self.current(font_name='Body-Italic'), ranges=(InlineRange(0, 45, 'italic'),)
                ),
            ),
            (
                'run-in heading in bold',
                self.previous(),
                replace(
                    self.current(font_name='Body-Italic'),
                    ranges=(InlineRange(0, 8, 'bold'), InlineRange(8, 40, 'italic')),
                ),
            ),
            ('inset line', self.previous(self.CLOSED), self.current(x1=150.0)),
            ('large indent above', self.previous(x1=60.0), self.current()),
            ('reference', self.previous(self.CLOSED), self.current('[3] A. Author, A paper')),
            ('enumeration', self.previous(self.CLOSED), self.current('(2) The second item')),
            ('theorem', self.previous(self.CLOSED), self.current('▶ Definition of terms')),
            ('numbered item', self.previous(self.CLOSED), self.current('4. The fourth item')),
        ):
            with self.subTest(name):
                self.assertEqual(self.group_count(previous, current), 2)

    def test_gap_keeps_a_paragraph_break(self) -> None:
        self.assertEqual(
            self.group_count(self.previous(self.CLOSED), line(self.NEXT, 8, block_no=2)), 2
        )

    SHORT_OPEN = 'notice by its two authors;'
    LOWER = 'licensed under some licence'

    def test_short_open_line_continues_in_lower_case(self) -> None:
        # As in lipics-64's licence notice, whose lines are far from full.
        self.assertEqual(
            self.group_count(self.previous(self.SHORT_OPEN, x2=120.0), self.current(self.LOWER)),
            1,
        )

    def test_lower_case_continuation_conservative_negatives(self) -> None:
        short_open = self.previous(self.SHORT_OPEN, x2=120.0)
        for name, previous, current in (
            ('sentence end', self.previous('notice by its two authors.', x2=120.0), None),
            ('upper case', short_open, self.current('Licensed under some licence')),
            ('letter label', short_open, self.current('a) the first item of a list')),
            ('roman label', short_open, self.current('iv. the fourth item of a list')),
            ('other left edge', short_open, self.current(self.LOWER, x1=60.0)),
            ('other face', short_open, self.current(self.LOWER, font_name='Label-Sans')),
            ('larger gap', short_open, self.current(self.LOWER, y1=90.0)),
        ):
            with self.subTest(name):
                current = current or self.current(self.LOWER)
                self.assertEqual(self.group_count(previous, current), 2)


class MarkerLineTests(unittest.TestCase):
    """Lines in a column from 20 to 220, centered at 120."""

    def text_lines(self) -> list[Line]:
        return [
            line('The first line of the closing paragraph', 1),
            line('and the second line of that paragraph', 2),
            line('with a short end.', 3, x2=100.0),
        ]

    def groups_with_following_text(self, *middle: Line) -> list[list[str]]:
        lines = [*self.text_lines(), *middle, line('The next section starts here', 6)]
        return [
            [line_obj.text for line_obj in group]
            for group in segment_lines(lines, marker_lines=find_marker_lines(lines))
        ]

    def test_centered_ornament_with_tight_leading_is_separated(self) -> None:
        ornament = line('⸟', 4, x1=117.0, x2=123.0, y1=44.0, font_size=11.0)

        self.assertEqual(
            self.groups_with_following_text(ornament)[-2:],
            [['⸟'], ['The next section starts here']],
        )

    def test_staggered_pieces_form_one_marker_line(self) -> None:
        pieces = [
            line('*', 4, x1=114.0, x2=118.0, y1=48.0),
            line('*', 4, x1=118.0, x2=122.0, y1=51.0),
            line('*', 4, x1=122.0, x2=126.0, y1=48.0),
        ]

        self.assertEqual(
            self.groups_with_following_text(*pieces)[-2:],
            [['*', '*', '*'], ['The next section starts here']],
        )

    def test_marker_on_a_sparse_page_ignores_its_own_pieces_for_columns(self) -> None:
        lines = [
            line('A closing paragraph that fills its column', 1),
            line('*', 2, x1=114.0, x2=118.0),
            line('*', 2, x1=118.0, x2=122.0),
            line('*', 2, x1=122.0, x2=126.0),
        ]

        self.assertEqual(len(find_marker_lines(lines)), 3)

    def test_marker_is_centered_within_its_own_column(self) -> None:
        lines = [
            *(line(f'Left column text, line {n}', n, x2=200.0) for n in range(1, 7)),
            *(
                line(f'Right column text, line {n}', n + 6, x1=300.0, x2=480.0, y1=n * 12.0)
                for n in range(1, 7)
            ),
            line('⁂', 13, x1=387.0, x2=393.0, y1=84.0),
        ]

        self.assertEqual(set(find_marker_lines(lines)), {id(lines[-1])})

    def test_conservative_negatives(self) -> None:
        for name, candidate in {
            'text': line('Fin', 4, x1=110.0, x2=130.0),
            'digit': line('1', 4, x1=117.0, x2=123.0),
            'uncentered': line('-', 4, x1=60.0, x2=66.0),
            'left-aligned': line('***', 4, x2=32.0),
            'wide': line('. . . . . . . . . . . . . .', 4, x1=30.0, x2=210.0),
            'undecoded': line('\ufffd\ufffd + \ufffd\ufffd', 4, x1=105.0, x2=135.0),
            'blank': line(' ', 4, x1=117.0, x2=123.0),
        }.items():
            with self.subTest(name):
                self.assertEqual(find_marker_lines([*self.text_lines(), candidate]), {})

    def test_note_sign_on_a_line_of_text_is_no_marker(self) -> None:
        lines = [
            *self.text_lines(),
            line('Centered title', 4, x1=90.0, x2=116.0),
            line('*', 4, x1=116.0, x2=120.0),
        ]

        self.assertEqual(find_marker_lines(lines), {})

    def test_ordinary_paragraph_is_not_split_without_markers(self) -> None:
        self.assertEqual(len(self.groups_with_following_text()), 1)


if __name__ == '__main__':
    unittest.main()


def open_body_lines(start: int, count: int) -> list[Line]:
    """Build full, open body lines of one column."""
    return [
        line(f'ordinary body text running on line {start + n}', start + n) for n in range(count)
    ]


class VisualLineIndentTests(unittest.TestCase):
    def test_indent_after_a_line_ending_in_a_script_piece_starts_a_paragraph(self) -> None:
        # As GaV₄S₈²³. ending a paragraph in nature.
        lines = [
            *open_body_lines(1, 5),
            line('ending with a formula GaV', 6, x2=120.0),
            replace(line('23.', 6, x1=120.5, x2=130.0, font_size=6.0), y1=70.0, y2=76.0),
            line('The next paragraph starts with an indent', 7, x1=30.0),
            *open_body_lines(8, 3),
        ]

        groups = group_texts(lines)

        self.assertEqual(groups[1][0], 'The next paragraph starts with an indent')
        self.assertEqual(groups[0][-1], '23.')

    def test_indented_line_split_by_inline_math_starts_a_paragraph(self) -> None:
        # As "… is given by κ = ∑ cᵢvᵢρᵢ" in nature, split before vᵢρᵢ.
        lines = [
            *open_body_lines(1, 5),
            line('the paragraph ends here.', 6, x2=120.0),
            line('The next paragraph is given by the formula', 7, x1=30.0, x2=200.0),
            line('vi', 7, x1=200.5, x2=210.0),
            *open_body_lines(8, 3),
        ]

        groups = group_texts(lines)

        self.assertEqual(groups[1][:2], ['The next paragraph is given by the formula', 'vi'])

    def test_split_line_followed_by_another_indented_line_starts_no_paragraph(self) -> None:
        lines = [
            *open_body_lines(1, 5),
            line('the paragraph ends here.', 6, x2=120.0),
            line('An inset passage is given by the formula', 7, x1=30.0, x2=200.0),
            line('vi', 7, x1=200.5, x2=210.0),
            line('and continues inset on the next line', 8, x1=30.0),
            *open_body_lines(9, 3),
        ]

        groups = group_texts(lines)

        self.assertNotIn('An inset passage is given by the formula', [g[0] for g in groups])


class NextVisualLineTests(unittest.TestCase):
    def test_skips_later_pieces_of_the_same_visual_line(self) -> None:
        lines = [
            line('given by the formula', 1, x2=150.0),
            line('vi', 1, x1=150.5, x2=160.0),
            line('ρi, where', 1, x1=160.5, x2=200.0),
            line('the next visual line', 2),
        ]

        self.assertIs(next_visual_line(lines, 0), lines[3])

    def test_returns_none_after_the_last_visual_line(self) -> None:
        lines = [line('given by the formula', 1, x2=150.0), line('vi', 1, x1=150.5, x2=160.0)]

        self.assertIsNone(next_visual_line(lines, 0))
