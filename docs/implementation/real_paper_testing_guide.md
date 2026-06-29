# Corpus-Driven Real-Paper Testing Guide

Use this guide for the next hardening phase:

```text
Corpus-Driven Hardening Of Extraction, Normalization, And Semantics
```

The goal is to use the local real-paper corpus to find the first artifact where
structure goes wrong, fix the earliest responsible parser stage, and keep only
regressions that protect known failures or stable artifact contracts.

## Evidence Used

- `docs/implementation/parser_todo.md`
- `docs/implementation/project_completion_priorities_draft.md`
- `/Users/robert/Projects/Epiconnector/testpapers`
- `outputs/testpapers_batch_20260629_152920`
- `outputs/testpapers_batch_20260629_152920/batch_artifact_summary.json`
- `outputs/testpapers_batch_20260629_152920/batch_comparison_to_20260629_140704.json`

Latest corpus baseline:

```text
PDFs: 27
parse command failures: 0
missing core artifacts: 0
table_processing_status:
  ok: 35
  rescued: 35
  failed: 12
failure_reasons:
  non_table_layout_candidate: 8
  insufficient_table_structure_after_extraction: 2
  no_variables_for_descriptive_table: 2
```

## Review Loop

For each checklist item:

1. Run the listed papers into a fresh ignored output directory under `outputs/`.
2. Inspect artifacts in parser order:
   `extracted_tables.json`, `normalized_tables.json`,
   `column_header_schemas.json`, `resolved_tables.json`,
   `table_definitions.json`, `parsed_cell_values.json`, `parsed_tables.json`.
3. Use `table_processing_status.json` and `parse_quality_reports.json` to
   confirm the failure, not to decide the fix location by themselves.
4. Record the first bad artifact and the earliest responsible parser stage.
5. Fix the earliest stage that owns the problem.
6. Add a focused regression only when the case protects a real failure mode or
   a stable artifact contract.
7. Re-run the reviewed chunk, then re-run the full corpus after parser behavior
   changes.

All paper paths below are relative to:

```text
/Users/robert/Projects/Epiconnector/testpapers
```

## Ordered Review Checklist

### C1. Failed Table Statuses First

- [ ] **C1.1** Review papers with `non_table_layout_candidate` failures and
  decide which failures are correct rejections versus missed real tables.
  Start with the paper where this dominates the output, then move to mixed
  papers:
  1. `papers_from_laha/Helicobacter pylori infection in the United States beyond NHANES- a scoping review of seroprevalence estimates by racial and ethnic groups.pdf`
  2. `papers_from_laha/Asthma prevalence among United States population insights from NHANES data analysis.pdf`
  3. `papers_from_laha/GOLD BioAge and depression- Associations with mortality among depressed NHANES participants (2005–2018).pdf`
  4. `papers_from_laha/periodontis2.pdf`
  5. `papers_from_johnny/periodontitis.pdf`

  Initial note for the Helicobacter pylori paper: this is a scoping-review /
  meta-analysis-style paper with a difficult Table 1 layout, not an ordinary
  descriptive baseline-characteristics table. User review indicates Table 1
  spans three pages and the visible Table 1 label appears at the bottom of the
  third table page. Current artifacts in
  `outputs/testpapers_batch_20260629_152920` extract table-like grids on pages
  5, 6, and 7, plus a separate page-13 references artifact that should remain a
  non-table rejection. A reasonable first parser goal for this paper is not
  full row semantics; it is to recover the three page-level table fragments as
  table-like grids with compatible repeated headers or an equivalent canonical
  header signature.

- [ ] **C1.2** Review papers with
  `insufficient_table_structure_after_extraction` failures. Decide whether the
  visible table is missed during extraction or damaged during early
  normalization:
  1. `papers_from_laha/An environment-wide association study (EWAS) on type 2 diabetes mellitus.pdf`
  2. `papers_from_laha/mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017.pdf`

- [ ] **C1.3** Review papers with
  `no_variables_for_descriptive_table` failures. Decide whether each failed
  table is actually not a descriptive Table 1-style table, or whether row
  variable/level semantics are failing:
  1. `papers_from_laha/Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009.pdf`
  2. `papers_from_laha/Uses of NHANES Biomarker Data for Chemical Risk Assessment- Trends, Challenges, and Opportunities.pdf`

Acceptance for C1: every failed table in the current baseline is classified as
one of: correct non-table rejection, extraction failure, normalization failure,
column-header failure, row-semantics failure, unsupported table family, or
ambiguous pending review.

### C2. Rescued Structural Cases

- [ ] **C2.1** Review rotated, rule-banded, or page-text fallback cases where
  extraction rescue is doing important work. Confirm whether the rescued grid
  matches the visible table before touching semantic code:
  1. `papers_from_laha/Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009.pdf`
  2. `papers_from_laha/Ethnic Differences in the Relationship Between Insulin Sensitivity and Insulin Response.pdf`
  3. `papers_from_laha/Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf`
  4. `papers_from_laha/periodontis2.pdf`

- [ ] **C2.2** Review collapsed-grid rescues in the smaller Johnny corpus and
  related NHANES papers. These are good candidates for distinguishing robust
  structural repairs from fragile paper-specific luck:
  1. `papers_from_johnny/fld.pdf`
  2. `papers_from_johnny/gallstones.pdf`
  3. `papers_from_johnny/hypertension.pdf`
  4. `papers_from_johnny/metabolic.pdf`
  5. `papers_from_johnny/pad.pdf`
  6. `papers_from_johnny/Sarcopenia.pdf`
  7. `papers_from_laha/Association between metabolic score for insulin resistance (METS-IR) and hypertension- a cross-sectional study based on NHANES 2007–2018.pdf`
  8. `papers_from_laha/The prevalence and mortality risks of PRISm and COPD in the United States from NHANES 2007–2012.pdf`

- [ ] **C2.3** Review normalization repairs that already fire on real papers:
  split value columns, extra-wide value columns, edge-column trims, dropped
  empty columns, and glyph repair. Confirm raw evidence is preserved and the
  visible value matrix is not being over-merged:
  1. `papers_from_laha/cobaltpaper.pdf`
  2. `papers_from_laha/Association between anthropometric indices and chronic kidney disease- Insights from NHANES 2009–2018.pdf`
  3. `papers_from_laha/Lead exposure as a contributor to the Black–White racial disparity in blood pressure- evidence from NHANES 1988–1994 and 2017–2020.pdf`
  4. `papers_from_laha/Role of Estimated Glucose Disposal Rate in Staging and Death Risk of Cardiovascular-Kidney-Metabolic Syndrome- Insights from NHANES 1999-2018.pdf`

Acceptance for C2: each active rescue path has at least one reviewed real-paper
case with a recorded first bad artifact, expected artifact state after rescue,
and a decision on whether a focused regression is justified.

### C3. Continuation Semantics After Resolution

- [ ] **C3.1** Review accepted continuations and confirm that
  `resolved_tables.json`, `table_definitions.json`, and `parsed_tables.json`
  use one semantic table where the paper visually has one continued table:
  1. `papers_from_laha/Association between anthropometric indices and chronic kidney disease- Insights from NHANES 2009–2018.pdf`
  2. `papers_from_johnny/gallstones.pdf`
  3. `papers_from_laha/mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017.pdf`
  4. `papers_from_laha/Systemic inflammation markers and the prevalence of hypertension- A NHANES cross-sectional study.pdf`

- [ ] **C3.2** Review rejected continuation candidates and decide whether each
  rejection is correct. These should fail closed unless column schemas and
  source evidence prove integration:
  1. `papers_from_laha/Asthma prevalence among United States population insights from NHANES data analysis.pdf`
  2. `papers_from_laha/Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009.pdf`
  3. `papers_from_laha/periodontis2.pdf`
  4. `papers_from_laha/Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf`

Acceptance for C3: accepted and rejected continuation decisions are explained
from source evidence and `ColumnHeaderSchema`, not from plausible labels alone.

### C4. Mixed Table Families And Unsupported Tables

- [ ] **C4.1** Review estimate-result and analysis-output heavy papers without
  trying to force them into descriptive Table 1 semantics. Record whether the
  current output should become a future estimate-table artifact, an unsupported
  recognized table, or a better-routed descriptive table:
  1. `papers_from_johnny/cardiovascular.pdf`
  2. `papers_from_johnny/stroke.pdf`
  3. `papers_from_johnny/fld.pdf`
  4. `papers_from_johnny/gallstones.pdf`
  5. `papers_from_laha/Association between anthropometric indices and chronic kidney disease- Insights from NHANES 2009–2018.pdf`
  6. `papers_from_laha/cobaltpaper.pdf`

- [ ] **C4.2** Review data-presentation and unknown-family papers. The goal is
  not to implement a matrix parser yet; it is to identify which current
  failures are real parser bugs versus unsupported table families:
  1. `papers_from_laha/Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009.pdf`
  2. `papers_from_laha/periodontis2.pdf`
  3. `papers_from_laha/mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017.pdf`
  4. `papers_from_laha/An atlas of exposome–phenome associations in health and disease risk.pdf`

Acceptance for C4: mixed-family papers are classified by needed future parser
family or recognized unsupported status, without adding paper-specific routing
vocabulary.

### C5. Regression Baseline Papers

- [ ] **C5.1** Review representative mostly-successful descriptive papers after
  fixes from C1-C4. These should be used to catch regressions in ordinary Table
  1 behavior:
  1. `papers_from_laha/Systemic inflammation markers and the prevalence of hypertension- A NHANES cross-sectional study.pdf`
  2. `papers_from_laha/Ethnic Differences in the Relationship Between Insulin Sensitivity and Insulin Response.pdf`
  3. `papers_from_laha/Lead exposure as a contributor to the Black–White racial disparity in blood pressure- evidence from NHANES 1988–1994 and 2017–2020.pdf`
  4. `papers_from_johnny/hypertension.pdf`
  5. `papers_from_johnny/pad.pdf`

- [ ] **C5.2** Run the complete 27-PDF corpus after each substantial parser
  change set and compare against the latest accepted baseline. Report command
  failures, missing artifacts, table status counts, failure reasons, resolved
  continuation counts, parsed cell-value counts, and any new unsupported-family
  classifications.

Acceptance for C5: the corpus comparison explains any movement in table-level
status or artifact counts. Command success alone is not sufficient.

## Issue Note Template

Use this short note for each reviewed chunk or paper:

```text
Review ID:
PDF path:
output directory:
table_id/table_index:
current status:
expected behavior:
first bad artifact:
earliest responsible stage:
observed evidence:
fix decision:
regression decision:
```

## Scope Guardrails

- Do not add paper-specific vocabulary rules to make one paper pass.
- Do not judge success from CLI exit status alone.
- Do not debug downstream semantics before confirming extraction and
  normalization are structurally correct.
- Do not create broad unit-test expansion; add focused regressions for known
  failures or artifact contracts.
- Do not add R helpers or diagnostics before repeated review use shows what is
  needed.
