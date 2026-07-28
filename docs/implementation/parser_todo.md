# Parser ToDo

- [x] Validated the completed printed-table identifier preservation cutover
  through the deterministic mention-to-reference chain and the ordinary Table
  1 and supplementary Table S1 references in
  `An environment-wide association study (EWAS) on type 2 diabetes mellitus.pdf`.

> **Printed-table identifier implementation checkpoint — 2026-07-28:** The
> mention and visual-reference grammars now preserve one complete alphanumeric,
> dot-separated identifier containing at least one digit. Caption binding keeps
> the caption region's identifier string instead of replacing it with a reduced
> candidate value. Existing `PaperDocument` table-caption ownership and schemas
> are unchanged, and visual construction continues to consume that caption
> component. Focused boundary checks pass for `1`, `S1`, `4A`, `4B`, `3.1`,
> `A.1`, and `B3.1.1`. The known non-extracting
> `upload_manuscript__WEE_Bangladesh.pdf` case is not an acceptance input for
> this identifier change. Final validation completed on
> 2026-07-28: the deterministic chain preserves `Table 3.1` through
> `paper_visual:table:3.1` and its resolved prose reference, and the fresh
> focused parse in `outputs/printed_table_identity_step6_ewas_20260728`
> preserves ordinary Table 1 on PDF pages 4 and 6 and supplementary Table S1
> on PDF pages 4 and 9.

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

> **Page-furniture rule-mask checkpoint — 2026-07-27:** Candidate construction
> and typed table-local positioned evidence now use one exact-containment mask
> for an accepted furniture rectangle and its constituent drawing segments.
> In `Association between anthropometric indices and chronic kidney disease-
> Insights from NHANES 2009–2018.pdf`, PDF page 8, printed Table 1, the raw
> artifact retains four ordinary and one stroked representations of the bottom
> furniture rectangle, both consumers exclude them, and the synthetic rule span
> at `y=744.2498168945312` is gone. All 28 corpus PDFs parsed successfully in
> `outputs/testpapers_batch_page_furniture_rule_mask_20260727`. Twenty-six papers
> are semantically unchanged. The intended paper recovers its PDF-page-8 Table 1
> continuation and PDF-page-12 Table 4, corrects PDF-page-10 Table 2, and removes
> the DOI-only row from PDF-page-15 Table 6. In `Systemic inflammation markers
> and the prevalence of hypertension- A NHANES cross-sectional study.pdf`, PDF
> pages 5–6, printed Table 1, grids and cells are unchanged; removal metadata
> changes from three segments and cluster IDs `[1, 2, 3]` to four segments and
> IDs `[1, 2]` because the singular matcher attributes overlapping exact and
> containing regions to the first match. Preserving every applicable cluster ID
> remains a metadata-only follow-up. This correction removes the duplicated-rule
> trigger; it does not replace the pending canonical prose-boundary ownership
> work above.

> **Internal-footer row-atomicity checkpoint — 2026-07-28:** `TableRegion` now
> rejects an internal footer-row claim when the completed backward footer walk
> does not own every classified positioned line group mapped to that physical
> row. The focused reconstruction of `Uses of NHANES Biomarker Data for Chemical
> Risk Assessment- Trends, Challenges, and Opportunities.pdf`, PDF page 7,
> printed Table 1, retains physical rows 0–9 and rejects the former partial claim
> on wrapped row 9. All 28 corpus PDFs parsed successfully in
> `outputs/testpapers_batch_footer_row_atomicity_20260728`. All current semantic
> artifacts match `outputs/testpapers_batch_page_furniture_rule_mask_20260727`;
> only the already approved non-operative drawing collections in
> `paper_positioned_document.json` and report timestamps differ. Because native
> proposal promotion remains non-operative at Step 4, the corpus establishes no
> regression while the focused reconstruction exercises the corrected ownership
> decision.

> **Scoped native-grid Step 5 checkpoint — 2026-07-28:** Complete unique native
> proposals now cut over at the existing candidate decision point while
> ambiguous proposals fail closed and the ruled path retains scopes without an
> accepted proposal. `TableRegion` selects exactly one typed consecutive
> header/body boundary without changing later header interpretation. In
> `Uses of NHANES Biomarker Data for Chemical Risk Assessment- Trends,
> Challenges, and Opportunities.pdf`, PDF page 7, printed Table 1, the normal
> CLI emits one 10×2 table with row 0 as its two-leaf header and rows 1–9 as
> body. In `upload_manuscript__WEE_Bangladesh.pdf`, PDF page 81, printed Table
> 3.1, it emits one 3×5 table with row 0 as its five-leaf header and visual ID
> `paper_visual:table:3.1`. The fresh 28-PDF corpus run in
> `outputs/testpapers_batch_native_table_step5_20260728` completed 26 papers and
> exposed two known blockers accepted for this checkpoint commit:
>
> - `Helicobacter pylori infection in the United States beyond NHANES- a
>   scoping review of seroprevalence estimates by racial and ethnic groups.pdf`,
>   PDF page 7, printed Table 1, aborts because continuation resolution still
>   expects an integer table number after canonical caption binding has
>   preserved the printed identifier as a string.
> - `periodontis2.pdf`, PDF page 12, printed Table 2, aborts after the Step 5
>   candidate becomes an empty 0×0 canonical extraction while a later column
>   header schema still projects source column indices onto that rejected grid.
>
> These failures remain explicit next work. They are not treated as a passing
> corpus result.

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
