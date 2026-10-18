import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from difflib import SequenceMatcher
from typing import Literal, cast
from unicodedata import category, name, normalize

from pdftext.schema import (
    Bbox,
    Page,
)
from pdftext.schema import (
    Char as PdfTextChar,
)
from pdftext.schema import (
    Line as PdfTextLine,
)
from pdftext.schema import (
    Span as PdfTextSpan,
)

from frompdf.models import InlineRange, Line
from frompdf.scripts import AnnotatedText
from frompdf.segmentation import same_physical_line, same_running_text_line

SPACING_TO_COMBINING = {
    '¨': '\u0308',
    '´': '\u0301',
    '`': '\u0300',
    '^': '\u0302',
    '~': '\u0303',
}

# Icon fonts map pictograms, such as e-mail, ORCID, or home-page symbols next
# to author names, to arbitrary letters and punctuation, so their text is noise.
ICON_FONT_NAME_PATTERN = re.compile(
    r'font[ _-]?awesome|academicons|material[ _-]?(?:icons|symbols)|glyphicons|ionicons',
    flags=re.IGNORECASE,
)

# TeX math extension fonts (Computer Modern and Latin Modern) hold large
# delimiters, operators, and accents. Without a Unicode mapping in the PDF,
# pdftext reports their font codes in TeX's OMX encoding instead, such as
# `\x00` and `\x01` for the parentheses in lipics-51's `Ω(n log …)`.
MATH_EXTENSION_FONT_NAME_PATTERN = re.compile(r'\b(?:cmex|lmex)\d|LMMathExtension', re.IGNORECASE)

# Characters a Unicode mapping could produce for these glyphs, which are
# therefore no evidence of a font code.
AMBIGUOUS_MATH_EXTENSION_CHARS = frozenset(' ()[]{}|/\\^~<>')

# OMX codes of glyphs standing for one character, from the glyph names in
# cmex10.afm. Each delimiter comes in several sizes.
MATH_EXTENSION_CHARS: dict[int, str] = {
    **dict(enumerate('()[]⌊⌋⌈⌉{}⟨⟩', start=0)),
    14: '/',
    15: '\\',
    **dict(enumerate('()()[]⌊⌋⌈⌉{}⟨⟩/\\', start=16)),
    **dict(enumerate('()[]⌊⌋⌈⌉{}⟨⟩/\\/\\', start=32)),
    68: '⟨',
    69: '⟩',
    **dict(enumerate('⨆⨆∮∮⨀⨀⨁⨁⨂⨂∑∏∫⋃⋂⨄⋀⋁∑∏∫⋃⋂⨄⋀⋁∐∐', start=70)),
    **dict(enumerate('[]⌊⌋⌈⌉{}', start=104)),
    **dict.fromkeys(range(112, 116), '√'),
}

# OMX codes of wide hats and tildes, with combining and spacing forms.
MATH_EXTENSION_ACCENTS: dict[int, tuple[str, str]] = {
    **dict.fromkeys(range(98, 101), ('̂', 'ˆ')),
    **dict.fromkeys(range(101, 104), ('̃', '˜')),
}

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


def composed_diacritic(base_text: str, spacing_accent: str) -> str | None:
    """Return a precomposed Latin letter for a supported base/accent pair."""
    combining_accent = SPACING_TO_COMBINING.get(spacing_accent)
    if len(base_text) != 1 or combining_accent is None:
        return None
    if not base_text.isascii() or category(base_text) not in {'Ll', 'Lu'}:
        return None

    composed = normalize('NFC', base_text + combining_accent)
    if len(composed) != 1 or composed == base_text:
        return None
    return composed


def diacritic_geometry_score(
    accent_char: PdfTextChar, base_char: PdfTextChar
) -> tuple[float, float, float] | None:
    """Score a strongly overlapping accent/base pair, or reject its geometry."""
    if abs(float(accent_char.get('rotation', 0)) - float(base_char.get('rotation', 0))) > 0.1:
        return None

    accent_x1, accent_y1, accent_x2, accent_y2 = get_bbox(accent_char)
    base_x1, base_y1, base_x2, base_y2 = get_bbox(base_char)
    if None in {
        accent_x1,
        accent_y1,
        accent_x2,
        accent_y2,
        base_x1,
        base_y1,
        base_x2,
        base_y2,
    }:
        return None

    # The None check above narrows these values for runtime, but not for basedpyright.
    assert accent_x1 is not None
    assert accent_y1 is not None
    assert accent_x2 is not None
    assert accent_y2 is not None
    assert base_x1 is not None
    assert base_y1 is not None
    assert base_x2 is not None
    assert base_y2 is not None

    accent_width = accent_x2 - accent_x1
    accent_height = accent_y2 - accent_y1
    base_width = base_x2 - base_x1
    base_height = base_y2 - base_y1
    if min(accent_width, accent_height, base_width, base_height) <= 0:
        return None

    horizontal_overlap = max(0.0, min(accent_x2, base_x2) - max(accent_x1, base_x1))
    overlap_ratio = horizontal_overlap / min(accent_width, base_width)
    horizontal_distance = abs((accent_x1 + accent_x2) / 2 - (base_x1 + base_x2) / 2)
    horizontal_ratio = horizontal_distance / base_width

    accent_center_y = (accent_y1 + accent_y2) / 2
    base_center_y = (base_y1 + base_y2) / 2
    vertical_offset = accent_center_y - base_center_y
    vertical_ratio = abs(vertical_offset) / base_height

    # pdftext loose glyph boxes often give a detached TeX accent almost the same
    # vertical extent as its base. Horizontal coincidence is therefore the strongest
    # signal; the vertical bounds allow both loose boxes and a smaller accent above.
    if (
        overlap_ratio < 0.8
        or horizontal_ratio > 0.25
        or vertical_offset < -base_height
        or vertical_offset > base_height * 0.25
    ):
        return None

    return horizontal_ratio, vertical_ratio, -overlap_ratio


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


def spacing_artifact_touches_accent(whitespace_char: PdfTextChar, accent_char: PdfTextChar) -> bool:
    """Return whether a zero-width space was inserted beside an out-of-order accent."""
    whitespace_text = whitespace_char.get('char', '')
    if not whitespace_text.isspace() or whitespace_text in {'\r', '\n'}:
        return False

    whitespace_x1, whitespace_y1, whitespace_x2, whitespace_y2 = get_bbox(whitespace_char)
    accent_x1, accent_y1, accent_x2, accent_y2 = get_bbox(accent_char)
    if None in {
        whitespace_x1,
        whitespace_y1,
        whitespace_x2,
        whitespace_y2,
        accent_x1,
        accent_y1,
        accent_x2,
        accent_y2,
    }:
        return False

    assert whitespace_x1 is not None
    assert whitespace_y1 is not None
    assert whitespace_x2 is not None
    assert whitespace_y2 is not None
    assert accent_x1 is not None
    assert accent_y1 is not None
    assert accent_x2 is not None
    assert accent_y2 is not None

    accent_width = accent_x2 - accent_x1
    accent_height = accent_y2 - accent_y1
    if accent_width <= 0 or accent_height <= 0 or abs(whitespace_x2 - whitespace_x1) > 0.1:
        return False

    edge_distance = min(abs(whitespace_x1 - accent_x1), abs(whitespace_x1 - accent_x2))
    horizontal_tolerance = max(0.5, accent_width * 0.2)
    vertical_tolerance = accent_height * 0.5
    return (
        edge_distance <= horizontal_tolerance
        and accent_y1 - vertical_tolerance <= whitespace_y1 <= accent_y2 + vertical_tolerance
    )


def normalize_detached_diacritics(page_list: Sequence[Page]) -> None:
    """Merge geometrically attached spacing accents into base characters in-place."""
    for page_dict in page_list:
        for block_dict in page_dict.get('blocks', []):
            for line_dict in block_dict.get('lines', []):
                positioned_chars: list[tuple[PdfTextSpan, PdfTextChar]] = []
                for span_dict in line_dict.get('spans', []):
                    positioned_chars.extend(
                        (span_dict, char_dict) for char_dict in span_dict.get('chars', [])
                    )

                accent_chars = [
                    (span_dict, char_dict)
                    for span_dict, char_dict in positioned_chars
                    if char_dict.get('char') in SPACING_TO_COMBINING
                ]
                if not accent_chars:
                    continue

                used_base_ids: set[int] = set()
                span_by_id = {id(span_dict): span_dict for span_dict in line_dict.get('spans', [])}
                text_ranges_by_span_id = {
                    span_id: span_char_text_ranges(span_dict)
                    for span_id, span_dict in span_by_id.items()
                }
                pending_edits: dict[int, dict[int, tuple[PdfTextChar, str]]] = defaultdict(dict)

                for accent_span, accent_char in accent_chars:
                    spacing_accent = accent_char.get('char', '')
                    if spacing_accent not in SPACING_TO_COMBINING:
                        continue

                    candidates: list[
                        tuple[tuple[float, float, float], PdfTextSpan, PdfTextChar, str]
                    ] = []
                    for base_span, base_char in positioned_chars:
                        if base_char is accent_char or id(base_char) in used_base_ids:
                            continue

                        composed = composed_diacritic(base_char.get('char', ''), spacing_accent)
                        if composed is None:
                            continue

                        score = diacritic_geometry_score(accent_char, base_char)
                        if score is not None:
                            candidates.append((score, base_span, base_char, composed))

                    if not candidates:
                        continue

                    _, base_span, base_char, composed = min(candidates, key=lambda item: item[0])
                    accent_span_id = id(accent_span)
                    base_span_id = id(base_span)
                    if (
                        id(accent_char) not in text_ranges_by_span_id[accent_span_id]
                        or id(base_char) not in text_ranges_by_span_id[base_span_id]
                    ):
                        continue

                    pending_edits[base_span_id][id(base_char)] = (base_char, composed)
                    pending_edits[accent_span_id][id(accent_char)] = (accent_char, '')
                    used_base_ids.add(id(base_char))

                    for whitespace_span, whitespace_char in positioned_chars:
                        whitespace_span_id = id(whitespace_span)
                        if (
                            spacing_artifact_touches_accent(whitespace_char, accent_char)
                            and id(whitespace_char) in text_ranges_by_span_id[whitespace_span_id]
                        ):
                            pending_edits[whitespace_span_id][id(whitespace_char)] = (
                                whitespace_char,
                                '',
                            )

                for span_id, edits in pending_edits.items():
                    span_dict = span_by_id[span_id]
                    text_edits = [
                        (*text_ranges_by_span_id[span_id][char_id], replacement)
                        for char_id, (_, replacement) in edits.items()
                    ]
                    text_value = span_dict.get('text', '')
                    for start, end, replacement in sorted(text_edits, reverse=True):
                        text_value = text_value[:start] + replacement + text_value[end:]
                    span_dict['text'] = text_value

                    for char_dict, replacement in edits.values():
                        char_dict['char'] = replacement


def is_icon_span(span_dict: PdfTextSpan) -> bool:
    """Return whether a span uses an icon font."""
    font_name = span_dict.get('font', {}).get('name')
    return isinstance(font_name, str) and bool(ICON_FONT_NAME_PATTERN.search(font_name))


def remove_icon_glyphs(page_list: Sequence[Page]) -> None:
    """Remove icon-font spans in place, with the space separating each from its text."""
    for page_dict in page_list:
        for block_dict in page_dict.get('blocks', []):
            for line_dict in block_dict.get('lines', []):
                spans = line_dict.get('spans', [])
                if not any(is_icon_span(span_dict) for span_dict in spans):
                    continue
                kept: list[PdfTextSpan] = []
                for index, span_dict in enumerate(spans):
                    if not is_icon_span(span_dict):
                        kept.append(span_dict)
                        continue
                    following = spans[index + 1] if index + 1 < len(spans) else None
                    if kept and not kept[-1].get('text', '').strip():
                        kept.pop()
                    elif following is not None and not following.get('text', '').strip():
                        # Only a space may separate the icon from following text.
                        following['text'] = following.get('text', '').replace(' ', '')
                line_dict['spans'] = kept


def is_math_extension_span(span_dict: PdfTextSpan) -> bool:
    """Return whether a span uses a TeX math extension font."""
    font_name = span_dict.get('font', {}).get('name')
    return isinstance(font_name, str) and bool(MATH_EXTENSION_FONT_NAME_PATTERN.search(font_name))


def is_decodable_math_extension_span(span_dict: PdfTextSpan) -> bool:
    """Return whether a span uses a TeX math extension font and its text is made of its chars."""
    visible_chars = (
        char.get('char', '')
        for char in span_dict.get('chars', [])
        if not is_omitted_control(char.get('char', ''))
    )
    return is_math_extension_span(span_dict) and span_dict.get('text', '') == ''.join(visible_chars)


def raw_math_extension_code(char_text: str) -> int | None:
    """Return the font code that pdftext reported in place of a math extension glyph.

    Without a Unicode mapping, pdftext reports the font code as a character.
    Characters that a mapping could also produce are ambiguous and skipped.
    """
    if len(char_text) != 1 or ord(char_text) >= 128 or char_text in AMBIGUOUS_MATH_EXTENSION_CHARS:
        return None
    return ord(char_text)


def is_omitted_control(char_text: str) -> bool:
    """Return whether pdftext omits a character from span text as a control character."""
    return len(char_text) == 1 and char_text < ' ' and char_text not in '\r\n'


def overlaps_horizontally(accent_char: PdfTextChar, base_char: PdfTextChar) -> bool:
    """Return whether an accent spans at least half of the narrower of it and its base."""
    accent_x1, _, accent_x2, _ = get_bbox(accent_char)
    base_x1, _, base_x2, _ = get_bbox(base_char)
    if accent_x1 is None or accent_x2 is None or base_x1 is None or base_x2 is None:
        return False
    overlap = min(accent_x2, base_x2) - max(accent_x1, base_x1)
    return overlap > 0 and overlap >= min(accent_x2 - accent_x1, base_x2 - base_x1) * 0.5


def decode_math_extension_glyphs(page_list: Sequence[Page]) -> None:
    """Replace font codes of TeX math extension glyphs with the characters they show, in place.

    Delimiters, big operators, and radicals become their Unicode characters.
    Wide accents combine with the preceding glyph if they lie above it.
    Pieces of extensible delimiters and arrows are left unchanged.
    """
    for page_dict in page_list:
        for block_dict in page_dict.get('blocks', []):
            for line_dict in block_dict.get('lines', []):
                previous_char: PdfTextChar | None = None
                for span_dict in line_dict.get('spans', []):
                    chars = span_dict.get('chars', [])
                    if not is_decodable_math_extension_span(span_dict):
                        previous_char = next(
                            (c for c in reversed(chars) if c.get('char', '').strip()),
                            previous_char,
                        )
                        continue
                    texts: list[str] = []
                    for char in chars:
                        char_text = char.get('char', '')
                        code = raw_math_extension_code(char_text)
                        if code in MATH_EXTENSION_CHARS:
                            char_text = MATH_EXTENSION_CHARS[code]
                        elif code in MATH_EXTENSION_ACCENTS:
                            combining, spacing = MATH_EXTENSION_ACCENTS[code]
                            attached = previous_char is not None and overlaps_horizontally(
                                char, previous_char
                            )
                            char_text = combining if attached else spacing
                        elif is_omitted_control(char_text):
                            continue
                        char['char'] = char_text
                        texts.append(char_text)
                        if char_text.strip():
                            previous_char = char
                    span_dict['text'] = ''.join(texts)


def bbox_height(obj: PdfTextLine | PdfTextSpan) -> float | None:
    """Return a usable bbox height, if present."""
    _, y1, _, y2 = get_bbox(obj)
    if y1 is None or y2 is None:
        return None

    height = abs(y2 - y1)
    if height <= 1.0:
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

    # Some PDFs report every readable font as size 1.0; in that case bbox height
    # is the better available proxy for the visually rendered size.
    if size_float <= 1.0:
        return bbox_height(span_dict)

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

    Only the letters of math italic fonts are styled.
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


def is_small_fragment(ordinary: list[ScriptGlyph], others: list[ScriptGlyph]) -> bool:
    """Return whether a line's ordinary glyphs are all small next to the rest of its visual line.

    Sizes are compared with the dominant size of the rest of the visual line,
    whose glyphs of that size must outnumber those of the fragment. A large
    initial, such as a drop cap, therefore never makes the following text
    small, nor do a few tall delimiters in a formula. Scripts of the rest of
    the line, as in lipics-64's `xᵢ − xⱼ`, do not count against its size.
    """
    real_sizes = all(g[4] > 1 for g in ordinary + others)
    sizes = Counter(round(glyph_size(g, real_sizes), 1) for g in others)
    dominant = max(sizes, key=lambda size: (sizes[size], size))
    references = [g for g in others if abs(glyph_size(g, real_sizes) - dominant) <= dominant * 0.08]
    return len(references) > len(ordinary) and all(
        glyph_size(g, real_sizes) <= dominant * SCRIPT_MAX_SIZE_RATIO for g in ordinary
    )


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
    others = [
        g for other in same_line for g in script_glyphs(other) if g[2].get('char', '').isalnum()
    ]
    runs = {run.start: run for run in script_runs(glyphs, ordinary)} if ordinary else {}
    line_box = positioned_box(line_dict)
    if others and (not ordinary or is_small_fragment(ordinary, others)):
        # Judge the fragment against the surrounding text. Scripts of its own,
        # such as the subscript in a superscript `2−c₁`, keep their own level
        # unless they are scripts of the surrounding text too.
        runs.update((run.start, run) for run in script_runs(glyphs, others))
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


def is_fraction_denominator(
    numerator: Line, numerator_dict: PdfTextLine, denominator: Line, following: Line
) -> bool:
    """Return whether a line is centered below small text ending the preceding line.

    The text following it must continue the line of the numerator, so text
    on the next line never counts as a denominator.
    """
    if (
        numerator.y1 is None
        or numerator.y2 is None
        or denominator.x1 is None
        or denominator.x2 is None
        or denominator.y1 is None
        or denominator.y2 is None
        or following.y2 is None
        or same_physical_line(numerator, denominator)
        or not same_running_text_line(numerator, following)
    ):
        return False
    font_size = max(numerator.font_size or 0.0, following.font_size or 0.0)
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


# pdftext occasionally puts a script into a block of its own, which reading
# order then moves away from its line, as with the superscript `i` of `Fⁱ` in
# lipics-64. Such a script touches the end of the text it belongs to.
SCRIPT_ATTACHMENT_MAX_GAP_EM = 0.1

# TeX moves a superscript right of the subscript below it by the italic
# correction of their base, 0.07 em for the `C` of lipics-64's `C₀⁽ˢ,ᶠ⁾`.
STACKED_SCRIPT_MAX_ITALIC_CORRECTION_EM = 0.15


def glyph_font_size(char: PdfTextChar) -> float | None:
    """Return a glyph's font size, or its bbox height for placeholder sizes."""
    size = float(char.get('font', {}).get('size', 1) or 1)
    if size > 1:
        return size
    _, y1, _, y2 = get_bbox(char)
    return None if y1 is None or y2 is None else y2 - y1


def is_line_end_span(span_dict: PdfTextSpan) -> bool:
    """Return whether a span holds nothing but a line end."""
    return not span_dict.get('text', '').strip('\r\n') and bool(span_dict.get('text'))


def continued_line(
    script_dict: PdfTextLine, candidates: Sequence[PdfTextLine]
) -> PdfTextLine | None:
    """Return the only candidate whose end a line of small glyphs directly continues."""
    script_box = positioned_box(script_dict)
    chars = visible_chars(script_dict)
    sizes = [glyph_font_size(char) for char in chars]
    if (
        script_box is None
        or not chars
        or any(abs(float(char.get('rotation', 0))) > 0.1 for char in chars)
    ):
        return None
    matches: list[PdfTextLine] = []
    for candidate in candidates:
        box = positioned_box(candidate)
        font_size = dominant_font_size(candidate)
        base_chars = visible_chars(candidate)
        if box is None or font_size is None or not base_chars:
            continue
        base_box = positioned_char_box(base_chars[-1])
        if (
            base_box is not None
            and abs(script_box[0] - box[2]) <= font_size * SCRIPT_ATTACHMENT_MAX_GAP_EM
            and all(
                size is not None and size <= font_size * SCRIPT_MAX_SIZE_RATIO for size in sizes
            )
            and script_kind(script_box, base_box) is not None
        ):
            matches.append(candidate)
    return matches[0] if len(matches) == 1 else None


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


def attach_stray_scripts(page_list: Sequence[Page]) -> None:
    """Append scripts that pdftext set apart in a block of their own to their line, in place.

    Scripts already adjacent to their line in pdftext's order are left alone.
    """
    for page_dict in page_list:
        blocks = page_dict.get('blocks', [])
        ordered = [line for block in blocks for line in block.get('lines', [])]
        for block in blocks:
            if len(block.get('lines', [])) != 1:
                continue
            script_dict = block['lines'][0]
            index = next(i for i, line in enumerate(ordered) if line is script_dict)
            neighbors = ordered[max(0, index - 1) : index + 2]
            target = continued_line(
                script_dict,
                [
                    line
                    for other in blocks
                    if other is not block
                    for line in other.get('lines', [])
                    if not any(line is neighbor for neighbor in neighbors)
                ],
            )
            if target is None:
                continue
            append_spans(target, script_dict.get('spans', []))
            block['lines'] = []


def append_spans(target: PdfTextLine, spans: Sequence[PdfTextSpan]) -> None:
    """Insert spans other than line ends before the line end of target, extending its bbox."""
    existing = target.get('spans', [])
    line_end = len(existing)
    while line_end and is_line_end_span(existing[line_end - 1]):
        line_end -= 1
    moved = [span for span in spans if not is_line_end_span(span)]
    target['spans'] = existing[:line_end] + moved + existing[line_end:]
    boxes = [box for box in map(positioned_box, [target, *moved]) if box is not None]
    if boxes:
        target['bbox'] = cast(Bbox, list(union_box(boxes)))


def trailing_small_run(
    chars: Sequence[PdfTextChar], font_size: float
) -> tuple[list[Box], Box | None] | None:
    """Return the boxes of small glyphs ending chars and of the glyph before them, if any."""
    run: list[Box] = []
    for char in reversed(chars):
        size = glyph_font_size(char)
        box = positioned_char_box(char)
        if size is None or box is None:
            return None
        if size > font_size * SCRIPT_MAX_SIZE_RATIO:
            return run, box
        run.append(box)
    return run, None


def trailing_script(
    line_dict: PdfTextLine, before: PdfTextLine | None
) -> tuple[Box, Box, Literal['sup', 'sub'], float] | None:
    """Return the boxes of a script ending a line and of its base glyph, its kind, and size.

    A line of nothing but a script, which pdftext can set apart from its base,
    takes the base from the end of the line before, if they touch.
    """
    chars = visible_chars(line_dict)
    font_size = dominant_font_size(line_dict)
    trailing = None if font_size is None else trailing_small_run(chars, font_size)
    if trailing is None:
        return None
    run, base_box = trailing
    if not run and before is not None:
        # Measure a line of small glyphs against the line it continues.
        before_chars = visible_chars(before)
        font_size = dominant_font_size(before)
        trailing = None if font_size is None else trailing_small_run(chars, font_size)
        if not before_chars or font_size is None or trailing is None or trailing[1] is not None:
            return None
        run = trailing[0]
        base_box = positioned_char_box(before_chars[-1])
        if (
            not run
            or base_box is None
            or abs(union_box(run)[0] - base_box[2]) > font_size * SCRIPT_ATTACHMENT_MAX_GAP_EM
        ):
            return None
    if not run or base_box is None or font_size is None:
        return None
    kind = script_kind(union_box(run), base_box)
    return None if kind is None else (union_box(run), base_box, kind, font_size)


def leading_small_spans(line_dict: PdfTextLine, font_size: float) -> tuple[int, Box] | None:
    """Return the number and box of the spans starting a line that hold only small glyphs."""
    count = 0
    boxes: list[Box] = []
    for span in line_dict.get('spans', []):
        chars = [char for char in span.get('chars', []) if char.get('char', '').strip()]
        sizes = [glyph_font_size(char) for char in chars]
        char_boxes = [positioned_char_box(char) for char in chars]
        if (
            not chars
            or any(size is None or size > font_size * SCRIPT_MAX_SIZE_RATIO for size in sizes)
            or any(box is None for box in char_boxes)
        ):
            break
        count += 1
        boxes.extend(box for box in char_boxes if box is not None)
    return (count, union_box(boxes)) if boxes else None


def attach_stacked_scripts(page_list: Sequence[Page]) -> None:
    """Move scripts stacked below or above a script ending the preceding line into it, in place.

    TeX aligns a subscript below a superscript, as in lipics-64's `R` with `i`
    above `∗`. When pdftext starts the next line record with the second
    script, that record seems to begin left of where the first one ends.
    """
    for page_dict in page_list:
        blocks = page_dict.get('blocks', [])
        ordered = [(block, line) for block in blocks for line in block.get('lines', [])]
        for index, (block, line) in enumerate(ordered[1:], start=1):
            previous = ordered[index - 1][1]
            trailing = trailing_script(previous, ordered[index - 2][1] if index > 1 else None)
            if trailing is None:
                continue
            script_box, base_box, kind, font_size = trailing
            leading = leading_small_spans(line, font_size)
            if leading is None:
                continue
            count, box = leading
            superscript_box, subscript_box = (
                (script_box, box) if kind == 'sup' else (box, script_box)
            )
            # A superscript follows the italic correction of its base.
            offset = superscript_box[0] - subscript_box[0]
            if not (
                -font_size * STACKED_ALIGNMENT_TOLERANCE_EM
                <= offset
                <= font_size * STACKED_SCRIPT_MAX_ITALIC_CORRECTION_EM
            ) or script_kind(box, base_box) in {None, kind}:
                continue
            spans = line.get('spans', [])
            append_spans(previous, spans[:count])
            line['spans'] = spans[count:]
            remaining = [
                box for box in map(positioned_char_box, visible_chars(line)) if box is not None
            ]
            if remaining:
                line['bbox'] = cast(Bbox, list(union_box(remaining)))
            else:
                block['lines'] = [other for other in block['lines'] if other is not line]


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
                )
                page_lines.append((line_obj, line_dict, block_dict.get('lines', []), raw_text))

                previous_x1 = x1
                previous_y1 = y1

        # pdftext emits the pieces of a split line of running text
        # consecutively, though not necessarily within one block.
        for index, (line_obj, line_dict, block_lines, raw_text) in enumerate(page_lines):
            same_line: list[PdfTextLine] = []
            if index > 0 and same_running_text_line(page_lines[index - 1][0], line_obj):
                same_line.append(page_lines[index - 1][1])
            if index + 1 < len(page_lines) and same_running_text_line(
                line_obj, page_lines[index + 1][0]
            ):
                same_line.append(page_lines[index + 1][1])
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
            line_list.append(line_obj)

    return line_list
