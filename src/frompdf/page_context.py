from collections import defaultdict
from dataclasses import dataclass
from itertools import pairwise
from statistics import median

from frompdf.line_features import (
    close_font_size,
    is_prose_line,
    same_physical_line,
    visibly_different_font_sizes,
)
from frompdf.models import Line

# Paragraph indentation is normally a modest offset from the body margin. Larger
# offsets are more likely to be quotations, side material, or right-aligned text.
MIN_FIRST_LINE_INDENT_EM = 0.55
MAX_FIRST_LINE_INDENT_EM = 2.5
MARGIN_TOLERANCE_EM = 0.3
LEFT_EDGE_CLUSTER_TOLERANCE_EM = 0.2

# Hanging-indent regions need repeated evidence in both directions. A single
# indented run is more likely to be a quote than a bibliography layout. Their
# wider limit accommodates list labels whose bounding boxes extend left of the
# aligned reference text, without broadening ordinary first-line indentation.
MAX_HANGING_INDENT_EM = 4.0
MIN_HANGING_EDGE_LINES = 3
MIN_HANGING_START_TO_CONTINUATION_TRANSITIONS = 2
MIN_HANGING_CONTINUATION_TO_START_TRANSITIONS = 2
MIN_HANGING_CONTINUATION_RUNS = 1

# A line advance this far above the page's normal rhythm is visible paragraph spacing.
LARGE_ADVANCE_MIN_RATIO = 1.25
LARGE_ADVANCE_EXTRA_EM = 0.35
NORMAL_ADVANCE_TOLERANCE_EM = 0.25
# An advance this many times the normal rhythm leaves a gap about as tall as a
# blank line, which separates paragraphs however full the line above is.
BLANK_LINE_ADVANCE_RATIO = 1.7

# Margin clusters farther apart than this are treated as separate columns.
MIN_COLUMN_GAP = 40.0
MIN_COLUMN_GAP_EM = 4.0
# A left edge shared by this many lines of prose is established as a margin.
# Figure labels rarely share an edge with that much text, while three lines
# are few enough for a column ending soon after the top of a page.
MIN_ESTABLISHED_EDGE_LINES = 3

# Sparse synthetic or highly irregular pages should retain pdftext's decisions.
MIN_RHYTHM_SAMPLES = 3
MIN_COLUMN_LINES = 5


@dataclass(frozen=True)
class ColumnContext:
    """Dominant margins for one page column."""

    left: float
    right: float
    line_count: int

    @property
    def width(self) -> float:
        return self.right - self.left


@dataclass(frozen=True)
class HangingIndentContext:
    """Repeated first-line and continuation margins within one page column."""

    column_left: float
    start_left: float
    continuation_left: float
    y_min: float
    y_max: float


@dataclass(frozen=True)
class PageContext:
    """Page-local geometry used to classify boundaries between ordered lines."""

    font_size: float
    normal_advance_ratio: float | None
    rhythm_sample_count: int
    columns: tuple[ColumnContext, ...]
    hanging_indents: tuple[HangingIndentContext, ...]


def dominant_page_font_size(line_list: list[Line]) -> float:
    """Return the text-length-weighted body font size for one page."""
    size_weights: dict[float, int] = defaultdict(int)
    for line_obj in line_list:
        if line_obj.font_size is None or not line_obj.text:
            continue
        size_weights[line_obj.font_size] += max(len(line_obj.text), 1)

    if not size_weights:
        return 10.0
    return max(size_weights.items(), key=lambda item: (item[1], item[0]))[0]


def column_gap(font_size: float | None) -> float:
    """Return the distance between left edges that separates page columns."""
    return max(MIN_COLUMN_GAP, (font_size or 1.0) * MIN_COLUMN_GAP_EM)


def margin_left_edges(line_list: list[Line], font_size: float | None) -> list[float]:
    """Return the left margins of page columns formed by the given body lines.

    Left edges closer than the column gap form one column. Its leftmost common
    edge is the continuation-line margin; modest first-line indents remain in
    the same column. Where the column has an established edge, its leftmost
    one is the margin, so that stray short lines just left of a column, as the
    labels of a figure beside it in nature, neither shift its margin nor join
    it to the next column. Columns with only stray lines keep their leftmost
    edge.
    """
    lefts = sorted(
        round(line_obj.x1, 1) for line_obj in line_list if line_obj.x1 is not None and line_obj.text
    )
    if not lefts:
        return []

    established = established_left_edges(line_list, font_size)
    clusters: list[list[float]] = []
    for left in lefts:
        if not clusters or left - clusters[-1][-1] > column_gap(font_size):
            clusters.append([left])
        else:
            clusters[-1].append(left)

    margins: list[float] = []
    for cluster in clusters:
        established_in_cluster = [edge for edge in established if cluster[0] <= edge <= cluster[-1]]
        margins.append(min(established_in_cluster, default=cluster[0]))
    return margins


def established_left_edges(line_list: list[Line], font_size: float | None) -> list[float]:
    """Return the left edges shared by enough lines of prose, as their leftmost value."""
    tolerance = max(1.5, (font_size or 1.0) * LEFT_EDGE_CLUSTER_TOLERANCE_EM)
    groups: list[list[float]] = []
    prose_lefts = sorted(
        round(line_obj.x1, 1)
        for line_obj in line_list
        if line_obj.x1 is not None and is_prose_line(line_obj)
    )
    for left in prose_lefts:
        if not groups or left - groups[-1][-1] > tolerance:
            groups.append([left])
        else:
            groups[-1].append(left)
    return [group[0] for group in groups if len(group) >= MIN_ESTABLISHED_EDGE_LINES]


def cluster_left_edges(line_list: list[Line], font_size: float) -> list[float]:
    """Return likely body-text left edges, separating widely spaced columns."""
    return margin_left_edges(
        [
            line_obj
            for line_obj in line_list
            if line_obj.font_size is not None and close_font_size(line_obj.font_size, font_size)
        ],
        font_size,
    )


def nearest_column_index(x1: float, left_edges: list[float] | tuple[float, ...]) -> int:
    """Return the index of the nearest page-column left edge."""
    return min(range(len(left_edges)), key=lambda index: abs(x1 - left_edges[index]))


def percentile_90(value_list: list[float]) -> float:
    """Return a simple deterministic 90th percentile."""
    ordered = sorted(value_list)
    return ordered[round((len(ordered) - 1) * 0.9)]


def build_columns(line_list: list[Line], font_size: float) -> tuple[ColumnContext, ...]:
    """Build dominant left and right margins for page columns."""
    left_edges = cluster_left_edges(line_list, font_size)
    if not left_edges:
        return ()

    rights_by_column: dict[int, list[float]] = defaultdict(list)
    counts_by_column: dict[int, int] = defaultdict(int)
    for line_obj in line_list:
        if line_obj.x1 is None or line_obj.x2 is None or not line_obj.text:
            continue
        column_index = nearest_column_index(line_obj.x1, left_edges)
        counts_by_column[column_index] += 1
        if line_obj.font_size is not None and close_font_size(line_obj.font_size, font_size):
            rights_by_column[column_index].append(line_obj.x2)

    columns: list[ColumnContext] = []
    for column_index, left in enumerate(left_edges):
        right_values = rights_by_column.get(column_index, [])
        if not right_values:
            continue
        columns.append(
            ColumnContext(
                left=left,
                right=percentile_90(right_values),
                line_count=counts_by_column[column_index],
            )
        )
    substantial_columns = tuple(
        column for column in columns if column.line_count >= MIN_COLUMN_LINES
    )
    if substantial_columns:
        return substantial_columns
    if not columns:
        return ()
    return (max(columns, key=lambda column: column.line_count),)


def cluster_line_lefts(line_list: list[Line], font_size: float) -> list[tuple[float, int]]:
    """Return tolerant left-edge clusters as median coordinate and line count."""
    tolerance = max(1.5, font_size * LEFT_EDGE_CLUSTER_TOLERANCE_EM)
    clusters: list[list[float]] = []

    for left in sorted(line_obj.x1 for line_obj in line_list if line_obj.x1 is not None):
        if not clusters or left - clusters[-1][-1] > tolerance:
            clusters.append([left])
        else:
            clusters[-1].append(left)

    return [(float(median(cluster)), len(cluster)) for cluster in clusters]


def near_left_edge(value: float | None, edge: float, font_size: float) -> bool:
    """Return whether a line starts at a tolerant learned left edge."""
    tolerance = max(1.5, font_size * LEFT_EDGE_CLUSTER_TOLERANCE_EM)
    return value is not None and abs(value - edge) <= tolerance


def hanging_transition_counts(
    line_list: list[Line], start_left: float, continuation_left: float, font_size: float
) -> tuple[int, int, int]:
    """Count local transitions supporting one hanging-indent edge pair."""
    start_to_continuation = 0
    continuation_to_start = 0
    continuation_runs = 0

    for left, right in pairwise(line_list):
        if left.y1 is None or right.y1 is None:
            continue
        advance = right.y1 - left.y1
        if advance <= 0 or advance > font_size * 2.5:
            continue

        left_is_start = near_left_edge(left.x1, start_left, font_size)
        left_is_continuation = near_left_edge(left.x1, continuation_left, font_size)
        right_is_start = near_left_edge(right.x1, start_left, font_size)
        right_is_continuation = near_left_edge(right.x1, continuation_left, font_size)
        if left_is_start and right_is_continuation:
            start_to_continuation += 1
        elif left_is_continuation and right_is_start:
            continuation_to_start += 1
        elif left_is_continuation and right_is_continuation:
            continuation_runs += 1

    return start_to_continuation, continuation_to_start, continuation_runs


def hanging_edge_regions(
    line_list: list[Line],
    start_left: float,
    continuation_left: float,
    font_size: float,
) -> list[list[Line]]:
    """Return contiguous runs whose lines use either candidate hanging-indent edge."""
    regions: list[list[Line]] = []
    current_region: list[Line] = []

    def uses_learned_edge(line_obj: Line) -> bool:
        return near_left_edge(line_obj.x1, start_left, font_size) or near_left_edge(
            line_obj.x1, continuation_left, font_size
        )

    for line_obj in line_list:
        continues_region = False
        if current_region and current_region[-1].y1 is not None and line_obj.y1 is not None:
            advance = line_obj.y1 - current_region[-1].y1
            continues_region = 0 < advance <= font_size * 2.5

        if uses_learned_edge(line_obj) and (not current_region or continues_region):
            current_region.append(line_obj)
            continue
        if current_region:
            regions.append(current_region)
        current_region = [line_obj] if uses_learned_edge(line_obj) else []

    if current_region:
        regions.append(current_region)
    return regions


def build_hanging_indents(
    line_list: list[Line], font_size: float, columns: tuple[ColumnContext, ...]
) -> tuple[HangingIndentContext, ...]:
    """Learn repeated hanging-indent margins without mistaking one inset run for a quote."""
    if not columns:
        return ()

    lines_by_column: dict[float, list[Line]] = defaultdict(list)
    column_lefts = tuple(column.left for column in columns)
    for line_obj in line_list:
        if (
            line_obj.x1 is None
            or not line_obj.text.strip()
            or visibly_different_font_sizes(line_obj.font_size, font_size)
        ):
            continue
        column_index = nearest_column_index(line_obj.x1, column_lefts)
        lines_by_column[columns[column_index].left].append(line_obj)

    hanging_indents: list[HangingIndentContext] = []
    min_indent = font_size * MIN_FIRST_LINE_INDENT_EM
    max_indent = font_size * MAX_HANGING_INDENT_EM

    for column in columns:
        column_lines = lines_by_column.get(column.left, [])
        edge_clusters = cluster_line_lefts(column_lines, font_size)
        candidates: list[tuple[int, HangingIndentContext]] = []
        for start_left, total_start_count in edge_clusters:
            if total_start_count < MIN_HANGING_EDGE_LINES:
                continue
            for continuation_left, total_continuation_count in edge_clusters:
                indent = continuation_left - start_left
                if (
                    total_continuation_count < MIN_HANGING_EDGE_LINES
                    or not min_indent <= indent <= max_indent
                ):
                    continue

                for region_lines in hanging_edge_regions(
                    column_lines, start_left, continuation_left, font_size
                ):
                    start_count = sum(
                        near_left_edge(line_obj.x1, start_left, font_size)
                        for line_obj in region_lines
                    )
                    continuation_count = sum(
                        near_left_edge(line_obj.x1, continuation_left, font_size)
                        for line_obj in region_lines
                    )
                    if (
                        start_count < MIN_HANGING_EDGE_LINES
                        or continuation_count <= start_count
                        or continuation_count < MIN_HANGING_EDGE_LINES
                    ):
                        continue

                    transitions = hanging_transition_counts(
                        region_lines, start_left, continuation_left, font_size
                    )
                    start_to_continuation, continuation_to_start, continuation_runs = transitions
                    if (
                        start_to_continuation < MIN_HANGING_START_TO_CONTINUATION_TRANSITIONS
                        or continuation_to_start < MIN_HANGING_CONTINUATION_TO_START_TRANSITIONS
                        or continuation_runs < MIN_HANGING_CONTINUATION_RUNS
                    ):
                        continue

                    y_values = [line_obj.y1 for line_obj in region_lines if line_obj.y1 is not None]
                    if not y_values:
                        continue
                    score = (
                        start_to_continuation * 3 + continuation_to_start * 2 + continuation_runs
                    )
                    candidates.append(
                        (
                            score,
                            HangingIndentContext(
                                column_left=column.left,
                                start_left=start_left,
                                continuation_left=continuation_left,
                                y_min=min(y_values),
                                y_max=max(y_values),
                            ),
                        )
                    )

        if candidates:
            selected_regions: list[HangingIndentContext] = []
            for _, candidate in sorted(candidates, key=lambda item: item[0], reverse=True):
                # Right-aligned list labels can create several first-line edges while
                # their text shares one continuation edge (for example, items 9 and 10).
                overlaps_incompatible = any(
                    candidate.y_min <= selected.y_max
                    and selected.y_min <= candidate.y_max
                    and not near_left_edge(
                        candidate.continuation_left, selected.continuation_left, font_size
                    )
                    for selected in selected_regions
                )
                if not overlaps_incompatible:
                    selected_regions.append(candidate)
            hanging_indents.extend(selected_regions)

    return tuple(hanging_indents)


def normal_advance_ratios(line_list: list[Line]) -> list[float]:
    """Return plausible ordinary line advances from the already ordered page."""
    ratios: list[float] = []
    for left, right in pairwise(line_list):
        if (
            left.y1 is None
            or right.y1 is None
            or left.x1 is None
            or left.x2 is None
            or right.x1 is None
            or right.x2 is None
            or not close_font_size(left.font_size, right.font_size)
            or same_physical_line(left, right)
        ):
            continue
        font_size = max(left.font_size or 0.0, right.font_size or 0.0)
        if font_size <= 0:
            continue
        advance = right.y1 - left.y1
        horizontal_overlap = min(left.x2, right.x2) - max(left.x1, right.x1)
        ratio = advance / font_size
        if horizontal_overlap > 0 and 0.65 <= ratio <= 1.65:
            ratios.append(ratio)
    return ratios


def build_page_context(line_list: list[Line]) -> PageContext:
    """Build robust page-local layout statistics."""
    font_size = dominant_page_font_size(line_list)
    advance_ratios = normal_advance_ratios(line_list)
    columns = build_columns(line_list, font_size)
    return PageContext(
        font_size=font_size,
        normal_advance_ratio=float(median(advance_ratios)) if advance_ratios else None,
        rhythm_sample_count=len(advance_ratios),
        columns=columns,
        hanging_indents=build_hanging_indents(line_list, font_size, columns),
    )


def column_for_line(line_obj: Line, context: PageContext) -> ColumnContext | None:
    """Return the nearest dominant column for a positioned line."""
    if line_obj.x1 is None or not context.columns:
        return None
    index = nearest_column_index(line_obj.x1, tuple(column.left for column in context.columns))
    return context.columns[index]


def same_flow(left: Line, right: Line, context: PageContext) -> bool:
    """Return whether adjacent ordered lines plausibly belong to one column flow."""
    if left.page_no != right.page_no:
        return False
    left_column = column_for_line(left, context)
    right_column = column_for_line(right, context)
    if left_column is not None and right_column is not None and left_column != right_column:
        return False
    if same_physical_line(left, right):
        return True
    if None in {left.y1, right.y1, left.x1, left.x2, right.x1, right.x2}:
        return True
    assert left.y1 is not None
    assert right.y1 is not None
    assert left.x1 is not None
    assert left.x2 is not None
    assert right.x1 is not None
    assert right.x2 is not None
    return right.y1 > left.y1 and min(left.x2, right.x2) > max(left.x1, right.x1)


def advance_ratio(left: Line, right: Line) -> float | None:
    """Return baseline advance normalized by the larger line font size."""
    if left.y1 is None or right.y1 is None:
        return None
    font_size = max(left.font_size or 0.0, right.font_size or 0.0)
    if font_size <= 0:
        return None
    return (right.y1 - left.y1) / font_size


def has_large_advance(left: Line, right: Line, context: PageContext) -> bool:
    """Return whether a pair has unusually large page-relative vertical spacing."""
    ratio = advance_ratio(left, right)
    normal = context.normal_advance_ratio
    if ratio is None or normal is None:
        return False
    return ratio >= max(normal * LARGE_ADVANCE_MIN_RATIO, normal + LARGE_ADVANCE_EXTRA_EM)


def has_normal_advance(left: Line, right: Line, context: PageContext) -> bool:
    """Return whether a pair follows the page's ordinary vertical rhythm."""
    ratio = advance_ratio(left, right)
    normal = context.normal_advance_ratio
    if ratio is None or normal is None:
        return False
    return 0 < ratio <= normal + NORMAL_ADVANCE_TOLERANCE_EM


def has_blank_line_advance(left: Line, right: Line, context: PageContext) -> bool:
    """Return whether a pair is separated by a gap about as tall as a blank line."""
    ratio = advance_ratio(left, right)
    normal = context.normal_advance_ratio
    return ratio is not None and normal is not None and ratio >= normal * BLANK_LINE_ADVANCE_RATIO


def near(value: float | None, target: float, font_size: float) -> bool:
    """Return whether a coordinate is close to a target margin."""
    return value is not None and abs(value - target) <= max(2.5, font_size * MARGIN_TOLERANCE_EM)


def line_is_short(line_obj: Line, column: ColumnContext, font_size: float) -> bool:
    """Return whether a line ends unusually early relative to its column."""
    if line_obj.x2 is None or column.width <= 0:
        return False
    shortfall = column.right - line_obj.x2
    return shortfall >= max(font_size * 3.0, column.width * 0.18)


def line_is_full(line_obj: Line, column: ColumnContext, font_size: float) -> bool:
    """Return whether a line reaches the ordinary column right edge."""
    if line_obj.x2 is None or column.width <= 0:
        return False
    shortfall = column.right - line_obj.x2
    return shortfall <= max(font_size * 1.5, column.width * 0.08)
