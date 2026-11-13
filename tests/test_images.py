import tempfile
import unittest
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from PIL import Image as PilImages

from frompdf.figures import FigureLayout
from frompdf.images import (
    ImageDirError,
    backup_existing_image_dir,
    build_image_dir_path,
    build_image_name,
    figure_resolution,
    holds_only_images,
    is_blank,
    write_images,
)
from frompdf.rules import extract_drawings


def write_pdf(path: Path) -> None:
    """Write a PDF of one page, 200 by 300 points, with a red square and a blue triangle.

    The square spans 20 to 80 points from the left and from the top of the
    page; the triangle lies within 100 to 160 points from the left and 200 to
    260 points from the top.
    """
    pdf = pdfium.PdfDocument.new()
    page = pdf.new_page(200, 300)
    square = pdfium_c.FPDFPageObj_CreateNewRect(20, 220, 60, 60)
    pdfium_c.FPDFPageObj_SetFillColor(square, 255, 0, 0, 255)
    pdfium_c.FPDFPath_SetDrawMode(square, pdfium_c.FPDF_FILLMODE_ALTERNATE, False)
    pdfium_c.FPDFPage_InsertObject(page.raw, square)
    triangle = pdfium_c.FPDFPageObj_CreateNewPath(100, 40)
    pdfium_c.FPDFPath_LineTo(triangle, 160, 40)
    pdfium_c.FPDFPath_LineTo(triangle, 130, 100)
    pdfium_c.FPDFPath_Close(triangle)
    pdfium_c.FPDFPageObj_SetFillColor(triangle, 0, 0, 255, 255)
    pdfium_c.FPDFPath_SetDrawMode(triangle, pdfium_c.FPDF_FILLMODE_ALTERNATE, False)
    pdfium_c.FPDFPage_InsertObject(page.raw, triangle)
    pdfium_c.FPDFPage_GenerateContent(page.raw)
    pdf.save(path)
    pdf.close()


class ImageDirTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.root = Path(temp_dir.name)
        self.image_dir = self.root / 'paper-img'
        self.backup = self.root / 'paper-img.bak'

    def test_image_dir_is_named_after_the_pdf(self) -> None:
        self.assertEqual(build_image_dir_path(Path('docs/my.paper.pdf')), Path('docs/my.paper-img'))

    def test_directory_of_images_is_moved_aside(self) -> None:
        self.image_dir.mkdir()
        (self.image_dir / 'p1-1.png').write_text('old')

        backup_existing_image_dir(self.image_dir)

        self.assertFalse(self.image_dir.exists())
        self.assertEqual((self.backup / 'p1-1.png').read_text(), 'old')

    def test_older_backup_of_images_is_replaced(self) -> None:
        self.image_dir.mkdir()
        (self.image_dir / 'p1-1.png').write_text('new')
        self.backup.mkdir()
        (self.backup / 'p12-3.jpg').write_text('old')

        backup_existing_image_dir(self.image_dir)

        self.assertEqual([entry.name for entry in self.backup.iterdir()], ['p1-1.png'])

    def test_missing_directory_needs_no_backup(self) -> None:
        backup_existing_image_dir(self.image_dir)

        self.assertFalse(self.backup.exists())

    def test_directory_with_other_files_is_not_touched(self) -> None:
        self.image_dir.mkdir()
        (self.image_dir / 'p1-1.png').write_text('image')
        (self.image_dir / 'notes.txt').write_text('mine')

        with self.assertRaises(ImageDirError):
            backup_existing_image_dir(self.image_dir)

        self.assertEqual((self.image_dir / 'notes.txt').read_text(), 'mine')
        self.assertFalse(self.backup.exists())

    def test_backup_with_other_files_is_not_replaced(self) -> None:
        self.image_dir.mkdir()
        (self.image_dir / 'p1-1.png').write_text('image')
        self.backup.mkdir()
        (self.backup / 'thesis.tex').write_text('mine')

        with self.assertRaises(ImageDirError):
            backup_existing_image_dir(self.image_dir)

        self.assertEqual((self.backup / 'thesis.tex').read_text(), 'mine')
        self.assertTrue((self.image_dir / 'p1-1.png').exists())

    def test_only_directories_of_image_files_hold_only_images(self) -> None:
        self.image_dir.mkdir()
        self.assertTrue(holds_only_images(self.image_dir))
        (self.image_dir / 'p1-1.png').write_text('image')
        (self.image_dir / 'p10-12.jpg').write_text('image')
        self.assertTrue(holds_only_images(self.image_dir))

        for name in ('p1.png', 'p1-1.gif', 'p1-1.png.txt', 'xp1-1.png'):
            with self.subTest(name):
                other = self.root / name
                other.mkdir()
                (other / name).write_text('other')
                self.assertFalse(holds_only_images(other))

        (self.image_dir / 'p2-1.png').mkdir()
        self.assertFalse(holds_only_images(self.image_dir))
        self.assertFalse(holds_only_images(self.root / 'missing'))
        self.assertFalse(holds_only_images(self.image_dir / 'p1-1.png'))


class ResolutionTests(unittest.TestCase):
    def test_pictures_with_drawings_or_text_use_the_default_resolution(self) -> None:
        self.assertEqual(figure_resolution(FigureLayout(1, (0.0, 0.0, 9.0, 9.0), [], [])), 300.0)

    def test_pictures_of_images_keep_a_lower_resolution_within_limits(self) -> None:
        for resolution, expected in ((200.0, 200.0), (600.0, 300.0), (20.0, 150.0)):
            with self.subTest(resolution):
                figure = FigureLayout(1, (0.0, 0.0, 9.0, 9.0), [], [], resolution=resolution)

                self.assertEqual(figure_resolution(figure), expected)


class ImageNameTests(unittest.TestCase):
    def test_numbers_are_padded_to_the_digits_of_their_counts(self) -> None:
        for args, expected in (
            ((1, 9, 1, 9), 'p1-1.png'),
            ((1, 10, 1, 9), 'p01-1.png'),
            ((12, 12, 3, 3), 'p12-3.png'),
            ((7, 250, 4, 12), 'p007-04.png'),
            ((100, 100, 10, 10), 'p100-10.png'),
        ):
            with self.subTest(args):
                self.assertEqual(build_image_name(*args, 'png'), expected)


class WriteImagesTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.root = Path(temp_dir.name)
        self.pdf_path = self.root / 'paper.pdf'
        self.image_dir = self.root / 'paper-img'
        write_pdf(self.pdf_path)

    def test_pictures_are_cut_from_their_page(self) -> None:
        square = FigureLayout(1, (20.0, 20.0, 80.0, 80.0), [], [])
        triangle = FigureLayout(1, (100.0, 200.0, 160.0, 260.0), [], [], 72.0, True)

        self.assertEqual(write_images(self.pdf_path, [square, triangle], self.image_dir), 2)

        self.assertEqual(square.image, 'paper-img/p1-1.png')
        self.assertEqual(triangle.image, 'paper-img/p1-2.jpg')
        with PilImages.open(self.image_dir / 'p1-1.png') as image:
            # 64 points with padding, at 300 pixels per inch.
            for length in image.size:
                self.assertAlmostEqual(length, 267, delta=1)
            self.assertEqual(image.getpixel((133, 133)), (255, 0, 0))
            self.assertEqual(image.getpixel((2, 2)), (255, 255, 255))
        with PilImages.open(self.image_dir / 'p1-2.jpg') as image:
            # Images alone are not rendered below 150 pixels per inch.
            for length in image.size:
                self.assertAlmostEqual(length, 133, delta=1)
            red, green, blue = image.getpixel((66, 40))
            self.assertGreater(blue, 200)
            self.assertLess(red + green, 60)

    def test_image_numbers_are_padded_for_pages_with_ten_images(self) -> None:
        squares = [FigureLayout(1, (20.0, 20.0, 80.0, 80.0), [], []) for _ in range(10)]
        blank = FigureLayout(1, (20.0, 100.0, 80.0, 160.0), [], [])

        self.assertEqual(write_images(self.pdf_path, [*squares, blank], self.image_dir), 10)

        self.assertEqual(squares[0].image, 'paper-img/p1-01.png')
        self.assertEqual(squares[9].image, 'paper-img/p1-10.png')
        self.assertIsNone(blank.image)

    def test_blank_pictures_get_no_image_and_no_directory(self) -> None:
        blank = FigureLayout(1, (20.0, 100.0, 80.0, 160.0), [], [])

        self.assertEqual(write_images(self.pdf_path, [blank], self.image_dir), 0)

        self.assertIsNone(blank.image)
        self.assertFalse(self.image_dir.exists())

    def test_existing_images_are_moved_aside_when_writing(self) -> None:
        self.image_dir.mkdir()
        (self.image_dir / 'p7-1.png').write_text('old')
        square = FigureLayout(1, (20.0, 20.0, 80.0, 80.0), [], [])

        write_images(self.pdf_path, [square], self.image_dir)

        self.assertEqual([entry.name for entry in self.image_dir.iterdir()], ['p1-1.png'])
        self.assertTrue((self.root / 'paper-img.bak' / 'p7-1.png').exists())

    def test_foreign_directory_stops_writing(self) -> None:
        self.image_dir.mkdir()
        (self.image_dir / 'notes.txt').write_text('mine')
        square = FigureLayout(1, (20.0, 20.0, 80.0, 80.0), [], [])

        with self.assertRaises(ImageDirError):
            write_images(self.pdf_path, [square], self.image_dir)

        self.assertEqual([entry.name for entry in self.image_dir.iterdir()], ['notes.txt'])
        self.assertIsNone(square.image)

    def test_blank_images_show_only_white(self) -> None:
        self.assertTrue(is_blank(PilImages.new('RGB', (4, 4), (255, 255, 255))))
        self.assertFalse(is_blank(PilImages.new('RGB', (4, 4), (255, 255, 0))))


class DrawingExtractionTests(unittest.TestCase):
    def test_paths_are_reported_with_their_boxes_and_diagonals(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / 'paper.pdf'
            write_pdf(pdf_path)

            drawings = extract_drawings(pdf_path, [{'rotation': 0}])  # type: ignore[list-item]

        self.assertEqual(
            [(drawing.kind, drawing.box, drawing.detail) for drawing in drawings[1]],
            [
                ('path', (20.0, 20.0, 80.0, 80.0), 0),
                ('path', (100.0, 200.0, 160.0, 260.0), 2),
            ],
        )


if __name__ == '__main__':
    unittest.main()
