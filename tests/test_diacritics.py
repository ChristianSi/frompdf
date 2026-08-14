import io
import re
import unittest
from pathlib import Path
from typing import cast

from pdftext.schema import Page

from frompdf.lines import normalize_detached_diacritics
from frompdf.output import markdown_to_text
from frompdf.pipeline import extract_markdown

CORPUS_DIR = Path(__file__).parent / 'pdf-corpus'


def positioned_char(char: str, bbox: list[float]) -> dict[str, object]:
    return {'char': char, 'bbox': bbox, 'rotation': 0.0, 'font': {}, 'char_idx': 0}


def page_with_line(chars: list[dict[str, object]], text: str) -> Page:
    span = {
        'bbox': [0.0, 0.0, 100.0, 10.0],
        'text': text,
        'font': {},
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
            'bbox': [0.0, 0.0, 100.0, 100.0],
            'width': 100,
            'height': 100,
            'blocks': [{'bbox': span['bbox'], 'lines': [{'bbox': span['bbox'], 'spans': [span]}]}],
            'rotation': 0,
            'refs': [],
        },
    )


class DetachedDiacriticTests(unittest.TestCase):
    def test_repairs_target_pdf_before_paragraph_text_is_built(self) -> None:
        blocks = extract_markdown(CORPUS_DIR / 'ceur-elearning-system-datenbanken.pdf')
        output = io.StringIO()
        markdown_to_text(blocks, output)
        searchable_text = re.sub(r'\s+', ' ', output.getvalue().replace('-\n', ''))

        for expected in (
            'Feedbackmöglichkeiten',
            'Nützlichkeit',
            'Unterstützungsmöglichkeiten',
            'grundsätzliche',
            'Köln',
            'München',
            'für',
            'Üben dieser Aufgaben',
            'Daten Café',
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, searchable_text)

    def test_leaves_precomposed_letters_and_standalone_punctuation_unchanged(self) -> None:
        chars = [
            positioned_char('ä', [0.0, 1.0, 5.0, 9.0]),
            positioned_char(' ', [5.0, 8.0, 5.0, 8.0]),
            positioned_char('a', [10.0, 1.0, 15.0, 9.0]),
            positioned_char(' ', [15.0, 8.0, 15.0, 8.0]),
            positioned_char('¨', [18.0, 1.0, 23.0, 9.0]),
        ]
        page = page_with_line(chars, 'ä a ¨')

        normalize_detached_diacritics([page])

        self.assertEqual(page['blocks'][0]['lines'][0]['spans'][0]['text'], 'ä a ¨')

    def test_uses_geometry_when_accent_text_order_is_unrelated(self) -> None:
        chars = [
            positioned_char('u', [10.0, 1.0, 15.0, 9.0]),
            positioned_char('r', [15.0, 1.0, 19.0, 9.0]),
            positioned_char('¨', [10.1, 0.5, 14.9, 8.5]),
        ]
        page = page_with_line(chars, 'ur¨')

        normalize_detached_diacritics([page])

        self.assertEqual(page['blocks'][0]['lines'][0]['spans'][0]['text'], 'ür')


if __name__ == '__main__':
    unittest.main()
