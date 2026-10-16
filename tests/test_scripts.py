import io
import unittest
from collections import Counter
from typing import cast

from pdftext.schema import Line as PdfTextLine
from pdftext.schema import Page

from frompdf.blocks import detect_headings
from frompdf.footnotes import DetectedNote, build_footnote, numbered_line
from frompdf.lines import iter_lines, line_script_ranges
from frompdf.models import BlockQuote, Heading, Line, PageNumber, Paragraph, ScriptRange
from frompdf.output import markdown_to_text
from frompdf.scripts import AnnotatedText, collapse_annotated_whitespace, render_scripts
from frompdf.unhyphenation import unhyphenate_annotated_lines


def pdf_line(
    text: str,
    positions: dict[int, tuple[float, float]],
    size: float = 1,
    flagged_sup: bool = False,
    x: float = 0,
) -> PdfTextLine:
    """Put all characters in one span, starting at x, with selected reduced/shifted glyphs."""
    chars = []
    for index, char in enumerate(text):
        top, height = positions.get(index, (10, 10))
        chars.append(
            {
                'char': char,
                'bbox': [x + index * 5, top, x + index * 5 + 5, top + height],
                'font': {'size': size if index not in positions else size * height / 10},
                'rotation': 0,
            }
        )
    return cast(
        PdfTextLine,
        {
            'bbox': [
                x,
                min(c['bbox'][1] for c in chars),
                x + len(text) * 5,
                max(c['bbox'][3] for c in chars),
            ],
            'spans': [
                {'text': text, 'chars': chars, 'superscript': flagged_sup, 'subscript': False}
            ],
        },
    )


def source_line(text: str, scripts: tuple[ScriptRange, ...], page: int = 1) -> Line:
    return Line(text, page, 1, 1, 8, 0, 100, 200, 108, None, None, 400, scripts=scripts)


def repaired(*parts: AnnotatedText) -> AnnotatedText:
    return unhyphenate_annotated_lines(parts, Counter(), set(), set())


class ScriptDetectionTests(unittest.TestCase):
    def test_detects_formula_digits_inside_one_span_with_placeholder_font_sizes(self) -> None:
        line = pdf_line('GaV4S8', {3: (14.5, 6.7), 5: (14.5, 6.7)})
        self.assertEqual(
            render_scripts('GaV4S8', line_script_ranges(line)), 'GaV<sub>4</sub>S<sub>8</sub>'
        )

    def test_corrects_wrong_upstream_direction_and_ignores_whitespace_geometry(self) -> None:
        line = pdf_line('at TC ', {4: (14.5, 6.7)}, flagged_sup=True)
        line['spans'][0]['chars'][-1]['bbox'] = [30, 30, 30, 30]  # type: ignore[typeddict-item]
        self.assertEqual(render_scripts('at TC ', line_script_ranges(line)), 'at T<sub>C</sub> ')

    def test_groups_citation_range_without_consuming_ordinary_period(self) -> None:
        line = pdf_line('text1–4.', {i: (8.3, 8) for i in (4, 5, 6)})
        self.assertEqual(
            render_scripts('text1–4.', line_script_ranges(line)), 'text<sup>1–4</sup>.'
        )

    def test_detects_multiple_letters_and_moderately_raised_graf_style_marker(self) -> None:
        for text, positions, expected in (
            ('32nd text', {2: (8, 6.7), 3: (8, 6.7)}, '32<sup>nd</sup> text'),
            ('word.1', {5: (10.4, 5.8)}, 'word.<sup>1</sup>'),
        ):
            with self.subTest(text=text):
                self.assertEqual(
                    render_scripts(text, line_script_ranges(pdf_line(text, positions))), expected
                )

    def test_real_font_sizes_and_multi_span_mathematical_subscript(self) -> None:
        line = pdf_line('p j+1 text', {i: (14, 7) for i in (2, 3, 4)}, size=10)
        span = line['spans'][0]
        line['spans'] = [
            {**span, 'text': span['text'][a:b], 'chars': span['chars'][a:b]}
            for a, b in [(0, 2), (2, 3), (3, 5), (5, 10)]
        ]
        self.assertEqual(
            render_scripts('p j+1 text', line_script_ranges(line)), 'p <sub>j+1</sub> text'
        )

    def test_leaves_small_caps_baseline_digits_and_unshifted_small_text_plain(self) -> None:
        for positions in ({}, {3: (13, 7)}, {3: (11.5, 7)}, {3: (10, 10)}):
            with self.subTest(positions=positions):
                self.assertEqual(
                    line_script_ranges(pdf_line('GaV4S8', positions, flagged_sup=True)), ()
                )

    def test_leaves_standalone_small_character_and_encoded_superscript_plain(self) -> None:
        self.assertEqual(line_script_ranges(pdf_line('1', {0: (8, 7)})), ())
        self.assertEqual(line_script_ranges(pdf_line('word²', {4: (8, 7)})), ())

    def test_rotated_or_unpositioned_candidate_is_not_marked(self) -> None:
        for bad_geometry in ('rotation', 'bbox'):
            line = pdf_line('text1', {4: (8, 7)})
            char = line['spans'][0]['chars'][-1]
            if bad_geometry == 'rotation':
                char['rotation'] = 90
            else:
                char.pop('bbox')
            self.assertEqual(line_script_ranges(line), ())

    def test_decoded_ligature_offsets_are_used(self) -> None:
        line = pdf_line('office1', {6: (8, 7)})
        chars = line['spans'][0]['chars']
        chars[2]['char'] = 'ﬁ'
        del chars[3]
        self.assertEqual(render_scripts('office1', line_script_ranges(line)), 'office<sup>1</sup>')

    def test_stacked_fraction_is_distinguished_from_normal_adjacent_lines(self) -> None:
        line = pdf_line('n log ID', {6: (8, 7), 7: (8, 7)}, size=10)
        denominator = pdf_line('n', {})
        denominator['bbox'] = [30, 16, 35, 23]  # type: ignore[typeddict-item]
        self.assertEqual(line_script_ranges(line, [line, denominator]), ())
        denominator['bbox'] = [0, 24, 35, 34]  # type: ignore[typeddict-item]
        self.assertTrue(line_script_ranges(line, [line, denominator]))

    def test_stacked_fraction_does_not_hide_unrelated_inline_marker(self) -> None:
        line = pdf_line('n log ID text2', {6: (8, 7), 7: (8, 7), 13: (8, 7)}, size=10)
        denominator = pdf_line('n', {})
        denominator['bbox'] = [30, 16, 35, 23]  # type: ignore[typeddict-item]
        self.assertEqual(
            render_scripts('n log ID text2', line_script_ranges(line, [line, denominator])),
            'n log ID text<sup>2</sup>',
        )


class SameLineScriptDetectionTests(unittest.TestCase):
    """Scripts that pdftext puts into line records of their own."""

    def test_raised_marker_fragment_is_judged_against_preceding_text(self) -> None:
        text = pdf_line('insulator OSeO3', {}, size=10)
        marker = pdf_line('51.', {0: (8, 7), 1: (8, 7)}, size=10, x=75)

        self.assertEqual(line_script_ranges(marker, [text, marker]), ())
        self.assertEqual(
            render_scripts('51.', line_script_ranges(marker, [text, marker], [text])),
            '<sup>51</sup>.',
        )

    def test_fragment_keeps_its_own_nested_script(self) -> None:
        text = pdf_line('probability 1 - U', {}, size=10)
        exponent = pdf_line('−c1', {0: (7, 7), 1: (7, 7), 2: (12, 5)}, size=10, x=85)

        self.assertEqual(
            render_scripts('−c1', line_script_ranges(exponent, [text, exponent], [text])),
            '<sup>−c</sup><sub>1</sub>',
        )

    def test_same_size_fragments_stay_plain(self) -> None:
        text = pdf_line('Budzinauskas', {}, size=10)
        following = pdf_line(', Prashant', {}, size=10, x=60)

        self.assertEqual(line_script_ranges(following, [text, following], [text]), ())

    def test_slightly_raised_smaller_fragment_stays_plain(self) -> None:
        # In Nature's author list, sizes taken from bounding boxes differ, but
        # the text is shifted by less than a tenth of the neighboring height.
        text = pdf_line('Kestutis Budzinauskas', {}, size=1)
        following = pdf_line(', Prashant', {index: (10.1, 8) for index in range(10)}, size=1, x=105)

        self.assertEqual(line_script_ranges(following, [text, following], [text]), ())

    def test_text_beside_a_drop_cap_stays_plain(self) -> None:
        initial = pdf_line('I', {0: (0, 40)}, size=1)
        text = pdf_line('n spin systems', {index: (0, 10) for index in range(14)}, size=1, x=5)

        self.assertEqual(line_script_ranges(text, [initial, text], [initial]), ())

    def test_fragment_beside_a_few_tall_formula_delimiters_keeps_its_own_scripts(self) -> None:
        # Nature reports math parentheses as tall letters next to formula parts
        # of various sizes, so they only form the dominant size by a narrow margin.
        variable = pdf_line('mj', {0: (9, 8.3), 1: (7.8, 5.1)}, size=1)
        argument = pdf_line('r0ðÞ', {0: (14, 5), 1: (13, 6.2), 2: (10, 12.4), 3: (10, 12.4)}, x=10)

        self.assertEqual(
            render_scripts('mj', line_script_ranges(variable, [variable, argument], [argument])),
            'm<sup>j</sup>',
        )

    def test_numerator_fragment_of_a_stacked_fraction_stays_plain(self) -> None:
        text = pdf_line('robust even when <', {}, size=10)
        numerator = pdf_line('1', {0: (8, 6.2)}, size=10, x=95)
        denominator = pdf_line('2', {0: (15.4, 6.2)}, size=10, x=95)

        self.assertTrue(line_script_ranges(numerator, [text, numerator], [text]))
        self.assertEqual(line_script_ranges(numerator, [text, numerator, denominator], [text]), ())

    def test_line_records_detect_marker_in_another_pdftext_block(self) -> None:
        text = pdf_line('insulator OSeO3', {}, size=10)
        marker = pdf_line('51.', {0: (8, 7), 1: (8, 7)}, size=10, x=75)
        for line in (text, marker):
            line['spans'][0]['font'] = {'size': 10}  # type: ignore[typeddict-item]
        page = cast(Page, {'blocks': [{'lines': [text]}, {'lines': [marker]}]})

        lines = iter_lines([page])

        self.assertEqual(lines[0].scripts, ())
        self.assertEqual(render_scripts(lines[1].text, lines[1].scripts), '<sup>51</sup>.')


class ScriptAnnotationTests(unittest.TestCase):
    def test_slicing_clips_runs_and_whitespace_collapse_retains_heading_scripts(self) -> None:
        value = AnnotatedText(
            '  GaV4S8\n title ', (ScriptRange(5, 6, 'sub'), ScriptRange(7, 8, 'sub'))
        )
        self.assertEqual(value.slice(5, 6), AnnotatedText('4', (ScriptRange(0, 1, 'sub'),)))
        heading = collapse_annotated_whitespace(value)
        self.assertEqual(
            render_scripts(heading.text, heading.scripts), 'GaV<sub>4</sub>S<sub>8</sub> title'
        )

    def test_unhyphenation_moves_script_with_right_token_and_preserves_other_occurrence(
        self,
    ) -> None:
        value = repaired(
            AnnotatedText('word2 inter-'),
            AnnotatedText('national2 rest', (ScriptRange(8, 9, 'sup'),)),
        )
        self.assertEqual(
            render_scripts(value.text, value.scripts), 'word2 inter-national<sup>2</sup>\nrest'
        )

    def test_unspaced_dash_repair_and_consumed_lines_preserve_annotations(self) -> None:
        value = repaired(
            AnnotatedText('word—'), AnnotatedText('other1', (ScriptRange(5, 6, 'sup'),))
        )
        self.assertEqual(render_scripts(value.text, value.scripts), 'word—other<sup>1</sup>')

    def test_scripted_hyphen_is_removed_with_the_source_hyphen(self) -> None:
        value = repaired(
            AnnotatedText('inter-', (ScriptRange(5, 6, 'sup'),)), AnnotatedText('national')
        )
        self.assertEqual(value, AnnotatedText('international'))

    def test_detected_note_label_loses_annotation_but_note_body_keeps_scripts(self) -> None:
        text = '2 Formula GaV4S8 and text3.'
        line = source_line(
            text,
            (
                ScriptRange(0, 1, 'sup'),
                ScriptRange(13, 14, 'sub'),
                ScriptRange(15, 16, 'sub'),
                ScriptRange(25, 26, 'sup'),
            ),
        )
        result = numbered_line([line], 0)
        self.assertIsNotNone(result)
        assert result is not None
        label, body, _ = result
        note = build_footnote(
            DetectedNote(label, [[body]]), {1: PageNumber(1, None)}, Counter(), set(), set()
        )
        output = io.StringIO()
        markdown_to_text([note], output)
        self.assertEqual(
            output.getvalue(), '2. Formula GaV<sub>4</sub>S<sub>8</sub> and text<sup>3</sup>.\n'
        )

    def test_cross_page_note_moves_annotations_with_joined_token_and_keeps_page_marker(
        self,
    ) -> None:
        first = source_line('An inter-', ())
        second = source_line(
            'national2 rest3.', (ScriptRange(8, 9, 'sup'), ScriptRange(14, 15, 'sup')), page=2
        )
        note = build_footnote(
            DetectedNote('1', [[first, second]]),
            {1: PageNumber(1, None), 2: PageNumber(2, None)},
            Counter(),
            set(),
            set(),
        )
        output = io.StringIO()
        markdown_to_text([note], output, page_markers=True)
        self.assertEqual(
            output.getvalue(),
            '1. <<PAGE:1>>An inter-national<sup>2</sup>\n   <<PAGE:2>>rest<sup>3</sup>.\n',
        )

    def test_scripts_survive_heading_conversion_and_output_prefixes(self) -> None:
        page = PageNumber(1, None)
        value = Paragraph(
            ' GaV4S8\n title ',
            page,
            page,
            font_size=20,
            scripts=(ScriptRange(4, 5, 'sub'), ScriptRange(6, 7, 'sub')),
        )
        heading = detect_headings([value], 10, 400)[0]
        self.assertIsInstance(heading, Heading)
        quote = BlockQuote('text\n1 next', page, page, scripts=(ScriptRange(5, 6, 'sup'),))
        output = io.StringIO()
        markdown_to_text([heading, quote], output, page_markers=True)
        self.assertIn('<<PAGE:1>>GaV<sub>4</sub>S<sub>8</sub> title', output.getvalue())
        self.assertIn('> text\n> <sup>1</sup> next', output.getvalue())

    def test_script_content_escapes_html_and_markdown(self) -> None:
        self.assertEqual(
            render_scripts('<&*', (ScriptRange(0, 3, 'sup'),)), '<sup>&lt;&amp;&#42;</sup>'
        )

    def test_citation_brackets_are_preserved_literally(self) -> None:
        self.assertEqual(render_scripts('[10]', (ScriptRange(0, 4, 'sup'),)), '<sup>[10]</sup>')


if __name__ == '__main__':
    unittest.main()
