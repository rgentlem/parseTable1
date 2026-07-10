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
    header-band geometry, which is the intended direction.

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
  - Latest usage: 2 tables.
  - Status: retire after hline/value-matrix extraction owns collapsed grid
    reconstruction.

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
  - Status: retire after extraction assigns text to the correct label/value
    columns.

- Vertical label continuation merge
  - Code: `table1_parser/normalize/pipeline.py::_repair_vertical_label_continuations`
  - Metadata: `column_repairs.vertical_label_continuations`.
  - Latest usage: 13 tables.
  - Status: high-priority removal candidate. Correct row extraction should
    preserve wrapped labels without deleting visual rows downstream.

- Split uncertainty columns
  - Code: `table1_parser/normalize/pipeline.py::_repair_split_uncertainty_columns`
  - Metadata: `column_repairs.split_uncertainty_columns`.
  - Latest usage: 2 tables.
  - Status: retire. Estimate and uncertainty fragments should be extracted as
    one cell or modeled as typed value components, not merged by a grid repair.

- Trailing nondata column drop
  - Code: `table1_parser/normalize/pipeline.py::_drop_trailing_nondata_column`
  - Metadata: `column_repairs.trailing_nondata_column`.
  - Latest usage: 1 table.
  - Status: move to table-region/page-furniture ownership.

- Sparse nonmatrix value-column drop
  - Code: `table1_parser/normalize/pipeline.py::_drop_sparse_nonmatrix_value_columns`
  - Metadata: `column_repairs.sparse_nonmatrix_value_columns`.
  - Status: retire by preventing page-margin or footer text from entering the
    extracted grid.

- Extra-wide value-column expansion
  - Code: `table1_parser/normalize/pipeline.py::_repair_extra_wide_value_column`
  - Metadata: `column_repairs.extra_wide_value_column`.
  - Latest usage: 3 tables.
  - Status: high-priority removal candidate. This belongs in positioned
    extraction, not normalization.

- Sparse stub label-column repair
  - Code: `table1_parser/normalize/pipeline.py::_repair_sparse_stub_label_column`
  - Metadata: `column_repairs.sparse_stub_label_column`.
  - Latest usage: 1 table.
  - Status: retire after extraction/table-region ownership can identify the
    true row-label column.

- Split row-label field columns
  - Code: `table1_parser/normalize/pipeline.py::_repair_split_row_label_field_columns`
  - Metadata: `column_repairs.split_row_label_field_columns`.
  - Latest usage: 1 table.
  - Status: retire. This is already disabled when extraction provides
    `header_row_geometry_roles`.

- Merged split label columns
  - Code: inline normalization block recorded as
    `column_repairs.merged_split_label_columns`.
  - Latest usage: 1 table.
  - Status: retire with split row-label field repair.

- Dropped empty columns after repair
  - Code: normalization empty-column pruning after repair metadata is built.
  - Metadata: `column_repairs.dropped_empty_columns_after_repair`.
  - Latest usage: 2 tables.
  - Status: remove as earlier repair paths disappear.

## Header And Schema Compensations

These paths should only run when extraction lacks structural header-band
evidence.

- Header rows inferred from geometry
  - Code: `table1_parser/column_header_schema.py::_infer_header_rows_from_geometry`
  - Status: keep only as fallback for older/non-ruled extraction.

- Header rows inferred from grid text
  - Code: `table1_parser/column_header_schema.py::_infer_header_rows_from_grid`
  - Status: retire or fail closed when no structural evidence exists.

- Group header reconstruction and blank-span expansion
  - Code: `table1_parser/column_header_schema.py::_header_runs_for_groups`
  - Includes `single_cell_blank_span` and repeated-label span inference.
  - Status: narrow to cases without extraction-provided header roles.

- Repeated leaf-header block grouping
  - Code: `table1_parser/column_header_schema.py::_repeated_leaf_header_blocks`
  - Status: keep only as a schema fallback for tables without usable extraction
    geometry.

- Enrich base schema labels from continuations
  - Code: `table1_parser/column_header_schema.py::_enrich_base_schema_leaf_labels_from_continuations`
  - Status: keep short-term for continuation review, but treat as a diagnostic
    bridge. Base extraction should eventually preserve complete labels itself.

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

1. Disable or remove normalization label-column shape repairs:
   `split_row_label_field_columns`, `merged_split_label_columns`, and
   `sparse_stub_label_column`.
2. Move `extra_wide_value_column` responsibility into positioned extraction.
3. Remove `split_uncertainty_columns` once value components can represent
   estimate/uncertainty fragments without grid mutation.
4. Verify that retired `caption_contaminated_backend_row_drop` and backend JSON
   cell-grid survival remain absent in real-paper runs.
5. Gate schema header/group fallback logic on missing extraction geometry.

Each pass should run the real-paper corpus and report exactly which real tables
improve, regress, or become intentionally unsupported.
