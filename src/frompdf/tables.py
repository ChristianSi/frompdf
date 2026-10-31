"""Recognize tables drawn with rules and assign their text to cells.

A table needs connected horizontal and vertical rules, with at least one
vertical rule inside its frame separating columns. Columns lie between
vertical rules. Rows lie between horizontal rules, except in tables without
rules between body rows, such as booktabs-style tables with column rules.
There, a header ruled off below forms one row, and each body line with text in
the first column starts another.

A horizontal rule crossing only some columns separates rows where it lines up
in all columns that are subdivided within the same row group. Elsewhere, as
in independently subdivided cells, it only separates parts of a cell's text.
Cells span rows or columns where rules between them are missing.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field, replace

from frompdf.models import Line, Word
from frompdf.rules import Rule

# Rules this close to each other touch, and boundaries this close coincide.
RULE_TOUCH_TOLERANCE = 2.0
BOUNDARY_TOLERANCE = 2.0

# A horizontal rule bounds a column when it covers at least this share of its width.
MIN_COLUMN_COVERAGE = 0.6

# Text may overhang the frame of a table by this much.
FRAME_OVERHANG_TOLERANCE = 3.0

# A word may cross a rule separating two cells by this much, as with italic overhangs.
WORD_CROSSING_TOLERANCE = 1.0

# A column where at least this many lines, and most of them, have this many
# words and fill this share of its width holds running text.
RUNNING_TEXT_MIN_LINES = 5
RUNNING_TEXT_MIN_WORDS = 6
RUNNING_TEXT_MIN_WIDTH_SHARE = 0.85

# A table needs this many cells with text, in at least two rows with text in
# two cells each, which rules out framed figures and boxed text.
MIN_FILLED_CELLS = 4


@dataclass
class CellLayout:
    """A table cell and the lines of its text, in parts separated by rules within the cell."""

    row: int
    column: int
    row_span: int = 1
    column_span: int = 1
    parts: list[list[Line]] = field(default_factory=list)

    @property
    def lines(self) -> list[Line]:
        """Return the lines of all parts."""
        return [line for part in self.parts for line in part]


@dataclass
class TableLayout:
    """A recognized table, with its source lines, the extent of its frame, and its cells."""

    page_no: int
    top: float
    bottom: float
    lines: list[Line]
    row_count: int
    column_count: int
    header_rows: int
    cells: list[CellLayout]


def touches(horizontal: Rule, vertical: Rule) -> bool:
    """Return whether a horizontal and a vertical rule cross or touch."""
    return (
        horizontal.start - RULE_TOUCH_TOLERANCE
        <= vertical.position
        <= horizontal.end + RULE_TOUCH_TOLERANCE
        and vertical.start - RULE_TOUCH_TOLERANCE
        <= horizontal.position
        <= vertical.end + RULE_TOUCH_TOLERANCE
    )


def rule_components(rules: Sequence[Rule]) -> list[list[Rule]]:
    """Return groups of rules connected by crossing or touching each other."""
    parents = list(range(len(rules)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    for index, rule in enumerate(rules):
        if not rule.horizontal:
            continue
        for other_index, other in enumerate(rules):
            if not other.horizontal and touches(rule, other):
                parents[find(index)] = find(other_index)
    components: dict[int, list[Rule]] = defaultdict(list)
    for index, rule in enumerate(rules):
        components[find(index)].append(rule)
    return list(components.values())


def cluster_positions(positions: Sequence[float]) -> list[float]:
    """Return the averages of positions lying within the boundary tolerance of each other."""
    clusters: list[list[float]] = []
    for position in sorted(positions):
        if clusters and position - clusters[-1][-1] <= BOUNDARY_TOLERANCE:
            clusters[-1].append(position)
        else:
            clusters.append([position])
    return [sum(cluster) / len(cluster) for cluster in clusters]


def covers_column(rules: Sequence[Rule], position: float, left: float, right: float) -> bool:
    """Return whether horizontal rules at a position bound a column between left and right."""
    covered = sum(
        max(0.0, min(rule.end, right) - max(rule.start, left))
        for rule in rules
        if abs(rule.position - position) <= BOUNDARY_TOLERANCE
    )
    return covered >= (right - left) * MIN_COLUMN_COVERAGE


def separates_at(rules: Sequence[Rule], position: float, y: float) -> bool:
    """Return whether a vertical rule at a position crosses height y."""
    return any(
        abs(rule.position - position) <= BOUNDARY_TOLERANCE and rule.start <= y <= rule.end
        for rule in rules
    )


def line_center(line: Line) -> float | None:
    """Return the vertical center of a line."""
    if line.y1 is None or line.y2 is None:
        return None
    return (line.y1 + line.y2) / 2


def has_positioned_words(line: Line) -> bool:
    """Return whether all visible characters of a line belong to words with known positions."""
    return sum(word.end - word.start for word in line.words) == sum(
        not char.isspace() for char in line.text
    )


def word_column(word: Word, columns: Sequence[float]) -> int:
    """Return the index of the column containing a word's center."""
    center = (word.x1 + word.x2) / 2
    for index in range(len(columns) - 2, 0, -1):
        if center >= columns[index]:
            return index
    return 0


def physical_lines(lines: Sequence[Line]) -> list[list[Line]]:
    """Group lines whose vertical centers lie close together into visual lines, top to bottom."""
    groups: list[list[Line]] = []
    for line in sorted(lines, key=lambda line: line_center(line) or 0.0):
        center = line_center(line) or 0.0
        size = line.font_size or 1.0
        if groups and center - (line_center(groups[-1][-1]) or 0.0) <= size * 0.3:
            groups[-1].append(line)
        else:
            groups.append([line])
    return groups


def ruled_row_boundaries(
    boundaries: list[float], columns: list[float], horizontals: Sequence[Rule]
) -> tuple[list[float], dict[int, set[float]]]:
    """Return the boundaries separating rows, and those separating parts of each column's cells.

    The outermost boundaries frame the table. Boundaries bounding all columns
    separate rows, as do those bounding all columns that are subdivided at all
    between the same complete boundaries.
    """
    column_count = len(columns) - 1

    def covered(position: float, column: int) -> bool:
        return covers_column(horizontals, position, columns[column], columns[column + 1])

    complete = [
        position
        for index, position in enumerate(boundaries)
        if index in (0, len(boundaries) - 1)
        or all(covered(position, column) for column in range(column_count))
    ]
    rows = list(complete)
    parts: dict[int, set[float]] = defaultdict(set)
    for top, bottom in zip(complete, complete[1:], strict=False):
        partial = [position for position in boundaries if top < position < bottom]
        subdivided = [
            column
            for column in range(column_count)
            if any(covered(position, column) for position in partial)
        ]
        for position in partial:
            if all(covered(position, column) for column in subdivided):
                rows.append(position)
            else:
                for column in subdivided:
                    if covered(position, column):
                        parts[column].add(position)
    return sorted(rows), parts


def line_row_boundaries(
    top: float,
    header_bottom: float | None,
    bottom: float,
    lines: Sequence[Line],
    columns: list[float],
) -> list[float]:
    """Return row boundaries for a table without rules between its body rows.

    A header ruled off below forms one row. In the body, each visual line with
    text in the first column starts a row; other lines continue the cells above.
    """
    rows = [top] if header_bottom is None else [top, header_bottom]
    body_top = rows[-1]
    body = [line for line in lines if (line_center(line) or 0.0) > body_top]
    starts = [
        min(line.y1 or 0.0 for line in visual_line)
        for visual_line in physical_lines(body)
        if any(word_column(word, columns) == 0 for line in visual_line for word in line.words)
    ]
    rows.extend(start for start in starts[1:] if start > body_top)
    rows.append(bottom)
    return rows


def looks_like_running_text(lines: Sequence[Line], columns: Sequence[float]) -> bool:
    """Return whether a column is mostly filled with long lines, as in paragraphs.

    Columns of text separated by a rule, or a framed text box, are no tables,
    though each line could otherwise read as a row of its own.
    """
    for left, right in zip(columns, columns[1:], strict=False):
        pieces = [
            [word for word in line.words if left <= (word.x1 + word.x2) / 2 < right]
            for line in lines
        ]
        pieces = [words for words in pieces if words]
        long_pieces = sum(
            len(words) >= RUNNING_TEXT_MIN_WORDS
            and words[-1].x2 - words[0].x1 >= (right - left) * RUNNING_TEXT_MIN_WIDTH_SHARE
            for words in pieces
        )
        if long_pieces >= RUNNING_TEXT_MIN_LINES and long_pieces * 2 > len(pieces):
            return True
    return False


def row_index(center: float, rows: Sequence[float]) -> int | None:
    """Return the index of the row between boundaries containing a height."""
    for index, (top, bottom) in enumerate(zip(rows, rows[1:], strict=False)):
        if top <= center < bottom:
            return index
    return None


def is_bold_text(lines: Sequence[Line]) -> bool:
    """Return whether all visible characters of lines are bold."""
    for line in lines:
        bold = {
            index
            for run in line.ranges
            if run.kind == 'bold'
            for index in range(run.start, run.end)
        }
        if any(not char.isspace() and index not in bold for index, char in enumerate(line.text)):
            return False
    return True


def header_row_count(cells: Sequence[CellLayout], row_count: int) -> int:
    """Return the number of header rows.

    Below a header row with a cell spanning columns, a row with only bold text
    belongs to the header as well, as for the labels of the spanned columns.
    """
    count = 1
    while count < row_count - 1:
        spanning = any(cell.row == count - 1 and cell.column_span > 1 for cell in cells)
        row_cells = [cell for cell in cells if cell.row == count and cell.lines]
        if not spanning or not row_cells or not all(is_bold_text(cell.lines) for cell in row_cells):
            break
        count += 1
    return count


def merge_slots(
    rows: list[float],
    columns: list[float],
    horizontals: Sequence[Rule],
    verticals: Sequence[Rule],
    ruled_rows: bool,
    row_centers: Sequence[float],
) -> list[CellLayout] | None:
    """Return the cells formed by merging grid slots not separated by rules.

    Returns None if merged slots do not form rectangles.
    """
    row_count = len(rows) - 1
    column_count = len(columns) - 1
    parents = {
        (row, column): (row, column) for row in range(row_count) for column in range(column_count)
    }

    def find(slot: tuple[int, int]) -> tuple[int, int]:
        while parents[slot] != slot:
            slot = parents[slot]
        return slot

    def union(first: tuple[int, int], second: tuple[int, int]) -> None:
        first_root, second_root = find(first), find(second)
        if first_root != second_root:
            parents[max(first_root, second_root)] = min(first_root, second_root)

    for row in range(row_count):
        for column in range(column_count):
            if column + 1 < column_count and not separates_at(
                verticals, columns[column + 1], row_centers[row]
            ):
                union((row, column), (row, column + 1))
            if (
                ruled_rows
                and row + 1 < row_count
                and not covers_column(
                    horizontals, rows[row + 1], columns[column], columns[column + 1]
                )
            ):
                union((row, column), (row + 1, column))

    groups: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    for slot in parents:
        groups[find(slot)].append(slot)
    cells: list[CellLayout] = []
    for slots in groups.values():
        top = min(row for row, _ in slots)
        left = min(column for _, column in slots)
        row_span = max(row for row, _ in slots) - top + 1
        column_span = max(column for _, column in slots) - left + 1
        if row_span * column_span != len(slots):
            return None
        cells.append(CellLayout(top, left, row_span, column_span))
    return sorted(cells, key=lambda cell: (cell.row, cell.column))


def split_line(
    line: Line, columns: Sequence[float], cell_of: dict[int, CellLayout], verticals: Sequence[Rule]
) -> list[tuple[CellLayout, Line]] | None:
    """Split a line into the pieces belonging to each cell, in text order.

    cell_of maps column indices of the line's row to their cells. Returns None
    if a word crosses a rule separating two cells.
    """
    center = line_center(line) or 0.0
    pieces: list[tuple[CellLayout, list[Word]]] = []
    for word in line.words:
        column = word_column(word, columns)
        cell = cell_of[column]
        for boundary in range(1, len(columns) - 1):
            position = columns[boundary]
            if (
                cell_of[boundary - 1] is not cell_of[boundary]
                and word.x1 < position - WORD_CROSSING_TOLERANCE
                and word.x2 > position + WORD_CROSSING_TOLERANCE
                and separates_at(verticals, position, center)
            ):
                return None
        if pieces and pieces[-1][0] is cell:
            pieces[-1][1].append(word)
        else:
            pieces.append((cell, [word]))
    result: list[tuple[CellLayout, Line]] = []
    for cell, words in pieces:
        start, end = words[0].start, words[-1].end
        text = line.text[start:end]
        result.append(
            (
                cell,
                replace(
                    line,
                    text=text,
                    x1=min(word.x1 for word in words),
                    x2=max(word.x2 for word in words),
                    ranges=tuple(
                        replace(
                            run, start=max(run.start, start) - start, end=min(run.end, end) - start
                        )
                        for run in line.ranges
                        if run.start < end and run.end > start
                    ),
                    space_before=False,
                    space_after=False,
                    fraction_denominator=False,
                    second_word_x1=None,
                    words=tuple(
                        Word(word.start - start, word.end - start, word.x1, word.x2)
                        for word in words
                    ),
                ),
            )
        )
    return result


def table_from_rules(
    component: Sequence[Rule], page_lines: Sequence[Line], page_no: int
) -> TableLayout | None:
    """Return the table framed by a group of connected rules, if they frame one."""
    horizontals = [rule for rule in component if rule.horizontal]
    verticals = [rule for rule in component if not rule.horizontal]
    if not verticals or len({round(rule.position) for rule in horizontals}) < 2:
        return None
    left = min([rule.start for rule in horizontals] + [rule.position for rule in verticals])
    right = max([rule.end for rule in horizontals] + [rule.position for rule in verticals])
    top = min([rule.position for rule in horizontals] + [rule.start for rule in verticals])
    bottom = max([rule.position for rule in horizontals] + [rule.end for rule in verticals])
    inner_columns = [
        position
        for position in cluster_positions([rule.position for rule in verticals])
        if left + BOUNDARY_TOLERANCE < position < right - BOUNDARY_TOLERANCE
    ]
    if not inner_columns:
        return None
    columns = [left, *inner_columns, right]

    lines = [
        line
        for line in page_lines
        if (center := line_center(line)) is not None
        and top < center < bottom
        and line.x1 is not None
        and line.x2 is not None
        and line.x2 > left
        and line.x1 < right
    ]
    if not lines:
        return None
    for line in lines:
        assert line.x1 is not None and line.x2 is not None
        if (
            line.x1 < left - FRAME_OVERHANG_TOLERANCE
            or line.x2 > right + FRAME_OVERHANG_TOLERANCE
            or not has_positioned_words(line)
        ):
            return None

    boundaries = [
        top,
        *(
            position
            for position in cluster_positions([rule.position for rule in horizontals])
            if top + BOUNDARY_TOLERANCE < position < bottom - BOUNDARY_TOLERANCE
        ),
        bottom,
    ]
    # Rules within the body separate rows. Without them, at most the header
    # is ruled off, and lines tell the rows.
    ruled_rows = len(boundaries) > 3
    parts: dict[int, set[float]] = {}
    if ruled_rows:
        rows, parts = ruled_row_boundaries(boundaries, columns, horizontals)
    elif looks_like_running_text(lines, columns):
        return None
    else:
        header_bottom = boundaries[1] if len(boundaries) == 3 else None
        rows = line_row_boundaries(top, header_bottom, bottom, lines, columns)
    if len(rows) < 3:
        return None

    row_lines: dict[int, list[Line]] = defaultdict(list)
    for line in lines:
        index = row_index(line_center(line) or 0.0, rows)
        if index is None:
            return None
        row_lines[index].append(line)
    row_centers = [
        sum(line_center(line) or 0.0 for line in row_lines[row]) / len(row_lines[row])
        if row_lines[row] and not ruled_rows
        else (rows[row] + rows[row + 1]) / 2
        for row in range(len(rows) - 1)
    ]
    cells = merge_slots(rows, columns, horizontals, verticals, ruled_rows, row_centers)
    if cells is None:
        return None
    cell_at = {
        (row, column): cell
        for cell in cells
        for row in range(cell.row, cell.row + cell.row_span)
        for column in range(cell.column, cell.column + cell.column_span)
    }

    pieces: dict[int, list[Line]] = defaultdict(list)
    for row, row_line_list in row_lines.items():
        cell_of = {column: cell_at[(row, column)] for column in range(len(columns) - 1)}
        for line in row_line_list:
            split = split_line(line, columns, cell_of, verticals)
            if split is None:
                return None
            for cell, piece in split:
                pieces[id(cell)].append(piece)
    for cell in cells:
        cell_lines = sorted(
            pieces[id(cell)], key=lambda line: (line_center(line) or 0.0, line.x1 or 0.0)
        )
        separators = sorted(
            {
                position
                for column in range(cell.column, cell.column + cell.column_span)
                for position in parts.get(column, ())
            }
        )
        for line in cell_lines:
            part = sum((line_center(line) or 0.0) > position for position in separators)
            while len(cell.parts) <= part:
                cell.parts.append([])
            cell.parts[part].append(line)
        cell.parts = [part for part in cell.parts if part]

    filled_rows: defaultdict[int, int] = defaultdict(int)
    for cell in cells:
        if cell.parts:
            filled_rows[cell.row] += 1
    if (
        sum(filled_rows.values()) < MIN_FILLED_CELLS
        or sum(count >= 2 for count in filled_rows.values()) < 2
    ):
        return None

    row_count = len(rows) - 1
    return TableLayout(
        page_no=page_no,
        top=top,
        bottom=bottom,
        lines=sorted(lines, key=lambda line: line.line_no_on_page),
        row_count=row_count,
        column_count=len(columns) - 1,
        header_rows=header_row_count(cells, row_count),
        cells=cells,
    )


def find_tables(lines: Sequence[Line], rules_by_page: dict[int, list[Rule]]) -> list[TableLayout]:
    """Return the tables framed by rules, in page order."""
    lines_by_page: dict[int, list[Line]] = defaultdict(list)
    for line in lines:
        lines_by_page[line.page_no].append(line)
    tables: list[TableLayout] = []
    for page_no in sorted(rules_by_page):
        page_lines = lines_by_page.get(page_no, [])
        if not page_lines:
            continue
        used: set[int] = set()
        page_tables: list[TableLayout] = []
        for component in rule_components(rules_by_page[page_no]):
            table = table_from_rules(component, page_lines, page_no)
            if table is None or any(id(line) in used for line in table.lines):
                continue
            used.update(id(line) for line in table.lines)
            page_tables.append(table)
        tables.extend(sorted(page_tables, key=lambda table: table.lines[0].line_no_on_page))
    return tables
