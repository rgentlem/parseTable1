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

3. [x] Normalize text for clustering
   - Collapse whitespace and remove volatile page numbers only as matching features.
   - Keep raw text unchanged in the artifact.
   - Avoid vocabulary-specific cleanup.
   - Implementation: `normalize_page_furniture_text()` writes the matching key used in observations.

4. [x] Cluster repeated text by content and location
   - Group text observations with similar normalized text and overlapping page-relative regions.
   - Require recurrence across multiple pages, such as at least 3 pages or at least 50-70% of pages.
   - Evaluate all-page, odd-page, and even-page recurrence because printed running headers can alternate by page parity.
   - Record matched page numbers and representative bbox.
   - Implementation: `cluster_page_furniture_observations()` returns in-memory clusters and ignored regions.

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
   - Review found repeated interior table values/model-note lines; clustering now requires an edge-band location to avoid suppressing body/table-note text later.

8. [x] Integrate into footnote finding
   - Pass page-furniture regions into cell text annotation and footnote PDF-block harvesting before those artifacts are built.
   - Remove repeated-furniture characters before grouping table-cell markers or PyMuPDF definition blocks.
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
