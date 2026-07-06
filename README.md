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

## What frompdf does right now

The current version provides one command:

- `frompdf file.pdf` - extract Markdown and diagnostic CSV files from a PDF

For an input named `file.pdf`, the command writes:

- `file.md` - Markdown output
- `file-lines.csv` - extracted line records with page, block, geometry, font
  size, and weight data
- `file-pagenos.csv` - visible page numbers detected in headers or footers, if
  any are found

If `file.md` already exists, frompdf renames it to `file.md.bak` before
writing the new output. Overwriting an existing `.bak` file is allowed.

## Current Markdown Features

frompdf currently detects and serializes:

- paragraphs
- headings, based mostly on font size plus a document-relative font-weight
  boost
- block quotes, based on indentation
- repeated headers and footers, which are removed from the Markdown output
- visible page numbers found in removed headers or footers

The internal block model tracks the raw PDF page number and, when available,
the visible page number for each block.

## Requirements

- Python 3.11 or newer
- `pdftext`, installed through this package's dependencies

## Installation

For local use from a checkout of this repository:

```bash
pip install -e .
```

That installs the package in editable mode and makes the `frompdf` command
available in the active Python environment.

If you prefer `pipx` for command-line tools, use editable mode when installing
from a local checkout so the command sees local code changes:

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
document-lines.csv
document-pagenos.csv
document.md
```

The command currently has no CLI options. It always writes the line CSV when
called through the script entry point. It writes the page-number CSV only when
visible page numbers were detected.

## Limitations

PDFs do not contain document structure directly, so most higher-level
structure has to be inferred. Current limitations include:

- heading detection is heuristic and can miss headings or over-detect short
  emphasized text
- block quote detection is conservative and currently relies on indentation
- lists, tables, captions, footnotes, and code blocks are not modeled as
  dedicated block types yet
- multi-column and heavily designed PDFs can still produce awkward reading
  order
- header and footer removal depends on repetition and page-position heuristics

The diagnostic CSV files are part of the workflow: they make it easier to see
why a specific line or block was classified the way it was.

## Planned Direction

Planned next improvements include:

- detection of lists, footnotes, and preformatted blocks
- dehyphenation of words split across line breaks
- better detection of paragraph boundaries, including merging paragraphs that
  span more than one page
- correction of font-encoding and ligature-related text extraction errors
- additional output formats such as HTML, EPUB, ODT, and DOCX

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, style rules,
testing commands, and guidance for contributors and coding agents.

## License

frompdf is distributed under the MIT license. See [LICENSE.txt](LICENSE.txt).
