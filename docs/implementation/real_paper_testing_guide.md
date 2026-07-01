# Corpus-Driven Real-Paper Testing Guide

Use this guide for the next hardening phase:

```text
Corpus-Driven Hardening Of Extraction, Normalization, Semantics, Footnotes, And References
```

The goal is to work through real papers in a reproducible order, identify the
first artifact where structure goes wrong, and fix the earliest parser stage
that owns the problem. The current priority is to review footnote/reference
artifacts before making larger extraction changes.

All paper paths below are relative to:

```text
/Users/robert/Projects/Epiconnector/testpapers
```

## Current Reference Baseline

Latest reference run:

```text
outputs/testpapers_footnote_current_20260701
```

This is the only retained generated parser-output directory after the
2026-07-01 cleanup. Older generated `outputs/` runs were removed so stale
artifacts are not mistaken for current parser behavior.

Current footnote summary:

```text
PDFs: 27
parse command failures: 0
paper_footnotes:
  anchors: 1186
  definitions: 293
  links: 1186
  resolved links: 260
  inferred links: 219
  ambiguous links: 16
  unresolved links: 691
  math/unit anchors suppressed before footnote linking: 30
```

Current papers with unresolved or ambiguous footnote links:

- `Association between anthropometric indices and chronic kidney disease`
  has 2 unresolved dagger links in column headers; its 160 p-value asterisk
  links are now conventional inferred links, not unresolved footnotes.
- `Ethnic Differences in the Relationship Between Insulin Sensitivity and
  Insulin Response` has 95 unresolved links, mostly small-letter fragments in
  column headers from collapsed/rotated extraction.
- `Helicobacter pylori infection in the United States beyond NHANES` has
  33 unresolved numeric row-label links that look like bibliographic citations,
  plus 1 ambiguous `letter:a` body-cell link.
- `Journal of Periodontology - 2015 - Eke` has 529 unresolved links and
  11 ambiguous links, mostly small-letter geometry false positives and repeated
  note candidates.
- `Science-Advanaced-Planetary Health Diet and risk of mortality and chronic
  diseases` has 6 unresolved links and 1 ambiguous link.
- `cardiovascular` has 20 unresolved double-dagger body-cell links with no
  extracted definitions.
- `mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older
  Adults` has 3 unresolved and 3 ambiguous numeric links.
- `periodontis2` has 3 unresolved numeric body-cell links.

## Review Loop

For each checklist item:

1. Inspect the current artifacts under the reference baseline first.
2. Identify the first bad artifact in parser order:
   `extracted_tables.json`, `normalized_tables.json`,
   `column_header_schemas.json`, `resolved_tables.json`,
   `table_definitions.json`, `parsed_cell_values.json`,
   `parsed_tables.json`, `paper_footnotes.json`, `paper_references.json`.
3. Record whether the issue belongs to extraction, normalization, continuation,
   table semantics, footnote detection/linking, or visual-reference resolution.
4. Fix only the earliest responsible stage.
5. Add focused regression coverage only for a known failure or stable artifact
   contract.
6. Re-run the reviewed chunk, then re-run the full corpus after parser behavior
   changes.

## Ordered Review Checklist

### C0. Footnotes And References First

- [x] **C0.0** Resolve embedded Table 1 p-value footnote definitions in
  `metabolic`.
  - PDF path: `papers_from_johnny/metabolic.pdf`
  - Previous artifact issue: Table 1 had detected `a`/`b` p-value superscript
    anchors but no definitions, because the definition line started with
    explanatory prose rather than a marker.
  - Current spot-check result: fixed in
    `outputs/testpapers_footnote_current_20260701`; Table 1 `a`/`b` links are
    resolved, and Table 2 asterisk p-value markers are now conventional
    `inferred` links rather than unresolved footnotes.

- [ ] **C0.1** Review false-positive footnote marker detection in Eke.
  - PDF path: `papers_from_laha/Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009.pdf`
  - Current artifact issue: `paper_footnotes.json` has 529 unresolved links and
    11 ambiguous links.
  - Strong signal: many unresolved anchors are small-letter glyphs such as
    `letter:t`, `letter:r`, and `letter:l`; these are likely not table footnote
    markers. Review whether small-letter geometry is being over-detected.

- [ ] **C0.2** Review bibliographic superscripts versus table footnotes.
  - PDF path: `papers_from_laha/Helicobacter pylori infection in the United States beyond NHANES- a scoping review of seroprevalence estimates by racial and ethnic groups.pdf`
  - Current artifact issue: 33 unresolved links and 1 ambiguous link.
  - Strong signal: the study-name superscripts in the leftmost column are mostly
    numeric citation markers. They should not be treated as unresolved table
    footnotes unless a real local table-note definition exists.

- [ ] **C0.3** Review collapsed/rotated extraction causing bogus footnote
  anchors.
  - PDF path: `papers_from_laha/Ethnic Differences in the Relationship Between Insulin Sensitivity and Insulin Response.pdf`
  - Current artifact issue: 95 unresolved links.
  - Strong signal: anchors come from one collapsed table cell with fragments such
    as `letter:t`, `letter:r`, `letter:fri`, and symbol fragments. This may be an
    extraction-grid failure creating false footnote anchors.

- [x] **C0.4** Resolve statistical-significance stars with footer definitions
  in `stroke`.
  - PDF path: `papers_from_johnny/stroke.pdf`
  - Previous artifact issue: 65 unresolved links.
  - Strong signal: 58 unresolved anchors were statistical-significance
    asterisks, often attached to p-values such as `<0.001***`.
  - Current spot-check result: fixed in
    `outputs/testpapers_footnote_current_20260701`; Table 1, Table 2, and Table 3
    each have local `*`, `**`, and `***` definitions linked by same-table scope.
  - The previous 7 row-label unit exponents are now suppressed before
    `FootnoteAnchor` creation and counted in
    `math_unit_anchor_suppression_count`, so this paper is now a clean resolved
    footnote baseline for the local statistical-star-footer case.

- [ ] **C0.5** Review ambiguous footnote linking where definitions exist but are
  not unique.
  - PDF paths:
    1. `papers_from_laha/Association between anthropometric indices and chronic kidney disease- Insights from NHANES 2009–2018.pdf`
    2. `papers_from_laha/mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017.pdf`
  - Current artifact issue: anthropometric CKD has 2 unresolved dagger links and
    160 conventional inferred p-value-star links; MDPI Mediterranean has
    3 ambiguous links and 3 unresolved numeric links.
  - Decide whether ambiguity comes from duplicate definitions, repeated page
    furniture, or too-broad matching scope.

- [ ] **C0.6** Review unresolved table-reference resolution before worrying
  about figures.
  - Highest unresolved table-reference counts:
    1. `papers_from_laha/An atlas of exposome–phenome associations in health and disease risk.pdf` - 21 unresolved table references.
    2. `papers_from_laha/Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf` - 10 unresolved table references, mostly supplement tables.
    3. `papers_from_laha/An environment-wide association study (EWAS) on type 2 diabetes mellitus.pdf` - 9 unresolved supplement table references.
    4. `papers_from_laha/Uses of NHANES Biomarker Data for Chemical Risk Assessment- Trends, Challenges, and Opportunities.pdf` - 9 unresolved table references.
  - Treat unresolved figure references separately; the table parser is not yet a
    figure extractor.

Acceptance for C0: footnote anchors are separated into true table-note markers,
bibliographic citations, statistical-significance markers, and false positives.
Reference resolution should clearly distinguish unresolved in-paper tables from
supplement-only or out-of-scope references.

### C1. Actual Failed Table Statuses

- [ ] **C1.1** Review failed statuses that may be correct non-target tables.
  1. `papers_from_laha/An environment-wide association study (EWAS) on type 2 diabetes mellitus.pdf`
     - `An environment-wide association study (EWAS) on type 2 diabetes mellitus-p6-t0`
     - Status: `failed`, reason: `insufficient_table_structure_after_extraction`.
     - Prior review: structurally plausible ENWAS data table with sparse left
       descriptor columns; likely unsupported table family rather than missing
       extraction.
  2. `papers_from_laha/mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017.pdf`
     - `mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017-p3-t0`
     - Status: `failed`, reason: `insufficient_table_structure_after_extraction`.
     - Prior review: text/reference table comparing frailty definitions; likely
       not a Table 1-style data table.

- [ ] **C1.2** Review `non_table_layout_candidate` failures.
  1. `papers_from_laha/Asthma prevalence among United States population insights from NHANES data analysis.pdf`
     - `Asthma prevalence among United States population insights from NHANES data analysis-p6-t0`
  2. `papers_from_laha/GOLD BioAge and depression- Associations with mortality among depressed NHANES participants (2005–2018).pdf`
     - `GOLD BioAge and depression- Associations with mortality among depressed NHANES participants (2005–2018)-p1-t0`
  3. `papers_from_laha/Helicobacter pylori infection in the United States beyond NHANES- a scoping review of seroprevalence estimates by racial and ethnic groups.pdf`
     - `Helicobacter pylori infection in the United States beyond NHANES- a scoping review of seroprevalence estimates by racial and ethnic groups-p5-t0-resolved-continuation`
  4. `papers_from_laha/periodontis2.pdf`
     - `periodontis2-p6-t0`
  5. `papers_from_johnny/periodontitis.pdf`
     - `periodontitis-p11-t0`

- [ ] **C1.3** Review the collapsed-grid failure.
  - PDF path: `papers_from_laha/Ethnic Differences in the Relationship Between Insulin Sensitivity and Insulin Response.pdf`
  - Table: `Ethnic Differences in the Relationship Between Insulin Sensitivity and Insulin Response-p5-t0`
  - Status: `failed`, reason: `collapsed_grid_unrecovered`.
  - Current expectation: fail closed is better than recovering an implausible
    50-plus-column rotated grid. Any fix should recover the true visible grid,
    probably in extraction using raw PyMuPDF geometry.

Acceptance for C1: every failed table is classified as correct non-target table,
extraction failure, normalization failure, unsupported table family, or ambiguous
pending review.

### C2. Continuation Decisions

- [ ] **C2.1** Review accepted continuations and confirm one visual continued
  table becomes one semantic resolved table.
  1. `papers_from_laha/Association between anthropometric indices and chronic kidney disease- Insights from NHANES 2009–2018.pdf`
     - p7 -> p8 and p11 -> p12 accepted.
  2. `papers_from_laha/Helicobacter pylori infection in the United States beyond NHANES- a scoping review of seroprevalence estimates by racial and ethnic groups.pdf`
     - p5 -> p6 and p6 -> p7 accepted.
  3. `papers_from_laha/Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009.pdf`
     - p6 -> p7 accepted.
  4. `papers_from_laha/Systemic inflammation markers and the prevalence of hypertension- A NHANES cross-sectional study.pdf`
     - p5 -> p6 accepted.
  5. `papers_from_johnny/gallstones.pdf`
     - p5 -> p6 accepted.
  6. `papers_from_laha/mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017.pdf`
     - p5 -> p6 accepted.

- [ ] **C2.2** Review rejected continuation candidates that may expose header or
  column-schema defects.
  1. `papers_from_laha/Asthma prevalence among United States population insights from NHANES data analysis.pdf`
     - p4 -> p5 rejected; p5 -> p6 rejected.
  2. `papers_from_laha/Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009.pdf`
     - p4 -> p5 rejected.
  3. `papers_from_laha/Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf`
     - p2 -> p3 rejected.
  4. `papers_from_laha/periodontis2.pdf`
     - p5 -> p6 rejected.

Acceptance for C2: continuation decisions are explainable from
`resolved_tables.json`, source table IDs, row provenance, and
`column_header_schemas.json`.

### C3. Header/Body And Extraction Geometry

- [ ] **C3.1** Review current header/body split disagreements.
  1. `papers_from_laha/Association between metabolic score for insulin resistance (METS-IR) and hypertension- a cross-sectional study based on NHANES 2007–2018.pdf`
     - p6-t0: hline body start 2, value-anchor body start 3, selected 2.
  2. `papers_from_laha/Asthma prevalence among United States population insights from NHANES data analysis.pdf`
     - p5-t0 and p6-t0.
  3. `papers_from_laha/GOLD BioAge and depression- Associations with mortality among depressed NHANES participants (2005–2018).pdf`
     - p4-t1: hline body start 2, value-anchor body start 4, selected 2.
  4. `papers_from_laha/Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009.pdf`
     - p4-t0 and p5-t0: hline body start 3, value-anchor body start 10,
       selected 10.
  5. `papers_from_johnny/Sarcopenia.pdf`
     - p7-t0 and p8-t0.
  6. `papers_from_laha/Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf`
     - p2-t0.
  7. `papers_from_johnny/cardiovascular.pdf`
     - p5-t0.
  8. `papers_from_laha/mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017.pdf`
     - p7-t0.

- [ ] **C3.2** Review explicit hline and preamble behavior in papers with
  title/preamble rows above true column headers.
  1. `papers_from_johnny/fld.pdf`
  2. `papers_from_johnny/pad.pdf`
  3. `papers_from_laha/cobaltpaper.pdf`
  4. `papers_from_johnny/cardiovascular.pdf`
  5. `papers_from_laha/Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009.pdf`

- [ ] **C3.3** Decide whether raw PyMuPDF geometry should replace
  PyMuPDF4LLM-derived grids for specific failure classes.
  - Start only with ruled or rotated cases where words, rules, and table bbox
    provide strong structural evidence.
  - Do not add downstream continuation/schema hacks to compensate for bad
    extraction geometry.

Acceptance for C3: each disagreement is classified as correct hline split,
correct value-anchor split, extraction hline defect, normalization candidate
defect, or unsupported/misrouted table family.

### C4. Mixed Table Families And Regression Baseline

- [ ] **C4.1** Review estimate-result and data-presentation tables without
  forcing them into descriptive Table 1 semantics.
  1. `papers_from_johnny/cardiovascular.pdf`
  2. `papers_from_johnny/stroke.pdf`
  3. `papers_from_laha/cobaltpaper.pdf`
  4. `papers_from_laha/An atlas of exposome–phenome associations in health and disease risk.pdf`
  5. `papers_from_laha/An environment-wide association study (EWAS) on type 2 diabetes mellitus.pdf`

- [ ] **C4.2** Re-run representative mostly-successful descriptive papers after
  fixes from C0-C4.1.
  1. `papers_from_laha/Systemic inflammation markers and the prevalence of hypertension- A NHANES cross-sectional study.pdf`
  2. `papers_from_laha/Lead exposure as a contributor to the Black–White racial disparity in blood pressure- evidence from NHANES 1988–1994 and 2017–2020.pdf`
  3. `papers_from_johnny/hypertension.pdf`
  4. `papers_from_johnny/pad.pdf`
  5. `papers_from_johnny/fld.pdf`

- [ ] **C4.3** Run the complete 27-PDF corpus after each substantial parser
  change set and compare against the latest accepted baseline. Report command
  failures, missing artifacts, table status counts, failure reasons, resolved
  continuation counts, footnote link statuses, reference resolution statuses,
  parsed cell-value counts, and header/body split disagreements.

Acceptance for C4: corpus comparison explains any movement in table-level
status, artifact counts, footnote/reference counts, or structural split
disagreements. Command success alone is not sufficient.

## Issue Note Template

Use this short note for each reviewed chunk or paper:

```text
Review ID:
PDF path:
output directory:
table_id/table_index:
current status:
first bad artifact:
earliest responsible stage:
observed evidence:
expected behavior:
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
