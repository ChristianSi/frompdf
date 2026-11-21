import io
import unittest
from collections import Counter
from dataclasses import replace

from frompdf.footnotes import (
    DetectedNote,
    build_footnote,
    extract_footnotes,
    page_body_sizes,
    place_footnotes,
    scan_note_sizes,
    scan_note_starts,
)
from frompdf.models import Footnote, Heading, Line, PageNumber, Paragraph, TextFragment
from frompdf.output import markdown_to_text
from frompdf.rules import Rule


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


def heading(text: str, level: int = 2, page: int = 1) -> Heading:
    source = PageNumber(page, None)
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


def paragraph(text: str, page: int = 1, end_page: int | None = None) -> Paragraph:
    return Paragraph(text, PageNumber(page, None), PageNumber(end_page or page, None))


def scanned_body(lines: int = 5, pitch: float = 14.0) -> list[Line]:
    """Return body lines of a scanned page, set pitch points apart."""
    return [
        line(
            f'Body text line {index} running across the whole column.', 20 + index * pitch, size=10
        )
        for index in range(lines)
    ]


class PageBodySizeTests(unittest.TestCase):
    def sized(self, page: int, sizes: dict[float, int]) -> list[Line]:
        return [line('x' * chars, 10, page=page, size=size) for size, chars in sizes.items()]

    def test_part_set_in_another_size_uses_its_largest_common_size(self) -> None:
        pages = {
            1: self.sized(1, {11: 700, 9: 300}),
            2: self.sized(2, {11: 400, 9: 600}),
            3: self.sized(3, {11: 700, 9: 300}),
            4: self.sized(4, {13: 900}),
            9: self.sized(9, {13: 900}),
        }
        sizes = page_body_sizes(pages, 13)
        # Page 2 is mostly notes, but its body size is still that of its part.
        # Page 3 neighbors text in the document size, which it keeps.
        self.assertEqual([sizes[page] for page in pages], [11, 11, 13, 13, 13])

    def test_keeps_document_size_where_used_or_where_text_is_scarce(self) -> None:
        pages = {
            1: self.sized(1, {10: 250, 8: 750}),
            2: self.sized(2, {10: 250, 8: 750}),
            5: self.sized(5, {12: 400}),
        }
        self.assertEqual(page_body_sizes(pages, 10), {1: 10, 2: 10, 5: 10})


class ScanNoteTests(unittest.TestCase):
    def test_runs_of_closely_set_lines_count_as_small(self) -> None:
        notes = [line(f'Note line {index}', 110 + index * 10, size=10) for index in range(3)]
        page = scanned_body() + notes
        sizes = [item.font_size for item in scan_note_sizes(page, 10, [])]
        self.assertEqual(sizes[:5], [10] * 5)
        self.assertTrue(all(size is not None and size <= 9 for size in sizes[5:]))
        # A single close pair can be an error in measured baselines.
        pair = scanned_body() + notes[:2]
        self.assertEqual(scan_note_sizes(pair, 10, []), pair)

    def test_lines_below_a_low_rule_are_small_where_they_start_like_notes(self) -> None:
        rule = Rule(True, 100, 20, 80)
        for text, small in [('* See the appendix.', True), ('Ordinary text below.', False)]:
            with self.subTest(text=text):
                page = scanned_body() + [line(text, 110, size=10)]
                result = scan_note_sizes(page, 10, [rule])
                self.assertEqual((result[-1].font_size or 10) < 10, small)
                self.assertEqual(result[:5], page[:5])
        # A rule high on the page separates no notes.
        page = scanned_body() + [line('* See the appendix.', 110, size=10)]
        self.assertEqual(scan_note_sizes(page, 10, [Rule(True, 10, 20, 80)]), page)

    def test_hanging_indent_and_misread_labels_number_notes_in_order(self) -> None:
        region = [
            line('iNetscher, p. 156, indeed insists on Dutch sovereignty', 100),
            replace(line('over Siak, but speaks otherwise.', 110), x1=23),
            line('^Memorandum for the guidance of Mr. Anderson, with', 120),
            replace(line('the letters, G/34/89.', 130), x1=23),
            line('3See below, pp. 210-22.', 140),
            line('Ibid., p. 12.', 150),
        ]
        starts = scan_note_starts(region)
        self.assertEqual(sorted(starts), [0, 2, 4, 5])
        self.assertEqual([label for label, _, _ in starts.values()], ['1', '2', '3', '4'])
        self.assertEqual(
            [text_line.text for _, text_line, _ in starts.values()],
            [
                'Netscher, p. 156, indeed insists on Dutch sovereignty',
                'Memorandum for the guidance of Mr. Anderson, with',
                'See below, pp. 210-22.',
                'Ibid., p. 12.',
            ],
        )

    def test_numbers_continue_from_labels_read_as_numbers(self) -> None:
        region = [line('^First note.', 100), line('8Second note.', 110), line('®Third.', 120)]
        starts = scan_note_starts(region)
        self.assertEqual([label for label, _, _ in starts.values()], ['7', '8', '9'])

    def test_symbols_and_misread_daggers_mark_notes_in_order(self) -> None:
        region = [
            line('* Marsden’s Sumatra, page 409.', 100),
            line('t Ibid, page 439.', 110),
            line('X Ibid, page 441.', 120),
        ]
        starts = scan_note_starts(region)
        self.assertEqual([label for label, _, _ in starts.values()], ['*', '†', '‡'])
        self.assertEqual(starts[1][1].text, 'Ibid, page 439.')
        # Without a symbol before, a letter is just a word.
        self.assertEqual(scan_note_starts(region[1:]), {})

    def test_extracts_notes_with_misread_labels_on_scanned_pages_only(self) -> None:
        notes = [
            line('^A first note explaining the text.', 100, size=8),
            replace(line('continued on its second line.', 110, size=8), x1=24),
            line('®Ibid., p. 5.', 120, size=8),
        ]
        lines = scanned_body() + notes
        remaining, detected = extract_footnotes(lines, 10, {1})
        self.assertEqual(remaining, lines[:5])
        self.assertEqual([note.label for note in detected], ['1', '2'])
        self.assertEqual(len(detected[0].paragraphs[0]), 2)
        self.assertEqual(extract_footnotes(lines, 10), (lines, []))


class FootnotePlacementTests(unittest.TestCase):
    def test_single_numbering_sequence_is_document_endmatter_at_h2(self) -> None:
        first, last = note('4'), note('8', 2)
        intermediate = heading('Intermediate')
        subsection, references = heading('Subsection', 3, 3), heading('References', page=4)
        blocks = place_footnotes([first, intermediate, last, subsection, references])
        self.assertEqual(
            [b.text for b in blocks],
            ['Intermediate', 'Subsection', 'References', 'Notes', 'Note 4', 'Note 8'],
        )
        self.assertEqual(blocks[3], heading('Notes', 2))

    def test_continuous_notes_covering_major_sections_wait_for_major_boundary(self) -> None:
        first, last = note('1'), note('2', 2)
        initial = heading('Initial subsection', 3)
        major = heading('Another major section', 2, 2)
        minor = heading('Later subsection', 3, 3)
        conclusion = heading('Conclusion', 2, 4)
        restarted = note('1', 4)
        result = place_footnotes([initial, first, major, last, minor, conclusion, restarted])
        self.assertEqual(
            result,
            [
                initial,
                major,
                minor,
                heading('Notes', 3),
                first,
                last,
                conclusion,
                heading('Notes', 3, 4),
                restarted,
            ],
        )

    def test_notes_covering_h4_sections_can_be_siblings_before_h4_bibliography(self) -> None:
        initial = heading('Prologue', 4)
        chapter = heading('Chapter', 4, 2)
        bibliography = heading('Bibliography', 4, 3)
        appendix = heading('Appendix', 3, 4)
        appendix_section = heading('Appendix section', 4, 4)
        first, last, restarted = note('1'), note('2', 2), note('1', 4)
        result = place_footnotes(
            [initial, first, chapter, last, bibliography, appendix, appendix_section, restarted]
        )
        self.assertEqual(
            result[result.index(bibliography) - 3 : result.index(bibliography)],
            [heading('Notes', 4), first, last],
        )
        self.assertEqual(result[-2:], [heading('Notes', 4, 4), restarted])

    def test_restart_boundary_prevents_waiting_for_a_later_major_heading(self) -> None:
        initial = heading('Major section', 2)
        next_section = heading('New numbered section', 4, 2)
        conclusion = heading('Conclusion', 2, 3)
        first, restarted = note('1'), note('1', 2)
        result = place_footnotes([initial, first, next_section, restarted, conclusion])
        self.assertEqual(result[:4], [initial, heading('Notes', 4), first, next_section])

    def test_equal_or_smaller_labels_share_one_title_at_the_same_boundary(self) -> None:
        source = [note('4'), note('7'), note('7'), note('2'), heading('References')]
        blocks = place_footnotes(source, 'Anmerkungen')
        titles = [b for b in blocks if isinstance(b, Heading) and b.text == 'Anmerkungen']
        self.assertEqual(len(titles), 1)
        self.assertTrue(all(b.level == 2 for b in titles))
        self.assertEqual([b.label for b in blocks if isinstance(b, Footnote)], ['4', '7', '7', '2'])

    def test_restart_without_a_section_boundary_does_not_create_adjacent_titles(self) -> None:
        boundary = heading('Next section')
        blocks = place_footnotes([note('1'), note('1'), boundary])
        self.assertEqual([b.text for b in blocks], ['Notes', 'Note 1', 'Note 1', 'Next section'])

    def test_notes_need_not_be_children_but_cannot_parent_the_following_section(self) -> None:
        for previous_level, following_level in [(4, 4), (4, 2), (2, 4), (1, 1), (5, 3), (6, 4)]:
            with self.subTest(previous=previous_level, following=following_level):
                previous = heading('Current section', previous_level)
                following = heading('Next section', following_level, 2)
                result = place_footnotes([previous, note('1'), following, note('1', 2)])
                self.assertEqual(result[1], heading('Notes', max(3, following_level)))
                self.assertIsInstance(result[2], Footnote)
                self.assertIs(result[3], following)

    def test_restart_before_any_heading_level_including_h6_needs_no_extra_level(self) -> None:
        for level in [1, 2, 3, 4, 5, 6]:
            with self.subTest(level=level):
                boundary = heading('Next section', level, 2)
                result = place_footnotes([note('1'), boundary, note('1', 2)])
                self.assertIs(result[2], boundary)
                self.assertIsInstance(result[1], Footnote)
                self.assertEqual(result[0], heading('Notes', max(3, level)))

    def test_single_notes_section_at_document_end_does_not_inherit_last_heading_level(self) -> None:
        paragraph = Paragraph('Last body paragraph.', PageNumber(1, None), PageNumber(1, None))
        for initial in [[], [heading('Chapter', 4)], [heading('Small subsection', 6)]]:
            result = place_footnotes(initial + [note('1'), paragraph])
            self.assertEqual(
                [b.text for b in result[-3:]], ['Last body paragraph.', 'Notes', 'Note 1']
            )
            self.assertEqual(result[-2], heading('Notes', 2))

    def test_same_page_restart_moves_old_notes_before_the_midpage_heading(self) -> None:
        first = note('1', 29)
        old_end = [note('11', 32), note('12', 32)]
        new_notes = [note('1', 32), note('2', 33)]
        chapter_one = heading('Chapter one', 4, 29)
        chapter_two = heading('Chapter two', 4, 32)
        chapter_three = heading('Chapter three', 4, 35)
        result = place_footnotes(
            [chapter_one, first, chapter_two, *old_end, *new_notes, chapter_three]
        )
        self.assertEqual(
            result,
            [
                chapter_one,
                heading('Notes', 4, 29),
                first,
                *old_end,
                chapter_two,
                heading('Notes', 4, 32),
                *new_notes,
                chapter_three,
            ],
        )

    def test_same_page_coincidence_without_restart_does_not_move_notes_backwards(self) -> None:
        first, last = note('1'), note('2', 2)
        middle, following = heading('Subsection', 4, 2), heading('Following', 4, 3)
        result = place_footnotes([heading('Chapter', 4), first, middle, last, following])
        self.assertLess(result.index(middle), result.index(first))
        self.assertLess(result.index(following), result.index(last))

    def test_restart_does_not_move_a_group_before_its_own_opening_heading(self) -> None:
        first, second = heading('First chapter', 4), heading('Second chapter', 4, 2)
        result = place_footnotes([first, note('1'), second, note('1', 2)])
        self.assertEqual(
            result,
            [first, heading('Notes', 4), note('1'), second, heading('Notes', 4, 2), note('1', 2)],
        )

    def test_continuing_labels_above_next_page_restart_need_preheading_prose(self) -> None:
        page = PageNumber(43, None)
        prose = Paragraph('End of preceding chapter.', page, page)
        boundary, following = heading('Chapter five', 4, 43), heading('Chapter six', 4, 45)
        old, new = note('5', 43), note('1', 44)
        result = place_footnotes([prose, boundary, old, new, following])
        self.assertEqual(
            result,
            [
                prose,
                heading('Notes', 4, 43),
                old,
                boundary,
                heading('Notes', 4, 44),
                new,
                following,
            ],
        )
        without_prose = place_footnotes([boundary, old, new, following])
        self.assertEqual(without_prose, [boundary, heading('Notes', 4, 43), old, new, following])

    def test_distant_restart_does_not_pull_notes_before_an_earlier_heading(self) -> None:
        boundary, following = heading('Subsection', 4, 2), heading('Following', 4, 4)
        first, last, restarted = note('1'), note('2', 2), note('1', 4)
        result = place_footnotes([first, boundary, last, following, restarted])
        self.assertLess(result.index(boundary), result.index(first))
        self.assertLess(result.index(last), result.index(following))

    def test_ambiguous_restarts_never_reverse_note_order(self) -> None:
        page = PageNumber(1, None)
        prose = Paragraph('Text before the heading.', page, page)
        notes = [note('1'), note('2'), note('2'), note('1')]
        result = place_footnotes([prose, heading('Section'), *notes, heading('Next')])
        self.assertEqual([id(b) for b in result if isinstance(b, Footnote)], [id(b) for b in notes])
        self.assertEqual(sum(isinstance(b, Heading) and b.text == 'Notes' for b in result), 1)

    def test_cross_page_note_keeps_its_fragments_when_moved_before_a_heading(self) -> None:
        first, last, restarted = note('1'), note('2', 2), note('1', 3)
        last.end_page = PageNumber(3, None)
        fragments = [
            TextFragment('Some text', last.start_page),
            TextFragment('continued.', last.end_page, '\n'),
        ]
        last.fragments = fragments
        middle, following = heading('Section two', 4, 3), heading('Section three', 4, 4)
        result = place_footnotes(
            [heading('Section one', 4), first, middle, last, restarted, following]
        )
        self.assertIs(result[result.index(middle) - 1], last)
        self.assertEqual(last.end_page.raw, 3)
        self.assertIs(last.fragments, fragments)

    def test_existing_notes_heading_is_not_merged_or_releveled(self) -> None:
        existing = heading('Notes', 2, 2)
        result = place_footnotes([heading('Chapter'), note('1'), existing])
        self.assertIs(result[1], existing)
        self.assertEqual(existing.level, 2)

    def test_no_notes_leaves_blocks_untouched(self) -> None:
        blocks = [heading('Existing title', 5)]
        self.assertEqual(place_footnotes(blocks), blocks)


class PageNotePlacementTests(unittest.TestCase):
    def test_notes_numbered_by_page_follow_the_last_paragraph_starting_there(self) -> None:
        first = paragraph('Starts on page one.')
        spanning = paragraph('Starts on page one, ends on two.', 1, 2)
        second = paragraph('Starts on page two.', 2)
        boundary = heading('Next section', 2, 3)
        blocks = place_footnotes(
            [first, spanning, note('1'), note('2'), second, note('1', 2), boundary],
            'Anmerkungen',
        )
        self.assertEqual(
            [block.text for block in blocks],
            [
                'Starts on page one.',
                'Starts on page one, ends on two.',
                'Anmerkungen:',
                'Note 1',
                'Note 2',
                'Starts on page two.',
                'Anmerkungen:',
                'Note 1',
                'Next section',
            ],
        )
        self.assertIsInstance(blocks[2], Paragraph)

    def test_notes_numbered_by_section_keep_their_sections(self) -> None:
        # A heading between restarts tells of numbering by section.
        source = [note('1'), heading('Next section', 2, 2), note('1', 3)]
        blocks = place_footnotes(source)
        self.assertEqual(sum(block.text == 'Notes' for block in blocks), 2)

    def test_symbol_notes_are_by_page_and_precede_headings_ending_the_page(self) -> None:
        text = paragraph('Body text.')
        title = heading('Chapter two')
        source = [text, title, note('*'), note('†'), paragraph('More text.', 2)]
        blocks = place_footnotes(source)
        self.assertEqual(
            [block.text for block in blocks],
            ['Body text.', 'Notes:', 'Note *', 'Note †', 'Chapter two', 'More text.'],
        )
        output = io.StringIO()
        markdown_to_text(blocks[1:4], output)
        self.assertEqual(output.getvalue(), 'Notes:\n\n- \\* Note \\*\n- † Note †\n')

    def test_notes_of_successive_pages_at_one_place_form_separate_lists(self) -> None:
        source = [
            paragraph('Long paragraph.', 1, 4),
            note('1'),
            note('2'),
            note('1', 2),
            note('*', 3),
            note('*', 4),
        ]
        output = io.StringIO()
        markdown_to_text(place_footnotes(source), output)
        self.assertEqual(
            output.getvalue(),
            'Long paragraph.\n\nNotes:\n\n1. Note 1\n2. Note 2\n\n<!-- -->\n\n'
            '1. Note 1\n\n<!-- -->\n\n- \\* Note \\*\n\n<!-- -->\n\n- \\* Note \\*\n',
        )


class FootnoteTextTests(unittest.TestCase):
    def test_restarted_groups_share_a_title_but_render_as_separate_numbered_lists(self) -> None:
        blocks = place_footnotes(
            [note('4'), note('7'), note('7', 2), note('2', 2), heading('Next section', 2, 3)],
            'Anmerkungen',
        )
        output = io.StringIO()
        markdown_to_text(blocks, output, page_markers=True)
        self.assertEqual(
            output.getvalue(),
            '## [[PAGE:1]]Anmerkungen\n\n'
            '4. Note 4\n7. Note 7\n\n<!-- -->\n\n'
            '7. [[PAGE:2]]Note 7\n\n<!-- -->\n\n2. Note 2\n\n'
            '## [[PAGE:3]]Next section\n',
        )

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
            output.getvalue(), '1. [[PAGE:1]]Some international\n   [[PAGE:2]]evidence follows.\n'
        )

    def test_defers_marker_to_next_note_when_repair_consumes_whole_page_fragment(self) -> None:
        pages = {1: PageNumber(1, None), 2: PageNumber(2, None)}
        detected = DetectedNote('1', [[line('Some inter-', 100), line('national', 100, page=2)]])
        built = build_footnote(detected, pages, Counter({'international': 2}), set(), set())
        output = io.StringIO()
        markdown_to_text([built, note('2', 2)], output, page_markers=True)
        self.assertEqual(
            output.getvalue(), '1. [[PAGE:1]]Some international\n2. [[PAGE:2]]Note 2\n'
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
            '[[PAGE:3|VISIBLE:9]]Body.\n\n'
            '## [[PAGE:1|VISIBLE:7]]Notes\n\n'
            '12. Some international\n    [[PAGE:2|VISIBLE:8]]evidence.\n\n'
            '    A second paragraph.\n15. Note 15\n\n'
            '## [[PAGE:3|VISIBLE:9]]References\n',
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
                        '1. [[PAGE:1]]Some ordinary\n   [[PAGE:2]]continuation text.\n',
                    )
                else:
                    self.assertEqual(
                        output.getvalue(),
                        '1. [[PAGE:1]]A well-known\n   [[PAGE:2]]result.\n',
                    )


if __name__ == '__main__':
    unittest.main()
