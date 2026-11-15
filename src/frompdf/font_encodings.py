"""Read the glyph names that PDF fonts assign to their character codes.

pdfium reports neither font dictionaries nor glyph names, so the
`/Differences` arrays of font encodings are read from the raw file. The
objects are found by scanning for `obj` keywords, including those in
compressed object streams, without relying on the cross-reference table.
This is enough for the small, plain dictionaries of fonts; objects that
cannot be read are skipped.
"""

import re
import zlib
from collections.abc import Callable
from pathlib import Path

OBJECT_START_PATTERN = re.compile(rb'(?<![\d.])(\d+)\s+\d+\s+obj\b')
STREAM_KEYWORD_PATTERN = re.compile(rb'\bstream\r?\n')
OBJECT_STREAM_PATTERN = re.compile(rb'/Type\s*/ObjStm\b')
INTEGER_ENTRY_PATTERN = re.compile(rb'/(N|First|Length)\s+(\d+)(?!\s+\d+\s+R)')
NAME_TOKEN = rb'/([^\s/\[\]<>(){}%]*)'
BASE_FONT_PATTERN = re.compile(rb'/BaseFont\s*' + NAME_TOKEN)
ENCODING_REFERENCE_PATTERN = re.compile(rb'/Encoding\s*(\d+)\s+\d+\s+R')
DIFFERENCES_PATTERN = re.compile(rb'/Differences\s*(?:\[([^\]]*)\]|(\d+)\s+\d+\s+R)')
ARRAY_PATTERN = re.compile(rb'\s*\[([^\]]*)\]')
DIFFERENCES_TOKEN_PATTERN = re.compile(rb'(\d+)|' + NAME_TOKEN)
NAME_ESCAPE_PATTERN = re.compile(r'#([0-9A-Fa-f]{2})')

# Subset prefixes are six capitals and a plus sign, or, in Springer PDFs, six
# letters glued to the name, as in `XwktxbAdvPi3`.
SUBSET_PREFIX_PATTERN = re.compile(r'^(?:[A-Z]{6}\+|[A-Z][a-z]{5}(?=Adv|CM|MT))')

# Compressed object streams are inflated in chunks of this size, since their
# length may be given by a reference.
INFLATE_CHUNK_SIZE = 1 << 16


def base_font_name(font_name: str) -> str:
    """Return a font name without its subset prefix."""
    return SUBSET_PREFIX_PATTERN.sub('', font_name, count=1)


def decode_name(raw_name: bytes) -> str:
    """Decode a PDF name token, resolving `#xx` escapes."""
    text = raw_name.decode('latin-1')
    return NAME_ESCAPE_PATTERN.sub(lambda match: chr(int(match.group(1), 16)), text)


def inflate_stream(data: bytes, start: int, length: int | None) -> bytes | None:
    """Return the inflated content of a Flate stream starting at start, or None."""
    decompressor = zlib.decompressobj()
    end = len(data) if length is None else min(len(data), start + length)
    parts: list[bytes] = []
    try:
        for chunk_start in range(start, end, INFLATE_CHUNK_SIZE):
            chunk = data[chunk_start : min(end, chunk_start + INFLATE_CHUNK_SIZE)]
            parts.append(decompressor.decompress(chunk))
            if decompressor.eof:
                break
    except zlib.error:
        return None
    return b''.join(parts)


def object_stream_objects(data: bytes, dictionary: bytes, stream_start: int) -> dict[int, bytes]:
    """Return the objects stored in a compressed object stream, by number."""
    entries = {key: int(value) for key, value in INTEGER_ENTRY_PATTERN.findall(dictionary)}
    count, first = entries.get(b'N'), entries.get(b'First')
    if count is None or first is None or b'/FlateDecode' not in dictionary:
        return {}
    if b'/DecodeParms' in dictionary:
        return {}
    content = inflate_stream(data, stream_start, entries.get(b'Length'))
    if content is None:
        return {}
    header = content[:first].split()
    if len(header) < 2 * count or not all(token.isdigit() for token in header[: 2 * count]):
        return {}
    numbers = [int(token) for token in header[0 : 2 * count : 2]]
    offsets = [first + int(token) for token in header[1 : 2 * count : 2]]
    return {
        number: content[offset:end]
        for number, offset, end in zip(numbers, offsets, [*offsets[1:], len(content)], strict=True)
    }


def read_objects(data: bytes) -> dict[int, bytes]:
    """Return the dictionaries and values of a PDF's objects by number, without stream data.

    Later definitions replace earlier ones, as with incremental updates.
    """
    objects: dict[int, bytes] = {}
    for match in OBJECT_START_PATTERN.finditer(data):
        start = match.end()
        end = data.find(b'endobj', start)
        if end < 0:
            end = len(data)
        stream_match = STREAM_KEYWORD_PATTERN.search(data, start, end)
        body = data[start : stream_match.start() if stream_match else end]
        objects[int(match.group(1))] = body
        if stream_match and OBJECT_STREAM_PATTERN.search(body):
            objects.update(object_stream_objects(data, body, stream_match.end()))
    return objects


def parse_differences(array_text: bytes) -> dict[int, str]:
    """Return the glyph names that a `/Differences` array assigns to character codes."""
    names: dict[int, str] = {}
    code: int | None = None
    for number, name in DIFFERENCES_TOKEN_PATTERN.findall(array_text):
        if number:
            code = int(number)
        elif code is not None:
            names[code] = decode_name(name)
            code += 1
    return names


def font_differences(font: bytes, objects: dict[int, bytes]) -> dict[int, str]:
    """Return the `/Differences` of a font dictionary's encoding, if it has any."""
    encoding = font
    reference = ENCODING_REFERENCE_PATTERN.search(font)
    if reference:
        encoding = objects.get(int(reference.group(1)), b'')
    match = DIFFERENCES_PATTERN.search(encoding)
    if match is None:
        return {}
    if match.group(1) is not None:
        return parse_differences(match.group(1))
    array = ARRAY_PATTERN.match(objects.get(int(match.group(2)), b''))
    return parse_differences(array.group(1)) if array else {}


def read_font_differences(
    input_path: Path, wanted: Callable[[str], bool]
) -> dict[str, dict[int, str]]:
    """Return the `/Differences` of the fonts with wanted base names, by base name.

    Subsets of one font share its base name. Where they assign different
    glyphs to a code, the code is left out, as the glyph cannot be told.
    """
    try:
        data = input_path.read_bytes()
    except OSError:
        return {}
    objects = read_objects(data)
    names_by_font: dict[str, dict[int, str]] = {}
    conflicts: dict[str, set[int]] = {}
    for body in objects.values():
        match = BASE_FONT_PATTERN.search(body)
        if match is None:
            continue
        base_name = base_font_name(decode_name(match.group(1)))
        if not wanted(base_name):
            continue
        names = names_by_font.setdefault(base_name, {})
        for code, name in font_differences(body, objects).items():
            if names.setdefault(code, name) != name:
                conflicts.setdefault(base_name, set()).add(code)
    for base_name, codes in conflicts.items():
        for code in codes:
            del names_by_font[base_name][code]
    return names_by_font
