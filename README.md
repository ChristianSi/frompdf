# frompdf

frompdf is a simple CLI tool for extracting structured text from PDFs.

The initial and primary output format is Markdown, with additional output
formats planned. frompdf uses robust heuristics to detect paragraphs, headings
at various levels, block quotes, and other document features. Running headers
and footers are detected and removed, while page numbers can optionally be
exported as metadata.

These heuristics can never be perfect, but they should often provide a useful
approximation of the actual document content — one that is more useful than
plain text extraction for
[RAG](https://en.wikipedia.org/wiki/Retrieval-augmented_generation) and
similar workflows, or for turning read-only PDFs into editable structured
text.

While ML-based alternatives such as [Docling](https://www.docling.ai/) may
handle some details better, they are slower and have considerably higher
computational overhead. frompdf's heuristics will not get every detail right,
but they are fast, robust, and easy to run locally.

frompdf is released under the permissive MIT License. This can make it easier
to use, modify, and integrate than tools based on
[PyMuPDF](https://github.com/pymupdf/PyMuPDF), which is available under the
GNU AGPL or a commercial license.

## What frompdf does

The current version provides one command:

- `frompdf file.pdf` - extract Markdown from a PDF

For an input named `file.pdf`, the command writes:

- `file.md` - Markdown output

With diagnostic options, it can also write:

- `file-lines.csv` - extracted line records with page, block, geometry, font
  size, and weight data
- `file-pagenos.csv` - raw PDF page numbers mapped to detected or safely
  inferred visible page labels

If `file.md` already exists, frompdf renames it to `file.md.bak` before
writing the new output.

## Current Markdown features

frompdf currently detects and serializes:

- paragraphs, including paragraphs and block quotes continuing across column
  and page boundaries
- headings, based mostly on font size plus a document-relative font-weight
  boost
- subtitles, author names, and chapter labels near a document title, rendered
  as bold paragraphs instead of headings
- block quotes, based on indentation
- bulleted and numbered lists, rendered as compact Markdown lists
- repeated headers and footers, which are removed from the Markdown output
- visible page numbers found in removed headers or footers
- optional page-boundary markers embedded in the Markdown output
- document-aware unhyphenation of words split across lines within a block
- normalization of unspaced en and em dashes split across lines within a block
- inline superscripts and subscripts, preserved as `<sup>` and `<sub>` tags
- bold and italic text, rendered as `**bold**` and `*italic*` emphasis
- deliberate line breaks within blocks, such as in epigraphs or address cards,
  preserved as hard line breaks (a trailing backslash)
- escaping of text that Markdown would otherwise read as syntax

The internal block model tracks the raw PDF page number and, when available,
the visible page number for each block.

## Requirements

- Python 3.11 or newer
- `pdftext`, installed through this package's dependencies

## Installation

### Install the latest release from PyPI

Install the latest published version with `pip`:

```bash
pip install frompdf
```

For an isolated command-line installation, use `uv`:

```bash
uv tool install frompdf
```

Alternatively, use `pipx`:

```bash
pipx install frompdf
```

All three options make the `frompdf` command available in your environment.

### Install from a repository checkout

From a checkout of this repository, install the package in editable mode:

```bash
pip install -e .
```

This makes the `frompdf` command use your local source code, including any
changes you make.

To use `pipx` with a local checkout, install in editable mode as well:

```bash
pipx install -e .
```

## Usage

Convert a PDF:

```bash
frompdf ./document.pdf
```

Example output:

```text
document.md written
```

### Page markers

Use `-m` or its long form `--page-markers` to embed page boundaries in the
Markdown itself:

```bash
frompdf -m ./document.pdf
```

Each source page starts with a marker such as `[[PAGE:7]]`, containing its raw
PDF page number. When a different visible page label was detected or safely
inferred, the marker includes that label too, as in `[[PAGE:7|VISIBLE:9]]`.
The `VISIBLE:` field distinguishes the visible label from the raw page number,
matching the `visible` column of the `-pagenos.csv` file, including for
compound visible labels such as `[[PAGE:2|VISIBLE:51:2]]`. The markers remain
visible as plain text when the Markdown is rendered. A parenthesis directly
following a marker is escaped as `\(`, so it does not turn the marker into a
link, and `[[PAGE:` occurring in the source text is escaped as `[\[PAGE:`, so
it cannot be mistaken for a marker. Markers are placed after Markdown prefixes
such as `## ` for headings and `> ` for block quotes. A paragraph or block
quote continuing on the next page contains the marker where that page's text
starts; a word split across the boundary stays on its starting page. Collected
notes retain their source pages, so markers can move backward in page order
and can occur inside a continued note.

### Footnotes

Detected footnotes are collected in endnote-style "Notes" sections, with their
original numbers. A single uninterrupted numbering sequence is placed at the
document end under H2. When numbering restarts, each group prefers a following
heading at the level of the shallowest section it covers. This keeps notes
spanning several sections out of individual subsections.

A boundary before the next group starts takes priority over a later major
heading. Nearby restarts can also place old notes before a mid-page heading
above their footnote area. Without a following heading, notes go at the end.

Generated headings default to H2 for one Notes section or H3 for several.
Before a deeper heading, Notes matches that level so the following section
does not become its child (H4 before H4, for example). A trailing group among
several uses at least the level of the sections it covers. Groups sharing a
destination share one Notes heading, with separate lists to preserve restarts.

Choose a different section title with `-n` or its long form `--notes-title`:

```bash
frompdf -n Anmerkungen -m ./document.pdf
```

### Diagnostic options

Write diagnostic CSV files with `--dump-lines` and `--dump-pagenos`:

```bash
frompdf --dump-lines --dump-pagenos ./document.pdf
```

Example output:

```text
document-lines.csv written
document-pagenos.csv written
document.md written
```

`--dump-lines` writes the extracted line records. `--dump-pagenos` always
writes one mapping row per PDF page. Missing visible labels are written as
`?`; gaps are filled when surrounding Arabic or Roman page labels determine an
unambiguous value. The page-marker and diagnostic options are independent;
they can be combined or used separately, and `--page-markers` and
`--dump-pagenos` use the same page-number mapping.

### Lists

Lines starting with a bullet, dash, or number become Markdown list items,
together with following lines indented past the marker. Bullet glyphs such as
`•` mark list items on their own. Dashes and numbers also start ordinary
wrapped lines, as with a parenthetical dash or a date such as `23. Dezember`,
so they need at least two aligned items with consecutive numbers, and the
first item must follow a deliberate break, such as a short line, a colon, or
extra spacing. Numbers without a period or parenthesis, as in some reference
lists, need at least three items, most of which wrap onto hanging-indented
continuation lines. Numbered lines of code, as in algorithms, stay as they
are.

Bullets of all kinds become `-`. Numbered items keep their numbers and use
`.`, or `)` where the source has `3)` or `(3)`. Lists are written compactly,
without blank lines between items, and continuation lines are indented to the
item text. Lists are never block quotes, even when they are indented, and
items continue across page boundaries. Bullets that symbol fonts such as
Symbol or Wingdings map to private-use code points are restored.

Nested lists are not recognized; deeper-indented lines continue the item,
after a hard line break, since wrapped text never starts right of the item's
text. Entries with a hanging indent but no marker, as in many bibliographies,
remain separate paragraphs.

### Superscripts and subscripts

Small, raised or lowered characters in running text retain their position
using inline HTML tags, for example `text<sup>2</sup>` and
`GaV<sub>4</sub>S<sub>8</sub>`. Rendering these tags requires a Markdown
viewer that allows HTML. Detected footnote labels are still written as
ordinary numbered list markers, such as `2. `.

Detection uses character size and position relative to nearby ordinary text,
including when a PDF reports placeholder font sizes or mixes scripts into
ordinary spans. Recognition is conservative; standalone scripts and complex
stacked mathematical notation may remain plain text. Diagnostic line CSVs
retain plain text and include `ranges` with decoded character offsets, for
scripts as well as bold and italic text.

### Bold and italics

Bold and italic text is recognized by font names, such as `Times-Bold` or
`LMRoman10-Italic`, and the italic flag of PDF fonts. Letters in math italic
fonts, such as TeX variables, are italic as well. Other math fonts, holding
symbols and operators, are ignored even when flagged as italic. A style used
for most of a document's text is its body style and is not marked either.

Bold and italic parts of paragraphs, block quotes, and notes are rendered as
`**bold**` and `*italic*`, as are completely styled blocks. Headings and the
bold paragraphs used for subtitles and author names never get additional bold,
and italics covering all of their text are dropped; partial italics remain.

Emphasis is adjusted where Markdown would not render it as intended. List and
quote markers stay outside of it, and page markers interrupt it. Punctuation
and symbols at the edges move outside where a delimiter next to a letter could
not open or close, as in `*word*.next` rather than `*word.*next`, and so do
scripts. Where bold and italic ranges partly overlap, the shorter one loses
the overlap. A rare kind of opening delimiter inside a word, which Markdown
could read as closing the surrounding emphasis, is dropped.

## Limitations

PDFs do not contain document structure directly, so most higher-level
structure has to be inferred. Current limitations include:

- heading detection is heuristic and can miss headings or over-detect short
  emphasized text
- block quote detection is conservative and currently relies on indentation
- nested lists, tables, captions, and code blocks are not modeled as dedicated
  block types yet
- multi-column and heavily designed PDFs can still produce awkward reading
  order
- header and footer removal depends on repetition and page-position heuristics

The diagnostic CSV files are part of the workflow: they make it easier to see
why a specific line or block was classified the way it was.

## Planned direction

Planned next improvements include:

- detection of nested lists and preformatted blocks
- merging paragraphs that span more than one page
- correction of font-encoding and ligature-related text extraction errors
- better support for multi-column PDFs
- additional output formats such as HTML, EPUB, ODT, and DOCX

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, style rules,
testing commands, and guidance for contributors and coding agents.

Release history and unreleased changes are recorded in
[CHANGELOG.md](CHANGELOG.md).

## Acknowledgements

Development of frompdf has benefited from assistance by
[GPT](https://developers.openai.com/api/docs/models) in
[Codex](https://learn.chatgpt.com/docs/codex/ide) and
[Claude Opus](https://www.anthropic.com/claude/opus) in
[Claude Code](https://code.claude.com/docs/en/overview), including support
with coding, testing, and documentation.

## License

frompdf is distributed under the MIT license. See [LICENSE.txt](LICENSE.txt).
