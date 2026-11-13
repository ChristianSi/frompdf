import unittest

from frompdf.blocks import lines_to_markdown_blocks
from frompdf.figures import FigureLayout, find_figures, join_boxes, reading_position
from frompdf.models import Image, InlineRange, Line, PageNumber, Paragraph
from frompdf.rules import Drawing, DrawingBox
from frompdf.tables import TableFrame, TableLayout

BODY_TEXT = 'ordinary body text filling the whole column width'


def line(
    text: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float | None = None,
    *,
    font_size: float = 10.0,
    font_name: str = 'Body-Regular',
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
        y2=y1 + font_size if y2 is None else y2,
        rel_x=None,
        rel_y=None,
        avg_weight=400.0,
        font_name=font_name,
        ranges=(InlineRange(0, len(text), 'bold'),) if bold else (),
    )


def body(top: float, count: int, *, page_no: int = 1) -> list[Line]:
    """Build full lines of body text from top, 12 points apart."""
    return [
        line(BODY_TEXT, 40.0, top + 12.0 * index, 300.0, page_no=page_no) for index in range(count)
    ]


def elsewhere() -> list[Line]:
    """Build body text on another page, which sets the body size of the document."""
    return body(100.0, 8, page_no=2)


def label(text: str, x1: float, y1: float, x2: float, y2: float | None = None) -> Line:
    """Build a label of a plot, set in the font of its figure."""
    return line(text, x1, y1, x2, y2, font_size=8.0, font_name='Figure-Sans')


def plot(box: DrawingBox) -> Drawing:
    """Build the curves of a plot filling a box."""
    return Drawing(box, 'path', detail=20)


def photo(box: DrawingBox, *, lossy: bool = True) -> Drawing:
    """Build an image filling a box at 144 pixels per inch."""
    return Drawing(
        box,
        'image',
        pixel_width=round((box[2] - box[0]) * 2),
        pixel_height=round((box[3] - box[1]) * 2),
        lossy=lossy,
    )


# A plot drawn from (60, 200) to (300, 320), with labels in and around it.
PANEL = (60.0, 200.0, 300.0, 320.0)


def labels() -> list[Line]:
    """Build the labels of the plot: tick values, axis titles, and a legend."""
    return [
        label('100', 82.0, 200.0, 94.0),
        label('0', 90.0, 312.0, 94.0),
        label('Signal (a.u.)', 42.0, 230.0, 50.0, 290.0),
        label('30 mT', 250.0, 210.0, 270.0),
        label('Time (ps)', 180.0, 330.0, 216.0),
    ]


def caption(first: str = 'Fig. 1 A plot of the signal over time, with the field') -> list[Line]:
    """Build a two-line caption in small type below the plot."""
    return [
        line(first, 40.0, 350.0, 300.0, font_size=9.0),
        line('as indicated.', 40.0, 360.0, 100.0, font_size=9.0),
    ]


def texts(lines: list[Line]) -> list[str]:
    return [line_obj.text for line_obj in lines]


class FigureDetectionTests(unittest.TestCase):
    def test_plot_takes_its_labels_and_the_caption_below_it(self) -> None:
        # A body line, the short last line of its paragraph, and a heading
        # reach into the area around the plot.
        above = [
            *body(124.0, 4),
            line('ends.', 40.0, 172.0, 70.0),
            line('Experimental results', 120.0, 184.0, 260.0, font_size=14.0),
        ]
        lines = [*above, *labels(), *caption(), *body(400.0, 3)]

        figures = find_figures(lines, {1: [plot(PANEL)]})

        self.assertEqual(len(figures), 1)
        self.assertEqual(texts(figures[0].lines), texts(labels()))
        self.assertEqual(texts(figures[0].caption_lines), texts(caption()))
        # The picture extends over the axis titles beside and below the plot.
        self.assertEqual(figures[0].box, (42.0, 200.0, 300.0, 338.0))

    def test_picture_needs_no_caption(self) -> None:
        lines = [*body(100.0, 4), *body(400.0, 3)]

        figures = find_figures(lines, {1: [photo(PANEL)]})

        self.assertEqual([figure.box for figure in figures], [PANEL])
        self.assertEqual(figures[0].lines, [])
        self.assertEqual(figures[0].caption_lines, [])

    def test_caption_is_recognized_by_its_type_in_any_language(self) -> None:
        for first in ('Rys. 1. Wykres sygnału w czasie', 'Вид на город с холма, 1930 год'):
            with self.subTest(first):
                figures = find_figures(
                    [*body(100.0, 4), *caption(first), *body(400.0, 3)], {1: [photo(PANEL)]}
                )

                self.assertEqual(texts(figures[0].caption_lines), [first, 'as indicated.'])

    def test_body_text_below_a_picture_is_no_caption(self) -> None:
        figures = find_figures([*body(100.0, 4), *body(330.0, 3)], {1: [photo(PANEL)]})

        self.assertEqual(figures[0].caption_lines, [])

    def test_caption_at_body_size_starts_in_bold(self) -> None:
        bold = line('Figure 2: A screenshot', 90.0, 330.0, 250.0, bold=True)

        figures = find_figures([*body(100.0, 4), bold, *body(360.0, 3)], {1: [photo(PANEL)]})

        self.assertEqual(texts(figures[0].caption_lines), ['Figure 2: A screenshot'])

    def test_footnote_and_distant_small_text_below_a_picture_are_no_captions(self) -> None:
        footnote = line('1 A note on the text above.', 40.0, 330.0, 200.0, font_size=8.0)
        distant = line('Some small print far below.', 40.0, 420.0, 200.0, font_size=8.0)

        for small in (footnote, distant):
            with self.subTest(small.text):
                figures = find_figures([*body(100.0, 4), small], {1: [photo(PANEL)]})

                self.assertEqual(figures[0].caption_lines, [])

    def test_caption_ends_after_a_short_last_line(self) -> None:
        small_print = [
            line('Further small print, which is', 40.0, 370.0, 300.0, font_size=9.0),
            line('no part of the caption.', 40.0, 380.0, 150.0, font_size=9.0),
        ]

        figures = find_figures([*caption(), *small_print, *elsewhere()], {1: [photo(PANEL)]})

        self.assertEqual(texts(figures[0].caption_lines), texts(caption()))

    def test_frames_rules_and_plain_boxes_are_no_pictures(self) -> None:
        frame = Drawing(PANEL, 'path')
        rule = Drawing((40.0, 330.0, 300.0, 331.0), 'path')

        self.assertEqual(find_figures(body(100.0, 4), {1: [frame, rule]}), [])

    def test_small_drawings_are_no_pictures(self) -> None:
        icon = photo((60.0, 200.0, 80.0, 220.0))
        ornament = plot((100.0, 200.0, 130.0, 208.0))

        self.assertEqual(find_figures(body(100.0, 4), {1: [icon, ornament]}), [])

    def test_wide_strip_of_an_image_is_a_picture(self) -> None:
        strip = photo((60.0, 200.0, 300.0, 212.0))

        self.assertEqual(len(find_figures(body(100.0, 4), {1: [strip]})), 1)

    def test_drawing_with_running_text_on_it_is_a_background(self) -> None:
        lines = body(210.0, 4)

        for background in (photo(PANEL), plot(PANEL)):
            with self.subTest(background.kind):
                self.assertEqual(find_figures(lines, {1: [background]}), [])

    def test_long_lines_in_small_type_set_as_a_paragraph_are_running_text(self) -> None:
        abstract = [
            line(BODY_TEXT, 90.0, 220.0 + 10.0 * index, 280.0, font_size=8.0) for index in range(3)
        ]

        self.assertEqual(find_figures([*body(100.0, 4), *abstract], {1: [photo(PANEL)]}), [])

    def test_legend_entries_on_a_plot_are_no_running_text(self) -> None:
        legend = [
            line('Proposed method', 200.0, 210.0, 280.0, font_size=8.0),
            line('Baseline method', 200.0, 220.0, 280.0, font_size=8.0),
        ]

        figures = find_figures([*body(100.0, 4), *legend], {1: [plot(PANEL)]})

        self.assertEqual(texts(figures[0].lines), texts(legend))

    def test_image_covering_its_page_is_a_background_if_there_is_text_on_it(self) -> None:
        scan = photo((0.0, 0.0, 400.0, 600.0))
        title = [line('A Title', 150.0, 300.0, 250.0, font_size=20.0)]
        sizes = {1: (400.0, 600.0)}

        self.assertEqual(find_figures(title, {1: [scan]}, page_sizes=sizes), [])
        self.assertEqual(len(find_figures([], {1: [scan]}, page_sizes=sizes)), 1)

    def test_drawings_repeated_on_several_pages_are_furniture(self) -> None:
        logo = (60.0, 20.0, 300.0, 80.0)
        lines = [line_obj for page_no in (1, 2, 3) for line_obj in body(100.0, 4, page_no=page_no)]

        self.assertEqual(find_figures(lines, {1: [photo(logo)], 2: [photo(logo)]})[0].box, logo)
        self.assertEqual(find_figures(lines, {page_no: [photo(logo)] for page_no in (1, 2, 3)}), [])

    def test_rule_reaching_far_beyond_a_picture_does_not_extend_it(self) -> None:
        icon = (140.0, 200.0, 200.0, 260.0)
        heading = line('A heading above the icon', 40.0, 180.0, 200.0, font_size=14.0)
        underline = Drawing((40.0, 197.0, 300.0, 198.0), 'path')
        tick = Drawing((136.0, 230.0, 140.0, 231.0), 'path')

        figures = find_figures([heading, *body(300.0, 3)], {1: [photo(icon), underline, tick]})

        self.assertEqual([figure.box for figure in figures], [(136.0, 200.0, 200.0, 260.0)])

    def test_panels_close_together_form_one_picture(self) -> None:
        upper = (100.0, 100.0, 300.0, 200.0)
        lower = (100.0, 230.0, 300.0, 330.0)
        lines = [
            label('1.0', 110.0, 110.0, 122.0),
            label('upper label', 150.0, 205.0, 200.0),
            label('lower label', 150.0, 335.0, 200.0),
            line('Two panels of one figure.', 100.0, 355.0, 220.0, font_size=9.0),
            *elsewhere(),
        ]

        figures = find_figures(lines, {1: [plot(upper), plot(lower)]})

        self.assertEqual(len(figures), 1)
        self.assertEqual(texts(figures[0].lines), ['1.0', 'upper label', 'lower label'])
        self.assertEqual(texts(figures[0].caption_lines), ['Two panels of one figure.'])

    def test_pictures_separated_by_text_stay_apart(self) -> None:
        upper = (100.0, 100.0, 300.0, 200.0)
        lower = (100.0, 230.0, 300.0, 330.0)
        lines = [
            line('The upper photo.', 150.0, 208.0, 250.0, font_size=9.0),
            line('The lower photo.', 150.0, 338.0, 250.0, font_size=9.0),
            *elsewhere(),
        ]

        figures = find_figures(lines, {1: [photo(upper), photo(lower)]})

        self.assertEqual(
            [(figure.box, texts(figure.caption_lines)) for figure in figures],
            [(upper, ['The upper photo.']), (lower, ['The lower photo.'])],
        )

    def test_side_by_side_pictures_keep_their_own_captions(self) -> None:
        left = (60.0, 200.0, 200.0, 300.0)
        right = (330.0, 200.0, 470.0, 300.0)
        lines = [
            line('The left figure.', 60.0, 310.0, 200.0, font_size=9.0),
            line('The right figure.', 330.0, 310.0, 470.0, font_size=9.0),
            *elsewhere(),
        ]

        figures = find_figures(lines, {1: [photo(right), photo(left)]})

        self.assertEqual(
            [(figure.box, texts(figure.caption_lines)) for figure in figures],
            [(left, ['The left figure.']), (right, ['The right figure.'])],
        )

    def test_tick_values_in_the_document_font_are_labels(self) -> None:
        ticks = line('0 40 80 120', 60.0, 324.0, 300.0, font_size=8.0)

        figures = find_figures([*body(100.0, 4), ticks, *caption()], {1: [plot(PANEL)]})

        self.assertEqual(texts(figures[0].lines), ['0 40 80 120'])
        self.assertEqual(texts(figures[0].caption_lines), texts(caption()))

    def test_short_last_line_of_a_caption_is_no_label(self) -> None:
        lines = [
            line('A caption ending in a short line: 1930 and', 60.0, 324.0, 300.0, font_size=8.0),
            line('1946', 60.0, 333.0, 80.0, font_size=8.0),
        ]

        figures = find_figures([*lines, *elsewhere()], {1: [photo(PANEL)]})

        self.assertEqual(figures[0].lines, [])
        self.assertEqual(texts(figures[0].caption_lines), texts(lines))

    def test_prose_in_the_document_font_beside_a_plot_stays_text(self) -> None:
        note = line('(a) Gaussian samples.', 310.0, 250.0, 400.0, font_size=9.0)

        figures = find_figures([*body(100.0, 4), note], {1: [plot(PANEL)]})

        self.assertEqual(figures[0].lines, [])
        self.assertEqual(figures[0].box, PANEL)

    def test_figure_font_is_no_font_of_the_document(self) -> None:
        # The font of the label within the plot also sets text elsewhere.
        lines = [
            *body(100.0, 4),
            line('100', 82.0, 200.0, 94.0, font_size=8.0),
            line('A sidenote in small type', 310.0, 250.0, 400.0, font_size=8.0),
        ]

        figures = find_figures(lines, {1: [plot(PANEL)]})

        self.assertEqual(texts(figures[0].lines), ['100'])

    def test_picture_does_not_extend_over_a_table(self) -> None:
        table_lines = [line('A cell', 60.0, 335.0, 100.0)]
        table = TableLayout([TableFrame(1, 330.0, 360.0)], table_lines, 1, 1, 1, [])
        below = label('Time (ps)', 180.0, 340.0, 216.0)

        figures = find_figures(
            [label('100', 82.0, 200.0, 94.0), below, *table_lines], {1: [plot(PANEL)]}, [table]
        )

        self.assertEqual(figures[0].box, PANEL)
        self.assertEqual(texts(figures[0].lines), ['100'])

    def test_picture_of_images_only_has_their_resolution(self) -> None:
        frame = Drawing((59.0, 199.0, 301.0, 321.0), 'path')

        photo_only = find_figures([], {1: [photo(PANEL), frame]})[0]
        screenshot = find_figures([], {1: [photo(PANEL, lossy=False)]})[0]
        with_plot = find_figures([], {1: [photo(PANEL), plot((100.0, 220.0, 200.0, 300.0))]})[0]
        with_label = find_figures([label('100', 82.0, 200.0, 94.0)], {1: [photo(PANEL)]})[0]

        self.assertEqual((photo_only.resolution, photo_only.lossy), (144.0, True))
        self.assertEqual((screenshot.resolution, screenshot.lossy), (144.0, False))
        self.assertEqual((with_plot.resolution, with_plot.lossy), (None, False))
        self.assertEqual((with_label.resolution, with_label.lossy), (None, False))


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


class ReadingPositionTests(unittest.TestCase):
    def test_picture_precedes_the_first_line_below_it_in_its_column(self) -> None:
        left = body(100.0, 6)
        right = [line(BODY_TEXT, 320.0, 100.0 + 12.0 * index, 580.0) for index in range(6)]
        figure = FigureLayout(1, (320.0, 30.0, 580.0, 90.0), [], [])

        self.assertEqual(reading_position(figure, [*left, *right]), 5.5)

    def test_picture_below_all_lines_of_its_column_follows_them(self) -> None:
        left = body(100.0, 6)
        right = [line(BODY_TEXT, 320.0, 100.0 + 12.0 * index, 580.0) for index in range(6)]
        figure = FigureLayout(1, (40.0, 200.0, 300.0, 300.0), [], [])

        self.assertEqual(reading_position(figure, [*left, *right]), 5.5)

    def test_picture_on_a_page_without_lines_precedes_the_next_page(self) -> None:
        lines = [*body(100.0, 3), *body(100.0, 3, page_no=3)]
        figure = FigureLayout(2, (40.0, 200.0, 300.0, 300.0), [], [])

        self.assertEqual(reading_position(figure, lines), 2.5)
        self.assertEqual(reading_position(FigureLayout(4, figure.box, [], []), lines), 5.5)


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
        figure = FigureLayout(
            1, (60.0, 200.0, 300.0, 338.0), figure_lines, caption_lines, image='doc-img/p1-1.png'
        )
        pages = {1: PageNumber(1, None), 2: PageNumber(2, None)}

        blocks = lines_to_markdown_blocks(
            [*before, *figure_lines, *caption_lines, *after], pages, figures=[figure]
        )

        self.assertEqual([type(block) for block in blocks][:3], [Paragraph, Image, Paragraph])
        self.assertIn('continued on the next page', blocks[0].text.replace('\n', ' '))
        assert isinstance(blocks[1], Image)
        self.assertEqual(blocks[1].target, 'doc-img/p1-1.png')
        self.assertEqual(blocks[2].text, 'Fig. 1 The caption.')

    def test_figure_without_an_image_leaves_only_its_caption(self) -> None:
        figure_lines = [line('0 40 80', 120.0, 330.0, 160.0, font_size=8.0)]
        caption_lines = [line('Fig. 1 The caption.', 40.0, 350.0, 140.0, font_size=9.0)]
        figure = FigureLayout(1, (60.0, 200.0, 300.0, 338.0), figure_lines, caption_lines)

        blocks = lines_to_markdown_blocks(
            [*body(100.0, 4), *figure_lines, *caption_lines],
            {1: PageNumber(1, None)},
            figures=[figure],
        )

        self.assertEqual([type(block) for block in blocks], [Paragraph, Paragraph])
        self.assertEqual(blocks[1].text, 'Fig. 1 The caption.')

    def test_picture_without_text_is_placed_where_it_lies_on_its_page(self) -> None:
        figure = FigureLayout(1, (60.0, 160.0, 300.0, 280.0), [], [], image='doc-img/p1-1.jpg')

        blocks = lines_to_markdown_blocks(
            [*body(100.0, 4), *body(300.0, 4)], {1: PageNumber(1, None)}, figures=[figure]
        )

        self.assertEqual([type(block) for block in blocks], [Paragraph, Image, Paragraph])

    def test_caption_may_be_the_only_text_of_its_page(self) -> None:
        caption_lines = [line('A photo of the author.', 40.0, 350.0, 140.0, font_size=9.0)]
        figure = FigureLayout(
            2, (60.0, 200.0, 300.0, 338.0), [], caption_lines, image='doc-img/p2-1.jpg'
        )
        caption_lines[0].page_no = 2
        pages = {1: PageNumber(1, None), 2: PageNumber(2, None)}

        blocks = lines_to_markdown_blocks(
            [*body(100.0, 4), *caption_lines], pages, figures=[figure]
        )

        self.assertEqual([type(block) for block in blocks], [Paragraph, Image, Paragraph])
        self.assertEqual(blocks[2].text, 'A photo of the author.')


if __name__ == '__main__':
    unittest.main()
