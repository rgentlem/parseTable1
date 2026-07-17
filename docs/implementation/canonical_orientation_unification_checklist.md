# Canonical Positioned Evidence Unification Checklist

Goal: use one raw positioned-document source and one orientation-normalized,
table-local evidence structure for every extraction and ownership decision.

```text
PaperPositionedDocument
-> orientation transform exactly once
-> TablePositionedEvidence
-> ExtractedTable
-> TableBoundaryProposal
-> TableRegion and footer ownership
```

This checklist replaces the earlier orientation-unification status account.
The current source still contains competing candidate, rule, bbox, and region
representations, so prior completion claims must not be used as evidence that
the path is unified.

## Non-negotiable invariants

- [ ] `PaperPositionedDocument` is the only raw PDF text, character, span,
      image, rule-segment, and writing-direction source.
- [ ] `TablePositionedEvidence` is the only canonical table-local positioned
      evidence used after orientation projection.
- [ ] Upright and rotated tables use the same processing functions after the
      source-to-canonical affine transform.
- [ ] Source orientation remains provenance only; it never dispatches a later
      extraction, boundary, region, footer, or semantic path.
- [ ] Raw horizontal rule segments are preserved before any coverage or role
      interpretation.
- [ ] Caption and title lines do not enlarge the table-body bbox.
- [ ] `ExtractedTable`, boundary proposals, table regions, and footer ownership
      do not independently reconstruct text lines, rule lines, or table bounds.
- [ ] No fallback, rescue pass, new artifact, new class, vocabulary rule, or
      downstream repair is added.
- [ ] No numeric layout tolerance is added or changed without the exact
      `APPROVE_LAYOUT_TOLERANCE` keyword required by `AGENTS.md`.
- [ ] Raw text, cells, line IDs, character/span references, rule segments,
      source coordinates, canonical coordinates, and transform provenance are
      preserved.

## 0. Freeze and establish the current state

- [x] Revert the unrelated R, manual-page, package-metadata, and vignette work.
- [x] Keep the remaining parser working tree unchanged while planning the
      canonical evidence correction.
- [x] Confirm that no completed corpus output from an unapproved correction is
      used as a baseline.
- [x] Confirm the focused PDF-page-18 failure in `periodontis2.pdf`, printed
      Table 5:
  - canonical candidate bbox is x = 0.000-615.154;
  - the descriptive title is incorrectly retained as extracted row 0 and
    reaches x = 615.154;
  - all subsequent table header, data, and footer text ends by x = 317.230;
  - the closing rule at y = 399.355 reaches x = 322.230 and therefore covers
    the actual table content;
  - `ExtractedTable.metadata.horizontal_rules` is empty;
  - `TablePositionedEvidence` retains the rule segments;
  - `TableBoundaryProposal` retains 36 references for the y = 399.355 rule.
- [x] Confirm the circular failure on that page:
  - the title-inflated bbox makes the closing rule appear to cover only 52.38%
    of the candidate;
  - the candidate rule detector drops it;
  - caption completion then sees no rule boundary and retains only `Table 5`;
  - the descriptive title remains in the grid and continues inflating the bbox.
- [ ] Inventory every current producer and consumer of:
  - candidate/source/canonical bboxes;
  - caption and title bboxes and line IDs;
  - `horizontal_rules` and `full_width_horizontal_rules`;
  - canonical raw and stroked rule segments;
  - row bounds and cell bboxes;
  - orientation and transform metadata.
- [ ] Record the exact files/functions that will be changed, removed, or
      aligned.
- [ ] Present the exact Step 1 patch and focused commands to the user.
- [ ] Obtain explicit approval before editing parser logic.

## 1. Establish one authoritative evidence contract

- [ ] Keep `PaperPositionedDocument` as the source-coordinate artifact.
- [ ] Reuse the existing `TablePositionedEvidence` model; add no parallel
      table-evidence model.
- [ ] Define its canonical table-local contents as:
  - positioned text line IDs and canonical line bboxes;
  - positioned span and character references with canonical bboxes;
  - raw and stroked rule-segment references with canonical segments;
  - caption/title line IDs and canonical caption/title bbox;
  - canonical table-body bbox excluding caption/title text;
  - source bbox and affine-transform provenance.
- [ ] Separate raw evidence from derived interpretation:
  - raw rule segments remain unfiltered evidence;
  - clustered horizontal rule lines are derived from those segments;
  - full-width status is derived separately against the canonical table-body
    bbox;
  - boundary roles are assigned only by `TableBoundaryProposal`;
  - footer ownership is assigned only by `TableRegion`.
- [ ] Update the schema and output-design documentation only if the persisted
      `TablePositionedEvidence` contract changes.

## 2. Make orientation projection the only orientation boundary

- [ ] Detect source writing direction once from `PaperPositionedDocument`.
- [ ] Project text lines, spans, characters, words, rule segments, image bboxes,
      caption/title bboxes, and coarse candidate scope into one upright frame.
- [ ] Apply the identity transform to upright tables through the same function.
- [ ] Preserve inverse mapping to page coordinates as provenance.
- [ ] Remove the current upright-only rule-span/continuation dispatch.
- [ ] Remove the current rotated whole-orientation-group candidate dispatch.
- [ ] After projection, prohibit checks of orientation labels or rotation
      strategy in candidate extraction, grid materialization, boundary
      proposals, table regions, footer ownership, normalization, continuation
      resolution, or semantics.

## 3. Separate caption/title ownership from the table-body bbox

- [ ] Treat an initial candidate only as a coarse evidence scope, not the final
      table bbox.
- [ ] Bind the complete caption/title line sequence before materializing the
      table grid.
- [ ] Exclude the owned caption/title lines when calculating the table-body
      text extent.
- [ ] Calculate the canonical table-body bbox from table-local text, cells, and
      rules that remain after caption/title ownership.
- [ ] Keep caption/title bbox and table-body bbox as separate fields with
      separate meanings.
- [ ] Fail closed with preserved evidence if caption/title ownership or the
      table-body extent is ambiguous.
- [ ] Confirm that `periodontis2.pdf`, PDF page 18, printed Table 5, obtains a
      table-body right edge near x = 317 rather than the title-derived x = 615.

## 4. Preserve one canonical horizontal-rule inventory

- [ ] Build horizontal rule-line records only from the canonical raw/stroked
      rule segments in `TablePositionedEvidence`.
- [ ] Retain every positive-width horizontal segment within the canonical
      table-local evidence scope.
- [ ] Preserve connector segments and source segment identities.
- [ ] Do not use page width or caption/title width to decide whether a raw rule
      exists.
- [ ] Derive table-coverage, stub-coverage, value-coverage, continuity, and
      possible boundary roles after the raw inventory exists.
- [ ] Derive `full_width` only against the canonical table-body bbox.
- [ ] Make `ExtractedTable.metadata.horizontal_rules` and
      `full_width_horizontal_rules` derived projections of this inventory or
      retire them after all consumers migrate.
- [ ] Remove the independent rule inventory produced by
      `layout_fallback.detect_horizontal_rules()` once it has no consumers.
- [ ] Confirm that the y = 399.355 closing rule in `periodontis2.pdf`, PDF page
      18, printed Table 5, is retained and spans the complete table content.

## 5. Materialize `ExtractedTable` from canonical evidence

- [ ] Use the canonical table-body bbox, positioned text, and canonical rule
      inventory to establish physical rows and columns.
- [ ] Build row bounds and cell bboxes in the canonical frame for every table.
- [ ] Preserve exact cell text and source line/span/character provenance.
- [ ] Do not reuse candidate rows or cells merely because a backend or fallback
      already supplied them.
- [ ] Do not rewrite the accepted physical grid after materialization unless
      direct positioned PDF evidence proves the extraction itself is wrong.
- [ ] Ensure the same materialization function is called for upright and
      rotated tables.

## 6. Migrate every downstream consumer

- [ ] `TableBoundaryProposal` consumes canonical rows, cells, and rules only
      from `TablePositionedEvidence` and the derived `ExtractedTable` grid.
- [ ] `TableRegion` consumes the same canonical ordered text/rule evidence.
- [ ] Footer detection sees the same closing rule that boundary proposals see.
- [ ] Footer detection does not read an independently filtered
      `ExtractedTable.metadata.horizontal_rules` list.
- [ ] Body occupancy, leaf candidates, and header candidates consume the final
      table-body bbox and region ownership without rebuilding either.
- [ ] Continuation resolution compares canonical extracted grids and projected
      column schemas without orientation-specific exceptions.
- [ ] Remove all legacy decision reads from duplicate bbox/rule/orientation
      fields.
- [ ] Remove obsolete metadata, helpers, branches, docs, and tests only after
      the canonical consumer has replaced them.

## 7. Focused verification before any corpus run

- [ ] `periodontis2.pdf`, PDF page 12, printed Table 2 continued:
  - no closing rule is invented before `Marital status`;
  - `Marital status` remains table body content;
  - the genuine PDF-page-13 footer remains owned.
- [ ] `periodontis2.pdf`, PDF page 18, printed Table 5:
  - the caption/title is outside the grid;
  - the table-body bbox matches the table content;
  - the y = 399.355 closing rule is retained;
  - the abbreviation line is accepted as the footer;
  - physical rows and columns remain supported by positioned evidence.
- [ ] `Role of Estimated Glucose Disposal Rate in Staging and Death Risk of
      Cardiovascular-Kidney-Metabolic Syndrome- Insights from NHANES
      1999-2018.pdf`, PDF page 4, printed Table 1:
  - the continuous rule segments and connectors remain one closing rule;
  - the correct footer remains available below that rule;
  - the table body bbox does not expand into footer text.
- [ ] The same paper, PDF page 7, printed Table 2:
  - the table ends at the actual closing rule near y = 318.57;
  - Figures 3 and 4 remain separate visual objects;
  - later figure and page rules do not extend the table candidate.
- [ ] Run at least one ordinary upright reference table and confirm that its
      cells, bbox, rules, region ownership, and footer are unchanged.
- [ ] Compare the focused outputs at:
  - `paper_positioned_document.json`;
  - `extracted_tables.json`;
  - `table_boundary_proposals.json`;
  - `table_regions.json`;
  - `body_occupancy.json`;
  - `leaf_column_candidates.json`;
  - `paper_footnotes.json`.
- [ ] Stop and report any unexplained difference. Do not repair it downstream.

## 8. Complete 28-PDF corpus verification

- [ ] Select and record one completed pre-change corpus output as the comparison
      baseline; do not use incomplete or interrupted runs.
- [ ] Parse all 27 external PDFs plus `inst/extdata/NutritionEx.pdf` with up to
      six workers into one fresh output directory.
- [ ] Confirm all 28 commands complete.
- [ ] Compare every physical table fragment and resolved table.
- [ ] Report every changed:
  - physical grid and table bbox;
  - canonical positioned evidence record;
  - boundary proposal and rule inventory;
  - table region and footer assignment;
  - body occupancy and leaf geometry;
  - continuation decision;
  - footnote artifact;
  - processing status.
- [ ] Accept only differences directly explained by the canonical evidence
      correction.
- [ ] Report only current failures in the final failure document.
- [ ] Add no new test without separate permission.
- [ ] Run no pytest command unless the user explicitly requests it for this
      project.

## 9. Retire duplicate paths and prepare commits

- [ ] Confirm that one raw artifact and one canonical table-local artifact own
      all positioned evidence.
- [ ] Confirm that no upright/rotated processing branch remains after canonical
      projection.
- [ ] Confirm that candidate metadata is not an independent rule or bbox source.
- [ ] Delete or align every superseded field, helper, branch, test, and document.
- [ ] Update:
  - `docs/design/parsing_output_design.md`;
  - `docs/design/paper_parse_walkthrough.md`;
  - `docs/implementation/fallback_inventory.md`;
  - `docs/implementation/parser_todo.md`;
  - this checklist.
- [ ] Confirm the R/package work remains reverted and outside this parser
      change.
- [ ] Assess whether focused regression tests are needed before staging and
      obtain permission before adding any.
- [ ] Report the focused PDFs, corpus output, remaining failures, and test
      status before staging.
- [ ] Commit canonical extraction/parser work and its aligned documentation as
      one coherent change; do not include generated `outputs/` or temporary
      review files.

## Definition of done

- [ ] Every table begins with `PaperPositionedDocument` evidence.
- [ ] Every table has one orientation-normalized `TablePositionedEvidence`.
- [ ] Every physical grid is materialized from that evidence.
- [ ] Every boundary, region, footer, occupancy, and header decision consumes
      that same evidence.
- [ ] Caption/title width cannot enlarge the table-body bbox.
- [ ] Raw horizontal rules cannot disappear because they cover too little of a
      page, orientation group, caption, or incorrect candidate bbox.
- [ ] Upright and rotated tables differ only in transform provenance.
- [ ] The four focused table-page checks pass.
- [ ] The complete corpus contains no unexplained regression.
