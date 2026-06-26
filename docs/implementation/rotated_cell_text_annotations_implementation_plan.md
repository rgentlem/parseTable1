# Rotated Cell Text Annotations Implementation Plan

Short checklist for making `cell_text_annotations.json` work on rotated or
table-local geometry.

Design note: `docs/design/cell_text_annotations.md`.

## Goal

When a table is extracted in a rotated/local coordinate frame, annotation
detection should transform PyMuPDF characters into that same frame before
matching characters to cell bboxes.

## Steps

1. [x] Confirm current rotated metadata
   - Inspect `ExtractedTable.metadata` for rotated tables.
   - Confirm each rotated table records `geometry_coordinate_frame`.
   - Confirm it also records enough to replay the transform: source bbox,
     `rotation_direction`, and whether the transposed bbox path was used.
   - Audit result from real papers:
     - Present: `geometry_coordinate_frame`, `rotation_direction`,
       `rotation_source`, `rotation_confidence`, `table_orientation`,
       `grid_refinement_source`, and persisted `bbox`.
     - Missing/unclear: no explicit transform-source bbox field, no explicit
       transposed-attempt flag, and rotated refinements keep bboxes in
       `refined_table_cells` while normal cell construction reads
       `table_cells`.
     - Current annotation diagnostics on rotated-local tables are therefore
       `unsupported_coordinate_frame:*` plus `cell_bboxes_missing`.
     - Audit outputs: `/private/tmp/rotated_cell_text_step1` and
       `/private/tmp/rotated_cell_text_step1_summary.json`.

2. [x] Persist missing transform inputs
   - If any transform input is missing, add it during extraction.
   - Keep this metadata table-level, not page-level.
   - Do not change normalized rows or parsed values.
   - Add explicit fields for the source bbox used by the winning rotated
     refinement and whether it was the transposed bbox path.
   - Decision: `TableCell.bbox` and `metadata.table_cells` use the current
     refined-grid bboxes, even for rotated-local tables. Original backend cells
     remain in `metadata.original_table_cells` when refinement changed the grid.
   - Added metadata:
     - `geometry_transform_source_bbox`
     - `geometry_transform_transposed`
     - `geometry_transform_applied`
   - Page-word indentation inference remains page-frame only; rotated-local
     bboxes are not matched against raw page words for
     `first_column_text_x0_by_row`.
   - Real-paper check after step 2: rotated-local tables now have populated
     `TableCell.bbox`; `cell_bboxes_missing` is gone, leaving only
     `unsupported_coordinate_frame:*` for step 3.
   - Check outputs: `/private/tmp/rotated_cell_text_step2` and
     `/private/tmp/rotated_cell_text_step2_summary.json`.

3. [x] Add annotation-side transform
   - In `cell_text_annotations.py`, stop treating non-page frames as automatic
     unsupported cases.
   - For rotated/local frames, clip page chars to the recorded source bbox.
   - Apply `normalize_positioned_geometry_for_rotation(...)` with the recorded
     rotation direction.
   - Match transformed chars to transformed cell bboxes.
   - Supported frames now include:
     - `page_sideways_transformed`
     - `table_local_rotated_normalized`
     - `table_local_rotated_transposed_normalized`
   - Real-paper check after step 3: Eke and insulin sensitivity rotated-local
     tables no longer report `unsupported_coordinate_frame:*`; annotations are
     detected in rotated-local frames.
   - Check outputs: `/private/tmp/rotated_cell_text_step3` and
     `/private/tmp/rotated_cell_text_step3_summary.json`.

4. [x] Keep diagnostics explicit
   - If transform metadata is missing, emit a table diagnostic.
   - If char geometry is unavailable, keep the existing diagnostic.
   - Record the actual coordinate frame in the annotation table metadata.
   - Annotation metadata now records:
     - `coordinate_frame`
     - `geometry_transform_applied`
     - `geometry_transform_source_bbox`
     - `geometry_transform_transposed`
     - `rotation_direction`
   - Missing transform pieces use explicit diagnostics such as
     `geometry_transform_source_bbox_missing`,
     `geometry_transform_source_bbox_invalid`,
     `geometry_transform_not_applied`, and `rotation_direction_missing`.

5. [x] Real-paper checks
   - Parse the Eke periodontitis paper.
   - Parse the insulin sensitivity paper.
   - Confirm rotated tables no longer report `unsupported_coordinate_frame:*`
     when transform metadata is available.
   - Inspect results with `show_cell_text_annotations(...)`.

6. [x] Documentation update
   - Update `docs/design/cell_text_annotations.md` if annotation bbox semantics
     change.
   - Update `docs/r_visualization.md` only if the R surface changes.
   - `docs/design/cell_text_annotations.md` now documents transformed-frame
     annotation bbox semantics and transform metadata.
   - `docs/design/design_index.md` now links this checklist.
   - R surface did not change, so `docs/r_visualization.md` did not need an
     update for this rotated-geometry work.

## Non-Goals

- Do not link markers to footnote definitions.
- Do not alter raw cell text.
- Do not consume annotations in value parsing yet.
- Do not solve page-level mixed orientation globally; handle it per table.
