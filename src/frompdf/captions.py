"""Recognize the captions of figures and tables.

A caption starts with a letter or an opening mark. It is told by its
typography, being set smaller than the body or starting in bold or italics, or
else by a label starting it, such as `Fig. 3` or `Tabelle 2`. Labels are
recognized in English, French, German, Spanish, Portuguese, Japanese, and
Chinese. A caption continues in the lines directly below its first one, until
a sentence ends short of its right edge or the next line starts with another
label.

Figure captions lie below their pictures, as recognized with them. Table
captions lie right above or below their tables and always start with a table
label, as headings and notes set like captions often border on tables. All
tables of a document place their captions alike, on the side where more of
them find one.
"""

import re
from collections.abc import Iterable, Sequence

from frompdf.line_features import close_font_size, ends_sentence
from frompdf.models import Line
from frompdf.page_context import dominant_page_font_size
from frompdf.tables import TableLayout

# A caption starts at most this far from its picture or table, in body ems,
# and reaches at most this far into it.
MAX_CAPTION_GAP_EM = 3.5
MAX_CAPTION_OVERLAP_EM = 0.5
# Characters that may start a caption besides letters, as in "(a) …".
CAPTION_OPENERS = '([{"\'«‹„“‚‘'
# Labels of figures and tables in English, French, German, Spanish,
# Portuguese, Japanese, and Chinese, followed by an Arabic or Roman number,
# as in `Fig. 3`, `FIGURE 2.1`, `Abb. 4a`, `Figura IV`, `図 3`, or `第2図`,
# and `Table 1`, `TABLE IV`, `Tableau 2`, `Tab. 3`, `Tabelle 1`, `Tabla 2`,
# `Cuadro 3`, `Tabela 4`, `Quadro 5`, `表 3`, or `第2表`. Other words may
# follow a number at the start of a line, but these hardly ever do right
# below a picture. Next to a table, sentences such as "Table 3 shows …" often
# do, so a table label at body size without emphasis must stand alone or be
# followed by a separator, as in `Table 3:` or `TABLE IV` on a line of its own.
NUMBER = r'\.?\s*(?:\d+(?:[.\-–]\d+)*[a-z]?|[IVXLC]+)(?=$|[\s.:,;)—–-])'
CJK_NUMBER = r'\s*[0-9０-９]+(?:[.\-–．－][0-9０-９]+)*'
FIGURE_LABEL_PATTERN = re.compile(
    r'(?:(?:Fig(?:ures?|uras?|s)?|FIG(?:URES?|URAS?|S)?|Abb|Abbildung(?:en)?|ABB(?:ILDUNG)?)'
    + NUMBER
    + r'|[図图圖]'
    + CJK_NUMBER
    + r'|第\s*[0-9０-９]+\s*[図图圖])'
)
LATIN_TABLE_LABEL = (
    r'(?:Tab(?:les?|leaux?|ellen?|las?|elas?)?|TAB(?:LES?|LEAUX?|ELLEN?|LAS?|ELAS?)?'
    r'|Cuadros?|CUADROS?|Quadros?|QUADROS?)' + NUMBER
)
CJK_TABLE_LABEL = r'(?:表' + CJK_NUMBER + r'|第\s*[0-9０-９]+\s*表)'
TABLE_LABEL_PATTERN = re.compile(f'{LATIN_TABLE_LABEL}|{CJK_TABLE_LABEL}')
SEPARATED_TABLE_LABEL_PATTERN = re.compile(
    rf'{LATIN_TABLE_LABEL}\s*(?:$|[.:：—–-])|{CJK_TABLE_LABEL}(?:$|\s|[.:：．])'
)
# A caption continues in lines directly below its previous line, separated by
# less than this in ems of its size. It ends after a sentence ending this
# far, in ems, short of the right edge of its lines.
CAPTION_CONTINUATION_GAP_EM = 1.0
CAPTION_SHORT_LINE_EM = 2.0
# The pieces of one line of a caption are at most this far apart, in ems.
# Text further right on the same line is that of a picture beside it.
CAPTION_PIECE_GAP_EM = 2.0


def starts_with_label(line: Line, pattern: re.Pattern[str]) -> bool:
    """Return whether the text of a line starts with a label matching a pattern."""
    return pattern.match(line.text.lstrip()) is not None


def starts_with_any_label(line: Line) -> bool:
    """Return whether the text of a line starts with the label of a figure or table."""
    return starts_with_label(line, FIGURE_LABEL_PATTERN) or starts_with_label(
        line, TABLE_LABEL_PATTERN
    )


def starts_emphasized(line: Line) -> bool:
    """Return whether the text of a line starts in bold or italics."""
    start = len(line.text) - len(line.text.lstrip())
    return any(
        text_range.kind in ('bold', 'italic') and text_range.start <= start < text_range.end
        for text_range in line.ranges
    )


def is_caption_start(
    line: Line, body_size: float, label_pattern: re.Pattern[str] = FIGURE_LABEL_PATTERN
) -> bool:
    """Return whether a line is set as the start of a caption.

    A caption is set smaller than the body, or starts in bold or italics at
    body size, or with a label, such as `Fig. 3`. It starts with a letter or
    an opening mark, unlike footnotes.
    """
    text = line.text.lstrip()
    first = text[:1]
    if not (first.isalpha() or (first and first in CAPTION_OPENERS)):
        return False
    if close_font_size(line.font_size, body_size):
        return starts_emphasized(line) or label_pattern.match(text) is not None
    return line.font_size is not None and line.font_size < body_size


def continues_caption(caption: Sequence[Line], line: Line) -> bool:
    """Return whether a line continues a caption, given its lines so far.

    It continues the visual line of the last one closely to its right, or
    starts directly below it in the same size, unless that line ended a
    sentence short of the right edge of the caption, as the last line of a
    paragraph, or before the label of another caption. Lines share a visual
    line if they overlap by more than half the height of the lower one;
    consecutive lines may overlap a little, as with tight leading.
    """
    last = caption[-1]
    if (
        line.page_no != last.page_no
        or last.y1 is None
        or last.y2 is None
        or line.y1 is None
        or line.y2 is None
        or not close_font_size(line.font_size, last.font_size)
    ):
        return False
    font_size = last.font_size or 0.0
    overlap = min(line.y2, last.y2) - max(line.y1, last.y1)
    if overlap > min(line.y2 - line.y1, last.y2 - last.y1) / 2:
        return (
            line.x1 is None
            or last.x1 is None
            or last.x2 is None
            or last.x1 < line.x1 <= last.x2 + font_size * CAPTION_PIECE_GAP_EM
        )
    if ends_sentence(last.text.strip()):
        right_edge = max(previous.x2 for previous in caption if previous.x2 is not None)
        if starts_with_any_label(line) or (
            last.x2 is not None and last.x2 < right_edge - font_size * CAPTION_SHORT_LINE_EM
        ):
            return False
    return last.y1 < line.y1 and line.y1 - last.y2 <= font_size * CAPTION_CONTINUATION_GAP_EM


def caption_lines(first: Line, page_lines: Sequence[Line], used: set[int]) -> list[Line]:
    """Return the lines of the caption starting with first, following it in reading order."""
    start = next(index for index, line in enumerate(page_lines) if line is first)
    lines = [first]
    for line in page_lines[start + 1 :]:
        if id(line) in used or not continues_caption(lines, line):
            break
        lines.append(line)
    return lines


def is_table_caption_start(line: Line, body_size: float) -> bool:
    """Return whether a line starts with a table label and is set as a caption.

    At body size without emphasis, the label must stand alone or be followed
    by a separator.
    """
    if not starts_with_label(line, TABLE_LABEL_PATTERN):
        return False
    if close_font_size(line.font_size, body_size) and not starts_emphasized(line):
        return starts_with_label(line, SEPARATED_TABLE_LABEL_PATTERN)
    return is_caption_start(line, body_size, TABLE_LABEL_PATTERN)


def overlaps_horizontally(line: Line, left: float, right: float) -> bool:
    """Return whether a line overlaps the horizontal extent between left and right."""
    return line.x1 is not None and line.x2 is not None and line.x1 < right and left < line.x2


def table_extent(table: TableLayout, page_no: int) -> tuple[float, float]:
    """Return the horizontal extent of the lines of a table on a page."""
    boxes = [
        (line.x1, line.x2)
        for line in table.lines
        if line.page_no == page_no and line.x1 is not None and line.x2 is not None
    ]
    if not boxes:
        return float('-inf'), float('inf')
    return min(left for left, _ in boxes), max(right for _, right in boxes)


def caption_above(
    table: TableLayout, page_lines: Sequence[Line], used: set[int], body_size: float
) -> list[Line] | None:
    """Return the lines of the caption above a table, if it has one.

    The caption starts with a table label above the table and ends shortly
    above its top, overlapping it horizontally in some line. Of several, the
    one ending nearest to the table counts.
    """
    frame = table.frames[0]
    left, right = table_extent(table, frame.page_no)
    nearest: tuple[float, list[Line]] | None = None
    for line in page_lines:
        if (
            id(line) in used
            or line.y1 is None
            or line.y1 >= frame.top
            or not is_table_caption_start(line, body_size)
        ):
            continue
        lines = caption_lines(line, page_lines, used)
        bottom = max(caption_line.y2 or 0.0 for caption_line in lines)
        if (
            any(overlaps_horizontally(caption_line, left, right) for caption_line in lines)
            and -body_size * MAX_CAPTION_OVERLAP_EM
            <= frame.top - bottom
            <= body_size * MAX_CAPTION_GAP_EM
            and (nearest is None or bottom > nearest[0])
        ):
            nearest = (bottom, lines)
    return nearest[1] if nearest else None


def caption_below(
    table: TableLayout, page_lines: Sequence[Line], used: set[int], body_size: float
) -> list[Line] | None:
    """Return the lines of the caption below a table, if it has one.

    This is the unused line starting nearest below the table, shortly below
    its bottom, if it starts with a table label and is set as a caption. Only
    lines overlapping the table horizontally count, or captions doing so in
    some line.
    """
    frame = table.frames[-1]
    left, right = table_extent(table, frame.page_no)
    nearest: tuple[float, float, Line] | None = None
    for line in page_lines:
        if (
            id(line) in used
            or line.y1 is None
            or line.x1 is None
            or not -body_size * MAX_CAPTION_OVERLAP_EM
            <= line.y1 - frame.bottom
            <= body_size * MAX_CAPTION_GAP_EM
        ):
            continue
        if not overlaps_horizontally(line, left, right) and not (
            is_table_caption_start(line, body_size)
            and any(
                overlaps_horizontally(caption_line, left, right)
                for caption_line in caption_lines(line, page_lines, used)
            )
        ):
            continue
        if nearest is None or (line.y1, line.x1) < nearest[:2]:
            nearest = (line.y1, line.x1, line)
    if nearest is None or not is_table_caption_start(nearest[2], body_size):
        return None
    return caption_lines(nearest[2], page_lines, used)


def find_table_captions(
    lines: Sequence[Line], tables: Sequence[TableLayout], used: Iterable[int] = ()
) -> None:
    """Assign their captions to tables, in place.

    used are the IDs of lines already taken, such as those of pictures and
    their captions. Captions on the side where more tables find one are
    assigned first; other tables may still find theirs on the other side.
    """
    if not tables:
        return
    body_size = dominant_page_font_size(list(lines))
    table_lines = {id(line) for table in tables for line in table.lines}
    taken = set(used) | table_lines
    lines_by_page: dict[int, list[Line]] = {}
    for line in lines:
        if id(line) not in taken:
            lines_by_page.setdefault(line.page_no, []).append(line)

    def above(table: TableLayout) -> list[Line] | None:
        return caption_above(table, lines_by_page.get(table.page_no, []), taken, body_size)

    def below(table: TableLayout) -> list[Line] | None:
        page_no = table.frames[-1].page_no
        return caption_below(table, lines_by_page.get(page_no, []), taken, body_size)

    above_count = sum(above(table) is not None for table in tables)
    below_count = sum(below(table) is not None for table in tables)
    sides = [(above, True), (below, False)]
    if below_count > above_count:
        sides.reverse()
    for find, is_above in sides:
        for table in tables:
            if table.caption_lines:
                continue
            caption = find(table)
            if caption is not None:
                table.caption_lines = caption
                table.caption_above = is_above
                taken.update(id(line) for line in caption)
