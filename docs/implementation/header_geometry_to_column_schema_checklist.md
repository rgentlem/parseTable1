# Header Geometry to Column Schema - Closed Checklist

Status: **complete**. This is a concise closure record, not an active
implementation tracker.

Phase J established one geometry-driven header path. Detailed current table
geometry requirements are maintained in
`docs/implementation/table_geometry_reconstruction_checklist.md`. The later
orientation cleanup is tracked separately in
`docs/implementation/canonical_orientation_unification_checklist.md`; it does
not reopen header reconstruction.

## Final Contract

```text
selected physical grid
  -> TableRegion decides header/body ownership once
  -> body occupancy establishes canonical leaf columns
  -> HeaderStructureCandidate builds leaves and groups once
  -> NormalizedTable preserves the selected physical grid and region
  -> ColumnHeaderSchema directly projects the candidate
  -> body candidates and resolved tables
```

`HeaderStructureCandidate` does not revise `TableRegion`.
`NormalizedTable` does not rerun header detection or alter the physical grid.
`ColumnHeaderSchema` does not reconstruct, repair, respan, or replace the
candidate.

## Completed Work

- [x] Decide `TableRegion` once from positioned rules, row bounds, typography,
      canonical-column coverage, and adjacency.
- [x] Keep candidate construction downstream of the final region decision.
- [x] Build exactly one candidate leaf for every canonical physical column.
- [x] Treat same-band physical header rows as wrapped leaf text unless direct
      rule geometry separates hierarchy levels.
- [x] Create groups only over contiguous lower leaves supported by positioned
      coverage.
- [x] Preserve source evidence, raw text, marker links, rule references,
      canonical bounds, and continuation inheritance provenance.
- [x] Normalize without splitting, merging, moving, pruning, or synthesizing
      physical cells.
- [x] Project candidate leaves, groups, relationships, evidence, and marker
      targets directly into `ColumnHeaderSchema`.
- [x] Remove independent schema header inference, group reconstruction,
      continuation overrides, and the resolved-table rebuild fallback.
- [x] Attach body values and labels only after the projected leaf axis is
      settled.
- [x] Keep alignment evidence supporting and non-operative.
- [x] Validate the result on the complete 28-PDF real-paper corpus.

## Current Retained Baseline

The current post-geometry corpus is:

```text
outputs/testpapers_batch_phase_k_step5_guarded_final_20260715
```

It contains:

- 28 source PDFs;
- 91 physical table fragments;
- 78 resolved logical tables;
- 13 accepted continuation integrations.

The difference between 91 fragments and 78 resolved tables is exactly the 13
accepted integrations; no table objects are missing from that accounting.

The schema remains a direct projection of the accepted header candidate for
each physical fragment. Physical rows, columns, cells, occupancy, canonical
selection, continuation identity, and inherited headers are owned by their
earlier stages and are not revised by schema construction.

## Accepted Focused Corrections

- [x] `mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older
      Adults- NHANES 2007-2017.pdf`, PDF page 3, printed Table 1: direct
      rule-bounded typography evidence assigns physical row 0 to the header.
- [x] `Science-Advanaced-Planetary Health Diet and risk of mortality and
      chronic diseases- Results from US NHANES, UK Biobank, and a
      meta-analysis.pdf`, PDF pages 2-3, printed Table 1: direct candidate
      projection permits the accepted continuation integration.
- [x] `gallstones.pdf`, PDF pages 5-6, printed Table 1: direct candidate
      projection permits the accepted continuation integration.
- [x] `mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older
      Adults- NHANES 2007-2017.pdf`, PDF pages 5-6, printed Table 2: direct
      candidate projection permits the accepted continuation integration.
- [x] `periodontis2.pdf`, PDF pages 10-11, printed Table 1: the shared
      positioned-document pass retains clipped off-page source text, allowing
      the ordinary physical grid and matching projected header paths to be
      recovered without leaf inheritance or schema repair.

## Closed Paths

The following paths must not be reintroduced:

- independent header-row inference in normalization or schema construction;
- blank-span or same-row schema grouping overrides;
- fragment movement, body-row promotion, or body-anchor header repair;
- schema-only group creation, deletion, or respanning;
- continuation-only header replacement after candidate construction;
- resolved-table schema rebuilding when a source schema is missing;
- paper-specific vocabulary rules for header structure.

Any future header discrepancy must be traced to the earliest direct geometric
evidence or left explicit and unresolved. It must not create a second header
builder.
