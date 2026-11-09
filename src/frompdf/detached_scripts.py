from collections.abc import Sequence
from typing import Literal, cast

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

from frompdf.lines import (
    SCRIPT_MAX_SIZE_RATIO,
    STACKED_ALIGNMENT_TOLERANCE_EM,
    Box,
    dominant_font_size,
    glyph_font_size,
    positioned_box,
    positioned_char_box,
    script_kind,
    trailing_small_glyph_box,
    union_box,
    visible_chars,
)

# pdftext occasionally puts a script into a block of its own, which reading
# order then moves away from its line, as with the superscript `i` of `Fⁱ` in
# lipics-64. Such a script touches the end of the text it belongs to.
SCRIPT_ATTACHMENT_MAX_GAP_EM = 0.1

# TeX moves a superscript right of the subscript below it by the italic
# correction of their base, 0.07 em for the `C` of lipics-64's `C₀⁽ˢ,ᶠ⁾`.
STACKED_SCRIPT_MAX_ITALIC_CORRECTION_EM = 0.15


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
    takes the base from the end of the line before, if they touch. A line
    mostly in script size, as lipics-64's `⁽ˢ,ᶠ⁾∆ᴿ`, is measured against its
    largest glyphs, as the `∆` that the `R` is a script of.
    """
    chars = visible_chars(line_dict)
    font_size = dominant_font_size(line_dict)
    trailing = None if font_size is None else trailing_small_run(chars, font_size)
    if trailing is None:
        return None
    run, base_box = trailing
    sizes = [glyph_font_size(char) for char in chars]
    largest = max((size for size in sizes if size is not None), default=None)
    if not run and font_size is not None and largest is not None and largest > font_size:
        trailing = trailing_small_run(chars, largest)
        if trailing is None:
            return None
        font_size = largest
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


# Pieces of a denominator that pdftext splits into several records touch
# within this distance, relative to the size of the surrounding text, as the
# `s`, `2−f`, and `2` of lipics-64's `s/√(s²−f²)`.
DENOMINATOR_PIECE_MAX_GAP_EM = 0.1
RADICAL = '√'


def largest_glyph_size(line_dict: PdfTextLine) -> float | None:
    """Return the size of the largest visible glyph of a line, if known."""
    sizes = [glyph_font_size(char) for char in visible_chars(line_dict)]
    return max((size for size in sizes if size is not None), default=None)


def stacked_denominator_pieces(
    ordered: Sequence[PdfTextLine], index: int
) -> tuple[list[int], PdfTextSpan | None] | None:
    """Return the indexes of records forming a denominator after a numerator, and its radical.

    The record at index ends with a numerator in glyphs that are small next
    to its largest ones. At least two following records of small glyphs touch
    each other below it, followed by another record. A radical before the
    numerator belongs to the denominator if it reaches down beside it.
    Together they must be centered below the numerator.
    """
    numerator = ordered[index]
    font_size = largest_glyph_size(numerator)
    if font_size is None or font_size <= 0:
        return None
    end = index + 1
    while end < len(ordered):
        size = largest_glyph_size(ordered[end])
        if size is None or size > font_size * SCRIPT_MAX_SIZE_RATIO:
            break
        end += 1
    if end - index - 1 < 2 or end >= len(ordered):
        return None
    piece_boxes = [positioned_box(ordered[piece]) for piece in range(index + 1, end)]
    numerator_box = trailing_small_glyph_box(numerator, font_size)
    if numerator_box is None or any(box is None for box in piece_boxes):
        return None
    boxes = [box for box in piece_boxes if box is not None]
    if any(
        abs(right[0] - left[2]) > font_size * DENOMINATOR_PIECE_MAX_GAP_EM
        for left, right in zip(boxes, boxes[1:], strict=False)
    ):
        return None
    denominator_box = union_box(boxes)
    tolerance = font_size * STACKED_ALIGNMENT_TOLERANCE_EM
    if numerator_box[3] > denominator_box[1] + tolerance:
        return None

    radical = numerator_radical(numerator, font_size)
    radical_box = positioned_box(radical) if radical is not None else None
    if radical_box is not None and (
        radical_box[3] < denominator_box[3] - tolerance
        or radical_box[2] > denominator_box[0] + tolerance
    ):
        radical, radical_box = None, None
    if radical_box is not None:
        denominator_box = union_box([radical_box, denominator_box])
    numerator_center = (numerator_box[0] + numerator_box[2]) / 2
    if abs(numerator_center - (denominator_box[0] + denominator_box[2]) / 2) > tolerance:
        return None
    return list(range(index + 1, end)), radical


def numerator_radical(numerator: PdfTextLine, font_size: float) -> PdfTextSpan | None:
    """Return the span of a radical sign right before the small glyphs ending a line, if any."""
    spans = [span for span in numerator.get('spans', []) if span.get('text', '').strip()]
    small = 0
    while small < len(spans) and all(
        (glyph_font_size(char) or font_size) <= font_size * SCRIPT_MAX_SIZE_RATIO
        for char in spans[len(spans) - 1 - small].get('chars', [])
        if char.get('char', '').strip()
    ):
        small += 1
    if not small or small == len(spans):
        return None
    candidate = spans[len(spans) - 1 - small]
    return candidate if candidate.get('text', '').strip() == RADICAL else None


def merge_split_denominators(page_list: Sequence[Page]) -> None:
    """Merge the pieces of a denominator that pdftext splits into several records, in place.

    A radical reaching down beside the denominator moves from the numerator's
    record to the start of the denominator.
    """
    for page_dict in page_list:
        index = 0
        while True:
            ordered = [
                (block, line)
                for block in page_dict.get('blocks', [])
                for line in block.get('lines', [])
            ]
            if index >= len(ordered):
                break
            found = stacked_denominator_pieces([line for _, line in ordered], index)
            if found is None:
                index += 1
                continue
            pieces, radical = found
            numerator = ordered[index][1]
            first = ordered[pieces[0]][1]
            if radical is not None:
                spans = numerator.get('spans', [])
                position = next(i for i, span in enumerate(spans) if span is radical)
                following = spans[position + 1 : position + 2]
                removed = 2 if following and not following[0].get('text', '').strip() else 1
                numerator['spans'] = spans[:position] + spans[position + removed :]
                first['spans'] = [radical, *first.get('spans', [])]
                for line in (numerator, first):
                    boxes = [box for box in map(positioned_char_box, visible_chars(line)) if box]
                    if boxes:
                        line['bbox'] = cast(Bbox, list(union_box(boxes)))
            for piece in pieces[1:]:
                block, line = ordered[piece]
                append_spans(first, line.get('spans', []))
                block['lines'] = [other for other in block['lines'] if other is not line]
            index += 1
