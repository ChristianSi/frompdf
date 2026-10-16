"""Escape extracted text that Markdown would otherwise interpret as syntax.

Escapes are kept minimal, so the Markdown source stays readable: characters
are only escaped where CommonMark would treat them as markup.
"""

import re
import string
from bisect import bisect_left

from frompdf.models import HARD_LINE_BREAK, ScriptRange
from frompdf.scripts import AnnotatedText

ASCII_PUNCTUATION = frozenset(string.punctuation)
LINE_END_CHARACTERS = frozenset(('\n', HARD_LINE_BREAK))

# Entity and numeric character references, which Markdown decodes.
ENTITY_PATTERN = re.compile(r'&(?:#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});')

# A closing sequence that Markdown strips from the end of an ATX heading.
HEADING_CLOSING_PATTERN = re.compile(r'(?:^|[ \t])(#+)[ \t]*$')

ATX_HEADING_PATTERN = re.compile(r'#{1,6}(?=[ \t]|$)')
BULLET_PATTERN = re.compile(r'[-+](?=[ \t]|$)')
ORDERED_PATTERN = re.compile(r'(\d{1,9})([.)])(?=[ \t]|$)')
# Thematic breaks and setext heading underlines. Lines of asterisks or
# underscores are covered by the inline rules.
DASH_LINE_PATTERN = re.compile(r'-[- \t]*')
EQUALS_LINE_PATTERN = re.compile(r'=+[ \t]*')
LINK_DEFINITION_PATTERN = re.compile(r'\[[^\]]+\]:')

# Markdown allows up to three spaces of indentation before block syntax.
MAX_BLOCK_INDENT = 3


def inline_escape_positions(text: str, protected: set[int]) -> set[int]:
    """Return positions of characters that could start inline markup."""
    positions: set[int] = set()
    for index, char in enumerate(text):
        if index in protected:
            continue
        following = text[index + 1] if index + 1 < len(text) else ''
        if char in '*`':
            # Asterisks can open emphasis even within words.
            positions.add(index)
        elif char == '\\':
            # A backslash escapes following punctuation, and one at a line
            # end would become a hard line break.
            if not following or following in ASCII_PUNCTUATION or following in LINE_END_CHARACTERS:
                positions.add(index)
        elif char == '_':
            # Underscores between letters or digits cannot open or close emphasis.
            preceding = text[index - 1] if index else ''
            if not (preceding.isalnum() and following.isalnum()):
                positions.add(index)
        elif char == '&':
            if ENTITY_PATTERN.match(text, index):
                positions.add(index)
        elif char == '<':
            # Only a tag, comment, processing instruction, or autolink can follow.
            if following in {'/', '!', '?'} or (following.isascii() and following.isalpha()):
                positions.add(index)
    return positions


def list_item_kind(line: str) -> str | None:
    """Return the bullet character or ordered-list delimiter of a list item with content."""
    bullet = BULLET_PATTERN.match(line)
    if bullet and line[bullet.end() :].strip():
        return bullet.group()
    ordered = ORDERED_PATTERN.match(line)
    if ordered and line[ordered.end() :].strip():
        return ordered.group(2)
    return None


def line_start_escape_position(line: str, block_start: bool, list_kind: str | None) -> int | None:
    """Return the offset of a character in a line that would start block syntax.

    list_kind is the kind of list item that the block starts with and that is
    kept as a list. Further items of the same kind continue that list. Other list
    markers at the block start are escaped. On later lines, bullets with content
    and ordered items numbered 1 would interrupt the paragraph.
    """
    if ATX_HEADING_PATTERN.match(line) or line.startswith(('>', '~~~')):
        return 0
    if DASH_LINE_PATTERN.fullmatch(line) or (
        not block_start and EQUALS_LINE_PATTERN.fullmatch(line)
    ):
        return 0
    kind = list_item_kind(line)
    if kind is not None and kind == list_kind:
        return None
    if BULLET_PATTERN.match(line):
        return 0
    ordered = ORDERED_PATTERN.match(line)
    if ordered:
        # Only lists starting with 1 can interrupt a paragraph, and empty items cannot.
        if block_start or (kind is not None and int(ordered.group(1)) == 1):
            return ordered.start(2)
        return None
    if block_start and LINK_DEFINITION_PATTERN.match(line):
        return 0
    return None


def block_escape_positions(
    text: str, protected: set[int], block_line_start: bool, block_list_markers: bool
) -> set[int]:
    """Return positions of characters that would start block syntax at line starts."""
    positions: set[int] = set()
    list_kind: str | None = None
    line_starts = [0] + [match.end() for match in re.finditer('\n', text)]
    for line_start in line_starts:
        block_start = line_start == 0
        if block_start and not block_line_start:
            continue
        start = line_start
        while start < len(text) and text[start] == ' ' and start - line_start < MAX_BLOCK_INDENT:
            start += 1
        if start in protected:
            # Superscripts and subscripts are rendered as inline HTML tags.
            continue
        end = text.find('\n', start)
        line = text[start : end if end >= 0 else len(text)].rstrip(HARD_LINE_BREAK)
        if block_start and block_list_markers:
            list_kind = list_item_kind(line)
        offset = line_start_escape_position(line, block_start, list_kind)
        if offset is not None:
            positions.add(start + offset)
    return positions


def escape_markdown(
    value: AnnotatedText,
    heading: bool = False,
    block_line_start: bool = True,
    block_list_markers: bool = True,
) -> tuple[AnnotatedText, list[int]]:
    """Insert backslashes before text that Markdown would read as syntax.

    Heading text is only parsed as inline content, apart from a trailing closing
    sequence. For other blocks, line starts are checked as well; with
    block_line_start false, the block's first line follows other markup on the
    same line. With block_list_markers, list markers with content at the start
    of the block remain unescaped, so lists in the source still render as lists.

    Script ranges are rendered as inline HTML with their own escaping, so they
    are left alone. Returns the escaped text and the sorted original positions
    before which backslashes were inserted.
    """
    text = value.text
    protected = {index for run in value.scripts for index in range(run.start, run.end)}
    positions = inline_escape_positions(text, protected)
    if heading:
        closing = HEADING_CLOSING_PATTERN.search(text)
        if closing and closing.start(1) not in protected:
            positions.add(closing.start(1))
    else:
        positions |= block_escape_positions(text, protected, block_line_start, block_list_markers)

    insertions = sorted(positions)
    if not insertions:
        return value, []
    pieces: list[str] = []
    previous = 0
    for position in insertions:
        pieces.append(text[previous:position])
        pieces.append('\\')
        previous = position
    pieces.append(text[previous:])
    scripts = tuple(
        ScriptRange(shift_index(insertions, run.start), shift_index(insertions, run.end), run.kind)
        for run in value.scripts
    )
    return AnnotatedText(''.join(pieces), scripts), insertions


def shift_index(insertions: list[int], index: int) -> int:
    """Map an original position to escaped text, before any backslash inserted there."""
    return index + bisect_left(insertions, index)
