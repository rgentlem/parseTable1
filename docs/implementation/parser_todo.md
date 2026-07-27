# Parser ToDo

- [ ] Make table-candidate scoping consume the existing canonical block/prose
  boundary so later prose blocks and later page rules cannot expand a table
  candidate. Page furniture must remain only an early evidence mask, not the
  authority for a table's lower boundary. The current demonstrated failure is
  `Association between anthropometric indices and chronic kidney disease-
  Insights from NHANES 2009–2018.pdf`, PDF page 8, printed Table 1: prose is
  detected, but candidate construction ignores that ownership and extends the
  continuation fragment through the page.

> **Current checkpoint — 2026-07-25:** Typed table-row ownership and
> continuation-chain repair is implemented and validated across all 28 PDFs in
> `outputs/testpapers_batch_canonical_entity_step5_final_20260725`. The corpus
> has 76 canonical table entities owning 88 physical table references.

This is the persistent implementation ToDo list for parser work. Agents should check it before changing extraction, normalization, row/column semantics, table routing, value parsing, diagnostics, or R inspection helpers. Update it when a task is completed, reprioritized, split, or superseded.

The evidence-gated page-number substitution completed on 2026-07-27. All 28
corpus PDFs parsed successfully in
`outputs/testpapers_batch_page_number_substitution_20260727`; no accepted mask
was lost, and extracted table IDs, pages, dimensions, cell text, and cell bboxes
were unchanged. Ordinary observation keys now remain intact unless recurrent
positioned evidence accepts one constant-offset numeric-slot template.

Paper page scope is now the sole paper-length authority. The 28-PDF checkpoint
in `outputs/testpapers_batch_paper_scope_20260727` detects paper length 10 in
`Science-Advanaced-Planetary Health Diet and risk of mortality and chronic
diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf`, retains
its appended PDF page 11 only in raw positioned evidence, and prevents that
page from entering interpreted or extracted artifacts. All 14 detected
full-length papers and 13 unknown-scope papers retain every physical page.
Ninety-one of 92 physical tables exactly match the preceding grid and cell
baseline. On PDF page 3, printed Table 1 of that paper loses one empty row when
its recurrent journal header, footer, and `3 of 10` counter are correctly
masked over the included page set; all real table rows and cells remain.

Keep detailed implementation notes and epidemiology-table reasoning here or in linked implementation documents. Keep high-level design docs focused on stable pipeline shape, schemas, persisted artifact contracts, and durable architecture decisions.

## Current Priorities

- [ ] Complete the remaining canonical positioned-evidence unification described in
  `docs/implementation/canonical_orientation_unification_checklist.md` before
  another footer-specific correction. The shared identity-or-sideways affine
  path and required typed `ExtractedTable.positioned_evidence` authority are now
  implemented, every consumer has migrated, and the old metadata key is gone.
  Step 3 also separates role-free physical-column bands from preliminary
  terminal header nodes: geometry artifacts no longer assign stub/value roles,
  header nodes record `physical_col_idx`, and the typed canonical physical-grid
  destination is explicit but remains unpopulated. The corrected Step 4 records
  that adequate body-occupancy bands are authoritative. Implement only Step 5:
  remove the positioned-grid winner, materialize the final physical columns
  from occupancy bands, populate the typed final axes, retain the duplicate
  preliminary/final artifact cycle, run the focused checks, and stop. Do not
  add text-row handling or semantic header-role work. Each remaining logic step
  requires specific parser-logic approval.

- [ ] After Step 5 is complete and with separate approval, remove the three
  existing `±1.0` layout windows in
  `finalize_canonical_extracted_tables()`: row retention, header-cell
  containment within physical bands, and body-word row assignment. Do not
  include this tolerance work in the occupancy-authority implementation.

- [ ] After the occupancy-authority checkpoint, audit row-index and annotation
  dependencies across the preliminary and final artifact builds without
  changing behavior. Identify every place where caption/empty-row removal
  shifts row indices and determine what must remain aligned before the duplicate
  cycle can be removed.

- [ ] After that audit and separate approval, remove the duplicate
  preliminary/final geometry-artifact cycle. Build each prerequisite artifact
  once, then build header candidates once against the final occupancy-defined
  physical axis. Preserve row ownership and raw provenance; do not add a
  compatibility path, fallback, or text-row classifier.

- [ ] After the one-pass artifact cutover, rerun the focused real-paper checks
  for `periodontis2.pdf`, PDF page 18, printed Table 5; `Role of Estimated
  Glucose Disposal Rate in Staging and Death Risk of
  Cardiovascular-Kidney-Metabolic Syndrome- Insights from NHANES
  1999-2018.pdf`, PDF page 4, printed Table 1; and `GOLD BioAge and depression-
  Associations with mortality among depressed NHANES participants
  (2005–2018).pdf`, PDF page 5, printed Table 3. If those pass, run all 27
  external PDFs plus `inst/extdata/NutritionEx.pdf` with no more than six
  workers and accept only source-evidence-supported differences.

- [ ] Resolve the remaining canonical prose-versus-table-footer ownership
  boundary after positioned-evidence unification. The primary failure is
  `cardiovascular.pdf`, PDF page 5, printed Table 2: source line
  `page-5-line-2`, `Performance of models`, is accepted as an external footer
  even though it begins a body-prose block. Integrate the remaining prose-first
  partition and unified-footer work into one owner at `build_table_region()`,
  including a non-operative audit of internal footer rows against settled body
  occupancy before any behavior change. Preserve genuine notes in `GOLD BioAge
  and depression- Associations with mortality among depressed NHANES
  participants (2005–2018).pdf`, PDF pages 4–6, and the established false-footer
  rejections in `fld.pdf`, PDF page 6, printed Table 2, and `Journal of
  Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults
  in the United States  NHANES 2009.pdf`, PDF page 10, printed Table 5. Add no
  downstream cleanup, competing ownership path, or numeric layout tolerance.
  This item requires a separately approved ownership design.

- [ ] Review the seven current
  `long_bibliography_entry_possible_collapse` entries across four papers and
  distinguish genuine long references from missed entry starts or incorrect
  continuation ownership before changing segmentation: reference 23 in `Ethnic
  Differences in the Relationship Between Insulin Sensitivity and Insulin
  Response.pdf`; references 34, 45, 54, and 62 in `Helicobacter pylori infection
  in the United States beyond NHANES- a scoping review of seroprevalence
  estimates by racial and ethnic groups.pdf`; reference 31 in `Role of Estimated
  Glucose Disposal Rate in Staging and Death Risk of
  Cardiovascular-Kidney-Metabolic Syndrome- Insights from NHANES 1999-2018.pdf`;
  and reference 33 in `Systemic inflammation markers and the prevalence of
  hypertension- A NHANES cross-sectional study.pdf`. Any approved bibliography
  change must retain reference 41 in `NutritionEx.pdf`, reference 39 in
  `fld.pdf`, and all four source lines of reference 19 in `periodontitis.pdf`,
  PDF page 12, while preserving owned-block masks and table artifacts.

- [ ] Review or explicitly accept the deferred corpus gaps in
  `docs/implementation/corpus_artifact_uncertainties_20260715.md`. Promote only
  evidence-backed, currently reproducible defects into concrete ToDo entries;
  retain accepted limitations as documented uncertainties rather than treating
  every diagnostic as a parser defect.

## Notes

- Do not mark a task complete just because one narrow case has been patched. Mark it complete only when the repo has a general implementation and tests for the intended scope.
- If a task expands into multiple concrete implementation steps, add subitems or link to a dedicated implementation note.
