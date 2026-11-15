"""Decode the math glyphs of fonts embedded by Advent 3B2 (PTC Arbortext APP).

Many publisher PDFs, as from Elsevier, Wiley, and Nature Communications, set
math in fonts named `Adv…` that clone the layouts of TeX's Computer Modern
math fonts under wrong glyph names. Their Unicode mappings follow these names,
so `=` reads as `¼`, `+` as `þ`, and `(x)` as `ðxÞ`, as in nature-spin's
`κ = ∑ᵢ…`. Glyphs named after character positions, such as `C24`, have no
Unicode mapping at all, and pdftext reports their font codes instead.

Each glyph's name gives its position in the TeX layout: the extra glyphs of
the symbol fonts, such as `onequarter`, draw what roman type would; names
like `C24` give the position in decimal; and names of ASCII characters, such
as `zero` or `p`, give that character's code, so `zero` is the prime and `p`
the radical of the symbol font. The text fonts of Advent are left alone.
"""

import re
from collections.abc import Sequence
from pathlib import Path
from typing import cast
from unicodedata import normalize

from pdftext.schema import Bbox, Page
from pdftext.schema import Block as PdfTextBlock
from pdftext.schema import Char as PdfTextChar
from pdftext.schema import Line as PdfTextLine
from pdftext.schema import Span as PdfTextSpan

from frompdf.font_encodings import base_font_name, read_font_differences
from frompdf.glyph_repairs import (
    MATH_EXTENSION_ACCENTS,
    MATH_EXTENSION_CHARS,
    overlaps_horizontally,
)
from frompdf.lines import Box, union_box

# Base names of the clones by TeX layout. Not all of them have been seen in
# PDFs; the others follow zotero-pdf-miner's list.
ADVENT_MATH_FONTS: dict[str, frozenset[str]] = {
    'cmsy': frozenset(
        {
            'AdvMacMthSyN',
            'AdvP4C4E74',
            'AdvMT_SY',
            'AdvMacMthSy',
            'AdvMTSYan',
            'AdvMTSY_A',
            'AdvMathSymb',
            'Advcl-sym',
        }
    ),
    'cmmi': frozenset({'AdvP4C4E51', 'AdvMT_MI', 'AdvMacMthIt', 'AdvMTMI'}),
    'cmex': frozenset({'AdvP4C4E46', 'AdvMT_EX', 'AdvMTEX', 'AdvMathExtr'}),
    'cmr': frozenset({'AdvP4C4E59'}),
}
LAYOUT_BY_FONT = {name: layout for layout, names in ADVENT_MATH_FONTS.items() for name in names}

# Glyphs of TeX positions, from the glyph names in cmsy10.afm, cmmi10.afm, and
# cmr10.afm. Calligraphic capitals become plain ones. The `mapsto` bar and the
# hooks of arrows are pieces of other symbols and drop out.
NEGATION_SLASH = '̸'
CMSY: dict[int, str] = {
    **dict(enumerate('−·×∗÷⋄±∓⊕⊖⊗⊘⊙◯∘∙≍≡⊆⊇≤≥⪯⪰∼≈⊂⊃≪≫≺≻←→↑↓↔↗↘≃⇐⇒⇑⇓⇔↖↙∝′∞∈∋△▽')),
    0x36: NEGATION_SLASH,
    0x37: '',
    **dict(enumerate('∀∃¬∅ℜℑ⊤⊥ℵABCDEFGHIJKLMNOPQRSTUVWXYZ∪∩⊎∧∨⊢⊣⌊⌋⌈⌉{}⟨⟩|‖↕⇕∖≀', start=0x38)),
    **dict(enumerate('√⨿∇∫⊔⊓⊑⊒§†‡¶♣♢♡♠', start=0x70)),
}
CMMI: dict[int, str] = {
    **dict(enumerate('ΓΔΘΛΞΠΣΥΦΨΩαβγδϵζηθικλμνξπρστυϕχψωεϑϖϱςφ↼↽⇀⇁')),
    0x2C: '',
    0x2D: '',
    **dict(enumerate('▹◃0123456789.,</>⋆∂ABCDEFGHIJKLMNOPQRSTUVWXYZ♭♮♯⌣⌢ℓ', start=0x2E)),
    **dict(enumerate('abcdefghijklmnopqrstuvwxyzıȷ℘', start=0x61)),
    0x7E: '',
    0x7F: '',
}
CMR: dict[int, str] = {
    **dict(enumerate('ΓΔΘΛΞΠΣΥΦΨΩ')),
    **dict(enumerate(['ff', 'fi', 'fl', 'ffi', 'ffl'], start=0x0B)),
    **dict(enumerate('ıȷ`´ˇ˘¯˚¸ßæœøÆŒØ', start=0x10)),
    0x20: '',
    **dict(enumerate('!”#$%&’()*+,-./0123456789:;¡=¿?@', start=0x21)),
    **dict(enumerate('ABCDEFGHIJKLMNOPQRSTUVWXYZ[“]ˆ˙‘', start=0x41)),
    **dict(enumerate('abcdefghijklmnopqrstuvwxyz–—˝˜¨', start=0x61)),
}
# The math extension layout adds to the glyphs decoded for TeX fonts the top
# piece of each extensible delimiter and the bottom of the radical. Other
# pieces drop out.
CMEX: dict[int, str] = {
    **dict.fromkeys(range(0x80), ''),
    **MATH_EXTENSION_CHARS,
    **dict(zip((0x30, 0x31, 0x32, 0x33, 0x38, 0x39, 0x74), '()[]{}√', strict=True)),
}
LAYOUTS: dict[str, dict[int, str]] = {'cmsy': CMSY, 'cmmi': CMMI, 'cmex': CMEX, 'cmr': CMR}

# Glyphs outside the TeX layouts, by name. In the symbol fonts, these draw
# what roman type would at their positions. The `ffi` glyph of the extension
# font is the bar over a radical, as in nature-spin's `√(2πN)`.
SPECIAL_GLYPHS: dict[str, dict[str, str]] = {
    'cmsy': {
        'onequarter': '=',
        'thorn': '+',
        'eth': '(',
        'Thorn': ')',
        'onehalf': '[',
        'C138': ']',
    },
    'cmex': {'ffi': ''},
    # The dieresis of the roman font, as wiley's `Tielbörger`, is named `Euro`.
    'cmr': {'Euro': '¨'},
}
# The text that Unicode mappings following these glyph names give them.
SPECIAL_GLYPH_NAMES = {
    '¼': 'onequarter',
    'þ': 'thorn',
    'ð': 'eth',
    'Þ': 'Thorn',
    '½': 'onehalf',
    'ffi': 'ffi',
    'ﬃ': 'ffi',
    '€': 'Euro',
}
POSITION_NAME_PATTERN = re.compile(r'C(\d+)')


def advent_math_layout(font_name: str) -> str | None:
    """Return the TeX layout cloned by an Advent math font, or None for other fonts."""
    return LAYOUT_BY_FONT.get(base_font_name(font_name))


def decode_glyph(
    layout: str, text: str, differences: dict[int, str]
) -> tuple[int | None, str] | None:
    """Return the TeX position and text of a glyph that pdftext decoded as text.

    Font codes reported for glyphs without a Unicode mapping are looked up in
    the font's `/Differences`. Other text follows the glyph's name. Glyphs
    outside the layout have no position. Return None for unknown glyphs.
    """
    if len(text) == 1 and text < ' ':
        name = differences.get(ord(text))
    else:
        name = SPECIAL_GLYPH_NAMES.get(text)
    if name is not None:
        special = SPECIAL_GLYPHS.get(layout, {}).get(name)
        if special is not None:
            return None, special
        match = POSITION_NAME_PATTERN.fullmatch(name)
        position = int(match.group(1)) if match else None
    elif len(text) == 1 and ' ' < text < '\x7f':
        position = ord(text)
    else:
        position = None
    table = LAYOUTS[layout]
    return None if position not in table else (position, table[position])


def span_glyphs(span_dict: PdfTextSpan) -> list[list[PdfTextChar]]:
    """Return the characters of a span grouped by glyph.

    pdftext gives each character of a glyph mapped to several, as `ffi`, the
    glyph's box.
    """
    glyphs: list[list[PdfTextChar]] = []
    for char in span_dict.get('chars', []):
        if (
            glyphs
            and char.get('bbox') == glyphs[-1][0].get('bbox')
            and char.get('char', '').strip()
            and glyphs[-1][0].get('char', '').strip()
        ):
            glyphs[-1].append(char)
        else:
            glyphs.append([char])
    return glyphs


def decode_span(
    span_dict: PdfTextSpan,
    layout: str,
    differences: dict[int, str],
    previous_char: PdfTextChar | None,
) -> PdfTextChar | None:
    """Decode the glyphs of a span in an Advent math font in place.

    Return the last visible character, for wide accents in a following span.
    """
    texts: list[str] = []
    negation = False
    for glyph in span_glyphs(span_dict):
        text = ''.join(char.get('char', '') for char in glyph)
        result = decode_glyph(layout, text, differences) if text.strip() else None
        position, decoded = result if result is not None else (None, None)
        if decoded is None:
            # Font codes without a known glyph are dropped, as pdftext does.
            decoded = '' if len(text) == 1 and text < ' ' and text not in '\r\n' else text
        elif layout == 'cmex' and position in MATH_EXTENSION_ACCENTS:
            combining, spacing = MATH_EXTENSION_ACCENTS[position]
            above = previous_char is not None and overlaps_horizontally(glyph[0], previous_char)
            decoded = combining if above else spacing
        elif decoded == NEGATION_SLASH:
            # The slash precedes the symbol it negates, as `≠` from `=`.
            negation = True
            decoded = ''
        if negation and decoded.strip():
            decoded = normalize('NFC', decoded + NEGATION_SLASH)
            negation = False
        glyph[0]['char'] = decoded
        for char in glyph[1:]:
            char['char'] = ''
        texts.append(decoded)
        if decoded.strip():
            previous_char = glyph[0]
    # pdftext reads CRLF as one line end, as in span_char_text_ranges.
    text = ''.join(texts).replace('\r\n', '\n')
    if span_dict.get('text', '').endswith('\n') and not text.endswith('\n'):
        text += '\n'
    span_dict['text'] = text
    return previous_char


# pdftext takes font code 2 for pdfium's mark of a hyphen ending a line, so it
# reads such a glyph as `-` and a line end and starts a new line record after
# it, as after the `∼` of nature-spin's `τ ∼ c/κ`. The next record continues
# the same visual line if they overlap vertically by at least this share of
# the lower one's height.
HYPHEN_MARK_CODE = '\x02'
SAME_LINE_MIN_OVERLAP = 0.5


def ends_at_code_2(line_dict: PdfTextLine) -> bool:
    """Return whether a line record ends at a glyph of an Advent math font with font code 2."""
    spans = line_dict.get('spans', [])
    if not spans:
        return False
    font_name = spans[-1].get('font', {}).get('name')
    chars = spans[-1].get('chars', [])
    return (
        isinstance(font_name, str)
        and is_advent_math_font(font_name)
        and bool(chars)
        and chars[-1].get('char') == HYPHEN_MARK_CODE
    )


def line_box(line_dict: PdfTextLine) -> Box:
    """Return the box of a line record."""
    x1, y1, x2, y2 = line_dict['bbox']
    return x1, y1, x2, y2


def continues_visual_line(line_dict: PdfTextLine, next_line: PdfTextLine) -> bool:
    """Return whether a line record continues the visual line of the one before it."""
    x1, y1, _, y2 = line_dict['bbox']
    next_x1, next_y1, _, next_y2 = next_line['bbox']
    overlap = min(y2, next_y2) - max(y1, next_y1)
    height = min(y2 - y1, next_y2 - next_y1)
    return next_x1 > x1 and height > 0 and overlap >= height * SAME_LINE_MIN_OVERLAP


def join_lines_split_at_code_2(block_dict: PdfTextBlock) -> None:
    """Join line records that pdftext split after a glyph with font code 2, in place."""
    lines = block_dict.get('lines', [])
    index = 0
    while index + 1 < len(lines):
        line_dict, next_line = lines[index], lines[index + 1]
        if not ends_at_code_2(line_dict) or not continues_visual_line(line_dict, next_line):
            index += 1
            continue
        last_span = line_dict['spans'][-1]
        last_span['text'] = last_span.get('text', '').removesuffix('\n')
        line_dict['spans'].extend(next_line.get('spans', []))
        boxes = [line_box(line_dict), line_box(next_line)]
        line_dict['bbox'] = cast(Bbox, list(union_box(boxes)))
        del lines[index + 1]


def is_advent_math_font(font_name: str) -> bool:
    """Return whether a font is an Advent math font."""
    return advent_math_layout(font_name) is not None


def decode_advent_math_glyphs(page_list: Sequence[Page], input_path: Path | None = None) -> None:
    """Replace the misnamed glyphs of Advent math fonts with the characters they show, in place.

    The font encodings are read from input_path, if given, to decode glyphs
    without a Unicode mapping. Line records that pdftext split after a glyph
    with font code 2 are joined.
    """
    differences: dict[str, dict[int, str]] | None = None
    for page_dict in page_list:
        for block_dict in page_dict.get('blocks', []):
            join_lines_split_at_code_2(block_dict)
            for line_dict in block_dict.get('lines', []):
                previous_char: PdfTextChar | None = None
                for span_dict in line_dict.get('spans', []):
                    font_name = span_dict.get('font', {}).get('name')
                    layout = advent_math_layout(font_name) if isinstance(font_name, str) else None
                    if layout is None or not isinstance(font_name, str):
                        previous_char = next(
                            (
                                char
                                for char in reversed(span_dict.get('chars', []))
                                if char.get('char', '').strip()
                            ),
                            previous_char,
                        )
                        continue
                    if differences is None:
                        differences = (
                            read_font_differences(input_path, is_advent_math_font)
                            if input_path is not None
                            else {}
                        )
                    previous_char = decode_span(
                        span_dict,
                        layout,
                        differences.get(base_font_name(font_name), {}),
                        previous_char,
                    )
