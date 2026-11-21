import unittest

from frompdf.blocks import lines_to_markdown_blocks
from frompdf.captions import (
    FIGURE_LABEL_PATTERN,
    TABLE_LABEL_PATTERN,
    continues_caption,
    find_table_captions,
    is_table_caption_start,
)
from frompdf.models import Caption, InlineRange, Line, PageNumber, Paragraph, Table
from frompdf.tables import CellLayout, TableFrame, TableLayout

BODY_TEXT = 'ordinary body text filling the whole column width'


def line(
    text: str,
    x1: float,
    y1: float,
    x2: float,
    *,
    font_size: float = 10.0,
    page_no: int = 1,
    bold: bool = False,
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
        y2=y1 + font_size,
        rel_x=None,
        rel_y=None,
        avg_weight=400.0,
        ranges=(InlineRange(0, len(text), 'bold'),) if bold else (),
    )


def body(top: float, count: int, *, page_no: int = 1) -> list[Line]:
    """Build full lines of body text from top, 12 points apart."""
    return [
        line(BODY_TEXT, 40.0, top + 12.0 * index, 300.0, page_no=page_no) for index in range(count)
    ]


def elsewhere() -> list[Line]:
    """Build body text on another page, which sets the body size of the document."""
    return body(100.0, 10, page_no=2)


def table(top: float, bottom: float, left: float = 100.0, right: float = 240.0) -> TableLayout:
    """Build a one-cell table with a line of text spanning its width."""
    cell_line = line('cell', left, top + 2.0, right, font_size=9.0)
    return TableLayout(
        [TableFrame(1, top, bottom)], [cell_line], 1, 1, 0, [CellLayout(0, 0, parts=[[cell_line]])]
    )


def texts(lines: list[Line]) -> list[str]:
    return [line_obj.text for line_obj in lines]


class LabelPatternTests(unittest.TestCase):
    def test_table_labels_are_recognized_in_all_languages_of_figure_labels(self) -> None:
        for text in [
            'Table 1. Results',
            'TABLE IV',
            'Tables 2 and 3',
            'Tableau 2 : Résultats',
            'Tab. 3 Ergebnisse',
            'Tabelle 1: Ergebnisse',
            'TABELLE 2',
            'Tabla 2. Resultados',
            'Cuadro 3. Resultados',
            'Tabela 4 – Resultados',
            'Quadro 5 Resultados',
            '表 3 結果',
            '表１．結果',
            '第2表 結果',
        ]:
            with self.subTest(text=text):
                self.assertIsNotNone(TABLE_LABEL_PATTERN.match(text))
                self.assertIsNone(FIGURE_LABEL_PATTERN.match(text))

    def test_words_starting_like_table_labels_are_none(self) -> None:
        for text in ['Tablet 3', 'Table of contents', 'Tabelle', 'TABLE', '表示 3', 'Fig. 3']:
            with self.subTest(text=text):
                self.assertIsNone(TABLE_LABEL_PATTERN.match(text))


class TableCaptionStartTests(unittest.TestCase):
    def test_label_at_body_size_without_emphasis_needs_a_separator(self) -> None:
        for text, expected in [
            ('Table 3 shows the results of both rounds.', False),
            ('Tables 2, 3, and 4 summarize the results.', False),
            ('表1に示す結果', False),
            ('Table 3: Results of both rounds', True),
            ('Table 3. Results of both rounds', True),
            ('TABLE IV', True),
            ('Tabelle 2 – Ergebnisse', True),
            ('表1　結果', True),
        ]:
            with self.subTest(text=text):
                self.assertEqual(
                    is_table_caption_start(line(text, 40.0, 100.0, 300.0), 10.0), expected
                )

    def test_label_in_bold_or_small_type_needs_no_separator(self) -> None:
        self.assertTrue(
            is_table_caption_start(line('Table 1 Results', 40.0, 100.0, 300.0, bold=True), 10.0)
        )
        self.assertTrue(
            is_table_caption_start(
                line('Tabla 1 Resultados', 40.0, 100.0, 300.0, font_size=8.0), 10.0
            )
        )

    def test_other_text_is_no_table_caption(self) -> None:
        self.assertFalse(
            is_table_caption_start(line('Results', 40.0, 100.0, 300.0, font_size=8.0), 10.0)
        )
        self.assertFalse(
            is_table_caption_start(line('Fig. 1 Results', 40.0, 100.0, 300.0, font_size=8.0), 10.0)
        )


class CaptionContinuationTests(unittest.TestCase):
    def test_text_beside_the_last_line_continues_only_to_its_right(self) -> None:
        last = line('neighbors on seedling survival in 6 1-ha plots.', 302.0, 529.4, 450.0)
        right = line('continued', 455.0, 529.4, 500.0)
        # A caption in the other column, starting slightly higher.
        left = line('Table 2. Parameter estimates', 57.0, 523.4, 284.0)

        self.assertTrue(continues_caption([last], right))
        self.assertFalse(continues_caption([last], left))

    def test_line_below_may_overlap_slightly_with_tight_leading(self) -> None:
        first = line(
            'Fig. 1 Dynamics in the different phases of the sample, as', 44.0, 709.3, 552.0
        )
        second = line('measured at four temperatures.', 44.0, 719.1, 300.0)

        self.assertTrue(continues_caption([first], second))

    def test_label_of_another_caption_after_a_sentence_ends_the_caption(self) -> None:
        first = line(
            'Figure 1. Distribution of effects in all of the six plots.', 40.0, 100.0, 300.0
        )
        label = line('Table 2. Parameter estimates and significance', 40.0, 111.0, 300.0)
        mention = line('Table 2 lists the parameters estimated for them.', 40.0, 111.0, 300.0)
        within = line('Figure 1. Distribution of effects shown as in', 40.0, 100.0, 300.0)

        self.assertFalse(continues_caption([first], label))
        self.assertTrue(continues_caption([within], mention))


class TableCaptionTests(unittest.TestCase):
    def test_caption_above_may_start_left_of_a_centered_table(self) -> None:
        tables = [table(130.0, 200.0)]
        caption = [
            line('Table 1', 40.0, 100.0, 70.0, bold=True),
            line('Statistics of the test datasets in each round.', 40.0, 112.0, 280.0),
        ]

        find_table_captions([*caption, *tables[0].lines, *elsewhere()], tables)

        self.assertEqual(texts(tables[0].caption_lines), texts(caption))
        self.assertTrue(tables[0].caption_above)

    def test_caption_below_a_table(self) -> None:
        tables = [table(100.0, 170.0)]
        caption = [line('Tabelle 1: Ergebnisse beider Runden', 40.0, 180.0, 280.0)]

        find_table_captions([*tables[0].lines, *caption, *elsewhere()], tables)

        self.assertEqual(texts(tables[0].caption_lines), texts(caption))
        self.assertFalse(tables[0].caption_above)

    def test_sentences_mentioning_a_table_are_no_captions(self) -> None:
        tables = [table(130.0, 200.0)]
        above = [line('Table 1 shows the statistics of the test datasets.', 40.0, 112.0, 300.0)]
        below = [line('Table 1 also shows that the second round was harder.', 40.0, 210.0, 300.0)]

        find_table_captions([*above, *tables[0].lines, *below, *elsewhere()], tables)

        self.assertEqual(tables[0].caption_lines, [])

    def test_tables_place_their_captions_alike(self) -> None:
        # Each caption below a table also lies right above the next one.
        tables = [table(100.0, 150.0), table(180.0, 230.0)]
        captions = [
            line('Table 1: First results', 40.0, 160.0, 280.0),
            line('Table 2: Second results', 40.0, 240.0, 280.0),
        ]
        lines = [*tables[0].lines, captions[0], *tables[1].lines, captions[1], *elsewhere()]

        find_table_captions(lines, tables)

        self.assertEqual(
            [texts(table.caption_lines) for table in tables],
            [['Table 1: First results'], ['Table 2: Second results']],
        )

    def test_used_lines_are_no_captions(self) -> None:
        tables = [table(130.0, 200.0)]
        caption = line('Table 1: Statistics', 40.0, 112.0, 280.0)

        find_table_captions([caption, *tables[0].lines, *elsewhere()], tables, {id(caption)})

        self.assertEqual(tables[0].caption_lines, [])


class CaptionBlockTests(unittest.TestCase):
    def blocks_with(self, caption: list[Line], layout: TableLayout) -> list[type]:
        layout.caption_lines = caption
        layout.caption_above = caption[0].y1 is not None and caption[0].y1 < layout.frames[0].top
        lines = sorted(
            [*body(40.0, 4), *caption, *layout.lines, *body(260.0, 4)],
            key=lambda line_obj: line_obj.y1 or 0.0,
        )
        blocks = lines_to_markdown_blocks(lines, {1: PageNumber(1, None)}, tables=[layout])
        return [type(block) for block in blocks]

    def test_table_caption_precedes_or_follows_its_table(self) -> None:
        above = [line('Table 1: Results', 40.0, 110.0, 200.0)]
        below = [line('Table 1: Results', 40.0, 210.0, 200.0)]

        self.assertEqual(
            self.blocks_with(above, table(130.0, 200.0)), [Paragraph, Caption, Table, Paragraph]
        )
        self.assertEqual(
            self.blocks_with(below, table(130.0, 200.0)), [Paragraph, Table, Caption, Paragraph]
        )

    def test_caption_in_large_type_is_no_heading(self) -> None:
        caption = [line('Table 1: Results', 40.0, 105.0, 200.0, font_size=14.0)]

        self.assertEqual(
            self.blocks_with(caption, table(130.0, 200.0)), [Paragraph, Caption, Table, Paragraph]
        )


if __name__ == '__main__':
    unittest.main()
