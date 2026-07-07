# Header/Body Cleanup Real-Table Inspection

This note records the real-paper header/body row changes observed after
removing brittle content-scoring header detection from the normalization
fallback path.

Current reference run:

- `outputs/testpapers_batch_20260707_no_backend_grid`
- PDFs parsed: 27/27
- Extracted tables: 66
- Extraction geometry: 64 `pymupdf_positioned_words_and_rules`, 2
  `pymupdf_positioned_words`, 0 `pymupdf4llm_json_table_cells`
- Canonical extraction layer: 66 `pymupdf_positioned_geometry`
- Table processing statuses: ok 16, rescued 43, failed 0
- Bibliography extraction: 27 papers, 0 empty bibliographies, 1370 entries
- Footnote links: 387 links, 387 resolved
- Previous backend-grid survivor `periodontitis-p11-t0` is no longer emitted.

The current parser no longer uses the caption-contaminated backend-row-drop
path. PyMuPDF4LLM may still provide rough table boxes, but emitted rows,
columns, cell boxes, row bounds, and header geometry must come from positioned
PyMuPDF reconstruction. If a rough backend box cannot be reconstructed from
positioned geometry, it is not emitted as an extracted table.

Historical comparison runs:

- Previous baseline: `outputs/testpapers_batch_20260707_caption_binding`
- Cleanup run: `outputs/testpapers_batch_20260707_header_cleanup`

Corpus-level results from the cleanup run:

- PDFs parsed: 27/27
- Table statuses unchanged from baseline: ok 30, rescued 29, failed 1
- Known failed table: `periodontitis-p11-t0`
- Bibliography extraction unchanged: 27 papers, 0 empty bibliographies, 1370 entries
- Footnote links unchanged: 370 links, 370 resolved

Historical follow-up extraction run:

- Caption-row-drop run: `outputs/testpapers_batch_20260707_caption_row_drop`
- PDFs parsed: 27/27
- Table statuses: ok 27, rescued 33, failed 1
- Known failed table remains `periodontitis-p11-t0`, accepted as a non-table
  boxed supplementary-table note.
- Bibliography extraction remains stable: 27 papers, 0 empty bibliographies,
  1370 entries.
- Footnote links remain stable: 370 links, 370 resolved.

Seven extracted tables used the now-retired caption-contaminated backend-row
correction in that historical follow-up run. The current parser should solve
these cases through positioned PyMuPDF reconstruction and `TableRegion`
ownership, not by dropping backend rows.

Changed extracted tables in the historical follow-up run:

- Anthropometric CKD page 8 Table 1 continuation: `17x5 -> 16x5`; removed a
  continued-caption row and kept the 5-column header/body structure.
- Anthropometric CKD page 15 Table 6: `10x3 -> 9x3`; removed `metric indices.`
  and kept `Anthropometric indices | AUC | 95% CI` as row 0.
- Lead page 7 Table 4: `15x5 -> 15x4`; improved the table from split model/CI
  fragments into the visible row-label plus three-model layout.
- eGDR CKM page 4 Table 1: kept `48x7`; removed the caption-contaminated first
  backend row and preserved `Characteristics | All | Q1 | Q2 | Q3 | Q4 | P`.
- Sarcopenia page 5 Table 1: `49x5 -> 48x5`; removed `2011-2018` from the
  extracted grid and preserved the wrapped `Non-sarco-/penia` and
  `Sarcope-/nia` headers. Visual review confirmed this is correct.
- FLD page 5 Table 1: kept `41x5`; removed the caption-contaminated first
  backend row and preserved `Variables | Overall | Non-FLD group | FLD group | P-value`.
- Hypertension page 6 Table 2: kept `13x7`; removed the caption tail and
  preserved the `Model 1/Model 2/Model 3a` two-column OR/P-value blocks.

`periodontitis-p11-t0` is no longer emitted in the current reference run.
Visual review indicated it was not a data table; it was a boxed note describing
supplementary tables. Do not prioritize recovering it as a table extraction
case.

## Changed Tables

### 1. EWAS, page 6 table 0

Table ID:
`An environment-wide association study (EWAS) on type 2 diabetes mellitus-p6-t0`

Change:

- Old header rows: `[0, 1, 2, 3]`; old body start: `4`
- New header rows: `[1, 2, 3]`; new body start: `4`

Rows to inspect:

```text
row 0: Table 1. Highly statistically significant environmental factors associated | with T2D | found in more | than one NHANES | cohort.
row 1:  |  |  |  | Predicted
row 2: Environment N{ T2D, |  |  | Factor Level | Probability
row 3: Environmental class Factor Cohort No T2D | P | OR (95% CI) | (Lo-Hi) | (Lo-Hi)
row 4: Nutrients cis-b-carotene 2001-2002 211, 2852 | 0.01 | 0.6 (0.5-0.8) | 0.4-1.4 ug/dL | 0.12-0.05
```

Visual review: confirmed improvement. Row 0 is the caption. The PDF has a bold
horizontal rule under the caption, then whitespace, then a regular horizontal
rule before row 1. Row 1 is the correct start of the header band.

### 2. Anthropometric CKD, page 15 table 0

Table ID:
`Association between anthropometric indices and chronic kidney disease- Insights from NHANES 2009-2018-p15-t0`

Change:

- Old header rows: `[0]`; old body start: `1`
- New header rows: `[1]`; new body start: `2`

Rows to inspect:

```text
row 0: metric indices. |  |
row 1: Anthropometric indices | AUC | 95% CI
row 2: WC | 0.586 | 0.595-0.605
row 3: Height | 0.546 | 0.555-0.565
row 4: Weight | 0.504 | 0.514-0.524
```

Historical follow-up result: the retired
`outputs/testpapers_batch_20260707_caption_row_drop` run removed row 0 with
`metadata.grid_refinement_source = "caption_contaminated_backend_row_drop"`.
That backend-row-drop path is no longer current parser behavior; caption/table
ownership now must come from positioned PyMuPDF reconstruction and
`TableRegion`.

### 3. Metabolic, page 5 table 0

Table ID:
`Association between metabolic score for insulin resistance (METS-IR) and hypertension- a cross-sectional study based on NHANES 2007-2018-p5-t0`

Change:

- Old header rows: `[0]`; old body start: `1`
- New header rows: `[0, 1]`; new body start: `2`

Rows to inspect:

```text
row 0: Variable | Overall | Hypertensive | Non-hypertensive | P-value
row 1:  | (N = 8,902) | (n = 1,846) | (n = 7,056) |
row 2: Age (years), mean +/- SD | 45.93 +/- 0.29 | 55.88 +/- 0.40 | 43.78 +/- 0.31 | < 0.001
row 3: Sex, n (%) |  |  |  | 0.007
row 4: Male | 4,622 (51.89%) | 1,017 (55.62%) | 3,605 (51.09%) |
```

Visual review: confirmed improvement. Row 1 is a sample-size row and belongs
to the column-header band, not the body.

### 4. eGDR CKM, page 4 table 0

Table ID:
`Role of Estimated Glucose Disposal Rate in Staging and Death Risk of Cardiovascular-Kidney-Metabolic Syndrome- Insights from NHANES 1999-2018-p4-t0`

Change:

- Old header rows: `[0]`; old body start: `1`
- New header rows: `[0, 1]`; new body start: `2`

Rows to inspect:

```text
row 0: Characteristics | All | Q1 | Q2 | Q3 | Q4 | P
row 1:  | (N = 27,769) | (N = 6,946) | (N = 6,939) | (N = 6,942) | (N = 6,942) |
row 2: Age, years | 55.00 (40.00, 67.00) | 59.00 (46.00, 68.00) | 60.00 (46.00, 71.00) | 54.00 (40.00, 68.00) | 39.00 (29.00, 53.00) | < 0.001
row 3: Male, n (%) | 14,605 (52.59) | 4,148 (56.65) | 4,125 (56.32) | 3,519 (48.07) | 3,427 (46.80) | < 0.001
row 4: Race and ethnicity, n (%) |  |  |  |  |  | < 0.001
```

Visual review: confirmed improvement. Row 1 is a sample-size row and belongs
to the column-header band, not the body.

### 5. Sarcopenia, page 5 table 0

Table ID:
`Sarcopenia-p5-t0`

Change:

- Old header rows: `[0]`; old body start: `1`
- New header rows: `[1, 2, 3]`; new body start: `4`

Rows to inspect:

```text
row 0: 2011-2018 |  |  |  |
row 1: Characteristic | Total | Non-sarco- | Sarcope- | p-value
row 2:  | (n = 8802) | penia | nia |
row 3:  |  | (n = 8032) | (n = 770) |
row 4: Age(Mean +/- SD) | 39.2 +/- 11.5 | 38.8 +/- 11.5 | 43.6 +/- 11.3 | < 0.001**
```

Visual review: confirmed improvement. Row 0 is preamble/continued context, and
rows 1-3 are the correct header stack.

### 6. Planetary Health, page 3 table 0

Table ID:
`Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis-p3-t0`

Change:

- Old header rows: `[0, 1, 2, 3]`; old body start: `4`
- New header rows: `[1, 2, 3]`; new body start: `4`

Rows to inspect:

```text
row 0: Characteristic | Planetary health diet score quintiles in US NHANES Planetary health diet score quintiles in UKB |  |  |  |  |  |
row 1:  | Quintile 1 Quintile 2 Quintile 3 Quintile 4 Quintile 1 Quintile 2 Quintile 3 Quintile 4 |  |  |  |  |  |
row 2:  | (10-35), (35-43), (43-51), (51-95), (17-52), (52-60), (60-68), (68-110), |  |  |  |  |  |
row 3:  | N = 10,737 | N = 10,737 | N = 10,736 | N = 10,737 | N = 31,343 | N = 31,343 | N = 31,343
row 4: Current Income level | 3,392 (33) | 2,342 (22) | 1,761 (17) | 1,259 (12) | 3,254 (10) | 2,160 (6.9) | 1,797 (5.7)
```

Initial read: needs visual review; row 0 may be a legitimate spanning header.

### 7. Planetary Health, page 5 table 0

Table ID:
`Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis-p5-t0`

Change:

- Old header rows: `[0]`; old body start: `1`
- New header rows: `[1]`; new body start: `2`

Rows to inspect:

```text
row 0: Outcome | Numbers HR (95% CI) I2% PBegg value PEgger value Model |  |  |
row 1: Colorectal cancer | 3 | 0.87 (0.78-0.97) | 0.0 | 1.000
row 2: Lung cancer | 3 | 0.68 (0.59, 0.78) | 0.0 | 1.000
row 3: CVDs | 9 | 0.83 (0.76-0.90) | 62.7 | 0.466
row 4:  |  |  |  |
```

Initial read: likely regression; row 0 looks like the header row and row 1
looks like a body row.

### 8. Cardiovascular, page 4 table 0

Table ID:
`cardiovascular-p4-t0`

Change:

- Old header rows: `[0]`; old body start: `1`
- New header rows: `[0, 1]`; new body start: `2`

Rows to inspect:

```text
row 0:  | All | Live | Dead | Dead cause of cardiovascular
row 1:  | (n = 7921) | (n = 6010) | (n = 1911) | (n = 585)
row 2: Age(years) | 60.79 +/- 12.18 | 57.55 +/- 10.95 | 70.97 +/- 10.05 | 72.75 +/- 9.52
row 3: Male | 3866(48.81%) | 2800(46.59%) | 1066(55.78%) | 322(55.04%)
row 4: BMI(Kg/m2) | 28.57 +/- 7.13 | 29.01 +/- 6.83 | 27.2 +/- 7.86 | 27.28 +/- 8.26
```

Initial read: likely improvement; sample-size row belongs to the column-header
band.

### 9. Cobalt, page 3 table 0

Table ID:
`cobaltpaper-p3-t0`

Change:

- Old header rows: `[0]`; old body start: `1`
- New header rows: `[0, 1]`; new body start: `2`

Rows to inspect:

```text
row 0:  |  | Q1 | Q2 | Q3 | Q4
row 1: Cobalt quartiles (mg/l) | All | 0.12 | 0.13-0.14 | 0.15-0.18 | >=0.19 P value P for trend
row 2: Number | 6866 | 1931 | 1418 | 1792 | 1725
row 3: Age (yrs), mean+/-SD | 60.3+/-12.0 | 58.1+/-11.2 | 60.0+/-11.4 | 61.4+/-11.6 | 61.7+/-13.2 <.001 <.001
row 4: Male, n (%) | 3333 (48.5%) | 1202 (62.2%) | 749 (52.8%) | 788 (44.0%) | 594 (34.4%) <.001 <.001
```

Initial read: likely improvement; threshold row is part of the header.

### 10. Cobalt, page 3 table 1

Table ID:
`cobaltpaper-p3-t1`

Change:

- Old header rows: `[0]`; old body start: `1`
- New header rows: `[0, 1]`; new body start: `2`

Rows to inspect:

```text
row 0:  |  | Q1 | Q2 | Q3 | Q4 |  |
row 1: Cobalt quartiles (mg/l) | All | 0.12 | 0.13-0.14 | 0.15-0.18 | >=0.19 | P value | P for trend
row 2: Number | 6866 | 1931 | 1418 | 1792 | 1725 |  |
row 3: SBP (mm Hg), mean+/-SD | 131.0+/-19.7 | 129.4+/-18.1 | 131.2+/-19.0 | 132.1+/-20.2 | 131.3+/-21.3 | <.001 | .002
row 4: DBP (mm Hg), mean+/-SD | 72.3+/-12.1 | 73.0+/-11.8 | 73.1+/-12.1 | 72.3+/-12.1 | 70.7+/-12.2 | <.001 | <.001
```

Initial read: likely improvement; threshold row is part of the header.

### 11. Cobalt, page 4 table 1

Table ID:
`cobaltpaper-p4-t1`

Change:

- Old header rows: `[0]`; old body start: `1`
- New header rows: `[0, 1]`; new body start: `2`

Rows to inspect:

```text
row 0:  | Adjusted | 95% confidence |
row 1: Variable | odds ratio | intervals | P value
row 2: Cobalt |  |  |
row 3: Q1 | 1(reference) |  |
row 4: Q2 | 0.97 | 0.82-1.14 | .679
```

Initial read: likely improvement; row 1 is a leaf-header row.

### 12. Cobalt, page 5 table 0

Table ID:
`cobaltpaper-p5-t0`

Change:

- Old header rows: `[0]`; old body start: `1`
- New header rows: `[0, 1]`; new body start: `2`

Rows to inspect:

```text
row 0:  | Adjusted | 95% confidence |
row 1: Variable | odds ratio | intervals | P value
row 2: Cobalt |  |  |
row 3: Q1 | 1(reference) |  |
row 4: Q2 | 0.86 | 0.71-1.01 | .140
```

Initial read: likely improvement; row 1 is a leaf-header row.

### 13. Periodontitis, page 8 table 0

Table ID:
`periodontitis-p8-t0`

Change:

- Old header rows: `[0, 1, 2]`; old body start: `3`
- New header rows: `[0, 1, 2, 3]`; new body start: `4`

Rows to inspect:

```text
row 0: 0-1 healthy | 2-3 healthy lifestyle factors 4-6 healthy lifestyle factors Each additional healthy |  |  |  |  |  |
row 1: lifestyle |  |  |  |  |  |  | lifestyle factor
row 2: factor |  |  |  |  |  |  |
row 3:  | OR | 95% CI | p | OR | 95% CI | p | OR
row 4: Total Model 1 Ref | 0.80 | (0.70, 0.91) | < 0.01 | 0.53 | (0.42, 0.67) | < 0.01 | 0.84
```

Initial read: likely improvement; row 3 is a leaf-header row.

### 14. Stroke, page 6 table 0

Table ID:
`stroke-p6-t0`

Change:

- Old header rows: `[0]`; old body start: `1`
- New header rows: `[0, 1]`; new body start: `2`

Rows to inspect:

```text
row 0: Variables | Overall | Non-Stroke | Stroke | P value
row 1:  | (n = 44,019) | (n = 42,533) | (n = 1486) |
row 2: Age, years | 45.8 [45.5, 46.2] | 45.5 [45.1, 45.8] | 60.3 [59.4, 61.2] | < 0.001***
row 3: Sex-man, n (%) | 49.3 [47.6, 51.0] | 49.4 [48.9, 49.9] | 45.3 [42.1, 48.4] | 0.01*
row 4: Race, n (%) |  |  |  | < 0.001***
```

Initial read: likely improvement; sample-size row belongs to the column-header
band.
