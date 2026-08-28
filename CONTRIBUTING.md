# Contributing

This project is early and heuristic-heavy. Good changes are usually small,
easy to inspect, and checked against real PDFs.

These notes are for contributors working on the project.

## Development setup

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

## Coding style

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

Use sentence case for Markdown headings, retaining the standard capitalization
of proper nouns and acronyms.

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

Add notable user-facing changes to the `Unreleased` section of `CHANGELOG.md`.
When preparing a release, rename that section to the new version and release
date, then add a fresh `Unreleased` section above it.

## Running unit tests

The complete unit test suite can also be run from the `tests` directory:

```bash
cd tests
make
```

This Makefile is independent of the corpus conversion targets in
`tests/pdf-corpus`.

## Adding unit tests

There is no need to redundantly unit-test high-level extraction behavior that
is already covered by comparisons against expected files in `tests/pdf-corpus`.
Instead, add focused unit tests for helper functions, especially for corner
cases and details that high-level PDF-based tests might not cover.

When adding unit tests:

- Include both positive cases and conservative negative cases for heuristics.
- Prefer small synthetic fixtures that make the relevant inputs and expected
  behavior easy to understand.
- Keep tests deterministic and use temporary directories for generated files;
  do not write into `tests/pdf-corpus`.
- Follow the existing `unittest` structure and use descriptive test names.
- Run `cd tests && make` before submitting changes.

## Testing with the PDF corpus

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

## Working with corpus outputs

Be careful with generated corpus files. They are often used for manual
comparison, not only automated pass/fail testing.

Do not regenerate or overwrite corpus outputs unless that is part of the task.
For quick checks, copy a PDF to `/tmp` and run `frompdf` there:

```bash
cp tests/pdf-corpus/example.pdf /tmp/example.pdf
frompdf /tmp/example.pdf
```

## Heuristic guidelines

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

## Implementation notes

Keep this section in sync when a change adds or removes modules, changes the
core records or block types, or alters the pipeline stages described below.

The implementation is split into focused modules under `src/frompdf`:

- `blocks.py` turns segmented lines into blocks, classifies block quotes and
  headings, and coordinates within-block text repair.
- `cli.py` implements the command-line interface.
- `lines.py` repairs detached diacritics, flattens `pdftext` output, and
  extracts line geometry and typography.
- `models.py` defines line, page-number, and Markdown block records.
- `output.py` writes diagnostic line and page-number CSV files and serializes
  Markdown output.
- `page_edges.py` detects and removes headers and footers, extracts visible
  page labels, and safely completes unambiguous label sequences.
- `pipeline.py` coordinates extraction and classification.
- `reading_order.py` orders intact `pdftext` blocks within page regions and
  detected columns.
- `segmentation.py` combines `pdftext` block hints with page-local geometry
  and typography to find Markdown block boundaries.
- `unhyphenation.py` repairs words and unspaced dashes split across physical
  lines, using document-wide evidence where available.

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
2. Repair detached, geometrically positioned diacritics in the raw data.
3. Flatten the result into line records with geometry and typography.
4. Optionally dump the unfiltered line records to `-lines.csv`.
5. Detect and remove headers and footers, collecting visible page labels.
6. Order the remaining lines by page region and detected column.
7. Safely complete unambiguous page-label sequences and optionally dump them
   to `-pagenos.csv`.
8. Segment each page into blocks using `pdftext` hints, geometry, typography,
   indentation, and line-spacing evidence.
9. Build paragraph or block-quote records and repair words and unspaced dashes
   split across physical lines within each block.
10. Reclassify heading-like paragraphs and normalize their heading levels.
11. Serialize the blocks as Markdown in `.md`.
