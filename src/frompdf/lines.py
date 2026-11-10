import math
import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from difflib import SequenceMatcher
from itertools import pairwise
from typing import Literal
from unicodedata import category, name

from pdftext.schema import (
    Char as PdfTextChar,
)
from pdftext.schema import (
    Line as PdfTextLine,
)
from pdftext.schema import (
    Page,
)
from pdftext.schema import (
    Span as PdfTextSpan,
)

from frompdf.line_features import (
    RUNNING_TEXT_MAX_GAP_EM,
    same_physical_line,
    same_running_text_line,
)
from frompdf.models import InlineRange, Line, Word
from frompdf.scripts import AnnotatedText

BOLD_FONT_NAME_PATTERN = re.compile(
    r'(?:bold|black|heavy|semi[- ]?bold|demi[- ]?bold|[.+_-](?:b|bd|sb)(?:it)?$)',
    flags=re.IGNORECASE,
)

# Bold and italic text are recognized by font names. Reported weights are
# unreliable: cc-style-guide's Roboto-Medium is heavier than its
# SourceSansPro-SemiBold, and intertrans's Calibri-Italic heavier than its
# Calibri-Bold. Beyond conventional names, this covers suffixes such as `.B`
# with encoding variants (`AdvTTa351d857.B+20`), URW Nimbus fonts (`-Medi`,
# `-ReguItal`), and TeX font names (CMBX10, CMTI9).
BOLD_FACE_PATTERN = re.compile(
    r'(?i:bold|black|heavy)|[._-](?:B|Bd|SB|Sb)(?:I|It)?(?:\+\w+)?$'
    r'|(?i:nimbus)\w*-Medi|\b(?i:cmbx?|cmbxti|cmbxsl|sfbx|sfbi)\d'
)
ITALIC_FACE_PATTERN = re.compile(
    r'(?i:italic|oblique|slant|kursiv)|Ital|It(?:MT)?(?:\+\w+)?$|[._-]B?I(?:\+\w+)?$'
    r'|\b(?i:cmti|cmsl|cmbxti|cmbxsl|cmssi|cmitt|sfti|sfsl|sfbi|sfso)\d'
)
# Math italic fonts set variables in italics, as italic text fonts would. Only
# their letters look italic, not their digits and punctuation.
MATH_ITALIC_FONT_NAME_PATTERN = re.compile(
    r'math\W*italic|\b(?:cm|lm)mib?\d|\b(?:new)?(?:r?tx|px)mi', flags=re.IGNORECASE
)
# Other math fonts hold symbols, operators, and delimiters, which their PDF
# flags often mark as italic although they do not look italic.
MATH_FONT_NAME_PATTERN = re.compile(
    r'math|mth|symbol|\b(?:cm|lm)(?:mi|mib|sy|bsy|ex)\d|\b(?:new)?(?:r?tx|px)(?:mi|sy|ex)'
    r'|\bms(?:am|bm)\d|\beu(?:fm|fb|rm|rb|sm|sb|ex)\d',
    flags=re.IGNORECASE,
)
# The PDF font descriptor flag for italic fonts.
ITALIC_FONT_FLAG = 64
# A style used for most letters and digits of a document is its body style.
# Marking it would emphasize everything.
MAX_EMPHASIS_SHARE = 0.5


def round_or_none(value: float | int | None, digits: int = 1) -> float | None:
    """Round a numeric value, or return None."""
    if value is None:
        return None
    return round(float(value), digits)


def get_bbox(
    obj: PdfTextChar | PdfTextLine | PdfTextSpan,
) -> tuple[float | None, float | None, float | None, float | None]:
    """Extract a 4-value bbox tuple from an object, if present."""
    bbox = obj.get('bbox')
    if not isinstance(bbox, list | tuple) or len(bbox) != 4:
        return None, None, None, None

    try:
        x1, y1, x2, y2 = bbox
        return float(x1), float(y1), float(x2), float(y2)
    except (TypeError, ValueError):
        return None, None, None, None


def span_char_text_ranges(span_dict: PdfTextSpan) -> dict[int, tuple[int, int]]:
    """Map pdftext character objects to their ranges in the decoded span text."""
    char_list = span_dict.get('chars', [])
    raw_parts: list[str] = []
    raw_ranges: dict[int, tuple[int, int]] = {}
    raw_offset = 0

    for char_index, char_dict in enumerate(char_list):
        char_text = char_dict.get('char', '')
        # pdftext exposes CRLF as two characters but decodes it to one newline in
        # Span.text. Treat the CR as having no textual representation.
        if char_text == '\r' and char_index + 1 < len(char_list):
            if char_list[char_index + 1].get('char') == '\n':
                continue

        raw_parts.append(char_text)
        raw_ranges[id(char_dict)] = (raw_offset, raw_offset + len(char_text))
        raw_offset += len(char_text)

    raw_text = ''.join(raw_parts)
    decoded_text = span_dict.get('text', '')
    if raw_text == decoded_text:
        return raw_ranges
    text_ranges: dict[int, tuple[int, int]] = {}
    opcodes = SequenceMatcher(None, raw_text, decoded_text, autojunk=False).get_opcodes()

    for char_id, (raw_start, raw_end) in raw_ranges.items():
        for tag, raw_block_start, raw_block_end, text_start, text_end in opcodes:
            if raw_start < raw_block_start or raw_end > raw_block_end:
                continue

            raw_length = raw_block_end - raw_block_start
            text_length = text_end - text_start
            if tag == 'equal' or (tag == 'replace' and raw_length == text_length):
                mapped_start = text_start + raw_start - raw_block_start
                text_ranges[char_id] = (mapped_start, mapped_start + raw_end - raw_start)
            break

    return text_ranges


# Text turned by a quarter turn either way, within this tolerance in radians,
# runs vertically, so that its height shows as the width of its bbox, as in the
# axis labels of nature's figures.
QUARTER_TURN_TOLERANCE = 0.1


def is_quarter_turned(obj: PdfTextChar | PdfTextSpan) -> bool:
    """Return whether text runs vertically, turned by a quarter turn either way."""
    try:
        rotation = float(obj.get('rotation', 0) or 0) % math.pi
    except (TypeError, ValueError):
        return False
    return abs(rotation - math.pi / 2) <= QUARTER_TURN_TOLERANCE


def text_height(obj: PdfTextChar | PdfTextSpan) -> float | None:
    """Return the extent of a bbox across the direction of its text, if present."""
    x1, y1, x2, y2 = get_bbox(obj)
    if is_quarter_turned(obj):
        return None if x1 is None or x2 is None else abs(x2 - x1)
    return None if y1 is None or y2 is None else abs(y2 - y1)


def bbox_height(obj: PdfTextSpan) -> float | None:
    """Return a usable height of a span's bbox across its text, if present."""
    height = text_height(obj)
    if height is None or height <= 1.0:
        return None

    return height


def effective_span_font_size(span_dict: PdfTextSpan) -> float | None:
    """Return reported font size, falling back to bbox height for placeholder size 1.0."""
    font_dict = span_dict.get('font', {})
    size_value = font_dict.get('size')
    if size_value is None:
        return None

    try:
        size_float = float(size_value)
    except (TypeError, ValueError):
        return None

    # Some PDFs report every readable font as size 1.0; in that case box heights
    # are the better available proxy for the visually rendered size. The
    # tallest glyph box stands for the span, as the span's own box also
    # stretches over glyphs raised or lowered against the others, such as the
    # subscripts in `GaV₄S₈` in nature, while a large glyph keeps its size, as
    # the number of graf's "CHAPTER 10".
    if size_float <= 1.0:
        glyph_heights = [
            height
            for char in span_dict.get('chars', [])
            if char.get('char', '').strip()
            and (height := text_height(char)) is not None
            and height > 1.0
        ]
        return max(glyph_heights, default=None) or bbox_height(span_dict)

    return size_float


def dominant_font_size(line_dict: PdfTextLine) -> float | None:
    """Return the dominant font size for a line, weighted by text length."""
    size_weights: dict[float, int] = defaultdict(int)

    for span_dict in line_dict.get('spans', []):
        text_value = span_dict.get('text', '')
        weight = len(text_value.strip())
        if not weight:
            continue

        size_float = effective_span_font_size(span_dict)
        if size_float is None:
            continue

        size_weights[round(size_float, 1)] += weight

    if not size_weights:
        return None

    return max(size_weights.items(), key=lambda item: (item[1], item[0]))[0]


def dominant_font_name(line_dict: PdfTextLine) -> str | None:
    """Return the font name used for most of the visible text in a line."""
    name_weights: dict[str, int] = defaultdict(int)

    for span_dict in line_dict.get('spans', []):
        text_value = span_dict.get('text', '')
        weight = len(text_value.strip())
        font_name = span_dict.get('font', {}).get('name')
        if not weight or not isinstance(font_name, str) or not font_name:
            continue
        name_weights[font_name] += weight

    if not name_weights:
        return None

    return max(name_weights.items(), key=lambda item: (item[1], item[0]))[0]


def average_font_weight(line_dict: PdfTextLine) -> float | None:
    """Return the length-weighted average font weight for visible text in a line."""
    weighted_sum = 0.0
    total_weight = 0

    for span_dict in line_dict.get('spans', []):
        text_value = span_dict.get('text', '')
        weight = len(text_value.strip())
        if not weight:
            continue

        font_dict = span_dict.get('font', {})
        font_weight = font_dict.get('weight')
        if not isinstance(font_weight, int | float) or font_weight < 0:
            continue

        # Some embedded fonts report weight 0 for every span even though their
        # names retain a conventional bold marker such as `.B` or `-Bold`.
        font_name = font_dict.get('name')
        if font_weight == 0 and isinstance(font_name, str):
            if BOLD_FONT_NAME_PATTERN.search(font_name):
                font_weight = 700

        weighted_sum += float(font_weight) * weight
        total_weight += weight

    if not total_weight:
        return None

    return round(weighted_sum / total_weight, 1)


def span_font_name(span_dict: PdfTextSpan) -> str:
    """Return a span's font name, or an empty string."""
    font_name = span_dict.get('font', {}).get('name')
    return font_name if isinstance(font_name, str) else ''


def is_math_italic_span(span_dict: PdfTextSpan) -> bool:
    """Return whether a span uses a math italic font, such as CMMI10."""
    return bool(MATH_ITALIC_FONT_NAME_PATTERN.search(span_font_name(span_dict)))


def span_emphasis_kinds(span_dict: PdfTextSpan) -> tuple[Literal['bold', 'italic'], ...]:
    """Return whether a span's font is bold and whether it is italic.

    Math italic fonts are italic; other math fonts are ignored.
    """
    font_name = span_font_name(span_dict)
    math_italic = is_math_italic_span(span_dict)
    if MATH_FONT_NAME_PATTERN.search(font_name) and not math_italic:
        return ()
    kinds: list[Literal['bold', 'italic']] = []
    if BOLD_FACE_PATTERN.search(font_name):
        kinds.append('bold')
    flags = span_dict.get('font', {}).get('flags')
    if (
        math_italic
        or ITALIC_FACE_PATTERN.search(font_name)
        or isinstance(flags, int)
        and flags & ITALIC_FONT_FLAG
    ):
        kinds.append('italic')
    return tuple(kinds)


def line_emphasis_ranges(line_dict: PdfTextLine) -> tuple[InlineRange, ...]:
    """Return the bold and italic ranges of a line's text, merging those of adjacent spans.

    Only the letters of math italic fonts are styled, with combining marks
    following them.
    """
    ranges: list[InlineRange] = []
    open_runs: dict[str, InlineRange] = {}
    offset = 0
    for span_dict in line_dict.get('spans', []):
        text_value = span_dict.get('text', '')
        kinds = span_emphasis_kinds(span_dict) if text_value.strip() else ()
        pieces = (
            [(char, kinds if char.isalpha() else ()) for char in text_value]
            if kinds and is_math_italic_span(span_dict)
            else [(text_value, kinds)]
        )
        for piece, piece_kinds in pieces:
            end = offset + len(piece)
            if piece and all(category(char).startswith('M') for char in piece):
                # Combining marks belong to the styled letter they follow, as
                # the hat of a decoded wide accent in lipics-64's `P̂`.
                for kind, run in open_runs.items():
                    open_runs[kind] = InlineRange(run.start, end, run.kind)
                offset = end
                continue
            for kind in ('bold', 'italic'):
                run = open_runs.get(kind)
                if kind in piece_kinds:
                    open_runs[kind] = InlineRange(run.start if run else offset, end, kind)
                elif run is not None:
                    ranges.append(run)
                    del open_runs[kind]
            offset = end
    ranges.extend(open_runs.values())
    return tuple(sorted(ranges, key=lambda run: run.start))


def drop_dominant_emphasis(line_list: Sequence[Line]) -> None:
    """Remove bold or italic ranges, in place, where that style is the document's body style."""
    total = sum(char.isalnum() for line_obj in line_list for char in line_obj.text)
    shares: Counter[str] = Counter()
    for line_obj in line_list:
        for run in line_obj.ranges:
            if not run.is_script:
                shares[run.kind] += sum(
                    char.isalnum() for char in line_obj.text[run.start : run.end]
                )
    dominant = {kind for kind, count in shares.items() if count > total * MAX_EMPHASIS_SHARE}
    if not dominant:
        return
    for line_obj in line_list:
        line_obj.ranges = tuple(run for run in line_obj.ranges if run.kind not in dominant)


# Require at least a 15% size reduction and a center shift of 15% of the
# neighboring ordinary glyph height. Graf's raised markers shift by only 17%;
# Nature's lowered formula digits have a size ratio of about two-thirds.
SCRIPT_MAX_SIZE_RATIO = 0.85
SCRIPT_MIN_CENTER_SHIFT = 0.15
SCRIPT_PUNCTUATION = frozenset('.*∗,;:+−–-=()[]<>/†‡')


Box = tuple[float, float, float, float]

# A glyph that can be part of a script: its decoded text offsets, its pdftext
# character, its bbox, and its reported font size.
ScriptGlyph = tuple[int, int, PdfTextChar, Box, float]


def positioned_box(line_dict: PdfTextLine | PdfTextSpan) -> Box | None:
    """Return a line's or span's bbox if all of its coordinates are known."""
    x1, y1, x2, y2 = get_bbox(line_dict)
    if x1 is None or y1 is None or x2 is None or y2 is None:
        return None
    return x1, y1, x2, y2


def union_box(boxes: Sequence[Box]) -> Box:
    """Return the smallest box enclosing all given boxes."""
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def script_glyphs(line_dict: PdfTextLine) -> list[ScriptGlyph]:
    """Return the positioned glyphs of a line that could belong to a script."""
    # Entries retain decoded offsets, not raw character indices: ligatures and
    # CRLF normalization can make those differ. Detached accents are repaired
    # before this function is called.
    glyphs: list[ScriptGlyph] = []
    offset = 0
    for span in line_dict.get('spans', []):
        ranges = span_char_text_ranges(span)
        for char in span.get('chars', []):
            char_text = char.get('char', '')
            if not char_text or not all(c.isalnum() or c in SCRIPT_PUNCTUATION for c in char_text):
                continue
            if abs(float(char.get('rotation', 0))) > 0.1 or id(char) not in ranges:
                continue
            x1, y1, x2, y2 = get_bbox(char)
            if x1 is None or y1 is None or x2 is None or y2 is None or x2 <= x1 or y2 <= y1:
                continue
            size = float(char.get('font', {}).get('size', 1) or 1)
            start, end = ranges[id(char)]
            glyphs.append((offset + start, offset + end, char, (x1, y1, x2, y2), size))
        offset += len(span.get('text', ''))
    return glyphs


def glyph_size(glyph: ScriptGlyph, real_sizes: bool) -> float:
    """Return a glyph's reported font size, or its bbox height for placeholder sizes."""
    box = glyph[3]
    return glyph[4] if real_sizes else box[3] - box[1]


def script_kind(box: Box, ref_box: Box) -> Literal['sup', 'sub'] | None:
    """Return whether a small glyph is raised or lowered relative to an ordinary one."""
    height = ref_box[3] - ref_box[1]
    shift = ((box[1] + box[3]) - (ref_box[1] + ref_box[3])) / (2 * height)
    # A smaller character sitting on the ordinary baseline (e.g. small
    # caps) is not a subscript. Validate direction independently of pdftext
    # flags, which sometimes mislabel lowered C/j as superscripts.
    if (
        -0.8 <= shift <= -SCRIPT_MIN_CENTER_SHIFT
        and box[1] <= ref_box[1] + height * 0.08
        and box[3] < ref_box[3] - height * 0.15
    ):
        return 'sup'
    if (
        SCRIPT_MIN_CENTER_SHIFT <= shift <= 0.8
        and box[3] > ref_box[3] + height * 0.04
        and box[1] > ref_box[1] + height * 0.15
    ):
        return 'sub'
    return None


def script_runs(glyphs: list[ScriptGlyph], ordinary: list[ScriptGlyph]) -> list[InlineRange]:
    """Return the glyphs that are small and shifted relative to the dominant ordinary ones."""
    # Only use reported sizes when all visible alphanumerics have real sizes.
    # Nature reports size 1.0 even for differently scaled characters.
    real_sizes = all(g[4] > 1 for g in ordinary)
    sizes = Counter(round(glyph_size(g, real_sizes), 1) for g in ordinary)
    dominant = max(sizes, key=lambda size: (sizes[size], size))
    if dominant <= 0:
        return []
    references = [
        g for g in ordinary if abs(glyph_size(g, real_sizes) - dominant) <= dominant * 0.08
    ]
    runs: list[InlineRange] = []
    for glyph in glyphs:
        start, end, char, box, _ = glyph
        if glyph_size(glyph, real_sizes) > dominant * SCRIPT_MAX_SIZE_RATIO:
            continue
        reference = min(
            references,
            key=lambda g: abs((g[3][0] + g[3][2]) / 2 - (box[0] + box[2]) / 2),
        )
        ref_box = reference[3]
        horizontal_gap = max(0.0, ref_box[0] - box[2], box[0] - ref_box[2])
        if horizontal_gap > (ref_box[3] - ref_box[1]) * 6:
            continue
        kind = script_kind(box, ref_box)
        if kind is None:
            continue
        # Do not apply another script level to an already encoded script glyph.
        if any('SUPERSCRIPT' in name(c, '') or 'SUBSCRIPT' in name(c, '') for c in char['char']):
            continue
        runs.append(InlineRange(start, end, kind))
    return runs


# A fragment is a script of the rest of its visual line if its glyphs are at
# least this size relative to that line's largest ordinary glyphs, as TeX's
# 7 pt scripts of 10 pt text. Drop caps two lines tall or more are larger.
SCRIPT_FRAGMENT_MIN_SIZE_RATIO = 0.6


def plain_glyphs(line_dict: PdfTextLine) -> list[ScriptGlyph]:
    """Return the alphanumeric glyphs of a line that are no scripts within the line itself."""
    glyphs = script_glyphs(line_dict)
    ordinary = [g for g in glyphs if g[2].get('char', '').isalnum()]
    if not ordinary:
        return []
    script_starts = {run.start for run in script_runs(glyphs, ordinary)}
    return [g for g in ordinary if g[0] not in script_starts]


def fragment_references(
    ordinary: list[ScriptGlyph], others: list[ScriptGlyph]
) -> list[ScriptGlyph]:
    """Return the glyphs of the rest of a visual line that a line's glyphs are small next to.

    others holds the glyphs of the rest of the line that are no scripts there,
    so subscripts as in lipics-64's `‖m_Q − m_R‖₂ ≤ C` do not make the
    script size seem ordinary. Glyphs of a script's size next to the largest
    ones are small, as a formula fragment `(s,f)` after `C`, if the PDF reports
    real font sizes. Otherwise the
    dominant size of the rest of the line counts, whose glyphs of that size
    must outnumber those of the fragment. A large initial, such as a drop cap,
    therefore never makes the following text small. An empty list means that
    the glyphs are not small.
    """
    real_sizes = all(g[4] > 1 for g in ordinary + others)

    def size(glyph: ScriptGlyph) -> float:
        return glyph_size(glyph, real_sizes)

    largest = max(size(g) for g in others)
    # Glyph boxes, standing in for placeholder sizes, vary with letter shapes.
    if (
        real_sizes
        and largest > 0
        and all(
            largest * SCRIPT_FRAGMENT_MIN_SIZE_RATIO <= size(g) <= largest * SCRIPT_MAX_SIZE_RATIO
            for g in ordinary
        )
    ):
        return [g for g in others if abs(size(g) - largest) <= largest * 0.08]

    sizes = Counter(round(size(g), 1) for g in others)
    dominant = max(sizes, key=lambda value: (sizes[value], value))
    references = [g for g in others if abs(size(g) - dominant) <= dominant * 0.08]
    if len(references) > len(ordinary) and all(
        size(g) <= dominant * SCRIPT_MAX_SIZE_RATIO for g in ordinary
    ):
        return references
    return []


def line_script_ranges(
    line_dict: PdfTextLine,
    neighbors: Sequence[PdfTextLine] = (),
    same_line: Sequence[PdfTextLine] = (),
) -> tuple[InlineRange, ...]:
    """Recognize small shifted glyphs, including those inside ordinary spans.

    pdftext sometimes puts scripts into line records of their own. The other
    pieces of the same visual line, given as same_line, then provide the
    ordinary glyphs instead.
    """
    glyphs = script_glyphs(line_dict)
    ordinary = [g for g in glyphs if g[2].get('char', '').isalnum()]
    others = [g for other in same_line for g in plain_glyphs(other)]
    runs = {run.start: run for run in script_runs(glyphs, ordinary)} if ordinary else {}
    line_box = positioned_box(line_dict)
    references = fragment_references(ordinary, others) if others else []
    if references:
        # Judge the fragment against the surrounding text. Scripts of its own,
        # such as the subscript in a superscript `2−c₁`, keep their own level
        # unless they are scripts of the surrounding text too.
        runs.update((run.start, run) for run in script_runs(glyphs, references))
        # A fraction is stacked relative to the complete visual line.
        boxes = [positioned_box(own_line) for own_line in (line_dict, *same_line)]
        known_boxes = [box for box in boxes if box is not None]
        line_box = union_box(known_boxes) if len(known_boxes) == len(boxes) else None
    # A small numerator can look like an inline superscript. Reject only the
    # touching script group when another extraction line is stacked immediately
    # above/below it, preserving unrelated scripts elsewhere on the same line.
    groups: list[list[InlineRange]] = []
    for run in sorted(runs.values(), key=lambda run: run.start):
        if not groups or groups[-1][-1].end != run.start or groups[-1][-1].kind != run.kind:
            groups.append([])
        groups[-1].append(run)
    kept: list[InlineRange] = []
    for group in groups:
        script_box = union_box([g[3] for g in glyphs if group[0].start <= g[0] < group[-1].end])
        if not has_stacked_text(line_box, [line_dict, *same_line], neighbors, script_box, group[0]):
            kept.extend(group)
    return tuple(kept)


def has_stacked_text(
    line_box: Box | None,
    own_lines: Sequence[PdfTextLine],
    neighbors: Sequence[PdfTextLine],
    script_box: Box,
    run: InlineRange,
) -> bool:
    """Avoid interpreting the numerator of a vertically stacked fraction as a script.

    line_box covers the visual line of the script, which consists of own_lines.
    """
    if line_box is None:
        return False
    _, y1, _, y2 = line_box
    for neighbor in neighbors:
        if any(neighbor is own_line for own_line in own_lines):
            continue
        nx1, ny1, nx2, ny2 = get_bbox(neighbor)
        if nx1 is None or ny1 is None or nx2 is None or ny2 is None:
            continue
        if min(script_box[2], nx2) <= max(script_box[0], nx1):
            continue
        gap = ny1 - script_box[3] if run.kind == 'sup' else script_box[1] - ny2
        if not 0 <= gap <= (y2 - y1) * 0.3:
            continue
        # Numerator/denominator centers are much closer than consecutive prose
        # lines. Ignore nearly identical baselines, which can be split blocks.
        distance = abs((y1 + y2 - ny1 - ny2) / 2)
        if min(y2 - y1, ny2 - ny1) * 0.1 < distance < max(y2 - y1, ny2 - ny1) * 0.6:
            return True
    return False


# The denominator of an inline fraction is centered under the numerator, while
# a subscript below a superscript of another width is left-aligned with it, as
# in lipics-64's `R` with `i` above `∗`. Fractions in lipics-51 and lipics-64
# are centered within 0.03 em; the stacked scripts there are off by 0.055 em
# or more. The tolerance is relative to the size of the surrounding text.
STACKED_ALIGNMENT_TOLERANCE_EM = 0.05


def trailing_small_glyph_box(line_dict: PdfTextLine, font_size: float) -> Box | None:
    """Return the box of the visible glyphs ending a line that are small for font_size."""
    boxes: list[Box] = []
    for span in reversed(line_dict.get('spans', [])):
        for char in reversed(span.get('chars', [])):
            if not char.get('char', '').strip():
                continue
            x1, y1, x2, y2 = get_bbox(char)
            if x1 is None or y1 is None or x2 is None or y2 is None:
                return None
            size = float(char.get('font', {}).get('size', 1) or 1)
            if size <= 1:
                size = y2 - y1
            if size > font_size * SCRIPT_MAX_SIZE_RATIO:
                return union_box(boxes) if boxes else None
            boxes.append((x1, y1, x2, y2))
    return union_box(boxes) if boxes else None


def stacked_limit_count(page_lines: Sequence[Line], index: int) -> int:
    """Return the number of line records after index that form limits below its last word.

    Limits, as under `argmax` in lipics-64, are records of small text below
    the middle of the line, centered as a whole below its last word, which
    has letters in it. The record after them continues the line after the
    wider of the word and the limits.
    """
    operator = page_lines[index]
    if (
        not operator.words
        or operator.font_size is None
        or operator.x2 is None
        or operator.y1 is None
        or operator.y2 is None
    ):
        return 0
    word = operator.words[-1]
    if not any(char.isalpha() for char in operator.text[word.start : word.end]):
        return 0
    font_size = operator.font_size
    middle = (operator.y1 + operator.y2) / 2
    boxes: list[Box] = []
    end = index + 1
    while end < len(page_lines):
        piece = page_lines[end]
        if (
            piece.page_no != operator.page_no
            or piece.fraction_denominator
            or piece.font_size is None
            or piece.font_size > font_size * SCRIPT_MAX_SIZE_RATIO
            or piece.x1 is None
            or piece.x2 is None
            or piece.y1 is None
            or piece.y2 is None
            or piece.y1 < middle
        ):
            break
        boxes.append((piece.x1, piece.y1, piece.x2, piece.y2))
        end += 1
    if not boxes or end >= len(page_lines):
        return 0
    following = page_lines[end]
    limits = union_box(boxes)
    tolerance = font_size * STACKED_ALIGNMENT_TOLERANCE_EM
    if (
        abs((limits[0] + limits[2]) - (word.x1 + word.x2)) / 2 > tolerance
        or following.x1 is None
        or not same_physical_line(operator, following)
        or not 0 <= following.x1 - max(operator.x2, limits[2]) < font_size * RUNNING_TEXT_MAX_GAP_EM
    ):
        return 0
    return len(boxes)


def without_trailing_scripts(line_obj: Line) -> tuple[InlineRange, ...]:
    """Return a line's ranges without the scripts that end it, as a fraction's numerator."""
    end = len(line_obj.text)
    trailing: set[InlineRange] = set()
    for run in sorted((run for run in line_obj.ranges if run.is_script), key=lambda run: -run.end):
        if run.end != end:
            break
        trailing.add(run)
        end = run.start
    return tuple(run for run in line_obj.ranges if run not in trailing)


def is_fraction_denominator(
    numerator: Line, numerator_dict: PdfTextLine, denominator: Line, following: Line
) -> bool:
    """Return whether a line is centered below small text ending the preceding line.

    The text following it must continue the line of the numerator after the
    wider of numerator and denominator, so text on the next line never counts
    as a denominator.
    """
    if (
        numerator.y1 is None
        or numerator.y2 is None
        or denominator.x1 is None
        or denominator.x2 is None
        or denominator.y1 is None
        or denominator.y2 is None
        or following.y2 is None
        or numerator.x2 is None
        or following.x1 is None
        or same_physical_line(numerator, denominator)
        or not same_physical_line(numerator, following)
    ):
        return False
    font_size = max(numerator.font_size or 0.0, following.font_size or 0.0)
    fraction_end = max(numerator.x2, denominator.x2)
    if following.x1 - fraction_end >= max(font_size, 1.0) * RUNNING_TEXT_MAX_GAP_EM:
        return False
    if (
        font_size <= 0
        or (denominator.font_size or font_size) > font_size * SCRIPT_MAX_SIZE_RATIO
        or not numerator.y1 < denominator.y1 < max(numerator.y2, following.y2)
    ):
        return False
    box = trailing_small_glyph_box(numerator_dict, font_size)
    if box is None or box[3] > denominator.y2:
        return False
    tolerance = font_size * STACKED_ALIGNMENT_TOLERANCE_EM
    centered = abs((box[0] + box[2]) - (denominator.x1 + denominator.x2)) / 2 <= tolerance
    left_aligned_scripts = (
        abs(box[0] - denominator.x1) <= tolerance
        and abs((box[2] - box[0]) - (denominator.x2 - denominator.x1)) > tolerance
    )
    return centered and not left_aligned_scripts


def glyph_font_size(char: PdfTextChar) -> float | None:
    """Return a glyph's font size, or its bbox height for placeholder sizes."""
    size = float(char.get('font', {}).get('size', 1) or 1)
    if size > 1:
        return size
    return text_height(char)


def second_word_x1(line_dict: PdfTextLine) -> float | None:
    """Return where the text following a line's first word and its whitespace starts."""
    seen_word = False
    seen_space = False
    for span in line_dict.get('spans', []):
        for char in span.get('chars', []):
            if not char.get('char', '').strip():
                seen_space = seen_word
            elif seen_space:
                return get_bbox(char)[0]
            else:
                seen_word = True
    return None


def line_words(line_dict: PdfTextLine, lead: int) -> tuple[Word, ...]:
    """Return the words of a line's text with their horizontal extents.

    Offsets refer to the line text without the lead leading whitespace
    characters. Words without any positioned characters are omitted.
    """
    extents: dict[int, tuple[float, float]] = {}
    text_parts: list[str] = []
    offset = -lead
    for span in line_dict.get('spans', []):
        ranges = span_char_text_ranges(span)
        for char in span.get('chars', []):
            x1, _, x2, _ = get_bbox(char)
            if x1 is None or x2 is None or id(char) not in ranges:
                continue
            start, end = ranges[id(char)]
            for position in range(offset + start, offset + end):
                extents[position] = (min(x1, x2), max(x1, x2))
        text_value = span.get('text', '')
        text_parts.append(text_value)
        offset += len(text_value)
    text = ''.join(text_parts)[lead:]
    words: list[Word] = []
    for match in re.finditer(r'\S+', text):
        known = [extents[position] for position in range(*match.span()) if position in extents]
        if known:
            words.append(
                Word(
                    match.start(),
                    match.end(),
                    round(min(x1 for x1, _ in known), 1),
                    round(max(x2 for _, x2 in known), 1),
                )
            )
    return tuple(words)


def visible_chars(line_dict: PdfTextLine) -> list[PdfTextChar]:
    """Return the characters of a line other than whitespace."""
    return [
        char
        for span in line_dict.get('spans', [])
        for char in span.get('chars', [])
        if char.get('char', '').strip()
    ]


def positioned_char_box(char: PdfTextChar) -> Box | None:
    """Return a character's bbox if all of its coordinates are known."""
    x1, y1, x2, y2 = get_bbox(char)
    if x1 is None or y1 is None or x2 is None or y2 is None or y2 <= y1:
        return None
    return x1, y1, x2, y2


def has_edge_space(raw_text: str, at_end: bool) -> bool:
    """Return whether raw line text starts or ends with whitespace other than a line end."""
    text = raw_text.rstrip('\r\n') if at_end else raw_text.lstrip('\r\n')
    edge = text[-1:] if at_end else text[:1]
    return edge.isspace()


def iter_lines(page_list: Sequence[Page]) -> list[Line]:
    """Flatten pdftext dictionary output into a list of Line records."""
    line_list: list[Line] = []

    for page_index, page_dict in enumerate(page_list, start=1):
        previous_x1: float | None = None
        previous_y1: float | None = None
        line_no_on_page = 0
        page_lines: list[tuple[Line, PdfTextLine, list[PdfTextLine], str]] = []

        for block_index, block_dict in enumerate(page_dict.get('blocks', []), start=1):
            for line_dict in block_dict.get('lines', []):
                line_no_on_page += 1

                raw_text = ''.join(
                    span_dict.get('text', '') for span_dict in line_dict.get('spans', [])
                )
                text_value = raw_text.strip()
                x1, y1, x2, y2 = get_bbox(line_dict)

                rel_x = None
                rel_y = None
                if previous_x1 is not None and x1 is not None:
                    rel_x = round(x1 - previous_x1, 1)
                if previous_y1 is not None and y1 is not None:
                    rel_y = round(y1 - previous_y1, 1)

                line_obj = Line(
                    text=text_value,
                    page_no=page_index,
                    block_no=block_index,
                    line_no_on_page=line_no_on_page,
                    font_size=dominant_font_size(line_dict),
                    x1=round_or_none(x1),
                    y1=round_or_none(y1),
                    x2=round_or_none(x2),
                    y2=round_or_none(y2),
                    rel_x=rel_x,
                    rel_y=rel_y,
                    avg_weight=average_font_weight(line_dict),
                    font_name=dominant_font_name(line_dict),
                    space_before=bool(text_value) and has_edge_space(raw_text, at_end=False),
                    space_after=bool(text_value) and has_edge_space(raw_text, at_end=True),
                    second_word_x1=round_or_none(second_word_x1(line_dict)),
                    words=line_words(line_dict, len(raw_text) - len(raw_text.lstrip())),
                )
                page_lines.append((line_obj, line_dict, block_dict.get('lines', []), raw_text))

                previous_x1 = x1
                previous_y1 = y1

        # pdftext emits the pieces of a split line of running text
        # consecutively, though not necessarily within one block, nor always
        # from left to right, as in a formula in lipics-64. With real font
        # sizes, scripts are judged against all other pieces of the line;
        # glyph boxes, standing in for placeholder sizes, are too unreliable
        # beyond the neighboring pieces.
        visual_lines = [0]
        for (left, *_), (right, *_) in pairwise(page_lines):
            joined = same_running_text_line(left, right) or same_running_text_line(right, left)
            visual_lines.append(visual_lines[-1] + (not joined))
        real_sizes = all(
            float(char.get('font', {}).get('size', 1) or 1) > 1
            for _, line_dict, _, _ in page_lines
            for char in visible_chars(line_dict)
        )
        for index, (line_obj, line_dict, block_lines, raw_text) in enumerate(page_lines):
            same_line = [
                other_dict
                for other_index, (_, other_dict, _, _) in enumerate(page_lines)
                if visual_lines[other_index] == visual_lines[index]
                and (other_index != index if real_sizes else abs(other_index - index) == 1)
            ]
            scripts = line_script_ranges(line_dict, block_lines, same_line)
            annotated = AnnotatedText(raw_text, scripts + line_emphasis_ranges(line_dict)).slice(
                len(raw_text) - len(raw_text.lstrip()), len(raw_text.rstrip())
            )
            line_obj.ranges = annotated.ranges
            line_obj.fraction_denominator = 0 < index < len(
                page_lines
            ) - 1 and is_fraction_denominator(
                page_lines[index - 1][0],
                page_lines[index - 1][1],
                line_obj,
                page_lines[index + 1][0],
            )
            if line_obj.fraction_denominator:
                # Numerator and denominator are no scripts of the line around
                # them; the denominator's own scripts are judged within it.
                numerator = page_lines[index - 1][0]
                numerator.ranges = without_trailing_scripts(numerator)
                own = AnnotatedText(
                    raw_text, line_script_ranges(line_dict) + line_emphasis_ranges(line_dict)
                ).slice(len(raw_text) - len(raw_text.lstrip()), len(raw_text.rstrip()))
                line_obj.ranges = own.ranges
            line_list.append(line_obj)

        page_line_objs = [line_obj for line_obj, _, _, _ in page_lines]
        for index, line_obj in enumerate(page_line_objs):
            if line_obj.stacked_limit or line_obj.fraction_denominator:
                continue
            for limit in page_line_objs[
                index + 1 : index + 1 + stacked_limit_count(page_line_objs, index)
            ]:
                limit.stacked_limit = True

    return line_list
