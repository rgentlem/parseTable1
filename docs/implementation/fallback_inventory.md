# Fallback Inventory

This document inventories fallback, rescue, and repair paths that can mask
extraction errors. The current parser direction is to remove most downstream
gyration and make extraction more accurate near the front of the pipeline.

Reference usage counts below come from the latest available 27-PDF real-paper
batch inspected during the fallback audit:

```text
outputs/testpapers_batch_20260708_180516_fallback_cleanup_verify2
```

That output is generated evidence, not source truth. Re-run the corpus before
making removal decisions that depend on exact counts.

## Policy

Do not add new fallback tools, rescue passes, broad cleanup layers, or
downstream shape-repair logic to compensate for poor extraction.

Preferred response to a parser failure:

1. Fix page-furniture filtering, caption binding, table-region ownership, or
   positioned PyMuPDF extraction.
2. Preserve raw extraction evidence and write structured diagnostics.
3. Fail closed when geometry is inadequate.
4. Add downstream interpretation only after extraction has produced the correct
   row/column/caption/footer structure.

Existing fallback paths should be retired, narrowed, or converted into
canonical extraction logic with explicit provenance.

## Extraction And Candidate Recovery

### Keep Or Convert To Canonical Extraction

- `hline_word_positions`
  - Code: `table1_parser/extract/pymupdf4llm_extractor.py::_refine_grid_from_hline_word_positions`
  - Latest usage: 24 tables.
  - Status: keep, but rename mentally from fallback to primary ruled-table
    extraction. It uses positioned words, horizontal rules, value anchors, and
    header-band geometry, which is the intended direction. Ordinary
    `horizontal_rules` may include discontinuous same-y rule positions, but
    `full_width_horizontal_rules` must require a continuous near-edge-to-near-edge
    drawn rule so partial header rules are not misused as body separators.

- `value_matrix_word_positions`
  - Code: `table1_parser/extract/pymupdf4llm_extractor.py::_refine_grid_from_value_matrix_word_positions`
  - Latest usage: 8 tables.
  - Status: keep short-term, then fold into one canonical geometry extractor.
    It is structural and typed, but should not remain a separate rescue branch
    forever.

- `pymupdf_positioned_bbox_words`
  - Code: `table1_parser/extract/pymupdf4llm_extractor.py::_rebuild_grid_from_positioned_bbox_words`
  - Latest usage: 35 tables.
  - Status: keep as canonical positioned extraction for explicit table boxes
    when stronger hline/value-matrix reconstruction does not fire. It uses
    PyMuPDF words/chars/rules inside the rough table region and records
    `canonical_extraction_layer = "pymupdf_positioned_geometry"`.

- Rotated table-local geometry normalization
  - Code:
    - `table1_parser/extract/pymupdf4llm_extractor.py::_build_rotated_block_candidate_from_mixed_table_box`
    - `table1_parser/extract/layout_fallback.py::normalize_positioned_geometry_for_rotation`
  - Latest usage: 1 mixed rotated-block repair; 6 rotated word-position
    refinements.
  - Status: keep, but make this ordinary orientation-aware extraction rather
    than an exceptional recovery path. The older page-wide sideways replacement
    branch has been removed; retained rotated support is table-local and based
    on explicit/mixed table regions plus directional PyMuPDF text blocks.

### Retire Or Replace

- Low-quality page rescue
  - Code: `table1_parser/extract/pymupdf4llm_extractor.py::_rescue_low_quality_page_candidates`
  - Metadata: `layout_source = "pymupdf_text_positions_rescue"`,
    `fallback_used = true`.
  - Latest usage: 0 tables.
  - Status: retired and removed. Explicit table boxes now get a bbox-hinted
    PyMuPDF positioned rebuild; the broad page rescue path should not be
    reintroduced.

- Whole-page PyMuPDF text-position fallback
  - Code: `table1_parser/extract/pymupdf4llm_extractor.py` fallback loop with
    `layout_source = "pymupdf_text_positions"`.
  - Latest usage: 4 tables.
  - Status: replace with canonical positioned PyMuPDF extraction so pages
    without PyMuPDF4LLM table boxes are not a special path.

- Page-wide sideways transformed replacement
  - Metadata: `layout_source = "sideways_text_positions"` and transformed
    full-page candidate geometry.
  - Latest usage: 0 tables.
  - Status: retired and removed. Rotated extraction should stay table-local,
    using explicit/mixed table boxes and PyMuPDF directional text-block
    geometry rather than rewriting a whole page into a separate candidate
    stream.

- Caption-contaminated backend row drop
  - Code: `table1_parser/extract/pymupdf4llm_extractor.py`
  - Metadata: `grid_refinement_source = "caption_contaminated_backend_row_drop"`.
  - Latest usage: 0 tables.
  - Status: retired. Caption/table-region ownership and positioned-grid
    reconstruction now own this case; backend row dropping is no longer an
    emitted extraction path.

- Collapsed explicit-grid word-position rescue
  - Metadata: `grid_refinement_source = "collapsed_explicit_grid_word_positions"`.
  - Latest usage after ruled-body layout hardening and rule-continuity
    classification: 0 tables in
    `outputs/testpapers_batch_rule_continuity2_20260710`.
  - Status: retire after hline/value-matrix or ruled body-layout extraction
    owns collapsed grid reconstruction. Non-rotated three-rule tables with
    agreeing header visual runs and body value starts now use
    `grid_refinement_source = "ruled_body_layout_word_positions"` before this
    older numeric-anchor path is tried. Current blocker: `stroke-p7-t1` now
    reaches the ruled-body path but loses the row-label/value boundary, so the
    next fix should derive that first boundary from drawn rule geometry and
    body text positions rather than from header-run ordering.

- Special model/estimate `word_positions_with_horizontal_rules`
  - Metadata: `grid_refinement_source = "word_positions_with_horizontal_rules"`.
  - Latest usage: 0 tables.
  - Status: retired and removed. The former GOLD Table 3 case now emits the
    same 13 x 11 grid through the general `pymupdf_positioned_bbox_words` path
    instead of a model/estimate-specific refinement.

- Backend JSON cell grid survival
  - Metadata: `geometry_source = "pymupdf4llm_json_table_cells"`,
    `canonical_extraction_layer = "pymupdf4llm_backend_grid_noncanonical"`.
  - Latest usage: 0 tables in
    `outputs/testpapers_batch_20260708_180516_fallback_cleanup_verify2`. The previous survivor,
    `periodontitis-p11-t0`, is no longer emitted because positioned PyMuPDF
    reconstruction cannot build a credible grid from that rough box.
  - Status: retired. PyMuPDF4LLM may still supply a rough table box, but rows,
    columns, cell bboxes, and row bounds must come from PyMuPDF positioned
    extraction. If positioned reconstruction fails, the backend grid is not
    emitted as a normal extracted table.

- Strong uncaptioned table geometry
  - Code: `table1_parser/extract/layout_fallback.py::_has_strong_uncaptioned_table_geometry`
  - Status: risky. Keep only when document-position, table mention, and
    structural geometry evidence all agree.

- Trailing continuation-note trim
  - Code: `table1_parser/extract/layout_fallback.py::trim_trailing_non_table_rows`
  - Status: keep only for explicit continuation notes. It should not grow back
    into broad footer or prose cleanup.

## Normalization Shape Repairs

These are the highest-priority retirement targets because they rewrite table
shape after extraction.

- Embedded label-count cell repair
  - Code: `table1_parser/normalize/pipeline.py::_repair_embedded_label_count_cells`
  - Metadata: `column_repairs.embedded_label_count_cells`.
  - Status: retired. Embedded label/count splits should be represented by
    coordinate-faithful extraction and later value/label candidate layers, not
    by moving text between normalized-grid columns.

- Vertical label continuation merge
  - Code: `table1_parser/normalize/pipeline.py::_repair_vertical_label_continuations`
  - Metadata: `column_repairs.vertical_label_continuations`.
  - Latest retained-run usage before retirement: 16 tables.
  - Status: retired. Wrapped body row labels are now represented by
    `body_row_label_candidates.json` after `ColumnHeaderSchema`; normalization
    no longer deletes physical continuation rows or rewrites valued-row labels.

- Split uncertainty columns
  - Code: `table1_parser/normalize/pipeline.py::_repair_split_uncertainty_columns`
  - Metadata: `column_repairs.split_uncertainty_columns`.
  - Latest retained-run usage before retirement: 2 tables.
  - Status: retired. Estimate and uncertainty fragments remain physical grid
    evidence and should be related by typed value components, not merged by
    normalization.

- Merged count-percent value columns
  - Code: previous inline normalization block recorded as
    `column_repairs.merged_columns`.
  - Latest retained-run usage before retirement: 0 tables.
  - Status: retired. Count/percent fragments belong in body-value candidates
    or parsed value components, not normalized-grid column merging.

- Trailing nondata column drop
  - Code: `table1_parser/normalize/pipeline.py::_drop_trailing_nondata_column`
  - Metadata: `column_repairs.trailing_nondata_column`.
  - Latest retained-run usage before retirement: 1 table.
  - Status: retired. Extra right-side text must be excluded by extraction,
    table-region ownership, or page-furniture handling, not dropped by
    normalization.

- Sparse nonmatrix value-column drop
  - Code: `table1_parser/normalize/pipeline.py::_drop_sparse_nonmatrix_value_columns`
  - Metadata: `column_repairs.sparse_nonmatrix_value_columns`.
  - Latest retained-run usage before retirement: 1 table.
  - Status: retired. Sparse physical columns remain in `NormalizedTable`;
    nonmatrix ownership should be decided before normalization or represented
    by later semantic routing.

- Extra-wide value-column expansion
  - Code: `table1_parser/normalize/pipeline.py::_repair_extra_wide_value_column`
  - Metadata: `column_repairs.extra_wide_value_column`.
  - Status: retired. If positioned extraction cannot recover the visual
    columns, the table should fail with preserved evidence rather than having
    normalization synthesize columns from newline-stacked text.

- Sparse stub label-column repair
  - Code: `table1_parser/normalize/pipeline.py::_repair_sparse_stub_label_column`
  - Metadata: `column_repairs.sparse_stub_label_column`.
  - Latest retained-run usage before retirement: 1 table.
  - Status: retired. The physical row-label/stub columns remain in the grid;
    logical row-label assembly belongs in row-label candidates or semantic row
    logic.

- Split row-label field columns
  - Code: `table1_parser/normalize/pipeline.py::_repair_split_row_label_field_columns`
  - Metadata: `column_repairs.split_row_label_field_columns`.
  - Latest retained-run usage before retirement: 2 tables.
  - Status: retired. Split physical label columns should not be merged during
    normalization.

- Merged split label columns
  - Code: inline normalization block recorded as
    `column_repairs.merged_split_label_columns`.
  - Latest retained-run usage before retirement: 1 table.
  - Status: retired with split row-label field repair.

- Dropped empty columns after repair
  - Code: normalization empty-column pruning after repair metadata is built.
  - Metadata: `column_repairs.dropped_empty_columns_after_repair`.
  - Status: retired with the value-fragment grid mutation paths that created
    empty normalized columns.

- Marker-only body-candidate raw-text rewrite
  - Previous code: inline in
    `table1_parser/cli.py::_build_paper_parse_artifacts()` after candidate
    marker attachment.
  - Status: retired in Phase J Step 6. Both existing body-candidate builders
    now preserve exact matching `ExtractedTable` text for every source cell, so
    marker-bearing candidates no longer need a separate raw-text repair.

## Header And Schema Compensations

These paths are retired. Missing structural header evidence now fails closed
in the candidate or projection stage.

- Normalization-time header/body inference
  - Previous code:
    `table1_parser/normalize/pipeline.py::_detect_or_apply_region_header_rows`.
  - Status: retired. Normalization requires the matching final `TableRegion`
    and never makes a second row-ownership decision.

- Header rows inferred from geometry
  - Previous code:
    `table1_parser/column_header_schema.py::_infer_header_rows_from_geometry`.
  - Status: retired in Phase J Step 5.

- Header rows inferred from grid text
  - Previous code:
    `table1_parser/column_header_schema.py::_infer_header_rows_from_grid`.
  - Status: retired in Phase J Step 5.

- Group header reconstruction and blank-span expansion
  - Previous code: `table1_parser/column_header_schema.py::_header_runs_for_groups`.
  - Includes `single_cell_blank_span` and repeated-label span inference.
  - Status: retired in Phase J Step 5.

- Repeated leaf-header block grouping
  - Previous code:
    `table1_parser/column_header_schema.py::_repeated_leaf_header_blocks`.
  - Status: retired in Phase J Step 5.

- Enrich base schema labels from continuations
  - Previous candidate override after independent schema construction.
  - Status: retired in Phase J Step 5. Provenance-bearing continuation label
    inheritance occurs once in `HeaderStructureCandidate` before projection.

## Continuation, Footnote, And Bibliography Logic

These are not all bad fallbacks, but they must remain explicitly typed and
diagnostic.

- Continuation integration
  - Code: `table1_parser/resolved_tables.py`.
  - Status: legitimate when gated by `ColumnHeaderSchema`; risky when relying
    on uncaptioned adjacent fragments. Keep fail-closed diagnostics.

- Conventional p-value star meanings
  - Previous code: `table1_parser/paper_footnotes.py::_infer_p_value_star_meaning`.
  - Status: retired from the footnote extraction/link artifact. Observed
    asterisk markers remain unresolved unless an explicit candidate definition
    is found. Conventional statistical interpretation belongs in a later
    interpretation layer.

- Bibliography column/indent handling
  - Code: `table1_parser/paper_bibliography.py`.
  - Status: keep. This is document-structure extraction, not table-grid repair.

## First Removal Sequence

After the current parser state is committed, hardening should proceed in small
passes:

1. Verify that retired normalization shape-repair paths remain absent:
   `trailing_nondata_column`, `sparse_nonmatrix_value_columns`,
   `split_row_label_field_columns`, `merged_split_label_columns`, and
   `sparse_stub_label_column`.
2. Verify that retired value-fragment grid mutation paths remain absent:
   `merged_columns`, `split_uncertainty_columns`,
   `embedded_label_count_cells`, `extra_wide_value_column`, and
   `dropped_empty_columns_after_repair`.
3. Verify that retired `caption_contaminated_backend_row_drop` and backend JSON
   cell-grid survival remain absent in real-paper runs.
4. Verify that schema projection fails closed when its candidate is missing;
   no header/group fallback remains.

Each pass should run the real-paper corpus and report exactly which real tables
improve, regress, or become intentionally unsupported.
