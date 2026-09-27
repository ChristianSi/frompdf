"""Recognize bottom notes from layout and collect them into endnote sections."""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from statistics import median

from frompdf.models import Block, Footnote, Heading, Line, NoteFragment, PageNumber
from frompdf.segmentation import close_font_size, ends_sentence
from frompdf.unhyphenation import unhyphenate_block_lines

# Require a visible size reduction and a lower-page region, with ordinary text
# above it. The position is relative to the occupied page, not rel_y (which is
# the advance from the preceding line). Long notes can occupy half a page.
NOTE_FONT_RATIO = 0.90
NOTE_MIN_PAGE_FRACTION = 0.45
NOTE_LABEL = re.compile(r'^\s*(\d+)[.)]?\s+(\S.*)$')


@dataclass
class DetectedNote:
    label: str
    paragraphs: list[list[Line]] = field(default_factory=list)
    end_index: int = 0


def horizontally_overlaps(left: Line, right: Line) -> bool:
    return (
        left.x1 is not None
        and left.x2 is not None
        and right.x1 is not None
        and right.x2 is not None
        and min(left.x2, right.x2) > max(left.x1, right.x1)
    )


def is_small_note_line(page: list[Line], index: int, body_size: float) -> bool:
    """Allow one slightly enlarged numbered line surrounded by smaller note text."""
    line = page[index]
    if line.font_size is None:
        return False
    if line.font_size <= body_size * NOTE_FONT_RATIO:
        return True
    # Mixed spans (notably superscripts) can inflate a line's reported size.
    # Do not let that one line split an otherwise consistent note area.
    return (
        line.font_size <= body_size * 0.95
        and NOTE_LABEL.match(line.text) is not None
        and 0 < index < len(page) - 1
        and all(
            neighbor.font_size is not None and neighbor.font_size <= body_size * NOTE_FONT_RATIO
            for neighbor in (page[index - 1], page[index + 1])
        )
    )


def introduced_by_heading(above: list[Line], first: Line, note_size: float) -> bool:
    """Protect lists introduced by a title, even if Markdown missed the heading."""
    title = above[-1]
    if len(title.text) > 100 or len(title.text.split()) > 10:
        return False
    if title.block_no == first.block_no or ends_sentence(title.text):
        return False
    heavier = (title.avg_weight or 0) > max((first.avg_weight or 0) * 1.2, 100)
    gap_before = (title.y1 or 0) - (above[-2].y2 or 0) if len(above) > 1 else 0
    gap_after = (first.y1 or 0) - (title.y2 or 0)
    return heavier or gap_before > max(gap_after * 1.25, note_size)


def is_note_region(page: list[Line], start: int, end: int, body_size: float) -> bool:
    """Require a separated small-text region below prose in the same column."""
    region = page[start:end]
    prose = [line for line in region if sum(c.isalpha() for c in line.text) >= 3]
    if not prose:
        return False
    first = region[0]
    reference = prose[0]
    bottom = max((line.y2 or 0) for line in page)
    if first.y1 is None or first.y1 < bottom * NOTE_MIN_PAGE_FRACTION:
        return False
    above = [
        line
        for line in page[:start]
        if line.y2 is not None
        and line.y2 <= first.y1
        and (line.font_size or 0) > body_size * NOTE_FONT_RATIO
        and horizontally_overlaps(line, reference)
        and sum(c.isalpha() for c in line.text) >= 3
    ]
    if len(above) < 2:
        return False
    above.sort(key=lambda line: line.y1 or 0)
    note_size = median(line.font_size for line in prose if line.font_size is not None)
    # A real gap helps distinguish notes from an inline list or a small-font quote.
    if first.y1 - (above[-1].y2 or 0) < note_size * 0.5:
        return False
    if introduced_by_heading(above, reference, note_size):
        return False
    return not any(
        not is_small_note_line(page, index, body_size)
        and line.y1 is not None
        and line.y1 > first.y1
        and horizontally_overlaps(line, reference)
        and sum(c.isalpha() for c in line.text) >= 12
        for index, line in enumerate(page[end:], start=end)
    )


def numbered_line(region: list[Line], index: int) -> tuple[str, Line, int] | None:
    """Read an attached label or reconnect a detached superscript beside prose."""
    line = region[index]
    match = NOTE_LABEL.match(line.text)
    if match and sum(c.isalpha() for c in match[2]) >= 3:
        if index:
            previous = region[index - 1]
            size = line.font_size or 10
            if (
                previous.block_no == line.block_no
                and not ends_sentence(previous.text)
                and abs((previous.x1 or 0) - (line.x1 or 0)) < size * 0.3
                and (line.y1 or 0) - (previous.y2 or 0) < size
            ):
                # A wrapped date or quantity within a paragraph is not a label.
                return None
        return match[1], replace(line, text=match[2]), 1
    if not line.text.strip().isdecimal() or index + 1 >= len(region):
        return None
    following = region[index + 1]
    size = following.font_size or 0
    if (
        line.x2 is not None
        and following.x1 is not None
        and line.y1 is not None
        and following.y1 is not None
        and 0 <= following.x1 - line.x2 <= size * 1.5
        and abs(following.y1 - line.y1) <= size * 0.6
        and sum(c.isalpha() for c in following.text) >= 12
    ):
        return line.text.strip(), following, 2
    return None


def continues_previous_note(note: DetectedNote, first: Line) -> bool:
    """Only attach an unnumbered prefix to an open note on the preceding page."""
    previous = note.paragraphs[-1][-1]
    return (
        previous.page_no + 1 == first.page_no
        and close_font_size(previous.font_size, first.font_size)
        and not ends_sentence(previous.text)
    )


def append_note_line(note: DetectedNote, line: Line, source_index: int) -> None:
    """Keep genuine paragraph indents, ignoring incidental PDF block boundaries."""
    previous = note.paragraphs[-1][-1]
    size = line.font_size or 10
    new_paragraph = (
        previous.page_no == line.page_no
        and previous.block_no != line.block_no
        and ends_sentence(previous.text)
        and (
            (line.x1 or 0) - (previous.x1 or 0) >= size * 0.55
            or (line.y1 or 0) - (previous.y2 or 0) >= size
        )
    )
    if new_paragraph:
        note.paragraphs.append([])
    note.paragraphs[-1].append(line)
    note.end_index = source_index


def extract_footnotes(
    lines: list[Line], body_size: float | None
) -> tuple[list[Line], list[DetectedNote]]:
    """Remove confidently numbered note areas, retaining their original positions."""
    if body_size is None:
        return lines, []
    pages: dict[int, list[tuple[int, Line]]] = defaultdict(list)
    for index, line in enumerate(lines):
        pages[line.page_no].append((index, line))
    notes: list[DetectedNote] = []
    removed: set[int] = set()
    for indexed_page in pages.values():
        page = [line for _, line in indexed_page]
        start = 0
        while start < len(page):
            if not is_small_note_line(page, start, body_size):
                start += 1
                continue
            end = start + 1
            while end < len(page) and is_small_note_line(page, end, body_size):
                end += 1
            if is_note_region(page, start, end, body_size):
                region = page[start:end]
                first_label = next(
                    (index for index in range(len(region)) if numbered_line(region, index)), None
                )
                if (
                    first_label is not None
                    and first_label > 0
                    and introduced_by_heading(
                        region[:first_label],
                        region[first_label],
                        region[first_label].font_size or body_size,
                    )
                ):
                    # A small-font title can be inside the candidate region.
                    start = end
                    continue
                current = (
                    notes[-1] if notes and continues_previous_note(notes[-1], region[0]) else None
                )
                offset = 0
                while offset < len(region):
                    numbered = numbered_line(region, offset)
                    source_index = indexed_page[start + offset][0]
                    consumed = 1
                    if numbered:
                        label, text_line, consumed = numbered
                        current = DetectedNote(label, [[text_line]], source_index + consumed - 1)
                        notes.append(current)
                    elif current is not None:
                        append_note_line(current, region[offset], source_index)
                    if current is not None:
                        removed.update(indexed_page[start + offset + n][0] for n in range(consumed))
                    offset += consumed
            start = end
    return [line for index, line in enumerate(lines) if index not in removed], notes


def build_footnote(
    note: DetectedNote,
    page_numbers: dict[int, PageNumber],
    word_counts: Counter[str],
    mixed_case_words: set[str],
    coordination_tokens: set[str],
) -> Footnote:
    """Repair note text, attributing joined words to the page where they start."""
    fragments: list[NoteFragment] = []
    for paragraph in note.paragraphs:
        page_lines: list[list[Line]] = []
        for line in paragraph:
            if not page_lines or page_lines[-1][-1].page_no != line.page_no:
                page_lines.append([])
            page_lines[-1].append(line)
        for index, lines in enumerate(page_lines):
            text = unhyphenate_block_lines(
                (line.text for line in lines),
                word_counts,
                mixed_case_words,
                coordination_tokens,
            )
            separator = ('\n\n' if fragments else '') if index == 0 else '\n'
            if index:
                previous = fragments[-1]
                left_line = previous.text.rsplit('\n', 1)[-1]
                right_line, line_break, remainder = text.partition('\n')
                repaired = unhyphenate_block_lines(
                    [left_line, right_line], word_counts, mixed_case_words, coordination_tokens
                )
                if repaired != left_line + '\n' + right_line:
                    # Keep the complete repaired word on its starting page. The
                    # next page marker belongs before the remaining text instead.
                    joined_line, _, right_remainder = repaired.partition('\n')
                    previous.text = previous.text[: -len(left_line)] + joined_line
                    text = right_remainder + (line_break if right_remainder else '') + remainder
                    if not text:
                        # If repair consumed the entire page fragment, defer the
                        # marker until another fragment or block has text to emit.
                        continue
            fragments.append(NoteFragment(text, page_numbers[lines[0].page_no], separator))
    return Footnote(
        text=''.join(fragment.separator + fragment.text for fragment in fragments),
        start_page=fragments[0].page,
        end_page=fragments[-1].page,
        font_size=note.paragraphs[0][0].font_size,
        label=note.label,
        fragments=fragments,
    )


def note_group_scope_level(blocks: list[Block], group: list[tuple[int, Footnote]]) -> int:
    """Find the shallowest section covered by a continuous numbering sequence."""
    first, last = group[0][0], group[-1][0]
    initial_level = next(
        (block.level for block in reversed(blocks[:first]) if isinstance(block, Heading)),
        2,
    )
    return min(
        [initial_level]
        + [block.level for block in blocks[first:last] if isinstance(block, Heading)]
    )


def note_group_destination(
    blocks: list[Block],
    group: list[tuple[int, Footnote]],
    next_note: tuple[int, Footnote] | None,
    scope_level: int,
) -> int:
    """Prefer a boundary at the group's scope without skipping a new note section."""
    first_index, first_note = group[0]
    last_index, last_note = group[-1]
    boundaries = [
        (index, block.level)
        for index, block in enumerate(blocks[last_index + 1 :], start=last_index + 1)
        if isinstance(block, Heading)
    ]
    # A heading between this group's last note and a restarted group's first
    # note is a closing opportunity. Do not skip it to reach a larger heading
    # after the new group has begun (which would accumulate adjacent Notes).
    before_restart = [item for item in boundaries if next_note and item[0] < next_note[0]]
    candidates = before_restart or boundaries
    destination = next(
        (index for index, level in candidates if level <= scope_level),
        candidates[0][0] if candidates else len(blocks),
    )
    # A numbering restart on this or the next page can belong to a heading
    # above the old group's final bottom notes. Do not move an isolated group
    # backwards on page coincidence alone, or before its own opening heading.
    last_page = last_note.end_page.raw
    if next_note is None or not last_page <= next_note[1].start_page.raw <= last_page + 1:
        return destination
    for index in range(last_index - 1, -1, -1):
        boundary = blocks[index]
        if not isinstance(boundary, Heading) or boundary.start_page.raw != last_page:
            continue
        if first_index < index:
            return index
        # Excerpts can start with continuing labels (for example 5–8) below a
        # mid-page heading, with the new section's 1–3 only on the next page.
        # Require prose before that heading on the same page as extra evidence.
        if int(first_note.label) > 1 and any(
            not isinstance(previous, Footnote | Heading) and previous.end_page.raw == last_page
            for previous in blocks[:index]
        ):
            return index
    return destination


def place_footnotes(blocks: list[Block], title: str = 'Notes') -> list[Block]:
    """Place numeric groups at section boundaries, sharing one title per boundary."""
    groups: list[list[tuple[int, Footnote]]] = []
    for index, block in enumerate(blocks):
        if not isinstance(block, Footnote):
            continue
        if not groups or int(block.label) <= int(groups[-1][-1][1].label):
            groups.append([])
        groups[-1].append((index, block))
    insertions: dict[int, list[Footnote]] = defaultdict(list)
    insertion_scopes: dict[int, int] = {}
    previous_destination = 0
    for index, group in enumerate(groups):
        next_note = groups[index + 1][0] if index + 1 < len(groups) else None
        scope_level = note_group_scope_level(blocks, group)
        # One uninterrupted sequence is document-wide endmatter, independent
        # of the size of the final body heading.
        destination = (
            len(blocks)
            if len(groups) == 1
            else note_group_destination(blocks, group, next_note, scope_level)
        )
        # Ambiguous same-page restarts must never reverse the source order of
        # note groups. Share a later boundary when their evidence conflicts.
        destination = max(previous_destination, destination)
        previous_destination = destination
        insertions[destination].extend(note for _, note in group)
        insertion_scopes[destination] = min(
            insertion_scopes.get(destination, scope_level), scope_level
        )
    default_level = 2 if len(insertions) == 1 else 3
    result: list[Block] = []
    for index in range(len(blocks) + 1):
        if notes := insertions.get(index):
            following = blocks[index] if index < len(blocks) else None
            level = default_level
            if isinstance(following, Heading):
                # Equal levels suffice to prevent the next section becoming a
                # child of Notes; do not force Notes into the last subsection.
                level = max(level, following.level)
            elif len(insertions) > 1:
                level = max(level, insertion_scopes[index])
            result.append(Heading(title, notes[0].start_page, notes[0].start_page, level=level))
            result.extend(notes)
        if index < len(blocks) and not isinstance(blocks[index], Footnote):
            result.append(blocks[index])
    return result
