import unittest

from frompdf.models import Line
from frompdf.reading_order import order_lines_for_reading


def text_block(
    block_no: int,
    label: str,
    x1: float,
    y1: float,
    x2: float,
    line_count: int = 3,
) -> list[Line]:
    """Build a multiline synthetic pdftext block."""
    return [
        Line(
            text=f'{label} substantial text line {line_index}',
            page_no=1,
            block_no=block_no,
            line_no_on_page=block_no * 10 + line_index,
            font_size=10.0,
            x1=x1,
            y1=y1 + line_index * 10,
            x2=x2,
            y2=y1 + line_index * 10 + 8,
            rel_x=None,
            rel_y=None,
            avg_weight=400.0,
        )
        for line_index in range(line_count)
    ]


def ordered_block_numbers(line_list: list[Line]) -> list[int]:
    """Return block numbers without repeating consecutive line entries."""
    result: list[int] = []
    for line_obj in line_list:
        if not result or result[-1] != line_obj.block_no:
            result.append(line_obj.block_no)
    return result


class ReadingOrderTests(unittest.TestCase):
    def test_orders_two_columns_column_by_column(self) -> None:
        lines = [
            *text_block(1, 'left top', 20, 20, 120),
            *text_block(2, 'right top', 150, 20, 250),
            *text_block(3, 'left bottom', 20, 80, 120),
            *text_block(4, 'right bottom', 150, 80, 250),
        ]

        ordered = order_lines_for_reading(lines)

        self.assertEqual(ordered_block_numbers(ordered), [1, 3, 2, 4])

    def test_full_width_band_separates_two_column_regions(self) -> None:
        lines = [
            *text_block(1, 'upper left', 20, 20, 120),
            *text_block(2, 'upper right', 150, 20, 250),
            *text_block(3, 'upper left later', 20, 60, 120),
            *text_block(4, 'upper right later', 150, 60, 250),
            *text_block(5, 'wide caption', 20, 110, 250),
            *text_block(6, 'lower left', 20, 170, 120),
            *text_block(7, 'lower right', 150, 170, 250),
            *text_block(8, 'lower left later', 20, 210, 120),
            *text_block(9, 'lower right later', 150, 210, 250),
        ]

        ordered = order_lines_for_reading(lines)

        self.assertEqual(ordered_block_numbers(ordered), [1, 3, 2, 4, 5, 6, 8, 7, 9])

    def test_orders_three_aligned_author_cards_left_to_right(self) -> None:
        lines = [
            *text_block(1, 'middle author', 110, 20, 190, line_count=5),
            *text_block(2, 'left author', 20, 20, 90, line_count=5),
            *text_block(3, 'right author', 210, 20, 290, line_count=5),
        ]

        ordered = order_lines_for_reading(lines)

        self.assertEqual(ordered_block_numbers(ordered), [2, 1, 3])

    def test_preserves_ambiguous_blocks_without_vertical_overlap(self) -> None:
        lines = [
            *text_block(1, 'upper right', 150, 20, 250),
            *text_block(2, 'lower left', 20, 100, 120),
        ]

        ordered = order_lines_for_reading(lines)

        self.assertEqual(ordered_block_numbers(ordered), [1, 2])


if __name__ == '__main__':
    unittest.main()
