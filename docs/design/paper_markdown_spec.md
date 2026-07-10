# Paper Markdown Spec

This document defines the intent of `paper_markdown.md`, the paper-level markdown artifact written by `table1-parser parse`.

## Purpose

`paper_markdown.md` is the lightweight markdown view rendered from
`paper_text_stream.json`. The canonical ordered document-context source for
sections, bibliography extraction, visual references, variable inventory, and
table-context retrieval is the shared PyMuPDF positioned geometry pass persisted
as `paper_positioned_document.json` and projected through
`paper_text_stream.json`.

It exists to support:

- section detection
- `Table X` reference retrieval
- table and figure caption/reference inventory building
- variable and column-context retrieval
- paper-level candidate variable inventory building
- later LLM semantic interpretation

It is not the source of truth for table grid syntax.

## Source

The file is produced from:

- `paper_positioned_document.json`
- `paper_page_furniture.json`
- `paper_text_stream.json`

The parser builds one shared PyMuPDF positioned-document pass first. Page
furniture detection consumes that shared evidence, extraction and cell
annotation consume its words/chars/rules, then `paper_text_stream.json` filters
repeated furniture lines and orders text by page, detected column, and vertical
position. `paper_markdown.md` is rendered from that filtered stream.

There is no `pymupdf4llm.to_markdown(...)` fallback. If PyMuPDF positioned text
cannot produce the paper text stream, the parser should fail closed rather than
building downstream document-context artifacts from a second markdown path.

## Output Path

```text
outputs/papers/<paper_stem>/paper_markdown.md
```

## Design Rules

- Preserve the full-paper markdown view rendered from the filtered text stream.
- Allow only conservative repair of a small set of known extractor glyph-to-Unicode failures in text, such as a replacement character standing in for a threshold comparator.
- Do not rewrite it into a table-specific format.
- Do not use it as a replacement for `ExtractedTable` or `NormalizedTable`.
- Keep it paired with:
  - `paper_text_stream.json`
  - `paper_sections.json`
  - `paper_visual_inventory.json`
  - `paper_references.json`
  - `paper_style_profile.json`
  - `table_contexts/table_<n>_context.json`

## Expected Variation

The markdown will vary across papers.

Examples:

- section names may be `Methods`, `Study Design`, `Patients and Methods`, or something else
- heading levels may be inconsistent
- table references may appear as `Table 1`, `Table1`, or prose references
- some PDFs will have weak or imperfect heading markup
- footnotes and captions may be separated from the main table text

The pipeline should therefore:

- preserve the rendered markdown view with only conservative glyph repair
- treat these repairs as extractor-symbol recovery, not as a general-purpose file-encoding pass
- derive layout-aware structure in `paper_text_stream.json` and
  `paper_sections.json`
- derive actual in-paper table/figure objects in `paper_visual_inventory.json`
- derive anchored prose mentions in `paper_references.json`, resolving them against the visual inventory rather than assuming every `Figure X` mention belongs to this paper
- derive paper-level marker, caption, and reference-style summaries in
  `paper_style_profile.json` from the structured paper artifacts
- tolerate section-name variation
- avoid hardcoding exact heading names as the only way to find methods-like or results-like content
- avoid using the references or bibliography as a primary source for paper-level variable inventory
- treat references/bibliography as a separate document section, not as table
  content; bibliography extraction should keep each citation as an atomic
  `BibliographyEntry` rather than tokenizing references into table rows or
  variable mentions

## Relationship To Section Parsing

`paper_markdown.md` is a persisted view over structured positioned-text
evidence.

`paper_text_stream.json` is the layout-aware document-context artifact. It
records page-level column boundaries and bands, per-line geometry/style, and
minimal span records, then orders text as page, column, then vertical position.
This column-order model is independent of whether a page has one, two, three,
or more detected text columns.

`paper_sections.json` is the structured interpretation of that layout-aware
stream. The parser no longer falls back to backend markdown when positioned text
cannot be read.

Page furniture filtering removes repeated running headers, footers, watermarks,
and similar recurring non-content lines. It should not be used as the semantic
section classifier for arbitrary one-off headings. Section parsing should
preserve the original heading text while mapping headings into broad paper roles
such as abstract, introduction/background, methods, results, discussion,
conclusion, references, and other.

If section-parsing logic changes, this document and the section-parsing design notes should be updated in the same change.
