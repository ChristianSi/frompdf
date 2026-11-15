import ctypes
import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest import mock

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from pdftext.schema import Line as PdfTextLine
from pdftext.schema import Page
from pdftext.schema import Span as PdfTextSpan

from frompdf.glyph_weight import (
    body_font_name,
    contour_measures,
    find_heavy_fonts,
    font_stroke_widths,
    has_opaque_name,
)
from frompdf.lines import average_font_weight, line_emphasis_ranges, span_emphasis_kinds
from frompdf.models import InlineRange

STANDARD_FONTS = ('Helvetica', 'Helvetica-Bold', 'Times-Roman', 'Times-Bold')


def write_pdf(path: Path, font_names: tuple[str, ...]) -> None:
    """Write a PDF of one page with a line of lowercase letters in each standard font."""
    pdf = pdfium.PdfDocument.new()
    page = pdf.new_page(200, 200)
    text = ctypes.create_unicode_buffer('abcdeghmnopqrsu')
    for index, name in enumerate(font_names):
        font = pdfium_c.FPDFText_LoadStandardFont(pdf.raw, name.encode())
        text_object = pdfium_c.FPDFPageObj_CreateTextObj(pdf.raw, font, 10.0)
        encoded = ctypes.create_string_buffer(text.value.encode('utf-16-le') + b'\0\0')
        pdfium_c.FPDFText_SetText(
            text_object, ctypes.cast(encoded, ctypes.POINTER(pdfium_c.FPDF_WCHAR))
        )
        pdfium_c.FPDFPageObj_Transform(text_object, 1, 0, 0, 1, 10, 20 + 30 * index)
        pdfium_c.FPDFPage_InsertObject(page.raw, text_object)
    pdfium_c.FPDFPage_GenerateContent(page.raw)
    pdf.save(path)
    pdf.close()


def span(text: str, name: str, weight: int = 0) -> dict:
    return {'text': text, 'font': {'name': name, 'size': 10, 'flags': 4, 'weight': weight}}


def page_of_spans(*spans: dict) -> Page:
    return cast(Page, {'blocks': [{'lines': [{'spans': list(spans)}]}]})


class FontNameTests(unittest.TestCase):
    def test_hashed_names_without_a_style_are_opaque(self) -> None:
        for name in ('AdvOTcb88df00', 'AdvTT577c760c', 'MOPEGP+AdvOTcb88df00'):
            with self.subTest(name):
                self.assertTrue(has_opaque_name(name))

    def test_names_telling_a_style_or_naming_a_face_are_not_opaque(self) -> None:
        for name in (
            'AdvOTb65e897d.B',
            'AdvOT7d6df7ab.I',
            'AdvOT8244d044.BI+03',
            'ArialMT',
            'Calibri',
            'NimbusSanL-Regu',
            'Roboto-Medium',
            'CMB10',
            'BCDJEE+ArialMT',
        ):
            with self.subTest(name):
                self.assertFalse(has_opaque_name(name))

    def test_body_font_sets_most_visible_text(self) -> None:
        page = page_of_spans(span('Bold lead.', 'Heavy'), span(' ' + 'body text ' * 3, 'Body'))

        self.assertEqual(body_font_name([page]), 'Body')


class StrokeWidthTests(unittest.TestCase):
    def test_square_contour_has_its_area_and_perimeter(self) -> None:
        self.assertEqual(contour_measures([(0, 0), (2, 0), (2, 2), (0, 2)]), (4.0, 8.0))

    def test_bold_fonts_have_much_wider_strokes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / 'fonts.pdf'
            write_pdf(path, STANDARD_FONTS)

            widths = font_stroke_widths(path, set(STANDARD_FONTS))

        self.assertEqual(set(widths), set(STANDARD_FONTS))
        self.assertGreater(widths['Helvetica-Bold'], 1.4 * widths['Helvetica'])
        self.assertGreater(widths['Times-Bold'], 1.4 * widths['Times-Roman'])
        self.assertLess(widths['Helvetica'], 1.4 * widths['Times-Roman'])

    def test_fonts_much_heavier_than_the_body_font_are_heavy(self) -> None:
        page = page_of_spans(
            span('regular body text ' * 4, 'Times-Roman'),
            span('A bold lead.', 'Times-Bold'),
            span('Sans text.', 'Helvetica'),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / 'fonts.pdf'
            write_pdf(path, ('Times-Roman', 'Times-Bold', 'Helvetica'))
            # The standard fonts stand in for fonts named by hashes.
            with mock.patch('frompdf.glyph_weight.has_opaque_name', return_value=True):
                heavy = find_heavy_fonts(path, [page])

        self.assertEqual(heavy, frozenset({'Times-Bold'}))


class HeavyFontEmphasisTests(unittest.TestCase):
    def test_heavy_fonts_are_bold(self) -> None:
        heavy = frozenset({'AdvOTcb88df00'})
        bold = cast(PdfTextSpan, span('Fig. 1', 'AdvOTcb88df00'))
        line = cast(PdfTextLine, {'spans': [bold, span(' Caption text.', 'AdvOTea1a7398')]})

        self.assertEqual(span_emphasis_kinds(bold), ())
        self.assertEqual(span_emphasis_kinds(bold, heavy), ('bold',))
        self.assertEqual(line_emphasis_ranges(line, heavy), (InlineRange(0, 6, 'bold'),))
        self.assertEqual(average_font_weight(cast(PdfTextLine, {'spans': [bold]}), heavy), 700.0)


if __name__ == '__main__':
    unittest.main()
