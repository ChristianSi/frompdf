import tempfile
import unittest
import zlib
from pathlib import Path
from typing import cast

from pdftext.schema import Page

from frompdf.advent_fonts import advent_math_layout, decode_advent_math_glyphs
from frompdf.font_encodings import base_font_name, read_font_differences
from frompdf.lines import iter_lines

SYMBOLS = 'AdvMacMthSyN'
ITALIC = 'AdvP4C4E51'
EXTENSION = 'AdvP4C4E46'
# The encoding of nature-spin's symbol font.
SYMBOL_DIFFERENCES = (
    b'[2 /C24 /C0 /C1 48 /zero /one 112 /p 188 /onequarter 222 /Thorn 240 /eth 254 /thorn]'
)


def span(
    chars: list[str], font_name: str, text: str | None = None, x: float = 0.0, width: float = 5.0
) -> dict:
    """Build a span of glyphs side by side, with pdftext's text for them.

    A glyph given as several characters, as `ffi`, gives each of them its box.
    """
    char_dicts = []
    for index, glyph in enumerate(chars):
        x1 = x + index * width
        char_dicts.extend(
            {'char': char, 'bbox': [x1, 0.0, x1 + width, 10.0], 'rotation': 0} for char in glyph
        )
    return {
        'text': ''.join(char for char in ''.join(chars) if char >= ' ') if text is None else text,
        'font': {'name': font_name, 'size': 10.0},
        'chars': char_dicts,
    }


def page_of(*spans: dict) -> Page:
    return cast(Page, {'blocks': [{'lines': [{'bbox': [0, 0, 100, 10], 'spans': list(spans)}]}]})


def decoded_text(*spans: dict, input_path: Path | None = None) -> str:
    """Return the line text after decoding Advent math glyphs."""
    page = page_of(*spans)
    decode_advent_math_glyphs([page], input_path)
    return iter_lines([page])[0].text


def object_stream(objects: dict[int, bytes]) -> bytes:
    """Return a compressed object stream holding the given objects."""
    header = b''
    content = b''
    for number, body in objects.items():
        header += b'%d %d ' % (number, len(content))
        content += body + b'\n'
    data = zlib.compress(header + content)
    return (
        b'<< /Type /ObjStm /N %d /First %d /Filter /FlateDecode /Length %d >>\nstream\n'
        % (len(objects), len(header), len(data))
        + data
        + b'\nendstream'
    )


def write_pdf(directory: str, objects: dict[int, bytes]) -> Path:
    """Write the objects into a file read like a PDF, without cross-reference table."""
    path = Path(directory) / 'fonts.pdf'
    body = b''.join(b'%d 0 obj\n%s\nendobj\n' % (number, obj) for number, obj in objects.items())
    path.write_bytes(b'%PDF-1.5\n' + body + b'%%EOF\n')
    return path


class FontEncodingTests(unittest.TestCase):
    def test_subset_prefixes_are_stripped(self) -> None:
        self.assertEqual(base_font_name('MOPKPN+AdvMacMthSyN'), SYMBOLS)
        self.assertEqual(base_font_name('XwktxbAdvPi3'), 'AdvPi3')
        self.assertEqual(base_font_name('HqfbcsCMSY10'), 'CMSY10')
        self.assertEqual(base_font_name('AdvOT7d6df7ab.I+03'), 'AdvOT7d6df7ab.I+03')
        self.assertEqual(base_font_name('Helvetica'), 'Helvetica')

    def test_differences_are_read_from_referenced_and_compressed_objects(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = write_pdf(
                directory,
                {
                    1: b'<< /Type /Font /BaseFont /MOPKPN+AdvMacMthSyN /Encoding 2 0 R >>',
                    2: b'<< /Type /Encoding /Differences ' + SYMBOL_DIFFERENCES + b' >>',
                    3: object_stream(
                        {
                            4: b'<< /Type /Font /BaseFont /MOPLEB+AdvP4C4E46 '
                            b'/Encoding << /Differences [1 /C10 3 /C11 /ffi 90 /Z] >> >>',
                        }
                    ),
                    5: b'<< /Type /Font /BaseFont /ABCDEF+Times#2DRoman '
                    b'/Encoding << /Differences [188 /onequarter] >> >>',
                },
            )
            differences = read_font_differences(path, lambda name: name.startswith('Adv'))
        self.assertEqual(
            differences[SYMBOLS],
            {
                2: 'C24',
                3: 'C0',
                4: 'C1',
                48: 'zero',
                49: 'one',
                112: 'p',
                188: 'onequarter',
                222: 'Thorn',
                240: 'eth',
                254: 'thorn',
            },
        )
        self.assertEqual(differences[EXTENSION], {1: 'C10', 3: 'C11', 4: 'ffi', 90: 'Z'})
        self.assertNotIn('Times-Roman', differences)

    def test_codes_assigned_differently_by_subsets_are_left_out(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = write_pdf(
                directory,
                {
                    1: b'<< /BaseFont /AAAAAA+AdvMacMthSyN '
                    b'/Encoding << /Differences [2 /C24 /C0] >> >>',
                    2: b'<< /BaseFont /BBBBBB+AdvMacMthSyN '
                    b'/Encoding << /Differences [2 /C2 /C0] >> >>',
                },
            )
            differences = read_font_differences(path, lambda name: True)
        self.assertEqual(differences[SYMBOLS], {3: 'C0'})


class AdventMathGlyphTests(unittest.TestCase):
    def test_layouts_follow_base_names(self) -> None:
        self.assertEqual(advent_math_layout('MOPKPN+AdvMacMthSyN'), 'cmsy')
        self.assertEqual(advent_math_layout(ITALIC), 'cmmi')
        self.assertEqual(advent_math_layout(EXTENSION), 'cmex')
        self.assertIsNone(advent_math_layout('AdvOT7d6df7ab.I+03'))
        self.assertIsNone(advent_math_layout('AdvPi1'))

    def test_misnamed_symbols_become_the_characters_they_show(self) -> None:
        self.assertEqual(
            decoded_text(
                span(['ð'], SYMBOLS),
                span(['x'], 'AdvOT7d6df7ab.I'),
                span(['þ', '1', 'Þ', '¼', 'p'], SYMBOLS),
                span(['2', '0'], 'AdvOT1ef757c0'),
            ),
            '(x+∞)=√20',
        )

    def test_names_of_ascii_characters_give_positions_in_the_layout(self) -> None:
        # `zero` is the prime of the symbol font, `equal` and `semicolon` are
        # the slash and comma of the math italic font.
        self.assertEqual(
            decoded_text(
                span(['r'], 'AdvOT7d6df7ab.I'),
                span(['0'], SYMBOLS),
                span(['=', ';'], ITALIC),
            ),
            'r′/,',
        )

    def test_font_codes_are_decoded_by_their_glyph_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = write_pdf(
                directory,
                {
                    1: b'<< /BaseFont /MOPKPN+AdvMacMthSyN /Encoding << /Differences '
                    + SYMBOL_DIFFERENCES
                    + b' >> >>',
                    2: b'<< /BaseFont /MOPLEB+AdvP4C4E46 '
                    b'/Encoding << /Differences [1 /C10 3 /C11 /ffi 90 /Z] >> >>',
                },
            )
            text = decoded_text(
                span(['\x01'], EXTENSION, text=''),
                span(['\x02', '\x03', '\x04'], SYMBOLS, text='', x=5),
                span(['\x03', 'Z'], EXTENSION, text='Z', x=20),
                input_path=path,
            )
        self.assertEqual(text, '⟨∼−·⟩∫')

    def test_font_codes_without_known_glyph_names_are_dropped(self) -> None:
        self.assertEqual(
            decoded_text(span(['\x02', '¼'], SYMBOLS, text='¼'), span(['1'], 'AdvOT1ef757c0')),
            '=1',
        )

    def lines_after_code_2(self, next_top: float) -> list:
        """Decode a line ending in font code 2 and a next line record at next_top."""
        # pdftext reads font code 2 as a hyphen ending a line, and starts a new
        # line record after it.
        first = {'bbox': [0, 0, 20, 10], 'spans': [span(['y'], 'AdvOT7d6df7ab.I')]}
        first['spans'].append(span(['\x02'], SYMBOLS, text='-\n', x=10))
        second = {
            'bbox': [20, next_top, 60, next_top + 10],
            'spans': [span(['b', 'i', 'n'], 'AdvOT1ef757c0', x=20)],
        }
        page = cast(Page, {'blocks': [{'lines': [first, second]}]})
        with tempfile.TemporaryDirectory() as directory:
            path = write_pdf(
                directory,
                {1: b'<< /BaseFont /AdvMacMthSyN /Encoding << /Differences [2 /C24] >> >>'},
            )
            decode_advent_math_glyphs([page], path)
        return iter_lines([page])

    def test_line_split_after_font_code_2_is_joined(self) -> None:
        lines = self.lines_after_code_2(next_top=0.5)
        self.assertEqual([line.text for line in lines], ['y∼bin'])

    def test_line_end_after_font_code_2_is_kept_before_the_next_line(self) -> None:
        lines = self.lines_after_code_2(next_top=12)
        self.assertEqual([line.text for line in lines], ['y∼', 'bin'])

    def test_accents_of_the_roman_font_become_spacing_accents(self) -> None:
        # Code 2 is the acute accent (`C19`) of wiley's `Ravigné`, and the
        # dieresis of its `Tielbörger` is named `Euro`.
        with tempfile.TemporaryDirectory() as directory:
            path = write_pdf(
                directory,
                {1: b'<< /BaseFont /AdvP4C4E59 /Encoding << /Differences [2 /C19] >> >>'},
            )
            text = decoded_text(span(['\x02', '€'], 'AdvP4C4E59', text='-'), input_path=path)
        self.assertEqual(text, '´¨')

    def test_radical_bar_drawn_as_ligature_is_dropped(self) -> None:
        self.assertEqual(
            decoded_text(span(['ffi', 'ffi', 'ffi'], EXTENSION), span(['N'], 'AdvOT1ef757c0')),
            'N',
        )

    def test_negation_slash_combines_with_the_following_symbol(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = write_pdf(
                directory,
                {1: b'<< /BaseFont /AdvMacMthSyN /Encoding << /Differences [5 /C54] >> >>'},
            )
            self.assertEqual(decoded_text(span(['\x05', '¼'], SYMBOLS), input_path=path), '≠')

    def test_wide_accent_combines_with_the_glyph_below_it(self) -> None:
        # Code 0x62 (`b`) is the wide hat of the extension font.
        base = span(['P'], 'AdvOT7d6df7ab.I')
        self.assertEqual(decoded_text(base, span(['b'], EXTENSION)), 'P̂')
        base = span(['P'], 'AdvOT7d6df7ab.I')
        self.assertEqual(decoded_text(base, span(['b'], EXTENSION, x=12)), 'Pˆ')

    def test_same_characters_in_other_fonts_are_kept(self) -> None:
        # Real fractions and Icelandic letters must survive.
        self.assertEqual(
            decoded_text(span(['¼', ' ', 'þ', 'ð', 'Þ'], 'ABCDEF+Times-Roman')),
            '¼ þðÞ',
        )
        self.assertEqual(decoded_text(span(['=', 'p'], 'AdvOT1ef757c0')), '=p')


class AdventPiGlyphTests(unittest.TestCase):
    def test_misnamed_glyphs_become_the_characters_they_show(self) -> None:
        self.assertEqual(
            decoded_text(span(['c'], 'IGPHCJ+AdvPSMP10'), span(['species'], 'AdvMINION-R')),
            'γspecies',
        )
        self.assertEqual(
            decoded_text(
                span(['two '], 'AdvMINION-R'),
                span(['9'], 'AdvTir_symb'),
                span([' two'], 'AdvMINION-R'),
            ),
            'two × two',
        )
        self.assertEqual(decoded_text(span(['ª', ' 2014'], 'AdvPSSym')), '© 2014')
        self.assertEqual(decoded_text(span(['#'], 'BLECFF+AdvPi3')), '©')

    def test_glyphs_not_seen_in_documents_are_kept(self) -> None:
        self.assertEqual(decoded_text(span(['a', 'm'], 'AdvPSMP10')), 'am')
        self.assertEqual(decoded_text(span(['8'], 'AdvTir_symb')), '8')

    def test_same_characters_in_other_fonts_are_kept(self) -> None:
        self.assertEqual(decoded_text(span(['b', '9', 'ª', '#'], 'AdvMINION-R')), 'b9ª#')
        self.assertEqual(decoded_text(span(['b', '9', 'ª', '#'], 'AdvPi1')), 'b9ª#')


if __name__ == '__main__':
    unittest.main()
