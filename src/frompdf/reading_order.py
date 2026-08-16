from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

from frompdf.models import Line

# Empty gutters smaller than half an em are commonly just ragged text edges.
MIN_VERTICAL_GUTTER_EM = 0.5
MIN_VERTICAL_GUTTER = 6.0

# A horizontal gap of roughly one body-text line can separate layout regions.
MIN_HORIZONTAL_GAP_EM = 1.0
MIN_HORIZONTAL_GAP = 8.0

# Both sides of a proposed column cut must contain a useful amount of text.
MIN_COLUMN_LINES = 3
MIN_COLUMN_ALNUM_CHARS = 40
MIN_COLUMN_WIDTH_EM = 5.0
MIN_COLUMN_HEIGHT_EM = 2.0
MIN_COLUMN_OVERLAP_EM = 2.0
MIN_COLUMN_OVERLAP_RATIO = 0.35


@dataclass
class LayoutBlock:
    """A pdftext block and its geometry, kept intact during ordering."""

    lines: list[Line]
    original_index: int
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def visible_line_count(self) -> int:
        return sum(bool(line.text.strip()) for line in self.lines)

    @property
    def alnum_char_count(self) -> int:
        return sum(character.isalnum() for line in self.lines for character in line.text)


@dataclass(frozen=True)
class LayoutCut:
    """A whitespace cut and the blocks on either side of it."""

    first: list[LayoutBlock]
    second: list[LayoutBlock]
    gap: float
    score: float


def dominant_font_size(line_list: list[Line]) -> float:
    """Return a text-length-weighted font size for layout thresholds."""
    size_weights: dict[float, int] = defaultdict(int)
    for line_obj in line_list:
        if line_obj.font_size is None or not line_obj.text:
            continue
        size_weights[line_obj.font_size] += max(len(line_obj.text), 1)

    if not size_weights:
        return 10.0
    return max(size_weights.items(), key=lambda item: (item[1], item[0]))[0]


def layout_block_from_lines(line_list: list[Line], original_index: int) -> LayoutBlock | None:
    """Build a positioned layout block, or return None when geometry is unusable."""
    x1_values: list[float] = []
    y1_values: list[float] = []
    x2_values: list[float] = []
    y2_values: list[float] = []
    for line_obj in line_list:
        if None in {line_obj.x1, line_obj.y1, line_obj.x2, line_obj.y2}:
            continue
        assert line_obj.x1 is not None
        assert line_obj.y1 is not None
        assert line_obj.x2 is not None
        assert line_obj.y2 is not None
        x1_values.append(line_obj.x1)
        y1_values.append(line_obj.y1)
        x2_values.append(line_obj.x2)
        y2_values.append(line_obj.y2)

    if not x1_values:
        return None

    return LayoutBlock(
        lines=line_list,
        original_index=original_index,
        x1=min(x1_values),
        y1=min(y1_values),
        x2=max(x2_values),
        y2=max(y2_values),
    )


def projection_gaps(
    block_list: list[LayoutBlock], axis: Literal['horizontal', 'vertical']
) -> list[tuple[float, float]]:
    """Return empty gaps between the union of block projections on one axis."""
    if axis == 'horizontal':
        intervals = sorted((block.y1, block.y2) for block in block_list)
    else:
        intervals = sorted((block.x1, block.x2) for block in block_list)

    if not intervals:
        return []

    gaps: list[tuple[float, float]] = []
    _, current_end = intervals[0]
    for start, end in intervals[1:]:
        if start > current_end:
            gaps.append((current_end, start))
            current_end = end
        else:
            current_end = max(current_end, end)
    return gaps


def split_at_gap(
    block_list: list[LayoutBlock], gap: tuple[float, float], axis: Literal['horizontal', 'vertical']
) -> tuple[list[LayoutBlock], list[LayoutBlock]]:
    """Split blocks around a whitespace gap known not to cross any block."""
    midpoint = sum(gap) / 2
    if axis == 'horizontal':
        first = [block for block in block_list if block.y2 <= midpoint]
        second = [block for block in block_list if block.y1 >= midpoint]
    else:
        first = [block for block in block_list if block.x2 <= midpoint]
        second = [block for block in block_list if block.x1 >= midpoint]
    return first, second


def column_content_is_substantial(block_list: list[LayoutBlock], font_size: float) -> bool:
    """Return whether one side of a cut contains enough text to be a column."""
    if not block_list:
        return False

    visible_lines = sum(block.visible_line_count for block in block_list)
    alnum_chars = sum(block.alnum_char_count for block in block_list)
    x1 = min(block.x1 for block in block_list)
    y1 = min(block.y1 for block in block_list)
    x2 = max(block.x2 for block in block_list)
    y2 = max(block.y2 for block in block_list)
    return (
        visible_lines >= MIN_COLUMN_LINES
        and alnum_chars >= MIN_COLUMN_ALNUM_CHARS
        and x2 - x1 >= font_size * MIN_COLUMN_WIDTH_EM
        and y2 - y1 >= font_size * MIN_COLUMN_HEIGHT_EM
    )


def column_overlap_score(
    first: list[LayoutBlock], second: list[LayoutBlock], font_size: float
) -> float | None:
    """Score vertical coexistence of two substantial proposed columns."""
    if not column_content_is_substantial(first, font_size) or not column_content_is_substantial(
        second, font_size
    ):
        return None

    first_top = min(block.y1 for block in first)
    first_bottom = max(block.y2 for block in first)
    second_top = min(block.y1 for block in second)
    second_bottom = max(block.y2 for block in second)
    overlap = max(0.0, min(first_bottom, second_bottom) - max(first_top, second_top))
    smaller_height = min(first_bottom - first_top, second_bottom - second_top)
    if smaller_height <= 0:
        return None

    overlap_ratio = overlap / smaller_height
    if overlap < font_size * MIN_COLUMN_OVERLAP_EM or overlap_ratio < MIN_COLUMN_OVERLAP_RATIO:
        return None

    smaller_text_size = min(
        sum(block.alnum_char_count for block in first),
        sum(block.alnum_char_count for block in second),
    )
    return overlap_ratio * smaller_text_size


def best_vertical_cut(block_list: list[LayoutBlock], font_size: float) -> LayoutCut | None:
    """Return the strongest whitespace cut separating overlapping columns."""
    minimum_gap = max(MIN_VERTICAL_GUTTER, font_size * MIN_VERTICAL_GUTTER_EM)
    candidates: list[LayoutCut] = []

    for gap in projection_gaps(block_list, 'vertical'):
        gap_width = gap[1] - gap[0]
        if gap_width < minimum_gap:
            continue

        first, second = split_at_gap(block_list, gap, 'vertical')
        overlap_score = column_overlap_score(first, second, font_size)
        if overlap_score is None:
            continue
        candidates.append(
            LayoutCut(
                first=first,
                second=second,
                gap=gap_width,
                score=overlap_score + gap_width,
            )
        )

    if not candidates:
        return None
    return max(candidates, key=lambda cut: cut.score)


def best_horizontal_cut(block_list: list[LayoutBlock], font_size: float) -> LayoutCut | None:
    """Return a horizontal band split that exposes columns in either child."""
    minimum_gap = max(MIN_HORIZONTAL_GAP, font_size * MIN_HORIZONTAL_GAP_EM)
    candidates: list[LayoutCut] = []

    for gap in projection_gaps(block_list, 'horizontal'):
        gap_height = gap[1] - gap[0]
        if gap_height < minimum_gap:
            continue

        first, second = split_at_gap(block_list, gap, 'horizontal')
        if not first or not second:
            continue
        first_column_cut = best_vertical_cut(first, font_size)
        second_column_cut = best_vertical_cut(second, font_size)
        column_score = max(
            first_column_cut.score if first_column_cut is not None else 0.0,
            second_column_cut.score if second_column_cut is not None else 0.0,
        )
        if column_score <= 0:
            continue
        candidates.append(
            LayoutCut(
                first=first,
                second=second,
                gap=gap_height,
                score=column_score + gap_height,
            )
        )

    if not candidates:
        return None
    return max(candidates, key=lambda cut: cut.score)


def order_layout_region(block_list: list[LayoutBlock], font_size: float) -> list[LayoutBlock]:
    """Recursively order a page region while preserving ambiguous input order."""
    if len(block_list) < 2:
        return block_list

    vertical_cut = best_vertical_cut(block_list, font_size)
    if vertical_cut is not None:
        return order_layout_region(vertical_cut.first, font_size) + order_layout_region(
            vertical_cut.second, font_size
        )

    horizontal_cut = best_horizontal_cut(block_list, font_size)
    if horizontal_cut is not None:
        return order_layout_region(horizontal_cut.first, font_size) + order_layout_region(
            horizontal_cut.second, font_size
        )

    return sorted(block_list, key=lambda block: block.original_index)


def order_lines_for_reading(line_list: list[Line]) -> list[Line]:
    """Order intact pdftext blocks by page regions and detected columns."""
    if not line_list:
        return []

    font_size = dominant_font_size(line_list)
    lines_by_page_and_block: dict[tuple[int, int], list[Line]] = defaultdict(list)
    page_order: list[int] = []
    seen_pages: set[int] = set()
    block_order_by_page: dict[int, list[int]] = defaultdict(list)

    for line_obj in line_list:
        if line_obj.page_no not in seen_pages:
            page_order.append(line_obj.page_no)
            seen_pages.add(line_obj.page_no)
        key = (line_obj.page_no, line_obj.block_no)
        if key not in lines_by_page_and_block:
            block_order_by_page[line_obj.page_no].append(line_obj.block_no)
        lines_by_page_and_block[key].append(line_obj)

    ordered_lines: list[Line] = []
    original_index = 0
    for page_no in page_order:
        positioned_blocks: list[LayoutBlock] = []
        original_page_blocks: list[list[Line]] = []
        has_unpositioned_block = False
        for block_no in block_order_by_page[page_no]:
            block_lines = lines_by_page_and_block[(page_no, block_no)]
            original_page_blocks.append(block_lines)
            layout_block = layout_block_from_lines(block_lines, original_index)
            original_index += 1
            if layout_block is None:
                has_unpositioned_block = True
            else:
                positioned_blocks.append(layout_block)

        if has_unpositioned_block:
            for block_lines in original_page_blocks:
                ordered_lines.extend(block_lines)
            continue

        for layout_block in order_layout_region(positioned_blocks, font_size):
            ordered_lines.extend(layout_block.lines)

    return ordered_lines
