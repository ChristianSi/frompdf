import io
import unittest
from collections import Counter
from itertools import pairwise

from frompdf.continuations import build_page_fragments, build_page_layouts, join_fragments
from frompdf.line_breaks import (
    first_word_width,
    hard_line_break_ids,
    is_centered_line_layout,
    is_hard_line_break,
)
from frompdf.models import HARD_LINE_BREAK, BlockQuote, Heading, Line, PageNumber, Paragraph
from frompdf.output import markdown_to_text
from frompdf.scripts import AnnotatedText, collapse_annotated_whitespace

BODY_TEXT = 'Ordinary body text filling the whole column width'


def line(
    text: str,
    y1: float,
    *,
    x1: float = 20.0,
    x2: float | None = None,
    font_size: float = 10.0,
    font_name: str = 'Body-Regular',
    avg_weight: float = 400.0,
) -> Line:
    """Build a positioned synthetic line, 4 units per character unless x2 is given."""
    return Line(
        text=text,
        page_no=1,
        block_no=1,
        line_no_on_page=int(y1),
        font_size=font_size,
        x1=x1,
        y1=y1,
        x2=x2 if x2 is not None else x1 + 4.0 * len(text),
        y2=y1 + font_size,
        rel_x=None,
        rel_y=None,
        avg_weight=avg_weight,
        font_name=font_name,
    )


def body_column(top: float = 12.0, count: int = 6, font_size: float = 10.0) -> list[Line]:
    """Build a column of full body lines from x=20 to x=220."""
    return [
        line(BODY_TEXT, top + index * 12, x2=220.0, font_size=font_size) for index in range(count)
    ]


def card_page(block: list[Line]) -> list[Line]:
    """Return a page with a centered block above smaller body text.

    Lines of the body size would form a page column of their own instead.
    """
    return body_column(font_size=8.0) + block


def centered(text: str, y1: float, *, font_size: float = 10.0) -> Line:
    """Build a line centered at x=120, 4 units per character."""
    half_width = 2.0 * len(text)
    return line(text, y1, x1=120.0 - half_width, x2=120.0 + half_width, font_size=font_size)


def card(name_size: float = 12.0) -> list[Line]:
    """Build a centered address card whose name and e-mail lines may be larger."""
    return [
        centered('Ada Lovelace', 100, font_size=name_size),
        centered('Analytical Society of', 112),
        centered('engine builders', 124),
        centered('12345 London', 136),
        centered('ada@example.org', 148, font_size=name_size),
    ]


def breaks(block: list[Line], page: list[Line]) -> list[bool]:
    """Return whether each line of block except the last is followed by a hard break."""
    layout = build_page_layouts(page)[1]
    return [is_hard_line_break(left, right, layout) for left, right in pairwise(block)]


class FirstWordWidthTests(unittest.TestCase):
    def test_estimates_width_from_average_character_width(self) -> None:
        self.assertEqual(first_word_width(line('word and more', 0, x2=72.0)), 16.0)

    def test_no_break_space_joins_first_word(self) -> None:
        self.assertEqual(first_word_width(line('p.\u00a0325 more', 0)), 24.0)


class HardLineBreakTests(unittest.TestCase):
    def test_short_lines_with_room_for_the_next_word_break(self) -> None:
        block = [line('RECEIVED 09/04/21', 100), line('ACCEPTED 13/04/21', 112)]

        self.assertEqual(breaks(block, body_column() + block), [True])

    def test_wrapped_full_lines_do_not_break(self) -> None:
        page = body_column()

        self.assertEqual(breaks(page, page), [False] * 5)

    def test_ragged_line_without_room_for_the_next_word_does_not_break(self) -> None:
        # The line ends 40 units before the margin; the next word needs 48.
        block = [line('ragged text ending', 100, x2=180.0), line('Wordthatlong goes on', 112)]

        self.assertEqual(breaks(block, body_column() + block), [False])

    def test_open_sentence_continuing_in_lower_case_does_not_break(self) -> None:
        block = [line('a short line', 100), line('and its continuation', 112)]

        self.assertEqual(breaks(block, body_column() + block), [False])

    def test_hyphenated_word_does_not_break(self) -> None:
        block = [line('a short hyph-', 100), line('Enated word', 112)]

        self.assertEqual(breaks(block, body_column() + block), [False])

    def test_fragments_with_few_letters_or_digits_do_not_break(self) -> None:
        block = [line('(s,f)', 100), line('0 = 2 + x', 112)]

        self.assertEqual(breaks(block, body_column() + block), [False])

    def test_lines_with_enough_digits_break(self) -> None:
        block = [line('2021-06-07.', 100), line('Retrieved from the web', 112)]

        self.assertEqual(breaks(block, body_column() + block), [True])

    def test_right_aligned_inset_lines_with_room_break(self) -> None:
        block = [
            line('Nature loves to hide', 100, x1=140.0, x2=220.0),
            line('Heraclitus of Ephesus', 112, x1=136.0, x2=220.0),
        ]

        self.assertEqual(breaks(block, body_column() + block), [True])

    def test_indented_first_line_is_not_right_aligned(self) -> None:
        block = [
            line(BODY_TEXT[:45], 100, x1=36.0, x2=220.0),
            line('Next words of the paragraph', 112, x2=220.0),
        ]

        self.assertEqual(breaks(block, body_column() + block), [False])

    def test_style_change_after_short_line_breaks(self) -> None:
        # The address would not fit after the first line, but changes style.
        block = [
            line('Laboratory of Space Studies.', 100, x2=150.0),
            line('someone.with.a.long.address@example.org', 112, font_name='Body-Italic'),
        ]

        self.assertEqual(breaks(block, body_column() + block), [True])

    def test_style_change_on_full_line_does_not_break(self) -> None:
        block = [
            line(BODY_TEXT, 100, x2=220.0, font_name='Body-Italic'),
            line('Ordinary text continues here', 112),
        ]

        self.assertEqual(breaks(block, body_column() + block), [False])

    def test_measure_ignores_wider_lines_in_larger_type(self) -> None:
        title = [line('A Title Spanning The Whole Page', 0, x2=500.0, font_size=20.0)] * 3
        block = [
            line('Abstract text that is justified', 100, x2=220.0),
            line('Following text of the abstract', 112, x2=220.0),
        ]

        self.assertEqual(breaks(block, title + body_column() + block), [False])

    def test_hard_line_break_ids_mark_left_lines(self) -> None:
        block = [line('RECEIVED 09/04/21', 100), line('ACCEPTED 13/04/21', 112)]
        page = body_column() + block

        self.assertEqual(hard_line_break_ids(block, build_page_layouts(page)), {id(block[0])})


class CenteredLineLayoutTests(unittest.TestCase):
    def test_centered_short_lines_of_differing_widths_qualify(self) -> None:
        block = card()
        layout = build_page_layouts(card_page(block))[1]

        self.assertTrue(is_centered_line_layout(block, layout))

    def test_equal_widths_do_not_qualify(self) -> None:
        block = [centered('Same width line', 100 + index * 12) for index in range(3)]
        layout = build_page_layouts(card_page(block))[1]

        self.assertFalse(is_centered_line_layout(block, layout))

    def test_left_aligned_ragged_lines_do_not_qualify(self) -> None:
        block = [line('Short', 100), line('Somewhat longer line', 112), line('Medium line', 124)]
        layout = build_page_layouts(card_page(block))[1]

        self.assertFalse(is_centered_line_layout(block, layout))

    def test_two_lines_do_not_qualify(self) -> None:
        block = card()[:2]
        layout = build_page_layouts(card_page(block))[1]

        self.assertFalse(is_centered_line_layout(block, layout))

    def test_lines_filling_most_of_the_column_do_not_qualify(self) -> None:
        block = [
            centered('Centered Prose Of An Abstract Spanning', 100),
            centered('Most Of The Column Width In Lines', 112),
            centered('Of Differing Widths Throughout', 124),
        ]
        layout = build_page_layouts(card_page(block))[1]

        self.assertFalse(is_centered_line_layout(block, layout))

    def test_one_deliberate_break_extends_to_other_line_ends(self) -> None:
        block = card()
        layouts = build_page_layouts(card_page(block))

        # The lower-case continuation stays joined. The lone e-mail address
        # does not count as one.
        self.assertEqual(
            hard_line_break_ids(block, layouts), {id(block[0]), id(block[2]), id(block[3])}
        )

    def test_centered_block_without_a_deliberate_break_stays_joined(self) -> None:
        block = card(name_size=10.0)
        layouts = build_page_layouts(card_page(block))

        self.assertEqual(hard_line_break_ids(block, layouts), set())


class HardLineBreakTextTests(unittest.TestCase):
    def test_marker_keeps_hyphenated_words_apart(self) -> None:
        block = [line('Smith-', 100), line('Jones Ltd.', 112)]
        page = PageNumber(1, None)

        fragments = build_page_fragments(block, {1: page}, Counter(), set(), set(), {id(block[0])})

        self.assertEqual(join_fragments(fragments).text, f'Smith-{HARD_LINE_BREAK}\nJones Ltd.')

    def test_markers_render_as_backslashes(self) -> None:
        page = PageNumber(1, None)
        blocks = [
            Paragraph(f'RECEIVED{HARD_LINE_BREAK}\nACCEPTED', page, page),
            BlockQuote(f'Quote{HARD_LINE_BREAK}\nAuthor', page, page),
        ]
        output = io.StringIO()

        markdown_to_text(blocks, output)

        self.assertEqual(output.getvalue(), 'RECEIVED\\\nACCEPTED\n\n> Quote\\\n> Author\n')

    def test_heading_whitespace_collapse_removes_markers(self) -> None:
        collapsed = collapse_annotated_whitespace(AnnotatedText(f'Title{HARD_LINE_BREAK}\nPart'))
        page = PageNumber(1, None)
        output = io.StringIO()

        markdown_to_text([Heading(collapsed.text, page, page)], output)

        self.assertEqual(output.getvalue(), '# Title Part\n')


if __name__ == '__main__':
    unittest.main()
