from dataclasses import dataclass


@dataclass
class Line:
    """A flattened line record extracted from pdftext output."""

    text: str
    page_no: int
    block_no: int
    line_no_on_page: int
    font_size: float | None
    x1: float | None
    y1: float | None
    x2: float | None
    y2: float | None
    rel_x: float | None
    rel_y: float | None
    avg_weight: float | None
    font_name: str | None = None


@dataclass
class PageNumber:
    """A raw PDF page number with optional visible page label."""

    raw: int
    visible: str | None


@dataclass
class Block:
    """A Markdown block extracted from a PDF."""

    text: str
    start_page: PageNumber
    end_page: PageNumber
    font_size: float | None = None
    avg_weight: float | None = None


@dataclass
class Paragraph(Block):
    """A Markdown paragraph."""


@dataclass
class BlockQuote(Block):
    """A Markdown block quote."""


@dataclass
class Heading(Block):
    """A Markdown heading."""

    level: int = 1
