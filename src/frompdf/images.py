"""Write the pictures of a document as image files next to its Markdown output.

Each picture is rendered from its page with pypdfium2, so the image shows the
drawings and the text within its box as the PDF does. The images are written
to a directory named after the PDF, which is created only when needed.
"""

import math
import re
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

import pypdfium2 as pdfium
from PIL.Image import Image as PilImage

from frompdf.figures import FigureLayout

# The directory of images is named like the PDF, followed by this suffix.
IMAGE_DIR_SUFFIX = '-img'
# The names of image files: the page number and the number of the image on
# its page, both padded with zeros. Only directories holding nothing else are
# ever replaced.
IMAGE_NAME_PATTERN = re.compile(r'p\d+-\d+\.(?:png|jpg)')

# Pictures are rendered at this many pixels per inch. Those consisting of
# images only are rendered at the resolution of their images instead, if it
# is lower, but not below the minimum, as images may report wrong sizes.
IMAGE_RESOLUTION = 300.0
MIN_IMAGE_RESOLUTION = 150.0
# No image has more pixels than this, however large its page is.
MAX_IMAGE_PIXELS = 24_000_000
# Pictures are cut this many points beyond their box, which strokes on its
# edges extend past by half their width.
IMAGE_PADDING = 2.0
# The quality of images written as JPEG, as photos are.
JPEG_QUALITY = 90
# A rendered picture without any pixel darker than this is blank, as an
# image that is fully transparent.
BLANK_MIN_LEVEL = 250


class ImageDirError(Exception):
    """An existing directory is in the way of the images and is not safe to replace."""


def build_image_dir_path(input_path: Path) -> Path:
    """Return the default directory for the images of a PDF."""
    return input_path.with_name(f'{input_path.stem}{IMAGE_DIR_SUFFIX}')


def holds_only_images(directory: Path) -> bool:
    """Return whether a path is a directory holding nothing but image files as written here."""
    if directory.is_symlink() or not directory.is_dir():
        return False
    return all(
        IMAGE_NAME_PATTERN.fullmatch(entry.name) and entry.is_file() and not entry.is_symlink()
        for entry in directory.iterdir()
    )


def backup_existing_image_dir(image_dir: Path) -> None:
    """Move an existing directory of images aside before writing a new one.

    The directory is renamed by appending `.bak`, replacing an older backup.
    Neither is touched if it holds anything but images as written here, as a
    directory of the user that merely shares the name.
    """
    if not image_dir.exists() and not image_dir.is_symlink():
        return
    backup = image_dir.with_name(f'{image_dir.name}.bak')
    for path in (image_dir, backup):
        if (path.exists() or path.is_symlink()) and not holds_only_images(path):
            raise ImageDirError(
                f'Not replacing {path}: it is not a directory holding only images written by '
                'frompdf. Move it away, or use --no-images.'
            )
    if backup.exists():
        for entry in backup.iterdir():
            entry.unlink()
        backup.rmdir()
    image_dir.replace(backup)


def figure_resolution(figure: FigureLayout) -> float:
    """Return the resolution to render a picture at, in pixels per inch."""
    if figure.resolution is None:
        return IMAGE_RESOLUTION
    return min(IMAGE_RESOLUTION, max(figure.resolution, MIN_IMAGE_RESOLUTION))


def render_figure(page: pdfium.PdfPage, figure: FigureLayout) -> PilImage:
    """Render the box of a picture from its page.

    The box is in `pdftext` coordinates: points from the top left of the
    page, whose height `pdftext` rounds up.
    """
    width, height = page.get_size()
    slack = math.ceil(height) - height
    left = max(figure.box[0] - IMAGE_PADDING, 0.0)
    top = max(figure.box[1] - slack - IMAGE_PADDING, 0.0)
    right = min(figure.box[2] + IMAGE_PADDING, width)
    bottom = min(figure.box[3] - slack + IMAGE_PADDING, height)
    scale = figure_resolution(figure) / 72.0
    area = max(right - left, 1.0) * max(bottom - top, 1.0)
    scale = min(scale, math.sqrt(MAX_IMAGE_PIXELS / area))
    bitmap = page.render(
        # Annotated as int by pypdfium2, which accepts any number.
        scale=scale,  # pyright: ignore[reportArgumentType]
        crop=(left, height - bottom, width - right, top),
    )
    return bitmap.to_pil().convert('RGB')


def is_blank(image: PilImage) -> bool:
    """Return whether an image shows nothing but white."""
    return not any(image.convert('L').histogram()[:BLANK_MIN_LEVEL])


def build_image_name(
    page_no: int, page_count: int, image_no: int, image_count: int, suffix: str
) -> str:
    """Return the file name of an image, such as `p03-1.png`.

    The page number is padded with zeros to as many digits as the number of
    pages of the document has, and the number of the image to as many as the
    number of images on its page has, so the names sort in order.
    """
    page_digits = len(str(page_count))
    image_digits = len(str(image_count))
    return f'p{page_no:0{page_digits}d}-{image_no:0{image_digits}d}.{suffix}'


def write_images(input_path: Path, figures: Sequence[FigureLayout], image_dir: Path) -> int:
    """Write the images of figures into a directory and return their number.

    Each figure records the path of its image relative to the parent of the
    directory. Blank pictures get no image. The directory is created when the
    first image is written, after moving an existing one aside.
    """
    written = 0
    figures_by_page: dict[int, list[FigureLayout]] = defaultdict(list)
    for figure in figures:
        figures_by_page[figure.page_no].append(figure)
    pdf = pdfium.PdfDocument(input_path)
    try:
        page_count = len(pdf)
        for page_no, page_figures in figures_by_page.items():
            if page_no > page_count:
                continue
            # All pictures of a page are rendered before any is written, as
            # their names depend on how many of them are not blank.
            rendered: list[tuple[FigureLayout, PilImage]] = []
            page = pdf[page_no - 1]
            try:
                for figure in page_figures:
                    if figure.box[2] <= figure.box[0]:
                        continue
                    image = render_figure(page, figure)
                    if not is_blank(image):
                        rendered.append((figure, image))
            finally:
                page.close()
            if rendered and not written:
                backup_existing_image_dir(image_dir)
                image_dir.mkdir()
            for image_no, (figure, image) in enumerate(rendered, start=1):
                suffix = 'jpg' if figure.lossy else 'png'
                name = build_image_name(page_no, page_count, image_no, len(rendered), suffix)
                if figure.lossy:
                    image.save(image_dir / name, quality=JPEG_QUALITY, optimize=True)
                else:
                    image.save(image_dir / name, optimize=True)
                figure.image = f'{image_dir.name}/{name}'
                written += 1
    finally:
        pdf.close()
    return written
