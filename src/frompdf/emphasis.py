"""Resolve bold and italic ranges into Markdown emphasis that renders as intended.

CommonMark only lets an emphasis delimiter open or close where its neighboring
characters allow it, and partly overlapping ranges cannot be nested. Ranges
are therefore adjusted in plain text, before escaping, so the delimiters that
serialization inserts are always valid.
"""

import string
from collections import defaultdict
from collections.abc import Iterable, Mapping
from unicodedata import category

from frompdf.models import HARD_LINE_BREAK, InlineKind, InlineRange
from frompdf.scripts import AnnotatedText, merged_script_runs, render_script

DELIMITERS = {'bold': '**', 'italic': '*'}

ASCII_PUNCTUATION = frozenset(string.punctuation)


def is_whitespace(char: str) -> bool:
    """Return whether CommonMark treats a character as whitespace."""
    return char in '\t\n\f\r' or category(char) == 'Zs'


def is_punctuation(char: str) -> bool:
    """Return whether every CommonMark version treats a character as punctuation."""
    return char in ASCII_PUNCTUATION or category(char).startswith('P')


def may_be_punctuation(char: str) -> bool:
    """Return whether some CommonMark version treats a character as punctuation.

    CommonMark 0.31 added symbols, such as `€`, which earlier versions treat
    like letters. Delimiters must be valid either way.
    """
    return is_punctuation(char) or category(char).startswith('S')


class RenderedText:
    """The characters that serialization renders around positions in plain text.

    markers are the positions of inserted text, such as page markers, which
    starts with `[` and ends with `]`.
    """

    def __init__(self, value: AnnotatedText, markers: Iterable[int] = ()) -> None:
        self.text = value.text
        self.markers = frozenset(markers)
        self.scripts = merged_script_runs(value.ranges)
        self.script_at = {index: run for run in self.scripts for index in range(run.start, run.end)}

    def char_before(self, index: int) -> str:
        """Return the rendered character ending just before a position.

        Text edges act as whitespace, as at line starts. Markers end in `]`,
        scripts in `>`, and deliberate line breaks become backslashes.
        """
        if index in self.markers:
            return ']'
        if index <= 0:
            return ' '
        if index - 1 in self.script_at:
            return '>'
        char = self.text[index - 1]
        return '\\' if char == HARD_LINE_BREAK else char

    def char_after(self, index: int) -> str:
        """Return the rendered character starting at a position.

        Closing delimiters precede markers, which start with `[`, and scripts,
        which start with `<`.
        """
        if index in self.markers:
            return '['
        if index >= len(self.text):
            return ' '
        if index in self.script_at:
            return '<'
        char = self.text[index]
        return '\\' if char == HARD_LINE_BREAK else char

    def can_open(self, index: int) -> bool:
        """Return whether a delimiter inserted at a position is left-flanking."""
        following = self.char_after(index)
        preceding = self.char_before(index)
        return not is_whitespace(following) and (
            not may_be_punctuation(following)
            or is_whitespace(preceding)
            or is_punctuation(preceding)
        )

    def can_close(self, index: int) -> bool:
        """Return whether a delimiter inserted at a position is right-flanking."""
        preceding = self.char_before(index)
        following = self.char_after(index)
        return not is_whitespace(preceding) and (
            not may_be_punctuation(preceding)
            or is_whitespace(following)
            or is_punctuation(following)
        )

    def may_close(self, index: int) -> bool:
        """Return whether a delimiter inserted at a position is right-flanking in some version."""
        preceding = self.char_before(index)
        following = self.char_after(index)
        return not is_whitespace(preceding) and (
            not is_punctuation(preceding)
            or is_whitespace(following)
            or may_be_punctuation(following)
        )

    def trimmed(self, start: int, end: int, kind: InlineKind) -> InlineRange | None:
        """Return a range without whitespace at its edges or partly covered scripts."""
        for run in self.scripts:
            if run.start < start < run.end:
                start = run.end
            if run.start < end < run.end:
                end = run.start
        while start < end and self.text[start].isspace():
            start += 1
        while end > start and self.text[end - 1].isspace():
            end -= 1
        return InlineRange(start, end, kind) if start < end else None

    def flanking(self, run: InlineRange) -> InlineRange | None:
        """Move punctuation, symbols, or scripts at range edges outside where delimiters fail.

        A delimiter next to a letter cannot open before or close after
        punctuation, such as in `*word.*next`, nor next to a script tag.
        """
        current = self.trimmed(run.start, run.end, run.kind)
        while current is not None:
            start, end = current.start, current.end
            if not self.can_open(start):
                script = self.script_at.get(start)
                start = script.end if script else start + 1
            elif not self.can_close(end):
                script = self.script_at.get(end - 1)
                end = script.start if script else end - 1
            else:
                return current
            current = self.trimmed(start, end, run.kind)
        return None


def merged_emphasis(text: str, runs: Iterable[InlineRange]) -> list[InlineRange]:
    """Merge ranges of the same kind that overlap or are separated only by whitespace."""
    merged: list[InlineRange] = []
    for run in sorted(runs, key=lambda run: (run.kind, run.start)):
        previous = merged[-1] if merged else None
        if previous and previous.kind == run.kind and not text[previous.end : run.start].strip():
            merged[-1] = InlineRange(previous.start, max(previous.end, run.end), run.kind)
        else:
            merged.append(run)
    return merged


def cut_emphasis(runs: list[InlineRange], cuts: Iterable[tuple[int, int]]) -> list[InlineRange]:
    """Remove cut spans from ranges, splitting ranges at empty cuts within them."""
    for cut_start, cut_end in cuts:
        pieces: list[InlineRange] = []
        for run in runs:
            if run.start < cut_end and cut_start < run.end or run.start < cut_start < run.end:
                if run.start < cut_start:
                    pieces.append(InlineRange(run.start, cut_start, run.kind))
                if cut_end < run.end:
                    pieces.append(InlineRange(cut_end, run.end, run.kind))
            else:
                pieces.append(run)
        runs = pieces
    return runs


def without_partial_overlaps(rendered: RenderedText, runs: list[InlineRange]) -> list[InlineRange]:
    """Remove the overlap of partly overlapping ranges from the shorter one.

    Such ranges, as in a bold italic word between italic and bold text, cannot
    be nested, and every way of splitting them yields adjacent delimiters that
    render wrongly.
    """
    runs = list(runs)
    while True:
        overlap = next(
            (
                (first, second)
                for first in runs
                for second in runs
                if first.start < second.start < first.end < second.end
            ),
            None,
        )
        if overlap is None:
            return runs
        first, second = overlap
        runs.remove(first)
        runs.remove(second)
        if first.end - first.start <= second.end - second.start:
            first, second = rendered.trimmed(first.start, second.start, first.kind), second
        else:
            first, second = first, rendered.trimmed(first.end, second.end, second.kind)
        runs.extend(run for run in (first, second) if run is not None)


def delimiter_run_length(runs: Iterable[InlineRange], position: int) -> int:
    """Return the number of delimiters that serialization inserts at a position."""
    return sum(
        len(DELIMITERS[run.kind]) * ((run.start == position) + (run.end == position))
        for run in runs
    )


def without_ambiguous_openers(
    rendered: RenderedText, runs: list[InlineRange], strong: bool = False
) -> list[InlineRange]:
    """Adjust ranges whose opening delimiter could close the emphasis around it instead.

    An opening delimiter between two letters, as in `a*b`, or two punctuation
    characters can also close. CommonMark's rule of 3 keeps it from closing an
    enclosing range of the other kind, unless that range opens with a run of
    three delimiters, as after `*a***b` or in `***a*`. Punctuation then moves
    outside the inner range; otherwise, the inner range is dropped. With
    strong, the whole text is enclosed in strong emphasis.
    """
    runs = list(runs)
    while True:
        enclosing = [InlineRange(0, len(rendered.text), 'bold')] if strong else []
        ambiguous = next(
            (
                run
                for run in runs
                if rendered.may_close(run.start)
                and any(
                    outer.start < run.start < outer.end
                    and delimiter_run_length(runs + enclosing, outer.start) == 3
                    for outer in runs + enclosing
                )
            ),
            None,
        )
        if ambiguous is None:
            return runs
        runs.remove(ambiguous)
        if may_be_punctuation(rendered.char_after(ambiguous.start)):
            script = rendered.script_at.get(ambiguous.start)
            start = script.end if script else ambiguous.start + 1
            moved = rendered.trimmed(start, ambiguous.end, ambiguous.kind)
            moved = rendered.flanking(moved) if moved else None
            if moved is not None:
                runs.append(moved)


def covers_all_text(rendered: RenderedText, runs: Iterable[InlineRange]) -> bool:
    """Return whether ranges cover every letter and digit outside scripts."""
    covered = {index for run in runs for index in range(run.start, run.end)}
    return all(
        index in covered or index in rendered.script_at or not char.isalnum()
        for index, char in enumerate(rendered.text)
    )


def resolve_emphasis(
    value: AnnotatedText,
    markers: Iterable[int] = (),
    display: bool = False,
    strong: bool = False,
) -> AnnotatedText:
    """Return text whose bold and italic ranges render as valid, nested Markdown emphasis.

    Emphasis is split at markers, the positions of inserted text such as page markers, which
    starts with `[` and ends with `]`. Display blocks, such as headings,
    already stand out: they lose bold ranges, and italic ones if they cover all
    of their text. With strong, the whole text is rendered in strong emphasis.
    """
    markers = frozenset(markers)
    rendered = RenderedText(value, markers)
    runs = [run for run in value.ranges if not run.is_script]
    if display:
        runs = [run for run in runs if run.kind == 'italic']
        if covers_all_text(rendered, runs):
            runs = []
    runs = cut_emphasis(merged_emphasis(value.text, runs), ((marker, marker) for marker in markers))
    trimmed = (rendered.trimmed(run.start, run.end, run.kind) for run in runs)
    runs = without_partial_overlaps(rendered, [run for run in trimmed if run is not None])
    flanking = (rendered.flanking(run) for run in runs)
    emphasis = without_ambiguous_openers(
        rendered, [run for run in flanking if run is not None], strong
    )
    emphasis.sort(key=lambda run: run.start)
    return AnnotatedText(
        value.text, tuple(run for run in value.ranges if run.is_script) + tuple(emphasis)
    )


def render_inline(value: AnnotatedText, inserts: Mapping[int, str] | None = None) -> str:
    """Render scripts as inline HTML and emphasis with delimiters, adding inserted text.

    Emphasis ranges must be nested and must not partly cover scripts, as
    resolve_emphasis returns them. Inserted text, such as a page marker,
    follows the closing and precedes the opening delimiters at its position.
    """
    inserts = inserts or {}
    text = value.text
    scripts = merged_script_runs(value.ranges)
    script_at = {index: run for run in scripts for index in range(run.start, run.end)}
    openings: dict[int, list[InlineRange]] = defaultdict(list)
    closings: dict[int, list[InlineRange]] = defaultdict(list)
    for run in value.ranges:
        if not run.is_script:
            openings[run.start].append(run)
            closings[run.end].append(run)
    positions = sorted(
        {0, len(text), *inserts, *openings, *closings}
        | {position for run in scripts for position in (run.start, run.end)}
    )
    parts: list[str] = []
    for index, position in enumerate(positions):
        # Close inner ranges first and open outer ones first. Of ranges with
        # the same extent, italic is the inner one.
        for run in sorted(closings[position], key=lambda run: (-run.start, run.kind == 'bold')):
            parts.append(DELIMITERS[run.kind])
        parts.append(inserts.get(position, ''))
        for run in sorted(openings[position], key=lambda run: (-run.end, run.kind != 'bold')):
            parts.append(DELIMITERS[run.kind])
        if index + 1 < len(positions):
            segment = text[position : positions[index + 1]]
            script = script_at.get(position)
            parts.append(render_script(segment, script.kind) if script else segment)
    return ''.join(parts)
