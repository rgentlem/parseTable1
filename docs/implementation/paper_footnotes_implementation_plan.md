# Paper Footnotes Implementation Plan

Short checklist for adding paper-level footnote extraction and linking.

Scope:

- produce a structured `paper_footnotes.json` artifact
- link anchors to definitions by canonical glyph key and local scope
- expose R inspection objects aligned with `tableone` style
- keep value parsing and symbol semantics unchanged for now

Non-scope:

- do not rewrite cell text or parsed values
- do not infer domain-specific footnote meanings
- do not add synthetic-paper tests as the main evidence

## Steps

1. [x] Define the artifact contract
   - Add a concise design note for `paper_footnotes.json`.
   - Define anchor, definition, link, and metadata records.
   - Use explicit source scopes: table cell, table caption, table note, figure caption, page note, body text.
   - Include glyph fields: raw glyph, canonical glyph key, glyph kind, codepoints, confidence.
   - Design note: `docs/design/paper_footnotes.md`.

2. [x] Add Python schemas
   - Add Pydantic models for `FootnoteAnchor`, `FootnoteDefinition`, `FootnoteLink`, and `PaperFootnotes`.
   - Keep geometry fields optional but typed.
   - Preserve source IDs back to table IDs, page numbers, row/column indices, and text blocks.

3. [x] Build anchor inventory
   - Start from `cell_text_annotations.json` for table cells, row labels, and headers.
   - Add caption/title anchors when geometry or extracted text makes them available.
   - Preserve unresolved anchors; do not drop weak evidence.

4. [x] Extract definition candidates
   - Detect table-local note lines near table bounds.
   - Detect page-bottom notes and caption-attached notes.
   - Record raw text, cleaned text, bbox, page, source kind, and source ID.

5. [x] Canonicalize glyph keys
   - Normalize common footnote glyphs into stable keys.
   - Keep raw glyph and codepoints beside the key.
   - Do not assign semantic meanings such as statistical tests or data-source notes.

6. [x] Link anchors to definitions
   - Prefer same table, then same visual object, then same page, then paper-level matches.
   - Emit link confidence and link basis.
   - Preserve ambiguous and unresolved cases as structured records.

7. [x] Write parse output
   - Add `paper_footnotes.json` to the parse artifacts.
   - Include an empty valid artifact when no candidates are found.
   - Update parse walkthrough and output docs when the file is emitted.
   - Feed PyMuPDF page text lines into definition candidates for table-local notes and page-bottom notes.

8. [x] Add R loading and data frames
   - Load `paper_footnotes.json` in `load_paper_outputs()`.
   - Add `footnote_anchors_df()`, `footnote_definitions_df()`, and `footnote_links_df()`.
   - Add compact `show_paper_footnotes()`.

9. [x] Add tableone-aligned R object
   - Add `ObservedFootnotes` as an S3 list with `Anchors`, `Definitions`, `Links`, and `MetaData`.
   - Use `printToggle`, `quote`, and `noSpaces` conventions where useful.
   - Attach table-specific links to `ObservedTableOne$Footnotes`.

10. [x] Test on real papers
   - Use papers with existing cell-text annotations first.
   - Include table footnotes, page notes, and caption-adjacent notes when available.
   - Verify the artifact can represent unresolved and ambiguous links.
   - Real-paper pass: 28 fixture PDFs parsed without CLI failures. Generated artifacts included resolved table-note links, unresolved p-value marker anchors, and ambiguous glyph-key matches.
   - Review note: page-note candidates can include journal/download boilerplate and repeated marginal text; keep links review-only until pruning is improved.

11. [x] Review before consuming links
   - Inspect R outputs on several real papers.
   - Only after review, decide whether any downstream parser stage should consume footnote links.
   - Decision: do not consume links downstream yet; keep `paper_footnotes.json` and `ObservedFootnotes` as review artifacts.
   - Reviewed examples: `OPEandRA` showed resolved same-table note links; `metabolic` showed unresolved p-value marker anchors; the CKD paper showed ambiguous repeated `*` definitions; the Eke periodontitis paper showed noisy page-note candidates from journal/download boilerplate.
