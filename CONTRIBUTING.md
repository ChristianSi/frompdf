# Contributing

This project is early and heuristic-heavy. Good changes are usually small,
easy to inspect, and checked against real PDFs.

These notes are for contributors working on the project.

## Development Setup

Use Python 3.11 or newer.

From the repository root, install in editable mode:

```bash
pip install -e .
```

For an isolated CLI install with `pipx`, use editable mode if you want local
code changes to be picked up:

```bash
pipx install -e .
```

## Coding Style

The project uses Ruff and basedpyright. Important local style settings are in
`pyproject.toml`:

- Python line length: `100`
- Python quote style: single quotes
- Ruff lint rules: `E`/`F` for pycodestyle and Pyflakes checks, `I` for
  import sorting, `UP` for Python syntax upgrades, and `B` for bugbear checks
- basedpyright mode: `standard`

Custom-written Markdown files in the repository should usually be wrapped at
78 characters. Headings, code blocks, tables, URLs, literal paths, and
generated output may be longer.

Before considering a code change done, run:

```bash
basedpyright
python -m compileall -q src/frompdf
python -m unittest discover -s tests
ruff format --check src tests
ruff check src tests
```

If formatting is needed:

```bash
ruff format src tests
```

## Testing With The PDF Corpus

The semi-manual corpus lives in `tests/pdf-corpus`.

Run conversions:

```bash
cd tests/pdf-corpus
make extract
```

Compare generated outputs with opt-in expected files:

```bash
make diff
```

Show full diffs:

```bash
make vdiff
```

Calling `make` runs `extract` and then `diff`.

Expected files use `.expected.` in the filename. For example:

```text
file.expected.md
file.md
```

Only files with expected counterparts are checked by `make diff`. Other
generated files are useful for visual inspection and debugging.

## Working With Corpus Outputs

Be careful with generated corpus files. They are often used for manual
comparison, not only automated pass/fail testing.

Do not regenerate or overwrite corpus outputs unless that is part of the task.
For quick checks, copy a PDF to `/tmp` and run `frompdf` there:

```bash
cp tests/pdf-corpus/example.pdf /tmp/example.pdf
frompdf /tmp/example.pdf
```

## Heuristic Guidelines

Prefer conservative recognition. Missing a heading, quote, or special block is
usually easier to fix later than incorrectly converting ordinary body text.

When changing a heuristic:

- inspect the relevant `-lines.csv` output
- check the raw `pdftext` data when the CSV is not enough
- test at least one positive example and one likely regression example
- document new constants or thresholds close to the code that uses them
- keep the behavior explainable from line geometry, font size, font weight,
  repetition, or page metadata

Avoid adding broad rules based on one PDF unless the rule is guarded by
signals that make sense in other documents too.

## Implementation Notes

The implementation is split into focused modules under `src/frompdf`:

- `blocks.py` groups lines and detects block quotes and headings.
- `cli.py` implements the command-line interface.
- `lines.py` flattens `pdftext` output and extracts line geometry and
  typography.
- `models.py` defines line, page-number, and Markdown block records.
- `output.py` writes diagnostic CSV files and Markdown output.
- `page_edges.py` detects headers, footers, and visible page numbers.
- `pipeline.py` coordinates extraction and classification.

Important concepts:

- `Line` in `models.py` is a flattened record from `pdftext` output.
- `PageNumber` in `models.py` stores the raw page number and optional visible
  page number.
- `Block` in `models.py` is the base Markdown block type.
- `Paragraph`, `BlockQuote`, and `Heading` in `models.py` are currently
  supported block subclasses.
- `extract_markdown` in `pipeline.py` returns a list of blocks.
- `markdown_to_text` in `output.py` serializes blocks as Markdown.

The current pipeline is roughly:

1. Extract raw `pdftext` page data.
2. Flatten it into line records.
3. Optionally dump `-lines.csv`.
4. Detect and remove repeated headers and footers.
5. Extract visible page numbers from removed header/footer content.
6. Assemble lines into Markdown blocks.
7. Detect block quotes and headings.
8. Serialize Markdown to `.md`.
