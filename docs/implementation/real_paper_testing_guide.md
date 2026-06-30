# Corpus-Driven Real-Paper Testing Guide

Use this guide for the next hardening phase:

```text
Corpus-Driven Hardening Of Extraction, Normalization, And Semantics
```

The goal is to work through real papers in a reproducible order, identify the
first artifact where structure goes wrong, and fix the earliest parser stage
that owns the problem. The current emphasis is the new structural header/body
model:

- `selective_hline_prefix`: a validated full-width horizontal-rule separator,
  using stroked rule geometry rather than filled highlighting or background
  shading
- `first_value_region_data_row`: the first stable row-label plus value-region
  anchor
- content scoring only after those structural candidates are unavailable

`normalized_tables.json` stores the selected split in
`metadata.header_detection` and stores both structural candidates in
`metadata.header_body_split_rule_comparison`.

`parse_quality_reports.json` reports
`header_body_split_rule_disagreement` when both structural candidates exist and
choose different body starts. Cases where only one candidate exists remain
inspectable in normalized metadata but are not reported as disagreements.

## Current Baseline

Latest structural baseline:

```text
outputs/testpapers_structural_header_body_20260630_recomputed
```

Corpus summary:

```text
PDFs: 27
extracted tables: 85
normalized tables: 85
parse command failures: 0
table_processing_status:
  ok: 35
  rescued: 34
  failed: 8
failure_reasons:
  non_table_layout_candidate: 5
  insufficient_table_structure_after_extraction: 2
  collapsed_grid_unrecovered: 1
resolved semantic tables: 77
integrated continuations: 7
header/body structural disagreements: 12
missing core artifacts: 0
```

All paper paths below are relative to:

```text
/Users/robert/Projects/Epiconnector/testpapers
```

## Review Loop

For each checklist item:

1. Run the listed papers into a fresh ignored output directory under `outputs/`.
2. Inspect artifacts in parser order:
   `extracted_tables.json`, `normalized_tables.json`,
   `column_header_schemas.json`, `resolved_tables.json`,
   `table_definitions.json`, `parsed_cell_values.json`, `parsed_tables.json`.
3. For header/body issues, inspect:
   `metadata.header_detection` and
   `metadata.header_body_split_rule_comparison`.
4. Use `table_processing_status.json` and `parse_quality_reports.json` to find
   failures and warnings, not as substitutes for looking at the source
   artifacts.
5. Record the first bad artifact and the earliest responsible stage.
6. Fix extraction if the visual grid, table boundary, orientation, or hline
   evidence is wrong; fix normalization if the grid is correct but the
   header/body split or row/column repair is wrong.
7. Add a focused regression only when it protects a known failure or a stable
   artifact contract.
8. Re-run the reviewed chunk, then re-run the full corpus after parser behavior
   changes.

## Ordered Review Checklist

### C1. Structural Header/Body Disagreements

- [ ] **C1.1** Review non-Eke hline-selected disagreements. Confirm that the
  selected full-width separator is the true header/body boundary and that the
  value-anchor candidate is later only because it misses sparse or categorical
  body starters:
  1. `papers_from_laha/Association between anthropometric indices and chronic kidney disease- Insights from NHANES 2009–2018.pdf`
     - `Association between anthropometric indices and chronic kidney disease- Insights from NHANES 2009–2018-p12-t0`: hline body start 3, value-anchor body start 2, selected 3
  2. `papers_from_laha/Association between metabolic score for insulin resistance (METS-IR) and hypertension- a cross-sectional study based on NHANES 2007–2018.pdf`
     - `Association between metabolic score for insulin resistance (METS-IR) and hypertension- a cross-sectional study based on NHANES 2007–2018-p6-t0`: hline body start 2, value-anchor body start 3, selected 2

  METS-IR is currently the expected pattern: the header is bounded by full-width
  hlines, row 2 is the first body row, and `ColumnHeaderSchema` recovers
  `Model 1`, `Model 2`, and `Model 3` as grouped headers.

- [ ] **C1.2** Review value-anchor-selected disagreements. These are the cases
  where the first value-region anchor currently selects a later body start than
  an earlier hline candidate, or where the hline candidate is only a weak first
  selective boundary:
  1. **GOLD BioAge and depression: Associations with mortality among depressed NHANES participants (2005–2018)**
     - PDF path: `papers_from_laha/GOLD BioAge and depression- Associations with mortality among depressed NHANES participants (2005–2018).pdf`
     - `GOLD BioAge and depression- Associations with mortality among depressed NHANES participants (2005–2018)-p4-t1`: hline body start 2, value-anchor body start 4, selected 4 in the recomputed baseline; current parser should select body start 2 after accepting label-only parent body starters.
  2. [x] **Role of Estimated Glucose Disposal Rate in Staging and Death Risk of Cardiovascular-Kidney-Metabolic Syndrome: Insights from NHANES 1999-2018**
     - PDF path: `papers_from_laha/Role of Estimated Glucose Disposal Rate in Staging and Death Risk of Cardiovascular-Kidney-Metabolic Syndrome- Insights from NHANES 1999-2018.pdf`
     - `Role of Estimated Glucose Disposal Rate in Staging and Death Risk of Cardiovascular-Kidney-Metabolic Syndrome- Insights from NHANES 1999-2018-p4-t0`: hline body start 1, value-anchor body start 3, selected 3
     - Reviewed on 2026-06-30: selected body start 3 is acceptable. Row 0 is preamble/title, rows 1-2 are column headers, and row 3 (`Age, years`) starts the data body. The `(N = ...)` row is a column-header row, not a data row.
  3. `papers_from_johnny/Sarcopenia.pdf`
     - `Sarcopenia-p7-t0` and `Sarcopenia-p8-t0`: hline body start 1, value-anchor body start 2, selected 2
  4. `papers_from_laha/Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf`
     - `Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis-p2-t0`: hline body start 1, value-anchor body start 4, selected 4
     - `Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis-p5-t0`: hline body start 2, value-anchor body start 0, selected 0
  5. `papers_from_johnny/cardiovascular.pdf`
     - `cardiovascular-p5-t0`: hline body start 4, value-anchor body start 7, selected 7

  For `cardiovascular-p5-t0`, the selected body start 7 is currently expected:
  the hline at row 4 is internal to the header band, separating upper spanning
  headers from wrapped leaf headers. `ColumnHeaderSchema` should use rows 4-6
  as leaf labels and rows 0-3 as training/testing cohort groups.

- [ ] **C1.3** Review Eke disagreement tables as data/result-table examples.
  Do not force these into ordinary descriptive Table 1 semantics unless the
  visible table supports that:
  1. `papers_from_laha/Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009.pdf`
     - `Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009-p4-t0`: hline body start 2, value-anchor body start 8, selected 2
     - `Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009-p5-t0`: hline body start 3, value-anchor body start 10, selected 10
     - `Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009-p7-t0`: hline body start 3, value-anchor body start 5, selected 5

Acceptance for C1: each disagreement is classified as correct hline split,
correct value-anchor split, extraction hline defect, normalization candidate
defect, or unsupported/misrouted table family.

### C2. Failed Table Statuses

- [ ] **C2.1** Review `insufficient_table_structure_after_extraction`
  failures. Decide whether extraction missed the visible table structure or
  whether the page fragment is correctly rejected:
  1. `papers_from_laha/An environment-wide association study (EWAS) on type 2 diabetes mellitus.pdf`
     - `An environment-wide association study (EWAS) on type 2 diabetes mellitus-p6-t0`
  2. `papers_from_laha/mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017.pdf`
     - `mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017-p3-t0`

- [ ] **C2.2** Review the rotated collapsed-grid failure:
  1. `papers_from_laha/Ethnic Differences in the Relationship Between Insulin Sensitivity and Insulin Response.pdf`
     - `Ethnic Differences in the Relationship Between Insulin Sensitivity and Insulin Response-p5-t0`, `collapsed_grid_unrecovered`

  Current expectation: fail closed is better than recovering an implausible
  50-plus-column rotated grid. The next improvement should recover the true
  visible grid, not loosen the guardrail.

- [ ] **C2.3** Review `non_table_layout_candidate` failures and decide which
  are correct non-table rejections versus missed real tables:
  1. `papers_from_laha/Asthma prevalence among United States population insights from NHANES data analysis.pdf`
     - `Asthma prevalence among United States population insights from NHANES data analysis-p6-t0`
  2. `papers_from_laha/GOLD BioAge and depression- Associations with mortality among depressed NHANES participants (2005–2018).pdf`
     - `GOLD BioAge and depression- Associations with mortality among depressed NHANES participants (2005–2018)-p1-t0`
  3. `papers_from_laha/Helicobacter pylori infection in the United States beyond NHANES- a scoping review of seroprevalence estimates by racial and ethnic groups.pdf`
     - resolved continuation over pages 5, 6, and 7
  4. `papers_from_laha/periodontis2.pdf`
     - `periodontis2-p6-t0`
  5. `papers_from_johnny/periodontitis.pdf`
     - `periodontitis-p11-t0`

Acceptance for C2: every failed table is classified as correct non-table
rejection, extraction failure, normalization failure, unsupported table family,
or ambiguous pending review.

### C3. Extraction Rescue And Hline Quality

- [ ] **C3.1** Review explicit hline and preamble behavior in papers with
  title/preamble rows above true column headers. Confirm real stroked hlines are
  used and filled row highlighting is ignored:
  1. `papers_from_johnny/fld.pdf`
  2. `papers_from_johnny/pad.pdf`
  3. `papers_from_laha/cobaltpaper.pdf`
  4. `papers_from_johnny/cardiovascular.pdf`

- [ ] **C3.2** Review rescued or fallback grids where extraction is doing
  important structural work before normalization:
  1. `papers_from_laha/Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009.pdf`
  2. `papers_from_laha/periodontis2.pdf`
  3. `papers_from_laha/Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf`
  4. `papers_from_johnny/gallstones.pdf`
  5. `papers_from_johnny/hypertension.pdf`
  6. `papers_from_johnny/metabolic.pdf`

Acceptance for C3: each active rescue path has at least one reviewed real-paper
case with the expected grid, hline metadata, and first bad artifact recorded.

### C4. Continuations After Resolved Tables

- [ ] **C4.1** Review accepted continuations and confirm one visual continued
  table becomes one semantic resolved table:
  1. `papers_from_laha/Association between anthropometric indices and chronic kidney disease- Insights from NHANES 2009–2018.pdf`
  2. `papers_from_laha/Asthma prevalence among United States population insights from NHANES data analysis.pdf`
  3. `papers_from_laha/Helicobacter pylori infection in the United States beyond NHANES- a scoping review of seroprevalence estimates by racial and ethnic groups.pdf`
  4. `papers_from_laha/Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009.pdf`
  5. `papers_from_laha/Systemic inflammation markers and the prevalence of hypertension- A NHANES cross-sectional study.pdf`
  6. `papers_from_johnny/gallstones.pdf`
  7. `papers_from_laha/mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017.pdf`

- [ ] **C4.2** Review accepted but difficult continuations. Confirm that
  integration is structurally justified and that any remaining `failed` status
  belongs to later semantics, not to continuation resolution:
  1. `papers_from_laha/Helicobacter pylori infection in the United States beyond NHANES- a scoping review of seroprevalence estimates by racial and ethnic groups.pdf`
     - integrated pages 5, 6, and 7, but semantic status remains `non_table_layout_candidate`
  2. `papers_from_laha/Asthma prevalence among United States population insights from NHANES data analysis.pdf`
     - integrated pages 4 and 5; page 6 remains a separate `non_table_layout_candidate`
  3. `papers_from_laha/Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009.pdf`
     - integrated pages 6 and 7; treat as data/result-table review before forcing descriptive semantics
  4. `papers_from_laha/periodontis2.pdf`
     - no accepted continuation in the current baseline; page 6 remains `non_table_layout_candidate`

Acceptance for C4: continuation decisions are explainable from
`resolved_tables.json`, source table IDs, row provenance, and
`ColumnHeaderSchema`.

### C5. Mixed Table Families And Regression Baseline

- [ ] **C5.1** Review estimate-result and data-presentation tables without
  forcing them into descriptive Table 1 semantics:
  1. `papers_from_johnny/cardiovascular.pdf`
  2. `papers_from_johnny/stroke.pdf`
  3. `papers_from_laha/cobaltpaper.pdf`
  4. `papers_from_laha/Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009.pdf`
  5. `papers_from_laha/An atlas of exposome–phenome associations in health and disease risk.pdf`

- [ ] **C5.2** Re-run representative mostly-successful descriptive papers after
  fixes from C1-C5.1:
  1. `papers_from_laha/Systemic inflammation markers and the prevalence of hypertension- A NHANES cross-sectional study.pdf`
  2. `papers_from_laha/Lead exposure as a contributor to the Black–White racial disparity in blood pressure- evidence from NHANES 1988–1994 and 2017–2020.pdf`
  3. `papers_from_johnny/hypertension.pdf`
  4. `papers_from_johnny/pad.pdf`
  5. `papers_from_johnny/fld.pdf`

- [ ] **C5.3** Run the complete 27-PDF corpus after each substantial parser
  change set and compare against the latest accepted baseline. Report command
  failures, missing artifacts, table status counts, failure reasons, resolved
  continuation counts, parsed cell-value counts, shape/status changes, and
  header/body split disagreements.

Acceptance for C5: corpus comparison explains any movement in table-level
status, artifact counts, or structural split disagreements. Command success
alone is not sufficient.

## Issue Note Template

Use this short note for each reviewed chunk or paper:

```text
Review ID:
PDF path:
output directory:
table_id/table_index:
current status:
selected header/body source:
hline candidate:
value-anchor candidate:
rules agree:
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
- Do not treat row highlighting or background fills as horizontal-rule
  separators.
- Do not force data/result tables into descriptive Table 1 semantics.
- Do not create broad unit-test expansion; add focused regressions for known
  failures or artifact contracts.
- Do not add R helpers before repeated review use shows what is needed.
