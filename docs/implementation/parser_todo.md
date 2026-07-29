# Parser ToDo

- [x] Complete the stored printed-table identifier string cutover through
  candidate scoring, extraction continuation metadata, header inheritance,
  canonical resolution, continuation review artifacts, table inventory, table
  contexts, variable inventory, and R inspection. Identity-bearing table-number
  fields retain complete strings such as `"1"`, `"3.1"`, and `"S1"`; page,
  row, column, extraction-order indices, and the digit-only missing-integer-
  sequence audit remain numeric.

> **Printed-table identifier cutover complete — 2026-07-28:** Focused checks
> preserve `"1"`, `"3.1"`, `"S1"`, `"4B"`, `"A.1"`, and `"B3.1.1"`
> through candidate selection, extraction, continuation evidence, resolution,
> inventories, contexts, visual links, and R selection. In
> `upload_manuscript__WEE_Bangladesh.pdf`, PDF page 81, printed Table 3.1
> remains `"3.1"` through `paper_visual:table:3.1`. In `Helicobacter pylori
> infection in the United States beyond NHANES- a scoping review of
> seroprevalence estimates by racial and ethnic groups.pdf`, PDF pages 6–7,
> printed Table 1 no longer aborts on mixed identifier types; its page-6
> fragment remains rejected by the unchanged column-schema compatibility gate.
> In `An environment-wide association study (EWAS) on type 2 diabetes
> mellitus.pdf`, PDF pages 4 and 6, printed Table 1 remains distinct from
> printed Table S1 on PDF page 9. `NutritionEx.pdf`, PDF page 5, printed Table
> 1 also preserves the string `"1"`.
>
> The fresh 28-PDF run in
> `outputs/testpapers_batch_printed_table_identity_step7_20260728` attempted all
> papers with six workers and completed 27. It produced 85 source tables, 78
> resolved tables, and 7 accepted continuation integrations. Every successful
> identity-bearing JSON field is a string or null; no dotted identifier was
> reduced, and the numeric-index and digit-only audit contracts have no type
> violations. Against the 26-paper common baseline, 810 files are byte-identical
> and 166 contain only expected identity, derived-audit, downstream-label, or
> timestamp differences; there are no unexpected JSON, physical-grid,
> normalization, semantic, ownership, bibliography, or footnote differences.
> The one accepted known failure is `periodontis2.pdf`, PDF page 12, printed
> Table 2: `Column col_idx out of range: 1`. That failure is recorded but is not
> required to close this identifier cutover.

- [ ] Diagnose the earliest extraction or table-region ownership cause of the
  rejected canonical grids in `upload_manuscript__WEE_Bangladesh.pdf`. Treat
  the shared header-structure failure as an extraction problem, not as an
  identifier-string or downstream continuation problem, and preserve the raw
  native-grid evidence while investigating it.

> **Bangladesh whole-paper table checkpoint — 2026-07-28:** The complete
> 162-page paper parsed successfully and detected 21 printed table identities
> across 28 caption or continuation fragments. Every detected fragment has an
> extraction artifact, but only 15 grids are non-empty and 13 are rejected as
> `0×0`. Complete non-empty results occur for printed Table 3.1 on PDF page 81,
> Table 3.5 on page 105, Table 3.7 on page 114, Table 3.9 on page 124, Tables
> A.1 and A.2 on page 127, Tables A.3, A.4, and A.5 on page 128, Tables B.1 and
> B.2 on page 129, Table B.3 on page 130, and Table B.4 on page 132. Printed
> Table 3.6 is partial: its base on page 107 and continuation on page 108 are
> rejected, while its continuation on page 109 produces a 2×5 grid. Printed
> Table B.5 is partial: its base on page 135 produces a 2×6 grid and its
> continuation on page 136 is rejected. No usable grid is produced for printed
> Table ES.1 on page 20, Table B3.1.1 on page 75, Table 3.2 on pages 83–84,
> Table 3.3 on pages 93–94, Table 3.4 on pages 97–98, or Table 3.8 on pages
> 119–120. All 13 rejected fragments share canonical-grid status `rejected`,
> diagnostic `header_structure_candidate_inconsistent`, and concern
> `terminal_header_physical_column_mismatch`. All seven explicit continuation
> identities are correctly preserved as strings, but all seven continuation
> decisions are rejected rather than integrated. Do not use
> `table_processing_status.json` as evidence that these grids succeeded: it
> reports all 28 fragments as `ok`, including the 13 `0×0` artifacts.

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
> at that checkpoint exposed two known blockers:
>
> - `Helicobacter pylori infection in the United States beyond NHANES- a
>   scoping review of seroprevalence estimates by racial and ethnic groups.pdf`,
>   PDF page 7, printed Table 1, aborted because continuation resolution still
>   expected an integer table number after canonical caption binding preserved
>   the printed identifier as a string. The completed printed-identifier
>   cutover above resolves this type failure; the page-6 fragment is now
>   retained as a rejected continuation under the unchanged column-schema gate.
> - `periodontis2.pdf`, PDF page 12, printed Table 2, aborts after the Step 5
>   candidate becomes an empty 0×0 canonical extraction while a later column
>   header schema still projects source column indices onto that rejected grid.
>
> **Header/body value-region precedence checkpoint — 2026-07-29:** A unique
> typed consecutive header/body proposal now suppresses detector row/rule
> geometry only for that detector call, allowing the existing content-based
> value-region transition to take precedence while retaining the proposal when
> content is unclassified. Adjacent-continuation label inheritance now consumes
> final candidates rebuilt against final canonical tables. In `periodontis2.pdf`,
> PDF page 12, printed Table 2 now parses as 28×11 with header rows 0–1 and body
> row 2 onward; PDF pages 14 and 16, printed Tables 3 and 4, use three-row
> headers, while the PDF-page-13, -15, and -17 fragments remain rejected 0×0.
> `Uses of NHANES Biomarker Data for Chemical Risk Assessment- Trends,
> Challenges, and Opportunities.pdf`, PDF page 7, printed Table 1 remains 10×2,
> and `upload_manuscript__WEE_Bangladesh.pdf`, PDF page 81, printed Table 3.1
> remains 3×5.
>
> The narrow post-boundary correction classifies a sole typed proposal's
> immediate continuation-note row outside the body before occupancy is built.
> In `Helicobacter pylori infection in the United States beyond NHANES- a
> scoping review of seroprevalence estimates by racial and ethnic groups.pdf`,
> PDF pages 5–7, printed Table 1, every fragment retains 15 physical columns and
> 15 header leaves; `(Continued from previous page)` is continuation-note row 7
> on pages 6 and 7; and one resolved continuation owns all three fragments. The
> remaining `no_variables_for_descriptive_table` status is appropriate because
> this scoping-review table is not an epidemiological Table 1.
>
> All 28 PDFs parsed successfully with six workers in
> `outputs/testpapers_batch_post_boundary_continuation_note_v2_20260729`.
> Against the immediate pre-fix 28-paper baseline, all physical dimensions and
> semantic inventories are unchanged for the other 27 PDFs; their only JSON
> differences are parse-quality report timestamps. The candidate has 94 source
> tables, 83 resolved tables, 10 integrated continuations, and processing
> statuses of 30 `ok`, 37 `rescued`, and 16 `failed`. The two fewer resolved
> tables and two fewer `ok` statuses are the intended replacement of three
> Helicobacter singletons by one integrated, non-epidemiological table.

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

- [ ] After the narrow header/body value-region precedence correction, and with
  separate parser-logic and schema approval, preserve PyMuPDF's resolved table-
  edge topology from the existing scoped `find_tables()` pass. Record exact
  detector row-boundary identities, the effective PyMuPDF table-finder settings,
  and source drawing provenance where available so later boundary ownership can
  consume the detector's already snapped/joined/intersected structure instead
  of repeating a fuzzy raw-rule-to-row y comparison. Do not remove PyMuPDF's
  internal tolerances or copy their numeric defaults into another decision
  path. Do not reverse-map resolved edges to drawings with a new tolerance: if
  exact provenance cannot be retained from construction, keep that boundary
  non-operative and fail closed. Before activation, audit the available
  `TableFinder` edge fields and source-link limitations, define the typed
  artifact change, run focused multilevel-header and textual-table checks, and
  compare all 28 corpus PDFs.

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
