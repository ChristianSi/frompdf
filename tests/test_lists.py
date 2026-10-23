import unittest

from frompdf.blocks import lines_to_markdown_blocks
from frompdf.lists import ListMarker, find_list_items, parse_list_marker
from frompdf.models import BlockQuote, InlineRange, Line, ListItem, PageNumber, Paragraph

FULL = 'Body text that fills the whole line of its column'


def line(
    text: str,
    y1: float,
    *,
    x1: float = 20.0,
    x2: float = 220.0,
    page_no: int = 1,
    block_no: int = 1,
    ranges: tuple[InlineRange, ...] = (),
) -> Line:
    """Build a positioned synthetic body line with 10 pt type on 12 pt leading."""
    return Line(
        text=text,
        page_no=page_no,
        block_no=block_no,
        line_no_on_page=int(y1 // 12),
        font_size=10.0,
        x1=x1,
        y1=y1,
        x2=x2,
        y2=y1 + 10.0,
        rel_x=None,
        rel_y=None,
        avg_weight=400.0,
        font_name='Body-Regular',
        ranges=ranges,
    )


def introduction(
    last_text: str = 'and introduces a list as follows:', last_x2: float = 150.0
) -> list[Line]:
    """Return a body paragraph whose last line precedes a list at y 60."""
    return [line(FULL, y) for y in (12.0, 24.0, 36.0)] + [line(last_text, 48.0, x2=last_x2)]


def closing(y1: float, page_no: int = 1, x1: float = 20.0) -> list[Line]:
    """Return a body paragraph after a paragraph break."""
    return [line(FULL, y1 + 12.0 * index, x1=x1, page_no=page_no) for index in range(3)]


def item_texts(line_list: list[Line]) -> list[list[str]]:
    """Return the texts of recognized items, grouped by item."""
    items = find_list_items(line_list, {})
    grouped: dict[int, list[str]] = {}
    for line_obj in line_list:
        first = items.item_of_line.get(id(line_obj))
        if first is not None:
            grouped.setdefault(first, []).append(line_obj.text)
    return list(grouped.values())


class ListMarkerTests(unittest.TestCase):
    def test_parses_bullets_and_numbers(self) -> None:
        self.assertEqual(parse_list_marker('• Item'), ListMarker('strong', '•', None, 2))
        self.assertEqual(parse_list_marker('– Item'), ListMarker('weak', '–', None, 2))
        self.assertEqual(parse_list_marker('12. Item'), ListMarker('ordered', '.', 12, 4))
        self.assertEqual(parse_list_marker('3) Item'), ListMarker('ordered', ')', 3, 3))
        self.assertEqual(parse_list_marker('(3) Item'), ListMarker('ordered', '()', 3, 4))
        self.assertEqual(parse_list_marker('7 Item'), ListMarker('bare', '', 7, 2))

    def test_converts_markers_to_markdown(self) -> None:
        markers = ('• Item', '– Item', '12. Item', '3) Item', '(3) Item', '7 Item')
        self.assertEqual(
            [parse_list_marker(text).markdown for text in markers if parse_list_marker(text)],
            ['-', '-', '12.', '3)', '3)', '7.'],
        )

    def test_rejects_section_numbers_years_and_ornaments(self) -> None:
        for text in ('1.3 Section', '2019 was a year', '• • •', '-word', '12.'):
            with self.subTest(text=text):
                self.assertIsNone(parse_list_marker(text))


class ListItemTests(unittest.TestCase):
    def test_groups_bulleted_items_with_hanging_continuations(self) -> None:
        lines = [
            *introduction(),
            line('• First item that wraps onto', 60.0, x1=30.0),
            line('a continuation line', 72.0, x1=42.0, x2=140.0),
            line('• Second item', 84.0, x1=30.0, x2=100.0),
            *closing(108.0),
        ]

        self.assertEqual(
            item_texts(lines),
            [['• First item that wraps onto', 'a continuation line'], ['• Second item']],
        )

    def test_accepts_a_single_bullet_but_not_a_single_dash(self) -> None:
        for marker, expected in (('•', [['• Only item']]), ('–', [])):
            with self.subTest(marker=marker):
                lines = [
                    *introduction(),
                    line(f'{marker} Only item', 60.0, x1=30.0, x2=100.0),
                    *closing(84.0),
                ]
                self.assertEqual(item_texts(lines), expected)

    def test_accepts_numbered_items_after_a_deliberate_break(self) -> None:
        lines = [
            *introduction(),
            line('1. First', 60.0, x2=80.0),
            line('2. Second', 72.0, x2=80.0),
            *closing(96.0),
        ]

        self.assertEqual(item_texts(lines), [['1. First'], ['2. Second']])

    def test_rejects_numbers_starting_wrapped_lines(self) -> None:
        lines = [
            *introduction('Body text that ends at the margin without punctuation', 220.0),
            line('23. Dezember 1917 hielt er eine Rede, die in der ganzen Stadt', 60.0),
            line('24. Dezember wiederholte er sie vor einem anderen Publikum', 72.0),
            *closing(84.0),
        ]

        self.assertEqual(item_texts(lines), [])

    def test_requires_consecutive_numbers(self) -> None:
        lines = [
            *introduction(),
            line('1. First', 60.0, x2=80.0),
            line('3. Third', 72.0, x2=80.0),
            *closing(96.0),
        ]

        self.assertEqual(item_texts(lines), [])

    def test_requires_continuation_lines_for_numbers_without_delimiter(self) -> None:
        single_lines = [
            *introduction(),
            *(line(f'{number} Entry', 48.0 + 12.0 * number, x2=80.0) for number in (1, 2, 3)),
            *closing(108.0),
        ]
        wrapped_lines = [*introduction()]
        for number in (1, 2, 3):
            wrapped_lines.append(line(f'{number} Entry that wraps', 36.0 + 24.0 * number))
            wrapped_lines.append(line('onto a second line', 48.0 + 24.0 * number, x1=34.0))
        wrapped_lines.extend(closing(132.0))

        self.assertEqual(item_texts(single_lines), [])
        self.assertEqual(len(item_texts(wrapped_lines)), 3)

    def test_does_not_absorb_paragraph_after_spacing_or_with_other_indent(self) -> None:
        lines = [
            *introduction(),
            line('• First item that wraps onto', 60.0, x1=30.0),
            line('a continuation line', 72.0, x1=42.0, x2=140.0),
            line('• Second item', 84.0, x1=30.0, x2=100.0),
            line('A new paragraph with a first-line indent', 96.0, x1=36.0),
            *closing(108.0),
        ]

        self.assertEqual(item_texts(lines)[-1], ['• Second item'])

    def test_continues_items_on_the_next_page_with_other_margins(self) -> None:
        lines = [
            *introduction(),
            line('1. First item that wraps onto', 60.0),
            line('a second line', 72.0, x1=32.0),
            line('2. Second item that wraps onto', 84.0),
            *(line(FULL, 12.0 * index, x1=40.0, page_no=2) for index in (1, 2, 3)),
        ]
        # The second item continues at the top of page 2, whose margin is wider.
        lines[-3:-3] = [line('the next page', 0.0, x1=52.0, x2=140.0, page_no=2)]
        lines[-3:] = closing(36.0, page_no=2, x1=40.0)

        self.assertEqual(
            item_texts(lines),
            [
                ['1. First item that wraps onto', 'a second line'],
                ['2. Second item that wraps onto', 'the next page'],
            ],
        )


class ListBlockTests(unittest.TestCase):
    def test_builds_list_items_instead_of_quotes_and_strips_markers(self) -> None:
        bold_label = (InlineRange(0, 1, 'bold'),)
        lines = [
            *introduction(),
            line('1 First entry that wraps', 60.0, x1=30.0, ranges=bold_label),
            line('onto a second line', 72.0, x1=44.0, x2=140.0),
            line('2 Second entry that wraps', 84.0, x1=30.0, ranges=bold_label),
            line('onto a second line', 96.0, x1=44.0, x2=140.0),
            line('3 Third entry that wraps', 108.0, x1=30.0, ranges=bold_label),
            line('onto a second line', 120.0, x1=44.0, x2=140.0),
            *closing(144.0),
        ]
        page_numbers = {1: PageNumber(raw=1, visible=None)}

        blocks = lines_to_markdown_blocks(lines, page_numbers)

        self.assertEqual(
            [type(block) for block in blocks],
            [Paragraph, ListItem, ListItem, ListItem, Paragraph],
        )
        first = blocks[1]
        assert isinstance(first, ListItem)
        self.assertEqual(first.marker, '1.')
        self.assertEqual(first.text, 'First entry that wraps\nonto a second line')
        self.assertEqual(first.ranges, ())
        self.assertFalse(any(isinstance(block, BlockQuote) for block in blocks))
