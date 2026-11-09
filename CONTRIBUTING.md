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
- `continuations.py` recognizes text continuing at the top of the next column
  or page and assembles page-aware text fragments for blocks and notes.
- `emphasis.py` adjusts bold and italic ranges so their Markdown delimiters
  are valid and nested, and renders scripts and emphasis together.
- `escaping.py` escapes text that Markdown would otherwise read as syntax,
  checking inline characters everywhere and block syntax at line starts.
- `footnotes.py` detects numbered bottom notes, assembles continuations with
  page-aware text, and places numeric groups in Notes sections.
- `front_matter.py` renders subtitles, author names, and chapter labels near
  document titles as bold paragraphs and drops ornaments between them.
- `heading_candidates.py` identifies compact centered titles using caps or
  italic styling, established body columns, and surrounding whitespace.
- `line_breaks.py` recognizes deliberate line breaks within blocks, where the
  next word would have fit on the line or the font changes after a short line,
  extending them to all line ends of blocks set line by line in short
  centered lines. It also finds passages set off from the text line by line,
  such as quoted verse, whose line ends break even before a sentence
  continuing in lower case.
- `lines.py` repairs detached diacritics, removes icon-font glyphs, decodes
  glyphs of TeX math extension fonts and capitals of blackboard bold fonts,
  restores private-use bullets of symbol fonts, reattaches detached scripts,
  merges the pieces of split denominators, flattens `pdftext` output, and
  extracts line geometry, typography, inline script ranges, bold and italic
  ranges, and fraction denominators and limits stacked below a line.
- `lists.py` recognizes bulleted and numbered list items and their
  continuation lines, using marker alignment, consecutive numbering, and
  deliberate breaks before weakly marked lists.
- `models.py` defines line, page-number, and Markdown block records.
- `output.py` writes diagnostic line and page-number CSV files and serializes
  Markdown output.
- `page_edges.py` detects and removes headers and footers, extracts visible
  page labels, and safely completes unambiguous label sequences.
- `pipeline.py` coordinates extraction and classification.
- `reading_order.py` orders intact `pdftext` blocks within page regions and
  detected columns.
- `rules.py` reads horizontal and vertical rules, such as table borders, from
  the vector paths of each page with pypdfium2.
- `segmentation.py` combines `pdftext` block hints with page-local geometry
  and typography to find Markdown block boundaries.
- `scripts.py` slices and joins annotated plain text, preserving inline
  ranges through text repair, and renders `<sup>`/`<sub>` tags at serialization.
- `tables.py` recognizes tables framed by connected rules, or ruled off around
  their header with columns separated by gutters, infers their rows, columns,
  and spanning cells, splits lines into the pieces of each cell, and joins
  tables continuing on the next page.
- `unhyphenation.py` repairs words, unspaced dashes, and URLs split across
  physical lines, using document-wide evidence where available. This
  includes the parts of hyphenated compounds, which decide on hyphens within
  compounds.

Important concepts:

- `Line` in `models.py` is a flattened record from `pdftext` output. It
  records whether `pdftext` reported whitespace at its edges, which tells
  whether pieces of one visual line need a space between them, whether it
  is the denominator of an inline fraction ending the preceding record, and
  whether it belongs to the limits below the last word of the record before
  them, as under `argmax`. It
  also records where the text after its first word starts, which is where a
  list item's text follows its marker, and the horizontal extent of each
  word, which tells the table cells its pieces belong to.
- `InlineRange` records superscript, subscript, bold, or italic offsets in
  decoded plain text. Ranges of different kinds may overlap. Lines, blocks,
  and text fragments retain these ranges until serialization.
- `PageNumber` in `models.py` stores the raw page number and optional visible
  page number.
- `Block` in `models.py` is the base Markdown block type.
- `Paragraph`, `StrongParagraph`, `BlockQuote`, `Heading`, `Footnote`,
  `ListItem`, and `Table` in `models.py` are supported block subclasses.
  `StrongParagraph` is a paragraph rendered in bold. `ListItem` holds its
  Markdown list marker. `Table` holds `TableCell` records with their row and
  column spans and its number of header rows. `TextFragment` retains the
  source page and preceding whitespace of each piece of a block's text, so
  page markers can occur within paragraphs, block quotes, and notes.
- `HARD_LINE_BREAK` in `models.py` marks deliberate line breaks in block text
  until serialization renders them as a trailing backslash, or as `<br>` in
  table cells.
- `Rule` in `rules.py` is a horizontal or vertical rule in `pdftext`
  coordinates. `TableLayout` in `tables.py` holds a recognized table's source
  lines, its frame on each page, and its cells with the line pieces of their
  parts, which may continue on the next page.
- `extract_markdown` in `pipeline.py` returns a list of blocks.
- `markdown_to_text` in `output.py` serializes blocks as Markdown.

The current pipeline is roughly:

1. Extract raw `pdftext` page data.
2. Repair detached, geometrically positioned diacritics in the raw data,
   keeping a combining accent where no precomposed letter exists, remove
   glyphs from icon fonts, and decode TeX math extension glyphs that
   `pdftext` reports by their font codes. Capitals of blackboard bold fonts
   become double-struck letters. Restore bullets of symbol fonts, which
   `pdftext` drops as private-use characters. Move scripts that `pdftext` set
   apart, in a block of their own or stacked below or above another script,
   back into the line records they belong to; a record mostly in script size
   is measured against its largest glyphs. Merge touching records of small
   glyphs centered below a numerator into one denominator, which starts with
   a radical sign reaching down beside it from the numerator's record.
3. Flatten the result into line records with geometry, typography, and
   conservative character-level superscript/subscript annotations. When
   `pdftext` puts small glyphs into a line record of their own, the other
   pieces of the same line of running text serve as the ordinary reference
   text, leaving out their own scripts. With real font sizes, these are all
   pieces of the line, in either order, and glyphs of a script's size next to
   the largest ones are small; otherwise, the adjacent pieces must mostly be
   in a larger size. Small records centered below small text ending the
   preceding record, with the line continuing after the wider of numerator
   and denominator, are marked as fraction denominators. Neither part of a
   fraction is a script of the text around it. Records of small text centered
   below a line's last word, which has letters in it, with the line continuing
   after them, are marked as its limits. Bold and italic ranges follow font
   names and the italic font flag. Letters in math italic fonts are italic,
   with combining marks following them; other math fonts are ignored. A style
   covering most of the document's letters and digits is its body style and
   is dropped.
4. Optionally dump the unfiltered line records to `-lines.csv`.
5. Detect and remove headers and footers, collecting visible page labels.
6. Order the remaining lines by page region and detected column. A block
   ending where the first line of the block before it begins, on the same
   visual line, moves before that block.
7. Safely complete unambiguous page-label sequences and optionally dump them
   to `-pagenos.csv`.
8. Recognize tables framed by connected horizontal and vertical rules, read
   from the page drawings, with a vertical rule inside the frame. Columns lie
   between vertical rules. Horizontal rules separate rows where they bound
   all columns, or all columns subdivided between the same complete
   boundaries; elsewhere they separate parts of a cell's text. Without rules
   between body rows, lines starting in the first column start rows. Cells
   span rows or columns where rules are missing. Below a spanning header cell,
   rows of bold text extend the header. Without vertical rules, a top rule
   and a header rule of the same width frame the header, and the gutters of
   the body just left of header labels separate columns. Such a table ends at
   a third rule or continues on the next page. Lines starting left of the
   other lines of a cell part, as with hanging indents, start parts of their
   own. A table ending its page joins a table starting the next page, after
   at most a caption marked as continued, if its header repeats or its
   columns line up; the repeated header and the caption are dropped. A first
   row without text in the first column joins the last row if the table was
   not closed by a rule or the row's text starts in lower case. Unclosed
   tables that do not continue are dropped. Tables are left out of all other
   blocks, which are split where a table lies between their lines on a page.
9. Detect and extract numbered footnote regions using typography and geometry,
   assembling supported paragraph and adjacent-page continuations.
10. Recognize list items: lines starting with a marker, together with
    following lines indented past it, across page boundaries. Bullet glyphs
    suffice; dashes and numbers need at least two aligned items with
    consecutive numbers after a deliberate break, and numbers without a
    delimiter also most items wrapping onto continuation lines. Marker lines,
    described below, end a list although they are indented past its markers.
11. Segment each page's body into blocks using `pdftext` hints, geometry,
    typography, indentation, and line-spacing evidence. Display-sized lines
    sharing face, alignment, and tight leading stay together, as in titles,
    while a change of both size and face after a short line, as between author
    names and affiliations, starts a new block. Confirmed centered title
    candidates override boundaries only at and within those titles. Where
    `pdftext` starts a new block after a line split into pieces, the left edge
    of the whole visual line decides whether the text continues. Within a
    line of running text, a new block needs a change of size, not just face,
    and never starts at a short, touching piece in script-sized type.
    Below a line filling its column, regular spacing at the same left edge, or
    at the margin below an indented first line, continues the paragraph despite
    a `pdftext` block edge or a font change explained by italics within the
    lines, unless the next line starts with an item label. A visual line
    ending in a script-sized piece, such as a formula, is judged by its start.
    After a sentence end, this takes the same font, a line closely reaching the
    right edge, and a next line at the margin. Below a shorter line without a
    sentence end, a `pdftext` block edge is overridden by a next line starting
    in lower case, not with an item label, at the same left edge, in the same
    typography and at regular spacing.
    Each list item becomes a block of its own, and so does each passage set
    off line by line: evenly spaced lines in smaller type, inset at a shared
    left edge, most of which leave room for the next line's first word,
    followed by body text on the same page. A gap, as between stanzas, ends
    such a passage. Marker lines, such as ornaments, also become blocks of their
    own: visual lines without letters or digits, short and centered in their
    column. They are never block quotes.
12. Join blocks continuing at the top of the next column or page. Similar
    typography, a full last line, a non-indented first line, and consistent
    block-quote classification are required. An open sentence, a lower-case
    continuation, or a missing indent in a document whose paragraphs start
    indented must additionally support the join. List items join exactly
    where their recognized lines continue.
13. Build paragraph, block-quote, or list-item records, replacing list
    markers with Markdown ones, and mark deliberate line breaks, including
    before lines of a list item that start right of its text, and wherever a
    line of a passage set off line by line leaves room for the next word.
    Join the pieces into which `pdftext` split a physical line with a space
    or nothing, depending on reported whitespace and the gap between them,
    unless they are too far apart to be running text, and append fraction
    denominators to their numerators after a slash, writing a radical over a
    compound denominator as `√(…)`. Limits follow the word above them as a
    subscript, with their rows separated by commas. Then repair words and
    unspaced dashes split across physical lines within each block, preserving
    script ranges and attributing words joined across pages to their starting
    page. URLs and DOIs broken at a line end are joined first, top-down, with
    the next line's first token if it has the structure of a URL within it,
    or a value after a `=`, unless a change of script level, as before a
    note marker, lies between them. A token starting another URL only
    continues a URL ending in `/`.
14. Reclassify heading-like paragraphs using size and confirmed title
    candidates, which take precedence over block quotes. Blocks without
    letters or digits never become headings. In the front matter following the
    first heading and the first top-level heading, render subtitles, author
    names, and chapter labels in bold instead and drop ornaments. Then
    normalize heading levels.
15. Repair note text while retaining source-page boundaries, group notes when
    numbering restarts, and place a single sequence at the document end.
    Multiple groups prefer boundaries matching the sections they cover,
    limited by intervening restart boundaries. Nearby restarts can associate
    old notes with a preceding mid-page boundary. Groups sharing a boundary
    share one Notes title. Default H2/H3 Notes titles match a deeper following
    heading when necessary to prevent accidental parentage.
16. Serialize the blocks as Markdown in `.md`, including compact numbered notes.
    Text that Markdown would read as syntax is escaped, including list
    markers starting blocks that were not recognized as list items. Only
    paragraphs reading as a thematic break, such as `***`, stay unescaped and
    drop their emphasis; a page marker starting one becomes a paragraph of its
    own, so it does not turn the rule into literal text.
    Inline scripts become `<sup>`/`<sub>` tags, nesting scripts of the other
    kind within them; consumed footnote labels remain ordinary list markers.
    Bold and italic ranges become `**`/`*` emphasis. Headings and strong
    paragraphs drop bold, and italics covering all of their text. Ranges of
    the same kind separated only by whitespace are merged; list markers stay
    outside and page markers split them. Of partly overlapping ranges, the
    shorter one loses the overlap. Punctuation, symbols, and scripts at range
    edges move outside where a delimiter could not open or close, and
    openers that CommonMark could read as closing the enclosing emphasis are
    adjusted, so the delimiters render as intended. Ranges left with nothing but
    punctuation are dropped.
    Restarted lists sharing a Notes section are separated by an empty HTML
    comment so Markdown renderers preserve their starting numbers.
    List items are written compactly, with page markers after the list
    marker; adjacent lists that Markdown would merge are separated by the
    same comment.
    Tables are written as pipe tables, repairing cell text like paragraph
    text. Header rows below a cell spanning columns are combined with it;
    other spanning cells fill their first row and column. Header cells drop
    bold. Pipes are escaped, parts of a cell's text are separated by `<br>`,
    and page markers start the first header cell and the text of cells
    continuing on another page.
