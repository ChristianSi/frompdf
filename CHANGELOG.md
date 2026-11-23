# Changelog

All notable, user-visible changes to frompdf are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Scanned documents with an OCR text layer are read with the geometry of
  their scans. OCR layers only estimate where their lines end and how large
  their type is, and often drop the hyphens ending lines. Each line is now
  measured against the scan below it: where its ink starts and ends, its
  baseline, and the height of its letters, which gives its font size, and a
  hyphen ending the line is restored where the scan shows one. This keeps
  ordinary lines from becoming headings, line breaks from becoming paragraph
  breaks, and the columns of a page apart, and words hyphenated at line ends
  are joined again. Measurements far from where and how large the OCR layer
  typically sets lines are not trusted: a line placed so far off that the
  baseline of a neighboring line was measured is measured again where its
  baseline is expected, and a line whose letter height was misled, as by
  quotation marks, takes the size that its OCR size suggests. The not sign
  `¬`, by which some OCR engines mark words broken at line ends, is read as
  a soft hyphen, so that the parts of such words are joined. The text layer
  of a blank page, where the OCR engine read print showing through from the
  back of the leaf, is dropped. Lines of slightly skewed scans, which OCR
  layers turn by up to a few degrees, are measured like the others. Printed
  lines that the OCR layer sets so close together that they were read as one
  line are split again, as are lines of other PDFs joined because a tall
  glyph such as `✉` lets their boxes overlap.
- Footnotes of scanned documents are recognized. OCR text layers misread the
  superscript numbers labeling notes, or join them to the following word,
  and measured sizes can miss the smaller type of short notes. On scanned
  pages, lines below a rule printed above the notes, or set more closely
  than body text, are taken as notes, too. Notes are told apart by a
  hanging indent and by what OCR makes of their labels, and are numbered in
  order, as are notes marked by `*`, `†`, `‡`, `§`, `‖`, and `¶`, which OCR
  often reads as `t`, `+`, or `X`. Parts of a document set in another body
  size than the rest, such as the introduction of a reprint, are judged by
  their own body size.
- Notes numbered anew on each page, and notes marked by symbols, follow the
  last paragraph starting on their page instead of being collected at the
  end of a section, introduced by a paragraph such as `Notes:`, after the
  notes title. Notes marked by symbols are written as a bulleted list
  starting with their symbols, such as `- \* A note.`. Numbering restarts on
  each page where two pages with notes numbered from 1 follow each other
  without a heading between them.
- Captions set like body text, as in scans whose OCR text layer carries no
  typography, are recognized below pictures when they start with a figure
  label and number, such as `Fig. 3`, `Figure 2.1`, `Abb. 4a`, `Figura IV`,
  `図 3`, or `第2図`, in English, French, German, Spanish, Portuguese,
  Japanese, or Chinese. Captions in other languages are still recognized by
  their typography.
- Numbered items set as paragraphs, whose indented first lines start with
  the number and whose other lines continue at the margin, as numbered notes
  often are, are recognized as list items.
- Centered titles in capitals or italics spanning the columns of a page,
  such as a Notes title over two columns, are recognized as headings.

- The pictures of a document, such as photos, screenshots, plots, and
  diagrams, are written as image files and referenced from the Markdown
  output as `![](file-img/p3-1.png)`. Each picture is cut from its page as
  the PDF shows it, at 300 pixels per inch, together with the text lying
  within it, such as the tick values, axis titles, and legends of plots.
  This text is left out of the Markdown output instead of spilling into the
  flow as scattered paragraphs and headings. Pictures are recognized from
  their drawings alone, in documents of any language and with or without
  captions. Text of the document is never cut into an image: images and
  boxes with running text on them, such as scanned pages with a text layer
  and framed notes, stay text. Logos and other drawings repeated on several
  pages are skipped, as are pictures under 12 cm² without a caption, such as
  small logos and icons. The images of `file.pdf` are written as PNG, or
  JPEG for photos, to the directory `file-img`. They are named by their page
  and their number on it, padded with zeros so they sort in order, such as
  `p03-1.png` in a document of 10 to 99 pages. An existing directory is
  renamed to `file-img.bak`; a directory holding anything but such images is
  never replaced. Like tables, pictures and their captions are left out of
  the flow, so paragraphs interrupted by a picture continue past it, and the
  picture follows them with its caption as one paragraph.
  A caption is the text set directly below a picture in smaller type, or
  starting in bold or italics.
- The new option `-I`/`--no-images` leaves out the image files and the
  references to them. The text within pictures is still left out.
- Tables drawn with rules are rendered as pipe tables. Tables need connected
  horizontal and vertical rules with a vertical rule between columns, as in
  ruled grids or booktabs-style tables with column rules; rules nested in
  scaled or cropped drawings are found as well. Rules missing between cells
  make them span rows or columns. A header cell spanning several columns is
  combined with the labels below it; other spanning cells show their text in
  their first row and column. Rules dividing a cell's text without lining up
  across columns separate its parts by `<br>`, as do paragraphs with hanging
  indents. Tables without vertical rules are recognized from rules above and
  below their header and gaps between columns. Shorter rules within such a
  header, as below labels spanning several columns, divide it into rows and
  give these labels their spans. A label wrapped onto an indented line, with
  nothing beside it in the other columns, stays in its row. Tables
  continuing on the next page are joined, dropping a repeated header and a
  caption marked as continued, and a row split by the page break is joined
  where its text continues. Text around a table no longer runs into it.
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
  Paragraphs reading as a horizontal rule, such as `***`, stay unescaped.
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
  based on font names and the italic font flag. Fonts named by opaque hashes,
  such as `AdvOTcb88df00`, count as bold if their letters are drawn with
  strokes at least 1.4 times as wide as those of the body font, as for the
  bold lead sentences and panel letters of figure captions in Nature
  Communications. Fonts whose names tell no style and for which the PDF
  reports no weight count as bold with strokes at least twice as wide, as the
  black sans-serif face `AdvPSFTBL` of Wiley's subheadings, which thus become
  headings; regular sans-serif faces beside a serif body measure up to about
  1.4 times its stroke width. Letters in math italic fonts count as italic;
  other math fonts and a document's body style are ignored.
  Headings and bold front-matter paragraphs get no additional bold, nor
  italics covering all of their text. Emphasis is adjusted so Markdown renders
  it as intended: list, quote, and page markers stay outside, and punctuation,
  symbols, or scripts at its edges move outside where a delimiter could not
  open or close otherwise. Spans of nothing but punctuation are dropped.
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
- Capitals of the AMS blackboard bold fonts (`msbm`), which these fonts map
  to plain letters, become double-struck letters, as in `R ⊆ ℝⁿ`.
- Tables framed by rules get their captions, which lie right above or below
  them and start with a table label, such as `Table 1`, `TABLE IV`,
  `Tableau 2`, `Tabelle 3`, `Tabla 4`, `Cuadro 5`, `Tabela 6`, `Quadro 7`,
  or `表 8`. A label set like body text must stand alone or be followed by a
  separator, as in `Table 3:`, so sentences such as "Table 3 shows …" are
  no captions.
- Captions of figures and tables are set apart in italics, unless most of
  their text is already bold or italic. Their bold parts, such as a leading
  `**Figure 1.**`, stay as they are, and their italic parts, such as names of
  species or variables, are set upright, as typographers do in italic text.
  Captions are never turned into headings or block quotes.

### Changed

- PDFs that set all text at font size 1 and scale it by the text matrix, as
  those typeset by Advent 3B2, get their real font sizes from the matrix
  instead of from the heights of glyph boxes, which vary between fonts of the
  same size. Section titles such as "Results" and "Methods" in Nature
  Communications, set in bold at the body size, are now recognized as
  headings.
- A heading reading like a section heading, such as "Abstract", ends the
  front matter below a title even where it is set like the author names, so
  it stays a heading.
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
- Math set in the `Adv…` fonts of Advent 3B2 (PTC Arbortext APP), common in
  PDFs from Elsevier, Wiley, and Nature Communications, is decoded. These
  fonts clone TeX's math fonts under wrong glyph names, so `p = 0.03` no
  longer reads `p ¼ 0.03`, `(x + ∞)` no longer reads `ðx þ 1Þ`, and minus
  signs, `∼`, and `·`, which had no Unicode mapping at all, are no longer
  lost. Accents set in these fonts combine with their letters, as in
  `Tielbörger` and `Ravigné`. Lines are no longer broken after symbols with
  font code 2, which `pdftext` takes for a hyphen ending the line, as in
  `τ ∼ c/κ`. The same characters in other fonts, such as real fractions and
  Icelandic letters, are left alone. Advent's pi fonts, which set single
  symbols and Greek letters within text, misname their glyphs too; those
  seen in documents are decoded, so `© 2014`, `two × two`, and `β₀` no longer
  read `ª 2014`, `two 9 two`, and `b₀`. Their other glyphs, whose layouts
  are unknown, are left as they are.
- Inline fractions set with the numerator above the denominator, such as
  `IDmax/n` or `1/2` in running text, are written with a slash on one line
  instead of spreading over three. Compound denominators are parenthesized.
  Scripts stacked above each other, which are left-aligned rather than
  centered, are not affected. The `-lines.csv` dump gains a
  `fraction_denominator` column.
- Display equations broken over several lines, set off from the text, form
  one paragraph with a line break after each line, instead of a mix of
  paragraphs and block quotes. Their first line holds a relation, such as `=`
  or `≤`, and each further line starts with an operator, such as `+`, or
  follows a line ending with one. They never become block quotes or list
  items. Fractions set in full size, as `p/(1 − p)` in such equations, are
  written on one line like inline fractions.
- Superscripts and subscripts are measured against ordinary glyphs of their
  own font, whose boxes match theirs, so subscripts after Greek letters from
  symbol fonts, as in `γ_species` or `μ_quadrat`, are no longer missed or
  split. A piece of text is judged by the size most of its width is set in,
  so the subscript of `1 − p_ijk` is recognized although its glyphs outnumber
  the others.
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
- Running headers and footers whose Roman page number was misread by OCR,
  such as `XU INTRODUCTION` or `INTRODUCTION XVll`, are removed, and their
  page number is recovered. OCR often reads `I` as `l`, `1`, `|`, or `L`, and
  `II` as `U`; such a reading is accepted only if the rest of the line is
  repeated running text and the nearest page numbers predict exactly that
  number.
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
  words learned from explicit same-line patterns in the document. Within
  hyphenated compounds, such as `UNESCO-Kon-ferenz` or
  `christ-lich-anarchistischer`, the parts adjoining the line break are
  joined where the document uses the joined part elsewhere, as a word or as
  part of another compound; otherwise the hyphen is kept, as in
  `difficult-to-remove`.
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

- Bar charts drawn from rules and plain rectangles, as in Wiley's journals,
  are recognized as pictures. Their axes, a horizontal and a vertical rule
  meeting at a corner, now join the bars and the tick values around them,
  which are often drawn as outlines. Before, only their text labels were
  left, as `(A) (B)`.
- Captions set beside their pictures, as in Wiley's journals, are recognized
  where no caption lies below a picture. They must start with a figure label
  and be set as captions, smaller than the body or starting in bold or
  italics, as text beside a picture is often that of another column. Such
  captions were left in the text, often as block quotes.
- Columns set between text spanning them both above and below, as between
  the front matter and a licence footer on the first page of an article, are
  read column by column. Their blocks were left in the order `pdftext`
  reported them, which can start with the second column or interleave a
  sidebar with the abstract beside it.
- Notices running vertically along a page margin, such as the download notice
  that Wiley Online Library prints beside every page, are removed like
  running headers and footers when they repeat on several pages. They split a
  paragraph on every page and, spanning the page height, kept columns from
  being read in order below figures and tables spanning both columns.
- A figure caption no longer runs into the caption of a table or another
  figure that starts on the next line, after a sentence ending. Nor does it
  take in text further left on its last visual line, as a caption in the
  next column starting slightly higher.
- Glyphs that a PDF maps to a list of alternative characters, as the cover
  pages of JSTOR's early journal content map their spaces to a tab, carriage
  return, space, and no-break space, and their hyphens to a hyphen-minus, soft
  hyphen, and hyphen, are read as one space or hyphen. Every word of such
  text was followed by a line break, and every hyphen doubled.
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
- A `pdftext` block edge or font change below a line filling its column no
  longer starts a new paragraph where nothing else marks one: regular spacing,
  no indent, and no item label on the next line. This also holds after an
  indented first line, for lines mostly in italics, and for lines ending a
  sentence if they reach the right edge closely and the font stays the same.
- Indented text above a document's title on the same page, such as a
  letterhead, is no longer rendered as a block quote, but as paragraphs.
- Indented lines centered on each other, with varying left and right edges,
  are no longer rendered as a block quote, as they rather form a caption,
  title, or formula. Right-aligned epigraphs remain quoted.
- A gap about as tall as a blank line now starts a new paragraph even after a
  full line without final punctuation. This separates the parts of a
  small-print letterhead, or a heading from a long source note above it.
- An evenly spaced, left-aligned inset passage, such as a letterhead, no
  longer loses its first line to a `pdftext` block edge when the lines after
  the edge keep the same spacing.
- Verse quoted in prose, set off in smaller type at an inset left edge, is no
  longer split into a mix of paragraphs and partial block quotes, nor merged
  into the paragraph introducing it. Each stanza becomes a quoted paragraph,
  with a hard line break wherever a line leaves room for the next word, even
  before a sentence continuing in lower case. Such a passage is recognized
  when most of its lines leave that room and body text resumes after it.
- Short lines without letters or digits centered in their column, such as
  ornaments ending a chapter or separating sections, are now paragraphs of
  their own rather than lines of the preceding paragraph, list item, or block
  quote, also when they consist of several pieces, like asterisks at staggered
  heights. They are never rendered as block quotes.
- The start of a line no longer follows its continuation where `pdftext`
  puts them into separate blocks and orders the continuation first, as when a
  raised superscript lifts its top. The start now precedes a block that it
  touches on the same line, so definitions, lemmas, and author lists no longer
  come out scrambled, nor partly as headings.
- Short script-sized fragments touching the text of a line, such as the
  superscripts of a formula in a block of their own, no longer start a new
  paragraph within that line. A line ending in such a formula no longer starts
  a new paragraph at a `pdftext` block edge either, as its typography is now
  judged by its start.
- A single indented line split by `pdftext` into several pieces, such as a
  displayed formula with scripts, is no longer rendered as a block quote. Like
  any single indented line, it is only quoted after another block quote.
- Smaller print after a visibly larger gap, such as a licence notice at the
  bottom of a first page, now starts a new paragraph even below a full line
  of body text that does not end a sentence.
- A `pdftext` block edge below a short line no longer starts a new paragraph
  where the next line continues the open sentence in lower case, at the same
  left edge, in the same typography, and at regular spacing. Lines starting
  with a lower-case item label, such as `a)` or `iv.`, are not joined this way.
- URLs and DOIs broken at a line end are joined again without a space, as
  `https://proceedings.mlr.press/…` or `doi:10.1137/…`, also across several
  lines. The next line's first token must have the structure of a URL within
  it or give a value after a `=`; another URL continues only one ending in
  `/`, as in archive URLs. Text following a URL, list numbers, and a note
  marker starting the next line are left alone.
- Stacked math in formulas, such as `Δ^R_f`, fractions like `s/√(s²−f²)`
  whose denominator `pdftext` splits into several records, and limits below
  `argmax`, is no longer split over several lines. Limits follow their
  operator as a subscript. The `-lines.csv` dump gains a `stacked_limit`
  column.
- Superscripts and subscripts within a script are rendered as nested tags,
  as in `argmax<sub>r∈[R]<sup>s</sup></sub>`.
- Superscripts and subscripts that `pdftext` puts into line records of their
  own are now recognized in displayed formulas too, as in `C₀⁽ˢ,ᶠ⁾ Δ^Q`,
  where the scripts of the rest of the line outnumber its ordinary letters,
  or the pieces are reported from right to left. With real font sizes, such
  pieces are judged against the whole line, leaving out its own scripts.
- Accents set as modifier letters, as TeX's `ˆ` and `˜`, now combine with the
  letter below them, also where Unicode has no precomposed letter, as in `v̂`,
  which keeps a combining accent. The word space after such an accent is no
  longer dropped. Italics now include combining accents following an italic
  letter, as in `*P̂*`.
- Text running vertically, such as the axis labels of figures, no longer
  becomes oversized headings in PDFs that report no real font sizes. Its size
  is now measured across the text, by the width of its box, not by the length
  of the text.
- In PDFs that report no real font sizes, lines with subscripts or
  superscripts, as in `GaV₄S₈`, no longer turn into headings or split off from
  their paragraph. A span is now measured by its tallest glyph rather than by
  its box, which also stretches over glyphs raised or lowered against the
  others.
- An indented first line now starts a new paragraph also where it or the line
  before it is split into pieces at inline math or a superscript, as in
  `GaV₄S₈²³.` ending a paragraph.
- Paragraphs continuing at the top of the next column are joined also where a
  caption below a figure spans both columns, which no longer widens the
  column the caption starts in.
- Body text in the second column of a page is no longer quoted as a block
  quote where figure labels lie between the columns, or where the column is
  set in smaller type than the body, as the methods of a journal article.
  Column margins now follow edges shared by several lines of prose, so stray
  labels no longer shift them, and text starting beyond the end of the body
  lines of the column to its left starts another column rather than being
  indented.
- A hyphen ending a line after a single letter is kept, as in `g-tensor`.
- Words that a PDF sets apart without a space glyph get a space, where the
  gap is as wide as the word gaps of their line, as in `GaV₄S₈. a`.

## 0.1.0 - 2026-07-09

### Added

- Initial release.
- PDF-to-Markdown extraction of paragraphs, headings, and indented block
  quotes.
- Detection and removal of repeated headers and footers.
- Tracking of raw PDF page numbers and detected visible page labels.
- Optional line-level and page-number diagnostic CSV files.
