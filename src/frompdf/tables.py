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

Tables without vertical rules need a top rule and a rule below their header
of the same width. Their columns lie between gutters, which no word of the
body crosses, separating the labels of the header. The body ends at another
rule of the same width, or continues on the next page.

A table ending its page continues at the top of the next page if its header
is repeated there or its columns line up. The repeated header and a caption
marked as continued are dropped. A first row without text in the first column
continues the row before, if the table part on the first page was not closed
by a rule or the text of its cells continues in lower case.
"""

import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from statistics import median

from frompdf.continuations import begins_lowercase
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

# Without vertical rules, a header of at most this many visual lines lies
# between rules at least this long, and gaps between columns are at least
# this wide, relative to the font size of the body.
MAX_HEADER_LINES = 3
MIN_HEADER_RULE_LENGTH = 50.0
MIN_GUTTER_EM = 0.5

# A line starting at least this far, relative to its font size, left of the
# other lines of a cell part starts a paragraph of its own, as with hanging
# indents.
MIN_HANGING_INDENT_EM = 0.5

# Column boundaries of the parts of a table on consecutive pages differ by at
# most this much.
CONTINUED_COLUMN_TOLERANCE = 3.0

# A caption repeated on a following page, as in "Table 1 (continued)".
CONTINUED_CAPTION_PATTERN = re.compile(
    r'\S+(?:\s+\S+)?\s+\(?(?:continued|cont\.|fortsetzung|forts\.|continuación|suite)\)?\.?',
    re.IGNORECASE,
)


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


@dataclass(frozen=True)
class TableFrame:
    """The vertical extent of a table, or of its part on one page."""

    page_no: int
    top: float
    bottom: float


@dataclass
class TableLayout:
    """A recognized table, with its source lines, its frames on each page, and its cells.

    The source lines include those that are not part of any cell, such as a
    repeated header. columns are the column boundaries of the last part. A
    table is closed when a rule ends its last part.
    """

    frames: list[TableFrame]
    lines: list[Line]
    row_count: int
    column_count: int
    header_rows: int
    cells: list[CellLayout]
    columns: list[float] = field(default_factory=list)
    closed: bool = True

    @property
    def page_no(self) -> int:
        """Return the page on which the table starts."""
        return self.frames[0].page_no


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
    # The first row starts at the top of the body, possibly with lines
    # continuing a row from the previous page.
    first_top = min((line.y1 or 0.0 for line in body), default=body_top)
    rows.extend(start for start in starts if start > max(body_top, first_top + BOUNDARY_TOLERANCE))
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


def frame_lines(
    page_lines: Sequence[Line], left: float, right: float, top: float, bottom: float
) -> list[Line] | None:
    """Return the lines within a frame, or None if some cannot belong to table cells.

    Lines overhanging the frame and lines with unpositioned words cannot.
    """
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
    for line in lines:
        assert line.x1 is not None and line.x2 is not None
        if (
            line.x1 < left - FRAME_OVERHANG_TOLERANCE
            or line.x2 > right + FRAME_OVERHANG_TOLERANCE
            or not has_positioned_words(line)
        ):
            return None
    return lines


def split_hanging_paragraphs(part: list[Line]) -> list[list[Line]]:
    """Split a cell part where lines start left of the others, as paragraphs with hanging indents.

    All lines must start at one of two left edges, the first line at the
    outer one, so centered or ragged text stays together.
    """
    first = part[0].x1
    if len(part) < 2 or first is None or any(line.x1 is None for line in part):
        return [part]
    indent = MIN_HANGING_INDENT_EM * (part[0].font_size or 1.0)
    # Most of the other lines continue paragraphs.
    inner = median(line.x1 or 0.0 for line in part[1:])
    if inner - first < indent or any(
        abs((line.x1 or 0.0) - first) > BOUNDARY_TOLERANCE
        and abs((line.x1 or 0.0) - inner) > BOUNDARY_TOLERANCE
        for line in part
    ):
        return [part]
    paragraphs: list[list[Line]] = [[part[0]]]
    for line in part[1:]:
        if abs((line.x1 or 0.0) - first) <= BOUNDARY_TOLERANCE:
            paragraphs.append([])
        paragraphs[-1].append(line)
    return paragraphs


def assemble_table(
    page_no: int,
    lines: list[Line],
    columns: list[float],
    rows: list[float],
    horizontals: Sequence[Rule],
    verticals: Sequence[Rule],
    ruled_rows: bool,
    parts: dict[int, set[float]],
    closed: bool = True,
) -> TableLayout | None:
    """Return a table with grid slots merged into cells and lines split among them.

    Returns None if merged slots do not form rectangles, a word crosses a rule
    between cells, or too few cells have text.
    """
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
        cell.parts = [
            paragraph for part in cell.parts if part for paragraph in split_hanging_paragraphs(part)
        ]

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
        frames=[TableFrame(page_no, rows[0], rows[-1])],
        lines=sorted(lines, key=lambda line: line.line_no_on_page),
        row_count=row_count,
        column_count=len(columns) - 1,
        header_rows=header_row_count(cells, row_count),
        cells=cells,
        columns=columns,
        closed=closed,
    )


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
    lines = frame_lines(page_lines, left, right, top, bottom)
    if not lines:
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
    return assemble_table(page_no, lines, columns, rows, horizontals, verticals, ruled_rows, parts)


def gutters(lines: Sequence[Line], left: float, right: float, min_width: float) -> list[float]:
    """Return the centers of gaps between words that no line has words in."""
    extents = sorted(
        (max(word.x1, left), min(word.x2, right)) for line in lines for word in line.words
    )
    centers: list[float] = []
    if not extents:
        return centers
    covered_to = extents[0][1]
    for start, end in extents[1:]:
        if start - covered_to >= min_width:
            centers.append((start + covered_to) / 2)
        covered_to = max(covered_to, end)
    return centers


def column_gutters(header: Sequence[Line], centers: list[float], min_gap: float) -> list[float]:
    """Return the gutters separating the columns of header labels, or none if they do not fit.

    Labels are runs of header words separated by less than min_gap. Each column
    lies between the gutters just left of consecutive labels. Labels must not
    cross them, and no gutter may lie right of the last label, which would leave
    a column without one. Other gutters, as between coincidentally aligned
    words, are ignored.
    """
    labels: list[list[float]] = []
    for word in sorted((word for line in header for word in line.words), key=lambda word: word.x1):
        if labels and word.x1 - labels[-1][1] < min_gap:
            labels[-1][1] = max(labels[-1][1], word.x2)
        else:
            labels.append([word.x1, word.x2])
    if len(labels) < 2 or any(center > labels[-1][1] for center in centers):
        return []
    chosen: list[float] = []
    for previous, label in zip(labels, labels[1:], strict=False):
        candidates = [
            center for center in centers if previous[1] <= center <= label[0] + BOUNDARY_TOLERANCE
        ]
        if not candidates:
            return []
        chosen.append(max(candidates))
    return chosen


def table_below_header_rule(
    top: float,
    header_bottom: float,
    bottom: float | None,
    left: float,
    right: float,
    page_lines: Sequence[Line],
    page_no: int,
) -> TableLayout | None:
    """Return a table without vertical rules, ruled off above and below its header.

    Without a bottom rule, the table takes up the rest of the page and must
    continue on the next one.
    """
    page_bottom = max((line.y2 or 0.0) for line in page_lines) + 1.0
    lines = frame_lines(page_lines, left, right, top, bottom or page_bottom)
    if not lines:
        return None
    if bottom is None:
        # Nothing else may follow on the page.
        line_ids = {id(line) for line in lines}
        if any(
            (line_center(line) or 0.0) > header_bottom and id(line) not in line_ids
            for line in page_lines
        ):
            return None
    header = [line for line in lines if (line_center(line) or 0.0) < header_bottom]
    body = [line for line in lines if (line_center(line) or 0.0) > header_bottom]
    if not header or len(physical_lines(header)) > MAX_HEADER_LINES or len(body) < 2:
        return None
    font_size = sorted(line.font_size or 1.0 for line in body)[len(body) // 2]
    min_gap = font_size * MIN_GUTTER_EM
    centers = column_gutters(header, gutters(body, left, right, min_gap), min_gap)
    if not centers:
        return None
    columns = [left, *centers, right]
    frame_bottom = bottom if bottom is not None else page_bottom
    verticals = [Rule(False, center, top, frame_bottom) for center in centers]
    rows = line_row_boundaries(top, header_bottom, frame_bottom, lines, columns)
    return assemble_table(
        page_no, lines, columns, rows, [], verticals, False, {}, closed=bottom is not None
    )


def tables_below_header_rules(
    rules: Sequence[Rule], page_lines: Sequence[Line], page_no: int
) -> list[TableLayout]:
    """Return tables without vertical rules, framed by long horizontal rules of the same width."""
    groups: list[list[Rule]] = []
    for rule in sorted(rules, key=lambda rule: (rule.start, rule.end, rule.position)):
        if rule.end - rule.start < MIN_HEADER_RULE_LENGTH:
            continue
        group = next(
            (
                group
                for group in groups
                if abs(group[0].start - rule.start) <= BOUNDARY_TOLERANCE
                and abs(group[0].end - rule.end) <= BOUNDARY_TOLERANCE
            ),
            None,
        )
        if group is None:
            groups.append([rule])
        else:
            group.append(rule)
    tables: list[TableLayout] = []
    for group in groups:
        positions = cluster_positions([rule.position for rule in group])
        left = min(rule.start for rule in group)
        right = max(rule.end for rule in group)
        for index in range(len(positions) - 1):
            bottom = positions[index + 2] if index + 2 < len(positions) else None
            table = table_below_header_rule(
                positions[index], positions[index + 1], bottom, left, right, page_lines, page_no
            )
            if table is not None:
                tables.append(table)
    return tables


def is_continued_caption(line: Line) -> bool:
    """Return whether a line is a caption marked as continued, as in "Table 1 (continued)"."""
    return bool(CONTINUED_CAPTION_PATTERN.fullmatch(line.text))


def header_texts(table: TableLayout) -> list[tuple[int, int, str]]:
    """Return the position and text of each header cell."""
    return [
        (cell.row, cell.column, ' '.join(line.text for line in cell.lines))
        for cell in table.cells
        if cell.row < table.header_rows
    ]


def continues_cell_text(cell: CellLayout) -> bool:
    """Return whether the text of a cell continues text before it, starting in lower case.

    The end of the text before is no evidence, as cells often lack final punctuation.
    """
    return not cell.parts or begins_lowercase(cell.parts[0][0].text)


def append_continuation(
    table: TableLayout, continuation: TableLayout, repeated_header: bool
) -> None:
    """Append the rows of a table continued on the next page, in place.

    A repeated header is dropped. A first row without text in its first column
    continues the last row, if the table was not closed or the text of its
    cells continues.
    """
    skipped = continuation.header_rows if repeated_header else 0
    first_rows = [cell for cell in continuation.cells if cell.row == skipped]
    covering = {
        column: cell
        for cell in table.cells
        if cell.row <= table.row_count - 1 < cell.row + cell.row_span
        for column in range(cell.column, cell.column + cell.column_span)
    }
    if (
        skipped < continuation.row_count
        and all(cell.row_span == 1 for cell in first_rows)
        and any(cell.column == 0 and not cell.parts for cell in first_rows)
        and all(
            covering[cell.column].column == cell.column
            and covering[cell.column].column_span == cell.column_span
            for cell in first_rows
        )
        and (not table.closed or all(continues_cell_text(cell) for cell in first_rows))
    ):
        for cell in first_rows:
            target = covering[cell.column]
            if cell.parts and target.parts:
                target.parts[-1].extend(cell.parts[0])
                target.parts.extend(cell.parts[1:])
            elif cell.parts:
                target.parts = cell.parts
        skipped += 1
    offset = table.row_count - skipped
    for cell in continuation.cells:
        if cell.row >= skipped:
            cell.row += offset
            table.cells.append(cell)
    table.row_count += continuation.row_count - skipped
    table.frames.extend(continuation.frames)
    table.lines.extend(continuation.lines)
    table.columns = continuation.columns
    table.closed = continuation.closed


def join_continued_tables(
    tables: list[TableLayout], lines_by_page: dict[int, list[Line]]
) -> list[TableLayout]:
    """Join tables continuing at the top of the next page, dropping unclosed parts left over.

    A table continues if nothing follows it on its page and nothing but a
    caption marked as continued precedes the next part on the next page, with
    the same number of columns, and either the same header or columns lining up.
    """
    table_line_ids = {id(line) for table in tables for line in table.lines}
    joined: list[TableLayout] = []
    for table in tables:
        previous = joined[-1] if joined else None
        if previous is not None and previous.frames[-1].page_no + 1 == table.page_no:
            last_frame = previous.frames[-1]
            followed = any(
                id(line) not in table_line_ids and (line_center(line) or 0.0) > last_frame.bottom
                for line in lines_by_page.get(last_frame.page_no, [])
            )
            preceding = [
                line
                for line in lines_by_page.get(table.page_no, [])
                if id(line) not in table_line_ids
                and (line_center(line) or 0.0) < table.frames[0].top
            ]
            repeated_header = header_texts(previous) == header_texts(table)
            aligned = len(previous.columns) == len(table.columns) and all(
                abs(first - second) <= CONTINUED_COLUMN_TOLERANCE
                for first, second in zip(previous.columns, table.columns, strict=True)
            )
            if (
                not followed
                and all(is_continued_caption(line) for line in preceding)
                and previous.column_count == table.column_count
                and (repeated_header or aligned)
            ):
                table.lines.extend(preceding)
                append_continuation(previous, table, repeated_header)
                continue
        if previous is not None and not previous.closed:
            joined.pop()
        joined.append(table)
    if joined and not joined[-1].closed:
        joined.pop()
    return joined


def find_tables(lines: Sequence[Line], rules_by_page: dict[int, list[Rule]]) -> list[TableLayout]:
    """Return the tables framed by rules, in page order, joining those continued on later pages."""
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
        candidates: list[TableLayout] = []
        unconnected: list[Rule] = []
        for component in rule_components(rules_by_page[page_no]):
            if all(rule.horizontal for rule in component):
                unconnected.extend(component)
            elif (table := table_from_rules(component, page_lines, page_no)) is not None:
                candidates.append(table)
        candidates.extend(tables_below_header_rules(unconnected, page_lines, page_no))
        for table in candidates:
            if any(id(line) in used for line in table.lines):
                continue
            used.update(id(line) for line in table.lines)
            page_tables.append(table)
        tables.extend(sorted(page_tables, key=lambda table: table.frames[0].top))
    return join_continued_tables(tables, lines_by_page)
