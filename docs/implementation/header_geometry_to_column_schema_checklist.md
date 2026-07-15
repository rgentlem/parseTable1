# Phase J: One Geometry-Driven Header Path

Purpose: make one row-ownership decision, build the logical header once from
positioned geometry, and make `ColumnHeaderSchema` a direct projection of that
header. Phase J must remove the current second reconstruction path rather than
add another correction layer.

Current Phase J Step 1 baseline:
`outputs/testpapers_batch_phase_j_step1_final_20260715`.

Pre-Phase J comparison baseline:
`outputs/testpapers_batch_pre_phase_j_step2_final_20260715`.

Comparison baselines:

- Phase I:
  `outputs/testpapers_batch_geometry_phase_i_marker_attachment_final_20260715`.
- Phase H:
  `outputs/testpapers_batch_geometry_phase_h_closed_20260715`.

Current corpus accounting:

- 28 source PDFs.
- 91 extraction objects representing 91 unique physical grids.
- 79 resolved tables after 12 accepted two-fragment continuation merges. Step
  4 corrected three explicit continuations that the retired independent schema
  path had rejected despite already recognizing their continuation identity.

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
- [x] Record initial leaf-label agreement: 43 tables agree and 48 differ.
- [x] Record initial group agreement: 50 tables agree and 41 differ.
- [x] Record that the initial candidates contain 120 groups while the
      independent schemas contain 197.
- [x] Record that initially 90 candidates cover every canonical leaf column.
- [x] Identify the single initial incomplete case:
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

- [x] Decide header/body ownership before building the header candidate.
- [x] Use only direct positioned evidence: horizontal rules, row bounds,
      coverage of canonical columns, typography contrast, and adjacency.
- [x] Keep rules and value-anchored separation as the ordinary path.
- [x] For a text-dominant table without a usable value anchor, allow a
      complete mainly-bold row to be the header only when it covers all
      canonical columns, is separated from following rows by a rule, and is
      adjacent to the table start or caption.
- [x] Treat bold text and visually heavy rules as supporting evidence; neither
      is sufficient alone.
- [x] Do not use header labels, statistical vocabulary, disease names, journal
      names, or downstream schema expectations.
- [x] Do not feed the candidate back into region ownership.
- [x] Preserve every existing region except the one focused correction below.

Focused expected change:

- [x] In `mdpi-The Relationship Between a Mediterranean Diet and Frailty in
      Older Adults- NHANES 2007–2017.pdf`, PDF page 3, printed Table 1, assign
      physical row 0 to the header and rows 1–26 to the body. Row 0 has one bold
      cell in each of the three canonical columns and lies between the first
      two full-width rules. Physical cells and coordinates remain unchanged.

Step 1 checkpoint:
`outputs/testpapers_batch_phase_j_step1_final_20260715`. A character-weighted
audit found only the focused row eligible: its 66 visible characters are all
bold, while all 70 visible characters in the following row are non-bold. The
row lies between the full-width rules at y=327.944 and y=344.949.

All 28 PDFs complete with 91 byte-identical extraction objects, 82 resolved
tables, nine accepted continuation merges, and unchanged status counts of 17
`ok` and 65 `rescued`. Only the focused table changes region-dependent
artifacts. Removing row 0 from body evidence reduces its occupancy lines from
27 to 26, while its x range, bins, qualified gaps, separators, three canonical
leaf bounds, marker occurrences, and physical grid remain unchanged. The
candidate now contains the three leaves `Indicator`, `Fried Frailty Phenotype
[4]`, and `Modified Fried Frailty Phenotype [17]`, so candidate completeness
improves from 90 of 91 to 91 of 91.

## 2. Build `HeaderStructureCandidate` Once

Files and functions:

- `table1_parser/header_structure_candidates.py::build_header_structure_candidate()`
- `table1_parser/header_structure_candidates.py::build_header_structure_candidates()`
- `table1_parser/cli.py::_build_canonical_extraction_artifacts()` for the
  existing continuation-label inheritance call
- Existing models in
  `table1_parser/schemas/header_structure_candidate.py`

Checklist:

- [x] Use the final region, canonical leaf bands, positioned text, rules, and
      existing marker evidence as the only structural inputs.
- [x] Create exactly one candidate leaf for each canonical column, including
      the row-label column.
- [x] Read the lowest header band from left to right as the leaf-label band.
- [x] Treat multiple physical rows in that band as wrapped text for the same
      leaf unless an intervening rule separates them.
- [x] Process higher rule-separated header bands from bottom to top.
- [x] Create a group only when positioned coverage spans at least two
      contiguous lower leaves. Keep direct leaves outside that span.
- [x] Reject crossing or non-contiguous spans. Leave uncertain groups absent
      with an explicit candidate diagnostic.
- [x] Use no table-specific words or per-paper branches.
- [x] Preserve source evidence, `raw_text`, geometry-supported `base_text`,
      marker IDs, rule references, canonical bounds, and inheritance
      provenance.
- [x] Keep continuation-label inheritance in the candidate stage; do not add a
      second continuation override in the schema stage.
- [x] Keep the existing flat group-to-leaf representation. Do not add a new
      model, artifact, or hierarchy framework in Phase J.

Step 2 checkpoint:
`outputs/testpapers_batch_phase_j_step2_final_closed_20260715`. The candidate
builder now uses one rule-banded path over the final region: the lowest band
supplies direct leaves and same-band rule-backed spans, while higher bands are
processed bottom-up from exact local rule coverage and ordered peer geometry.
The canonical-grid leaf override, body-row promotion, body-anchor repair,
cross-band cluster helpers, and separate grouping branches are removed.

All 91 candidates contain exactly one leaf per canonical column: 663 leaves,
115 non-crossing contiguous groups, and 376 group-to-leaf relationships. All
56 header marker attachments remain linked to the same logical node, the eight
inherited continuation leaves retain exact provenance, and no candidate uses
evidence outside its final header rows. The only unresolved upper run is the
explicitly diagnosed title-like evidence on PDF page 18 of `periodontis2.pdf`;
it is not converted into a group or taken from the first body row.

The 28 PDFs retain 91 byte-identical extraction objects, 82 resolved tables,
nine accepted continuation integrations, and status counts of 17 `ok` and 65
`rescued`. Table regions, body occupancy, canonical leaf geometry, and marker
occurrences are byte-identical to Step 1. Candidate/schema leaf agreement
remains 44/91 because the schema stage still uses its independent builder;
group agreement improves from 50/91 to 53/91. Direct projection and removal of
that competing schema builder remain Steps 4-5. No pytest run was made.

## 3. Preserve The Grid In `NormalizedTable`

Files and functions:

- `table1_parser/normalize/pipeline.py::normalize_extracted_tables()`
- Existing call in `table1_parser/cli.py::_build_paper_parse_artifacts()`

Checklist:

- [x] Normalize from the final `TableRegion`.
- [x] Preserve physical row and column indices, source-cell identity, text,
      bounding boxes, and occupancy.
- [x] Do not split, merge, move, repair, or synthesize cells.
- [x] Do not rerun header/body inference during normalization.

Step 3 checkpoint:
Normalization now requires the matching final `TableRegion`, copies its header
and body rows directly, and fails if the region is missing or refers outside
the selected physical grid. The legacy normalization-time header detector and
the remaining sparse edge-column removal are gone. `NormalizedTable` keeps the
same row and column counts and the identity source-column map
`[0, ..., n_cols - 1]`; parser-facing text cleaning and row signatures remain
non-operative views over that grid.

The 28-PDF checkpoint is
`outputs/testpapers_batch_phase_j_step3_final_20260715`. It contains 91
extraction objects with 91 unique physical IDs, 82 resolved tables, nine
integrated continuations, and unchanged status counts of 17 `ok` and 65
`rescued`. Extracted tables, regions, body occupancy, leaf candidates, cell
annotations, header candidates, normalized tables, resolved tables, and
processing statuses are exact JSON matches to Step 2 for every paper. All 91
normalized records match their extracted row/column counts, region-owned rows,
and identity source-column indices. No pytest run was made.

## 4. Project `ColumnHeaderSchema`

Files and functions:

- `table1_parser/column_header_schema.py::build_column_header_schema()`
- `table1_parser/column_header_schema.py::build_column_header_schemas()`
- Existing models in `table1_parser/schemas/column_header_schema.py`
- `table1_parser/validation/column_header_schema.py::validate_column_header_schema()`

Checklist:

- [x] Require the matching validated candidate; do not make it optional in the
      canonical parse path.
- [x] Project one schema leaf from each candidate leaf at the same canonical
      column index.
- [x] Use candidate `base_text` for the structural label while retaining raw
      evidence and marker provenance.
- [x] Project candidate groups, their contiguous leaf coverage, and their
      evidence without creating, moving, respanning, or deleting nodes.
- [x] Derive parser-facing names only after labels and provenance are fixed.
- [x] Reuse the existing `ColumnHeaderSchema` and diagnostics. Do not add a
      result wrapper, class, or artifact.
- [x] If the candidate leaf axis or references are incomplete, preserve the
      projected evidence with a structured diagnostic and fail closed; do not
      reconstruct a substitute header.
- [x] Validate complete leaf coverage, bounds, references, contiguous groups,
      and non-crossing spans.

Projection invariant:

- [x] For every accepted table, candidate leaves and schema leaves have the
      same column indices and labels, and candidate groups and schema groups
      have the same labels and leaf coverage.

Step 4 checkpoint:
`outputs/testpapers_batch_phase_j_step4_final_20260715`. The canonical schema
path now projects the matching candidate by table ID. It preserves candidate
node and evidence IDs, so the 56 selected header-marker targets remain stable,
and finalizes geometry-supported header `base_text` before projection. The
schema contains exactly the candidate's 663 leaves, 115 groups, and 376
relationships, with zero label, coverage, evidence-reference, marker-node, or
crossing-span mismatches across 91 source tables.

The direct schemas also correct three continuation decisions that had already
recognized explicit continuation identity but were rejected solely because
the independent schema builder reconstructed the two page headers
differently:

- `Science-Advanaced-Planetary Health Diet and risk of mortality and chronic
  diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf`, PDF
  pages 2–3, printed Table 1.
- `gallstones.pdf`, PDF pages 5–6, printed Table 1.
- `mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older
  Adults- NHANES 2007–2017.pdf`, PDF pages 5–6, printed Table 2.

These approved corrections produce 79 resolved tables and 12 accepted
continuation integrations from the unchanged 91 physical grids. Processing
statuses are 16 `ok` and 63 `rescued`, with no failure. No pytest run was made.

## 5. Remove The Competing Builder

Remove or align in `table1_parser/column_header_schema.py`:

- [x] Independent header-row inference:
      `_infer_header_rows_from_geometry()` and
      `_infer_header_rows_from_grid()`.
- [x] Independent group construction: `_header_runs_for_groups()`,
      `_geometry_role_group_runs()`, `_repeated_leaf_header_blocks()`, and
      `_can_stack_header_runs()`.
- [x] Blank-span grouping, same-row overrides, fragment movement, body-comma
      splitting, count-header inference, and related reconstruction-only
      constants and helpers.
- [x] The continuation-only candidate override that runs after independent
      schema construction.

Remove in `table1_parser/cli.py::_build_paper_parse_artifacts()`:

- [x] The fallback call that independently invokes
      `build_column_header_schema(resolved_table.table)` when a resolved source
      schema is missing.
- [x] Keep the ordinary source-schema projection for resolved tables. A
      missing source schema must remain a structured failure, not trigger a
      rebuild.

Keep:

- [x] The existing public schema builder names and artifact name.
- [x] Existing schema models, validation entry point, serialization, column
      descriptors, and parser-facing name normalization.
- [x] One compact inline projection inside the existing schema stage; add no
      single-use helper.

Completion gate:

- [x] No second header builder, repair pass, continuation override, or resolved
      fallback remains.

Step 5 checkpoint:
`outputs/testpapers_batch_phase_j_step5_final_20260715`. The schema module is
reduced from 2,248 to 401 lines. All independent header-row inference,
blank-span and same-row overrides, fragment movement, body-comma and count
inference, group reconstruction, continuation-only override, and their helper
layer are deleted. The resolved-table path now projects the source schema or
emits an explicit zero-confidence missing-source record; it never invokes a
builder without a candidate.

All 28 PDFs reproduce Step 4 exactly apart from regenerated parse-quality
timestamps: 91 physical grids, 91 exact candidate/schema projections, 79
resolved tables, and no failure. Continuation reporting now includes both gate
outcomes: 13 candidates were recognized, 12 were accepted, and one was
rejected. The remaining rejection is `periodontis2.pdf`, PDF pages 10–11,
printed Table 1, whose projected column paths still disagree. Processing
statuses remain 16 `ok` and 63 `rescued`. No pytest run was made.

## 6. Attach Body Candidates After Projection

Files and functions:

- `table1_parser/parse/body_element_candidates.py`
- `table1_parser/parse/body_row_label_candidates.py`
- Existing calls in `table1_parser/cli.py::_build_paper_parse_artifacts()`

Checklist:

- [x] Keep body candidate construction after region, canonical leaves,
      candidate, normalization, and schema projection.
- [x] Attach each logical body value to its canonical leaf and projected header
      path.
- [x] Preserve source cells, physical lines, `raw_text`, geometry-supported
      `base_text`, marker IDs, and uncertain-marker diagnostics.
- [x] Make no body-parser change unless the projection requires an existing
      reference to be carried through.
- [x] Keep alignment supporting and non-operative; it must never change rows,
      columns, leaves, labels, groups, values, or semantics.

Step 6 checkpoint:
`outputs/testpapers_batch_phase_j_step6_final_20260715`. The existing body
builders still use `anchor_col_idx` as the stable join to the projected leaf;
`TableDefinition` and final values then carry that leaf ID, group IDs, and full
header path. All 9,523 body-value candidates and 56 logical row-label
candidates land on the expected projected leaf, and all 7,873 final values
carry the matching projected path.

The only parser correction overlays exact `ExtractedTable` cell text into the
two existing candidate builders before candidate assembly. This fixes 1,303
body-value and three row-label source-cell text records that had stored a
cleaned normalized spelling instead of the printed physical text. The former
CLI marker-only raw-text rewrite is removed. Parser-facing candidate text,
parsed components, semantic values, marker links, and diagnostics remain
exact. All 433 marker occurrences retain their established attachments: 56 to
header nodes, 317 to body values, one to a logical row label, and 59 to the
physical cell only. The two uncertain header markers and 114 body glyph
residues remain in `base_text` with their existing diagnostics.

The 28 PDFs retain 91 physical grids, 91 schemas, 79 resolved tables, 12
accepted continuation integrations, and processing statuses of 16 `ok` and 63
`rescued`. Thirteen continuation candidates are reported: 12 accepted and one
rejected. The rejected candidate remains `periodontis2.pdf`, PDF pages 10–11,
printed Table 1, whose projected column paths disagree. Return to that case
after Phase J closes. No pytest run was made.

## 7. Validate Only The Intended Change

Focused papers:

- [x] Text-only header ownership: `mdpi-The Relationship Between a
      Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017.pdf`,
      PDF page 3, printed Table 1.
- [x] Duplicate remains absent and continuation remains correct: `Asthma
      prevalence among United States population insights from NHANES data
      analysis.pdf`, PDF pages 4–5, printed Tables 1 and 2.
- [x] Flat header: `NutritionEx.pdf`, PDF page 5, printed Table 1.
- [x] Grouped and rotated headers: `Journal of Periodontology - 2015 - Eke -
      Update on Prevalence of Periodontitis in Adults in the United States
      NHANES 2009.pdf`, PDF pages 4–7, printed Tables 1 and 2.
- [x] Wrapped leaves without invented groups: `cobaltpaper.pdf`, PDF page 3,
      printed Table 1.
- [x] Continuation inheritance: `Association between anthropometric indices
      and chronic kidney disease- Insights from NHANES 2009–2018.pdf`, PDF
      pages 7–8, printed Table 1.

Full corpus:

- [x] Parse all 28 PDFs with at most six concurrent workers into a fresh
      ignored output directory.
- [x] Require 91 extraction objects, 91 unique physical grids, 79 resolved
      tables, and 12 accepted continuation merges.
- [x] Require exact equality for physical IDs, rows, columns, cells, text,
      bboxes, canonical leaf geometry, marker occurrences, and inherited-header
      provenance. Continuation identity may differ only for the three approved
      Step 4 integrations recorded above.
- [x] Require body occupancy to remain exact for 90 tables. For the focused
      MDPI table, allow only removal of header row 0 from body evidence;
      occupancy separators and canonical leaf geometry must remain exact.
- [x] Require all region rows to remain unchanged except the single MDPI row-0
      correction.
- [x] Require every schema to be an exact candidate projection.
- [x] Enumerate every changed candidate and schema; investigate any change not
      produced by the general geometry rules above.
- [x] Require no failed paper or table-processing result.
- [x] Do not add tests or run pytest without separate permission.

Step 7 checkpoint:
the existing fresh Step 6 corpus
`outputs/testpapers_batch_phase_j_step6_final_20260715` supplies the closure
evidence; no additional parse run was necessary. All 28 PDFs completed with 91
unique physical grids, 79 resolved tables, 12 accepted continuation
integrations, 16 `ok`, 63 `rescued`, and no failure. Thirteen continuation
candidates are explicit: 12 accepted and the retained `periodontis2.pdf`, PDF
pages 10–11, printed Table 1 rejection.

The six focused checks pass. The MDPI text table has header row 0 and body rows
1–26. The Asthma paper contains four unique grids; printed Table 1 on PDF pages
4–5 resolves to 67 x 5 and printed Table 2 remains a singleton. `NutritionEx`
printed Table 1 has seven flat leaves and no group. The Eke printed Tables 1–2
on PDF pages 4–7 retain four rotated grids, their geometry-built groups, and two
accepted integrations. `cobaltpaper.pdf` printed Table 1 has eight wrapped
leaves and no invented group. The anthropometric CKD printed Table 1 on PDF
pages 7–8 resolves to 63 x 5 with parent headers carried forward after the
schema match.

Compared with the pre-Phase J baseline, all 91 extracted grids and all 91 cell
annotation records are exact. Ninety regions, occupancy records, and leaf
candidate records are exact. Only the approved MDPI table changes: row 0 leaves
body evidence and becomes the header; its separators and canonical leaf bounds
remain exact. The general Step 2 candidate builder changes 87 candidates. The
other four candidates remain byte-identical: the two PDF-page-7 METS-IR tables,
PDF-page-4 Role of Estimated Glucose Disposal Rate table, and PDF-page-5
Planetary Health Diet table. All 91 schemas change from the former independent
construction to direct projection. The final audit finds exact projection of
663 leaves, 115 groups, and 376 relationships with zero mismatch. Compared
with Step 3, continuation decisions change only for the three approved Step 4
integrations. No tests were added and pytest was not run.

## 8. Implementation Gate

Expected parser files:

- `table1_parser/table_regions.py`
- `table1_parser/header_structure_candidates.py`
- `table1_parser/normalize/pipeline.py`
- `table1_parser/column_header_schema.py`
- `table1_parser/cli.py`
- `table1_parser/parse/body_element_candidates.py`
- `table1_parser/parse/body_row_label_candidates.py`
- `table1_parser/parse/cell_value_components.py`
- `table1_parser/schemas/column_header_schema.py`
- `table1_parser/validation/column_header_schema.py`

Constraints:

- [x] No new files, classes, artifacts, frameworks, helper layers, fallback
      paths, or single-use helpers.
- [x] Prefer net code deletion by replacing the large reconstruction path with
      compact projection logic.
- [x] Preserve unrelated dirty R, README, man-page, vignette, and `tmp/` files.
- [x] Update the parser ToDo, fallback inventory, and paper walkthrough only
      when the implementation actually changes those paths.
- [x] Report focused and full-corpus evidence before staging.
- [x] Assess whether tests are needed before staging; do not add them without
      permission.
- [x] Obtain explicit approval for this exact parser-logic change before
      editing the parser files above.

Step 8 audit:
the implementation gate passes. No source file, class, artifact, framework,
helper layer, fallback, repair path, or override was added. The Phase J parser
diff adds 1,660 lines and deletes 3,042, for a net reduction of 1,382 lines.
The independent schema reconstruction and normalization inference/pruning
paths are removed, while the existing stage and model names remain. Required
design, walkthrough, output, fallback-inventory, checklist, and ToDo documents
are aligned. Unrelated dirty R, README, man-page, vignette, and `tmp/` files are
unchanged by Phase J. `ruff check`, `py_compile`, and `git diff --check` pass.

The required pre-staging test assessment found no justification for adding a
new test: the 28-PDF corpus is the direct geometry evidence for this phase.
With explicit approval, the 13 builder tests for the deleted independent
reconstruction path and the 22 direct-normalization tests that omitted the
now-required `TableRegion` were removed. The active schema validator,
header-detector, and row-signature tests remain. Pytest was not run, in
accordance with the explicit instruction. Phase J is now implementation- and
test-alignment-complete and ready to stage.

Phase J is complete only when one region decision feeds one geometry-built
candidate, every schema is a direct projection of that candidate, the older
reconstruction path is gone, and the 91-grid physical baseline remains exact.

## Post-Phase J: Clipped Continuation Source Text

- [x] Inspect `periodontis2.pdf`, PDF pages 10–11, printed Table 1, before
      changing continuation logic.
- [x] Confirm the page-11 PDF content stream contains the complete repeated
      header and values, but places them beyond the declared page box.
- [x] Retain off-page text in the existing shared positioned-document pass.
- [x] Rebuild the ordinary physical grid, candidate, and projected schema from
      that direct source evidence.
- [x] Keep the existing exact continuation schema gate unchanged.
- [x] Add one focused regression for off-page positioned text; add no leaf
      inheritance, schema repair, or resolver workaround.

Checkpoint:
`outputs/testpapers_batch_offpage_text_recovery_20260715`. The recovered
page-11 fragment is 20 x 13 rather than the clipped 19 x 13 grid. Its complete
seven-row header now projects to the same 13 column paths as page 10, including
`Total Periodontitis Age Standardized %±SE`, and clipped values such as `47`
are recovered as `47.8±2.5`. The unchanged continuation gate accepts the two
fragments as one 43 x 13 Table 1. Across all 28 PDFs there are 91 extraction
objects, 78 resolved tables after 13 accepted continuation integrations, 16
`ok`, 62 `rescued`, and no failure. Structural artifacts outside
`periodontis2.pdf` are unchanged; no downstream leaf fix is needed.
