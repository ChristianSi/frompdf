"""Recognize bottom notes from layout and place them after the text they annotate.

Notes numbered through a section are collected into a Notes section at its
end. Notes numbered anew on each page, or marked by symbols such as `*` and
`†`, are placed after the last paragraph starting on their page, introduced
by a `Notes:` paragraph.

On scanned pages, measured sizes can miss the smaller size of notes, and
OCR misreads the superscript numbers and symbols labeling them. There, lines
below a printed rule or set more closely than body text count as small, too,
and notes are told apart by a hanging indent and by what OCR makes of labels.
"""

import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass, field, replace
from itertools import pairwise
from statistics import median

from frompdf.continuations import build_page_fragments, join_fragments
from frompdf.line_features import close_font_size, ends_sentence
from frompdf.models import Block, Footnote, Heading, Line, PageNumber, Paragraph, TextFragment
from frompdf.rules import Rule
from frompdf.scripts import AnnotatedText

# Require a visible size reduction and a lower-page region, with ordinary text
# above it. The position is relative to the occupied page, not rel_y (which is
# the advance from the preceding line). Long notes can occupy half a page.
NOTE_FONT_RATIO = 0.90
NOTE_MIN_PAGE_FRACTION = 0.45
NOTE_LABEL = re.compile(r'^\s*(\d+)[.)]?\s+(\S.*)$')
# Symbols marking notes, in the order of their use on a page. They are only
# taken for labels on scans: born-digital PDFs may map icons such as `✉`,
# marking an author's address, to `*`.
NOTE_SYMBOLS = '*†‡§‖¶'

# A page's body size is that of the document, unless text in that size makes
# up less than the first share of the text on the page and its neighbors, as
# where an introduction is set in another size than the main text. Then it is
# the largest size making up at least the second share there, rather than
# that of notes taking up more room, given they hold at least the third many
# characters.
MIN_BODY_SIZE_SHARE = 0.1
MIN_PART_BODY_SIZE_SHARE = 0.3
MIN_BODY_SIZE_CHARS = 500

# On scans, the measured size of notes can be that of body text, as for
# short lines mostly in capitals. Lines are small, too, where at least the
# second many in a row are set at most the first share of the distance
# between the lines of body text apart, or less than that distance from a
# line measured small. That is the median of at least the third many
# distances on the page. Single distances vary with the measured baselines
# of the scan.
NOTE_PITCH_RATIO = 0.85
MIN_CLOSE_LINES = 3
MIN_PITCH_SAMPLES = 3
# OCR reads the superscript labels of notes as other characters, or joins
# them to the following word. A line may start a note where it begins with a
# number joined to a capitalized word, or with one or two marks, or `i`,
# `I`, `l` or `|` misread for `1`, before one.
OCR_LABEL_PREFIX = re.compile(
    r'^\s*(?:(\d{1,2})\s*(?=[A-Z‘“(])|[^\w\s]{1,2}(?=[A-Z])|[iIl|](?=[A-Z]))'
)
# A note marked by a symbol starts with it as a word of its own. OCR reads
# the daggers following `*` on a page as these characters.
OCR_NOTE_MARK = re.compile(r'^\s*(\S{1,2})\s+(\S.*)$')
OCR_DAGGER_READINGS = frozenset({'t', 'f', '+', 'X', '|'})
# Lines starting notes with a hanging indent lie at least this many ems left
# of their continuation lines.
MIN_HANGING_INDENT = 0.2


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
        # Consume the label's annotation along with its text. Remaining scripts
        # in the note body retain their positions after this slice.
        annotated = AnnotatedText(line.text, line.ranges).slice(match.start(2))
        return match[1], replace(line, text=annotated.text, ranges=annotated.ranges), 1
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


def without_label(line: Line, start: int) -> Line:
    """Return a line without the label preceding the given offset of its text."""
    annotated = AnnotatedText(line.text, line.ranges).slice(start)
    return replace(line, text=annotated.text, ranges=annotated.ranges)


def label_rank(label: str) -> int:
    """Return the position of a note label in its sequence, counting from 1.

    Symbols follow the order of NOTE_SYMBOLS, then repeat doubled.
    """
    if label.isdecimal():
        return int(label)
    return NOTE_SYMBOLS.index(label[0]) + 1 + len(NOTE_SYMBOLS) * (len(label) - 1)


def is_symbol_label(label: str) -> bool:
    return not label.isdecimal()


def page_body_sizes(pages: Mapping[int, Sequence[Line]], body_size: float) -> dict[int, float]:
    """Return the body size of each page, which can differ by part of the document."""
    weights: dict[int, Counter[float]] = defaultdict(Counter)
    for page_no, page in pages.items():
        for line in page:
            if line.font_size is not None:
                weights[page_no][line.font_size] += len(line.text)
    sizes: dict[int, float] = {}
    for page_no in pages:
        window: Counter[float] = Counter()
        for neighbor in (page_no - 1, page_no, page_no + 1):
            window.update(weights.get(neighbor, Counter()))
        total = window.total()
        in_body_size = sum(
            weight for size, weight in window.items() if close_font_size(size, body_size)
        )
        if total < MIN_BODY_SIZE_CHARS or in_body_size >= total * MIN_BODY_SIZE_SHARE:
            sizes[page_no] = body_size
        else:
            sizes[page_no] = max(
                (
                    size
                    for size, weight in window.items()
                    if weight >= total * MIN_PART_BODY_SIZE_SHARE
                ),
                default=max(window.items(), key=lambda item: (item[1], item[0]))[0],
            )
    return sizes


def body_line_pitch(page: Sequence[Line], body_size: float) -> float | None:
    """Return the usual distance between successive lines of body text on a page."""
    distances = [
        below.y2 - above.y2
        for above, below in pairwise(page)
        if above.y2 is not None
        and below.y2 is not None
        and close_font_size(above.font_size, body_size)
        and close_font_size(below.font_size, body_size)
        and horizontally_overlaps(above, below)
        and 0 < below.y2 - above.y2 < 2 * body_size
    ]
    return median(distances) if len(distances) >= MIN_PITCH_SAMPLES else None


def starts_like_note(line: Line) -> bool:
    """Return whether the text of a scanned line begins with what may be a note label."""
    mark = OCR_NOTE_MARK.match(line.text)
    return (
        NOTE_LABEL.match(line.text) is not None
        or OCR_LABEL_PREFIX.match(line.text) is not None
        or (mark is not None and any(char in NOTE_SYMBOLS for char in mark[1]))
    )


def scan_note_sizes(page: list[Line], body_size: float, rules: Sequence[Rule]) -> list[Line]:
    """Return the lines of a scanned page, reduced in size where its layout shows notes.

    Runs of lines set more closely than body text are given the size their
    distances tell. Lines below a rule printed in the lower part of the page, starting
    with what may be a note label, are given the largest size of notes.
    """
    sizes = [line.font_size for line in page]
    pitch = body_line_pitch(page, body_size)
    if pitch is not None:
        # Runs of closely set lines, as their first index and their distances.
        runs: list[tuple[int, list[float]]] = []
        small = body_size * NOTE_FONT_RATIO
        for index, (above, below) in enumerate(pairwise(page)):
            distance = (below.y2 or 0) - (above.y2 or 0)
            measured_small = any(
                line.font_size is not None and line.font_size <= small for line in (above, below)
            )
            if not (
                above.y2 is not None
                and below.y2 is not None
                and horizontally_overlaps(above, below)
                and 0 < distance < pitch
                and (distance <= pitch * NOTE_PITCH_RATIO or measured_small)
            ):
                continue
            if runs and runs[-1][0] + len(runs[-1][1]) == index:
                runs[-1][1].append(distance)
            else:
                runs.append((index, [distance]))
        for first, distances in runs:
            if len(distances) + 1 < MIN_CLOSE_LINES:
                continue
            reduced = min(body_size * median(distances) / pitch, small)
            for index in range(first, first + len(distances) + 1):
                size = sizes[index]
                if size is not None:
                    sizes[index] = min(size, reduced)
    bottom = max((line.y2 or 0) for line in page)
    below_rule = [
        [index for index, line in enumerate(page) if (line.y1 or 0) >= rule.position]
        for rule in rules
        if rule.horizontal and rule.position >= bottom * NOTE_MIN_PAGE_FRACTION
    ]
    # The rule nearest to the notes separates them, rather than one above
    # some last body text.
    lowest = min((indices for indices in below_rule if indices), key=len, default=[])
    if lowest and starts_like_note(page[lowest[0]]):
        for index in lowest:
            size = sizes[index]
            if size is not None:
                sizes[index] = min(size, body_size * NOTE_FONT_RATIO)
    return [
        line if size == line.font_size else replace(line, font_size=size)
        for line, size in zip(page, sizes, strict=True)
    ]


def note_starts(region: list[Line]) -> dict[int, tuple[str, Line, int]]:
    """Return the lines of a note region starting notes, by index.

    Each comes with its label, its text without the label, and the number of
    lines it consumes, which is 2 for a detached label.
    """
    starts: dict[int, tuple[str, Line, int]] = {}
    index = 0
    while index < len(region):
        numbered = numbered_line(region, index)
        if numbered:
            starts[index] = numbered
            index += numbered[2]
        else:
            index += 1
    return starts


def hanging_note_starts(region: list[Line]) -> set[int]:
    """Return the lines of a scanned note region that a hanging indent shows to start notes.

    The lines set furthest left start notes where continuation lines are
    indented, given most of them begin like labels. A single first line
    left of all others starts a note by its position alone.
    """
    if any(line.x1 is None for line in region):
        return set()
    sizes = [line.font_size for line in region if line.font_size]
    em = median(sizes) if sizes else 10.0
    left = min(line.x1 or 0 for line in region)
    offsets = sorted((line.x1 or 0) - left for line in region)
    limit = next(
        (lower for lower, upper in pairwise(offsets) if upper - lower >= MIN_HANGING_INDENT * em),
        None,
    )
    if limit is None:
        return set()
    flush = [index for index, line in enumerate(region) if (line.x1 or 0) - left <= limit]
    labeled = sum(OCR_LABEL_PREFIX.match(region[index].text) is not None for index in flush)
    if labeled * 2 >= len(flush) or (flush == [0] and len(region) > 2):
        return set(flush)
    return set()


def sequence_labels(found: list[str | None], symbols: bool) -> list[str]:
    """Number the notes of a scanned region in order, as OCR misreads their labels.

    Numbers continue from the first one that most labels read as numbers agree
    on, or from 1.
    """
    if symbols:
        count = len(NOTE_SYMBOLS)
        return [NOTE_SYMBOLS[index % count] * (index // count + 1) for index in range(len(found))]
    firsts = Counter(
        int(label) - index for index, label in enumerate(found) if label and label.isdecimal()
    )
    first = max(firsts.most_common(1)[0][0], 1) if firsts else 1
    return [str(first + index) for index in range(len(found))]


def scan_note_starts(region: list[Line]) -> dict[int, tuple[str, Line, int]]:
    """Return the lines of a scanned note region starting notes, like note_starts.

    Besides labels read correctly, a line starts a note where it begins with
    a symbol or a misreading of a dagger after one, where it begins like a
    label after a sentence ends, or where a hanging indent shows it. Labels
    are numbered or marked in order, as OCR misreads many of them.
    """
    hanging = hanging_note_starts(region)
    found: dict[int, tuple[str | None, Line, int]] = {}
    symbols = False
    index = 0
    while index < len(region):
        line = region[index]
        numbered = numbered_line(region, index)
        mark = OCR_NOTE_MARK.match(line.text)
        prefix = OCR_LABEL_PREFIX.match(line.text)
        if numbered:
            found[index] = numbered
            index += numbered[2]
            continue
        if mark and (
            any(char in NOTE_SYMBOLS for char in mark[1])
            or (symbols and mark[1] in OCR_DAGGER_READINGS)
        ):
            found[index] = (None, without_label(line, mark.start(2)), 1)
            symbols = True
        elif prefix and (index in hanging or index == 0 or ends_sentence(region[index - 1].text)):
            found[index] = (prefix[1], without_label(line, prefix.end()), 1)
        elif index in hanging:
            found[index] = (None, line, 1)
        index += 1
    labels = sequence_labels([label for label, _, _ in found.values()], symbols)
    return {
        index: (label, line, consumed)
        for label, (index, (_, line, consumed)) in zip(labels, found.items(), strict=True)
    }


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
    lines: list[Line],
    body_size: float | None,
    scanned_pages: Set[int] = frozenset(),
    scan_rules: Mapping[int, Sequence[Rule]] | None = None,
) -> tuple[list[Line], list[DetectedNote]]:
    """Remove confidently labeled note areas, retaining their original positions.

    scanned_pages are the pages with OCR text, and scan_rules the rules printed
    on them, which tell notes apart where sizes and labels do not.
    """
    if body_size is None:
        return lines, []
    pages: dict[int, list[tuple[int, Line]]] = defaultdict(list)
    for index, line in enumerate(lines):
        pages[line.page_no].append((index, line))
    body_sizes = page_body_sizes(
        {page_no: [line for _, line in indexed] for page_no, indexed in pages.items()}, body_size
    )
    notes: list[DetectedNote] = []
    removed: set[int] = set()
    for page_no, indexed_page in pages.items():
        page_body_size = body_sizes[page_no]
        page = [line for _, line in indexed_page]
        scanned = page_no in scanned_pages
        if scanned:
            page = scan_note_sizes(page, page_body_size, (scan_rules or {}).get(page_no, ()))
        start = 0
        while start < len(page):
            if not is_small_note_line(page, start, page_body_size):
                start += 1
                continue
            end = start + 1
            while end < len(page) and is_small_note_line(page, end, page_body_size):
                end += 1
            if is_note_region(page, start, end, page_body_size):
                region = page[start:end]
                starts = scan_note_starts(region) if scanned else note_starts(region)
                first_label = min(starts, default=None)
                if (
                    first_label is not None
                    and first_label > 0
                    and introduced_by_heading(
                        region[:first_label],
                        region[first_label],
                        region[first_label].font_size or page_body_size,
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
                    source_index = indexed_page[start + offset][0]
                    consumed = 1
                    if offset in starts:
                        label, text_line, consumed = starts[offset]
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
    fragments: list[TextFragment] = []
    for paragraph in note.paragraphs:
        paragraph_fragments = build_page_fragments(
            paragraph, page_numbers, word_counts, mixed_case_words, coordination_tokens
        )
        if fragments:
            paragraph_fragments[0].separator = '\n\n'
        fragments.extend(paragraph_fragments)
    complete = join_fragments(fragments)
    return Footnote(
        text=complete.text,
        ranges=complete.ranges,
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


def is_page_confined(group: list[tuple[int, Footnote]]) -> bool:
    """Return whether all notes of a group start on the same page."""
    return len({note.start_page.raw for _, note in group}) == 1


def page_local_groups(blocks: list[Block], groups: list[list[tuple[int, Footnote]]]) -> set[int]:
    """Return the groups of notes labeled anew on each page, by index.

    Notes marked by symbols always are. Numbered notes are where two groups
    on different pages, both starting at 1, follow each other without a
    heading between them, as a new section would number its notes anew. Then
    all groups of a single page starting at 1 are.
    """
    local = {index for index, group in enumerate(groups) if is_symbol_label(group[0][1].label)}
    numbered = [
        index
        for index, group in enumerate(groups)
        if index not in local and group[0][1].label == '1' and is_page_confined(group)
    ]
    restarting_pages = any(
        following == index + 1
        and groups[index][0][1].start_page.raw < groups[following][0][1].start_page.raw
        and not any(
            isinstance(block, Heading)
            for block in blocks[groups[index][-1][0] + 1 : groups[following][0][0]]
        )
        for index, following in pairwise(numbered)
    )
    return local | set(numbered) if restarting_pages else local


def page_notes_destination(blocks: list[Block], group: list[tuple[int, Footnote]]) -> int:
    """Return where notes of a page follow the last paragraph starting on it.

    That is before headings ending the page, whose text follows on the next.
    """
    page = group[0][1].start_page.raw
    destination = next(
        (
            index + 1
            for index in range(len(blocks) - 1, -1, -1)
            if not isinstance(blocks[index], Footnote) and blocks[index].start_page.raw <= page
        ),
        0,
    )
    while destination > 1 and isinstance(blocks[destination - 1], Heading):
        destination -= 1
    return destination


def place_footnotes(blocks: list[Block], title: str = 'Notes') -> list[Block]:
    """Place notes after the text they annotate, sharing one title per position.

    Notes labeled anew on each page follow the last paragraph starting on
    their page, after a paragraph of the title and a colon. Other groups are
    placed at section boundaries, under a heading of the title.
    """
    groups: list[list[tuple[int, Footnote]]] = []
    for index, block in enumerate(blocks):
        if not isinstance(block, Footnote):
            continue
        if (
            not groups
            or is_symbol_label(block.label) != is_symbol_label(groups[-1][-1][1].label)
            or label_rank(block.label) <= label_rank(groups[-1][-1][1].label)
        ):
            groups.append([])
        groups[-1].append((index, block))
    local = page_local_groups(blocks, groups)
    page_insertions: dict[int, list[Footnote]] = defaultdict(list)
    for index in sorted(local):
        page_insertions[page_notes_destination(blocks, groups[index])].extend(
            note for _, note in groups[index]
        )
    groups = [group for index, group in enumerate(groups) if index not in local]
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
        if notes := page_insertions.get(index):
            result.append(Paragraph(f'{title}:', notes[0].start_page, notes[0].start_page))
            result.extend(notes)
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
