"""Recognize display equations running over several lines.

A display equation is set off from the running text, indented from its
column or ending well short of its right edge. One broken over several lines
starts with a line holding a relation, such as `=` or `≤`, and continues in
lines starting with an operator or relation, as in `+ β₂x₂`, or following a
line ending with one. Such lines form a block of their own, never a block
quote or list item, with a deliberate break after each line.

A fraction's denominator, and the text continuing after the fraction, belong
to the line of its numerator. Single lines are left alone: they cannot be
told from the short last line of a paragraph holding a formula.
"""

from dataclasses import replace
from itertools import pairwise

from frompdf.continuations import PageLayout
from frompdf.line_features import same_physical_line, visibly_different_font_sizes
from frompdf.models import Line
from frompdf.page_context import (
    MIN_FIRST_LINE_INDENT_EM,
    PageContext,
    column_for_line,
    line_is_short,
)

# Relations between the sides of an equation or inequality.
RELATIONS = frozenset('=<>≤≥≠≈∼≃≅≡≜∝∈∉⊂⊆⊃⊇→⇒⇔↦≪≫≺≻⪯⪰')

# The lines of a display equation follow each other at most this far apart,
# relative to their font size, measured from the bottom of one to the top of
# the next, which also covers lines holding fractions.
MAX_LINE_GAP_EM = 1.0

# Binary operators continuing a formula. The hyphen-minus is left out, as it
# also marks list items; formulas set it as a minus sign.
OPERATORS = frozenset('+−±∓×÷')


def logical_lines(line_list: list[Line]) -> list[list[Line]]:
    """Group consecutive pieces of the same line of text, in their order.

    Besides the pieces of a visual line, a fraction's denominator and the
    piece continuing after the fraction belong to the line of its numerator.
    """
    grouped: list[list[Line]] = []
    after_fraction = False
    for line_obj in line_list:
        if grouped and (
            same_physical_line(grouped[-1][-1], line_obj)
            or line_obj.fraction_denominator
            or (after_fraction and same_physical_line(grouped[-1][-2], line_obj))
        ):
            grouped[-1].append(line_obj)
        else:
            grouped.append([line_obj])
        after_fraction = line_obj.fraction_denominator and len(grouped[-1]) > 1
    return grouped


def line_text(pieces: list[Line]) -> str:
    """Return the text of a line's pieces, separated by spaces."""
    return ' '.join(piece.text for piece in pieces).strip()


def is_set_off(pieces: list[Line], context: PageContext) -> bool:
    """Return whether a line is indented from its column or ends well short of it."""
    first = pieces[0]
    lefts = [piece.x1 for piece in pieces if piece.x1 is not None]
    rights = [piece.x2 for piece in pieces if piece.x2 is not None]
    column = column_for_line(first, context)
    if column is None or len(lefts) < len(pieces) or len(rights) < len(pieces):
        return False
    font_size = first.font_size or context.font_size
    whole = replace(first, text=line_text(pieces), x1=min(lefts), x2=max(rights))
    return min(lefts) - column.left >= font_size * MIN_FIRST_LINE_INDENT_EM or line_is_short(
        whole, column, font_size
    )


def starts_equation(text: str) -> bool:
    """Return whether a line's text holds a relation, as the first line of an equation."""
    return any(char in RELATIONS for char in text)


def continues_equation(previous: str, current: str) -> bool:
    """Return whether a line continues a formula broken before or after an operator."""
    symbols = RELATIONS | OPERATORS
    return current[:1] in symbols or previous[-1:] in symbols


def follows_closely(previous: list[Line], current: list[Line], context: PageContext) -> bool:
    """Return whether a line follows the one above closely, in no larger type.

    This keeps a heading or a paragraph after a formula ending in an operator
    or relation apart from it.
    """
    bottoms = [piece.y2 for piece in previous if piece.y2 is not None]
    tops = [piece.y1 for piece in current if piece.y1 is not None]
    if not bottoms or not tops:
        return False
    previous_size = max(piece.font_size or context.font_size for piece in previous)
    current_size = max(piece.font_size or context.font_size for piece in current)
    return min(tops) - max(bottoms) <= previous_size * MAX_LINE_GAP_EM and not (
        current_size > previous_size and visibly_different_font_sizes(current_size, previous_size)
    )


def display_equations(layouts: dict[int, PageLayout]) -> dict[int, int]:
    """Map the IDs of lines of display equations to the ID of their first line.

    An equation needs at least two lines, set off from the running text in the
    same column. Its first line holds a relation, and each further line
    starts with an operator or relation, or follows a line ending with one,
    closely and in no larger type.
    """
    equation_of_line: dict[int, int] = {}
    for layout in layouts.values():
        context = layout.context
        lines = logical_lines(list(layout.lines))
        texts = [line_text(pieces) for pieces in lines]
        set_off = [is_set_off(pieces, context) for pieces in lines]
        runs: list[list[int]] = []
        for index, pieces in enumerate(lines):
            if not set_off[index]:
                continue
            if (
                runs
                and runs[-1][-1] == index - 1
                and column_for_line(lines[index - 1][0], context)
                == column_for_line(pieces[0], context)
                and continues_equation(texts[index - 1], texts[index])
                and follows_closely(lines[index - 1], pieces, context)
            ):
                runs[-1].append(index)
            elif starts_equation(texts[index]):
                runs.append([index])
        for run in runs:
            if len(run) < 2:
                continue
            first = id(lines[run[0]][0])
            equation_of_line.update((id(piece), first) for index in run for piece in lines[index])
    return equation_of_line


def equation_break_ids(line_list: list[Line]) -> set[int]:
    """Return the IDs of the last pieces of all but the last line of an equation."""
    return {id(left[-1]) for left, _ in pairwise(logical_lines(line_list))}
