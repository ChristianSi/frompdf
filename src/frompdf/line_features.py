import re

from frompdf.models import Line

# Ignore small size changes caused by rounding or mixed inline typography.
FONT_SIZE_BREAK_RATIO = 1.1
FONT_SIZE_BREAK_POINTS = 0.75
FONT_WEIGHT_BREAK = 200.0

# Numbered headings and list items start a new block even in display type.
NUMBERED_OR_BULLETED_START_PATTERN = re.compile(r'^(?:\d+(?:\.\d+)*\.?|[IVXLC]+\.|[•◦▪●■])\s')
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


def compatible_size_and_weight(left: Line, right: Line) -> bool:
    """Return whether two lines have compatible font sizes and weights."""
    if not close_font_size(left.font_size, right.font_size):
        return False
    return (
        left.avg_weight is None
        or right.avg_weight is None
        or abs(left.avg_weight - right.avg_weight) < FONT_WEIGHT_BREAK
    )


def compatible_style(left: Line, right: Line) -> bool:
    """Return whether two lines have compatible dominant typography."""
    if not compatible_size_and_weight(left, right):
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


def has_alphanumeric(text: str) -> bool:
    """Return whether text contains letters or digits, unlike ornaments and rules."""
    return any(character.isalnum() for character in text)


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
    tolerance = font_size * 0.35
    # Tops differ at tall delimiters, which are centered on the text instead.
    same_band = abs(right.y1 - left.y1) <= tolerance or (
        left.y2 is not None
        and right.y2 is not None
        and abs((right.y1 + right.y2) - (left.y1 + left.y2)) / 2 <= tolerance
    )
    return same_band and right.x1 >= left.x2 - font_size * 0.25


# Pieces of one visual line further apart than this, relative to the larger
# size, are not running text, such as the cells of a table row in folie or a
# logo beside a title in intertrans.
RUNNING_TEXT_MAX_GAP_EM = 1.0


def same_running_text_line(left: Line, right: Line) -> bool:
    """Return whether adjacent fragments of one visual line belong to the same running text."""
    if not same_physical_line(left, right):
        return False
    assert left.x2 is not None
    assert right.x1 is not None
    font_size = max(left.font_size or 0.0, right.font_size or 0.0, 1.0)
    return right.x1 - left.x2 < font_size * RUNNING_TEXT_MAX_GAP_EM


# A short piece of a visual line in script-sized type, such as a formula
# fragment with raised and lowered parts, touching its neighbor within this distance,
# relative to the larger size, continues the line, as in lipics-64's
# Definition 2.4. Scripts are at most the larger ratio of their base text's
# size, and at least about half of it, as TeX's second-level scripts. Much
# smaller ratios rather stem from rotated figure labels, as in nature.
SCRIPT_FRAGMENT_MAX_GAP_EM = 0.1
SCRIPT_FRAGMENT_MIN_SIZE_RATIO = 0.4
SCRIPT_FRAGMENT_MAX_SIZE_RATIO = 0.85


def is_script_sized(piece: Line, reference: Line) -> bool:
    """Return whether a piece is set in script-sized type relative to a reference."""
    return (
        piece.font_size is not None
        and reference.font_size is not None
        and reference.font_size * SCRIPT_FRAGMENT_MIN_SIZE_RATIO
        <= piece.font_size
        <= reference.font_size * SCRIPT_FRAGMENT_MAX_SIZE_RATIO
    )


def touches_script_fragment(left: Line, right: Line) -> bool:
    """Return whether adjacent pieces of one visual line touch, one a short script-sized one.

    Script-sized prose, such as a label in another face, is no script.
    """
    if not same_physical_line(left, right) or not any(
        is_script_sized(piece, other) and not is_prose_line(piece)
        for piece, other in ((left, right), (right, left))
    ):
        return False
    assert left.x2 is not None
    assert right.x1 is not None
    font_size = max(left.font_size or 0.0, right.font_size or 0.0, 1.0)
    return abs(right.x1 - left.x2) <= font_size * SCRIPT_FRAGMENT_MAX_GAP_EM


def ends_sentence(text: str) -> bool:
    """Return whether text ends in language-independent sentence punctuation."""
    return bool(SENTENCE_END_PATTERN.search(text.rstrip()))


def ends_word_break_hyphen(text: str) -> bool:
    """Return whether a line ends in a likely word-breaking hyphen."""
    return bool(WORD_BREAK_HYPHEN_PATTERN.search(text.rstrip()))


def mixes_italics(line_obj: Line) -> bool:
    """Return whether a line has both italic and upright letters."""
    italic = {
        index
        for run in line_obj.ranges
        if run.kind == 'italic'
        for index in range(run.start, run.end)
    }
    return bool(italic) and any(
        character.isalpha() and index not in italic for index, character in enumerate(line_obj.text)
    )


def differs_only_by_italics(left: Line, right: Line) -> bool:
    """Return whether a font difference may just reflect italics within running text.

    A line's font is its dominant one, so a line that is mostly italic differs
    from an upright neighbor, though its upright text continues in the same font.
    Bold is left out, as it often marks a run-in heading.
    """
    return (
        compatible_size_and_weight(left, right)
        and (mixes_italics(left) or mixes_italics(right))
        and not any(run.kind == 'bold' for run in (*left.ranges, *right.ranges))
    )
