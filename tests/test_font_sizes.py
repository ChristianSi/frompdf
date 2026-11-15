import ctypes
import tempfile
import unittest
from pathlib import Path
from typing import cast

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from pdftext.extraction import dictionary_output
from pdftext.schema import Char as PdfTextChar
from pdftext.schema import Page

from frompdf.font_sizes import plausible_size, restore_font_sizes


def add_text(
    pdf: pdfium.PdfDocument, page: pdfium.PdfPage, text: str, scale: float, x: float
) -> None:
    """Add text set at font size 1, scaled up by its matrix, at a position on the page."""
    font = pdfium_c.FPDFText_LoadStandardFont(pdf.raw, b'Helvetica')
    text_object = pdfium_c.FPDFPageObj_CreateTextObj(pdf.raw, font, 1.0)
    encoded = ctypes.create_string_buffer(text.encode('utf-16-le') + b'\0\0')
    pdfium_c.FPDFText_SetText(
        text_object, ctypes.cast(encoded, ctypes.POINTER(pdfium_c.FPDF_WCHAR))
    )
    pdfium_c.FPDFPageObj_Transform(text_object, scale, 0, 0, scale, x, 100)
    pdfium_c.FPDFPage_InsertObject(page.raw, text_object)


def write_pdf(path: Path) -> None:
    """Write a PDF of one page with text at font size 1, scaled to 12 and 30 points."""
    pdf = pdfium.PdfDocument.new()
    page = pdf.new_page(400, 200)
    add_text(pdf, page, 'Chapter', 12.0, 20)
    add_text(pdf, page, '10', 30.0, 80)
    pdfium_c.FPDFPage_GenerateContent(page.raw)
    pdf.save(path)
    pdf.close()


def spans(page_list: list[Page]) -> list[dict]:
    return [
        span
        for page in page_list
        for block in page['blocks']
        for line in block['lines']
        for span in line['spans']
        if span['text'].strip()
    ]


class RestoreFontSizesTests(unittest.TestCase):
    def test_sizes_scaled_by_the_text_matrix_are_restored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / 'scaled.pdf'
            write_pdf(path)
            page_list = dictionary_output(str(path), sort=True, keep_chars=True)
            # pdftext reports the font size of the text objects only.
            self.assertTrue(all(span['font']['size'] <= 1.0 for span in spans(page_list)))

            restore_font_sizes(path, page_list)

        sizes = {span['text'].strip(): span['font']['size'] for span in spans(page_list)}
        self.assertAlmostEqual(sizes['Chapter'], 12.0, places=1)
        self.assertAlmostEqual(sizes['10'], 30.0, places=1)
        char_sizes = {char['font']['size'] for span in spans(page_list) for char in span['chars']}
        self.assertEqual({round(size) for size in char_sizes}, {12, 30})

    def test_size_must_fit_the_box_of_its_glyph(self) -> None:
        char = cast(PdfTextChar, {'char': 'a', 'bbox': [0, 0, 5, 12], 'rotation': 0})
        space = cast(PdfTextChar, {'char': ' ', 'bbox': [0, 0, 5, 0], 'rotation': 0})

        self.assertTrue(plausible_size(char, 10.0))
        self.assertFalse(plausible_size(char, 30.0))
        self.assertFalse(plausible_size(char, 5.0))
        self.assertTrue(plausible_size(space, 30.0))


if __name__ == '__main__':
    unittest.main()
