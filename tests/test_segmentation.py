import unittest

from frompdf.models import Line
from frompdf.segmentation import segment_lines


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

    def test_splits_same_size_bold_heading_from_body(self) -> None:
        lines = [
            line('previous body line', 1),
            line('BOLD DISPLAY HEADING', 2, block_no=2, avg_weight=700.0, font_name='Body-Bold'),
            line('body opening after heading', 3, block_no=2),
            line('body continuation after heading', 4, block_no=2),
            line('body ending.', 5, block_no=2, x2=100.0),
        ]

        groups = group_texts(lines)

        self.assertEqual(groups[1], ['BOLD DISPLAY HEADING'])
        self.assertEqual(groups[2][0], 'body opening after heading')

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


if __name__ == '__main__':
    unittest.main()
