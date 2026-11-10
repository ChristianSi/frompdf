import unittest
from dataclasses import replace

from frompdf.models import Line
from frompdf.page_context import build_columns, margin_left_edges

BODY_TEXT = 'ordinary body text filling the whole column width'


def line(text: str, x1: float, y1: float) -> Line:
    """Build a positioned synthetic body line."""
    return Line(
        text=text,
        page_no=1,
        block_no=1,
        line_no_on_page=int(y1),
        font_size=10.0,
        x1=x1,
        y1=y1,
        x2=x1 + 200.0,
        y2=y1 + 10.0,
        rel_x=None,
        rel_y=None,
        avg_weight=400.0,
        font_name='Body-Regular',
    )


def column(x1: float, count: int = 6, text: str = BODY_TEXT) -> list[Line]:
    """Build a column of lines sharing one left edge."""
    return [line(text, x1, 12.0 + 12.0 * index) for index in range(count)]


class MarginLeftEdgeTests(unittest.TestCase):
    def test_stray_labels_left_of_a_column_do_not_shift_its_margin(self) -> None:
        # Figure labels between two columns, as in nature.
        labels = [
            line('Magnetic Field (mT)', 250.0, 300.0),
            line('Frequency', 262.0, 320.0),
            line('15', 275.0, 340.0),
            line('Temperature (K)', 284.0, 360.0),
        ]

        self.assertEqual(
            margin_left_edges(column(40.0) + labels + column(300.0), 10.0), [40.0, 300.0]
        )

    def test_first_line_indents_stay_with_their_margin(self) -> None:
        indented = [line(BODY_TEXT, 52.0, 200.0), line(BODY_TEXT, 52.0, 300.0)]

        self.assertEqual(margin_left_edges(column(40.0) + indented, 10.0), [40.0])

    def test_leftmost_established_edge_is_the_margin(self) -> None:
        # Hanging labels set out from the text are established as well.
        hanging = column(30.0, count=3, text='[1] reference entry with a hanging label')

        self.assertEqual(margin_left_edges(hanging + column(40.0), 10.0), [30.0])

    def test_column_without_established_edge_keeps_its_leftmost_edge(self) -> None:
        stray = [line('Magnetic Field (mT)', 400.0, 12.0), line('Frequency', 410.0, 24.0)]

        self.assertEqual(margin_left_edges(column(40.0) + stray, 10.0), [40.0, 400.0])

    def test_too_few_prose_lines_do_not_establish_an_edge(self) -> None:
        # Two prose lines and a run of tick labels sharing an edge.
        labels = column(280.0, count=2, text='Magnetic Field (mT)') + column(
            280.0, count=4, text='0.5'
        )

        self.assertEqual(
            margin_left_edges(column(40.0) + labels + column(300.0), 10.0), [40.0, 300.0]
        )


def spanning(x1: float, x2: float, y1: float) -> Line:
    """Build a line running from x1 to x2."""
    return replace(line(BODY_TEXT, x1, y1), x2=x2)


class ColumnRightEdgeTests(unittest.TestCase):
    def test_lines_spanning_into_the_next_column_do_not_widen_a_column(self) -> None:
        # A caption set across the page below a column, as in nature.
        caption = [spanning(40.0, 500.0, 200.0 + 12.0 * index) for index in range(2)]
        columns = build_columns(column(40.0, count=8) + caption + column(300.0, count=8), 10.0)

        self.assertEqual([(c.left, c.right) for c in columns], [(40.0, 240.0), (300.0, 500.0)])

    def test_mostly_wide_lines_keep_their_right_edge(self) -> None:
        wide = [spanning(40.0, 500.0, 200.0 + 12.0 * index) for index in range(6)]
        columns = build_columns(column(40.0, count=3) + wide + column(300.0, count=6), 10.0)

        self.assertEqual(columns[0].right, 500.0)


if __name__ == '__main__':
    unittest.main()
