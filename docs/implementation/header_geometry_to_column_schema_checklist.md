# Header Geometry To Column Schema Cutover

This checklist completes one geometry-first header path:

```text
positioned evidence -> provisional body band -> occupancy/canonical leaves
-> canonical ExtractedTable -> HeaderStructureCandidate -> final TableRegion
-> validated ColumnHeaderSchema -> body/value candidates
```

Physical leaves are authoritative. Header logic may label and group them but
must not create, remove, split, move, or repair columns.

Current continuation-header checkpoint:
`outputs/testpapers_batch_header_inheritance_recovered_20260714`.

Physical comparison baseline:
`outputs/testpapers_batch_canonical_axis_validation_final_20260714`.

## 1. Audit The Existing Two Paths

- [ ] Compare every finalized candidate with its schema across all 92 tables.
- [ ] Compare leaves, labels, groups, relationships, row ownership, header
      paths, unresolved fragments, and evidence references.
- [ ] Classify each difference at its first structural cause: boundary, leaf
      axis, wrapping, grouping, competing reconstruction, or ambiguity.
- [ ] Report each difference by exact PDF filename, page, printed table number,
      and table ID.
- [ ] Keep the audit read-only; do not add another inference path.

## 2. Complete `HeaderStructureCandidate`

- [ ] Require one candidate leaf for every canonical column, including the stub.
- [ ] Preserve each fragment's raw text, source IDs, font, row, bbox, covered
      leaves, rule references, and marker IDs.
- [ ] Record fragment attachment as accepted, ambiguous, or unresolved.
- [ ] Join wrapped fragments only when they align to the same node without an
      intervening rule.
- [ ] Create groups only from geometric/rule coverage of contiguous lower nodes;
      allow direct leaves beside groups and recursive groups.
- [ ] Reject crossing spans, missing children, cycles, and unresolved references.
- [ ] Preserve local, effective, and inherited labels with provenance.

## 3. Finalize Region Ownership In Order

- [ ] Use a provisional boundary only to select body lines for occupancy.
- [ ] Build the final candidate after canonical grid selection.
- [ ] Build or validate final `TableRegion` ownership from the canonical grid,
      candidate, rules, occupancy, and caption/footer ownership.
- [ ] Preserve competing boundary evidence.
- [ ] Fail closed when final ownership conflicts with settled geometry.

## 4. Make `ColumnHeaderSchema` A Projection

- [ ] Use the finalized candidate as structural input for every table.
- [ ] Project leaves, groups, relationships, and header paths without changing
      column indices.
- [ ] Retain stable local and inherited evidence references.
- [ ] Normalize semantic names only after labels and provenance are fixed.
- [ ] Emit structured incomplete/rejected diagnostics; do not reconstruct.
- [ ] Replace the continuation-only schema branch with this ordinary path.

## 5. Remove Competing Reconstruction

- [ ] Remove `_infer_header_rows_from_geometry()` and
      `_infer_header_rows_from_grid()` from the canonical path.
- [ ] Remove independent grouping by `_header_runs_for_groups()` and
      `_repeated_leaf_header_blocks()`.
- [ ] Remove competing blank-span, fragment-movement, and continuation-schema
      enrichment.
- [ ] Remove the continuation-specific override after the general projection.
- [ ] Update the fallback inventory and design walkthrough as paths are removed.

## 6. Preserve Continuation Gates

- [x] Establish adjacent identity before inheritance using explicit identity or
      the existing uncaptioned-adjacent rule plus matching repeated groups.
- [x] Require complete unique leaf alignment and inherit only blank labels.
- [x] Record parent table, leaf, page, and structural evidence while preserving
      the existing resolver identity path.
- [ ] Carry inherited provenance through the general schema projection.
- [x] Reject inheritance when non-empty local text conflicts.

## 7. Use Stable Leaves Downstream

- [ ] Build body elements and row-label candidates after final region/schema.
- [ ] Give each element source-cell, physical-line, canonical-leaf, and
      header-path references.
- [ ] Represent wrapping through relationships, not grid mutation.
- [ ] Expose `raw_text`, geometry-supported marker-free `base_text`, and marker
      IDs; retain uncertain glyphs with diagnostics.

## 8. Verify The Cutover

- [x] Run the focused rotated continuation example and verify its artifacts.
- [ ] Run focused flat, wrapped, grouped, mixed, rotated, continued, and
      ambiguous real-paper examples.
- [x] Run all 27 external PDFs plus `inst/extdata/NutritionEx.pdf` with bounded
      workers.
- [x] Require unchanged physical IDs, shapes, cells, bboxes, coordinates,
      occupancy, and leaf candidates unless separately approved extraction
      evidence requires a change.
- [x] Enumerate every changed candidate, schema, resolved table, definition,
      parsed table, status, and R inspection input.
- [ ] Confirm every schema change was predicted by the initial audit and no
      fallback repairs ambiguity.
- [ ] Obtain permission before adding tests; update retained outputs and docs.

## Complete When

- [ ] Final region ownership uses the selected grid and candidate.
- [ ] Every schema is a validated candidate projection.
- [ ] No generic downstream header reconstruction remains.
- [ ] One provenance-bearing leaf axis is used through parsed values and the
      complete 28-PDF corpus shows only intended changes.
