# Phase J: One Geometry-Driven Header Path

Purpose: make one row-ownership decision, build the logical header once from
positioned geometry, and make `ColumnHeaderSchema` a direct projection of that
header. Phase J must remove the current second reconstruction path rather than
add another correction layer.

Current input baseline:
`outputs/testpapers_batch_pre_phase_j_step2_final_20260715`.

Comparison baselines:

- Phase I:
  `outputs/testpapers_batch_geometry_phase_i_marker_attachment_final_20260715`.
- Phase H:
  `outputs/testpapers_batch_geometry_phase_h_closed_20260715`.

Corpus accounting that must remain unchanged:

- 28 source PDFs.
- 91 extraction objects representing 91 unique physical grids.
- 82 resolved tables after nine accepted two-fragment continuation merges.

## Fixed Pipeline

```text
selected physical grid
  -> TableRegion: decide header/body ownership once
  -> body occupancy and canonical leaf columns
  -> HeaderStructureCandidate: build leaves, wrapped labels, and groups once
  -> NormalizedTable: preserve the selected physical grid and region
  -> ColumnHeaderSchema: project the candidate without reconstruction
  -> body candidates and resolved tables
```

`HeaderStructureCandidate` must not revise `TableRegion`.
`ColumnHeaderSchema` must not revise either one.

## 0. Reset Audit

- [x] Re-baseline the audit on the 91-grid corpus.
- [x] Confirm `TableRegion` and `HeaderStructureCandidate` carry identical
      header/body row indices for 91 of 91 tables.
- [x] Record that this agreement is not independent validation: the candidate
      currently receives those indices from the region.
- [x] Record current leaf-label agreement: 43 tables agree and 48 differ.
- [x] Record current group agreement: 50 tables agree and 41 differ.
- [x] Record that the current candidates contain 120 groups while the
      independent schemas contain 197.
- [x] Record that 90 candidates cover every canonical leaf column.
- [x] Retain the single incomplete case:
      `mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older
      Adults- NHANES 2007–2017.pdf`, PDF page 3, printed Table 1. Its complete
      bold first row is currently assigned to the body.
- [x] Confirm the existing eight inherited continuation labels remain in the
      candidate evidence.
- [x] Retire the old abbreviated per-table patch ledger. The 48 leaf
      differences and 41 group differences overlap in 33 tables, so 56
      retained tables currently differ on at least one axis. Phase J will
      resolve them through the single general path below, not table-specific
      corrections.

## 1. Decide `TableRegion` Once

Files and functions:

- `table1_parser/table_regions.py::build_table_region()`
- `table1_parser/table_regions.py::build_table_regions()`
- `table1_parser/cli.py::_build_table_geometry_artifacts()`

Checklist:

- [ ] Decide header/body ownership before building the header candidate.
- [ ] Use only direct positioned evidence: horizontal rules, row bounds,
      coverage of canonical columns, typography contrast, and adjacency.
- [ ] Keep rules and value-anchored separation as the ordinary path.
- [ ] For a text-dominant table without a usable value anchor, allow a
      complete mainly-bold row to be the header only when it covers all
      canonical columns, is separated from following rows by a rule, and is
      adjacent to the table start or caption.
- [ ] Treat bold text and visually heavy rules as supporting evidence; neither
      is sufficient alone.
- [ ] Do not use header labels, statistical vocabulary, disease names, journal
      names, or downstream schema expectations.
- [ ] Do not feed the candidate back into region ownership.
- [ ] Preserve every existing region except the one focused correction below.

Focused expected change:

- [ ] In `mdpi-The Relationship Between a Mediterranean Diet and Frailty in
      Older Adults- NHANES 2007–2017.pdf`, PDF page 3, printed Table 1, assign
      physical row 0 to the header and rows 1–26 to the body. Row 0 has one bold
      cell in each of the three canonical columns and lies between the first
      two full-width rules. Physical cells and coordinates remain unchanged.

## 2. Build `HeaderStructureCandidate` Once

Files and functions:

- `table1_parser/header_structure_candidates.py::build_header_structure_candidate()`
- `table1_parser/header_structure_candidates.py::build_header_structure_candidates()`
- `table1_parser/cli.py::_build_canonical_extraction_artifacts()` for the
  existing continuation-label inheritance call
- Existing models in
  `table1_parser/schemas/header_structure_candidate.py`

Checklist:

- [ ] Use the final region, canonical leaf bands, positioned text, rules, and
      existing marker evidence as the only structural inputs.
- [ ] Create exactly one candidate leaf for each canonical column, including
      the row-label column.
- [ ] Read the lowest header band from left to right as the leaf-label band.
- [ ] Treat multiple physical rows in that band as wrapped text for the same
      leaf unless an intervening rule separates them.
- [ ] Process higher rule-separated header bands from bottom to top.
- [ ] Create a group only when positioned coverage spans at least two
      contiguous lower leaves. Keep direct leaves outside that span.
- [ ] Reject crossing or non-contiguous spans. Leave uncertain groups absent
      with an explicit candidate diagnostic.
- [ ] Use no table-specific words or per-paper branches.
- [ ] Preserve source evidence, `raw_text`, geometry-supported `base_text`,
      marker IDs, rule references, canonical bounds, and inheritance
      provenance.
- [ ] Keep continuation-label inheritance in the candidate stage; do not add a
      second continuation override in the schema stage.
- [ ] Keep the existing flat group-to-leaf representation. Do not add a new
      model, artifact, or hierarchy framework in Phase J.

## 3. Preserve The Grid In `NormalizedTable`

Files and functions:

- `table1_parser/normalize/pipeline.py::normalize_extracted_tables()`
- Existing call in `table1_parser/cli.py::_build_paper_parse_artifacts()`

Checklist:

- [ ] Normalize from the final `TableRegion`.
- [ ] Preserve physical row and column indices, source-cell identity, text,
      bounding boxes, and occupancy.
- [ ] Do not split, merge, move, repair, or synthesize cells.
- [ ] Do not rerun header/body inference during normalization.

## 4. Project `ColumnHeaderSchema`

Files and functions:

- `table1_parser/column_header_schema.py::build_column_header_schema()`
- `table1_parser/column_header_schema.py::build_column_header_schemas()`
- Existing models in `table1_parser/schemas/column_header_schema.py`
- `table1_parser/validation/column_header_schema.py::validate_column_header_schema()`

Checklist:

- [ ] Require the matching validated candidate; do not make it optional in the
      canonical parse path.
- [ ] Project one schema leaf from each candidate leaf at the same canonical
      column index.
- [ ] Use candidate `base_text` for the structural label while retaining raw
      evidence and marker provenance.
- [ ] Project candidate groups, their contiguous leaf coverage, and their
      evidence without creating, moving, respanning, or deleting nodes.
- [ ] Derive parser-facing names only after labels and provenance are fixed.
- [ ] Reuse the existing `ColumnHeaderSchema` and diagnostics. Do not add a
      result wrapper, class, or artifact.
- [ ] If the candidate leaf axis or references are incomplete, preserve the
      projected evidence with a structured diagnostic and fail closed; do not
      reconstruct a substitute header.
- [ ] Validate complete leaf coverage, bounds, references, contiguous groups,
      and non-crossing spans.

Projection invariant:

- [ ] For every accepted table, candidate leaves and schema leaves have the
      same column indices and labels, and candidate groups and schema groups
      have the same labels and leaf coverage.

## 5. Remove The Competing Builder

Remove or align in `table1_parser/column_header_schema.py`:

- [ ] Independent header-row inference:
      `_infer_header_rows_from_geometry()` and
      `_infer_header_rows_from_grid()`.
- [ ] Independent group construction: `_header_runs_for_groups()`,
      `_geometry_role_group_runs()`, `_repeated_leaf_header_blocks()`, and
      `_can_stack_header_runs()`.
- [ ] Blank-span grouping, same-row overrides, fragment movement, body-comma
      splitting, count-header inference, and related reconstruction-only
      constants and helpers.
- [ ] The continuation-only candidate override that runs after independent
      schema construction.

Remove in `table1_parser/cli.py::_build_paper_parse_artifacts()`:

- [ ] The fallback call that independently invokes
      `build_column_header_schema(resolved_table.table)` when a resolved source
      schema is missing.
- [ ] Keep the ordinary source-schema projection for resolved tables. A
      missing source schema must remain a structured failure, not trigger a
      rebuild.

Keep:

- [ ] The existing public schema builder names and artifact name.
- [ ] Existing schema models, validation entry point, serialization, column
      descriptors, and parser-facing name normalization.
- [ ] One compact inline projection inside the existing schema stage; add no
      single-use helper.

Completion gate:

- [ ] No second header builder, repair pass, continuation override, or resolved
      fallback remains.

## 6. Attach Body Candidates After Projection

Files and functions:

- `table1_parser/parse/body_element_candidates.py`
- `table1_parser/parse/body_row_label_candidates.py`
- Existing calls in `table1_parser/cli.py::_build_paper_parse_artifacts()`

Checklist:

- [ ] Keep body candidate construction after region, canonical leaves,
      candidate, normalization, and schema projection.
- [ ] Attach each logical body value to its canonical leaf and projected header
      path.
- [ ] Preserve source cells, physical lines, `raw_text`, geometry-supported
      `base_text`, marker IDs, and uncertain-marker diagnostics.
- [ ] Make no body-parser change unless the projection requires an existing
      reference to be carried through.
- [ ] Keep alignment supporting and non-operative; it must never change rows,
      columns, leaves, labels, groups, values, or semantics.

## 7. Validate Only The Intended Change

Focused papers:

- [ ] Text-only header ownership: `mdpi-The Relationship Between a
      Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017.pdf`,
      PDF page 3, printed Table 1.
- [ ] Duplicate remains absent and continuation remains correct: `Asthma
      prevalence among United States population insights from NHANES data
      analysis.pdf`, PDF pages 4–5, printed Tables 1 and 2.
- [ ] Flat header: `NutritionEx.pdf`, PDF page 5, printed Table 1.
- [ ] Grouped and rotated headers: `Journal of Periodontology - 2015 - Eke -
      Update on Prevalence of Periodontitis in Adults in the United States
      NHANES 2009.pdf`, PDF pages 4–7, printed Tables 1 and 2.
- [ ] Wrapped leaves without invented groups: `cobaltpaper.pdf`, PDF page 3,
      printed Table 1.
- [ ] Continuation inheritance: `Association between anthropometric indices
      and chronic kidney disease- Insights from NHANES 2009–2018.pdf`, PDF
      pages 7–8, printed Table 1.

Full corpus:

- [ ] Parse all 28 PDFs with at most six concurrent workers into a fresh
      ignored output directory.
- [ ] Require 91 extraction objects, 91 unique physical grids, 82 resolved
      tables, and nine accepted continuation merges.
- [ ] Require exact equality for physical IDs, rows, columns, cells, text,
      bboxes, occupancy, canonical leaves, marker occurrences, continuation
      identity, and inherited-header provenance.
- [ ] Require all region rows to remain unchanged except the single MDPI row-0
      correction.
- [ ] Require every schema to be an exact candidate projection.
- [ ] Enumerate every changed candidate and schema; investigate any change not
      produced by the general geometry rules above.
- [ ] Require no failed paper or table-processing result.
- [ ] Do not add tests or run pytest without separate permission.

## 8. Implementation Gate

Expected parser files:

- `table1_parser/table_regions.py`
- `table1_parser/header_structure_candidates.py`
- `table1_parser/column_header_schema.py`
- `table1_parser/cli.py`
- `table1_parser/validation/column_header_schema.py` only if its existing
  checks must be aligned with direct projection

Constraints:

- [ ] No new files, classes, artifacts, frameworks, helper layers, fallback
      paths, or single-use helpers.
- [ ] Prefer net code deletion by replacing the large reconstruction path with
      compact projection logic.
- [ ] Preserve unrelated dirty R, README, man-page, vignette, and `tmp/` files.
- [ ] Update the parser ToDo, fallback inventory, and paper walkthrough only
      when the implementation actually changes those paths.
- [ ] Report focused and full-corpus evidence before staging.
- [ ] Assess whether tests are needed before staging; do not add them without
      permission.
- [ ] Obtain explicit approval for this exact parser-logic change before
      editing the parser files above.

Phase J is complete only when one region decision feeds one geometry-built
candidate, every schema is a direct projection of that candidate, the older
reconstruction path is gone, and the 91-grid physical baseline remains exact.
