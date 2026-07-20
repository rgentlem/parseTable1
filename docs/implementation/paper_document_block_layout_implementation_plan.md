# PaperDocument Block-First Physical Layout Implementation Plan

> **Accepted checkpoint — 2026-07-20:** Steps 0–5 are complete. They establish
> and validate a non-operative block-layout candidate without changing document
> order, ownership, bibliography parsing, or downstream table behavior. This
> checkpoint does not approve Step 6 activation or any later parser change.

## Status and Scope

This document is the step-by-step implementation plan for replacing the
current line-first, page-wide column calculation with a block-first physical
layout inside canonical `PaperDocument`.

It operationalizes:

- `docs/design/paper_document_plan_and_contract.md`;
- the block-preservation direction confirmed on 2026-07-19.

This is a plan and checklist. It is not, by itself, approval to change parser
logic. Each operative checkpoint still requires explicit approval for its
specific logic change. No step may add or alter a numeric layout tolerance
without the exact `APPROVE_LAYOUT_TOLERANCE` keyword.

The accepted scope currently ends after Step 5 validation of the non-operative
candidate. The current page-wide layout and bibliography implementations remain
operative and unchanged. Steps 6–10 below are unapproved follow-up proposals,
not part of the accepted checkpoint or its commit candidate.

## Goal

Establish physical reading order from retained extracted blocks:

```text
PaperPositionedDocument lines
-> page-furniture filtering
-> retained PaperDocument blocks
-> orientation-local layout regions
-> left-to-right columns inside each region
-> top-to-bottom block IDs inside each column
-> canonical physical block traversal
```

The layout stage stops after arranging blocks. It does not decide whether a
block is prose, a caption, a bibliography entry, a table component, a figure,
or residual material.

## Central Block-First Principle

The extracted source block is the default unit of physical relatedness.
PyMuPDF often places text that belongs together in one block: a paragraph, a
heading with related lines, a caption fragment, a bibliography entry, or
another locally coherent object. That grouping is useful extraction evidence
and should be preserved unless stronger direct evidence requires refinement.

Therefore:

- construct retained blocks before detecting page columns or reading order;
- keep every block intact during layout detection;
- keep its lines in block-local source order;
- derive layout from block bboxes, not from individual line widths or starts;
- refer to blocks by ID from page layout rather than copying their text or
  geometry into layout records;
- interpret a whole block before considering a split;
- split only at a direct, accepted source-line boundary and never merely
  because downstream semantics prefer smaller pieces; and
- preserve source order and exact geometry when block topology does not
  establish a reliable relationship.

Blocks are strong evidence, not infallible semantic truth. An accepted
`PaperDocumentBlock` may be a line-preserving refinement of one source block.
Such parts retain the same `source_block_index`, disjoint contiguous `line_ids`,
and exact bboxes. Layout still treats every retained canonical block as an
indivisible unit.

## Current Design Problem

`table1_parser/context/paper_document_builder.py` currently performs the work
in the opposite order:

1. filter positioned lines;
2. detect page-wide columns from line widths and x-start clusters in
   `_detect_page_columns()` and `_detect_caption_aligned_columns()`;
3. reconstruct source blocks temporarily inside `_order_page_blocks()`;
4. assign column metadata to individual lines;
5. flatten those lines into page order; and
6. reconstruct `PaperDocument` blocks afterward.

This makes line geometry determine block order, assigns one column arrangement
to a whole orientation group, and stores that page-wide decision on every
block. It cannot represent a page that changes from full-width material to
columns, passes through a spanning block, or returns to columns below.

The current bibliography parser then performs another line-based visual-row
and column reconstruction. That later path is outside this checklist, but it is
the first required consumer migration after the block layout is established.

## Target Artifact Shape

`PaperDocument.blocks` remains the single block registry. Layout records only
ordered references to those blocks:

```text
PaperDocument
  pages
    page_num
    width
    height
    orientation_groups
      group_id
      orientation
      source_bbox
      canonical_width
      canonical_height
      layout_kind              single | multicolumn | mixed
      layout_regions
        region_id
        bbox
        candidate_gutters
        columns
          column_id
          bbox
        block_placements
          block_id
          start_column
          end_column_exclusive
  blocks
    block_id
    page_num
    source_block_index
    role
    bbox
    canonical_bbox
    orientation
    orientation_group_id
    line_ids
    text
  prose
  entities
  unassigned_block_ids
```

For this layout branch, `layout_region.bbox` and `column.bbox` are expressed in
the canonical coordinate frame of their declared orientation group.
`PaperDocumentBlock.bbox` remains the exact page-space bbox, while
`PaperDocumentBlock.canonical_bbox` remains orientation-local canonical
geometry. Consumers must not compare canonical coordinates across orientation
groups.

The following legacy persisted fields are retired when the new layout becomes
operative:

- orientation-group `column_boundaries`;
- orientation-group `column_bands`;
- block `column_index`; and
- block `column_count`.

Leaf-column number and width belong to the region containing the block. A
column is an exact track frame, not a block owner. A consumer that needs
physical order traverses the region's ordered block placements and resolves
their block IDs through the registry. It does not recalculate columns from
block or line geometry.

## Required Invariants

The following invariants apply at every checkpoint:

- Page-furniture filtering happens before retained blocks are constructed.
- `PaperPositionedDocument` remains the unchanged source of raw line, span,
  character, rule, font, direction, and page geometry.
- Every retained line ID occurs in exactly one `PaperDocumentBlock`.
- Every retained block ID occurs in exactly one layout-region placement for
  its orientation group. A placement may span more than one leaf column.
- Layout does not split, merge, rewrite, or semantically classify blocks.
- Lines remain in preserved block-local source order.
- Block page number, source block index, orientation, source bbox, canonical
  bbox, text, and source line IDs remain traceable.
- Each layout region contains whole blocks; a region boundary may not cut
  through a block.
- Regions are stored in physical page order.
- Columns are stored left to right as track frames without block ownership.
- Region block placements are stored by start column, canonical top, and
  source order; preserved block-local line order is the final traversal level.
- A multicolumn decision requires a positive empty gutter between coexisting
  groups of block bboxes.
- A block that crosses a proposed gutter prevents that gutter.
- Rotated blocks remain in their own orientation group and are never joined
  directly to upright blocks.
- When geometry is insufficient, retain one column and preserve source order.
- No line-width range, x-start cluster tolerance, page-width fraction, minimum
  line count, font-size multiple, or point-distance threshold defines layout.
- No second reading-order artifact or second positioned-text pass is added.
- Prose, entity, and residual ownership remain complete and disjoint.

## Files Expected to Change During Implementation

Primary code:

- `table1_parser/context/paper_document_builder.py`
- `table1_parser/context/paper_document.py`
- `table1_parser/cli.py`

Existing consumers that must be checked when canonical traversal changes:

- `table1_parser/context/table_mentions.py`
- `table1_parser/context/section_parser.py`
- `table1_parser/context/visual_inventory.py`
- `table1_parser/table_regions.py`
- `table1_parser/paper_footnotes.py`
- `table1_parser/paper_style_profile.py`
- `table1_parser/extract/pymupdf_extractor.py`

Documentation to align when the new shape becomes operative:

- `docs/design/paper_document_plan_and_contract.md`
- `docs/design/parsing_output_design.md`
- `docs/design/paper_parse_walkthrough.md`
- `docs/design/paper_bibliography.md`
- `docs/implementation/parser_todo.md`
- `docs/implementation/fallback_inventory.md`
- `docs/implementation/paper_text_reading_order_repair.md`

Do not add a Pydantic model for this nested layout. `PaperDocument` currently
uses a plain declarative dictionary shape, and this change does not demonstrate
a boundary-validation benefit that requires a new model.

## Checkpoint Discipline

Each checkpoint should be independently inspectable and should have one clear
purpose. Do not combine block construction, new ordering behavior, prose
classification changes, and bibliography changes in one unreviewable patch.

Before every operative checkpoint:

1. report the observed problem;
2. name the exact functions being changed;
3. state the proposed logic;
4. explain why it is structural;
5. identify the old or competing path that will be removed or held frozen;
6. list the focused real-paper checks; and
7. wait for explicit approval.

If a checkpoint changes layout decisions, enumerate every new decision rule
before staging or committing. Compare each rule against `AGENTS.md`, the
numeric layout tolerance gate, the canonical document contract, and the
no-fallback rule.

## Step 0: Freeze Scope and Capture the Baseline

- [x] Confirm that this layout migration is the active parser priority before
      residual caption and entity assignment.
- [x] Record the current git status and preserve unrelated user changes.
- [x] Identify the most recent accepted 28-PDF output available for comparison.
- [x] If no suitable current baseline exists, run all 28 PDFs into a fresh
      ignored output directory with up to six bounded workers.
- [x] Record baseline counts for retained document blocks, source line IDs,
      prose blocks, residual blocks, orientation groups, bibliography entries,
      extracted tables, and final parsed tables.
- [x] Inspect each concrete page shape directly in the retained baseline and
      current corpus directories without creating separate focused JSON copies.
- [x] Confirm that this phase does not change bibliography entry logic,
      extraction logic, table geometry, normalization, or semantic parsing.

Checkpoint output: a written baseline and focused-page manifest, with no parser
behavior change.

## Step 1: Construct Blocks Before Layout Without Changing Results

Rearrange `build_paper_document()` so retained blocks exist before any page
column or reading-order calculation.

- [x] After page-furniture filtering, group positioned lines by page,
      orientation group, and source `block_index`.
- [x] Sort lines only by their existing block-local `line_index`.
- [x] Construct a provisional retained block with exact source and canonical
      union bboxes, line IDs, text, orientation, and source-block provenance.
- [x] Preserve the currently accepted heading/body line-boundary refinement.
- [x] Leave the frozen bibliography heading confirmation in its current
      semantic role during this behavior-preserving checkpoint. It may preserve
      an existing accepted heading/body split, but it must not supply columns
      or reading order to the new document layout.
- [x] Preserve current canonical block IDs or define an explicit deterministic
      replacement and compare every changed reference.
- [x] Do not infer columns while creating the block registry.
- [x] Do not sort blocks by line y-position while creating the registry.
- [x] Keep source order as provisional order until layout is available.
- [x] Keep current prose ownership decisions and segment contents unchanged
      during this structural refactor.
- [x] Serialize the same block registry, prose membership, residual membership,
      and downstream artifacts as the baseline.

The initial version may retain the existing page-wide layout functions only as
a temporary ordering consumer after block construction. It must not allow
those functions to participate in block formation. This is a behavior-
preserving checkpoint, not the final layout.

Acceptance gate:

- [x] Every baseline block has the same text, line IDs, page, source block,
      orientation, role, and bboxes.
- [x] Prose and residual ownership are byte-for-byte unchanged apart from any
      explicitly approved serialization ordering.
- [x] All downstream artifacts are substantively unchanged.

Step 1 completed in
`outputs/testpapers_batch_block_first_step1_20260719`, compared with the
accepted `outputs/testpapers_batch_paper_document_step3_bullet4_20260718`
baseline. All 28 parse commands completed. `build_paper_document()` now builds
complete provisional source-block records before the frozen page-wide layout
calculation, and `_order_page_blocks()` only orders those blocks; it no longer
reconstructs them from individual lines. All substantive JSON and Markdown
artifacts are byte-for-byte unchanged. Only generated `report_timestamp`
values differ. The run retains 4,674 blocks, 774 prose blocks, 3,900 residual
blocks, 486 rotated blocks, 1,350 bibliography entries, 92 extracted tables,
and 81 parsed tables.

## Step 2: Add Non-Operative Block Layout Evidence

Add `layout_kind` and `layout_regions` to each populated orientation group, but
do not yet use them to order blocks or drive consumers.

- [x] Build proposals only from retained block canonical bboxes, orientation,
      and source order.
- [x] Give every proposal stable deterministic region and column IDs.
- [x] Record region and column bboxes as exact unions of their block bboxes.
- [x] Record block IDs only; do not duplicate block text, line IDs, roles, or
      geometry inside layout columns.
- [x] Validate that each group block appears exactly once in the proposed
      layout.
- [x] Retain the existing operative order during this checkpoint.
- [x] Add diagnostics for ambiguous groups where source order is preserved,
      without changing pass/fail interpretation.
- [x] Inspect proposed layouts before any consumer uses them.

This proposal lives inside `PaperDocument`; it is not a separate
`PaperReadingOrder` artifact or second ownership model.

Acceptance gate:

- [x] Proposal generation changes no block, prose, entity, residual,
      bibliography, table, section, or Markdown decision.
- [x] Every proposed layout can be flattened deterministically.
- [x] Every group satisfies exact block coverage and uniqueness.

Step 2 completed in
`outputs/testpapers_batch_block_layout_candidate_step2_20260719`, compared with
the accepted Step 1 corpus checkpoint. Each of the 351 populated orientation
groups now has one conservative non-operative region and one column, stable
group-derived IDs, an exact canonical bbox union, source-ordered block IDs, and
the `nonoperative_single_region_source_order_candidate` diagnostic. The 351
candidate columns reference all 4,674 retained blocks exactly once. All 28
parse commands completed. Removing `layout_kind`, `layout_regions`, and
`layout_diagnostics` makes every `paper_document.json` identical to Step 1;
all other substantive JSON and Markdown artifacts are byte-for-byte unchanged,
and only generated `report_timestamp` values differ. Geometry-union, source-
order, uniqueness, and coverage validation passed for every orientation group.

## Step 3: Establish Regions from Exact Block Topology

Region detection is the central structural problem. Column splitting is valid
only after a vertically coherent region has been established. Do not apply the
simple positive-gutter split to all blocks on a page at once.

Implement region formation from exact block relationships:

- [x] Use canonical block top and bottom edges as vertical events.
- [x] Examine the block set active between consecutive exact vertical events.
- [x] A candidate gutter exists only where active blocks occupy both sides and
      their x intervals leave a positive uncovered interval between them.
- [x] Require vertical coexistence for a left/right relationship. Vertically
      stacked blocks with different indents do not establish columns by
      themselves.
- [x] Carry a gutter across adjacent vertical intervals only while the
      intersection of its observed empty x interval remains positive.
- [x] Treat an empty vertical interval as absence of evidence, not by itself as
      a new region.
- [x] End a multicolumn region when a whole block crosses and closes its gutter.
- [x] Represent such a spanning block or group of spanning blocks in a
      one-column region covering its observed width.
- [x] Permit a new multicolumn arrangement below that region; do not propagate
      columns from above.
- [x] Do not place a region boundary through a block. If a block would belong
      to two candidate regions, combine the affected vertical intervals and
      preserve the block whole.
- [x] If exact topology cannot establish a transition, keep one region or
      preserve the source grouping rather than guessing.

This step must be developed and reviewed as non-operative evidence first. The
focused-page inspection should show the exact blocks that caused every region
transition.

Acceptance gate:

- [x] Full-width headings above columns become their own one-column region only
      when their block geometry closes the observed gutter.
- [x] Side-by-side blocks remain in one multicolumn region.
- [x] A spanning caption or object between column runs becomes a one-column
      region.
- [x] A lower column run is detected independently from the upper run.
- [x] Indented single-column headings and paragraphs are not misclassified as
      side-by-side columns.

Step 3 completed in
`outputs/testpapers_batch_block_region_topology_step3_20260719`. All 28 parse
commands completed. The 351 populated orientation groups contain 602 exact
topology regions and 496 positive candidate gutters, covering all 4,674
retained blocks exactly once; 27 rotated orientation groups remain isolated.
Focused visual review confirmed the expected continuous two-column pages, the
upper-column/spanning-caption transition above printed Table 1 on PDF page 4,
and the complex but source-supported topology inside multi-panel figures and
rotated tables. Region bboxes, block coverage, gutter positivity, gutter
crossing, diagnostics, and layout-kind checks passed. Removing the three
layout fields makes every `paper_document.json` identical to Step 2, all other
substantive artifacts are unchanged apart from generated timestamps, and the
simplified implementation reproduces all 28 validated layout hashes exactly.
Column splitting remains deferred to Step 4.

## Step 4: Establish Columns Within Each Region

Once region membership is fixed, construct columns from positive block-level
gutters.

- [x] Sort region blocks by canonical x start for gutter analysis only.
- [x] For each possible left/right partition, compute the greatest right edge
      of the proposed left group and the least left edge of the proposed right
      group.
- [x] Accept the partition only when the left edge is strictly less than the
      right edge and the groups have exact vertical coexistence evidence inside
      the region.
- [x] One accepted gutter creates two columns; two accepted gutters create
      three columns; continue without imposing a maximum column count.
- [x] Reject a gutter crossed by any block assigned to the region.
- [x] Store columns left to right by their observed bboxes.
- [x] Store blocks inside each column by canonical top, then source block order.
- [x] Preserve block-local line order without any geometry recheck.
- [x] Use a single column when no positive gutter is established.

Define `layout_kind` mechanically:

- [x] `single` when the orientation group has one region with one column;
- [x] `multicolumn` when it has one region with more than one column; and
- [x] `mixed` when it has more than one physical layout region.

Do not infer layout kind from textual roles or expected page content.

Acceptance gate:

- [x] Each column has a positive observed content width.
- [x] Adjacent columns have a positive empty gutter.
- [x] Each block is wholly contained in its assigned column bbox.
- [x] Flattening region, column, and block lists emits every group block once.

Step 4 completed in
`outputs/testpapers_batch_block_columns_step4_20260719`. The unchanged 602
Step 3 regions now contain 1,105 materialized columns separated by 503 exact
positive gutters. Of those regions, 253 are single-column, 280 have two
columns, 38 have three, 13 have four, 4 have five, 7 have six, 4 have seven, 2
have eight, and one source-supported figure-label region has 20; no maximum was
imposed. Region-level recomputation adds seven valid gutters across four
regions relative to the Step 3 transition evidence. All 351 orientation groups
retain exact and unique coverage of all 4,674 blocks, including 27 rotated
groups. Column bbox unions, positive widths and adjacent gutters, containment,
left-to-right column order, top-then-source block order, mechanical
`layout_kind`, and diagnostics all passed. All 28 parse commands completed and
all 1,061 artifact comparisons found no substantive change outside the
non-operative layout candidate. Step 5 remains separate.

## Step 4.1: Replace Region-Global Gutters with Vertical Gutter Tracks

The Step 4 candidate assumes that one gutter set applies to every block in a
region. That is too coarse for a region in which one lane refines vertically.
On PDF page 1 of
`Uses of NHANES Biomarker Data for Chemical Risk Assessment- Trends,
Challenges, and Opportunities.pdf`, the abstract spans the future left and
middle columns while the right column is already active; below the abstract,
the left lane divides into two shorter columns. Region-global gutter
recomputation therefore collapses the two lower columns into one wide column.

Replace the Step 3 region-wide gutter suppression and the Step 4 region-wide
column recomputation with one exact vertical-event track model:

- [x] Divide each orientation group at every exact canonical block top and
      bottom edge.
- [x] For every non-empty atomic vertical interval, form the exact union of
      active block x intervals and record every positive uncovered interval
      between occupied components.
- [x] Continue an established gutter track only when its prior x interval and
      the newly observed empty interval have a positive intersection; carry
      that exact intersection forward.
- [x] Treat occupancy confined to only one side of an established gutter as
      absence of evidence. It neither closes the gutter nor creates a region
      transition.
- [x] Treat a block crossing a gutter as closing that gutter only for the
      interval in which the block is active. The track may resume below.
- [x] Permit a new gutter inside an existing lane as a refinement when at
      least one established gutter persists or is merely absent. Do not split
      the region in that case.
- [x] Start a new region only when a non-empty interval closes every
      established gutter. When gutters first appear after a no-gutter phase,
      separate that earlier phase only if its blocks cross every newly
      observed gutter.
- [x] Never place a region boundary at an event crossed by an active block;
      if the proposed transition would cut a block, retain one region.
- [x] Materialize the final disjoint gutter tracks left to right as leaf
      columns. A column bbox is the exact canonical track rectangle bounded by
      the region bbox and its adjacent gutter edges; it is not a duplicate
      block-union owner.
- [x] Replace `columns[].block_ids` with one ordered region-level
      `block_placements` list. Each placement records `block_id`,
      `start_column`, and `end_column_exclusive`, so a block may span adjacent
      leaf columns while remaining present exactly once.
- [x] Order placements by start column, canonical top, and retained source
      order. Preserve line order inside each referenced block.
- [x] Remove the superseded region-global gutter and block-partition logic
      from `_build_block_layout_candidates()`; do not retain it as a fallback.
- [x] Keep the candidate non-operative. Do not change the frozen legacy page
      order, prose ownership, extraction, bibliography parsing, or any table
      artifact at this checkpoint.

Expected focused placement on PDF page 1 of the named paper:

```text
source block 9  abstract              columns [0, 2)
source block 2  lower-left prose      columns [0, 1)
source block 3  lower-middle prose    columns [1, 2)
source blocks 4 and 5 right prose     columns [2, 3)
```

This is one three-leaf-column region: the outer gutter persists, the internal
gutter refines its left lane below the abstract, and the abstract spans the
first two leaves. The former middle-before-left symptom is not repaired by a
separate ordering rule; column-first placement order resolves it from the
correct geometry.

Acceptance gate:

- [x] The focused page has one abstract/right region whose placements match
      the three-leaf geometry above.
- [x] Every retained block has one and only one placement in its orientation
      group, including spanning blocks.
- [x] Every placement range is non-empty and within the region's leaf-column
      count.
- [x] Adjacent leaf columns are separated by positive exact gutter tracks.
- [x] No region boundary cuts a block.
- [x] Previously accepted document-flow relationships remain valid. Internal
      table-block column grouping is not an acceptance criterion for this
      document-layout candidate and remains the responsibility of the separate
      table parser.
- [x] All 28 PDFs complete, and artifacts outside the non-operative layout
      candidate remain substantively unchanged.
- [x] No numeric layout tolerance, semantic vocabulary rule, rescue pass, or
      alternate layout path is added.

Step 4.1 completed in
`outputs/testpapers_batch_block_gutter_tracks_step4_1_20260719`. All 28 parse
commands completed. The 351 populated orientation groups contain 500 regions,
967 leaf columns, 467 exact positive gutter tracks, and 4,674 unique block
placements, including 533 spanning placements; all 27 rotated orientation
groups remain isolated. The focused PDF page 1 has the expected three-leaf
abstract/prose layout. All placement coverage, range, gutter, column-bbox,
region-bbox, region-boundary, ordering, and mechanical `layout_kind` checks
passed. All 1,061 artifact comparisons found no unexpected difference after
excluding the non-operative layout fields and generated report timestamps.

On PDF page 4, printed Table 1, of
`Role of Estimated Glucose Disposal Rate in Staging and Death Risk of
Cardiovascular-Kidney-Metabolic Syndrome- Insights from NHANES 1999-2018.pdf`,
source block 6 shares the following local table-header region and spans four of
its six candidate leaves. This grouping is explicitly accepted for this
non-operative document candidate: Step 4.1 does not parse or validate a
table's internal columns, and every specialized table artifact remains
unchanged.

## Step 5: Validate the Non-Operative Layout Across Focused Pages

Before switching any consumer, render or inspect the proposed region and
column membership for the concrete page forms.

- [x] `NutritionEx.pdf`, PDF page 10: one two-column region, with every
      left-column block before every right-column block.
- [x] `Role of Estimated Glucose Disposal Rate in Staging and Death Risk of
      Cardiovascular-Kidney-Metabolic Syndrome- Insights from NHANES
      1999-2018.pdf`, PDF page 10: one two-column region with source block 7 on
      the left and source block 8 on the right.
- [x] The same exact PDF filename, PDF page 4, printed Table 1: source block 3
      is followed by source block 4 in the upper two-column document flow.
      Internal column grouping among the following table blocks is outside
      this document-layout acceptance check.
- [x] `An environment-wide association study (EWAS) on type 2 diabetes
      mellitus.pdf`, PDF page 9: lower-left blocks precede upper-right blocks
      in flattened column order.
- [x] `Uses of NHANES Biomarker Data for Chemical Risk Assessment- Trends,
      Challenges, and Opportunities.pdf`, PDF page 1: source block 9 spans
      leaf columns `[0, 2)`, source blocks 2 and 3 occupy lower leaf columns 0
      and 1, and source blocks 4 and 5 occupy right leaf column 2. Candidate
      traversal must emit the lower-left and lower-middle blocks before the
      right-column blocks.
- [x] Review at least one genuinely single-column page and one page with a
      full-width heading above columns.
- [x] Review every proposed layout difference from the current page-wide
      metadata before activation.

If a focused page fails, fix the earliest block-region relationship. Do not add
a paper word, paper filename, semantic role, line-gap tolerance, or rescue pass.

Step 5 completed against
`outputs/testpapers_batch_block_gutter_tracks_step4_1_20260719` without a
parser edit or another corpus copy. Artifact assertions and rendered-page
inspection passed for all five named requirements, the genuinely single-column
PDF page 4 of `periodontis2.pdf`, and the full-width title above the mixed
three-leaf layout on PDF page 1 of
`Uses of NHANES Biomarker Data for Chemical Risk Assessment- Trends,
Challenges, and Opportunities.pdf`.

The exhaustive comparison with frozen registry order reviewed all 351
orientation groups. Candidate traversal is unchanged in 257 groups and differs
in 94 groups on 92 PDF pages across 27 papers. All 4,032 reordered block pairs
are explained by the declared mechanics: 1,064 by exact non-overlapping region
order, 2,462 by left-to-right start column, 495 by top-to-bottom order within a
start column, and 11 by retained source-order ties. No unsupported reorder was
found. The candidate remains non-operative; activation and legacy removal were
not approved under this plan.

## Plan Boundary

This plan was abandoned after the accepted Step 5 checkpoint. Steps 0–5
remain the complete record of the non-operative block-layout candidate and
its focused and full-corpus validation. No layout activation, legacy-path
removal, consumer cutover, or bibliography migration was approved or
implemented under this plan.

Any later use of the candidate requires a separate plan and explicit approval.
