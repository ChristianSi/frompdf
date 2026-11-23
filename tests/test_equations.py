import unittest
from dataclasses import replace

from frompdf.blocks import lines_to_markdown_blocks
from frompdf.continuations import build_page_layouts
from frompdf.equations import display_equations, logical_lines
from frompdf.models import HARD_LINE_BREAK, BlockQuote, Line, PageNumber, Paragraph

# Synthetic text is set in 10-point type, 5 points per character, in a column
# from 100 to 400 with lines 12 points apart.
CHAR_WIDTH = 5.0
LEFT = 100.0
PROSE = 'the quick brown fox jumps over the lazy dog and runs on'


def line(text: str, y: float, x: float = LEFT, size: float = 10.0, line_no: int = 0) -> Line:
    return Line(
        text=text,
        page_no=1,
        block_no=line_no,
        line_no_on_page=line_no,
        font_size=size,
        x1=x,
        y1=y,
        x2=x + len(text) * CHAR_WIDTH * size / 10,
        y2=y + size,
        rel_x=None,
        rel_y=None,
        avg_weight=400.0,
    )


# The top of the first line between the prose.
TOP = 160.0


def page(middle: list[Line]) -> list[Line]:
    """Return lines of prose filling the column, the given lines, and more prose below."""
    lines = [line(PROSE[:60], 100 + 12 * index) for index in range(5)]
    lines += middle
    bottom = max(item.y1 or 0.0 for item in middle) + 14
    lines += [line(PROSE[:60], bottom + 12 * index) for index in range(5)]
    return [
        replace(item, line_no_on_page=index, block_no=index) for index, item in enumerate(lines)
    ]


def equation_texts(lines: list[Line]) -> list[list[str]]:
    """Return the texts of the lines of each display equation found."""
    equations: dict[int, list[str]] = {}
    by_id = {id(item): item for item in lines}
    for line_id, first in display_equations(build_page_layouts(lines)).items():
        equations.setdefault(first, []).append(by_id[line_id].text)
    return list(equations.values())


EQUATION = [line('f(x) = a', TOP), line('+ b + c', TOP + 12, 140), line('+ d', TOP + 24, 140)]


class DisplayEquationTests(unittest.TestCase):
    def test_lines_continuing_with_operators_form_one_equation(self) -> None:
        self.assertEqual(equation_texts(page(EQUATION)), [['f(x) = a', '+ b + c', '+ d']])

    def test_line_after_a_line_ending_with_a_relation_continues_it(self) -> None:
        lines = page([line('f(x) =', TOP, 140), line('a + b', TOP + 12, 160)])

        self.assertEqual(equation_texts(lines), [['f(x) =', 'a + b']])

    def test_single_set_off_formula_is_left_alone(self) -> None:
        self.assertEqual(equation_texts(page([line('f(x) = a', TOP, 140)])), [])

    def test_prose_lines_starting_with_an_operator_are_no_equation(self) -> None:
        lines = page(
            [
                line('a temperature of ' + PROSE[:41] + ' =', TOP),
                line('+ 15 degrees, ' + PROSE[:46], TOP + 12),
            ]
        )

        self.assertEqual(equation_texts(lines), [])

    def test_larger_or_distant_line_after_a_trailing_relation_is_no_continuation(self) -> None:
        heading = line('Results', TOP + 13, size=12.0)
        distant = line('a + b', TOP + 30, 160)
        for following in (heading, distant):
            with self.subTest(following=following.text):
                lines = page([line('f(x) =', TOP, 140), following])
                self.assertEqual(equation_texts(lines), [])

    def test_denominator_and_text_after_it_join_the_numerator_line(self) -> None:
        numerator = line('log(p', 100, 100)
        denominator = replace(line('1 − p', 106, 115), fraction_denominator=True)
        after = line(')= x', 101, 141)
        below = line('+ y', 118, 120)

        self.assertEqual(
            logical_lines([numerator, denominator, after, below]),
            [[numerator, denominator, after], [below]],
        )


class EquationBlockTests(unittest.TestCase):
    def test_equation_forms_one_paragraph_breaking_after_each_line(self) -> None:
        blocks = lines_to_markdown_blocks(page(EQUATION), {1: PageNumber(1, None)})
        equations = [block for block in blocks if block.text.startswith('f(x)')]

        self.assertFalse(any(isinstance(block, BlockQuote) for block in blocks))
        self.assertEqual(len(equations), 1)
        self.assertIsInstance(equations[0], Paragraph)
        self.assertEqual(
            equations[0].text, f'f(x) = a{HARD_LINE_BREAK}\n+ b + c{HARD_LINE_BREAK}\n+ d'
        )


if __name__ == '__main__':
    unittest.main()
