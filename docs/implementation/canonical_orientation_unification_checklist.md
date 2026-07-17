# Extracted-Table Orientation and Geometry Authority Checklist

Goal: start with the selected extracted table, rotate sideways tables accurately,
and then establish one authoritative location for every table geometry and size
fact.

```text
selected extracted table + PaperPositionedDocument references
-> one source-to-canonical transform
-> one canonical ExtractedTable
-> TableBoundaryProposal
-> TableRegion/footer ownership
```

The earlier proposal to add caption and nullable body-bbox fields without
removing their existing equivalents is withdrawn. It would have created more
storage locations without establishing authority.

## Invariants

- [ ] The initially selected extracted grid is the input. It is not retained as
      a competing persisted table after canonicalization.
- [ ] Upright tables use the identity transform; sideways tables use one exact
      affine transform through the same code path.
- [ ] Rotation is inferred from table-owned positioned evidence, not page width
      or the fraction of the page occupied by the table.
- [ ] Every table-local word, character, line, cell bbox, rule segment, row
      bound, and column bound is transformed by the same matrix exactly once.
- [ ] Source-coordinate evidence remains authoritative only in
      `PaperPositionedDocument`.
- [ ] Canonical table geometry is authoritative only in the final
      `ExtractedTable` and its typed `TablePositionedEvidence`.
- [ ] A field is moved atomically: add the authoritative typed location, migrate
      every consumer, and remove the old metadata copy in the same approved
      change.
- [ ] Candidate metadata is temporary extraction state, not persisted geometry
      authority.
- [ ] No new evidence class, fallback path, vocabulary shortcut, or numeric
      layout tolerance is added.
- [ ] If orientation or geometry cannot be proved from positioned evidence, the
      table fails closed and preserves its raw references.

## 0. Freeze and record the present defect

- [x] Preserve checkpoint commit `484a29b` as the current parser state.
- [x] Revert the unrelated R/package work.
- [x] Confirm that `TablePositionedEvidence` is currently created only after
      candidate bbox selection, filtered-rule construction, candidate ranking,
      and caption completion.
- [x] Confirm that the pipeline currently builds boundary/region/occupancy/leaf
      artifacts from a provisional grid, canonicalizes the grid, and then builds
      the same artifacts again.
- [x] Confirm that upright and sideways tables currently enter different
      candidate paths after their source geometry has already been projected.
- [x] Confirm the guidepost failure in `periodontis2.pdf`, PDF page 18, printed
      Table 5:
  - the title-inflated candidate reaches x = 615.154;
  - actual table text ends by x = 317.230;
  - the closing rule reaches x = 322.230 at y = 399.355;
  - raw canonical rule segments retain that rule;
  - `ExtractedTable.metadata.horizontal_rules` loses it.
- [x] Withdraw the previous proposal to add more nullable bbox fields.
- [ ] Obtain approval for the first implementation step before parser edits.

## 1. Canonicalize orientation from the extracted table

- [ ] Audit the selected extracted table first and record the actual coordinate
      frame of its candidate bbox, cell bboxes, row bounds, positioned lines,
      words, characters and rules. Do not assume the existing fields share a
      frame.
- [ ] Treat the selected extracted table bbox and its referenced positioned
      objects as the table-local source scope.
- [ ] Determine the table orientation from the writing directions of its owned
      lines/characters and the axes of its owned rules.
- [ ] Do not infer sideways orientation from page orientation, page coverage,
      table width, or expected table content.
- [ ] Calculate one affine source-to-canonical matrix and its inverse.
- [ ] Apply the identity matrix to upright tables through the same function.
- [ ] Apply the matrix once to:
  - positioned line, span, word and character bboxes;
  - extracted cell bboxes;
  - raw and stroked rule segments;
  - image/visual-object bboxes that intersect the table-local scope;
  - the coarse candidate scope.
- [ ] Sort canonical lines and cells in upright reading order only after the
      transform.
- [ ] Remove the current upright-only rule-span/continuation dispatch and the
      sideways whole-orientation-group dispatch.
- [ ] After transformation, retain orientation only as provenance; no later
      stage may branch on it.

### First proposed implementation patch

This first behavior patch changes orientation normalization only. It adds no
field and moves no metadata yet.

- [ ] Make `canonical_extraction.finalize_canonical_extracted_tables()` accept
      the selected extracted grid plus its `PaperPositionedDocument` source
      references as the canonicalization input.
- [ ] Use `normalize_positioned_geometry_for_rotation()` as the single affine
      implementation for upright and sideways tables; remove any duplicate
      rotation calculation encountered in this path.
- [ ] Apply that matrix to the selected table's cells and referenced positioned
      evidence exactly once, using the identity matrix for upright tables.
- [ ] Preserve the selected cell text and physical row/column identity; this
      patch changes coordinates, not table content or table boundaries.
- [ ] Keep the result in the existing evidence location temporarily so the
      patch does not introduce another authority before Step 2 moves it.
- [ ] Do not change caption completion, table-body size, rule clustering,
      boundary roles, regions, footer ownership or normalization.
- [ ] Run `python3 -m compileall table1_parser` and the focused sideways and
      upright tables in Step 6. Do not run pytest or the corpus.

### Rotation validity checks

- [ ] Applying the inverse matrix to every transformed bbox corner reproduces
      its source coordinate.
- [ ] Every canonical cell bbox is inside the canonical evidence scope.
- [ ] Canonical row order is monotonic from top to bottom.
- [ ] Canonical column order is monotonic from left to right.
- [ ] A horizontal source rule for an upright table remains horizontal.
- [ ] A source rule belonging to a sideways table has the correct horizontal or
      vertical role after transformation.
- [ ] Text and rules from other page orientations are not admitted merely
      because their source bboxes overlap.
- [ ] A failed validity check rejects canonicalization instead of invoking a
      different extractor.

## 2. Establish authoritative metadata and size from the canonical table

- [ ] Use the existing `TablePositionedEvidence`; add no parallel evidence
      model.
- [ ] Promote it from untyped
      `ExtractedTable.metadata["table_positioned_evidence"]` to one typed
      `ExtractedTable.positioned_evidence` field.
- [ ] Move rather than copy: update every consumer and remove the metadata key
      in the same patch.
- [ ] Record the following ownership contract in the schema and output docs:

| Fact | Sole authority |
|---|---|
| Raw page lines, spans, words, characters, rules, images and source bboxes | `PaperPositionedDocument` |
| Source references, orientation, affine matrix, inverse provenance and canonical positioned bboxes | `ExtractedTable.positioned_evidence` |
| Final physical row/column count and cell text | `ExtractedTable.n_rows`, `n_cols`, and `cells` |
| Final canonical cell bboxes | `ExtractedTable.cells[].bbox` |
| Final canonical table-body bbox, row bounds and column bounds | `ExtractedTable.positioned_evidence` |
| Complete caption/title ownership | one typed caption region referenced by `ExtractedTable`; not candidate metadata and not the table-body bbox |
| Raw horizontal segments | `ExtractedTable.positioned_evidence`, by references into `PaperPositionedDocument` |
| Clustered rule lines, coverage and possible boundary roles | `TableBoundaryProposal` |
| Caption/header/body/footer row ownership and selected boundaries | `TableRegion` |

- [ ] Set typed `positioned_evidence` on `ExtractedTable` and stop writing
      `metadata["table_positioned_evidence"]`.
- [ ] Migrate all readers in canonical extraction, boundary proposals, table
      regions, body occupancy, leaf candidates, header candidates and cell-text
      annotations.
- [ ] Confirm with repository search that no live reader of the metadata key
      remains.
- [ ] Do not create aliases or compatibility copies for the moved evidence.
- [ ] Update `parsing_output_design.md` and `paper_parse_walkthrough.md` in the
      same patch because the persisted `ExtractedTable` shape changes.

## 3. Complete authoritative table-body geometry

- [ ] Complete caption/title ownership before measuring the table body.
- [ ] Exclude caption/title lines from the canonical table-body bbox.
- [ ] Derive final physical rows and columns from the transformed cell/text
      geometry.
- [ ] Store the final canonical table-body bbox, row bounds and column bounds
      once in `ExtractedTable.positioned_evidence`.
- [ ] Store canonical cell bboxes only in `ExtractedTable.cells[].bbox`.
- [ ] Ensure `n_rows` and `n_cols` exactly match the final cell axis.
- [ ] Delete the following independent metadata authorities as their consumers
      migrate:
  - `bbox` and candidate/source/canonical bbox copies;
  - `row_bounds`;
  - `table_cells`;
  - `positioned_column_start_boundaries`;
  - `horizontal_rules`;
  - `full_width_horizontal_rules`.
- [ ] Keep coarse candidate bounds only inside candidate construction; do not
      serialize them as final table size.
- [ ] Do not calculate the final table bbox from caption width, page width,
      article prose, footer text, or later figures.

## 4. Build one rule and boundary path from canonical geometry

- [ ] Preserve every positive-width raw horizontal segment referenced by the
      canonical extracted table.
- [ ] Cluster rule segments once in `TableBoundaryProposal`.
- [ ] Calculate rule coverage against the authoritative canonical table-body
      bbox, not the page or caption width.
- [ ] Store derived rule roles only in `TableBoundaryProposal`; do not copy a
      rule-y list back into `ExtractedTable` or `TableRegion`.
- [ ] Make `TableRegion` consume proposal candidates for table start,
      header/body, body/footer and table end.
- [ ] Make footer ownership see exactly the same closing-rule candidate and raw
      segment references as boundary selection.
- [ ] Make normalization consume the final `TableRegion`; it must not reread
      legacy rule metadata.

## 5. Remove the duplicate provisional/final geometry cycle

- [ ] Canonicalize the selected extracted table before building boundary,
      region, occupancy, leaf or header artifacts.
- [ ] Build those artifacts once from the final canonical `ExtractedTable`.
- [ ] Remove the first provisional call to
      `cli._build_table_geometry_artifacts()`.
- [ ] Remove candidate rule/row/bbox scoring inputs that duplicate the final
      canonical evidence.
- [ ] Retire `layout_fallback.detect_horizontal_rules()` after its final live
      consumer is gone.
- [ ] Retire the uncalled legacy PDF reconstruction functions
      `table_detector.detect_page_candidates()` and
      `table_detector.detect_table_candidates()` only during final cleanup.

## 6. Focused verification after each approved behavior change

- [ ] `periodontis2.pdf`, PDF page 18, printed Table 5:
  - the sideways table becomes upright through the single transform;
  - the caption/title is outside the physical grid;
  - the table-body right edge follows the content near x = 317;
  - the y = 399.355 rule spanning to x = 322.230 is retained as the closing
    rule;
  - the abbreviation line is available to footer ownership.
- [ ] `periodontis2.pdf`, PDF pages 12–13, printed Table 2 continued:
  - `Marital status` remains body content;
  - the real footer remains owned on the terminal fragment.
- [ ] `Role of Estimated Glucose Disposal Rate in Staging and Death Risk of
      Cardiovascular-Kidney-Metabolic Syndrome- Insights from NHANES
      1999-2018.pdf`, PDF page 4, printed Table 1:
  - connector segments remain part of each continuous closing rule;
  - the table body does not absorb its footer.
- [ ] The same paper, PDF page 7, printed Table 2:
  - the table ends near the closing rule at y = 318.57;
  - Figures 3 and 4 are outside the canonical table body;
  - later figure/page rules cannot enlarge the table.
- [ ] `GOLD BioAge and depression- Associations with mortality among depressed
      NHANES participants (2005–2018).pdf`, PDF page 5, printed Table 3:
  - the ordinary upright identity-transform path preserves its grid, bbox,
    rules, region and footer exactly.
- [ ] Compare `extracted_tables.json`, `table_boundary_proposals.json`,
      `table_regions.json`, `body_occupancy.json`,
      `leaf_column_candidates.json`, and `paper_footnotes.json` after every
      behavior-changing step.
- [ ] Stop on any unexplained difference. Do not repair it downstream.

## 7. Corpus verification and commit

- [ ] Select one completed pre-change 28-PDF output as the comparison baseline.
- [ ] Run all 27 external PDFs plus `inst/extdata/NutritionEx.pdf` with up to six
      workers into one fresh output directory.
- [ ] Compare every physical grid, canonical bbox, row/column bound, cell bbox,
      rule proposal, table region, footer, continuation decision and processing
      status.
- [ ] Accept only changes directly supported by source positioned evidence.
- [ ] Add no test without separate permission.
- [ ] Run no pytest command unless explicitly requested.
- [ ] Confirm there is one authority for every field using repository search.
- [ ] Update design, implementation, fallback and walkthrough documents.
- [ ] Commit source and aligned documentation without `outputs/` or temporary
      review files.

## Definition of done

- [ ] Every selected table passes through one identity-or-rotation transform.
- [ ] Upright and sideways tables use the same post-transform code.
- [ ] One final `ExtractedTable` owns the canonical grid and size.
- [ ] One typed `TablePositionedEvidence` owns canonical positioned metadata.
- [ ] No geometry or rule fact has a competing metadata copy.
- [ ] Boundary proposals and table regions derive decisions without rebuilding
      raw evidence.
- [ ] The focused tables pass and the corpus has no unexplained regression.
