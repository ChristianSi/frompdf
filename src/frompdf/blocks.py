import math
import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import replace
from itertools import pairwise
from statistics import median

from frompdf.continuations import (
    PageLayout,
    build_page_fragments,
    build_page_layouts,
    continues_across_boundary,
    continues_previous_alignment,
    document_indents_paragraphs,
    join_fragments,
)
from frompdf.figures import FigureLayout, reading_position
from frompdf.footnotes import build_footnote, extract_footnotes, place_footnotes
from frompdf.front_matter import format_front_matter, unquote_blocks_above_title
from frompdf.heading_candidates import find_typographic_heading_lines
from frompdf.line_breaks import hard_line_break_ids, line_by_line_passages
from frompdf.line_features import has_alphanumeric, same_physical_line
from frompdf.lists import ListMarker, find_list_items
from frompdf.models import (
    HARD_LINE_BREAK,
    Block,
    BlockQuote,
    Heading,
    Image,
    Line,
    ListItem,
    PageNumber,
    Paragraph,
    Table,
    TableCell,
    TextFragment,
)
from frompdf.page_context import (
    ColumnContext,
    margin_left_edges,
    nearest_column_index,
    percentile_90,
)
from frompdf.scripts import AnnotatedText, collapse_annotated_whitespace, join_annotated_texts
from frompdf.segmentation import find_marker_lines, segment_lines
from frompdf.tables import TableLayout
from frompdf.unhyphenation import (
    document_coordination_tokens,
    document_mixed_case_words,
    document_word_counts,
    spelling_evidence_text,
)

# Tables and figures with captions are placed half a line before the first
# line following their first one, other figures where they lie on their page.
# Figures at the same place are ordered by steps much smaller than that, and
# their captions follow them by an even smaller one.
FIGURE_ORDER_STEP = 1e-3
CAPTION_ORDER_STEP = 1e-6

# Treat clearly heavier font weights as slightly larger for heading detection.
HEADING_WEIGHT_FONT_SIZE_MULTIPLIER = 1.08

# A block must be at least 40% heavier than the document median to get the boost.
HEADING_WEIGHT_BOOST_THRESHOLD = 1.4

# When the document median is zero, only an almost entirely bold block should
# receive the boost. Lower averages usually indicate a bold lead-in followed by
# ordinary paragraph text.
ZERO_MEDIAN_HEADING_MIN_WEIGHT = 600.0

# Long multiline blocks only count as headings when their size is clearly distinct
# from body text. This keeps compact author/address cards as paragraphs.
MULTILINE_HEADING_LINE_THRESHOLD = 4
MULTILINE_HEADING_MIN_FONT_RATIO = 1.16

HEADING_LEVEL_THRESHOLDS = [
    # Derived from 105% of the default font size, repeatedly multiplied by 10%,
    # rounded to the nearest full percentage, and capped at 200%.
    (2.00, 1),
    (1.86, 2),
    (1.69, 3),
    (1.54, 4),
    (1.40, 5),
    (1.27, 6),
    (1.16, 7),
    (1.05, 8),
]


def dominant_document_font_size(line_list: list[Line]) -> float | None:
    """Return the font size most widely used in the document."""
    size_weights: dict[float, int] = defaultdict(int)

    for line_obj in line_list:
        if line_obj.font_size is None or not line_obj.text:
            continue
        size_weights[line_obj.font_size] += max(len(line_obj.text), 1)

    if not size_weights:
        return None

    return max(size_weights.items(), key=lambda item: (item[1], item[0]))[0]


def document_median_avg_weight(line_list: list[Line]) -> float | None:
    """Return the median line average font weight, ignoring lines without usable weight data."""
    weight_list = [line_obj.avg_weight for line_obj in line_list if line_obj.avg_weight is not None]
    if not weight_list:
        return None

    return float(median(weight_list))


def block_font_size(line_list: list[Line]) -> float | None:
    """Return the dominant font size in a Markdown block."""
    size_weights: dict[float, int] = defaultdict(int)

    for line_obj in line_list:
        if line_obj.font_size is None:
            continue
        size_weights[line_obj.font_size] += max(len(line_obj.text), 1)

    if not size_weights:
        return None

    return max(size_weights.items(), key=lambda item: (item[1], item[0]))[0]


def block_avg_weight(line_list: list[Line]) -> float | None:
    """Return the length-weighted average font weight in a Markdown block."""
    weighted_sum = 0.0
    total_weight = 0

    for line_obj in line_list:
        line_weight = len(line_obj.text.strip())
        if not line_weight or line_obj.avg_weight is None:
            continue

        weighted_sum += line_obj.avg_weight * line_weight
        total_weight += line_weight

    if not total_weight:
        return None

    return round(weighted_sum / total_weight, 1)


def build_body_columns_by_page(
    line_list: list[Line], default_font_size: float | None
) -> dict[int, list[ColumnContext]]:
    """Return the likely columns of body text for each page.

    A column extends from its left margin to where most body lines starting
    nearest that margin end, or indefinitely without line ends to tell.
    """
    body_lines_by_page: dict[int, list[Line]] = defaultdict(list)

    for line_obj in line_list:
        if (
            line_obj.x1 is None
            or line_obj.font_size is None
            or default_font_size is None
            or not line_obj.text
            or abs(line_obj.font_size - default_font_size) > 0.2
        ):
            continue

        body_lines_by_page[line_obj.page_no].append(line_obj)

    body_columns_by_page: dict[int, list[ColumnContext]] = {}
    for page_no, body_lines in body_lines_by_page.items():
        lefts = margin_left_edges(body_lines, default_font_size)
        rights: dict[int, list[float]] = defaultdict(list)
        for line_obj in body_lines:
            if line_obj.x1 is not None and line_obj.x2 is not None:
                rights[nearest_column_index(line_obj.x1, lefts)].append(line_obj.x2)
        body_columns_by_page[page_no] = [
            ColumnContext(
                left,
                percentile_90(rights[index]) if rights[index] else math.inf,
                len(rights[index]),
            )
            for index, left in enumerate(lefts)
        ]

    return body_columns_by_page


def is_footnote_like_block(line_list: list[Line]) -> bool:
    """Return whether a small-font block looks like a bottom footnote."""
    if not line_list:
        return False

    first_line = line_list[0]
    return bool(re.match(r'\s*\d+\s+', first_line.text))


def indent_threshold(font_size: float | None) -> float:
    """Return the required indentation in PDF coordinate units."""
    if font_size is None:
        return 6.0

    return max(font_size * 0.8, 6.0)


def is_indented_line(line_obj: Line, body_columns: list[ColumnContext], threshold: float) -> bool:
    """Return whether a line is indented from its nearest page or column left edge.

    A line starting beyond where the body lines of the nearest column to its
    left end rather starts another column, such as one set in smaller type
    than the body and so without body edges of its own, as the methods in
    nature.
    """
    if line_obj.x1 is None:
        return False

    if any(abs(line_obj.x1 - column.left) < threshold for column in body_columns):
        return False

    preceding_columns = [
        column for column in body_columns if column.left <= line_obj.x1 - threshold
    ]
    if not preceding_columns:
        return False

    return line_obj.x1 < max(preceding_columns, key=lambda column: column.left).right


def is_centered_block(line_list: list[Line], threshold: float) -> bool:
    """Return whether lines are centered on each other, with varying left and right edges.

    Pieces of a visual line that pdftext splits count as one line. Lines that
    share a left or right edge, as in justified, ragged, or right-aligned text,
    are not centered.
    """
    extents: list[list[float]] = []
    for index, line_obj in enumerate(line_list):
        if line_obj.x1 is None or line_obj.x2 is None:
            return False
        if index and same_physical_line(line_list[index - 1], line_obj):
            extents[-1][1] = line_obj.x2
        else:
            extents.append([line_obj.x1, line_obj.x2])
    if len(extents) < 2:
        return False

    def spread(values: list[float]) -> float:
        return max(values) - min(values)

    return (
        spread([left for left, _ in extents]) >= threshold
        and spread([right for _, right in extents]) >= threshold
        and spread([(left + right) / 2 for left, right in extents]) < threshold
    )


def visual_line_count(line_list: list[Line]) -> int:
    """Return the number of visual lines formed by consecutive line records."""
    if not line_list:
        return 0
    return 1 + sum(not same_physical_line(left, right) for left, right in pairwise(line_list))


def is_indented_blockquote_block(
    line_list: list[Line],
    body_columns_by_page: dict[int, list[ColumnContext]],
    default_font_size: float | None,
    allow_single_line: bool = False,
) -> bool:
    """Return whether a block is consistently inset from its page or column margin.

    Centered lines with varying left edges are not, as they rather form a
    caption or title. A single visual line counts as one line however many
    pieces pdftext splits it into, as a formula with scripts.
    """
    if visual_line_count(line_list) < 2 and not allow_single_line:
        return False

    font_size = block_font_size(line_list) or default_font_size
    threshold = indent_threshold(font_size)

    for line_obj in line_list:
        body_columns = body_columns_by_page.get(line_obj.page_no, [])
        if not body_columns or not is_indented_line(line_obj, body_columns, threshold):
            return False

    return not is_centered_block(line_list, threshold)


def is_blockquote_block(
    line_list: list[Line],
    default_font_size: float | None,
    body_columns_by_page: dict[int, list[ColumnContext]],
    follows_blockquote: bool = False,
) -> bool:
    """Return whether a group of lines should be rendered as a Markdown block quote."""
    if not line_list or is_footnote_like_block(line_list):
        return False
    font_size = block_font_size(line_list)
    if default_font_size is not None and font_size is not None and font_size > default_font_size:
        return False

    return is_indented_blockquote_block(
        line_list,
        body_columns_by_page,
        default_font_size,
        allow_single_line=follows_blockquote,
    )


def markdown_block_from_lines(
    line_list: list[Line],
    page_number_map: dict[int, PageNumber],
    default_font_size: float | None,
    body_columns_by_page: dict[int, list[ColumnContext]],
    page_layouts: dict[int, PageLayout],
    word_counts: Counter[str],
    mixed_case_words: set[str],
    coordination_tokens: set[str],
    follows_blockquote: bool = False,
    typographic_heading: bool = False,
    list_marker: ListMarker | None = None,
    passage: bool = False,
    marker_line: bool = False,
) -> Block:
    """Build a Markdown block from grouped line records.

    With a list marker, the lines form a list item whose first line starts
    with that marker, which is replaced by a Markdown marker. A passage is set
    off from the text line by line, as quoted verse. A marker line, such as an
    ornament, is inset but not quoted.
    """
    block_class: type[Block] = (
        BlockQuote
        if not typographic_heading
        and not marker_line
        and list_marker is None
        and is_blockquote_block(
            line_list, default_font_size, body_columns_by_page, follows_blockquote
        )
        else Paragraph
    )
    if list_marker is not None:
        first = line_list[0]
        item_text = AnnotatedText(first.text, first.ranges).slice(list_marker.length)
        line_list = [replace(first, text=item_text.text, ranges=item_text.ranges), *line_list[1:]]
    fragments = build_page_fragments(
        line_list,
        page_number_map,
        word_counts,
        mixed_case_words,
        coordination_tokens,
        hard_line_break_ids(
            line_list,
            page_layouts,
            line_list[0].second_word_x1 if list_marker is not None else None,
            passage,
        ),
    )
    annotated = join_fragments(fragments)
    if list_marker is not None:
        return ListItem(
            text=annotated.text,
            ranges=annotated.ranges,
            start_page=fragments[0].page,
            end_page=fragments[-1].page,
            font_size=block_font_size(line_list),
            avg_weight=block_avg_weight(line_list),
            fragments=fragments,
            marker=list_marker.markdown,
        )
    return block_class(
        text=annotated.text,
        ranges=annotated.ranges,
        start_page=fragments[0].page,
        end_page=fragments[-1].page,
        font_size=block_font_size(line_list),
        avg_weight=block_avg_weight(line_list),
        fragments=fragments,
    )


def merge_continued_groups(
    group_list: list[list[Line]],
    page_layouts: dict[int, PageLayout],
    default_font_size: float | None,
    body_columns_by_page: dict[int, list[ColumnContext]],
    heading_lines: dict[int, int],
    list_item_lines: dict[int, int],
) -> list[list[Line]]:
    """Join groups continuing at the top of the next column or page.

    Both parts and the joined group must agree on whether they form a block
    quote, so a quote never absorbs ordinary paragraph text or vice versa. As an
    exception, a continuation is not a quote merely because all of its lines
    keep the indentation of the preceding lines, as in a hanging-indent list.
    List items continue exactly where their recognized lines do.
    """
    indented_paragraphs = document_indents_paragraphs(group_list, page_layouts)
    merged: list[list[Line]] = []
    for group in group_list:
        if merged and (id(merged[-1][0]) in list_item_lines or id(group[0]) in list_item_lines):
            if list_item_lines.get(id(merged[-1][0])) == list_item_lines.get(id(group[0])):
                merged[-1] = merged[-1] + group
            else:
                merged.append(group)
            continue
        if (
            merged
            and id(merged[-1][0]) not in heading_lines
            and id(group[0]) not in heading_lines
            and continues_across_boundary(
                merged[-1],
                group,
                page_layouts,
                indented_paragraphs,
                merged[-2] if len(merged) > 1 else None,
            )
        ):
            previous_is_quote = is_blockquote_block(
                merged[-1], default_font_size, body_columns_by_page
            )
            current_is_quote = is_blockquote_block(
                group, default_font_size, body_columns_by_page, previous_is_quote
            )
            joined = merged[-1] + group
            if previous_is_quote == is_blockquote_block(
                joined, default_font_size, body_columns_by_page
            ) and (
                current_is_quote == previous_is_quote
                or continues_previous_alignment(merged[-1], group, page_layouts)
            ):
                merged[-1] = joined
                continue
        merged.append(group)
    return merged


def should_boost_heading_font_size(block_obj: Block, document_median_weight: float | None) -> bool:
    """Return whether a block is heavy enough, relative to the document, for a heading boost."""
    if block_obj.avg_weight is None or document_median_weight is None:
        return False
    if document_median_weight <= 0:
        return block_obj.avg_weight >= ZERO_MEDIAN_HEADING_MIN_WEIGHT
    return block_obj.avg_weight >= document_median_weight * HEADING_WEIGHT_BOOST_THRESHOLD


def initial_heading_level(
    block_obj: Block, default_font_size: float | None, document_median_weight: float | None
) -> int | None:
    """Return the initial heading level for a block, if adjusted font-size heuristics match."""
    if (
        not isinstance(block_obj, Paragraph)
        or default_font_size is None
        or block_obj.font_size is None
        or len(block_obj.text) > 250
    ):
        return None

    adjusted_font_size = block_obj.font_size
    if should_boost_heading_font_size(block_obj, document_median_weight):
        adjusted_font_size *= HEADING_WEIGHT_FONT_SIZE_MULTIPLIER

    font_ratio = adjusted_font_size / default_font_size
    visible_line_count = sum(bool(line.strip()) for line in block_obj.text.split('\n'))
    if (
        visible_line_count >= MULTILINE_HEADING_LINE_THRESHOLD
        and font_ratio < MULTILINE_HEADING_MIN_FONT_RATIO
    ):
        return None

    for threshold, level in HEADING_LEVEL_THRESHOLDS:
        if font_ratio >= threshold:
            return level

    return None


def compact_unused_heading_levels(block_list: list[Block]) -> None:
    """Remove gaps in heading levels while preserving their relative order."""
    used_levels = sorted(
        {block_obj.level for block_obj in block_list if isinstance(block_obj, Heading)}
    )
    level_map = {old_level: new_level for new_level, old_level in enumerate(used_levels, start=1)}

    for block_obj in block_list:
        if isinstance(block_obj, Heading):
            block_obj.level = level_map[block_obj.level]


def merge_heading_level_pair(block_list: list[Block], kept_level: int) -> None:
    """Merge kept_level + 1 into kept_level and shift deeper levels up."""
    removed_level = kept_level + 1

    for block_obj in block_list:
        if not isinstance(block_obj, Heading):
            continue
        if block_obj.level == removed_level:
            block_obj.level = kept_level
        elif block_obj.level > removed_level:
            block_obj.level -= 1


def merge_extra_heading_levels(block_list: list[Block]) -> None:
    """Merge adjacent heading levels until Markdown's six-level limit is satisfied."""
    while True:
        heading_counts = Counter(
            block_obj.level for block_obj in block_list if isinstance(block_obj, Heading)
        )
        if len(heading_counts) <= 6:
            return

        pairs = [
            (heading_counts[level] + heading_counts[level + 1], -level, level)
            for level in sorted(heading_counts)
            if level >= 2 and level + 1 in heading_counts
        ]
        if not pairs:
            return

        _, _, kept_level = min(pairs)
        merge_heading_level_pair(block_list, kept_level)


def detect_headings(
    block_list: list[Block],
    default_font_size: float | None,
    document_median_weight: float | None,
    typographic_heading_indices: set[int] | None = None,
) -> list[Block]:
    """Recognize headings from adjusted sizes or confirmed source-line evidence.

    Heading levels are compacted, but may still exceed Markdown's six levels.
    """
    converted_blocks: list[Block] = []
    typographic_heading_indices = typographic_heading_indices or set()

    for index, block_obj in enumerate(block_list):
        if (
            len(block_obj.fragments) > 1
            or not has_alphanumeric(block_obj.text)
            or isinstance(block_obj, ListItem)
        ):
            # Text continuing across a page boundary is not a heading, nor are
            # list items, or ornaments and rules without letters or digits.
            converted_blocks.append(block_obj)
            continue
        heading_level = initial_heading_level(block_obj, default_font_size, document_median_weight)
        if heading_level is None and index in typographic_heading_indices:
            # Use the smallest existing heading tier. Glyph heights in small-cap
            # fonts should not create arbitrary extra levels below body text.
            heading_level = HEADING_LEVEL_THRESHOLDS[-1][1]
        if heading_level is None:
            converted_blocks.append(block_obj)
            continue

        annotated = collapse_annotated_whitespace(AnnotatedText(block_obj.text, block_obj.ranges))
        converted_blocks.append(
            Heading(
                text=annotated.text,
                ranges=annotated.ranges,
                start_page=block_obj.start_page,
                end_page=block_obj.end_page,
                font_size=block_obj.font_size,
                avg_weight=block_obj.avg_weight,
                level=heading_level,
            )
        )

    compact_unused_heading_levels(converted_blocks)
    return converted_blocks


# A frame on a page: its page number, top, bottom, left, and right.
Frame = tuple[int, float, float, float, float]


def table_frames(tables: Sequence[TableLayout]) -> list[Frame]:
    """Return the frames of tables, which span the width of their pages."""
    return [
        (frame.page_no, frame.top, frame.bottom, -math.inf, math.inf)
        for table in tables
        for frame in table.frames
    ]


def figure_frames(figures: Sequence[FigureLayout]) -> list[Frame]:
    """Return the frames of figures, enclosing their pictures and captions."""
    frames: list[Frame] = []
    for figure in figures:
        left, top, right, bottom = figure.frame
        frames.append((figure.page_no, top, bottom, left, right))
    return frames


def split_groups_at_frames(
    group_list: list[list[Line]], frames: Sequence[Frame]
) -> list[list[Line]]:
    """Split groups of lines where a frame lies between two of them on the same page.

    Frames are those of tables and figures. A frame lies between two lines
    if it is below the first, above the second, and not beside the first.
    Text continuing past a frame at the top of another column or page stays
    together, so the frame follows it.
    """
    if not frames:
        return group_list
    split: list[list[Line]] = []
    for group in group_list:
        split.append([group[0]])
        for previous, line in zip(group, group[1:], strict=False):
            if any(
                page_no == line.page_no == previous.page_no
                and previous.y2 is not None
                and line.y1 is not None
                and previous.y2 <= top
                and bottom <= line.y1
                and (previous.x1 is None or previous.x1 < right)
                and (previous.x2 is None or left < previous.x2)
                for page_no, top, bottom, left, right in frames
            ):
                split.append([])
            split[-1].append(line)
    return split


def split_groups_at_tables(
    group_list: list[list[Line]], tables: Sequence[TableLayout]
) -> list[list[Line]]:
    """Split groups of lines where a table lies between two of them on the same page."""
    return split_groups_at_frames(group_list, table_frames(tables))


def build_image(figure: FigureLayout, page_number_map: dict[int, PageNumber]) -> Image:
    """Build the block referencing the image written for a figure."""
    page = page_number_map[figure.page_no]
    return Image(text='', start_page=page, end_page=page, target=figure.image or '')


def single_line_text(value: AnnotatedText) -> AnnotatedText:
    """Join the lines of text with spaces, or nothing after hard line breaks."""
    lines = [value.slice(match.start(), match.end()) for match in re.finditer('[^\n]+', value.text)]
    joined = join_annotated_texts(
        line + AnnotatedText('' if line.text.endswith(HARD_LINE_BREAK) else ' ') for line in lines
    )
    return joined.slice(0, len(joined.text.rstrip(' ')))


def build_table(
    layout: TableLayout,
    page_number_map: dict[int, PageNumber],
    word_counts: Counter[str],
    mixed_case_words: set[str],
    coordination_tokens: set[str],
) -> Table:
    """Build a table block, repairing the text of each cell like that of a paragraph.

    Lines within a cell are joined by spaces, and its parts by hard line breaks.
    """
    cells: list[TableCell] = []
    for cell in layout.cells:
        fragments: list[TextFragment] = []
        if cell.parts:
            for fragment in build_page_fragments(
                cell.lines,
                page_number_map,
                word_counts,
                mixed_case_words,
                coordination_tokens,
                {id(part[-1]) for part in cell.parts[:-1]},
            ):
                text = single_line_text(AnnotatedText(fragment.text, fragment.ranges))
                separator = (
                    '' if not fragments or fragments[-1].text.endswith(HARD_LINE_BREAK) else ' '
                )
                fragments.append(
                    TextFragment(text.text, fragment.page, separator, ranges=text.ranges)
                )
        annotated = join_fragments(fragments)
        cells.append(
            TableCell(
                cell.row,
                cell.column,
                cell.row_span,
                cell.column_span,
                annotated.text,
                annotated.ranges,
                fragments,
            )
        )
    return Table(
        text='\n'.join(cell.text for cell in cells if cell.text),
        start_page=page_number_map[layout.frames[0].page_no],
        end_page=page_number_map[layout.frames[-1].page_no],
        row_count=layout.row_count,
        column_count=layout.column_count,
        header_rows=layout.header_rows,
        cells=sorted(cells, key=lambda cell: (cell.row, cell.column)),
    )


def lines_to_markdown_blocks(
    line_list: list[Line],
    page_number_map: dict[int, PageNumber],
    notes_title: str = 'Notes',
    tables: Sequence[TableLayout] = (),
    figures: Sequence[FigureLayout] = (),
) -> list[Block]:
    """Convert line records into Markdown blocks.

    The lines of tables and figures are left out of all other blocks. Tables
    and figures with captions are placed before the first line following
    their first one or that of their caption, other figures where they lie
    among the lines of their page. Figures become images if one was written
    for them, followed by their captions.
    """
    block_list: list[Block] = []
    evidence_texts = [
        spelling_evidence_text(AnnotatedText(line.text, line.ranges)) for line in line_list
    ]
    word_counts = document_word_counts(evidence_texts)
    mixed_case_words = document_mixed_case_words(evidence_texts)
    coordination_tokens = document_coordination_tokens(evidence_texts)
    frame_of_line: dict[int, TableLayout | FigureLayout] = {
        id(line): frame for frame in tables for line in frame.lines
    }
    frame_of_line.update(
        (id(line), figure) for figure in figures for line in [*figure.lines, *figure.caption_lines]
    )
    frame_positions: dict[int, float] = {}
    remaining_lines: list[Line] = []
    for line in line_list:
        frame = frame_of_line.get(id(line))
        if frame is None:
            remaining_lines.append(line)
        elif isinstance(frame, TableLayout) or (
            frame.caption_lines and line is frame.caption_lines[0]
        ):
            frame_positions.setdefault(id(frame), len(remaining_lines) - 0.5)
    for figure in figures:
        if id(figure) not in frame_positions:
            frame_positions[id(figure)] = reading_position(figure, remaining_lines)
    line_list = remaining_lines
    default_font_size = dominant_document_font_size(line_list)
    document_median_weight = document_median_avg_weight(line_list)
    body_columns_by_page = build_body_columns_by_page(line_list, default_font_size)
    source_positions = {id(line): index for index, line in enumerate(line_list)}
    body_lines, notes = extract_footnotes(line_list, default_font_size)
    heading_lines = find_typographic_heading_lines(body_lines)
    typographic_heading_indices: set[int] = set()
    block_positions: list[float] = []
    page_layouts = build_page_layouts(body_lines)
    marker_lines = find_marker_lines(body_lines)
    list_items = find_list_items(body_lines, heading_lines, marker_lines)
    passage_lines = line_by_line_passages(page_layouts)

    group_list = split_groups_at_frames(
        merge_continued_groups(
            segment_lines(
                body_lines, heading_lines, list_items.item_of_line, passage_lines, marker_lines
            ),
            page_layouts,
            default_font_size,
            body_columns_by_page,
            heading_lines,
            list_items.item_of_line,
        ),
        table_frames(tables) + figure_frames(figures),
    )
    # Figures at the same position keep their order, and their captions follow
    # their images.
    figure_positions = {
        id(figure): frame_positions[id(figure)] + index * FIGURE_ORDER_STEP
        for index, figure in enumerate(figures)
    }
    positioned_groups: list[tuple[float, list[Line]]] = [
        (source_positions[id(group[0])], group) for group in group_list
    ]
    # Captions may be the only text of their page.
    caption_layouts = build_page_layouts(
        [line for figure in figures for line in figure.caption_lines]
    )
    page_layouts = caption_layouts | page_layouts
    # A caption forms one paragraph, also where its lines change faces or a
    # sentence ends a line.
    positioned_groups.extend(
        (figure_positions[id(figure)] + CAPTION_ORDER_STEP, figure.caption_lines)
        for figure in figures
        if figure.caption_lines
    )
    positioned_groups.sort(key=lambda item: item[0])

    for position, current_lines in positioned_groups:
        typographic_heading = id(current_lines[0]) in heading_lines
        if typographic_heading:
            typographic_heading_indices.add(len(block_list))
        block_positions.append(position)
        block_list.append(
            markdown_block_from_lines(
                current_lines,
                page_number_map,
                default_font_size,
                body_columns_by_page,
                page_layouts,
                word_counts,
                mixed_case_words,
                coordination_tokens,
                follows_blockquote=bool(block_list) and isinstance(block_list[-1], BlockQuote),
                typographic_heading=typographic_heading,
                list_marker=list_items.markers.get(id(current_lines[0])),
                passage=all(id(line) in passage_lines for line in current_lines),
                marker_line=all(id(line) in marker_lines for line in current_lines),
            )
        )

    source_blocks = block_list
    block_list = detect_headings(
        block_list, default_font_size, document_median_weight, typographic_heading_indices
    )
    dropped = format_front_matter(block_list, source_blocks)
    unquote_blocks_above_title(block_list)
    positioned_blocks: list[tuple[float, Block]] = [
        (position, block_obj)
        for index, (position, block_obj) in enumerate(zip(block_positions, block_list, strict=True))
        if index not in dropped
    ]
    heading_blocks = [block_obj for _, block_obj in positioned_blocks]
    compact_unused_heading_levels(heading_blocks)
    merge_extra_heading_levels(heading_blocks)
    positioned_blocks.extend(
        (
            note.end_index,
            build_footnote(
                note, page_number_map, word_counts, mixed_case_words, coordination_tokens
            ),
        )
        for note in notes
    )
    positioned_blocks.extend(
        (
            frame_positions[id(table)],
            build_table(table, page_number_map, word_counts, mixed_case_words, coordination_tokens),
        )
        for table in tables
    )
    positioned_blocks.extend(
        (figure_positions[id(figure)], build_image(figure, page_number_map))
        for figure in figures
        if figure.image
    )
    positioned_blocks.sort(key=lambda item: item[0])
    return place_footnotes([block for _, block in positioned_blocks], notes_title)
