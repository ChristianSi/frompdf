import unittest

from frompdf.rules import (
    Rule,
    clipped_segment,
    filled_rules,
    join_rules,
    multiply,
    stroked_rules,
    transform,
)


def rectangle(left: float, bottom: float, right: float, top: float) -> list[tuple[float, float]]:
    """Return the closed outline of a rectangle."""
    return [(left, bottom), (right, bottom), (right, top), (left, top), (left, bottom)]


class MatrixTests(unittest.TestCase):
    def test_nested_matrices_apply_inner_matrix_first(self) -> None:
        # A form scaled by half and moved, containing content moved by (-100, -200),
        # as for a table cropped from a larger page.
        inner = (1.0, 0.0, 0.0, 1.0, -100.0, -200.0)
        outer = (0.5, 0.0, 0.0, 0.5, 72.0, 700.0)

        self.assertEqual(transform(multiply(inner, outer), 110.0, 220.0), (77.0, 710.0))


class StrokedRuleTests(unittest.TestCase):
    def test_rectangle_outline_yields_its_four_edges(self) -> None:
        rules = stroked_rules([rectangle(10.0, 20.0, 110.0, 70.0)], None)

        self.assertCountEqual(
            rules,
            [
                (True, 20.0, 10.0, 110.0),
                (False, 110.0, 20.0, 70.0),
                (True, 70.0, 10.0, 110.0),
                (False, 10.0, 20.0, 70.0),
            ],
        )

    def test_slanted_short_and_curved_segments_are_no_rules(self) -> None:
        subpaths: list[list[tuple[float, float]] | None] = [
            [(0.0, 0.0), (50.0, 10.0)],
            [(0.0, 0.0), (2.0, 0.0)],
            None,
        ]

        self.assertEqual(stroked_rules(subpaths, None), [])

    def test_rules_are_clipped_to_the_visible_area(self) -> None:
        rules = stroked_rules([[(-50.0, 30.0), (200.0, 30.0)], [(5.0, 0.0), (5.0, 50.0)]], None)
        clipped = stroked_rules(
            [[(-50.0, 30.0), (200.0, 30.0)], [(5.0, 0.0), (5.0, 50.0)]], (0.0, 0.0, 100.0, 40.0)
        )

        self.assertEqual(rules, [(True, 30.0, -50.0, 200.0), (False, 5.0, 0.0, 50.0)])
        self.assertEqual(clipped, [(True, 30.0, 0.0, 100.0), (False, 5.0, 0.0, 40.0)])

    def test_segments_outside_the_clip_box_vanish(self) -> None:
        self.assertIsNone(clipped_segment((-50.0, 30.0), (-10.0, 30.0), (0.0, 0.0, 100.0, 40.0)))


class FilledRuleTests(unittest.TestCase):
    def test_thin_rectangles_are_rules_along_their_center(self) -> None:
        rules = filled_rules(
            [rectangle(86.5, 769.6, 150.4, 771.0), rectangle(85.1, 600.0, 86.5, 700.0)], None
        )

        self.assertEqual(rules, [(True, 770.3, 86.5, 150.4), (False, 85.8, 600.0, 700.0)])

    def test_shaded_cells_and_other_shapes_are_no_rules(self) -> None:
        subpaths: list[list[tuple[float, float]] | None] = [
            rectangle(50.0, 284.0, 343.0, 298.0),
            [(0.0, 0.0), (10.0, 0.0), (5.0, 1.0), (0.0, 0.0)],
        ]

        self.assertEqual(filled_rules(subpaths, None), [])


class JoinRuleTests(unittest.TestCase):
    def test_collinear_pieces_drawn_cell_by_cell_are_joined(self) -> None:
        rules = [
            Rule(True, 71.6, 86.5, 150.4),
            Rule(True, 71.8, 151.8, 276.3),
            Rule(True, 71.7, 277.7, 397.0),
        ]

        self.assertEqual(join_rules(rules), [Rule(True, 71.7, 86.5, 397.0)])

    def test_pieces_separated_by_a_wide_gap_stay_apart(self) -> None:
        rules = [Rule(False, 90.0, 10.0, 50.0), Rule(False, 90.0, 60.0, 90.0)]

        self.assertEqual(join_rules(rules), rules)

    def test_parallel_rules_at_different_positions_stay_apart(self) -> None:
        rules = [Rule(True, 100.0, 0.0, 50.0), Rule(True, 103.0, 0.0, 50.0)]

        self.assertEqual(join_rules(rules), rules)


if __name__ == '__main__':
    unittest.main()
