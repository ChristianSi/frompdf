"""Recognize text continuing across columns and pages, and assemble page-aware text."""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import pairwise

from frompdf.models import HARD_LINE_BREAK, Line, PageNumber, TextFragment
from frompdf.scripts import AnnotatedText, join_annotated_texts
from frompdf.segmentation import (
    FONT_WEIGHT_BREAK,
    MAX_FIRST_LINE_INDENT_EM,
    MIN_COLUMN_LINES,
    MIN_FIRST_LINE_INDENT_EM,
    PageContext,
    build_page_context,
    close_font_size,
    column_for_line,
    dominant_page_font_size,
    ends_sentence,
    is_prose_line,
    is_textual_line,
    line_is_full,
    line_is_short,
    near,
    same_physical_line,
    same_running_text_line,
    significant_style_change,
)
from frompdf.unhyphenation import unhyphenate_annotated_lines

# A list item at the top of a column starts a new block even when the preceding
# item lacks final punctuation.
LIST_MARKER_PATTERN = re.compile(
    r'^\s*(?:[•●▪◦·∙‣*–—-]|\(?(?:\d{1,3}|[a-zA-Z]|[ivxIVX]{1,4})[.)])\s'
)

# Opening punctuation that may precede the first word of a continued sentence.
OPENING_PUNCTUATION = ' \t"\'“‘„‚«‹»›([{¿¡'

# URLs and e-mail addresses never take final punctuation, so their lack of it
# is no evidence of an unfinished sentence.
TRAILING_ADDRESS_PATTERN = re.compile(r'(?:://|www\.|@)\S*$')

# A column flow ends where no further line of the column follows within this
# advance. More distant material, such as a figure below the text, is ignored,
# while the next row of a table is not.
COLUMN_FLOW_MAX_ADVANCE_EM = 2.0

# A non-indented first line is evidence of a continuation only in documents
# that indent new paragraphs. Flush starts remain common there (after headings,
# in end matter, and at continuations), so a modest share of indented starts
# suffices, while block-paragraph documents show almost none.
MIN_INDENTED_PARAGRAPHS = 5
MIN_INDENTED_PARAGRAPH_SHARE = 0.25

# pdftext splits visual lines at superscripts, font changes, and math. Its
# whitespace at the split usually tells whether the pieces are separate words,
# but not always, as in ceur-open-source's `harm¹ and`, where a gap of 0.4 em
# without a space character separates them. Touching pieces, such as `word`
# and `¹, more`, are joined directly. Gaps are relative to the larger size.
# The threshold lies between a thin space (1/6 em) and the narrowest word
# space of tightly justified TeX lines (about 0.22 em), as before `messages`
# in lipics-51's `Ω(…) messages`.
SAME_LINE_SPACE_GAP_EM = 0.2

# Characters making the denominator of an inline fraction compound, such that
# it needs parentheses after a slash.
FRACTION_OPERATORS = frozenset('+−-±=<>×·/')


@dataclass(frozen=True)
class PageLayout:
    """The body lines of one page with the statistics that segmentation uses."""

    context: PageContext
    lines: tuple[Line, ...]


def build_page_layouts(line_list: list[Line]) -> dict[int, PageLayout]:
    """Group body lines by page and build their layout statistics."""
    lines_by_page: dict[int, list[Line]] = defaultdict(list)
    for line_obj in line_list:
        lines_by_page[line_obj.page_no].append(line_obj)
    return {
        page_no: PageLayout(build_page_context(lines), tuple(lines))
        for page_no, lines in lines_by_page.items()
    }


def begins_lowercase(text: str) -> bool:
    """Return whether text starts with a lower-case word, ignoring opening punctuation."""
    return text.lstrip(OPENING_PUNCTUATION)[:1].islower()


def ends_open_sentence(text: str) -> bool:
    """Return whether text lacks final punctuation that a sentence end would need."""
    return not ends_sentence(text) and not TRAILING_ADDRESS_PATTERN.search(text.rstrip())


def is_column_extreme(line_obj: Line, layout: PageLayout, bottom: bool) -> bool:
    """Return whether no nearby line of the same page column is below (or above) a line."""
    column = column_for_line(line_obj, layout.context)
    if column is None or line_obj.y1 is None:
        return False
    font_size = line_obj.font_size or layout.context.font_size
    for other in layout.lines:
        if other.y1 is None or column_for_line(other, layout.context) != column:
            continue
        advance = other.y1 - line_obj.y1 if bottom else line_obj.y1 - other.y1
        if font_size * 0.35 < advance <= font_size * COLUMN_FLOW_MAX_ADVANCE_EM:
            return False
    return True


def crosses_flow_boundary(
    previous: list[Line], right: Line, layouts: dict[int, PageLayout]
) -> bool:
    """Return whether previous ends a column and right starts the next page or a later column.

    Requiring the bottom and top of the columns, and a later column starting
    above the text it continues, distinguishes a column change from a move to
    the next cell of a table row.
    """
    left = previous[-1]
    left_layout = layouts[left.page_no]
    right_layout = layouts[right.page_no]
    if right.page_no == left.page_no:
        context = left_layout.context
        left_column = column_for_line(left, context)
        right_column = column_for_line(right, context)
        start = next(line for line in previous if line.page_no == left.page_no)
        if (
            left_column is None
            or right_column is None
            or left_column.left >= right_column.left
            or start.y1 is None
            or right.y1 is None
            or right.y1 >= start.y1
        ):
            return False
    elif right.page_no != left.page_no + 1:
        return False
    return is_column_extreme(left, left_layout, bottom=True) and is_column_extreme(
        right, right_layout, bottom=False
    )


def physical_line_starts(group: list[Line]) -> list[Line]:
    """Return the lines that begin a visual line, skipping same-line pdftext fragments."""
    return group[:1] + [
        right for left, right in pairwise(group) if not same_physical_line(left, right)
    ]


def column_offset(line_obj: Line, context: PageContext) -> float | None:
    """Return a line's left edge relative to its column margin."""
    column = column_for_line(line_obj, context)
    if column is None or line_obj.x1 is None:
        return None
    return line_obj.x1 - column.left


def ends_at_column_edge(group: list[Line], context: PageContext) -> bool:
    """Return whether a group's last line is not shorter than an ordinary line."""
    last = group[-1]
    column = column_for_line(last, context)
    if column is None or last.x2 is None or column.line_count < MIN_COLUMN_LINES:
        return False
    font_size = last.font_size or context.font_size
    if line_is_short(last, column, font_size):
        return False
    if line_is_full(last, column, font_size):
        return True
    # Ragged-right text rarely reaches the column edge. Compare with earlier
    # lines of the same column instead.
    other_rights = [
        left.x2
        for left, right in pairwise(group)
        if left.x2 is not None
        and left.page_no == last.page_no
        and column_for_line(left, context) == column
        and not same_physical_line(left, right)
    ]
    return bool(other_rights) and last.x2 >= min(other_rights) - font_size * 0.3


def aligned_in_columns(left: Line, right: Line, layouts: dict[int, PageLayout]) -> bool:
    """Return whether two lines start at the same offset from their column margins."""
    left_offset = column_offset(left, layouts[left.page_no].context)
    right_offset = column_offset(right, layouts[right.page_no].context)
    return (
        left_offset is not None
        and right_offset is not None
        and near(right_offset, left_offset, right.font_size or left.font_size or 10.0)
    )


def continues_previous_alignment(
    previous: list[Line], current: list[Line], layouts: dict[int, PageLayout]
) -> bool:
    """Return whether current starts like the continuation lines at the end of previous."""
    return len(physical_line_starts(previous)) > 1 and aligned_in_columns(
        previous[-1], current[0], layouts
    )


def starts_without_indent(
    previous: list[Line], current: list[Line], layouts: dict[int, PageLayout]
) -> bool:
    """Return whether current's first line is aligned like a continuation line."""
    # Prefer a continuation line of the new group. Otherwise, use the old group's
    # last line unless it is that group's first (possibly indented) line.
    reference_line = next(iter(physical_line_starts(current)[1:]), None)
    if reference_line is not None:
        return aligned_in_columns(reference_line, current[0], layouts)
    if len(physical_line_starts(previous)) > 1:
        return aligned_in_columns(previous[-1], current[0], layouts)
    first = current[0]
    first_offset = column_offset(first, layouts[first.page_no].context)
    return first_offset is not None and near(
        first_offset, 0.0, first.font_size or layouts[first.page_no].context.font_size
    )


def first_line_indent(group: list[Line], layouts: dict[int, PageLayout]) -> bool | None:
    """Return whether a group's first line is indented from its next one, if clearly either."""
    starts = physical_line_starts(group)
    if len(starts) < 2:
        return None
    first, second = starts[:2]
    if first.page_no != second.page_no or first.x1 is None or second.x1 is None:
        return None
    context = layouts[first.page_no].context
    if column_for_line(first, context) != column_for_line(second, context):
        return None
    font_size = first.font_size or context.font_size
    indent = first.x1 - second.x1
    if near(indent, 0.0, font_size):
        return False
    if font_size * MIN_FIRST_LINE_INDENT_EM <= indent <= font_size * MAX_FIRST_LINE_INDENT_EM:
        return True
    return None


def document_indents_paragraphs(
    group_list: list[list[Line]], layouts: dict[int, PageLayout]
) -> bool:
    """Return whether body paragraphs in a document conventionally start indented."""
    indented = flush = 0
    for group in group_list:
        first = group[0]
        if not is_prose_line(first) or not close_font_size(
            first.font_size, layouts[first.page_no].context.font_size
        ):
            continue
        indent = first_line_indent(group, layouts)
        indented += indent is True
        flush += indent is False
    return (
        indented >= MIN_INDENTED_PARAGRAPHS
        and indented >= (indented + flush) * MIN_INDENTED_PARAGRAPH_SHARE
    )


def similar_typography(previous: list[Line], current: list[Line]) -> bool:
    """Return whether two groups and their boundary lines share size, family, and weight."""
    last = previous[-1]
    first = current[0]
    if (
        last.avg_weight is not None
        and first.avg_weight is not None
        and abs(last.avg_weight - first.avg_weight) >= FONT_WEIGHT_BREAK
    ):
        return False
    return (
        close_font_size(last.font_size, first.font_size)
        and close_font_size(dominant_page_font_size(previous), dominant_page_font_size(current))
        and not significant_style_change(last, first)
    )


def average_weight(group: list[Line]) -> float | None:
    """Return the text-length-weighted average font weight of a group."""
    weighted = [
        (line_obj.avg_weight, len(line_obj.text.strip()))
        for line_obj in group
        if line_obj.avg_weight is not None and line_obj.text.strip()
    ]
    total = sum(length for _, length in weighted)
    return sum(weight * length for weight, length in weighted) / total if total else None


def is_heading_like(group: list[Line], following: list[Line]) -> bool:
    """Return whether a group is visibly larger or heavier than the following text.

    Whole groups are compared, since a bold lead-in does not make a paragraph
    heavier than the next one overall.
    """
    size = dominant_page_font_size(group)
    following_size = dominant_page_font_size(following)
    if size > following_size and not close_font_size(size, following_size):
        return True
    weight = average_weight(group)
    following_weight = average_weight(following)
    return (
        weight is not None
        and following_weight is not None
        and weight - following_weight >= FONT_WEIGHT_BREAK
    )


def starts_like_indented_paragraph(
    preceding: list[Line] | None, previous: list[Line], layouts: dict[int, PageLayout]
) -> bool:
    """Return whether previous starts indented, or flush only because it follows a heading."""
    return first_line_indent(previous, layouts) is True or (
        preceding is not None and is_heading_like(preceding, previous)
    )


def continues_across_boundary(
    previous: list[Line],
    current: list[Line],
    layouts: dict[int, PageLayout],
    indented_paragraphs: bool = False,
    preceding: list[Line] | None = None,
) -> bool:
    """Return whether current continues previous at the top of a new column or page.

    Typography, a full last line, and a non-indented first line are required.
    These also match paragraphs that happen to end at a column edge, so further
    evidence must support the join: an open sentence, a lower-case
    continuation, or a missing indent where the document and the old paragraph
    (following preceding) show that new paragraphs are indented.
    """
    last = previous[-1]
    first = current[0]
    if (
        not is_prose_line(last)
        or not is_textual_line(first)
        or LIST_MARKER_PATTERN.match(first.text)
        or not crosses_flow_boundary(previous, first, layouts)
        or not similar_typography(previous, current)
        or not ends_at_column_edge(previous, layouts[last.page_no].context)
        or not starts_without_indent(previous, current, layouts)
    ):
        return False
    return (
        ends_open_sentence(last.text)
        or begins_lowercase(first.text)
        or (indented_paragraphs and starts_like_indented_paragraph(preceding, previous, layouts))
    )


def line_separator(left: Line, right: Line) -> str:
    """Return the text separating two consecutive lines of a block.

    Pieces of one visual line are joined by a space or nothing, unless they are
    too far apart to be running text. Other lines are separated by a newline.
    """
    if not same_running_text_line(left, right):
        return '\n'
    assert left.x2 is not None
    assert right.x1 is not None
    font_size = max(left.font_size or 0.0, right.font_size or 0.0, 1.0)
    if (
        left.space_after
        or right.space_before
        or right.x1 - left.x2 >= font_size * SAME_LINE_SPACE_GAP_EM
    ):
        return ' '
    return ''


def fraction_part(value: AnnotatedText) -> AnnotatedText:
    """Return the denominator of an inline fraction, parenthesized if it is compound."""
    if any(char.isspace() or char in FRACTION_OPERATORS for char in value.text):
        return AnnotatedText('(') + value + AnnotatedText(')')
    return value


def physical_line_texts(line_list: list[Line], hard_break_ids: set[int]) -> list[AnnotatedText]:
    """Return the annotated text of each visual line, joining pdftext's pieces of it.

    Lines whose IDs are in hard_break_ids end with HARD_LINE_BREAK. Since
    deliberate breaks never separate pieces of one line, it ends the joined line.
    The denominator of an inline fraction follows its numerator after a slash.
    """
    texts: list[AnnotatedText] = []
    previous: Line | None = None
    for line in line_list:
        text = AnnotatedText(line.text, line.scripts) + AnnotatedText(
            HARD_LINE_BREAK if id(line) in hard_break_ids else ''
        )
        if (
            line.fraction_denominator
            and previous is not None
            and id(previous) not in hard_break_ids
            and previous.page_no == line.page_no
            and previous.line_no_on_page == line.line_no_on_page - 1
        ):
            # The text after the fraction continues the numerator's line.
            texts[-1] = texts[-1] + AnnotatedText('/') + fraction_part(text)
            continue
        separator = '\n' if previous is None else line_separator(previous, line)
        if separator == '\n':
            texts.append(text)
        else:
            texts[-1] = texts[-1] + AnnotatedText(separator) + text
        previous = line
    return texts


def build_page_fragments(
    line_list: list[Line],
    page_numbers: dict[int, PageNumber],
    word_counts: Counter[str],
    mixed_case_words: set[str],
    coordination_tokens: set[str],
    hard_break_ids: set[int] | None = None,
) -> list[TextFragment]:
    """Repair one block's text, attributing joined words to the page where they start.

    Lines whose IDs are in hard_break_ids end with HARD_LINE_BREAK, which also
    keeps words from being joined across the break.
    """
    hard_break_ids = hard_break_ids or set()
    page_lines: list[list[Line]] = []
    for line in line_list:
        if not page_lines or page_lines[-1][-1].page_no != line.page_no:
            page_lines.append([])
        page_lines[-1].append(line)

    fragments: list[TextFragment] = []
    for lines in page_lines:
        annotated = unhyphenate_annotated_lines(
            physical_line_texts(lines, hard_break_ids),
            word_counts,
            mixed_case_words,
            coordination_tokens,
        )
        if fragments:
            previous = fragments[-1]
            left_line = previous.text.rsplit('\n', 1)[-1]
            right_line, line_break, _ = annotated.text.partition('\n')
            previous_value = AnnotatedText(previous.text, previous.scripts)
            left_start = len(previous.text) - len(left_line)
            repaired = unhyphenate_annotated_lines(
                [previous_value.slice(left_start), annotated.slice(0, len(right_line))],
                word_counts,
                mixed_case_words,
                coordination_tokens,
            )
            if repaired.text != left_line + '\n' + right_line:
                # Keep the complete repaired word on its starting page. The
                # next page marker belongs before the remaining text instead.
                joined_line, _, right_remainder = repaired.text.partition('\n')
                previous_value = previous_value.slice(0, left_start) + repaired.slice(
                    0, len(joined_line)
                )
                previous.text, previous.scripts = previous_value.text, previous_value.scripts
                annotated = (
                    repaired.slice(len(joined_line) + 1)
                    + AnnotatedText(line_break if right_remainder else '')
                    + annotated.slice(len(right_line) + len(line_break))
                )
                if not annotated.text:
                    # If repair consumed the entire page fragment, defer the
                    # marker until another fragment or block has text to emit.
                    continue
        fragments.append(
            TextFragment(
                annotated.text,
                page_numbers[lines[0].page_no],
                '\n' if fragments else '',
                scripts=annotated.scripts,
            )
        )
    return fragments


def join_fragments(fragments: list[TextFragment]) -> AnnotatedText:
    """Return the complete text of page fragments, including their separators."""
    return join_annotated_texts(
        AnnotatedText(fragment.separator) + AnnotatedText(fragment.text, fragment.scripts)
        for fragment in fragments
    )
