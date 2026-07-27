# Paper Page Furniture Implementation Plan

Short checklist for detecting repeated non-table page text before footnote
linking consumes page geometry.

Scope:

- produce `paper_page_furniture.json`
- detect text that recurs in nearly the same page-relative region
- keep detection structural: repeated text plus stable position
- use the artifact first to protect extraction, then footnote harvesting

Non-scope:

- do not hard-code publisher names, journal names, URLs, or watermarks
- do not remove one-off table notes or page notes
- do not hard-code extraction cleanup around specific publisher boilerplate

## Steps

1. [x] Define the artifact contract
   - Add schemas for page text observations, recurring clusters, ignored regions, and metadata.
   - Store page number, raw text, normalized text, bbox, page-relative bbox, orientation, recurrence counts, and confidence.
   - Keep ignored regions generic; classification such as header, watermark, or footer is not needed for footnote suppression.
   - Design note: `docs/design/paper_page_furniture.md`.
   - Python schemas: `table1_parser/schemas/paper_page_furniture.py`.

2. [x] Collect positioned page text
   - Reuse PyMuPDF page text geometry.
   - Preserve raw lines/spans and page dimensions.
   - Normalize coordinates to fractions of page width/height.
   - Collector: `table1_parser/paper_page_furniture.py`.

3. [x] Preserve ordinary text and gate page-number templates
   - Collapse whitespace in `normalized_text` while preserving every observed
     integer and the exact `raw_text`.
   - Create one non-operative candidate for each standalone integer, masking
     only that slot in the candidate template.
   - Group candidates by template and orientation through positive common
     intersection of page-relative source bboxes; reject ambiguous membership.
   - Accept only groups with one observation on each of at least two distinct
     pages, one constant `slot value - PDF page number`, no duplicate page, and
     complete all-page, even-page, or odd-body-page coverage.
   - Feed only accepted templates into the canonical clustering pass. Rejected
     candidates retain ordinary full-text matching.
   - Avoid vocabulary-specific cleanup or a second mask path.

4. [x] Cluster repeated text by content and location
   - Group exact ordinary text or an accepted candidate template, with matching
     orientations, only while every page-relative source bbox retains one
     positive common intersection. Do not round coordinates or use a distance,
     overlap-fraction, or IoU threshold.
   - Evaluate all-page, even-page, and odd-body-page recurrence independently.
     Require complete coverage of the accepted scope and reject partial parity
     sequences and arbitrary subsets.
   - Record matched page numbers and representative bbox.
   - Implementation: `cluster_page_furniture_observations()` returns in-memory clusters and ignored regions.
   - The common-intersection cutover completed all 28 corpus PDFs without
     removing an accepted furniture line or changing extracted table IDs,
     pages, dimensions, cell text, or cell bboxes.

5. [x] Emit `paper_page_furniture.json`
   - Write a valid empty artifact when no repeated furniture is found.
   - Add the file to parse outputs and output docs.
   - Include diagnostics explaining thresholds and skipped candidates.
   - Implementation: `table1-parser parse` writes the `PaperPageFurniture` payload for every paper.

6. [x] Add R inspection helpers
   - Load the artifact in `load_paper_outputs()`.
   - Add compact data-frame and print helpers for recurring clusters and ignored regions.
   - Implementation: `page_furniture_clusters_df()`, `page_furniture_regions_df()`, and `show_paper_page_furniture()`.

7. [x] Test on real papers
   - Use Eke and other papers with download notices, marginal text, page numbers, and running headers.
   - Verify table notes and one-off page notes are not classified as furniture.
   - Verify repeated regions are stable enough to suppress only their own text.
   - Real-paper pass: 28 PDFs, 0 failures. Eke, metabolic, Ethnic Differences, periodontis2, cobaltpaper, and OPEandRA were included.
   - Current evidence-gated page-number checkpoint:
     `outputs/testpapers_batch_page_number_substitution_20260727`. All 28 PDFs
     parse successfully; no accepted mask is lost; established counters retain
     final two-digit pages; and 10 newly masked lines across eight papers are
     recurrent furniture recovered from the old unconditional substitution.
     Extracted table IDs, pages, dimensions, cell text, and cell bboxes are
     unchanged.

8. [x] Integrate into footnote finding
   - Pass page-furniture regions into cell text annotation and text-stream footer detection before those artifacts are built.
   - Remove repeated-furniture characters before grouping table-cell markers or footer line groups.
   - Do not keep separate late footnote cleanup paths for overlapping table-cell anchors or definition lines.
   - Implementation: `paper_footnotes.json` records `page_furniture_filter_stage`, while the source character and table-row filtering happens before anchor and definition construction.

9. [x] Integrate before table extraction
   - Build `paper_page_furniture.json` before `extract()` in the `parse`,
     `extract`, and `normalize` flows.
   - Pass ignored regions to the extractor as page-coordinate mask evidence.
   - Remove repeated page-furniture words and chars before text-position,
     rescue, rotated, or sideways reconstruction consumes them.
   - Remove explicit-grid rows only when most populated cell bboxes are mostly
     inside ignored regions.
   - Record `metadata.page_furniture_overlap` for candidate bboxes that touch
     ignored regions and `metadata.page_furniture_mask` when extraction evidence
     was actually removed.
   - Retire broad large-gap/text-spread trailing-row cleanup after the final
     value row; `metadata.trailing_non_table_rows` now records only explicit
     trailing continuation-page notes.

10. [x] Establish and apply the paper page scope
   - Store the sole typed page-length authority on `PaperPageFurniture`.
   - Accept the first recurrent `N of M` or `N / M` candidate only when its
     terminal `M of M` observation is present; otherwise include every page.
   - Use the included page set for furniture recurrence and one early in-memory
     positioned-document projection consumed by all later stages, while keeping
     the persisted raw positioned document complete.
   - Corpus checkpoint: `outputs/testpapers_batch_paper_scope_20260727` parses
     all 28 PDFs. The 10-page paper followed by appended PDF page 11 retains
     that page only in raw evidence; all 14 detected full-length papers and 13
     unknown-scope papers retain every physical page.
   - Ninety-one of 92 physical tables exactly match the preceding grid and cell
     baseline. The only difference is one empty row removed from PDF page 3,
     printed Table 1 of the appended-page paper after its recurrent journal
     header, footer, and `3 of 10` counter become included-page furniture.

## Current Decisions And Deferred Recovery

- Text clusters use complete all-page, even-page, or odd-body-page coverage,
  matching orientation, and positive common bbox intersection. Page-number
  candidates use the same recurrence geometry and complete-scope gate; there
  is no coordinate tolerance, vocabulary rule, or separate masking path.
- Positioned words and characters are removed by exact PyMuPDF block/line
  provenance when available. Bbox masking is reserved for objects, such as
  explicit grid cells, that lack source-line identity. This prevents a
  horizontal furniture line from deleting characters belonging to a rotated
  table that crosses the same page-space bbox.
- Deferred option: after a furniture cluster has first been established by
  strict recurrence and edge evidence, search the remaining pages for the same
  normalized text in a wider nearby region. Such a pass may add occurrences to
  an already proven cluster; it must not broaden initial candidate discovery.
  No such recovery pass is implemented because the current corpus does not
  require it.
- Page length remains unknown when no accepted recurrent current/total counter
  includes its terminal observation. Unknown scope intentionally retains all
  physical pages rather than inferring a boundary from weaker evidence.
