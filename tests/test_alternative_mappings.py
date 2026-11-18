import unittest
from typing import cast

from pdftext.schema import Page

from frompdf.glyph_repairs import alternative_mapping, collapse_alternative_mappings
from frompdf.lines import iter_lines


def glyph_chars(glyphs: list[str], start_x: float = 0.0) -> list[dict[str, object]]:
    """Return pdftext characters, sharing one box for each glyph's characters."""
    chars: list[dict[str, object]] = []
    for index, glyph in enumerate(glyphs):
        x1 = start_x + 5.0 * index
        for char in glyph:
            chars.append({'bbox': [x1, 0.0, x1 + 5.0, 10.0], 'char': char, 'rotation': 0})
    return chars


def page_with_span(text: str, chars: list[dict[str, object]]) -> Page:
    bbox = [0.0, 0.0, 200.0, 10.0]
    span = {
        'bbox': bbox,
        'text': text,
        'font': {'name': 'Calibri', 'size': 10.0, 'weight': 400},
        'chars': chars,
        'char_start_idx': 0,
        'char_end_idx': len(chars),
        'rotation': 0,
        'url': '',
        'superscript': False,
        'subscript': False,
    }
    return cast(
        Page,
        {
            'page': 1,
            'bbox': [0.0, 0.0, 200.0, 100.0],
            'width': 200,
            'height': 100,
            'blocks': [{'bbox': bbox, 'lines': [{'bbox': bbox, 'spans': [span]}]}],
            'rotation': 0,
            'refs': [],
        },
    )


class AlternativeMappingTests(unittest.TestCase):
    def test_alternative_whitespace_stands_for_a_space(self) -> None:
        self.assertEqual(alternative_mapping(list('\t\r \xa0')), ' ')

    def test_alternative_dashes_stand_for_the_first_dash(self) -> None:
        self.assertEqual(alternative_mapping(list('-\xad‐')), '-')

    def test_ligature_letters_are_text(self) -> None:
        self.assertIsNone(alternative_mapping(list('ffi')))

    def test_repeated_dashes_are_text(self) -> None:
        self.assertIsNone(alternative_mapping(list('--')))

    def test_single_characters_are_text(self) -> None:
        self.assertIsNone(alternative_mapping([' ']))
        self.assertIsNone(alternative_mapping(['\xad']))

    def test_collapses_alternative_spaces_and_hyphens_in_text_and_chars(self) -> None:
        # pdftext normalizes `\r` to a line end, `\xa0` to a space, and drops
        # the soft hyphen from the span text.
        chars = glyph_chars(['n', 'o', 'n', '-\xad‐', 'c', '\t\r \xa0', 'o', 'k'])
        page = page_with_span('non-‐c\t\n  ok', chars)

        collapse_alternative_mappings([page])

        span = page['blocks'][0]['lines'][0]['spans'][0]
        self.assertEqual(span['text'], 'non-c ok')
        self.assertEqual(''.join(char['char'] for char in span['chars']), 'non-c ok')
        self.assertEqual(iter_lines([page])[0].text, 'non-c ok')

    def test_keeps_ligatures_and_line_ends_without_width(self) -> None:
        chars = glyph_chars(['ffi', 'x'])
        chars.extend(
            {'bbox': [10.0, 10.0, 10.0, 10.0], 'char': char, 'rotation': 0} for char in '\r\n'
        )
        page = page_with_span('ffix\n', chars)

        collapse_alternative_mappings([page])

        span = page['blocks'][0]['lines'][0]['spans'][0]
        self.assertEqual(span['text'], 'ffix\n')
        self.assertEqual(''.join(char['char'] for char in span['chars']), 'ffix\r\n')


if __name__ == '__main__':
    unittest.main()
