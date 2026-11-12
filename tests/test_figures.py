import unittest

from frompdf.blocks import lines_to_markdown_blocks
from frompdf.figures import FigureLayout, figure_grid, find_figures, join_boxes
from frompdf.models import FigureText, Line, PageNumber, Paragraph

BODY_TEXT = 'ordinary body text filling the whole column width'


def line(
    text: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float | None = None,
    *,
    font_size: float = 10.0,
    page_no: int = 1,
) -> Line:
    """Build a positioned synthetic line."""
    return Line(
        text=text,
        page_no=page_no,
        block_no=1,
        line_no_on_page=int(y1),
        font_size=font_size,
        x1=x1,
        y1=y1,
        x2=x2,
        y2=y1 + font_size if y2 is None else y2,
        rel_x=None,
        rel_y=None,
        avg_weight=400.0,
        font_name='Body-Regular',
    )


def body(top: float, count: int, *, page_no: int = 1) -> list[Line]:
    """Build full lines of body text from top, 12 points apart."""
    return [
        line(BODY_TEXT, 40.0, top + 12.0 * index, 300.0, page_no=page_no) for index in range(count)
    ]


# A plot drawn from (60, 200) to (300, 320), with labels around it.
PANEL = (60.0, 200.0, 300.0, 320.0)


def labels() -> list[Line]:
    """Build the labels of the plot: tick values, axis titles, and a legend."""
    return [
        line('100', 82.0, 200.0, 94.0, font_size=8.0),
        line('0', 90.0, 312.0, 94.0, font_size=8.0),
        line('Signal (a.u.)', 62.0, 230.0, 70.0, 290.0, font_size=8.0),
        line('30 mT', 250.0, 210.0, 270.0, font_size=8.0),
        line('Time (ps)', 180.0, 330.0, 216.0, font_size=8.0),
    ]


def caption() -> list[Line]:
    """Build a two-line caption below the plot."""
    return [
        line(
            'Fig. 1 A plot of the signal over time, with the field',
            40.0,
            350.0,
            300.0,
            font_size=9.0,
        ),
        line('as indicated.', 40.0, 360.0, 100.0, font_size=9.0),
    ]


class FigureDetectionTests(unittest.TestCase):
    def test_labels_around_drawings_with_a_caption_form_a_figure(self) -> None:
        # A body line, the short last line of its paragraph, and a heading
        # reach into the area around the plot.
        above = [
            *body(124.0, 4),
            line('ends.', 40.0, 172.0, 70.0),
            line('Experimental results', 120.0, 184.0, 260.0, font_size=14.0),
        ]
        lines = [*above, *labels(), *caption(), *body(400.0, 3)]

        figures = find_figures(lines, {1: [PANEL]})

        self.assertEqual(len(figures), 1)
        self.assertEqual(
            [label.text for label in figures[0].lines], [label.text for label in labels()]
        )
        self.assertEqual(
            [line_obj.text for line_obj in figures[0].caption_lines],
            [line_obj.text for line_obj in caption()],
        )

    def test_drawings_without_a_caption_form_no_figure(self) -> None:
        lines = [*body(100.0, 4), *labels(), *body(400.0, 3)]

        self.assertEqual(find_figures(lines, {1: [PANEL]}), [])

    def test_caption_far_below_the_drawings_is_not_theirs(self) -> None:
        far_caption = [line('Fig. 1 A distant caption.', 40.0, 500.0, 200.0, font_size=9.0)]

        self.assertEqual(find_figures([*body(100.0, 4), *labels(), *far_caption], {1: [PANEL]}), [])

    def test_small_drawings_are_no_panels(self) -> None:
        rule = (40.0, 330.0, 300.0, 331.0)

        self.assertEqual(find_figures([*body(100.0, 4), *caption()], {1: [rule]}), [])

    def test_side_by_side_figures_keep_their_own_captions_and_labels(self) -> None:
        left = (60.0, 200.0, 200.0, 300.0)
        right = (330.0, 200.0, 470.0, 300.0)
        lines = [
            line('left label', 100.0, 305.0, 150.0, font_size=8.0),
            line('right label', 370.0, 305.0, 420.0, font_size=8.0),
            line('Fig. 1 The left figure.', 60.0, 330.0, 200.0, font_size=9.0),
            line('Fig. 2 The right figure.', 330.0, 330.0, 470.0, font_size=9.0),
        ]

        figures = find_figures(lines, {1: [left, right]})

        self.assertEqual(
            [([label.text for label in figure.lines], figure.caption.text) for figure in figures],
            [
                (['left label'], 'Fig. 1 The left figure.'),
                (['right label'], 'Fig. 2 The right figure.'),
            ],
        )

    def test_upper_panel_shares_the_caption_below_the_lower_one(self) -> None:
        upper = (100.0, 100.0, 300.0, 200.0)
        lower = (100.0, 240.0, 300.0, 340.0)
        lines = [
            line('upper label', 150.0, 205.0, 200.0, font_size=8.0),
            line('lower label', 150.0, 345.0, 200.0, font_size=8.0),
            line('Fig. 1 Two panels.', 100.0, 370.0, 200.0, font_size=9.0),
        ]

        figures = find_figures(lines, {1: [upper, lower]})

        self.assertEqual(len(figures), 1)
        self.assertEqual([label.text for label in figures[0].lines], ['upper label', 'lower label'])

    def test_figure_without_labels_keeps_its_caption(self) -> None:
        figures = find_figures([*body(100.0, 4), *caption()], {1: [PANEL]})

        self.assertEqual(len(figures), 1)
        self.assertEqual(figures[0].lines, [])
        self.assertEqual(len(figures[0].caption_lines), 2)


class JoinBoxesTests(unittest.TestCase):
    def test_joins_chains_of_near_boxes_and_keeps_distant_ones(self) -> None:
        boxes = [(0.0, 0.0, 10.0, 10.0), (12.0, 0.0, 20.0, 10.0), (22.0, 5.0, 30.0, 20.0)]
        distant = (100.0, 0.0, 110.0, 10.0)

        self.assertEqual(
            sorted(join_boxes([*boxes, distant], 3.0)),
            [(0.0, 0.0, 30.0, 20.0), distant],
        )

    def test_joined_box_may_reach_further_boxes(self) -> None:
        # The third box is near only the union of the first two.
        boxes = [(0.0, 0.0, 10.0, 10.0), (0.0, 10.0, 50.0, 20.0), (45.0, 0.0, 50.0, 5.0)]

        self.assertEqual(join_boxes(boxes, 0.0), [(0.0, 0.0, 50.0, 20.0)])


class FigureGridTests(unittest.TestCase):
    def test_labels_keep_their_relative_positions(self) -> None:
        # 8-point labels, 4 points per character.
        lines = [
            line('1.0', 10.0, 0.0, 22.0, font_size=8.0),
            line('30 mT', 58.0, 0.0, 78.0, font_size=8.0),
            line('0.0', 10.0, 16.0, 22.0, font_size=8.0),
            line('Time (ps)', 34.0, 32.0, 70.0, font_size=8.0),
        ]

        self.assertEqual(
            figure_grid(lines),
            ['1.0         30 mT', '', '0.0', '', '      Time (ps)'],
        )

    def test_vertical_label_is_written_horizontally_at_its_center(self) -> None:
        lines = [
            line('10', 32.0, 0.0, 40.0, font_size=8.0),
            line('Signal', 0.0, 0.0, 8.0, 48.0, font_size=8.0),
            line('0', 34.0, 40.0, 38.0, font_size=8.0),
        ]

        self.assertEqual(figure_grid(lines), ['        10', '', 'Signal', '', '        0'])

    def test_colliding_labels_move_to_a_free_row(self) -> None:
        lines = [
            line('first', 0.0, 0.0, 20.0, font_size=8.0),
            line('second', 4.0, 0.0, 28.0, font_size=8.0),
        ]

        self.assertEqual(figure_grid(lines), ['first', ' second'])


class FigureBlockTests(unittest.TestCase):
    def test_paragraph_interrupted_by_a_figure_continues_past_it(self) -> None:
        before = [
            *body(100.0, 7),
            line('a sentence running into the figure, continued on', 40.0, 184.0, 300.0),
        ]
        figure_lines = [line('0 40 80', 120.0, 330.0, 160.0, font_size=8.0)]
        caption_lines = [line('Fig. 1 The caption.', 40.0, 350.0, 140.0, font_size=9.0)]
        after = [
            line('the next page, where it ends.', 40.0, 100.0, 200.0, page_no=2),
            *body(112.0, 7, page_no=2),
        ]
        figure = FigureLayout(1, figure_lines, caption_lines, 200.0, 359.0)
        pages = {1: PageNumber(1, None), 2: PageNumber(2, None)}

        blocks = lines_to_markdown_blocks(
            [*before, *figure_lines, *caption_lines, *after], pages, figures=[figure]
        )

        self.assertEqual([type(block) for block in blocks][:3], [Paragraph, FigureText, Paragraph])
        self.assertIn('continued on the next page', blocks[0].text.replace('\n', ' '))
        self.assertEqual(blocks[1].text, '0 40 80')
        self.assertEqual(blocks[2].text, 'Fig. 1 The caption.')


if __name__ == '__main__':
    unittest.main()
