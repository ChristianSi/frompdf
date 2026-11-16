import ctypes
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from pdftext.extraction import dictionary_output
from PIL import Image, ImageDraw, ImageFont

from frompdf.ocr_text import (
    Scan,
    dense_band,
    group_sizes,
    ink_runs,
    letter_kind,
    line_end_hyphen,
    measure_line,
    repair_ocr_text_layers,
)

# Synthetic scans have 4 pixels per point.
SCALE = 4.0


def blank(width: float = 300.0, height: float = 100.0) -> np.ndarray:
    """Return an empty scan of a size in points."""
    return np.zeros((round(height * SCALE), round(width * SCALE)), dtype=bool)


def ink(scan: np.ndarray, x1: float, y1: float, x2: float, y2: float) -> None:
    """Ink a box given in points."""
    scan[round(y1 * SCALE) : round(y2 * SCALE), round(x1 * SCALE) : round(x2 * SCALE)] = True


def write_word(
    scan: np.ndarray, x: float, baseline: float, letters: str, em: float = 10.0
) -> float:
    """Ink letters as blocks of a 10 pt face, returning where the word ends.

    `x` stands for a lowercase letter, `l` for one with an ascender, `p` for
    one with a descender, and `-` for a hyphen.
    """
    for letter in letters:
        if letter == '-':
            ink(scan, x, baseline - 0.3 * em, x + 0.3 * em, baseline - 0.2 * em)
            x += 0.35 * em
            continue
        top = baseline - (0.7 if letter == 'l' else 0.5) * em
        bottom = baseline + (0.2 if letter == 'p' else 0.0) * em
        ink(scan, x, top, x + 0.4 * em, bottom)
        x += 0.5 * em
    return x


class LetterKindTests(unittest.TestCase):
    def test_tells_lowercase_capitals_and_mixed_lines(self) -> None:
        self.assertEqual(letter_kind('the ancient Egyptians used'), 'x')
        self.assertEqual(letter_kind('NOTES'), 'cap')
        self.assertEqual(letter_kind('405–414.'), 'cap')
        self.assertEqual(letter_kind('GM 114 (1990):35-42, and E.'), 'mixed')
        self.assertEqual(letter_kind('—'), 'mixed')


class InkRunTests(unittest.TestCase):
    def test_joins_runs_across_small_gaps_only(self) -> None:
        columns = np.array([0, 1, 1, 0, 1, 0, 0, 0, 1, 1], dtype=bool)

        self.assertEqual(ink_runs(columns, 1), [(1, 4), (8, 9)])
        self.assertEqual(ink_runs(columns, 3), [(1, 9)])
        self.assertEqual(ink_runs(np.zeros(4, dtype=bool), 1), [])


class DenseBandTests(unittest.TestCase):
    def test_finds_x_height_below_frequent_ascenders(self) -> None:
        # Rows 0-9 hold ascenders only, rows 10-29 all letters, rows 30-34
        # descenders.
        profile = np.array([0.0] * 5 + [40.0] * 10 + [100.0] * 20 + [10.0] * 5 + [0.0] * 5)

        band = dense_band(profile, 25, 44, 40)

        assert band is not None
        self.assertAlmostEqual(band[0], 15.0, delta=1.0)
        self.assertAlmostEqual(band[1], 35.0, delta=1.0)

    def test_baseline_of_digits_lies_below_a_denser_dash(self) -> None:
        # A dash fills rows 20-23 more densely than the digits around it.
        profile = np.array([0.0] * 5 + [30.0] * 15 + [60.0] * 4 + [30.0] * 6 + [0.0] * 6)

        band = dense_band(profile, 15, 35, 40, capitals=True)

        assert band is not None
        self.assertAlmostEqual(band[0], 5.0, delta=1.0)
        self.assertAlmostEqual(band[1], 30.0, delta=1.0)


class LineEndHyphenTests(unittest.TestCase):
    def hyphen(self, scan: np.ndarray, x2: float) -> float | None:
        return line_end_hyphen(Scan(scan, SCALE), 0.0, x2, 50.0, 10.0)

    def test_finds_a_hyphen_ending_a_line(self) -> None:
        scan = blank()
        end = write_word(scan, 10.0, 50.0, 'xlxx-')

        self.assertAlmostEqual(self.hyphen(scan, end) or 0.0, end - 3.5, delta=0.5)

    def test_finds_a_hyphen_below_an_overhanging_letter(self) -> None:
        scan = blank()
        end = write_word(scan, 10.0, 50.0, 'xlx-')
        # The arm of an `f` reaches over the hyphen above the x-height.
        ink(scan, end - 5.0, 43.0, end - 2.0, 45.0)

        self.assertIsNotNone(self.hyphen(scan, end))

    def test_rejects_letters_periods_and_marks_above_a_hyphen(self) -> None:
        letters = blank()
        letters_end = write_word(letters, 10.0, 50.0, 'xlxp')
        period = blank()
        period_end = write_word(period, 10.0, 50.0, 'xlx')
        ink(period, period_end, 49.0, period_end + 1.0, 50.0)
        quote = blank()
        quote_end = write_word(quote, 10.0, 50.0, 'xlx-')
        ink(quote, quote_end + 0.5, 43.0, quote_end + 1.5, 45.0)

        self.assertIsNone(self.hyphen(letters, letters_end))
        self.assertIsNone(self.hyphen(period, period_end + 1.0))
        self.assertIsNone(self.hyphen(quote, quote_end + 1.5))


class MeasureLineTests(unittest.TestCase):
    def test_takes_line_ends_from_the_ink_not_the_text_layer(self) -> None:
        scan = blank()
        x = 20.0
        for word in ('xlx', 'pxxl', 'xx', 'lxpx-'):
            x = write_word(scan, x, 50.0, word) + 3.0
        # The hyphen ends half a point before the advance past it.
        end = x - 3.5
        # The text layer starts the line 2 points right of its ink and ends
        # it 40 points beyond, with its origin below the descenders.
        line = measure_line(
            Scan(scan, SCALE), 'the ancient Egyp', (22.0, 41.0, end + 40.0, 54.0), 52.0, 9.0, 300.0
        )

        assert line is not None
        self.assertAlmostEqual(line.x1, 20.0, delta=0.3)
        self.assertAlmostEqual(line.x2, end, delta=0.3)
        self.assertAlmostEqual(line.baseline, 50.0, delta=0.3)
        # Smoothing blurs the sharp edges of synthetic letters a little;
        # sizes only need to compare with those of other lines.
        self.assertAlmostEqual(line.em, 10.0, delta=1.0)

    def test_ends_before_the_next_column_and_at_a_gutter(self) -> None:
        scan = blank()
        left_end = write_word(scan, 20.0, 50.0, 'xxlxxlxx')
        write_word(scan, left_end + 4.0, 50.0, 'xxlxx')
        right_column = blank()
        write_word(right_column, 20.0, 50.0, 'xxlxxlxx')
        write_word(right_column, 120.0, 50.0, 'xxlxx')

        bounded = measure_line(
            Scan(scan, SCALE), 'the ancient', (20.0, 41.0, 200.0, 54.0), 50.0, 9.0, left_end + 2.0
        )
        gutter = measure_line(
            Scan(right_column, SCALE), 'the ancient', (20.0, 41.0, 200.0, 54.0), 50.0, 9.0, 300.0
        )

        assert bounded is not None and gutter is not None
        self.assertAlmostEqual(bounded.x2, left_end - 1.0, delta=0.3)
        self.assertAlmostEqual(gutter.x2, left_end - 1.0, delta=0.3)

    def test_without_ink_there_is_no_measurement(self) -> None:
        self.assertIsNone(
            measure_line(Scan(blank(), SCALE), 'text', (20.0, 41.0, 80.0, 54.0), 50.0, 9.0, 300.0)
        )


class GroupSizeTests(unittest.TestCase):
    def test_groups_sizes_around_the_most_common_ones(self) -> None:
        sizes = [(10.0, 5), (10.5, 3), (9.4, 2), (8.0, 2), (8.3, 2), (12.5, 1)]

        self.assertEqual(group_sizes(sizes), [10.0, 10.0, 10.0, 8.0, 8.0, 12.5])
        self.assertEqual(group_sizes([]), [])


def add_invisible_text(
    pdf: pdfium.PdfDocument, page: pdfium.PdfPage, text: str, size: float, x: float, y: float
) -> None:
    """Add a line of invisible text, as OCR text layers are, at a baseline position."""
    font = pdfium_c.FPDFText_LoadStandardFont(pdf.raw, b'Helvetica')
    text_object = pdfium_c.FPDFPageObj_CreateTextObj(pdf.raw, font, size)
    encoded = ctypes.create_string_buffer(text.encode('utf-16-le') + b'\0\0')
    pdfium_c.FPDFText_SetText(
        text_object, ctypes.cast(encoded, ctypes.POINTER(pdfium_c.FPDF_WCHAR))
    )
    pdfium_c.FPDFTextObj_SetTextRenderMode(text_object, pdfium_c.FPDF_TEXTRENDERMODE_INVISIBLE)
    pdfium_c.FPDFPageObj_Transform(text_object, 1, 0, 0, 1, x, y)
    pdfium_c.FPDFPage_InsertObject(page.raw, text_object)


def write_scanned_pdf(path: Path) -> None:
    """Write a page whose image shows two lines, under an inaccurate invisible text layer.

    The text layer omits the hyphen ending the first line and sets the
    second one, which has no descenders, in a smaller size.
    """
    resolution = 4
    image = Image.new('L', (300 * resolution, 200 * resolution), 255)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=10 * resolution)
    draw.text((20 * resolution, 40 * resolution), 'the nude human figure ex-', font=font, fill=0)
    draw.text((20 * resolution, 56 * resolution), 'pressed more than status', font=font, fill=0)
    pdf = pdfium.PdfDocument.new()
    page = pdf.new_page(300, 200)
    pdf_image = pdfium.PdfImage.new(pdf)
    pdf_image.set_bitmap(pdfium.PdfBitmap.from_pil(image))
    pdf_image.set_matrix(pdfium.PdfMatrix().scale(300, 200))
    page.insert_obj(pdf_image)
    add_invisible_text(pdf, page, 'the nude human figure ex', 12.0, 21.0, 147.0)
    add_invisible_text(pdf, page, 'pressed more than status', 9.0, 21.0, 131.0)
    pdfium_c.FPDFPage_GenerateContent(page.raw)
    pdf.save(path)
    pdf.close()


class RepairTests(unittest.TestCase):
    def test_repairs_line_ends_sizes_and_hyphens_of_a_text_layer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'scan.pdf'
            write_scanned_pdf(path)
            pages = dictionary_output(str(path), keep_chars=True)
            repair_ocr_text_layers(path, pages)

        lines = [line for block in pages[0]['blocks'] for line in block['lines']]
        texts = [''.join(span['text'] for span in line['spans']).strip() for line in lines]
        sizes = {span['font']['size'] for line in lines for span in line['spans']}
        rights = [line['bbox'][2] for line in lines]
        self.assertEqual(texts, ['the nude human figure ex-', 'pressed more than status'])
        self.assertEqual(len(sizes), 1)
        # Both lines end within the ink of the image, short of the page.
        for right in rights:
            self.assertLess(right, 200.0)

    def test_leaves_visible_text_alone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'plain.pdf'
            pdf = pdfium.PdfDocument.new()
            page = pdf.new_page(300, 200)
            font = pdfium_c.FPDFText_LoadStandardFont(pdf.raw, b'Helvetica')
            text_object = pdfium_c.FPDFPageObj_CreateTextObj(pdf.raw, font, 10.0)
            encoded = ctypes.create_string_buffer('Visible text'.encode('utf-16-le') + b'\0\0')
            pdfium_c.FPDFText_SetText(
                text_object, ctypes.cast(encoded, ctypes.POINTER(pdfium_c.FPDF_WCHAR))
            )
            pdfium_c.FPDFPageObj_Transform(text_object, 1, 0, 0, 1, 20, 100)
            pdfium_c.FPDFPage_InsertObject(page.raw, text_object)
            pdfium_c.FPDFPage_GenerateContent(page.raw)
            pdf.save(path)
            pdf.close()
            pages = dictionary_output(str(path), keep_chars=True)
            before = repr(pages)
            repair_ocr_text_layers(path, pages)

        self.assertEqual(repr(pages), before)


if __name__ == '__main__':
    unittest.main()
