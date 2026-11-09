import re
from collections import defaultdict
from collections.abc import Sequence
from unicodedata import category, normalize

from pdftext.schema import (
    Char as PdfTextChar,
)
from pdftext.schema import (
    Page,
)
from pdftext.schema import (
    Span as PdfTextSpan,
)

from frompdf.lines import get_bbox, span_char_text_ranges

# Spacing accents, including the modifier letters that TeX fonts map their
# circumflex and tilde to, as for lipics-64's `v̂`.
SPACING_TO_COMBINING = {
    '¨': '\u0308',
    '´': '\u0301',
    '`': '\u0300',
    '^': '\u0302',
    'ˆ': '\u0302',
    '~': '\u0303',
    '˜': '\u0303',
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

# Symbol and Wingdings fonts map their bullets to private-use code points,
# such as U+F0B7 in schmueck's Literatur section. pdftext drops these from span
# text as non-printable, but keeps them in its character data.
SYMBOL_FONT_NAME_PATTERN = re.compile(r'symbol', flags=re.IGNORECASE)
WINGDINGS_FONT_NAME_PATTERN = re.compile(r'wingdings', flags=re.IGNORECASE)
SYMBOL_BULLETS = {'\uf0b7': '•'}
WINGDINGS_BULLETS = {'\uf0a7': '▪', '\uf076': '❖', '\uf0d8': '➢', '\uf0fc': '✓'}


def composed_diacritic(base_text: str, spacing_accent: str) -> str | None:
    """Return a Latin letter with the accent of a supported base/accent pair.

    Letters without a precomposed form, as `v̂`, keep a combining accent.
    """
    combining_accent = SPACING_TO_COMBINING.get(spacing_accent)
    if len(base_text) != 1 or combining_accent is None:
        return None
    if not base_text.isascii() or category(base_text) not in {'Ll', 'Lu'}:
        return None
    return normalize('NFC', base_text + combining_accent)


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


# A zero-width space beside an accent separates words if the next character
# follows at a gap of this range, relative to the accent's height, as after
# the accent of lipics-64's `v̂`, which follows its base in reading order.
# Beside the out-of-order accents of ceur-elearning, the next character is
# far away or at the same position.
WORD_GAP_AFTER_ACCENT_RANGE = (0.1, 1.0)


def spacing_artifact_touches_accent(
    whitespace_char: PdfTextChar,
    accent_char: PdfTextChar,
    following_char: PdfTextChar | None = None,
) -> bool:
    """Return whether a zero-width space was inserted beside an out-of-order accent.

    following_char is the visible character after the space, if any.
    """
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

    following_x1 = get_bbox(following_char)[0] if following_char is not None else None
    if following_x1 is not None:
        gap = following_x1 - whitespace_x1
        min_gap, max_gap = WORD_GAP_AFTER_ACCENT_RANGE
        if accent_height * min_gap < gap <= accent_height * max_gap:
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

                    for whitespace_index, (whitespace_span, whitespace_char) in enumerate(
                        positioned_chars
                    ):
                        whitespace_span_id = id(whitespace_span)
                        following_char = next(
                            (
                                char_dict
                                for _, char_dict in positioned_chars[whitespace_index + 1 :]
                                if char_dict.get('char', '').strip()
                            ),
                            None,
                        )
                        if (
                            spacing_artifact_touches_accent(
                                whitespace_char, accent_char, following_char
                            )
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


# The AMS blackboard bold fonts (msbm5 to msbm10) map their double-struck
# capitals to plain ones, as the `ℝ` of lipics-64's `R ⊆ ℝⁿ`. Their other
# glyphs are unrelated symbols, left as reported.
DOUBLE_STRUCK_FONT_NAME_PATTERN = re.compile(r'\bmsbm\d', re.IGNORECASE)
LETTERLIKE_DOUBLE_STRUCK = {'C': 'ℂ', 'H': 'ℍ', 'N': 'ℕ', 'P': 'ℙ', 'Q': 'ℚ', 'R': 'ℝ', 'Z': 'ℤ'}
DOUBLE_STRUCK_CAPITALS = str.maketrans(
    {
        letter: LETTERLIKE_DOUBLE_STRUCK.get(letter, chr(0x1D538 + index))
        for index, letter in enumerate('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
    }
)


def decode_double_struck_letters(page_list: Sequence[Page]) -> None:
    """Replace capitals of blackboard bold fonts with double-struck letters, in place."""
    for page_dict in page_list:
        for block_dict in page_dict.get('blocks', []):
            for line_dict in block_dict.get('lines', []):
                for span_dict in line_dict.get('spans', []):
                    font_name = span_dict.get('font', {}).get('name')
                    if not isinstance(font_name, str) or not DOUBLE_STRUCK_FONT_NAME_PATTERN.search(
                        font_name
                    ):
                        continue
                    span_dict['text'] = span_dict.get('text', '').translate(DOUBLE_STRUCK_CAPITALS)
                    for char in span_dict.get('chars', []):
                        char['char'] = char.get('char', '').translate(DOUBLE_STRUCK_CAPITALS)


def private_use_bullets(span_dict: PdfTextSpan) -> dict[str, str]:
    """Return the bullets that a span's font maps to private-use code points."""
    font_name = span_dict.get('font', {}).get('name')
    if not isinstance(font_name, str):
        return {}
    if SYMBOL_FONT_NAME_PATTERN.search(font_name):
        return SYMBOL_BULLETS
    if WINGDINGS_FONT_NAME_PATTERN.search(font_name):
        return WINGDINGS_BULLETS
    return {}


def restore_private_use_bullets(page_list: Sequence[Page]) -> None:
    """Restore bullets that pdftext dropped from the text of symbol-font spans, in place.

    Only spans without other text are restored, so text that pdftext
    normalized is never rebuilt from its character data.
    """
    for page_dict in page_list:
        for block_dict in page_dict.get('blocks', []):
            for line_dict in block_dict.get('lines', []):
                for span_dict in line_dict.get('spans', []):
                    bullets = private_use_bullets(span_dict)
                    chars = [char.get('char', '') for char in span_dict.get('chars', [])]
                    if (
                        bullets
                        and chars
                        and not span_dict.get('text', '').strip()
                        and all(char in bullets for char in chars)
                    ):
                        span_dict['text'] = ''.join(bullets[char] for char in chars)
