# Changelog

All notable, user-visible changes to frompdf are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Tables drawn with rules are rendered as pipe tables. Tables need connected
  horizontal and vertical rules with a vertical rule between columns, as in
  ruled grids or booktabs-style tables with column rules; rules nested in
  scaled or cropped drawings are found as well. Rules missing between cells
  make them span rows or columns. A header cell spanning several columns is
  combined with the labels below it; other spanning cells show their text in
  their first row and column. Rules dividing a cell's text without lining up
  across columns separate its parts by `<br>`. Text around a table no longer
  runs into it. Tables without column rules or continuing across pages are not
  recognized yet.
- Bulleted and numbered lists are rendered as compact Markdown lists, with
  continuation lines indented to the item text. Bullet glyphs mark items on
  their own; dashes and numbers need at least two aligned items with
  consecutive numbers after a deliberate break, so wrapped lines starting with
  a dash or a date are left alone. Numbers without a delimiter, as in
  reference lists, also need most items to wrap onto hanging-indented
  continuation lines, so numbered lines of algorithms are left alone. Indented
  lists are no longer block quotes, items continue across pages, and page
  markers follow the list marker. Lines of an item starting right of its text
  follow a hard line break. Bullets that Symbol and Wingdings fonts map
  to private-use code points, which `pdftext` drops, are restored.
- Subtitles, author names, and chapter labels near a document title are
  rendered as bold paragraphs rather than taking up heading levels of their
  own, so section headings keep the levels right below the title. This
  applies after the document's first heading and its first top-level heading,
  up to the body text on the same page. The level of a heading directly
  below the title is demoted there, as for a subtitle or author names
  alternating with affiliations, unless it reads like a section heading and
  is also used elsewhere. Ornaments in that area, such as rows of bullets, are
  dropped.
- Text that Markdown would read as syntax is escaped, such as asterisks,
  underscores outside words, and heading, quote, and list markers at line
  starts. Escapes are limited to where they are needed. Text that only looks
  like a list marker, at the start of a paragraph that was not recognized as
  a list item, is escaped as well, so it does not become an accidental list.
- Deliberate line breaks within paragraphs and block quotes, such as those in
  epigraphs and their attributions, author and affiliation cards, or lists of
  dates, are preserved as CommonMark hard line breaks (a trailing backslash).
  A break counts as deliberate when the next word would have fit on the line
  or the font changes after a clearly short line. In blocks of short centered
  lines, such as address cards, one such break marks the other line ends as
  deliberate too.
- Inline superscripts and subscripts are detected from character geometry and
  preserved as `<sup>` and `<sub>` tags in Markdown, including footnote and
  citation markers, chemical formulas, and mathematical indices. Detected
  footnote labels remain ordinary numbered list markers.
- Bold and italic text is rendered as `**bold**` and `*italic*` emphasis,
  based on font names and the italic font flag. Letters in math italic fonts
  count as italic; other math fonts and a document's body style are ignored.
  Headings and bold front-matter paragraphs get no additional bold, nor
  italics covering all of their text. Emphasis is adjusted so Markdown renders
  it as intended: list, quote, and page markers stay outside, and punctuation,
  symbols, or scripts at its edges move outside where a delimiter could not
  open or close otherwise.
- Numbered footnotes are collected into Notes sections, with separate groups
  when numbering restarts, original list labels, and a `--notes-title` option.
  Recognized continuation paragraphs and notes spanning adjacent pages retain
  their text and source-page markers. Existing endnotes are left in place.
- Paragraphs and block quotes continuing at the top of the next column or page
  are joined, using typography, line geometry, the document's paragraph
  indentation, and weaker textual cues. Words split across the boundary are
  repaired, and page markers are placed within the joined text after the
  repaired word.
- Inference of missing Arabic and Roman visible page labels when the
  surrounding sequence is unambiguous.
- A `-m`/`--page-markers` option that embeds raw and visible PDF page numbers
  at page boundaries in Markdown output, as in `[[PAGE:7|VISIBLE:9]]`. The
  markers render as plain text in Markdown viewers and HTML. A parenthesis
  directly following a marker is escaped, so it does not form a link, as is
  the second bracket of `[[PAGE:` in the source text.

### Changed

- Titles set in several ragged or centered lines are kept as one heading,
  even when `pdftext` splits them into separate blocks or their extracted
  sizes vary slightly. Fragments of one physical line in the same font face
  are kept together despite size differences caused by superscripts.
- A change of both font size and face after a short line now starts a new
  block when one of the lines is larger than body text, separating author
  names from affiliations or a heading from the following text.
- Blocks without letters or digits never become headings.
- Glyphs from icon fonts, such as FontAwesome e-mail and ORCID symbols next to
  author names, are removed.
- Large delimiters, operators, radicals, and wide accents from TeX math
  extension fonts (Computer Modern and Latin Modern) are decoded when the PDF
  lacks a Unicode mapping for them, so `Ω(n log …)` no longer loses its
  parentheses and `P̂` no longer reads `Pb`. Pieces of extensible delimiters
  are left unchanged.
- Inline fractions set with the numerator above the denominator, such as
  `IDmax/n` or `1/2` in running text, are written with a slash on one line
  instead of spreading over three. Compound denominators are parenthesized.
  Scripts stacked above each other, which are left-aligned rather than
  centered, are not affected. The `-lines.csv` dump gains a
  `fraction_denominator` column.
- Scripts that `pdftext` separates from their line are reattached. This
  covers a subscript set below a superscript, as in `R` with `i` above `∗`,
  and a script that `pdftext` puts into a block of its own, which used to end
  up after the paragraph.
- A single uninterrupted footnote sequence is collected at the document end
  under H2. Multiple groups prefer section boundaries reflecting their scope,
  without skipping boundaries associated with numbering restarts. Notes titles
  default to H2/H3 and match deeper following headings when needed to prevent
  accidental parentage. Nearby restarts can place old notes before a mid-page
  heading above their footnote area. Groups sharing a boundary use one Notes
  title with separate lists, retaining original numbers and pages.
- Centered uppercase and small-cap titles can now be recognized from their
  typography and surrounding layout even when their extracted size is below
  body size. Confirmed titles stay together across extraction blocks and take
  precedence over block quotes. Short centered italic labels above smaller
  notes or references are separated from the following text and recognized as
  headings.
- Header and footer detection is now more robust.
- Missing page labels are filled when the nearest printed labels on either
  side predict the same numbering. At document edges, an agreeing pair of
  printed labels supports backward or forward extrapolation. Conflicting
  predictions across excerpt jumps or numbering changes remain unknown.
- Running footer detection now measures repetition within local page ranges
  and alternating recto/verso pages, tolerates short OCR-damaged page-label
  suffixes, and can join nearby Roman-number anchors across opposite edges.
- Indented attributions following block quotes now remain part of the quote.
- Paragraph boundaries now combine `pdftext` block hints with page-local font
  size and family, line spacing, indentation, alignment, and line-length
  evidence. New boundaries are not introduced solely by changes between font
  faces such as regular and bold.
- Repeated hanging-indent regions are now learned per page and column, so
  outdented first lines start paragraphs while indented reference
  continuations remain attached.
- Words split by line-final hyphens are now rejoined within detected blocks,
  using document-wide spelling evidence and conservative fallback heuristics
  to retain lexical hyphens. Coordination hyphens are preserved using link
  words learned from explicit same-line patterns in the document.
- Unspaced en and em dashes split across lines are now rejoined within
  detected blocks.
- Multi-column page regions are now ordered column by column while full-width
  and ambiguous regions retain their existing order.
- Bold embedded-font names are used when PDFs report zero font weights, while
  slightly enlarged multiline metadata blocks no longer become headings.
- Detached, geometrically positioned diacritics from older TeX-generated PDFs
  are now combined with their base letters before line text is assembled.
- `--dump-pagenos` now always writes one row per PDF page, using `?` where no
  visible page label can be detected or safely inferred.

### Fixed

- Whitespace-only lines reported by `pdftext` no longer produce empty blocks
  or stray empty lines in the Markdown output, nor split paragraphs.
- Lines that `pdftext` splits at superscripts, font changes, or math no longer
  produce stray line breaks within paragraphs. Their pieces are joined with a
  space where `pdftext` reports one or a word gap separates them, and directly
  where they touch, as in `word¹, more`. Widely separated pieces, such as
  table cells, stay on separate lines. Superscripts and subscripts split off
  this way are now detected against the neighboring text, so markers such as
  `OSeO₃⁵¹.` no longer read as ordinary digits. The `-lines.csv` dump gains
  `space_before` and `space_after` columns.
- Spurious `pdftext` block edges after such split lines no longer start a new
  paragraph mid-sentence. The left edge of the whole visual line, rather than
  of its last piece, now decides whether the text continues.
- Text continuing a line at the same size no longer starts a new block at a
  `pdftext` block edge just because its font face differs, as after a run-in
  theorem label. Pieces of a line centered on a tall delimiter, rather than
  sharing its top, now also count as one line.

## 0.1.0 - 2026-07-09

### Added

- Initial release.
- PDF-to-Markdown extraction of paragraphs, headings, and indented block
  quotes.
- Detection and removal of repeated headers and footers.
- Tracking of raw PDF page numbers and detected visible page labels.
- Optional line-level and page-number diagnostic CSV files.
