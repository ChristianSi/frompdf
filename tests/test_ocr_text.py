import ctypes
import math
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import numpy as np
import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from pdftext.extraction import dictionary_output
from pdftext.schema import Char as PdfTextChar
from pdftext.schema import Line as PdfTextLine
from PIL import Image, ImageDraw, ImageFont

from frompdf.ocr_text import (
    InkLine,
    OcrLine,
    Placement,
    Scan,
    assign_sizes,
    dense_band,
    estimate_size,
    find_scan_rules,
    group_sizes,
    has_implausible_size,
    ink_runs,
    is_misplaced,
    is_upright,
    letter_kind,
    line_end_hyphen,
    mark_soft_hyphen,
    measure_line,
    remeasure,
    repair_ocr_text_layers,
    split_joined_lines,
    typical_placements,
    visible_line_chars,
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


class ScanRuleTests(unittest.TestCase):
    def test_finds_a_printed_rule_also_where_skewed(self) -> None:
        scan = blank()
        ink(scan, 20.0, 30.0, 120.0, 30.5)
        # A skewed rule descends by a quarter point every 25 points.
        for step in range(8):
            x = 150.0 + step * 12.5
            ink(scan, x, 60.0 + step * 0.25, x + 12.5, 60.5 + step * 0.25)

        rules = find_scan_rules(Scan(scan, SCALE))

        self.assertEqual(len(rules), 2)
        self.assertTrue(all(rule.horizontal for rule in rules))
        self.assertAlmostEqual(rules[0].position, 30.25, delta=0.3)
        self.assertAlmostEqual(rules[0].start, 20.0, delta=0.3)
        self.assertAlmostEqual(rules[0].end, 120.0, delta=0.3)
        self.assertAlmostEqual(rules[1].start, 150.0, delta=0.3)
        self.assertAlmostEqual(rules[1].end, 250.0, delta=0.3)

    def test_rejects_short_rules_text_and_underlined_words(self) -> None:
        scan = blank()
        ink(scan, 10.0, 20.0, 25.0, 20.5)
        # Letters running together, as in a dark scan.
        ink(scan, 40.0, 45.0, 140.0, 50.0)
        end = write_word(scan, 160.0, 80.0, 'xlxxlxxpxlxxlxxx')
        ink(scan, 160.0, 80.5, end, 81.0)

        self.assertEqual(find_scan_rules(Scan(scan, SCALE)), [])


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


def ocr_line(
    origin: float,
    baseline: float,
    em: float = 11.5,
    ocr_size: float = 10.0,
    kind: str = 'x',
    block_index: int = 0,
    measured: bool = True,
) -> OcrLine:
    """Return a line of a text layer from 20 to 200 points with its measurement."""
    ink_line = InkLine(20.0, 200.0, baseline, em, em * 0.5 if measured else None, kind, None)
    return OcrLine(
        0,
        block_index,
        {'bbox': [20.0, origin - ocr_size, 200.0, origin], 'spans': []},
        [],
        30,
        ink_line,
        'the ancient Egyptians used',
        (20.0, origin - ocr_size, 200.0, origin),
        origin,
        ocr_size,
        300.0,
    )


class PlacementTests(unittest.TestCase):
    def test_typical_placement_is_the_median_of_each_kind_with_enough_lines(self) -> None:
        # Lowercase lines lie 0.35 sizes above their origins, three are
        # misplaced on the next line; too few lines of capitals are known.
        lines = [ocr_line(100.0 + 20 * index, 96.5 + 20 * index) for index in range(10)]
        lines += [ocr_line(400.0 + 20 * index, 405.0 + 20 * index) for index in range(3)]
        lines += [ocr_line(500.0, 500.0, kind='cap') for _ in range(3)]

        placements = typical_placements(lines)

        self.assertEqual(set(placements), {'x'})
        self.assertAlmostEqual(placements['x'].offset, -0.35)
        self.assertAlmostEqual(placements['x'].scale or 0.0, 1.15)

    def test_finds_misplaced_baselines_and_implausible_sizes(self) -> None:
        placements = {'x': Placement(-0.35, 1.15)}

        # A baseline on the next line is misplaced, one scattered by a
        # quarter of the size is not.
        self.assertTrue(is_misplaced(ocr_line(100.0, 105.0), placements))
        self.assertFalse(is_misplaced(ocr_line(100.0, 94.0), placements))
        # A baseline above its typical placement is not the next line's.
        self.assertFalse(is_misplaced(ocr_line(100.0, 91.0), placements))
        # Lines of a kind without a typical placement are not judged.
        self.assertFalse(is_misplaced(ocr_line(100.0, 105.0, kind='cap'), placements))
        # A height misled by quotation marks is implausible, a size off by a
        # tenth or one not told by the letters is not.
        self.assertTrue(has_implausible_size(ocr_line(100.0, 96.5, em=20.4), placements))
        self.assertTrue(has_implausible_size(ocr_line(100.0, 96.5, em=5.4), placements))
        self.assertFalse(has_implausible_size(ocr_line(100.0, 96.5, em=12.6), placements))
        self.assertFalse(
            has_implausible_size(ocr_line(100.0, 96.5, em=20.4, measured=False), placements)
        )


def two_printed_lines() -> np.ndarray:
    """Return a scan of two lines of words, with baselines at 50 and 66 points."""
    scan = blank()
    x = 20.0
    for word in ('xlx', 'pxxl', 'xx', 'lxpx'):
        x = write_word(scan, x, 50.0, word) + 3.0
    x = 20.0
    for word in ('lxx', 'xxlp', 'xlx'):
        x = write_word(scan, x, 66.0, word) + 3.0
    return scan


class RemeasureTests(unittest.TestCase):
    def test_measures_a_misplaced_line_where_its_placement_expects_it(self) -> None:
        # The text layer puts the first line so low that its baseline was
        # taken from the second one.
        line = ocr_line(54.0, 66.0)

        remeasure(Scan(two_printed_lines(), SCALE), line, Placement(-0.4, 1.0))

        self.assertAlmostEqual(line.ink.baseline, 50.0, delta=0.3)
        self.assertAlmostEqual(line.ink.x1, 20.0, delta=0.3)
        self.assertFalse(line.estimated)

    def test_finds_a_line_set_far_too_low_above_its_expected_baseline(self) -> None:
        # As where pdftext joined it with the next line, the text layer puts
        # the first line 0.7 sizes lower than its typical placement.
        line = ocr_line(61.0, 66.0)

        remeasure(Scan(two_printed_lines(), SCALE), line, Placement(-0.4, 1.0))

        self.assertAlmostEqual(line.ink.baseline, 50.0, delta=0.3)
        self.assertFalse(line.estimated)

    def test_places_a_line_without_ink_where_its_placement_expects_it(self) -> None:
        line = ocr_line(54.0, 66.0)

        remeasure(Scan(blank(), SCALE), line, Placement(-0.4, 1.15))

        self.assertAlmostEqual(line.ink.baseline, 50.0)
        self.assertEqual((line.ink.x1, line.ink.x2), (20.0, 200.0))
        self.assertAlmostEqual(line.ink.em, 11.5)
        self.assertIsNone(line.ink.height)
        self.assertTrue(line.estimated)


class AssignSizeTests(unittest.TestCase):
    def test_estimated_sizes_take_the_nearest_common_size_not_their_blocks(self) -> None:
        # The last body line shares its block with notes set in a smaller size.
        body = [ocr_line(100.0 + 15 * index, 96.5 + 15 * index, em=11.3) for index in range(4)]
        notes = [
            ocr_line(200.0 + 12 * index, 197.0 + 12 * index, em=9.7, ocr_size=8.0, block_index=1)
            for index in range(4)
        ]
        estimated = ocr_line(180.0, 176.5, em=20.4, block_index=1)
        unmeasured = ocr_line(250.0, 247.0, em=9.0, ocr_size=8.0, block_index=1, measured=False)
        estimate_size(estimated, Placement(-0.35, 1.15))

        assign_sizes([*body, *notes, estimated, unmeasured])

        self.assertEqual(estimated.size, 11.3)
        self.assertEqual(unmeasured.size, 9.7)


def text_line(*words: str) -> PdfTextLine:
    """Return a line of a text layer with a span per word, followed by a space."""
    spans = [
        {'text': word + ' ', 'chars': [{'char': char} for char in word + ' ']} for word in words
    ]
    return cast(PdfTextLine, {'spans': spans})


def line_text(line: PdfTextLine) -> str:
    """Return the text of a line from its spans."""
    return ''.join(span['text'] for span in line['spans']).strip()


def char_text(line: PdfTextLine) -> str:
    """Return the text of a line from its characters."""
    return ''.join(char['char'] for span in line['spans'] for char in span['chars']).strip()


class UprightTests(unittest.TestCase):
    def test_tells_skewed_lines_from_turned_ones(self) -> None:
        def char(rotation: float) -> PdfTextChar:
            return cast(PdfTextChar, {'char': 'a', 'rotation': rotation})

        self.assertTrue(is_upright(char(0.0)))
        self.assertTrue(is_upright(char(math.radians(0.6))))
        # A slight clockwise skew comes as nearly a full turn.
        self.assertTrue(is_upright(char(math.tau - math.radians(0.6))))
        self.assertFalse(is_upright(char(math.radians(10.0))))
        self.assertFalse(is_upright(char(math.pi / 2)))
        self.assertFalse(is_upright(char(math.pi)))


def write_text_layer(path: Path, lines: Sequence[tuple[str, float, float]]) -> None:
    """Write a page with invisible lines of 12 point text, given with their origins."""
    pdf = pdfium.PdfDocument.new()
    page = pdf.new_page(300, 200)
    for text, x, y in lines:
        add_invisible_text(pdf, page, text, 12.0, x, y)
    pdfium_c.FPDFPage_GenerateContent(page.raw)
    pdf.save(path)
    pdf.close()


def split_text_layer(lines: Sequence[tuple[str, float, float]]) -> list[PdfTextLine]:
    """Return the lines of a text layer read by pdftext, after splitting joined ones."""
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'layer.pdf'
        write_text_layer(path, lines)
        page = dictionary_output(str(path), keep_chars=True)[0]
        pdf = pdfium.PdfDocument(path)
        try:
            text_page = pdf[0].get_textpage()
            split_joined_lines(text_page, page)
        finally:
            pdf.close()
    return [line for block in page['blocks'] for line in block['lines']]


class JoinedLineTests(unittest.TestCase):
    def test_splits_printed_lines_that_pdftext_joined(self) -> None:
        # The second line lies two thirds of a size below the first, so
        # that their boxes overlap and pdftext joins them.
        lines = split_text_layer(
            [('the nude human figure ex', 21.0, 147.0), ('pressed more than status', 21.0, 139.0)]
        )

        self.assertEqual(
            [line_text(line) for line in lines],
            ['the nude human figure ex', 'pressed more than status'],
        )
        self.assertEqual(
            [char_text(line) for line in lines],
            ['the nude human figure ex', 'pressed more than status'],
        )
        first, second = lines
        self.assertLess(first['bbox'][1], second['bbox'][1])
        self.assertLess(second['bbox'][0], first['bbox'][2] - 12.0)
        self.assertEqual(
            second['spans'][0]['char_start_idx'], second['spans'][0]['chars'][0]['char_idx']
        )

    def test_keeps_lines_that_continue_rightwards_or_barely_drop(self) -> None:
        # Text continuing to the right below the line, as a subscript does,
        # and a next line only a third of a size lower are not split.
        rightwards = split_text_layer([('the nude', 21.0, 147.0), ('human figure', 80.0, 139.0)])
        barely = split_text_layer(
            [('the nude human figure ex', 21.0, 147.0), ('pressed more than status', 21.0, 143.0)]
        )

        self.assertEqual(len(rightwards), 1)
        self.assertEqual(len(barely), 1)


class SoftHyphenTests(unittest.TestCase):
    def test_turns_a_not_sign_breaking_a_word_into_a_soft_hyphen(self) -> None:
        line = text_line('the', 'East', 'India', 'Com\u00ac')

        mark_soft_hyphen(line, visible_line_chars(line))

        self.assertEqual(line_text(line), 'the East India Com\u00ad')
        self.assertEqual(char_text(line), 'the East India Com\u00ad')

    def test_leaves_negations_and_not_signs_within_lines_alone(self) -> None:
        negation = text_line('p', '\u2227', '\u00ac')
        within = text_line('de\u00ac', 'sire', 'to')

        mark_soft_hyphen(negation, visible_line_chars(negation))
        mark_soft_hyphen(within, visible_line_chars(within))

        self.assertEqual(line_text(negation), 'p \u2227 \u00ac')
        self.assertEqual(line_text(within), 'de\u00ac sire to')


def add_invisible_text(
    pdf: pdfium.PdfDocument,
    page: pdfium.PdfPage,
    text: str,
    size: float,
    x: float,
    y: float,
    skew: float = 0.0,
) -> None:
    """Add a line of invisible text, as OCR text layers are, at a baseline position.

    skew turns the line counterclockwise on the page by that many degrees, which
    pdftext reports as a clockwise rotation.
    """
    font = pdfium_c.FPDFText_LoadStandardFont(pdf.raw, b'Helvetica')
    text_object = pdfium_c.FPDFPageObj_CreateTextObj(pdf.raw, font, size)
    encoded = ctypes.create_string_buffer(text.encode('utf-16-le') + b'\0\0')
    pdfium_c.FPDFText_SetText(
        text_object, ctypes.cast(encoded, ctypes.POINTER(pdfium_c.FPDF_WCHAR))
    )
    pdfium_c.FPDFTextObj_SetTextRenderMode(text_object, pdfium_c.FPDF_TEXTRENDERMODE_INVISIBLE)
    cos, sin = math.cos(math.radians(skew)), math.sin(math.radians(skew))
    pdfium_c.FPDFPageObj_Transform(text_object, cos, sin, -sin, cos, x, y)
    pdfium_c.FPDFPage_InsertObject(page.raw, text_object)


def write_scanned_pdf(
    path: Path,
    first_text: str = 'the nude human figure ex',
    extra_text: str | None = None,
    skew: float = 0.0,
) -> None:
    """Write a page whose image shows two lines, under an inaccurate invisible text layer.

    The text layer omits the hyphen ending the first line and sets the
    second one, which has no descenders, in a smaller size. extra_text is
    set near the bottom of the page, where the image shows no print. The
    text layer is skewed by skew degrees, as for a slightly skewed scan.
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
    add_invisible_text(pdf, page, first_text, 12.0, 21.0, 147.0, skew)
    add_invisible_text(pdf, page, 'pressed more than status', 9.0, 21.0, 131.0, skew)
    if extra_text is not None:
        add_invisible_text(pdf, page, extra_text, 9.0, 21.0, 20.0)
    pdfium_c.FPDFPage_GenerateContent(page.raw)
    pdf.save(path)
    pdf.close()


def write_blank_scan_pdf(path: Path) -> None:
    """Write a page whose image shows no print, under the text layer of show-through."""
    pdf = pdfium.PdfDocument.new()
    page = pdf.new_page(300, 200)
    pdf_image = pdfium.PdfImage.new(pdf)
    image = Image.new('L', (1200, 800), 160)
    pdf_image.set_bitmap(pdfium.PdfBitmap.from_pil(image))
    pdf_image.set_matrix(pdfium.PdfMatrix().scale(300, 200))
    page.insert_obj(pdf_image)
    add_invisible_text(pdf, page, 'MISSION TO THE', 12.0, 21.0, 147.0)
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

    def test_measures_a_skewed_text_layer_as_upright_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'scan.pdf'
            write_scanned_pdf(path, skew=0.6)
            pages = dictionary_output(str(path), keep_chars=True)
            skewed = [
                char.get('rotation')
                for block in pages[0]['blocks']
                for line in block['lines']
                for span in line['spans']
                for char in span['chars']
            ]
            repair_ocr_text_layers(path, pages)

        lines = [line for block in pages[0]['blocks'] for line in block['lines']]
        rotations = {
            char.get('rotation')
            for line in lines
            for span in line['spans']
            for char in span['chars']
        }
        texts = [''.join(span['text'] for span in line['spans']).strip() for line in lines]
        # pdftext reports the skew as nearly a full turn.
        self.assertTrue(any(rotation and rotation > 6.0 for rotation in skewed))
        self.assertEqual(texts, ['the nude human figure ex-', 'pressed more than status'])
        self.assertEqual(rotations, {0.0})
        for line in lines:
            self.assertLess(line['bbox'][2], 200.0)

    def test_keeps_a_single_hyphen_where_the_text_layer_has_one(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'scan.pdf'
            write_scanned_pdf(path, 'the nude human figure ex-')
            pages = dictionary_output(str(path), keep_chars=True)
            repair_ocr_text_layers(path, pages)

        first = pages[0]['blocks'][0]['lines'][0]
        self.assertEqual(
            ''.join(span['text'] for span in first['spans']).strip(), 'the nude human figure ex-'
        )

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

    def test_drops_the_text_layer_of_a_blank_page(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'blank.pdf'
            write_blank_scan_pdf(path)
            pages = dictionary_output(str(path), keep_chars=True)
            repair_ocr_text_layers(path, pages)

        self.assertEqual(pages[0]['blocks'], [])

    def test_keeps_a_line_off_the_ink_of_a_printed_page(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'scan.pdf'
            write_scanned_pdf(path, extra_text='far below the print')
            pages = dictionary_output(str(path), keep_chars=True)
            repair_ocr_text_layers(path, pages)

        texts = [
            ''.join(span['text'] for span in line['spans']).strip()
            for block in pages[0]['blocks']
            for line in block['lines']
        ]
        self.assertIn('far below the print', texts)


if __name__ == '__main__':
    unittest.main()
