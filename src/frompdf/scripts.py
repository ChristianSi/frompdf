"""Keep script positions in plain text until Markdown serialization."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from html import escape

from frompdf.models import ScriptRange


@dataclass(frozen=True)
class AnnotatedText:
    text: str
    scripts: tuple[ScriptRange, ...] = ()

    def slice(self, start: int = 0, end: int | None = None) -> 'AnnotatedText':
        """Slice text and clip/shift its annotations using ordinary string indices."""
        start, end, _ = slice(start, end).indices(len(self.text))
        return AnnotatedText(
            self.text[start:end],
            tuple(
                ScriptRange(max(run.start, start) - start, min(run.end, end) - start, run.kind)
                for run in self.scripts
                if run.start < end and run.end > start
            ),
        )

    def __add__(self, other: 'AnnotatedText') -> 'AnnotatedText':
        offset = len(self.text)
        return AnnotatedText(
            self.text + other.text,
            self.scripts
            + tuple(ScriptRange(r.start + offset, r.end + offset, r.kind) for r in other.scripts),
        )


def join_annotated_texts(parts: Iterable[AnnotatedText], separator: str = '') -> AnnotatedText:
    """Join text pieces without changing which characters carry scripts."""
    texts: list[str] = []
    runs: list[ScriptRange] = []
    offset = 0
    for part in parts:
        if texts:
            texts.append(separator)
            offset += len(separator)
        texts.append(part.text)
        runs.extend(ScriptRange(r.start + offset, r.end + offset, r.kind) for r in part.scripts)
        offset += len(part.text)
    return AnnotatedText(''.join(texts), tuple(runs))


def collapse_annotated_whitespace(value: AnnotatedText) -> AnnotatedText:
    """Normalize heading whitespace while retaining annotations on visible text."""
    return join_annotated_texts(
        (value.slice(match.start(), match.end()) for match in re.finditer(r'\S+', value.text)),
        ' ',
    )


def render_scripts(text: str, scripts: tuple[ScriptRange, ...]) -> str:
    """Render script runs as inline HTML, merging contiguous runs of the same kind."""
    merged: list[ScriptRange] = []
    for run in scripts:
        if merged and merged[-1].end == run.start and merged[-1].kind == run.kind:
            previous = merged[-1]
            merged[-1] = ScriptRange(previous.start, run.end, run.kind)
        else:
            merged.append(run)
    parts: list[str] = []
    offset = 0
    for run in merged:
        parts.append(text[offset : run.start])
        content = escape(text[run.start : run.end], quote=False)
        # Inline HTML contents are still parsed as Markdown. Keep math/marker
        # characters literal rather than accidentally starting emphasis or links.
        for char in '\\`*_[]':
            content = content.replace(char, f'&#{ord(char)};')
        parts.append(f'<{run.kind}>{content}</{run.kind}>')
        offset = run.end
    parts.append(text[offset:])
    return ''.join(parts)
