# Changelog

All notable, user-visible changes to frompdf are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Inference of missing Arabic and Roman visible page labels when the
  surrounding sequence is unambiguous.

### Changed

- Words split by line-final hyphens are now rejoined within detected blocks,
  using document-wide spelling evidence and conservative fallback heuristics
  to retain lexical hyphens.
- Multi-column page regions are now ordered column by column while full-width
  and ambiguous regions retain their existing order.
- Bold embedded-font names are used when PDFs report zero font weights, while
  slightly enlarged multiline metadata blocks no longer become headings.
- Detached, geometrically positioned diacritics from older TeX-generated PDFs
  are now combined with their base letters before line text is assembled.
- `--dump-pagenos` now always writes one row per PDF page, using `?` where no
  visible page label can be detected or safely inferred.

## 0.1.0 - 2026-07-09

### Added

- Initial release.
- PDF-to-Markdown extraction of paragraphs, headings, and indented block
  quotes.
- Detection and removal of repeated headers and footers.
- Tracking of raw PDF page numbers and detected visible page labels.
- Optional line-level and page-number diagnostic CSV files.
