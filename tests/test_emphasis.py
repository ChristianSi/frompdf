import io
import unittest
from typing import cast

from pdftext.schema import Line as PdfTextLine
from pdftext.schema import Page
from pdftext.schema import Span as PdfTextSpan

from frompdf.emphasis import render_inline, resolve_emphasis
from frompdf.lines import (
    drop_dominant_emphasis,
    iter_lines,
    line_emphasis_ranges,
    span_emphasis_kinds,
)
from frompdf.models import (
    HARD_LINE_BREAK,
    Block,
    BlockQuote,
    Heading,
    InlineKind,
    InlineRange,
    Line,
    PageNumber,
    Paragraph,
    StrongParagraph,
    TextFragment,
)
from frompdf.output import markdown_to_text
from frompdf.scripts import AnnotatedText


def font_span(text: str, name: str = 'Serif-Regular', flags: int = 4, x: float = 0) -> dict:
    """Build a span of equally wide glyphs in a named font."""
    chars = [
        {
            'char': char,
            'bbox': [x + index * 5, 10, x + index * 5 + 5, 20],
            'font': {'size': 10},
            'rotation': 0,
        }
        for index, char in enumerate(text)
    ]
    return {
        'text': text,
        'bbox': [x, 10, x + len(text) * 5, 20],
        'font': {'name': name, 'size': 10, 'flags': flags, 'weight': 400},
        'chars': chars,
    }


def font_line(*spans: dict) -> PdfTextLine:
    boxes = [span['bbox'] for span in spans]
    return cast(
        PdfTextLine,
        {
            'bbox': [boxes[0][0], 10, boxes[-1][2], 20],
            'spans': list(spans),
        },
    )


def kinds(name: str, flags: int = 4) -> tuple[str, ...]:
    return span_emphasis_kinds(cast(PdfTextSpan, font_span('text', name, flags)))


def styled(text: str, *runs: tuple[int, int, InlineKind]) -> tuple[InlineRange, ...]:
    return tuple(InlineRange(start, end, kind) for start, end, kind in runs)


def page_number(raw: int) -> PageNumber:
    return PageNumber(raw=raw, visible=None)


def render(*blocks: Block, page_markers: bool = False) -> str:
    output = io.StringIO()
    markdown_to_text(list(blocks), output, page_markers=page_markers)
    return output.getvalue()


def paragraph(text: str, *runs: tuple[int, int, InlineKind]) -> Paragraph:
    page = page_number(1)
    return Paragraph(text, page, page, ranges=styled(text, *runs))


def resolved_markdown(text: str, *runs: tuple[int, int, InlineKind]) -> str:
    return render_inline(resolve_emphasis(AnnotatedText(text, styled(text, *runs))))


class EmphasisDetectionTests(unittest.TestCase):
    def test_recognizes_conventional_bold_and_italic_font_names(self) -> None:
        self.assertEqual(kinds('SourceSansPro-SemiBold'), ('bold',))
        self.assertEqual(kinds('Arial-BoldItalicMT'), ('bold', 'italic'))
        self.assertEqual(kinds('LMRoman10-Italic'), ('italic',))
        self.assertEqual(kinds('MinionPro-BoldIt'), ('bold', 'italic'))

    def test_recognizes_suffixes_with_encoding_variants(self) -> None:
        self.assertEqual(kinds('AdvTTa351d857.B+20'), ('bold',))
        self.assertEqual(kinds('AdvOT7d6df7ab.I+03'), ('italic',))

    def test_recognizes_nimbus_and_tex_font_names(self) -> None:
        self.assertEqual(kinds('NimbusRomNo9L-Medi'), ('bold',))
        self.assertEqual(kinds('NimbusRomNo9L-ReguItal'), ('italic',))
        self.assertEqual(kinds('CMBX10'), ('bold',))
        self.assertEqual(kinds('ABCDEF+CMTI9'), ('italic',))

    def test_recognizes_italic_font_flag(self) -> None:
        self.assertEqual(kinds('F12', flags=68), ('italic',))

    def test_ignores_math_italics(self) -> None:
        self.assertEqual(kinds('LMMathItalic10-Regular', flags=68), ())
        self.assertEqual(kinds('CMMI6', flags=68), ())
        self.assertEqual(kinds('LMMathSymbols10-Regular', flags=68), ())
        self.assertEqual(kinds('LMMathItalic10-Bold', flags=68), ())

    def test_ignores_regular_and_medium_faces(self) -> None:
        self.assertEqual(kinds('Roboto-Medium'), ())
        self.assertEqual(kinds('TimesNewRoman'), ())
        self.assertEqual(kinds('Digital-Regular'), ())
        self.assertEqual(kinds('NimbusSanL-Regu'), ())

    def test_merges_adjacent_spans_and_breaks_at_whitespace_spans(self) -> None:
        line = font_line(
            font_span('Some ', 'Serif-Italic'),
            font_span('words', 'Serif-BoldItalic', x=25),
            font_span(' ', x=50),
            font_span('end', 'Serif-Italic', x=55),
        )

        self.assertEqual(
            line_emphasis_ranges(line),
            (
                InlineRange(0, 10, 'italic'),
                InlineRange(5, 10, 'bold'),
                InlineRange(11, 14, 'italic'),
            ),
        )

    def test_line_records_keep_emphasis_relative_to_stripped_text(self) -> None:
        line = font_line(font_span(' plain ', x=0), font_span('word', 'Serif-Bold', x=35))
        page_obj = cast(Page, {'blocks': [{'lines': [line]}]})

        line_obj = iter_lines([page_obj])[0]

        self.assertEqual(line_obj.text, 'plain word')
        self.assertEqual(line_obj.ranges, (InlineRange(6, 10, 'bold'),))

    def test_drops_style_of_most_document_text(self) -> None:
        def line(text: str, *runs: tuple[int, int, InlineKind]) -> Line:
            return Line(text, 1, 1, 1, 10, 0, 0, 0, 0, None, None, 400, ranges=styled(text, *runs))

        lines = [
            line('mostly italic body', (0, 18, 'italic')),
            line('more italic and bold', (0, 11, 'italic'), (16, 20, 'bold')),
            line('plain'),
        ]

        drop_dominant_emphasis(lines)

        self.assertEqual(
            [line_obj.ranges for line_obj in lines], [(), styled('', (16, 20, 'bold')), ()]
        )

    def test_keeps_minority_styles(self) -> None:
        text = 'plain body text with one word'
        lines = [
            Line(
                text,
                1,
                1,
                1,
                10,
                0,
                0,
                0,
                0,
                None,
                None,
                400,
                ranges=styled(text, (25, 29, 'italic')),
            )
        ]

        drop_dominant_emphasis(lines)

        self.assertEqual(lines[0].ranges, (InlineRange(25, 29, 'italic'),))


class EmphasisResolutionTests(unittest.TestCase):
    def test_renders_bold_and_italic_parts_of_paragraphs(self) -> None:
        self.assertEqual(
            render(paragraph('A bold and italic text', (2, 6, 'bold'), (11, 17, 'italic'))),
            'A **bold** and *italic* text\n',
        )

    def test_renders_completely_styled_paragraphs(self) -> None:
        self.assertEqual(render(paragraph('All bold', (0, 8, 'bold'))), '**All bold**\n')

    def test_merges_ranges_across_whitespace_and_line_breaks(self) -> None:
        text = f'Set in{HARD_LINE_BREAK}\nitalics'
        self.assertEqual(
            render(paragraph(text, (0, 6, 'italic'), (8, 15, 'italic'))),
            '*Set in\\\nitalics*\n',
        )

    def test_nests_bold_within_italic(self) -> None:
        self.assertEqual(
            resolved_markdown('an emphasized word', (0, 18, 'italic'), (14, 18, 'bold')),
            '*an emphasized **word***',
        )

    def test_moves_trailing_punctuation_outside_before_letters(self) -> None:
        self.assertEqual(resolved_markdown('word.next', (0, 5, 'italic')), '*word*.next')
        self.assertEqual(resolved_markdown('word. next', (0, 5, 'italic')), '*word.* next')

    def test_moves_leading_punctuation_and_symbols_outside_after_letters(self) -> None:
        self.assertEqual(resolved_markdown('x"quote" y', (1, 8, 'italic')), 'x"*quote"* y')
        self.assertEqual(resolved_markdown('ab€5 y', (2, 4, 'italic')), 'ab€*5* y')

    def test_drops_ranges_of_punctuation_only_between_letters(self) -> None:
        self.assertEqual(resolved_markdown('a-b', (1, 2, 'italic')), 'a-b')

    def test_moves_scripts_outside_only_where_delimiters_fail(self) -> None:
        text = 'word3 next'
        sup = (4, 5, 'sup')
        self.assertEqual(resolved_markdown(text, (0, 5, 'italic'), sup), '*word<sup>3</sup>* next')
        self.assertEqual(
            resolved_markdown('word3next', (0, 5, 'italic'), sup), '*word*<sup>3</sup>next'
        )

    def test_excludes_partly_covered_scripts(self) -> None:
        self.assertEqual(
            resolved_markdown('x12 y', (0, 2, 'bold'), (1, 3, 'sup')), '**x**<sup>12</sup> y'
        )

    def test_removes_overlap_from_shorter_of_partly_overlapping_ranges(self) -> None:
        self.assertEqual(
            resolved_markdown('aa bb c', (0, 5, 'italic'), (3, 7, 'bold')), '*aa bb* **c**'
        )
        self.assertEqual(
            resolved_markdown('a bb cc', (0, 4, 'italic'), (2, 7, 'bold')), '*a* **bb cc**'
        )

    def test_moves_punctuation_out_of_ambiguous_opener_within_triple_run(self) -> None:
        # `.*(` could close the strong emphasis opened by `***` instead.
        self.assertEqual(
            resolved_markdown('ab c.(de', (0, 8, 'bold'), (0, 2, 'italic'), (5, 8, 'italic')),
            '***ab* c.(*de***',
        )

    def test_drops_ambiguous_opener_within_word_inside_triple_run(self) -> None:
        self.assertEqual(
            resolved_markdown('ab cde', (0, 6, 'bold'), (0, 2, 'italic'), (4, 6, 'italic')),
            '***ab* cde**',
        )

    def test_keeps_opener_within_word_where_rule_of_3_prevents_closing(self) -> None:
        self.assertEqual(
            resolved_markdown('ab cde', (0, 6, 'bold'), (4, 6, 'italic')), '**ab c*de***'
        )

    def test_list_markers_stay_outside_emphasis(self) -> None:
        text = '- First item\n  continued\n- Second'
        self.assertEqual(
            render(paragraph(text, (0, len(text), 'bold'))),
            '- **First item\n  continued**\n- **Second**\n',
        )

    def test_block_quotes_keep_emphasis_after_their_markers(self) -> None:
        page = page_number(1)
        text = 'Quote set\nin italics'
        block = BlockQuote(text, page, page, ranges=styled(text, (0, len(text), 'italic')))

        self.assertEqual(render(block), '> *Quote set\n> in italics*\n')

    def test_page_markers_split_emphasis(self) -> None:
        fragments = [
            TextFragment('one two', page_number(1), ranges=styled('', (0, 7, 'italic'))),
            TextFragment('three', page_number(2), ' ', ranges=styled('', (0, 5, 'italic'))),
        ]
        block = Paragraph('one two three', page_number(1), page_number(2), fragments=fragments)

        self.assertEqual(
            render(block, page_markers=True), '<<PAGE:1>>*one two* <<PAGE:2>>*three*\n'
        )
        self.assertEqual(render(block), '*one two three*\n')

    def test_escapes_underscores_and_backslashes_next_to_delimiters(self) -> None:
        self.assertEqual(render(paragraph('foo_bar', (0, 3, 'italic'))), '*foo*\\_bar\n')
        self.assertEqual(render(paragraph('a\\ b', (0, 2, 'italic'))), '*a\\\\* b\n')


class DisplayBlockEmphasisTests(unittest.TestCase):
    def heading(self, text: str, *runs: tuple[int, int, InlineKind]) -> Heading:
        page = page_number(1)
        return Heading(text, page, page, ranges=styled(text, *runs), level=2)

    def test_headings_drop_bold(self) -> None:
        self.assertEqual(render(self.heading('Bold title', (0, 4, 'bold'))), '## Bold title\n')

    def test_headings_drop_italics_covering_all_text(self) -> None:
        self.assertEqual(
            render(self.heading('An italic title.', (0, 15, 'italic'))), '## An italic title.\n'
        )

    def test_headings_keep_partial_italics(self) -> None:
        self.assertEqual(
            render(self.heading('About Beldi foods', (6, 11, 'italic'))),
            '## About *Beldi* foods\n',
        )

    def test_strong_paragraphs_drop_bold_and_keep_partial_italics(self) -> None:
        page = page_number(1)
        text = 'Edited by Some One'
        block = StrongParagraph(
            text, page, page, ranges=styled(text, (0, 18, 'bold'), (10, 18, 'italic'))
        )

        self.assertEqual(render(block), '**Edited by *Some One***\n')

    def test_strong_paragraphs_avoid_openers_that_could_close_their_emphasis(self) -> None:
        page = page_number(1)
        text = 'ab c.(de'
        block = StrongParagraph(
            text, page, page, ranges=styled(text, (0, 2, 'italic'), (5, 8, 'italic'))
        )

        self.assertEqual(render(block), '***ab* c.(*de***\n')


if __name__ == '__main__':
    unittest.main()
