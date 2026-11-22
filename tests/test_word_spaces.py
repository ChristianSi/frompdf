import unittest
from typing import cast

from pdftext.schema import Line as PdfTextLine
from pdftext.schema import Page

from frompdf.word_spaces import insert_line_word_spaces, insert_missing_word_spaces

GLYPH_WIDTH = 5.0


def laid_out_line(layout: str, letter_gap: float = 0.2, word_gap: float = 2.5) -> PdfTextLine:
    """Return a line of a single span laid out from left to right.

    A space in layout is a space glyph followed by a word gap, a `|` a word
    gap without a glyph, and other characters glyphs separated by the letter
    gap.
    """
    chars: list[dict[str, object]] = []
    x = 10.0
    gap = 0.0
    for char in layout:
        if char in ' |':
            if char == ' ':
                chars.append({'char': ' ', 'bbox': [x, 100.0, x, 100.0], 'rotation': 0.0})
            gap = word_gap
            continue
        x += gap
        chars.append({'char': char, 'bbox': [x, 92.0, x + GLYPH_WIDTH, 100.0], 'rotation': 0.0})
        x += GLYPH_WIDTH
        gap = letter_gap
    text = ''.join(str(char['char']) for char in chars)
    return cast(PdfTextLine, {'spans': [{'text': text, 'chars': chars}]})


def span_text(line: PdfTextLine) -> str:
    """Return the text of a line's spans."""
    return ''.join(span['text'] for span in line['spans'])


def char_text(line: PdfTextLine) -> str:
    """Return the text of a line's characters."""
    return ''.join(char['char'] for span in line['spans'] for char in span['chars'])


class InsertLineWordSpacesTests(unittest.TestCase):
    def test_inserts_space_at_word_gap_without_glyph(self) -> None:
        line = laid_out_line('of GaV.|a Magnetic phase diagram')

        insert_line_word_spaces(line)

        self.assertEqual(span_text(line), 'of GaV. a Magnetic phase diagram')
        self.assertEqual(char_text(line), 'of GaV. a Magnetic phase diagram')

    def test_space_spans_the_gap(self) -> None:
        line = laid_out_line('one two three four|five')

        insert_line_word_spaces(line)

        chars = line['spans'][0]['chars']
        space = chars[char_text(line).rindex(' ')]
        self.assertEqual(space['bbox'][0], chars[char_text(line).rindex(' ') - 1]['bbox'][2])
        self.assertEqual(space['bbox'][2], chars[char_text(line).rindex(' ') + 1]['bbox'][0])

    def test_leaves_narrower_gaps_alone(self) -> None:
        line = laid_out_line('one two three four|five', word_gap=2.5)
        line['spans'][0]['chars'][-4]['bbox'][0] -= 1.5
        line['spans'][0]['chars'][-4]['bbox'][2] -= 1.5

        insert_line_word_spaces(line)

        self.assertEqual(span_text(line), 'one two three fourfive')

    def test_needs_several_word_gaps_to_compare(self) -> None:
        line = laid_out_line('GaV.|a Magnetic')

        insert_line_word_spaces(line)

        self.assertEqual(span_text(line), 'GaV.a Magnetic')

    def test_letter_spaced_line_measures_its_own_gaps(self) -> None:
        line = laid_out_line('ORIGINAL PAPER OPEN ACCESS', letter_gap=4.0, word_gap=9.0)

        insert_line_word_spaces(line)

        self.assertEqual(span_text(line), 'ORIGINAL PAPER OPEN ACCESS')

    def test_gap_holding_a_later_glyph_is_not_a_word_gap(self) -> None:
        # The `t` of m(t) comes after the parentheses but is set between them.
        line = laid_out_line('the magnetization m(|) at the position')
        chars = line['spans'][0]['chars']
        opening = next(char for char in chars if char['char'] == '(')
        t = {'char': 't', 'bbox': [opening['bbox'][2] + 0.2, 92.0, opening['bbox'][2] + 2.0, 100.0]}
        closing_index = next(index for index, char in enumerate(chars) if char['char'] == ')')
        chars.insert(closing_index + 1, t)
        line['spans'][0]['text'] = char_text(line)

        insert_line_word_spaces(line)

        self.assertEqual(span_text(line), 'the magnetization m()t at the position')

    def test_skips_lines_running_across_the_page(self) -> None:
        line = laid_out_line('one two three four|five')
        for char in line['spans'][0]['chars']:
            char['rotation'] = 1.5708

        insert_line_word_spaces(line)

        self.assertEqual(span_text(line), 'one two three fourfive')


class InsertMissingWordSpacesTests(unittest.TestCase):
    def test_skips_pages_of_ocr_text(self) -> None:
        pages = [
            cast(Page, {'blocks': [{'lines': [laid_out_line('one two three four|five')]}]})
            for _ in range(2)
        ]

        insert_missing_word_spaces(pages, {2})

        self.assertEqual(span_text(pages[0]['blocks'][0]['lines'][0]), 'one two three four five')
        self.assertEqual(span_text(pages[1]['blocks'][0]['lines'][0]), 'one two three fourfive')


if __name__ == '__main__':
    unittest.main()
