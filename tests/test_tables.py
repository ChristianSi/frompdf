import unittest

from frompdf.blocks import lines_to_markdown_blocks, split_groups_at_tables
from frompdf.models import (
    HARD_LINE_BREAK,
    InlineRange,
    Line,
    PageNumber,
    Paragraph,
    Table,
    Word,
)
from frompdf.rules import Rule
from frompdf.tables import TableFrame, TableLayout, find_tables, split_hanging_paragraphs

# Synthetic text is set in 10-point type, 5 points per character.
CHAR_WIDTH = 5.0


def table_line(
    pieces: list[tuple[float, str]], y: float, line_no: int, bold: bool = False, page: int = 1
) -> Line:
    """Build a line of pieces of text starting at given x positions, such as table cells."""
    texts: list[str] = []
    words: list[Word] = []
    offset = 0
    for x, piece in pieces:
        if texts:
            offset += 1
        for index, word in enumerate(piece.split(' ')):
            start = offset + len(' '.join(piece.split(' ')[:index])) + (1 if index else 0)
            word_x = x + (start - offset) * CHAR_WIDTH
            words.append(Word(start, start + len(word), word_x, word_x + len(word) * CHAR_WIDTH))
        texts.append(piece)
        offset += len(piece)
    text = ' '.join(texts)
    return Line(
        text=text,
        page_no=page,
        block_no=1,
        line_no_on_page=line_no,
        font_size=10.0,
        x1=words[0].x1,
        y1=y,
        x2=words[-1].x2,
        y2=y + 8.0,
        rel_x=None,
        rel_y=None,
        avg_weight=400.0,
        ranges=(InlineRange(0, len(text), 'bold'),) if bold else (),
        words=tuple(words),
    )


def grid_rules(columns: list[float], rows: list[float]) -> list[Rule]:
    """Return the rules of a complete grid."""
    return [Rule(True, y, columns[0], columns[-1]) for y in rows] + [
        Rule(False, x, rows[0], rows[-1]) for x in columns
    ]


def cell_texts(table: TableLayout) -> dict[tuple[int, int], list[str]]:
    """Return the text of each cell part, by row and column."""
    return {
        (cell.row, cell.column): [' '.join(line.text for line in part) for part in cell.parts]
        for cell in table.cells
    }


def spans(table: TableLayout) -> dict[tuple[int, int], tuple[int, int]]:
    """Return the row and column spans of cells spanning more than one slot."""
    return {
        (cell.row, cell.column): (cell.row_span, cell.column_span)
        for cell in table.cells
        if (cell.row_span, cell.column_span) != (1, 1)
    }


class RuledGridTests(unittest.TestCase):
    def test_grid_cells_receive_the_pieces_of_lines_crossing_them(self) -> None:
        lines = [
            table_line([(105, 'Name'), (205, 'Value')], 104, 1, bold=True),
            table_line([(105, 'Alpha'), (205, '1.5')], 124, 2),
            table_line([(105, 'Beta'), (205, '2.5')], 144, 3),
        ]
        tables = find_tables(lines, {1: grid_rules([100, 200, 300], [100, 120, 140, 160])})

        self.assertEqual(len(tables), 1)
        table = tables[0]
        self.assertEqual((table.row_count, table.column_count, table.header_rows), (3, 2, 1))
        self.assertEqual(
            cell_texts(table),
            {
                (0, 0): ['Name'],
                (0, 1): ['Value'],
                (1, 0): ['Alpha'],
                (1, 1): ['1.5'],
                (2, 0): ['Beta'],
                (2, 1): ['2.5'],
            },
        )
        self.assertEqual(table.cells[0].lines[0].ranges, (InlineRange(0, 4, 'bold'),))

    def test_rule_missing_in_one_column_makes_its_cell_span_rows(self) -> None:
        lines = [
            table_line([(105, 'Set'), (205, 'Task'), (305, 'F1')], 104, 1),
            table_line([(205, 'CEA'), (305, '0.9')], 124, 2),
            table_line([(105, 'Round 1')], 134, 3),
            table_line([(205, 'CTA'), (305, '0.7')], 144, 4),
        ]
        rules = grid_rules([100, 200, 300, 400], [100, 120, 160])
        rules.append(Rule(True, 140, 200, 400))

        table = find_tables(lines, {1: rules})[0]

        self.assertEqual(table.row_count, 3)
        self.assertEqual(spans(table), {(1, 0): (2, 1)})
        self.assertEqual(cell_texts(table)[(1, 0)], ['Round 1'])
        self.assertEqual(cell_texts(table)[(2, 2)], ['0.7'])

    def test_rules_dividing_columns_independently_separate_parts_of_cells(self) -> None:
        lines = [
            table_line([(105, 'Service'), (205, 'Pros'), (305, 'Cons')], 104, 1),
            table_line([(105, 'Viewer'), (205, '- Simple'), (305, '- Slow')], 124, 2),
            table_line([(205, '- Fast')], 144, 3),
            table_line([(305, '- Manual')], 154, 4),
        ]
        rules = grid_rules([100, 200, 300, 400], [100, 120, 170])
        rules += [Rule(True, 140, 200, 300), Rule(True, 150, 300, 400)]

        table = find_tables(lines, {1: rules})[0]

        self.assertEqual(table.row_count, 2)
        self.assertEqual(spans(table), {})
        self.assertEqual(cell_texts(table)[(1, 1)], ['- Simple', '- Fast'])
        self.assertEqual(cell_texts(table)[(1, 2)], ['- Slow', '- Manual'])

    def test_rules_aligned_across_divided_columns_separate_rows(self) -> None:
        lines = [
            table_line([(105, 'Service'), (205, 'Pros'), (305, 'Cons')], 104, 1),
            table_line([(105, 'Viewer'), (205, '- Simple'), (305, '- Slow')], 124, 2),
            table_line([(205, '- Fast'), (305, '- Manual')], 144, 3),
        ]
        rules = grid_rules([100, 200, 300, 400], [100, 120, 160])
        rules.append(Rule(True, 140, 200, 400))

        table = find_tables(lines, {1: rules})[0]

        self.assertEqual(table.row_count, 3)
        self.assertEqual(spans(table), {(1, 0): (2, 1)})
        self.assertEqual(cell_texts(table)[(2, 1)], ['- Fast'])

    def test_bold_labels_below_spanning_header_cells_extend_the_header(self) -> None:
        lines = [
            table_line([(240, 'System')], 104, 1, bold=True),
            table_line([(105, 'Set'), (205, 'F1'), (305, 'Pr')], 124, 2, bold=True),
            table_line([(105, 'A'), (205, '0.9'), (305, '0.8')], 144, 3),
            table_line([(105, 'B'), (205, '0.7'), (305, '0.6')], 164, 4),
        ]
        rules = grid_rules([100, 200, 300, 400], [100, 120, 140, 160, 180])
        rules = [rule for rule in rules if rule.horizontal or rule.position != 300]
        rules.append(Rule(False, 300, 120, 180))

        table = find_tables(lines, {1: rules})[0]

        self.assertEqual(table.header_rows, 2)
        self.assertEqual(spans(table), {(0, 1): (1, 2)})

    def test_bold_first_row_without_spanning_header_cells_is_the_only_header_row(self) -> None:
        lines = [
            table_line([(105, 'Set'), (205, 'F1')], 104, 1, bold=True),
            table_line([(105, 'A'), (205, '0.9')], 124, 2, bold=True),
            table_line([(105, 'B'), (205, '0.7')], 144, 3),
        ]

        table = find_tables(lines, {1: grid_rules([100, 200, 300], [100, 120, 140, 160])})[0]

        self.assertEqual(table.header_rows, 1)


class LineRowTests(unittest.TestCase):
    def test_lines_starting_in_the_first_column_start_rows_below_a_ruled_header(self) -> None:
        lines = [
            table_line([(105, 'Algorithm'), (205, 'Replicas')], 104, 1),
            table_line([(105, 'OneShot'), (205, '4f + 1')], 124, 2),
            table_line([(105, 'ABA'), (205, '5f + 1')], 136, 3),
            table_line([(205, 'or more')], 148, 4),
            table_line([(105, 'BVC'), (205, '(d + 2)f + 1')], 160, 5),
        ]
        rules = [
            Rule(True, 100, 100, 300),
            Rule(True, 120, 100, 300),
            Rule(True, 175, 100, 300),
            Rule(False, 200, 100, 175),
        ]

        table = find_tables(lines, {1: rules})[0]

        self.assertEqual((table.row_count, table.header_rows), (4, 1))
        self.assertEqual(
            cell_texts(table),
            {
                (0, 0): ['Algorithm'],
                (0, 1): ['Replicas'],
                (1, 0): ['OneShot'],
                (1, 1): ['4f + 1'],
                (2, 0): ['ABA'],
                (2, 1): ['5f + 1 or more'],
                (3, 0): ['BVC'],
                (3, 1): ['(d + 2)f + 1'],
            },
        )

    def test_columns_of_running_text_separated_by_a_rule_are_no_table(self) -> None:
        sentence = 'the quick brown fox jumps over the lazy dog'
        lines = [
            table_line([(100, sentence[:36]), (300, sentence[:36])], 100 + 12 * index, index + 1)
            for index in range(8)
        ]
        rules = [Rule(True, 95, 100, 485), Rule(True, 200, 100, 485), Rule(False, 290, 95, 200)]

        self.assertEqual(find_tables(lines, {1: rules}), [])


class NegativeTests(unittest.TestCase):
    def test_framed_text_without_column_rules_is_no_table(self) -> None:
        lines = [
            table_line([(105, 'Note'), (205, 'text')], 104, 1),
            table_line([(105, 'More'), (205, 'text')], 124, 2),
        ]
        rules = grid_rules([100, 300], [100, 140])

        self.assertEqual(find_tables(lines, {1: rules}), [])

    def test_text_overhanging_the_frame_is_no_table(self) -> None:
        lines = [
            table_line([(105, 'Name'), (205, 'Value')], 104, 1),
            table_line([(105, 'Alpha'), (205, 'a value much too long for its cell')], 124, 2),
            table_line([(105, 'Beta'), (205, '2.5')], 144, 3),
        ]

        tables = find_tables(lines, {1: grid_rules([100, 200, 300], [100, 120, 140, 160])})

        self.assertEqual(tables, [])

    def test_words_crossing_column_rules_are_no_table(self) -> None:
        lines = [
            table_line([(105, 'Name'), (205, 'Value')], 104, 1),
            table_line([(180, 'Crossing'), (235, 'x')], 124, 2),
            table_line([(105, 'Beta'), (205, '2.5')], 144, 3),
        ]

        tables = find_tables(lines, {1: grid_rules([100, 200, 300], [100, 120, 140, 160])})

        self.assertEqual(tables, [])

    def test_grid_with_a_single_filled_row_is_no_table(self) -> None:
        lines = [table_line([(105, 'Panel'), (205, 'Panel')], 104, 1)]

        self.assertEqual(find_tables(lines, {1: grid_rules([100, 200, 300], [100, 120, 140])}), [])


def header_rules(top: float, header_bottom: float, bottom: float | None) -> list[Rule]:
    """Return horizontal rules above and below a header, and optionally below the table."""
    positions = [top, header_bottom] + ([] if bottom is None else [bottom])
    return [Rule(True, position, 100, 400) for position in positions]


def year_rows(page: int, y: float, years: list[str], first_line_no: int = 10) -> list[Line]:
    """Return table rows of a year and two cells of text, ten points apart."""
    return [
        table_line(
            [(105, year), (155, f'Text for {year}'), (305, 'More text')],
            y + 10 * index,
            first_line_no + index,
            page=page,
        )
        for index, year in enumerate(years)
    ]


HEADER = [(105, 'Date'), (155, 'Definition'), (305, 'Origin')]


class TablesWithoutColumnRulesTests(unittest.TestCase):
    def test_gutters_below_a_ruled_header_separate_columns(self) -> None:
        lines = [
            table_line(HEADER, 104, 1),
            *year_rows(1, 124, ['2004', '2005']),
            table_line([(163, 'continued'), (313, 'and more')], 144, 20),
        ]

        table = find_tables(lines, {1: header_rules(100, 118, 160)})[0]

        self.assertEqual((table.row_count, table.column_count), (3, 3))
        self.assertEqual(cell_texts(table)[(2, 1)], ['Text for 2005 continued'])
        self.assertEqual(cell_texts(table)[(2, 2)], ['More text and more'])

    def test_header_label_crossing_a_gutter_is_no_table(self) -> None:
        lines = [
            table_line([(105, 'A title running across the columns')], 104, 1),
            *year_rows(1, 124, ['2004', '2005']),
        ]

        self.assertEqual(find_tables(lines, {1: header_rules(100, 118, 150)}), [])

    def test_column_without_header_label_is_no_table(self) -> None:
        lines = [table_line([(105, 'Date'), (155, 'Definition')], 104, 1)]
        lines += year_rows(1, 124, ['2004', '2005'])

        self.assertEqual(find_tables(lines, {1: header_rules(100, 118, 150)}), [])

    def test_unclosed_table_without_continuation_is_dropped(self) -> None:
        lines = [table_line(HEADER, 104, 1), *year_rows(1, 124, ['2004', '2005'])]

        self.assertEqual(find_tables(lines, {1: header_rules(100, 118, None)}), [])

    def test_hanging_indents_start_paragraphs_within_cells(self) -> None:
        def line(x: float, text: str, y: float) -> Line:
            return table_line([(x, text)], y, 1)

        part = [
            line(250, 'First', 0),
            line(258, 'more', 10),
            line(250, 'Second', 20),
            line(258, 'and', 30),
            line(258, 'more', 40),
        ]
        centered = [line(270, 'Service', 0), line(285, 'of', 10), line(262, 'queries', 20)]

        self.assertEqual(split_hanging_paragraphs(part), [part[:2], part[2:]])
        self.assertEqual(split_hanging_paragraphs(centered), [centered])


class ContinuedTableTests(unittest.TestCase):
    def test_table_continues_with_repeated_header_and_continued_row(self) -> None:
        first_page = [table_line(HEADER, 104, 1), *year_rows(1, 124, ['2004', '2005'])]
        second_page = [
            table_line([(105, 'Table 1 (continued)')], 80, 1, page=2),
            table_line(HEADER, 104, 2, page=2),
            table_line([(163, 'and continued'), (313, 'further')], 124, 3, page=2),
            *year_rows(2, 134, ['2006']),
        ]
        rules = {1: header_rules(100, 118, None), 2: header_rules(100, 118, 150)}

        tables = find_tables(first_page + second_page, rules)

        self.assertEqual(len(tables), 1)
        table = tables[0]
        self.assertEqual([frame.page_no for frame in table.frames], [1, 2])
        self.assertEqual((table.row_count, table.header_rows), (4, 1))
        self.assertEqual(cell_texts(table)[(2, 1)], ['Text for 2005 and continued'])
        self.assertEqual(cell_texts(table)[(3, 0)], ['2006'])
        self.assertIn(second_page[0], table.lines)

    def test_closed_table_continues_with_a_new_row_unless_text_continues(self) -> None:
        def table(first_row: str) -> TableLayout:
            first_page = [table_line(HEADER, 104, 1), *year_rows(1, 124, ['2004', '2005'])]
            second_page = [
                table_line(HEADER, 104, 2, page=2),
                table_line([(155, first_row)], 124, 3, page=2),
                *year_rows(2, 144, ['2006']),
            ]
            rules = {
                1: grid_rules([100, 150, 300, 400], [100, 118, 134, 145]),
                2: grid_rules([100, 150, 300, 400], [100, 118, 135, 155]),
            }
            return find_tables(first_page + second_page, rules)[0]

        new_row = table('- New item')
        continued = table('continued text')

        self.assertEqual(new_row.row_count, 5)
        self.assertEqual(cell_texts(new_row)[(3, 1)], ['- New item'])
        self.assertEqual(continued.row_count, 4)
        self.assertEqual(cell_texts(continued)[(2, 1)], ['Text for 2005 continued text'])

    def test_text_after_a_table_keeps_the_next_page_table_apart(self) -> None:
        first_page = [
            table_line(HEADER, 104, 1),
            *year_rows(1, 124, ['2004', '2005']),
            table_line([(105, 'A paragraph after the table.')], 200, 30),
        ]
        second_page = [table_line(HEADER, 104, 2, page=2), *year_rows(2, 124, ['2006', '2007'])]
        rules = {1: header_rules(100, 118, 150), 2: header_rules(100, 118, 150)}

        tables = find_tables(first_page + second_page, rules)

        self.assertEqual(
            [[frame.page_no for frame in table.frames] for table in tables], [[1], [2]]
        )


class TableBlockTests(unittest.TestCase):
    def test_table_lines_form_a_table_block_between_paragraphs(self) -> None:
        def paragraph_line(text: str, y: float, line_no: int) -> Line:
            return Line(text, 1, 1, line_no, 10.0, 100.0, y, 300.0, y + 8.0, None, None, 400.0)

        rows = [
            table_line([(105, 'Name'), (205, 'Value')], 104, 2),
            table_line([(105, 'Alpha'), (205, 'first,')], 124, 3),
            table_line([(205, 'second')], 134, 4),
            table_line([(105, '(old)')], 143, 5),
            table_line([(105, 'Beta'), (205, '2.5')], 154, 6),
        ]
        # Rules divide the cells of both columns, but not in line with each other.
        rules = grid_rules([100, 200, 300], [100, 120, 152, 170])
        rules += [Rule(True, 132, 200, 300), Rule(True, 141, 100, 200)]
        lines = [paragraph_line('Before.', 80, 1), *rows, paragraph_line('After.', 190, 7)]
        tables = find_tables(lines, {1: rules})

        blocks = lines_to_markdown_blocks(lines, {1: PageNumber(1, None)}, tables=tables)

        self.assertEqual([type(block) for block in blocks], [Paragraph, Table, Paragraph])
        table = blocks[1]
        assert isinstance(table, Table)
        self.assertEqual(
            [cell.text for cell in table.cells],
            [
                'Name',
                'Value',
                f'Alpha{HARD_LINE_BREAK}(old)',
                f'first,{HARD_LINE_BREAK}second',
                'Beta',
                '2.5',
            ],
        )

    def test_text_is_split_only_where_a_table_lies_between_its_lines(self) -> None:
        table = TableLayout(
            frames=[TableFrame(1, 100.0, 150.0)],
            lines=[],
            row_count=2,
            column_count=2,
            header_rows=1,
            cells=[],
        )
        above = table_line([(100, 'Text above')], 80, 1)
        below = table_line([(100, 'text below.')], 160, 2)
        # Text continuing at the top of the next column, beside the table.
        bottom_of_column = table_line([(100, 'Text at the bottom')], 400, 3)
        top_of_next_column = table_line([(320, 'continues.')], 60, 4)

        self.assertEqual(
            split_groups_at_tables(
                [[above, below], [bottom_of_column, top_of_next_column]], [table]
            ),
            [[above], [below], [bottom_of_column, top_of_next_column]],
        )

    def test_table_continued_on_the_next_page_forms_one_block(self) -> None:
        lines = [
            table_line(HEADER, 104, 1),
            *year_rows(1, 124, ['2004', '2005']),
            table_line(HEADER, 104, 1, page=2),
            table_line([(163, 'and so'), (313, 'on')], 124, 2, page=2),
            *year_rows(2, 134, ['2006']),
        ]
        pages = {1: PageNumber(1, None), 2: PageNumber(2, None)}
        tables = find_tables(
            lines, {1: header_rules(100, 118, None), 2: header_rules(100, 118, 150)}
        )

        blocks = lines_to_markdown_blocks(lines, pages, tables=tables)

        self.assertEqual(len(blocks), 1)
        table = blocks[0]
        assert isinstance(table, Table)
        self.assertEqual((table.start_page.raw, table.end_page.raw), (1, 2))
        cell = next(cell for cell in table.cells if (cell.row, cell.column) == (2, 1))
        self.assertEqual(cell.text, 'Text for 2005 and so')
        self.assertEqual(
            [(fragment.text, fragment.page.raw, fragment.separator) for fragment in cell.fragments],
            [('Text for 2005', 1, ''), ('and so', 2, ' ')],
        )


if __name__ == '__main__':
    unittest.main()
