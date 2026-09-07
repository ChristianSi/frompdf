import io
import unittest
from collections import Counter
from dataclasses import replace

from frompdf.footnotes import DetectedNote, build_footnote, extract_footnotes, place_footnotes
from frompdf.models import Footnote, Heading, Line, PageNumber, Paragraph
from frompdf.output import markdown_to_text


def line(text: str, y: float, *, page: int = 1, size: float = 8, block: int = 2) -> Line:
    return Line(text, page, block, int(y), size, 20, y, 220, y + size, None, None, 400)


def body(page: int = 1) -> list[Line]:
    return [
        line(
            'An ordinary body paragraph with enough text to identify its layout.',
            20,
            page=page,
            size=10,
            block=1,
        ),
        line('The second line completes the body paragraph.', 34, page=page, size=10, block=1),
    ]


def note(label: str, page: int = 1) -> Footnote:
    source = PageNumber(page, None)
    return Footnote('Note ' + label, source, source, label=label)


def heading(text: str, level: int = 2) -> Heading:
    source = PageNumber(1, None)
    return Heading(text, source, source, level=level)


class FootnoteDetectionTests(unittest.TestCase):
    def test_keeps_short_notes_and_ignores_wrapped_year(self) -> None:
        lines = body() + [
            line('7 The event happened in August', 100),
            line('1944 according to the surviving records.', 110),
            line('9 Ebd.', 120),
        ]
        remaining, notes = extract_footnotes(lines, 10)
        self.assertEqual(remaining, lines[:2])
        self.assertEqual([n.label for n in notes], ['7', '9'])
        self.assertEqual(len(notes[0].paragraphs[0]), 2)

    def test_reconnects_detached_superscript_but_not_a_distant_number(self) -> None:
        label = replace(line('1', 100, size=5), x2=23)
        text = replace(line('An explanatory footnote beside its label.', 101, block=3), x1=27)
        remaining, notes = extract_footnotes(body() + [label, text], 10)
        self.assertEqual(len(remaining), 2)
        self.assertEqual(notes[0].paragraphs[0][0].text, text.text)
        self.assertEqual(extract_footnotes(body() + [label, replace(text, y1=120)], 10)[1], [])

    def test_font_spike_does_not_split_note_area(self) -> None:
        lines = body() + [
            line('1 First explanation.', 100),
            line('2 Another explanation with an inflated font size.', 110, size=9.3),
            line('The rest of that explanation.', 120),
        ]
        remaining, notes = extract_footnotes(lines, 10)
        self.assertEqual(len(remaining), 2)
        self.assertEqual([n.label for n in notes], ['1', '2'])

    def test_preserves_paragraph_indent_but_not_incidental_block_break(self) -> None:
        lines = body() + [
            line('1 A first sentence.', 100),
            line('Another sentence in the same paragraph.', 110, block=3),
            replace(line('A genuinely indented second paragraph.', 120, block=4), x1=25),
        ]
        _, notes = extract_footnotes(lines, 10)
        self.assertEqual([len(p) for p in notes[0].paragraphs], [2, 1])

    def test_merges_open_continuation_across_pages(self) -> None:
        lines = body() + [line('2 A note that continues into the next', 100)]
        lines += body(2) + [
            line('page before the next note begins.', 100, page=2),
            line('3 Next explanation.', 110, page=2, block=3),
        ]
        remaining, notes = extract_footnotes(lines, 10)
        self.assertEqual(len(remaining), 4)
        self.assertEqual([n.label for n in notes], ['2', '3'])
        self.assertEqual([item.page_no for item in notes[0].paragraphs[0]], [1, 2])

    def test_does_not_attach_unrelated_prefix_to_closed_or_nonadjacent_note(self) -> None:
        for ending, page in [('A complete explanation.', 2), ('An unfinished explanation', 3)]:
            with self.subTest(ending=ending, page=page):
                prefix = line('Unnumbered small text should stay here.', 100, page=page)
                lines = body() + [line('1 ' + ending, 100)]
                lines += body(page) + [prefix, line('2 Another note.', 110, page=page)]
                remaining, notes = extract_footnotes(lines, 10)
                self.assertIn(prefix, remaining)
                self.assertEqual(len(notes), 2)

    def test_protects_existing_endnotes_and_their_next_page(self) -> None:
        title = replace(line('Anmerkungen', 80, size=10, block=2), avg_weight=700)
        lines = body() + [title, line('1. Existing endnote.', 100, block=3)]
        lines += [line('2. Existing endnote on the next page.', 20, page=2)]
        remaining, notes = extract_footnotes(lines, 10)
        self.assertEqual(remaining, lines)
        self.assertEqual(notes, [])

    def test_protects_endnotes_with_a_title_the_same_size_as_the_notes(self) -> None:
        title = replace(line('Anmerkungen', 80), avg_weight=700)
        lines = body() + [title, line('1. Existing endnote.', 100, block=3)]
        self.assertEqual(extract_footnotes(lines, 10), (lines, []))

    def test_leaves_body_lists_and_small_midpage_quotes_alone(self) -> None:
        examples = [
            body() + [line('1. Body-sized ordered item.', 100, size=10)],
            body()
            + [
                line('1 Small quoted material.', 100),
                line('Normal body text resumes below the quote.', 150, size=10, block=3),
            ],
            [line('1. Endnotes occupying an entire page.', 100)],
        ]
        for lines in examples:
            with self.subTest(lines=lines):
                self.assertEqual(extract_footnotes(lines, 10), (lines, []))
        self.assertEqual(extract_footnotes(body(), None), (body(), []))

    def test_detects_column_notes_without_consuming_the_other_column(self) -> None:
        left = body() + [line('1 A note under the left column.', 100)]
        right = [replace(item, x1=260, x2=460, block_no=item.block_no + 3) for item in body()]
        right.append(replace(line('2 A note under the right column.', 100), x1=260, x2=460))
        remaining, notes = extract_footnotes(left + right, 10)
        self.assertEqual(len(remaining), 4)
        self.assertEqual([n.label for n in notes], ['1', '2'])


class FootnotePlacementTests(unittest.TestCase):
    def test_waits_until_whole_group_is_read_and_prefers_h2(self) -> None:
        first, last = note('4'), note('8', 2)
        intermediate = heading('Intermediate')
        subsection, references = heading('Subsection', 3), heading('References')
        blocks = place_footnotes([first, intermediate, last, subsection, references])
        self.assertEqual(
            [b.text for b in blocks],
            ['Intermediate', 'Subsection', 'Notes', 'Note 4', 'Note 8', 'References'],
        )
        self.assertEqual(blocks[2], heading('Notes'))

    def test_equal_or_smaller_labels_start_groups_with_h3_titles(self) -> None:
        source = [note('4'), note('7'), note('7'), note('2'), heading('References')]
        blocks = place_footnotes(source, 'Anmerkungen')
        titles = [b for b in blocks if isinstance(b, Heading) and b.text == 'Anmerkungen']
        self.assertEqual(len(titles), 3)
        self.assertTrue(all(b.level == 3 for b in titles))
        self.assertEqual([b.label for b in blocks if isinstance(b, Footnote)], ['4', '7', '7', '2'])

    def test_restart_can_precede_the_first_groups_insertion_boundary(self) -> None:
        boundary = heading('Next section')
        blocks = place_footnotes([note('1'), note('1', 2), boundary])
        self.assertEqual(
            [b.text for b in blocks], ['Notes', 'Note 1', 'Notes', 'Note 1', 'Next section']
        )

    def test_falls_back_by_heading_level_then_to_document_end(self) -> None:
        for level in [3, 4, 5, 6]:
            with self.subTest(level=level):
                boundary = heading('Next section', level)
                deeper = heading('Deeper subsection', min(level + 1, 6))
                source = [note('1'), deeper, boundary] if level < 6 else [note('1'), boundary]
                result = place_footnotes(source)
                self.assertIs(result[-1], boundary)
                self.assertIsInstance(result[-2], Footnote)
        paragraph = Paragraph('Last body paragraph.', PageNumber(1, None), PageNumber(1, None))
        self.assertEqual(
            [b.text for b in place_footnotes([note('1'), paragraph])],
            ['Last body paragraph.', 'Notes', 'Note 1'],
        )

    def test_no_notes_leaves_blocks_untouched(self) -> None:
        blocks = [heading('Existing title', 5)]
        self.assertEqual(place_footnotes(blocks), blocks)


class FootnoteTextTests(unittest.TestCase):
    def test_preserves_three_source_lines_with_list_indentation(self) -> None:
        page = PageNumber(1, None)
        detected = DetectedNote(
            '12',
            [
                [
                    line('The first line of a note', 100),
                    line('continues on the second line', 110),
                    line('and ends on the third.', 120),
                ]
            ],
        )
        built = build_footnote(detected, {1: page}, Counter(), set(), set())
        output = io.StringIO()
        markdown_to_text([built, note('15')], output)
        self.assertEqual(
            output.getvalue(),
            '12. The first line of a note\n'
            '    continues on the second line\n'
            '    and ends on the third.\n'
            '15. Note 15\n',
        )

    def test_repairs_hyphenation_without_reflowing_remaining_lines(self) -> None:
        pages = {1: PageNumber(1, None), 2: PageNumber(2, None)}
        for continuation_page in [1, 2]:
            with self.subTest(continuation_page=continuation_page):
                detected = DetectedNote(
                    '1',
                    [
                        [
                            line('An opening line', 90),
                            line('with inter-', 100),
                            line('national evidence', 110, page=continuation_page),
                            line('on a final line.', 120, page=continuation_page),
                        ]
                    ],
                )
                built = build_footnote(detected, pages, Counter({'international': 2}), set(), set())
                self.assertEqual(
                    built.text, 'An opening line\nwith international\nevidence\non a final line.'
                )

    def test_keeps_following_line_when_a_cross_page_repair_consumes_one_word_line(self) -> None:
        pages = {1: PageNumber(1, None), 2: PageNumber(2, None)}
        detected = DetectedNote(
            '1',
            [
                [
                    line('Some inter-', 100),
                    line('national', 100, page=2),
                    line('evidence follows.', 110, page=2),
                ]
            ],
        )
        built = build_footnote(detected, pages, Counter({'international': 2}), set(), set())
        output = io.StringIO()
        markdown_to_text([built], output, page_markers=True)
        self.assertEqual(
            output.getvalue(), '1. <<PAGE:1>>Some international\n   <<PAGE:2>>evidence follows.\n'
        )

    def test_defers_marker_to_next_note_when_repair_consumes_whole_page_fragment(self) -> None:
        pages = {1: PageNumber(1, None), 2: PageNumber(2, None)}
        detected = DetectedNote('1', [[line('Some inter-', 100), line('national', 100, page=2)]])
        built = build_footnote(detected, pages, Counter({'international': 2}), set(), set())
        output = io.StringIO()
        markdown_to_text([built, note('2', 2)], output, page_markers=True)
        self.assertEqual(
            output.getvalue(), '1. <<PAGE:1>>Some international\n2. <<PAGE:2>>Note 2\n'
        )

    def test_page_markers_follow_repaired_words_and_preserve_paragraphs(self) -> None:
        pages = {1: PageNumber(1, '7'), 2: PageNumber(2, '8'), 3: PageNumber(3, '9')}
        detected = DetectedNote(
            '12',
            [
                [line('Some inter-', 100), line('national evidence.', 100, page=2)],
                [line('A second paragraph.', 110, page=2)],
            ],
        )
        built = build_footnote(detected, pages, Counter({'international': 2}), set(), set())
        self.assertEqual(built.text, 'Some international\nevidence.\n\nA second paragraph.')
        blocks = [
            Paragraph('Body.', pages[3], pages[3]),
            Heading('Notes', pages[1], pages[1], level=2),
            built,
            note('15', 2),
            Heading('References', pages[3], pages[3], level=2),
        ]
        output = io.StringIO()
        markdown_to_text(blocks, output, page_markers=True)
        self.assertEqual(
            output.getvalue(),
            '<<PAGE:3|LABEL:9>>Body.\n\n'
            '## <<PAGE:1|LABEL:7>>Notes\n\n'
            '12. Some international\n    <<PAGE:2|LABEL:8>>evidence.\n\n'
            '    A second paragraph.\n15. Note 15\n\n'
            '## <<PAGE:3|LABEL:9>>References\n',
        )
        output = io.StringIO()
        markdown_to_text([built, note('15', 2)], output)
        self.assertEqual(
            output.getvalue(),
            '12. Some international\n    evidence.\n\n    A second paragraph.\n15. Note 15\n',
        )

    def test_cross_page_lexical_hyphen_and_ordinary_line_break(self) -> None:
        pages = {1: PageNumber(1, None), 2: PageNumber(2, None)}
        for left, right, expected in [
            ('A well-', 'known result.', 'A well-known\nresult.'),
            ('Some ordinary', 'continuation text.', 'Some ordinary\ncontinuation text.'),
        ]:
            with self.subTest(left=left):
                detected = DetectedNote('1', [[line(left, 100), line(right, 100, page=2)]])
                built = build_footnote(detected, pages, Counter({'well-known': 2}), set(), set())
                self.assertEqual(built.text, expected)
                self.assertEqual(len(built.fragments), 2)
                output = io.StringIO()
                markdown_to_text([built], output, page_markers=True)
                if left == 'Some ordinary':
                    self.assertEqual(
                        output.getvalue(),
                        '1. <<PAGE:1>>Some ordinary\n   <<PAGE:2>>continuation text.\n',
                    )
                else:
                    self.assertEqual(
                        output.getvalue(),
                        '1. <<PAGE:1>>A well-known\n   <<PAGE:2>>result.\n',
                    )


if __name__ == '__main__':
    unittest.main()
