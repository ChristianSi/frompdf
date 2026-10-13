import io
import unittest
from dataclasses import replace

from frompdf.blocks import (
    build_body_lefts_by_page,
    lines_to_markdown_blocks,
    merge_continued_groups,
)
from frompdf.continuations import (
    begins_lowercase,
    build_page_layouts,
    continues_across_boundary,
    document_indents_paragraphs,
    ends_open_sentence,
    is_heading_like,
)
from frompdf.models import BlockQuote, Line, PageNumber, Paragraph, TextFragment
from frompdf.output import markdown_to_text

BODY_TEXT = 'ordinary body text filling the whole column width'


def line(
    text: str,
    y1: float,
    *,
    page_no: int = 1,
    x1: float = 20.0,
    x2: float = 220.0,
    font_size: float = 10.0,
    block_no: int = 1,
) -> Line:
    """Build a positioned synthetic body line."""
    return Line(
        text=text,
        page_no=page_no,
        block_no=block_no,
        line_no_on_page=int(y1),
        font_size=font_size,
        x1=x1,
        y1=y1,
        x2=x2,
        y2=y1 + font_size,
        rel_x=None,
        rel_y=None,
        avg_weight=400.0,
        font_name='Body-Regular',
    )


def column(page_no: int, *, x1: float = 20.0, top: float = 12.0, count: int = 6) -> list[Line]:
    """Build one column of full body lines."""
    return [
        line(BODY_TEXT, top + index * 12, page_no=page_no, x1=x1, x2=x1 + 200)
        for index in range(count)
    ]


def two_pages(last: Line | None = None, first: Line | None = None) -> tuple[list[Line], ...]:
    """Return the final group of page 1, the first group of page 2, and all lines."""
    page_1 = column(1)
    page_2 = column(2)
    if last is not None:
        page_1[-1] = last
    if first is not None:
        page_2[0] = first
    return page_1[3:], page_2[:3], page_1 + page_2


class TextCueTests(unittest.TestCase):
    def test_lowercase_start_ignores_opening_punctuation(self) -> None:
        self.assertTrue(begins_lowercase('„was ist das“'))
        self.assertTrue(begins_lowercase('(and more)'))
        self.assertFalse(begins_lowercase('The next sentence'))
        self.assertFalse(begins_lowercase('1995 was a year'))

    def test_trailing_addresses_do_not_count_as_open_sentences(self) -> None:
        self.assertTrue(ends_open_sentence('a sentence that continues with'))
        self.assertFalse(ends_open_sentence('a complete sentence.'))
        self.assertFalse(ends_open_sentence('available at http://www.example.org/reprints'))
        self.assertFalse(ends_open_sentence('contact: someone@example.org'))


class IndentationEvidenceTests(unittest.TestCase):
    def groups(self, indented_count: int, flush_count: int) -> list[list[Line]]:
        groups: list[list[Line]] = []
        for index in range(indented_count + flush_count):
            top = 12 + index * 36
            first_x1 = 32.0 if index < indented_count else 20.0
            groups.append(
                [line(BODY_TEXT, top, x1=first_x1)]
                + [line(BODY_TEXT, top + offset) for offset in (12, 24)]
            )
        return groups

    def assert_indents(self, indented_count: int, flush_count: int, expected: bool) -> None:
        groups = self.groups(indented_count, flush_count)
        layouts = build_page_layouts([line_obj for group in groups for line_obj in group])
        self.assertEqual(document_indents_paragraphs(groups, layouts), expected)

    def test_document_with_indented_paragraph_starts(self) -> None:
        self.assert_indents(6, 10, True)

    def test_block_paragraph_document_and_sparse_indents(self) -> None:
        self.assert_indents(0, 12, False)
        self.assert_indents(4, 0, False)
        self.assert_indents(5, 20, False)

    def test_bold_lead_in_is_not_heading_like(self) -> None:
        lead_in = [
            replace(
                line('Peer review information Journal thanks the reviewers', 12), avg_weight=700
            ),
            line('for their contribution to the peer review of this work.', 24),
        ]
        paragraph = [line('Reprints and permission information is available', 36)]
        heading = [replace(line('Additional information', 12), avg_weight=700)]
        self.assertFalse(is_heading_like(lead_in, paragraph))
        self.assertTrue(is_heading_like(heading, paragraph))


class PageBoundaryTests(unittest.TestCase):
    def assert_continues(self, last: Line, first: Line, expected: bool) -> None:
        previous, current, lines = two_pages(last, first)
        self.assertEqual(
            continues_across_boundary(previous, current, build_page_layouts(lines)), expected
        )

    def test_open_sentence_continues_on_next_page(self) -> None:
        self.assert_continues(
            line('this sentence is not complete on the first', 72),
            line('Page because it continues here as expected', 12, page_no=2),
            True,
        )

    def test_lowercase_start_continues_after_sentence_end(self) -> None:
        self.assert_continues(
            line('an abbreviation ends this line, e.g.', 72),
            line('which is followed by lower-case text here', 12, page_no=2),
            True,
        )

    def test_complete_sentence_and_capitalized_start_remain_separate(self) -> None:
        self.assert_continues(
            line('this paragraph ends exactly at the edge.', 72),
            line('The next paragraph starts on the new page', 12, page_no=2),
            False,
        )

    def test_missing_indent_continues_complete_sentence_in_indenting_document(self) -> None:
        previous, current, lines = two_pages(
            line('this paragraph has a sentence ending here.', 72),
            line('The sentence on the new page is not indented', 12, page_no=2),
        )
        layouts = build_page_layouts(lines)
        indented_start = [replace(previous[0], x1=32.0)] + previous[1:]
        self.assertTrue(continues_across_boundary(indented_start, current, layouts, True))
        self.assertFalse(continues_across_boundary(indented_start, current, layouts, False))

    def test_flush_paragraph_needs_preceding_heading_as_indent_evidence(self) -> None:
        previous, current, lines = two_pages(
            line('this paragraph has a sentence ending here.', 72),
            line('The sentence on the new page is not indented', 12, page_no=2),
        )
        layouts = build_page_layouts(lines)
        body = [line(BODY_TEXT, 24)]
        heading = [replace(line('Section heading', 24), font_size=14.0)]
        self.assertFalse(continues_across_boundary(previous, current, layouts, True, body))
        self.assertTrue(continues_across_boundary(previous, current, layouts, True, heading))

    def test_short_last_line_remains_separate(self) -> None:
        self.assert_continues(
            line('a short final line without', 72, x2=100),
            line('continuation text at the top of the page', 12, page_no=2),
            False,
        )

    def test_indented_first_line_remains_separate(self) -> None:
        self.assert_continues(
            line('this sentence is not complete on the first', 72),
            line('page but the next line is indented', 12, page_no=2, x1=32),
            False,
        )

    def test_list_item_remains_separate(self) -> None:
        self.assert_continues(
            line('a list item without final punctuation', 72),
            line('• another item at the top of the next page', 12, page_no=2),
            False,
        )

    def test_different_font_size_remains_separate(self) -> None:
        previous, current, lines = two_pages(line('an open sentence at the end of', 72))
        current = [replace(line_obj, font_size=7.0) for line_obj in current]
        lines = previous + current
        self.assertFalse(continues_across_boundary(previous, current, build_page_layouts(lines)))

    def test_text_after_a_skipped_page_remains_separate(self) -> None:
        previous, current, _ = two_pages(line('an open sentence at the end of', 72))
        current = [replace(line_obj, page_no=3) for line_obj in current]
        layouts = build_page_layouts(previous + current)
        self.assertFalse(continues_across_boundary(previous, current, layouts))


class ColumnBoundaryTests(unittest.TestCase):
    def test_paragraph_continues_at_top_of_next_column(self) -> None:
        left = column(1)
        left[-1] = line('this sentence continues in the next', 72)
        right = column(1, x1=260)
        right[0] = line('column of the same page as expected', 12, x1=260, x2=460)
        layouts = build_page_layouts(left + right)
        self.assertTrue(continues_across_boundary(left[3:], right[:3], layouts))

    def test_next_table_cell_is_not_a_column_continuation(self) -> None:
        left = column(1)
        left[-1] = line('this cell continues in the next', 72)
        right = column(1, x1=260, top=48)
        right[0] = line('cell of the same table row as expected', 48, x1=260, x2=460)
        layouts = build_page_layouts(left + right)
        self.assertFalse(continues_across_boundary(left[3:], right[:3], layouts))


class GroupMergeTests(unittest.TestCase):
    def merge(
        self, previous: list[Line], current: list[Line], following: list[Line] | None = None
    ) -> list[list[Line]]:
        groups = [column(1)[:3], previous, current] + ([following] if following else [])
        lines = [line_obj for group in groups for line_obj in group]
        return merge_continued_groups(
            groups,
            build_page_layouts(lines),
            10.0,
            build_body_lefts_by_page(lines, 10.0),
            {},
        )

    def test_quote_does_not_absorb_paragraph_continuation(self) -> None:
        previous = [line(BODY_TEXT, y) for y in (48, 60)]
        previous.append(line('this sentence does not end on the first', 72))
        current = [
            line('quoted text set in from the margin', y, page_no=2, x1=40, x2=200)
            for y in (12, 24, 36)
        ]
        following = column(2, top=60)
        self.assertEqual(len(self.merge(previous, current, following)), 4)

    def test_hanging_indent_continuation_is_not_a_quote(self) -> None:
        previous = [line('1. A list item that starts at the margin', 48)]
        previous += [line(BODY_TEXT, y, x1=40) for y in (60,)]
        previous.append(line('and continues with the hanging indent of', 72, x1=40))
        current = [line('the item on the next page as expected', 12, page_no=2, x1=40)]
        current += [line(BODY_TEXT, y, page_no=2, x1=40) for y in (24, 36, 48, 60, 72)]
        self.assertEqual(len(self.merge(previous, current)), 2)


class PageAwareParagraphTests(unittest.TestCase):
    def test_marker_follows_word_repaired_across_pages(self) -> None:
        _, _, lines = two_pages(
            line('this text discusses an inter-', 72),
            line('national topic on the next page', 12, page_no=2, block_no=2),
        )
        lines = [replace(line_obj, block_no=line_obj.page_no) for line_obj in lines]
        pages = {1: PageNumber(1, '7'), 2: PageNumber(2, '8')}
        blocks = lines_to_markdown_blocks(lines, pages)
        self.assertEqual(len(blocks), 1)
        self.assertIsInstance(blocks[0], Paragraph)
        self.assertEqual((blocks[0].start_page, blocks[0].end_page), (pages[1], pages[2]))
        output = io.StringIO()
        markdown_to_text(blocks, output, page_markers=True)
        self.assertEqual(
            output.getvalue().split('\n')[5:7],
            ['this text discusses an international', '<<PAGE:2|VISIBLE:8>>topic on the next page'],
        )
        output = io.StringIO()
        markdown_to_text(blocks, output)
        self.assertNotIn('<<PAGE', output.getvalue())

    def test_quote_markers_stay_inside_quote(self) -> None:
        pages = {1: PageNumber(1, None), 2: PageNumber(2, None)}
        quote = BlockQuote('unused', pages[1], pages[2])
        quote.fragments = [
            TextFragment('quoted text that', pages[1]),
            TextFragment('continues', pages[2], '\n'),
        ]
        output = io.StringIO()
        markdown_to_text([quote], output, page_markers=True)
        self.assertEqual(output.getvalue(), '> <<PAGE:1>>quoted text that\n> <<PAGE:2>>continues\n')


if __name__ == '__main__':
    unittest.main()
