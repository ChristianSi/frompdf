import unittest
from typing import cast

from pdftext.schema import Page

from frompdf.lines import iter_lines, remove_icon_glyphs


def span(text: str, font_name: str, x1: float) -> dict[str, object]:
    return {
        'bbox': [x1, 0.0, x1 + 5.0 * len(text), 10.0],
        'text': text,
        'font': {'name': font_name, 'size': 10.0, 'weight': 400},
        'chars': [],
        'char_start_idx': 0,
        'char_end_idx': 0,
        'rotation': 0,
        'url': '',
        'superscript': False,
        'subscript': False,
    }


def page_with_spans(spans: list[dict[str, object]]) -> Page:
    bbox = [0.0, 0.0, 200.0, 10.0]
    return cast(
        Page,
        {
            'page': 1,
            'bbox': [0.0, 0.0, 200.0, 100.0],
            'width': 200,
            'height': 100,
            'blocks': [{'bbox': bbox, 'lines': [{'bbox': bbox, 'spans': spans}]}],
            'rotation': 0,
            'refs': [],
        },
    )


class IconGlyphTests(unittest.TestCase):
    def test_removes_icon_font_glyphs_with_their_separating_spaces(self) -> None:
        page = page_with_spans(
            [
                span('Roy Shadmon', 'LMRoman12-Bold', 0.0),
                span(' ', '', 55.0),
                span('#', 'FontAwesome5Free-Regular', 60.0),
                span(' ', '', 65.0),
                span('Ñ', 'FontAwesome5Free-Solid', 70.0),
                span(' ', '', 75.0),
                span('and Owen Arden', 'LMRoman12-Bold', 80.0),
            ]
        )

        remove_icon_glyphs([page])

        self.assertEqual(iter_lines([page])[0].text, 'Roy Shadmon and Owen Arden')

    def test_keeps_ordinary_symbols_from_text_fonts(self) -> None:
        page = page_with_spans(
            [span('Jane Doe', 'Times-Roman', 0.0), span(' #', 'Times-Roman', 40.0)]
        )

        remove_icon_glyphs([page])

        self.assertEqual(iter_lines([page])[0].text, 'Jane Doe #')


if __name__ == '__main__':
    unittest.main()
