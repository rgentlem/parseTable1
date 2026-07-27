# Canonical Positioned-Evidence Unification Checklist

## Goal and scope

Give every extracted table one canonical geometry path and one authoritative
typed positioned-evidence record. Upright tables must use the identity transform
through the same path used to rotate sideways tables. Boundary, region, header,
body, footer, annotation, and normalization consumers must read that final
canonical table rather than reconstructing or selecting among competing
metadata.

This work must preserve cell text and physical row/column identity. It must not
add a paper-specific rule, numeric layout tolerance, fallback, alternate
extractor, compatibility copy, second evidence model, or downstream repair.
Each behavior-changing step requires explicit parser-logic approval before
implementation.

The active work is limited to making body occupancy authoritative for the
physical axis and body-cell placement while preserving the existing
`HeaderStructureCandidate` as the authority for terminal leaves and
multicolumn groups. Later work is limited to a read-only artifact-cycle audit,
separately approved duplicate-cycle removal, and verification. Text-row and
mixed-row handling, semantic-role redesign, and numeric-tolerance removal are
outside this checklist. Implement and approve one behavior-changing step at a
time, preserving Step 2 as the comparison checkpoint.

## Established baseline

- Steps 1 through 3 are implemented and validated. The selected grid and its owned
  positioned references use one exact identity-or-sideways affine path, and
  `ExtractedTable.positioned_evidence` is the sole table-local positioned-
  evidence contract.
- The CLI still builds provisional geometry artifacts, canonicalizes the
  extracted tables, and then builds the same geometry artifact family again.
- The earlier partial Step 3 implementation that treated body-occupancy bands
  as both physical grid columns and semantic header leaves was removed. The
  replacement Step 3 keeps those contracts separate.
- In `periodontis2.pdf`, PDF page 18, printed Table 5, body occupancy identifies
  12 physical bands while the temporary extractor grid estimates 11 columns.
  Semantic-role interpretation for this table is outside this checklist.
- The comparison checkpoint for the remaining work is
  `outputs/canonical_positioned_evidence_step2_focused_20260725`.

## 1. Canonicalize the selected table through one transform

Outcome: the selected extracted grid and its owned positioned references pass
through one exact source-to-canonical transform before downstream geometry is
built.

- [x] Establish and verify one exact identity-or-sideways affine path for the
  selected grid and its owned positioned evidence without changing cells,
  boundaries, captions, or downstream semantics.

Step 1 checkpoint — 2026-07-25: source positioned objects are page-space;
the selected grid, cells, row bounds, column boundaries, and candidate geometry
are already in the canonical orientation-group frame because the grid is built
from transformed positioned words. The implementation now derives the final
orientation from table-owned line directions, uses one affine matrix constructor
for identity and sideways transforms, projects owned words, characters, raw and
stroked rules together, and stores line/span/word/character references in
canonical reading order. Focused output is in
`outputs/canonical_positioned_evidence_step1_focused_20260725` and matches the
baseline in cells and every downstream semantic artifact; only positioned-
evidence reference ordering and report timestamps differ.

Stop if source objects used by the selected table cannot be assigned one proven
coordinate frame, if the transform would need a new tolerance, or if preserving
the grid requires a fallback or second extraction path.

## 2. Move positioned evidence to one typed authority

Outcome: `ExtractedTable.positioned_evidence` is the sole table-local positioned
evidence contract, with no live metadata copy or compatibility alias.

- [x] Make the existing `TablePositionedEvidence` model a required
  `ExtractedTable.positioned_evidence` field and migrate every consumer in one
  cutover.
- [x] Remove the metadata writer, all metadata readers, and every compatibility
  alias while preserving the record's source references and canonical
  transform exactly.
- [x] Confirm the old key is absent from code and fresh outputs, update the
  persisted schema and walkthrough documentation, and verify focused semantic
  artifacts are unchanged.

Step 2 checkpoint — 2026-07-25: the extractor passes the typed evidence model
directly into both provisional and final extracted tables. Canonical extraction,
boundary proposals, table regions, body occupancy, leaf/header candidates,
cell annotations, and canonical paper-entity ownership read only that field.
The focused output in
`outputs/canonical_positioned_evidence_step2_focused_20260725` preserves every
evidence value from Step 1 and has no `table_positioned_evidence` metadata key.
After accounting for the intentional field relocation and source-artifact label,
all focused downstream artifacts are unchanged.

Stop if any consumer requires both old and new locations, if migration exposes
incompatible evidence meanings, or if the cutover cannot remain atomic.

## Remaining-work decisions

Physical grid structure and semantic header structure are separate:

- A physical column band is an x-axis interval in the extracted grid.
- A grid column is a physical `ExtractedTable` column.
- A header leaf is a terminal header node mapped to a grid column.
- A value leaf is a header leaf whose column contains table values.
- A descriptor column participates in the row axis; a table may have more than
  one.
- A header group spans multiple terminal nodes or lower groups.
- `body` means the data-row region. The complete caption-free extracted
  rectangle is the `grid`.

Step 2 remains the comparison baseline. The 2026-07-25 reconstruction in
`tmp/canonical_positioned_evidence_step2_reconstruction_20260725` matches all
116 focused artifacts across the three Step 2 papers after excluding only
`report_timestamp`. The old metadata key and the partial Step 3 canonical body,
row, and column fields are absent.

## 3. Separate physical-grid and semantic-header contracts

Outcome: no physical band or grid column is called a semantic leaf or assigned
a semantic role before header interpretation.

- [x] Rename `canonical_body_bbox` to `canonical_grid_bbox` in one schema and
  consumer cutover.
- [x] Define canonical row bounds and canonical physical-column bounds as the
  final grid axes, without stub, descriptor, value, group, or leaf meaning.
- [x] Distinguish a cell's extracted bbox from its row/column slot; neither
  implies that the cell is a semantic leaf.
- [x] Define terminal header nodes, value leaves, descriptor columns, header
  groups, and their mappings to physical grid columns.
- [x] Remove `provisional_role` and other stub/value assignments from
  geometry-only band evidence.
- [x] Align the persisted schema and design contracts with these meanings
  before implementing later semantic decisions.

Step 3 checkpoint — 2026-07-25: `TablePositionedEvidence` now reserves
`canonical_grid_bbox`, `canonical_row_bounds`, and
`canonical_physical_column_bounds` as role-free physical-grid fields. The
removed partial implementation's `canonical_body_bbox` has no live consumer;
the new grid fields intentionally remain null or empty until Step 4 populates
the final axis. `TableCell.bbox` is documented as geometry evidence rather
than slot or leaf identity. The legacy-named leaf-candidate artifact now emits
`PhysicalColumnBandCandidate` records and `physical_band_ids` without
`provisional_role` or a provisional stub. Header interpretation creates
terminal nodes separately and maps them with `physical_col_idx`; the existing
first-column descriptor assumption remains confined to semantic header
interpretation outside this checklist.

Focused output is in
`tmp/canonical_positioned_evidence_step3_contract_focused_20260725`. Across the
three Step 2 papers, all 116 artifacts match the reconstructed Step 2 baseline
after normalizing only the approved Step 3 field/terminology cutover and
`report_timestamp`. No cells, grid boundaries, regions, semantic schemas,
continuation decisions, processing statuses, or other parser behavior changed.

Stop if a consumer needs a provisional semantic role to determine the physical
grid, or if one field would retain both physical and semantic meanings.

## 4. Correct the physical-axis authority contract

Outcome: the implementation plan states the agreed authority without changing
parser behavior.

- [x] Record that adequate body-occupancy bands, not the extractor-estimated
  column grid, define the final physical column axis.
- [x] Keep physical bands role-free and keep semantic header leaves as later
  nodes mapped to physical-column indices.
- [x] Exclude body text-row and separator-row classification from this change.
- [x] Limit the next implementation step to the occupancy-authority cutover;
  leave the duplicate preliminary/final artifact cycle in place.
- [x] Keep the row-index audit, duplicate-cycle removal, and final verification
  as separately gated work after the occupancy/header-authority checkpoint.

Step 4 checkpoint — 2026-07-26: this documentation-only correction replaces
the withdrawn extractor-grid-authority plan. It makes no parser, schema, or
output change.

Stop if the authority statement starts requiring text-row classification,
semantic header-role redesign, a new tolerance, or one-pass artifact cleanup.

## 5. Make occupancy and the header candidate authoritative

Outcome: every accepted canonical `ExtractedTable` uses adequate body-occupancy
bands as its physical columns and for body-cell placement. The existing
`HeaderStructureCandidate` for that table remains authoritative for terminal
header leaves and multicolumn groups. The two artifacts must be exactly
structurally consistent; otherwise the table fails without repair or fallback.
The existing preliminary/final artifact cycle remains unchanged in this step.

- [ ] Reuse the current boundary proposals, row ownership, body occupancy,
  role-free physical-band candidates, and `HeaderStructureCandidate` without
  changing how any of them is constructed.
- [ ] Remove every decision that lets the temporary extractor grid determine or
  validate the final physical-column count, bounds, or body-cell placement.
- [ ] Require adequate occupancy evidence; if it is absent, fail through the
  existing failure path instead of selecting the temporary extractor grid.
- [ ] Materialize `n_cols`, physical-column bounds, and body-cell column
  placement solely from the accepted occupancy bands.
- [ ] Populate `canonical_grid_bbox`, `canonical_row_bounds`, and
  `canonical_physical_column_bounds` from the accepted final physical axes.
- [ ] Use the existing `HeaderStructureCandidate` without rebuilding or
  reallocating it from temporary extractor header cells or their `col_idx`
  values.
- [ ] Require the candidate's physical-band identities and order to equal the
  accepted occupancy bands exactly.
- [ ] Require exactly one terminal header leaf for each physical column and
  exactly one physical-column mapping for each leaf.
- [ ] Require every header group to reference existing, contiguous terminal
  leaves without conflicting spans.
- [ ] Accept an empty terminal label for a descriptor column; it is not a
  structural inconsistency.
- [ ] On any occupancy/header-candidate inconsistency, fail through the existing
  failure path without reconstructing either artifact, reallocating header
  text, or consulting the temporary extractor grid.
- [ ] Preserve candidate leaf text, multicolumn groups, positioned word and line
  references, bounding boxes, rule evidence, and source ordering exactly; do
  not split or redistribute a spanning header run into ordinary column cells.
- [ ] Retain the temporary extractor grid only as raw source provenance. Its
  column count, bounds, header allocation, and `col_idx` values cannot validate,
  override, or reconstruct occupancy or the header candidate.
- [ ] Preserve caption/header/body/footer ownership, continuation handling, and
  the existing duplicate preliminary/final artifact cycle.
- [ ] Add no text-row or mixed-row handling, semantic-role change, fallback,
  repair path, artifact, construction-order change, or numeric-tolerance work.
- [ ] Confirm `periodontis2.pdf`, PDF pages 10 and 11, printed Table 1 and its
  continuation, retain 13 physical columns, one blank descriptor leaf plus 12
  terminal leaves, and three multicolumn groups spanning columns 1–4,
  5–8, and 9–12.
- [ ] Confirm focused differences are limited to occupancy becoming the
  physical-axis and body-placement authority; the accepted
  `HeaderStructureCandidate` and unrelated artifacts remain unchanged.
- [ ] Record the focused checkpoint and stop before the row-index audit or
  duplicate-cycle removal.

Stop at the first unexplained failure or difference and return for discussion;
do not revise the implementation in response. Also stop if this cutover needs a
new artifact, a changed artifact-construction order, a tolerance change, or any
header reconstruction.

## 6. Audit the duplicate artifact cycle

Outcome: the dependencies that currently require preliminary and final geometry
artifact builds are known before any behavior changes.

- [ ] Trace row indices and caption/header/body/footer ownership through both
  artifact builds.
- [ ] Identify every consumer of each preliminary and final boundary, region,
  occupancy-band, and header-candidate artifact.
- [ ] Record the direct wiring needed to preserve the Step 5 occupancy and
  `HeaderStructureCandidate` authorities in one artifact build.
- [ ] Confirm the proposed removal needs no new artifact, compatibility path,
  fallback, text-row handling, semantic-role decision, or tolerance change.
- [ ] Report the audit and obtain separate approval before changing parser
  behavior.

Stop if row identity or ownership cannot be preserved exactly, or if removing
the cycle requires a new parser decision.

## 7. Remove the duplicate artifact cycle

Outcome: each table builds its boundary, region, occupancy, physical bands, and
`HeaderStructureCandidate` once, while preserving the Step 5 authority and
failure contracts.

- [ ] Remove the second construction of the same geometry-artifact family and
  wire every consumer to the single accepted artifacts identified in Step 6.
- [ ] Preserve occupancy as the sole physical-axis and body-cell-placement
  authority and preserve the same accepted `HeaderStructureCandidate` as the
  sole leaf/group authority.
- [ ] Remove only competing selection, reconstruction, or remapping paths proven
  unused by the Step 6 audit; retain the temporary extractor grid solely as raw
  source provenance.
- [ ] Preserve row identity, ownership, continuation behavior, positioned
  references, and persisted artifact meanings without a compatibility path.
- [ ] Confirm no header candidate is regenerated from canonical cells and no
  temporary extractor column assignment becomes authoritative.
- [ ] Run the focused checks and accept no difference from the completed Step 5
  checkpoint except removal of the duplicate construction cycle.
- [ ] Record the checkpoint and stop before corpus verification.

Stop at the first unexplained failure or difference and return for discussion;
do not add a repair or alternate construction path. Also stop if cycle removal
requires text-row or mixed-row handling, semantic-role work, a new artifact, or
a numeric-tolerance change.

## 8. Verify, document, and close the cutover

Outcome: focused and corpus evidence support the two-authority contract, no
competing live decision path remains, and affected documentation is aligned.

- [ ] Verify `periodontis2.pdf`, PDF pages 10 and 11, printed Table 1 and its
  continuation, preserve 13 occupancy columns and the accepted blank-plus-12
  terminal leaves with groups spanning columns 1–4, 5–8, and 9–12.
- [ ] Verify `periodontis2.pdf`, PDF page 18, printed Table 5, uses its 12
  occupancy bands as physical columns without treating the temporary
  11-column extractor estimate as evidence against them.
- [ ] Verify `Role of Estimated Glucose Disposal Rate in Staging and Death Risk
  of Cardiovascular-Kidney-Metabolic Syndrome- Insights from NHANES
  1999-2018.pdf`, PDF pages 4 and 7, printed Tables 1 and 2, preserve their
  accepted occupancy axes and header candidates.
- [ ] Verify `GOLD BioAge and depression- Associations with mortality among
  depressed NHANES participants (2005–2018).pdf`, PDF page 5, printed Table 3,
  preserves its accepted occupancy axis and header candidate.
- [ ] Compare extraction, boundaries, regions, occupancy, header candidates,
  annotations, footnotes, continuation decisions, and processing status after
  each approved behavior change.
- [ ] Run all 27 external PDFs plus `inst/extdata/NutritionEx.pdf` with no more
  than six workers and accept only source-evidence-supported differences.
- [ ] Confirm repository search and fresh outputs contain no competing live
  physical-axis, body-placement, header reconstruction, or duplicate artifact
  construction path.
- [ ] Update only the ToDo, design, schema, walkthrough, and implementation
  documentation affected by the implemented contract.
- [ ] Reduce this checklist to the essential completed checkpoint and report
  the PDFs, output directory, failures, decision rules, final diff size, and
  any conflict before staging or committing.

Stop at the first unexplained focused or corpus failure and return for
discussion; do not iterate on the implementation. Also stop if any canonical
fact retains competing authority or completion requires an unapproved parser
rule.
