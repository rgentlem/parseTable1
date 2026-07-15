# Pre-Phase J: Extraction Integrity And One Header Path

Purpose: correct the known duplicate extraction, establish a clean corpus
baseline, and return to Phase J with one geometry-driven header builder.

## 0. Confirmed Audit

- [x] Trace the current path from positioned PDF evidence through extraction,
      `TableRegion`, `HeaderStructureCandidate`, and `ColumnHeaderSchema`.
- [x] Confirm the candidate copies header/body rows from `TableRegion`; their
      92/92 agreement is not independent validation.
- [x] Confirm `ColumnHeaderSchema` independently reconstructs headers after the
      geometry candidate and normally ignores that candidate.
- [x] Confirm the retained corpus contains 92 extracted objects, not 92 proven
      unique physical tables.
- [x] Identify the duplicate: `Asthma prevalence among United States population
      insights from NHANES data analysis.pdf`, PDF page 5. Two overlapping
      objects contain the same printed Table 2 body; one is misbound to the
      printed Table 1 caption.
- [x] Obtain explicit approval before changing extraction logic.

## 1. Correct The Duplicate At Extraction

- [x] Fix caption-to-grid ownership in the existing PyMuPDF extraction path.
- [x] Require one physical grid to have at most one caption and one extracted
      object.
- [x] Use caption placement, rule enclosure, and bbox/grid overlap only; add no
      paper-specific text rule or downstream cleanup.
- [x] Align the current `(page_num, table_index)` selection key with physical
      overlap so it cannot retain the same grid twice.
- [x] Preserve the real Table 1 continuation and the real printed Table 2 on
      PDF page 5; remove only the misbound duplicate.
- [x] Remove or align any competing caption-binding or deduplication path.

Focused checkpoint result: the paper changes from five to four extracted
objects; only the misbound `...-p5-t1` object is removed. All four retained
physical grids are exactly equal in shape, cell text, and bbox. The real PDF
pages 4–5 Table 1 fragments now resolve together, and the single printed Table
2 remains separate, reducing five resolved objects to three. The focused
output was superseded by the full Step 2 corpus baseline below.

## 2. Re-baseline The Corpus

- [x] Parse the asthma PDF first and inspect captions, bboxes, grids, regions,
      normalized tables, and resolved tables.
- [x] Parse all 28 PDFs with at most six parallel workers into a fresh ignored
      output directory.
- [x] Compare all retained physical grids against the Phase I baseline; require
      exact equality except for removal of the duplicate object.
- [x] Report extractions, unique retained grids, continuation merges, and
      resolved tables separately.
- [x] Establish the new output as the Phase J baseline.
- [x] Do not add tests or run pytest without separate permission.

Full-corpus checkpoint:
`outputs/testpapers_batch_pre_phase_j_step2_final_20260715`. The 28 PDFs
produce 91 extracted objects representing 91 unique retained physical grids,
then 82 resolved tables after nine accepted two-fragment continuation merges.
All 82 table-processing results succeed: 17 are `ok`, 65 are `rescued`, and
none fail.

The 91 table IDs retained from the Phase I baseline are exactly equal in page,
shape, cell text and bbox, row bounds, column boundaries, rules, and physical
cell geometry. There are no added IDs or other physical changes. The only
removed ID is the known misbound duplicate `...-p5-t1` on PDF page 5 of
`Asthma prevalence among United States population insights from NHANES data
analysis.pdf`; the retained corpus has no remaining same-page, same-grid pair
with at least 80% directional bbox overlap.

## 3. Reset The Phase J Plan

- [x] Refresh the Phase J audit against the 91-grid baseline.
- [x] Replace the old abbreviated per-table patch ledger with general
      geometry-only requirements.
- [x] Specify `TableRegion` as the sole header/body ownership decision, using
      direct rule, typography, coverage, and adjacency evidence.
- [x] Explicitly prohibit candidate-to-region feedback and treating copied row
      indices as independent validation.
- [x] Specify one candidate construction for leaves, wrapped labels, and groups
      from positioned geometry and canonical bands.
- [x] Require ambiguous attachments to remain unresolved rather than adding
      table-specific refinements.
- [x] Specify `ColumnHeaderSchema` as a direct candidate projection.
- [x] Name the older schema reconstruction, continuation override, and
      resolved-schema rebuild fallback that must be removed during Phase J.

Completion gate met: the corpus has a clean extraction baseline and the
revised Phase J document describes one region decision, one header
construction, and one schema projection. This reset changed documentation
only; the Phase J parser-logic gates remain open pending explicit approval.
