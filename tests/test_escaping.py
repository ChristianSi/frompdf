import unittest

from frompdf.escaping import escape_markdown, shift_index
from frompdf.models import HARD_LINE_BREAK, ScriptRange
from frompdf.scripts import AnnotatedText


def escaped(text: str, **options: bool) -> str:
    return escape_markdown(AnnotatedText(text), **options)[0].text


class InlineEscapeTests(unittest.TestCase):
    def test_escapes_asterisks_and_backticks_everywhere(self) -> None:
        self.assertEqual(escaped('72*72*1 and `code`'), '72\\*72\\*1 and \\`code\\`')
        self.assertEqual(escaped('***'), '\\*\\*\\*')

    def test_escapes_underscores_only_outside_words(self) -> None:
        self.assertEqual(escaped('snake_case_name'), 'snake_case_name')
        self.assertEqual(
            escaped('_emphasis_ and title=Chick_'), '\\_emphasis\\_ and title=Chick\\_'
        )

    def test_escapes_backslashes_only_where_markdown_reads_them(self) -> None:
        self.assertEqual(escaped('C:\\temp\\file'), 'C:\\temp\\file')
        self.assertEqual(escaped('a\\*b'), 'a\\\\\\*b')
        self.assertEqual(escaped('ends\\'), 'ends\\\\')
        self.assertEqual(
            escaped(f'ends\\{HARD_LINE_BREAK}\nnext'), f'ends\\\\{HARD_LINE_BREAK}\nnext'
        )

    def test_escapes_entities_and_tags_but_not_plain_ampersands_or_comparisons(self) -> None:
        self.assertEqual(escaped('Tom & Jerry &amp; &#42;'), 'Tom & Jerry \\&amp; \\&#42;')
        self.assertEqual(escaped('a < b <i>x</i> <!-- c'), 'a < b \\<i>x\\</i> \\<!-- c')
        self.assertEqual(escaped('3 <5 and a < b'), '3 <5 and a < b')

    def test_leaves_square_brackets_readable(self) -> None:
        self.assertEqual(escaped('see [1] and [sic]'), 'see [1] and [sic]')

    def test_leaves_script_ranges_to_their_own_escaping(self) -> None:
        value = AnnotatedText('x*_1 *', (ScriptRange(1, 4, 'sup'),))

        result, insertions = escape_markdown(value)

        self.assertEqual(result.text, 'x*_1 \\*')
        self.assertEqual(result.scripts, (ScriptRange(1, 4, 'sup'),))
        self.assertEqual(insertions, [5])


class LineStartEscapeTests(unittest.TestCase):
    def test_escapes_headings_quotes_and_fences_at_line_starts(self) -> None:
        self.assertEqual(escaped('# The Author(s)'), '\\# The Author(s)')
        self.assertEqual(escaped('text\n## more\n> quote'), 'text\n\\## more\n\\> quote')
        self.assertEqual(escaped('~~~ fence'), '\\~~~ fence')
        self.assertEqual(escaped('#hashtag and C# code'), '#hashtag and C# code')

    def test_escapes_dash_and_equals_lines(self) -> None:
        self.assertEqual(escaped('---'), '\\---')
        self.assertEqual(escaped('text\n-'), 'text\n\\-')
        self.assertEqual(escaped('text\n==='), 'text\n\\===')
        self.assertEqual(escaped('==='), '===')

    def test_keeps_list_markers_starting_a_block(self) -> None:
        self.assertEqual(escaped('- item\nmore'), '- item\nmore')
        self.assertEqual(escaped('3. item'), '3. item')

    def test_keeps_sibling_list_markers_of_a_block_starting_as_list(self) -> None:
        self.assertEqual(escaped('- one\n- two\n+ three'), '- one\n- two\n\\+ three')
        self.assertEqual(escaped('1. one\n2. two\n1) new'), '1. one\n2. two\n1\\) new')

    def test_escapes_list_markers_interrupting_a_paragraph(self) -> None:
        self.assertEqual(escaped('text\n+ C\n- item'), 'text\n\\+ C\n\\- item')
        self.assertEqual(escaped('properties:\n1. first'), 'properties:\n1\\. first')

    def test_keeps_numbers_that_cannot_interrupt_a_paragraph(self) -> None:
        self.assertEqual(escaped('Am\n23. Dezember 1917'), 'Am\n23. Dezember 1917')
        self.assertEqual(escaped('Pages\n1.'), 'Pages\n1.')
        self.assertEqual(escaped('-1 and -2'), '-1 and -2')

    def test_escapes_empty_list_items_and_list_markers_when_lists_are_not_kept(self) -> None:
        self.assertEqual(escaped('-'), '\\-')
        self.assertEqual(escaped('2.'), '2\\.')
        self.assertEqual(escaped('1. one', block_list_markers=False), '1\\. one')

    def test_checks_lines_after_hard_breaks_and_indentation(self) -> None:
        self.assertEqual(
            escaped(f'first{HARD_LINE_BREAK}\n  > second'), f'first{HARD_LINE_BREAK}\n  \\> second'
        )

    def test_escapes_link_reference_definitions_at_block_start(self) -> None:
        self.assertEqual(escaped('[1]: Author, Title'), '\\[1]: Author, Title')

    def test_skips_first_line_after_opening_markup(self) -> None:
        self.assertEqual(escaped('# one\n# two', block_line_start=False), '# one\n\\# two')


class HeadingEscapeTests(unittest.TestCase):
    def test_escapes_closing_sequence_but_not_line_start_syntax(self) -> None:
        self.assertEqual(escaped('Roy Shadmon #', heading=True), 'Roy Shadmon \\#')
        self.assertEqual(escaped('1. Introduction', heading=True), '1. Introduction')
        self.assertEqual(escaped('C# Basics', heading=True), 'C# Basics')


class ShiftIndexTests(unittest.TestCase):
    def test_places_boundaries_before_backslashes_inserted_there(self) -> None:
        insertions = [0, 5]

        self.assertEqual(shift_index(insertions, 0), 0)
        self.assertEqual(shift_index(insertions, 3), 4)
        self.assertEqual(shift_index(insertions, 5), 6)
        self.assertEqual(shift_index(insertions, 6), 8)


if __name__ == '__main__':
    unittest.main()
