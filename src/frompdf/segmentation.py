import re
from collections import defaultdict
from dataclasses import dataclass
from statistics import median

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

# Ignore small size changes caused by rounding or mixed inline typography.
FONT_SIZE_BREAK_RATIO = 1.1
FONT_SIZE_BREAK_POINTS = 0.75
FONT_WEIGHT_BREAK = 200.0

# Margin clusters farther apart than this are treated as separate columns.
MIN_COLUMN_GAP = 40.0
MIN_COLUMN_GAP_EM = 4.0

# Sparse synthetic or highly irregular pages should retain pdftext's decisions.
MIN_RHYTHM_SAMPLES = 3
MIN_COLUMN_LINES = 5

SENTENCE_END_PATTERN = re.compile(r'[.!?…][’”\'"\]\)}»›]*(?:\d+)?$')
WORD_BREAK_HYPHEN_PATTERN = re.compile(r'\w[-\u00ad]$')
FONT_SUBSET_PREFIX_PATTERN = re.compile(r'^[A-Z]{6}\+')
FONT_FACE_SUFFIX_PATTERN = re.compile(
    r'(?:[-_.](?:black|bold|bolditalic|bolditalicmt|boldmt|boldoblique|book|bookitalic|'
    r'demibold|heavy|italic|italicmt|light|medi|medium|mediumitalic|oblique|regular|'
    r'regu|reguital|semibold|thin|b|bd|bi|i|it|sb)(?:\+\d+)?)$',
    flags=re.IGNORECASE,
)
ATTACHED_FONT_VENDOR_SUFFIX_PATTERN = re.compile(r'(?<![\s-])MT$', flags=re.IGNORECASE)


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


def close_font_size(left: float | None, right: float | None) -> bool:
    """Return whether two line font sizes are visually compatible."""
    if left is None or right is None:
        return True
    return abs(left - right) <= max(0.3, max(left, right) * 0.04)


def visibly_different_font_sizes(left: float | None, right: float | None) -> bool:
    """Return whether two dominant sizes differ enough to signal distinct layout roles."""
    if left is None or right is None:
        return False
    smaller = min(left, right)
    larger = max(left, right)
    return (
        smaller > 0
        and larger - smaller >= FONT_SIZE_BREAK_POINTS
        and larger / smaller >= FONT_SIZE_BREAK_RATIO
    )


def normalized_font_family(font_name: str | None) -> str | None:
    """Normalize a PDF font name to its family, ignoring face and vendor suffixes."""
    if font_name is None:
        return None
    family_name = FONT_SUBSET_PREFIX_PATTERN.sub('', font_name)
    family_name = FONT_FACE_SUFFIX_PATTERN.sub('', family_name)
    family_name = ATTACHED_FONT_VENDOR_SUFFIX_PATTERN.sub('', family_name)
    return family_name.casefold()


def normalized_font_name(font_name: str | None) -> str | None:
    """Normalize an exact PDF font face name for conservative compatibility checks."""
    if font_name is None:
        return None
    return FONT_SUBSET_PREFIX_PATTERN.sub('', font_name).casefold()


def compatible_style(left: Line, right: Line) -> bool:
    """Return whether two lines have compatible dominant typography."""
    if not close_font_size(left.font_size, right.font_size):
        return False
    if (
        left.avg_weight is not None
        and right.avg_weight is not None
        and abs(left.avg_weight - right.avg_weight) >= FONT_WEIGHT_BREAK
    ):
        return False

    left_name = normalized_font_name(left.font_name)
    right_name = normalized_font_name(right.font_name)
    return left_name is None or right_name is None or left_name == right_name


def significant_size_change(left: Line, right: Line) -> bool:
    """Return whether the dominant font size visibly changes between two lines."""
    return visibly_different_font_sizes(left.font_size, right.font_size)


def significant_style_change(left: Line, right: Line) -> bool:
    """Return whether dominant size or font family clearly changes."""
    if significant_size_change(left, right):
        return True
    left_name = normalized_font_family(left.font_name)
    right_name = normalized_font_family(right.font_name)
    return left_name is not None and right_name is not None and left_name != right_name


def is_prose_line(line_obj: Line) -> bool:
    """Return whether a line has enough letters for prose-oriented heuristics."""
    return sum(character.isalpha() for character in line_obj.text) >= 8


def is_textual_line(line_obj: Line) -> bool:
    """Return whether a short line still contains meaningful natural-language text."""
    return sum(character.isalpha() for character in line_obj.text) >= 3


def cluster_left_edges(line_list: list[Line], font_size: float) -> list[float]:
    """Return likely body-text left edges, separating widely spaced columns."""
    weighted_lefts: dict[float, int] = defaultdict(int)
    for line_obj in line_list:
        if (
            line_obj.x1 is None
            or line_obj.font_size is None
            or not line_obj.text
            or not close_font_size(line_obj.font_size, font_size)
        ):
            continue
        weighted_lefts[round(line_obj.x1, 1)] += max(len(line_obj.text), 1)

    if not weighted_lefts:
        return []

    cluster_gap = max(MIN_COLUMN_GAP, font_size * MIN_COLUMN_GAP_EM)
    clusters: list[list[float]] = []
    for left in sorted(weighted_lefts):
        if not clusters or left - clusters[-1][-1] > cluster_gap:
            clusters.append([left])
        else:
            clusters[-1].append(left)

    # The leftmost common edge in a cluster is the continuation-line margin;
    # modest first-line indents remain in the same cluster.
    return [min(cluster) for cluster in clusters]


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

    for left, right in zip(line_list, line_list[1:], strict=False):
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


def same_physical_line(left: Line, right: Line) -> bool:
    """Return whether pdftext emitted adjacent fragments from one visual line."""
    if None in {left.x1, left.y1, left.x2, right.x1, right.y1}:
        return False
    assert left.x1 is not None
    assert left.y1 is not None
    assert left.x2 is not None
    assert right.x1 is not None
    assert right.y1 is not None
    font_size = max(left.font_size or 0.0, right.font_size or 0.0, 1.0)
    return abs(right.y1 - left.y1) <= font_size * 0.35 and right.x1 >= left.x2 - font_size * 0.25


def normal_advance_ratios(line_list: list[Line]) -> list[float]:
    """Return plausible ordinary line advances from the already ordered page."""
    ratios: list[float] = []
    for left, right in zip(line_list, line_list[1:], strict=False):
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


def hanging_indents_for_boundary(
    left: Line, right: Line, context: PageContext
) -> tuple[HangingIndentContext, ...]:
    """Return learned hanging-indent patterns shared by two adjacent lines."""
    left_column = column_for_line(left, context)
    right_column = column_for_line(right, context)
    if left_column is None or right_column != left_column:
        return ()
    if left.y1 is None or right.y1 is None:
        return ()
    region_tolerance = context.font_size * 2.5

    return tuple(
        hanging_indent
        for hanging_indent in context.hanging_indents
        if hanging_indent.column_left == left_column.left
        and hanging_indent.y_min - region_tolerance
        <= left.y1
        <= hanging_indent.y_max + region_tolerance
        and hanging_indent.y_min - region_tolerance
        <= right.y1
        <= hanging_indent.y_max + region_tolerance
    )


def continues_hanging_indent_paragraph(previous: Line, current: Line, context: PageContext) -> bool:
    """Return whether current uses a learned hanging continuation margin."""
    if (
        not previous.text.strip()
        or not current.text.strip()
        or significant_size_change(previous, current)
        or not same_flow(previous, current, context)
        or not has_normal_advance(previous, current, context)
    ):
        return False

    font_size = current.font_size or context.font_size
    return any(
        (
            near_left_edge(previous.x1, hanging_indent.start_left, font_size)
            or near_left_edge(previous.x1, hanging_indent.continuation_left, font_size)
        )
        and near_left_edge(current.x1, hanging_indent.continuation_left, font_size)
        for hanging_indent in hanging_indents_for_boundary(previous, current, context)
    )


def begins_hanging_indent_paragraph(previous: Line, current: Line, context: PageContext) -> bool:
    """Return whether an outdented line follows a learned hanging continuation."""
    if (
        not previous.text.strip()
        or not is_prose_line(current)
        or significant_size_change(previous, current)
        or not same_flow(previous, current, context)
    ):
        return False

    font_size = current.font_size or context.font_size
    matching_pattern = any(
        (
            near_left_edge(previous.x1, hanging_indent.start_left, font_size)
            or near_left_edge(previous.x1, hanging_indent.continuation_left, font_size)
        )
        and near_left_edge(current.x1, hanging_indent.start_left, font_size)
        for hanging_indent in hanging_indents_for_boundary(previous, current, context)
    )
    if not matching_pattern:
        return False

    ratio = advance_ratio(previous, current)
    normal = context.normal_advance_ratio
    return ratio is not None and normal is not None and 0 < ratio <= normal + 1.0


def large_advance_supports_break(left: Line, right: Line, context: PageContext) -> bool:
    """Return whether visible spacing follows a completed or unusually short line."""
    if not has_large_advance(left, right, context):
        return False
    column = column_for_line(left, context)
    if column is None:
        return False
    font_size = left.font_size or context.font_size
    return line_is_short(left, column, font_size) or ends_sentence(left.text)


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


def ends_sentence(text: str) -> bool:
    """Return whether text ends in language-independent sentence punctuation."""
    return bool(SENTENCE_END_PATTERN.search(text.rstrip()))


def ends_word_break_hyphen(text: str) -> bool:
    """Return whether a line ends in a likely word-breaking hyphen."""
    return bool(WORD_BREAK_HYPHEN_PATTERN.search(text.rstrip()))


def begins_first_line_indent(
    previous: Line,
    current: Line,
    following: Line | None,
    context: PageContext,
) -> bool:
    """Return whether current has the transient indent of a new paragraph's first line."""
    if (
        following is None
        or current.x1 is None
        or not is_textual_line(previous)
        or not is_prose_line(current)
        or not is_prose_line(following)
        or not compatible_style(current, following)
    ):
        return False
    column = column_for_line(current, context)
    following_column = column_for_line(following, context)
    if column is None or following_column != column or column.line_count < MIN_COLUMN_LINES:
        return False

    font_size = current.font_size or context.font_size
    indent = current.x1 - column.left
    if not (
        font_size * MIN_FIRST_LINE_INDENT_EM <= indent <= font_size * MAX_FIRST_LINE_INDENT_EM
        and near(following.x1, column.left, font_size)
        and has_normal_advance(current, following, context)
    ):
        return False

    return line_is_short(previous, column, font_size) or ends_sentence(previous.text)


def aligned_open_continuation(left: Line, right: Line, context: PageContext) -> bool:
    """Return whether inset lines continue a right-aligned or centered open passage."""
    if left.x1 is None or right.x1 is None or left.x2 is None or right.x2 is None:
        return False
    column = column_for_line(right, context)
    if column is None:
        return False
    font_size = right.font_size or context.font_size
    both_inset = min(left.x1, right.x1) - column.left > font_size * MAX_FIRST_LINE_INDENT_EM
    right_edges_match = abs(left.x2 - right.x2) <= font_size * MARGIN_TOLERANCE_EM
    return both_inset and right_edges_match and not ends_sentence(left.text)


def high_confidence_continuation(left: Line, right: Line, context: PageContext) -> bool:
    """Return whether geometry safely overrides a spurious pdftext block edge."""
    if (
        context.rhythm_sample_count < MIN_RHYTHM_SAMPLES
        or not is_prose_line(left)
        or not is_prose_line(right)
        or not same_flow(left, right, context)
        or not compatible_style(left, right)
        or not has_normal_advance(left, right, context)
    ):
        return False

    column = column_for_line(right, context)
    if column is None or column.line_count < MIN_COLUMN_LINES:
        return False
    font_size = right.font_size or context.font_size
    left_edges_match = near(left.x1, right.x1 or column.left, font_size)
    open_full_line = (
        left_edges_match and line_is_full(left, column, font_size) and not ends_sentence(left.text)
    )
    hyphenated_line = left_edges_match and ends_word_break_hyphen(left.text)
    return open_full_line or hyphenated_line or aligned_open_continuation(left, right, context)


def should_start_new_group(
    preceding: Line | None,
    previous: Line,
    current: Line,
    following: Line | None,
    context: PageContext,
) -> bool:
    """Decide whether current begins a new page-local Markdown block."""
    if previous.page_no != current.page_no:
        return True
    pdftext_break = previous.block_no != current.block_no

    if same_physical_line(previous, current):
        return pdftext_break and not (
            is_prose_line(previous)
            and is_prose_line(current)
            and compatible_style(previous, current)
        )
    if not same_flow(previous, current, context):
        return pdftext_break

    reliable_context = context.rhythm_sample_count >= MIN_RHYTHM_SAMPLES
    if reliable_context:
        if continues_hanging_indent_paragraph(previous, current, context):
            return False
        if begins_hanging_indent_paragraph(previous, current, context):
            return True

        previous_style_is_stable = preceding is None or compatible_style(preceding, previous)
        previous_starts_pdftext_block = preceding is None or preceding.block_no != previous.block_no
        current_style_is_stable = following is not None and compatible_style(current, following)
        if (
            is_prose_line(previous)
            and is_prose_line(current)
            and significant_style_change(previous, current)
            and current_style_is_stable
            and (previous_style_is_stable or previous_starts_pdftext_block)
            and (
                close_font_size(previous.font_size, context.font_size)
                or close_font_size(current.font_size, context.font_size)
            )
        ):
            return True
        if (
            is_prose_line(previous)
            and is_prose_line(current)
            and large_advance_supports_break(previous, current, context)
        ):
            return True
        if begins_first_line_indent(previous, current, following, context):
            return True
    if pdftext_break and high_confidence_continuation(previous, current, context):
        return False
    return pdftext_break


def segment_page(line_list: list[Line]) -> list[list[Line]]:
    """Segment one ordered page into visually supported Markdown block groups."""
    if not line_list:
        return []
    context = build_page_context(line_list)
    groups: list[list[Line]] = [[line_list[0]]]

    for index, current in enumerate(line_list[1:], start=1):
        preceding = line_list[index - 2] if index >= 2 else None
        previous = line_list[index - 1]
        following = line_list[index + 1] if index + 1 < len(line_list) else None
        if should_start_new_group(preceding, previous, current, following, context):
            groups.append([])
        groups[-1].append(current)
    return groups


def segment_lines(line_list: list[Line]) -> list[list[Line]]:
    """Segment ordered lines without ever joining text across page boundaries."""
    groups: list[list[Line]] = []
    current_page: list[Line] = []
    current_page_no: int | None = None

    for line_obj in line_list:
        if current_page_no is not None and line_obj.page_no != current_page_no:
            groups.extend(segment_page(current_page))
            current_page = []
        current_page.append(line_obj)
        current_page_no = line_obj.page_no

    groups.extend(segment_page(current_page))
    return groups
