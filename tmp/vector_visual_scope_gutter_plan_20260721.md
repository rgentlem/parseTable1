# Figure Scope Plan

## Status and Goal

The goal is to identify a captioned figure and materialize its complete
page-space scope as one composite figure block. Text and drawing content inside
the figure remains preserved behind that composite, but document-structure
traversal exposes only the composite.

The required order is:

```text
PaperPositionedDocument visual evidence
-> retained PaperDocument blocks
-> caption-bound FigureScopeCandidate
-> one FigureCompositeBlockCandidate
-> canonical PaperDocument figure entity
```

Tables and boxes are outside this change. The composite-placement mechanism may
be evaluated for them later, but this plan adds no table- or box-detection rule.
Gutter, column, and layout-region consumption of the composite is outside this
plan and must be handled separately after figure ownership is operational.

## Candidate Shape

Record the smallest explicit structure needed for review:

```text
FigureScopeCandidate
  candidate_id
  page_num
  figure_label
  caption_block_ids
  visual_component_ids
  internal_block_ids
  content_bbox
  composite_bbox
  structural_evidence
  concerns
```

`content_bbox` is the exact page-space union of the bound raster and vector
components plus assigned internal text blocks. `composite_bbox` is the exact
page-space union of `content_bbox` and the caption blocks. The source block and
positioned-evidence registries remain unchanged.

After scope detection, record one compact derived block:

```text
FigureCompositeBlockCandidate
  composite_block_id
  figure_scope_candidate_id
  page_num
  bbox
```

Its `bbox` is exactly the linked scope candidate's `composite_bbox`; membership
and provenance remain in the scope candidate rather than being duplicated. A
candidate structural traversal records only:

```text
FigureAtomicStructureCandidate
  page_num
  structural_unit_ids
```

It is present only for pages with an accepted figure. The ordered IDs resolve
either to unchanged source blocks or to the one composite substituted for that
figure's caption and internal blocks. The composite bbox is the exact mask for
intersecting visual and rule evidence. The source registries remain unchanged.
This traversal is the artifact Step 6 validates; the four-field composite
record alone is not an atomic figure.

Step 7 retires both candidate fields. Every page then has one canonical
`PaperDocument.structure` record with the same two-field shape. A composite ID
resolves directly to a canonical `figure` entity containing the page-space
bbox, separate caption and content block membership, and links to the bound
visual components. Only rejected detections remain in
`figure_scope_rejections`; accepted scope evidence is stored on its entity.

## Observed Page 3 Rule Duplication

On `An atlas of exposome–phenome associations in health and disease risk.pdf`,
PDF page 3, none of the 30 reported additions was previously uncaptured. The
ordinary drawing extraction already represented each shape once as a combined
fill-and-stroke (`fs`) record. Extended extraction represented the same bbox as
separate fill (`f`) and stroke (`s`) records. Passing that extended list into
rule extraction admitted the second copy of each bbox.

The 30 duplicates are the 29 circular node outlines in the lower-left network
diagram and the red VOC oval. They contain cubic curve commands rather than
straight-line commands. All 30 lie inside the accepted Figure 1 `content_bbox`,
and all 30 drawing sequence numbers lie within a bound visual component's
recorded sequence range. They were therefore captured by the figure scope but
were also exposed a second time through the independent `rule_segments` list.
Extended visual discovery must remain separate from ordinary rule extraction.
Atomic figure traversal must still hide every legitimate rule record inside the
figure, not merely these duplicates.

## Implementation Steps

- [x] **1. Record page-space visual components without changing rule evidence.**
  - [x] Add one compact `PaperPositionedVisualComponent` record containing only
        a stable ID, component kind, page-space bbox, source index, optional
        nesting level, and optional drawing-sequence range. Store only these
        records in `PaperPositionedPage.visual_components`.
  - [x] Give each existing raster image bbox a stable component ID and retain
        its page-space bbox and source block index. Detect displayed PDF image
        objects; do not depend on the original file having been a PNG.
  - [x] Read `page.get_drawings(extended=True)` once and record compact vector
        clip or group components with their page-space `scissor`/bbox, nesting
        level, and drawing-sequence provenance.
  - [x] Use the extended drawing hierarchy only for visual-component evidence.
        Continue building `rule_segments` and `stroked_rule_segments` from the
        ordinary drawing extraction used before this work. Do not pass extended
        clip, group, or nested drawing records into rule extraction.
  - [x] Do not add a separate render-entry artifact or attempt text-to-drawing
        sequence binding. Figure-internal text assignment uses the exact figure
        envelope in Step 5, not drawing or text extraction order.
  - [x] Treat a default clip equal to the complete page as non-figure evidence.
        Treat a non-full clip only as component evidence, not as a figure by
        itself.
  - [x] Add no numeric layout tolerance.

- [x] **2. Build retained document blocks unchanged.**
  - [x] Apply page-furniture filtering first.
  - [x] Preserve every block's line IDs, source block, page-space bbox,
        orientation-local canonical bbox, writing direction, text, and source
        order.
  - [x] Do not change prose, residual, bibliography, or entity ownership in
        this checkpoint.

- [x] **3. Build caption assemblies.**
  - [x] Scan retained blocks for an explicit block-leading `Fig.` or `Figure`
        label and number.
  - [x] Preserve the matching block as the caption anchor.
  - [x] Assemble additional caption blocks only when they are on the same page,
        consecutive in retained source order, and have exact positive vertical
        overlap with the anchor caption band. Store the ordered block IDs; do
        not merge their text or bboxes.
  - [x] If more than one caption assembly is possible, leave the caption
        unbound and record the ambiguity.

This assembly supports the two side-by-side caption blocks on PDF pages 4 and
5 of the focused paper.

- [x] **4. Bind visual components to one caption.**
  - [x] Consider raster and vector components on the caption's page.
  - [x] Consider only components entirely above the caption assembly and require
        exact positive page-space horizontal overlap. Do not use PDF extraction
        order, edge alignment, a distance threshold, or a component below the
        caption.
  - [x] Bind the compatible components only when no competing figure caption
        claims any component in that set.
  - [x] Preserve sibling raster panels or vector clip components separately
        inside the candidate, but unite their exact bbox union as one figure
        `content_bbox`.
  - [x] Do not infer a figure from the presence, size, or count of clip
        rectangles alone. If caption-to-component binding is not unique, fail
        closed.

- [x] **5. Assign figure-internal text blocks.**
  - [x] Define one exact figure envelope from the horizontal union of the bound
        components and caption assembly, the highest component top, and the
        caption assembly's top edge.
  - [x] Assign unchanged non-caption blocks with exact positive page-space
        intersection with that envelope. Do not use render sequence, extraction
        order, a page-width threshold, or an overlap percentage.
  - [x] Include upright and vertical figure labels, axes, legends, panel
        letters, and annotations when both requirements hold.
  - [x] Keep every assigned block unchanged in the canonical block registry and
        list it once in `internal_block_ids`.
  - [x] Do not assign a prose block merely because it is near the figure.
        Uncertain blocks remain ordinary residual or prose candidates.
  - [x] Recompute `content_bbox` and `composite_bbox` as exact unions after
        assignment.

- [x] **6. Materialize and validate one atomic composite figure candidate.**
  - [x] Create exactly one `FigureCompositeBlockCandidate` for each accepted
        figure scope and none for rejected or ambiguous scopes.
  - [x] Link it to the scope candidate and copy only the page number and exact
        `composite_bbox`; do not duplicate caption, internal-block, or visual-
        component membership.
  - [x] Before materializing it, require every retained block with exact positive
        page-space intersection with the interior of `composite_bbox` to be an
        existing caption or internal member of that scope. Reject the scope if
        an intersecting block is unclaimed; do not silently absorb prose.
  - [x] Build a candidate structural traversal that emits the composite exactly
        once and does not emit its caption blocks, internal blocks, visual
        components, or rule evidence independently.
  - [x] Mask raw visual components by exact positive bbox intersection with the
        composite interior. Mask a raw rule segment when the segment or its
        recorded drawing bbox intersects the composite interior. Geometry that
        only touches the composite boundary remains outside.
  - [x] Keep every covered block, visual component, and rule segment unchanged
        in `PaperDocument` or `PaperPositionedDocument`. Figure processing can
        recover the complete source evidence from the linked scope, page, and
        bbox; do not copy thousands of source records into the composite.
  - [x] Validate the one-to-one scope/composite relationship, unique member
        ownership, exact bbox union, complete interior masking, and no change to
        evidence or structural units outside the bbox.
  - [x] Persist the candidate structural traversal for inspection, but do not
        make it the canonical traversal or add gutter, column, or reading-order
        interpretation in this step.

- [x] **7. Atomically cut over to canonical figure ownership.**
  - [x] Require the focused checks and the 28-PDF review of the atomic candidate
        traversal to pass before changing operative behavior.
  - [x] Promote each accepted figure scope into one canonical
        `PaperDocument` figure entity with separate caption and content block
        membership; leave rejected or ambiguous candidates unassigned.
  - [x] Replace the canonical document-structure traversal atomically with the
        already-validated traversal from Step 6. Step 7 must not introduce new
        containment or figure-detection logic.
  - [x] Expose each accepted figure exactly once through its composite block.
        Access to covered blocks and positioned evidence requires explicit
        figure-evidence retrieval rather than ordinary structural traversal.
  - [x] Preserve every source block and line exactly once across prose, figure
        entities, other entities, and residual ownership, while preserving
        separate caption and content membership.
  - [x] Remove or retire superseded non-operative composite fields, competing
        figure ownership, and inspection paths in the same change. Candidate
        evidence may remain only as provenance linked to the canonical entity.
  - [x] Update persisted-output documentation and the paper parse walkthrough
        in the cutover change.
  - [x] Run all 28 PDFs after cutover and fail closed on incomplete ownership,
        duplicate membership, an inexact bbox union, or exposed interior
        evidence.
  - [x] Do not change gutter, column, or layout-region input in this cutover.
        A later layout task must consume the same canonical composite block and
        must not rediscover or independently filter its member blocks.

## Required Checks

- [x] `An atlas of exposome–phenome associations in health and disease risk.pdf`,
  PDF page 3, printed Figure 1: ordinary rule extraction retains the original
  combined fill-and-stroke records, extended extraction adds no duplicate
  stroke bboxes to `rule_segments`, and no legitimate rule inside the figure
  appears independently in the atomic candidate traversal.
- [x] `An atlas of exposome–phenome associations in health and disease risk.pdf`,
  PDF page 4, printed Figure 2: one composite figure-plus-caption block; all
  lower article blocks remain outside it.
- [x] The same exact PDF filename, PDF page 5, printed Figure 3: one composite
  figure-plus-caption block; all lower article blocks remain outside it.
- [x] `An environment-wide association study (EWAS) on type 2 diabetes
  mellitus.pdf`, PDF page 5, printed Figure 2: construct the scope from the
  raster image bbox even though the page has no vector clip component.
- [x] `Role of Estimated Glucose Disposal Rate in Staging and Death Risk of
  Cardiovascular-Kidney-Metabolic Syndrome- Insights from NHANES 1999-2018.pdf`,
  PDF page 4, printed Table 1: its many clip components must not become a figure
  without an explicit compatible figure caption.
- [x] Across all 28 PDFs, validate one composite per accepted scope, unique
  component/block membership, exact bbox unions, complete interior masking, and
  no change outside each composite bbox. Confirm that ordinary rule extraction
  is identical to the pre-visual-component baseline.
- [x] At Step 7, compare the full corpus before and after the atomic cutover and
  confirm that every difference is an intended figure ownership or derived
  structural-view change with preserved raw positioned evidence and unchanged
  layout candidates.
