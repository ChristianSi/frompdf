"""Keep inline ranges, such as scripts and emphasis, in plain text until Markdown serialization."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from html import escape

from frompdf.models import InlineRange


@dataclass(frozen=True)
class AnnotatedText:
    text: str
    ranges: tuple[InlineRange, ...] = ()

    def slice(self, start: int = 0, end: int | None = None) -> 'AnnotatedText':
        """Slice text and clip/shift its annotations using ordinary string indices."""
        start, end, _ = slice(start, end).indices(len(self.text))
        return AnnotatedText(
            self.text[start:end],
            tuple(
                InlineRange(max(run.start, start) - start, min(run.end, end) - start, run.kind)
                for run in self.ranges
                if run.start < end and run.end > start
            ),
        )

    def __add__(self, other: 'AnnotatedText') -> 'AnnotatedText':
        offset = len(self.text)
        return AnnotatedText(
            self.text + other.text,
            self.ranges
            + tuple(InlineRange(r.start + offset, r.end + offset, r.kind) for r in other.ranges),
        )


def join_annotated_texts(parts: Iterable[AnnotatedText], separator: str = '') -> AnnotatedText:
    """Join text pieces without changing which characters carry annotations."""
    texts: list[str] = []
    runs: list[InlineRange] = []
    offset = 0
    for part in parts:
        if texts:
            texts.append(separator)
            offset += len(separator)
        texts.append(part.text)
        runs.extend(InlineRange(r.start + offset, r.end + offset, r.kind) for r in part.ranges)
        offset += len(part.text)
    return AnnotatedText(''.join(texts), tuple(runs))


def collapse_annotated_whitespace(value: AnnotatedText) -> AnnotatedText:
    """Normalize heading whitespace while retaining annotations on visible text."""
    return join_annotated_texts(
        (value.slice(match.start(), match.end()) for match in re.finditer(r'\S+', value.text)),
        ' ',
    )


def merged_script_runs(ranges: Iterable[InlineRange]) -> list[InlineRange]:
    """Return the script runs among ranges, merging contiguous runs of the same kind."""
    merged: list[InlineRange] = []
    for run in sorted((run for run in ranges if run.is_script), key=lambda run: run.start):
        if merged and merged[-1].end == run.start and merged[-1].kind == run.kind:
            previous = merged[-1]
            merged[-1] = InlineRange(previous.start, run.end, run.kind)
        else:
            merged.append(run)
    return merged


def render_script(content: str, kind: str) -> str:
    """Render the text of a script run as inline HTML."""
    content = escape(content, quote=False)
    # Inline HTML contents are still parsed as Markdown. Keep math/marker
    # characters literal rather than accidentally starting emphasis or code.
    # Keep citation brackets readable in the Markdown source.
    for char in '\\`*_':
        content = content.replace(char, f'&#{ord(char)};')
    return f'<{kind}>{content}</{kind}>'


def render_scripts(text: str, ranges: tuple[InlineRange, ...]) -> str:
    """Render script runs as inline HTML, ignoring other ranges."""
    parts: list[str] = []
    offset = 0
    for run in merged_script_runs(ranges):
        parts.append(text[offset : run.start])
        parts.append(render_script(text[run.start : run.end], run.kind))
        offset = run.end
    parts.append(text[offset:])
    return ''.join(parts)
