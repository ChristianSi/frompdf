# Changelog

All notable, user-visible changes to frompdf are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
  starts. Escapes are limited to where they are needed. List markers at the
  start of a block remain unescaped, so lists in the source still render as
  lists.
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
  at page boundaries in Markdown output, using `|VISIBLE:` to introduce visible
  labels.

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

## 0.1.0 - 2026-07-09

### Added

- Initial release.
- PDF-to-Markdown extraction of paragraphs, headings, and indented block
  quotes.
- Detection and removal of repeated headers and footers.
- Tracking of raw PDF page numbers and detected visible page labels.
- Optional line-level and page-number diagnostic CSV files.
