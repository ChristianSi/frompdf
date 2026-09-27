# frompdf

frompdf is a simple CLI tool for extracting structured text from PDFs.

The initial and primary output format is Markdown, with additional output
formats planned. frompdf uses robust heuristics to detect paragraphs, headings
at various levels, block quotes, and other document features. Running headers
and footers are detected and removed, while page numbers can optionally be
exported as metadata.

These heuristics can never be perfect, but they should often provide a
useful approximation of the actual document content — one that is more
useful than plain text extraction for
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

- paragraphs
- headings, based mostly on font size plus a document-relative font-weight
  boost
- block quotes, based on indentation
- repeated headers and footers, which are removed from the Markdown output
- visible page numbers found in removed headers or footers
- optional page-boundary markers embedded in the Markdown output
- document-aware unhyphenation of words split across lines within a block
- normalization of unspaced en and em dashes split across lines within a block

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

Each source page starts with a marker such as `<<PAGE:7>>`, containing its raw
PDF page number. When a different visible page label was detected or safely
inferred, the marker includes that label too, as in `<<PAGE:7|LABEL:9>>`.
The `LABEL:` field distinguishes the visible label from the raw page number,
including for compound visible labels such as `<<PAGE:2|LABEL:51:2>>`.
Markers are placed after Markdown prefixes such as `## ` for headings and
`> ` for block quotes. Collected notes retain their source pages, so markers
can move backward in page order and can occur inside a continued note.

### Footnotes

Detected footnotes are collected in endnote-style "Notes" sections, with
their original numbers. A single uninterrupted numbering sequence is placed
at the document end under H2. When numbering restarts, each group prefers a
following heading at the level of the shallowest section it covers. This
keeps notes spanning several sections out of individual subsections.

A boundary before the next group starts takes priority over a later major
heading. Nearby restarts can also place old notes before a mid-page heading
above their footnote area. Without a following heading, notes go at the end.

Generated headings default to H2 for one Notes section or H3 for several.
Before a deeper heading, Notes matches that level so the following section
does not become its child (H4 before H4, for example). A trailing group among
several uses at least the level of the sections it covers. Groups sharing a
destination share one Notes heading, with separate lists to preserve restarts.

Choose a different section title with `--notes-title`:

```bash
frompdf --notes-title Anmerkungen -m ./document.pdf
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
`?`; gaps are filled when surrounding Arabic or Roman page labels determine
an unambiguous value. The page-marker and diagnostic options are independent;
they can be combined or used separately, and `--page-markers` and
`--dump-pagenos` use the same page-number mapping.

## Limitations

PDFs do not contain document structure directly, so most higher-level
structure has to be inferred. Current limitations include:

- heading detection is heuristic and can miss headings or over-detect short
  emphasized text
- block quote detection is conservative and currently relies on indentation
- general lists, tables, captions, and code blocks are not modeled as
  dedicated block types yet
- multi-column and heavily designed PDFs can still produce awkward reading
  order
- header and footer removal depends on repetition and page-position heuristics

The diagnostic CSV files are part of the workflow: they make it easier to see
why a specific line or block was classified the way it was.

## Planned direction

Planned next improvements include:

- detection of general lists and preformatted blocks
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
[ChatGPT](https://chatgpt.com/) and
[Codex](https://learn.chatgpt.com/docs/codex/ide), including support with
coding, testing, and documentation.

## License

frompdf is distributed under the MIT license. See [LICENSE.txt](LICENSE.txt).
