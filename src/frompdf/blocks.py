import re
from collections import Counter, defaultdict
from statistics import median

from frompdf.models import Block, BlockQuote, Heading, Line, PageNumber, Paragraph
from frompdf.unhyphenation import (
    document_mixed_case_words,
    document_word_counts,
    unhyphenate_block_lines,
)

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


def build_body_lefts_by_page(
    line_list: list[Line], default_font_size: float | None
) -> dict[int, list[float]]:
    """Return likely body-text left edges for each page."""
    weighted_lefts_by_page: dict[int, dict[float, int]] = defaultdict(lambda: defaultdict(int))

    for line_obj in line_list:
        if (
            line_obj.x1 is None
            or line_obj.font_size is None
            or default_font_size is None
            or not line_obj.text
            or abs(line_obj.font_size - default_font_size) > 0.2
        ):
            continue

        rounded_x1 = round(line_obj.x1, 1)
        weighted_lefts_by_page[line_obj.page_no][rounded_x1] += max(len(line_obj.text), 1)

    body_lefts_by_page: dict[int, list[float]] = {}
    column_gap = max((default_font_size or 1.0) * 4.0, 40.0)

    for page_no, weighted_lefts in weighted_lefts_by_page.items():
        if not weighted_lefts:
            continue

        clusters: list[list[float]] = []
        for x1 in sorted(weighted_lefts):
            if not clusters or x1 - clusters[-1][-1] > column_gap:
                clusters.append([x1])
            else:
                clusters[-1].append(x1)

        body_lefts_by_page[page_no] = [min(cluster) for cluster in clusters]

    return body_lefts_by_page


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


def is_indented_line(line_obj: Line, body_lefts: list[float], threshold: float) -> bool:
    """Return whether a line is indented from its nearest page or column left edge."""
    if line_obj.x1 is None:
        return False

    if any(abs(line_obj.x1 - body_left) < threshold for body_left in body_lefts):
        return False

    preceding_body_lefts = [
        body_left for body_left in body_lefts if body_left <= line_obj.x1 - threshold
    ]
    if not preceding_body_lefts:
        return False

    return line_obj.x1 - max(preceding_body_lefts) >= threshold


def is_indented_blockquote_block(
    line_list: list[Line],
    body_lefts_by_page: dict[int, list[float]],
    default_font_size: float | None,
    allow_single_line: bool = False,
) -> bool:
    """Return whether a block is consistently inset from its page or column margin."""
    if len(line_list) < 2 and not allow_single_line:
        return False

    font_size = block_font_size(line_list) or default_font_size
    threshold = indent_threshold(font_size)

    for line_obj in line_list:
        body_lefts = body_lefts_by_page.get(line_obj.page_no, [])
        if not body_lefts or not is_indented_line(line_obj, body_lefts, threshold):
            return False

    return True


def is_blockquote_block(
    line_list: list[Line],
    default_font_size: float | None,
    body_lefts_by_page: dict[int, list[float]],
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
        body_lefts_by_page,
        default_font_size,
        allow_single_line=follows_blockquote,
    )


def markdown_block_from_lines(
    line_list: list[Line],
    page_number_map: dict[int, PageNumber],
    default_font_size: float | None,
    body_lefts_by_page: dict[int, list[float]],
    word_counts: Counter[str],
    mixed_case_words: set[str],
    follows_blockquote: bool = False,
) -> Block:
    """Build a Markdown block from grouped line records."""
    block_class: type[Block] = (
        BlockQuote
        if is_blockquote_block(line_list, default_font_size, body_lefts_by_page, follows_blockquote)
        else Paragraph
    )
    font_size = block_font_size(line_list)
    avg_weight = block_avg_weight(line_list)
    start_page = page_number_map[line_list[0].page_no]
    end_page = page_number_map[line_list[-1].page_no]
    return block_class(
        text=unhyphenate_block_lines(
            (line_obj.text for line_obj in line_list), word_counts, mixed_case_words
        ),
        start_page=start_page,
        end_page=end_page,
        font_size=font_size,
        avg_weight=avg_weight,
    )


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
    block_list: list[Block], default_font_size: float | None, document_median_weight: float | None
) -> list[Block]:
    """Convert paragraph blocks with heading-like adjusted font sizes into Heading blocks."""
    converted_blocks: list[Block] = []

    for block_obj in block_list:
        heading_level = initial_heading_level(block_obj, default_font_size, document_median_weight)
        if heading_level is None:
            converted_blocks.append(block_obj)
            continue

        converted_blocks.append(
            Heading(
                text=re.sub(r'\s+', ' ', block_obj.text).strip(),
                start_page=block_obj.start_page,
                end_page=block_obj.end_page,
                font_size=block_obj.font_size,
                avg_weight=block_obj.avg_weight,
                level=heading_level,
            )
        )

    compact_unused_heading_levels(converted_blocks)
    merge_extra_heading_levels(converted_blocks)
    return converted_blocks


def lines_to_markdown_blocks(
    line_list: list[Line], page_number_map: dict[int, PageNumber]
) -> list[Block]:
    """Convert line records into Markdown blocks."""
    block_list: list[Block] = []
    current_lines: list[Line] = []
    current_page_no: int | None = None
    current_block_no: int | None = None
    default_font_size = dominant_document_font_size(line_list)
    document_median_weight = document_median_avg_weight(line_list)
    body_lefts_by_page = build_body_lefts_by_page(line_list, default_font_size)
    word_counts = document_word_counts(line_obj.text for line_obj in line_list)
    mixed_case_words = document_mixed_case_words(line_obj.text for line_obj in line_list)

    for line_obj in line_list:
        if (
            current_page_no is not None
            and current_block_no is not None
            and (line_obj.page_no != current_page_no or line_obj.block_no != current_block_no)
        ):
            block_list.append(
                markdown_block_from_lines(
                    current_lines,
                    page_number_map,
                    default_font_size,
                    body_lefts_by_page,
                    word_counts,
                    mixed_case_words,
                    follows_blockquote=bool(block_list) and isinstance(block_list[-1], BlockQuote),
                )
            )
            current_lines = []

        current_lines.append(line_obj)
        current_page_no = line_obj.page_no
        current_block_no = line_obj.block_no

    if current_lines:
        block_list.append(
            markdown_block_from_lines(
                current_lines,
                page_number_map,
                default_font_size,
                body_lefts_by_page,
                word_counts,
                mixed_case_words,
                follows_blockquote=bool(block_list) and isinstance(block_list[-1], BlockQuote),
            )
        )

    return detect_headings(block_list, default_font_size, document_median_weight)
