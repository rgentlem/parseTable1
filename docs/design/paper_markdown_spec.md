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
repeated furniture lines, partitions each page by writing direction, projects
rotated groups into upright local coordinates, and orders positioned source
blocks by page, orientation group, detected group-local column, and block top.
`paper_markdown.md` is rendered from that filtered stream.

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
- do not use a heading-name list to assign heading roles
- avoid using the references or bibliography as a primary source for paper-level variable inventory
- treat references/bibliography as a separate document section, not as table
  content; bibliography extraction should keep each citation as an atomic
  `BibliographyEntry` rather than tokenizing references into table rows or
  variable mentions

## Relationship To Section Parsing

`paper_markdown.md` is a persisted view over structured positioned-text
evidence.

`paper_text_stream.json` is the layout-aware document-context artifact. It
records orientation groups, group-local column boundaries and bands, original
source line IDs/page-space bboxes, canonical bboxes, per-line geometry/style,
minimal source span records, and typed `PaperTextBlock` records. Each block
stores its document order, page, source block index, orientation-group ID,
orientation, exact page-space and canonical union bboxes, column index and
count, ordered line IDs, role, and text. Typography remains on the block's
source lines and spans rather than being duplicated. The raw positioned
document remains unchanged; the canonical orientation is a derived
reading-order projection.

Each block also records a non-operative `prose_candidate` decision. Positive
body evidence requires upright orientation, consecutive block-local source
lines, exact containment in the observed column extent, one font name, and a
within-block largest-minus-smallest line font-size span below 0.5. Independent
paragraph evidence requires the selected body style and a completed sentence
before a later source line. Confirmed headings may open that prose flow across
a layout change within the same page orientation group. Blocks already marked
as full-width are treated as spanning but cannot independently establish
paragraph evidence. Unfinished accepted prose may continue across a page,
column, or spanning-layout change, including across one intervening spanning
residual block. Arbitrary body blocks are not promoted into headings, and
opaque font names are not interpreted. Body candidates do not yet filter
sections or Markdown.

The extraction caption path consumes this stream directly. Caption labels are
recognized from line/span evidence, bound to table candidates in the canonical
orientation-group frame, and expanded through adjacent lines only until table
rule geometry begins. Backend text boxes and backend page-text caption
fallbacks are not caption sources. Raw line text and page coordinates remain
unchanged in the stream even when span order or font separation provides the
evidence needed to recognize a label.

`paper_sections.json` is built directly from the ordered blocks in that
layout-aware stream. Each section stores its heading block ID and ordered body
block IDs, and its content is assembled from those body blocks. Markdown is a
view of the same blocks and is not the source of section structure. The parser
no longer falls back to backend markdown when positioned text cannot be read.

Heading roles are assigned from the positioned typography after the paper body
font profile is available. Every visible span on the line must be bold and the
line font size must be strictly greater than the dominant body font size. A
table-caption line is excluded, as is an entirely bold source block containing
completed sentence prose. General heading text is not matched against a
vocabulary. Separately, exact whole-line `References`, `References and Notes`,
`Bibliography`, `Works Cited`, and `Literature Cited` labels become headings
when the existing bibliography parser confirms an immediately following
reference list. After these final roles are available, each source block is
split at heading/body transitions into ordered logical blocks. Split blocks
retain their source block index and ordered line provenance; only their block
ID, union bbox, role, and text reflect the segment. This occurs before Markdown
rendering.

Page furniture filtering removes repeated running headers, footers, watermarks,
and similar recurring non-content lines. It should not be used as the semantic
section classifier for arbitrary one-off headings. Section construction should
preserve the original heading text while mapping headings into broad paper roles
such as abstract, introduction/background, methods, results, discussion,
conclusion, references, and other.

If section-parsing logic changes, this document and the section-parsing design notes should be updated in the same change.
