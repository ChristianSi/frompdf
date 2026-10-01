from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class ScriptRange:
    """A superscript or subscript range in decoded plain text."""

    start: int
    end: int
    kind: Literal['sup', 'sub']


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
    scripts: tuple[ScriptRange, ...] = field(default=(), kw_only=True)


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
    scripts: tuple[ScriptRange, ...] = field(default=(), kw_only=True)


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


@dataclass
class NoteFragment:
    """A piece of a note, retaining its source page and preceding whitespace."""

    text: str
    page: PageNumber
    separator: str = ''
    scripts: tuple[ScriptRange, ...] = field(default=(), kw_only=True)


@dataclass
class Footnote(Block):
    """A numbered note with page-aware text, later moved to a Notes section."""

    label: str = '1'
    fragments: list[NoteFragment] = field(default_factory=list)
