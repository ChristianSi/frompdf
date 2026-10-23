from dataclasses import dataclass, field
from typing import Literal

# Marks a deliberate line break in block text until Markdown serialization.
# U+2028 LINE SEPARATOR counts as whitespace, so text normalization, such as
# collapsing heading whitespace, treats it like any other line break.
HARD_LINE_BREAK = ' '


InlineKind = Literal['sup', 'sub', 'bold', 'italic']


@dataclass(frozen=True)
class InlineRange:
    """A superscript, subscript, bold, or italic range in decoded plain text.

    Ranges of different kinds may overlap, such as an italic superscript.
    """

    start: int
    end: int
    kind: InlineKind

    @property
    def is_script(self) -> bool:
        """Return whether the range is a superscript or subscript."""
        return self.kind in ('sup', 'sub')


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
    ranges: tuple[InlineRange, ...] = field(default=(), kw_only=True)
    # Whether pdftext reported whitespace, other than line ends, before or after
    # the text. This tells whether fragments of one visual line need a space.
    space_before: bool = field(default=False, kw_only=True)
    space_after: bool = field(default=False, kw_only=True)
    # Whether the text is the denominator of an inline fraction whose numerator
    # ends the preceding line record.
    fraction_denominator: bool = field(default=False, kw_only=True)
    # Where the text following the first word and its whitespace starts, as
    # the text of a list item following its marker.
    second_word_x1: float | None = field(default=None, kw_only=True)


@dataclass
class PageNumber:
    """A raw PDF page number with optional visible page label."""

    raw: int
    visible: str | None


@dataclass
class TextFragment:
    """A piece of block text, retaining its source page and preceding whitespace."""

    text: str
    page: PageNumber
    separator: str = ''
    ranges: tuple[InlineRange, ...] = field(default=(), kw_only=True)


@dataclass
class Block:
    """A Markdown block extracted from a PDF."""

    text: str
    start_page: PageNumber
    end_page: PageNumber
    font_size: float | None = None
    avg_weight: float | None = None
    ranges: tuple[InlineRange, ...] = field(default=(), kw_only=True)
    # Page-aware pieces of text. Blocks without them are rendered from text.
    fragments: list[TextFragment] = field(default_factory=list, kw_only=True)


@dataclass
class Paragraph(Block):
    """A Markdown paragraph."""


@dataclass
class StrongParagraph(Paragraph):
    """A Markdown paragraph rendered with strong emphasis, such as a subtitle or author name."""


@dataclass
class BlockQuote(Block):
    """A Markdown block quote."""


@dataclass
class Heading(Block):
    """A Markdown heading."""

    level: int = 1


@dataclass
class Footnote(Block):
    """A numbered note with page-aware text, later moved to a Notes section."""

    label: str = '1'


@dataclass
class ListItem(Block):
    """An item of a bulleted or numbered list, with its Markdown list marker.

    The marker is `-` for bulleted items, or a number followed by `.` or `)`.
    """

    marker: str = '-'

    @property
    def number(self) -> int | None:
        """Return the number of an ordered item."""
        return int(self.marker[:-1]) if self.marker[0].isdigit() else None
