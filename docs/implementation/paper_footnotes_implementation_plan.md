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
   - Detect table-local note/footer lines from extracted table geometry and
     positioned `paper_text_stream.json` line groups near table bounds.
   - Detect caption-attached notes.
   - Do not promote generic page-bottom or body-text blocks into this
     table-local artifact.
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
   - Feed PyMuPDF page text blocks through geometry-based table-footer
     classification before definition parsing.

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
   - Follow-up fix: `metabolic` Table 1 p-value markers now resolve because PyMuPDF text-block harvesting keeps embedded definitions such as `significance. a Represents ... b Represents ...` when they classify as local table notes.
   - Follow-up fix: `stroke` Table 1-3 statistical-significance asterisks now resolve because repeated asterisk runs are preserved on anchors and comma-separated footer definitions are split into `*`, `**`, and `***` records.
   - Review note: page-note candidates can include journal/download boilerplate and repeated marginal text; keep links review-only until pruning is improved.

11. [x] Review before consuming links
   - Inspect R outputs on several real papers.
   - Only after review, decide whether any downstream parser stage should consume footnote links.
   - Decision: do not consume links downstream yet; keep `paper_footnotes.json` and `ObservedFootnotes` as review artifacts.
   - Reviewed examples: `OPEandRA` showed resolved same-table note links; `metabolic` originally showed unresolved p-value marker anchors and now resolves its embedded `a`/`b` Table 1 notes; `stroke` originally showed unresolved statistical-significance stars and now resolves local `*`/`**`/`***` footer definitions; the CKD paper showed ambiguous repeated `*` definitions; the Eke periodontitis paper showed noisy page-note candidates from journal/download boilerplate.

12. [x] Add pre-footnote math/unit notation rejection
   - Before promoting cell-text annotations into `FootnoteAnchor` records,
     reject obvious mathematical notation such as `10^9`, `10^6`, `m^2`,
     `cm^3`, `kg/m^2`, and `×10^9/L`.
   - Use structural text context only: numeric base, multiplication-by-ten
     patterns, slash-separated units, or unit-like tokens adjacent to the
     superscript/subscript.
   - Keep the original evidence visible in `cell_text_annotations.json`; do not
     erase the marker from extraction artifacts.
   - Add focused tests from the `stroke` row-label unit-exponent pattern.
   - Implemented: `paper_footnotes.json` metadata now records
     `math_unit_anchor_suppression_count`; the 2026-07-01 stroke spot check
     suppresses 7 unit/exponent candidates before footnote linking.

13. [x] Retire conventional p-value star fallback interpretation
   - Current pass preserves observed markers and explicit links only.
   - Asterisks in p-value context remain unresolved when no explicit local
     definition is found.
   - Conventional p-value-star thresholds belong in a later interpretation
     layer that consumes preserved anchors and table-local note blocks.
   - The earlier inferred-link tests were removed because they encoded an
     interpretation behavior outside the current artifact scope.

14. [x] Accept known symbol-marker footer definitions without semantic body checks
   - Treat `†`, `‡`, `§`, `¶`, `#`, `|`, and asterisk runs as structural
     footnote-definition markers when they start a local table/footer definition
     followed by any non-empty body text.
   - Keep stricter body-start filtering for letter and numeric marker lines,
     where false positives are more common.
   - Do not add p-value-specific requirements to definition harvesting.
     P-value semantics belong in a later interpretation layer, not this
     extraction/link artifact.
   - Implemented: the 2026-07-01 corpus run in
     `outputs/testpapers_footer_blocks_20260701_final` resolves the
     `cardiovascular` Table 1 double-dagger footer and the anthropometric CKD
     dagger/star footer definitions.

15. [x] Build table-local footer definitions from extracted table rows
   - Harvest definition source lines only from the matching final
     `TableRegion.footer_note_rows`, using extracted row order.
   - Append adjacent non-marker rows to the current marker definition block so
     multiline footers preserved by rotated extraction are not truncated to one
     PyMuPDF text line.
   - Prefer same-table extracted-footer definitions over same-table PDF-text
     definitions during linking, so global PDF-text duplicates do not make a
     fuller table-local definition ambiguous.

16. [x] Add a table-footer line-group finder for positioned text geometry
   - Consume page-furniture-filtered `paper_text_stream.json` lines rather than
     running a separate PDF block parse.
   - Start only from the positioned lines attached to the final retained rule
     by `TableBoundaryProposal.following_text_line_ids`; do not scan arbitrary
     styled text below the table bbox.
   - Let `TableRegion` accept that adjacent group through the unified footer
     detector. The footnote consumer must not requalify it from markers, local
     type, or line count. Same-font size differences of at most 0.2 PDF points
     remain harmless while the proposal collects adjacent line evidence.
   - Carry final accepted resolved-table visual IDs into footnote scoping so a
     footer on an uncaptioned terminal fragment can resolve anchors from earlier
     fragments of the same visual table.
   - Split distinctive symbol markers inside one footer block, including glued
     forms such as `†Education` and comma-separated forms such as `*`, `**`,
     `***`.
   - Persist filtered PDF-classified table-footer blocks as unsplit
     `footers` records before splitting them into definition records, so R
     review can inspect the same footer region that supplied definitions.
   - Filter R table-specific footnote review by visual ID as well as table ID,
     so continued-table footers remain visible when reviewing the first
     fragment's table number.
   - Implemented: the 2026-07-01 corpus run in
     `outputs/testpapers_footer_blocks_20260701_final` resolves the Planetary
     Health Table 1 `*`, `†`, `‡`, and `§` links and keeps stroke and
     anthropometric CKD explicit footer links resolved.

17. [x] Align table-cell anchor identity and physical-line-start definitions
   - Reuse `CellTextAnnotation.annotation_id` directly for promoted table-cell
     anchors and retain the annotation type in anchor evidence; do not create a
     second table-position/index identity.
   - Keep definition markers as separate positioned evidence. Accept an exact
     smaller-raised marker at the beginning of its own physical source line
     without requiring punctuation on the preceding physical line.
   - Preserve the complete raw footer group and explicit-only resolution rule.
   - Implemented: `outputs/testpapers_batch_phase_k_step2_final_20260715`
     changes only `hypertension.pdf`, PDF page 6, printed Table 2 from
     unresolved to resolved, producing 347 resolved and 53 unresolved links.

18. [x] Use final resolved-table membership for continuation scope
   - Pass `ResolvedTableSet` through the existing anchor, footer, definition,
     and linking functions; remove their dependency on
     `Table1ContinuationGroup`.
   - Admit a cross-fragment `same_visual` candidate only when both source table
     IDs belong to the same accepted `integrated_continuation`; rejected
     continuations fail closed.
   - Keep exact-table, same-page, and paper-level ranking unchanged.
   - Implemented: `outputs/testpapers_batch_phase_k_step3_final_20260715`
     preserves all 94 cross-fragment links and assigns accepted printed Table
     2–4 visual IDs to the terminal footers in `periodontis2.pdf`.
