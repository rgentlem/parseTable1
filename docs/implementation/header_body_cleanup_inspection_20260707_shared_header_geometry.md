# Header/Body Cleanup Inspection: Shared Header Geometry

This note records the real-paper changes after adding shared PyMuPDF
word/rule header-span repair for ruled explicit tables and text-position
fallback tables.

Comparison runs:

- Previous baseline: `outputs/testpapers_batch_20260707_caption_row_drop`
- Current run: `outputs/testpapers_batch_20260707_shared_header_geometry_schema`

Corpus-level result:

- PDFs parsed: 27/27
- Command failures: 0
- Extracted tables: 67 in both runs
- Table statuses: `ok: 27`, `rescued: 32`, `failed: 1`
- Known failed table: `periodontitis-p11-t0`, `non_table_layout_candidate`
- Bibliography: 1370 entries, 0 empty bibliographies, 0 diagnostics
- Footnotes: 381 links, 381 resolved, 0 inferred, 0 ambiguous, 0 unresolved

Net interpretation:

- Good: `papers_from_laha/Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf`
  p2-t0 and p3-t0 now share the same extracted
  9-column header stack, the same `ColumnHeaderSchema`, and resolve as one
  integrated Table 1.
- Good: several previously collapsed upper group-header rows now split into
  visible multicolumn groups: PRISm, PAD, gallstones, MDPI frailty, Lead,
  Cobalt, and periodontitis.
- Neutral: `table_processing_status.json` has one fewer source-fragment row
  because the Planetary Health source file's p2-t0 and p3-t0 fragments are now
  one resolved continuation.
- Watch: `papers_from_laha/cobaltpaper.pdf` p4-t0 still has imperfect semantic
  header grouping. The extracted grid improves, but the column-schema group
  labels still need later review.

Only two table-region decisions changed:

- `papers_from_laha/Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf`
  p3-t0: row 0 moved from `preamble_rows` into `column_header_rows`, giving
  header rows `[0, 1, 2, 3]`.
- `papers_from_laha/Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf`
  p5-t0: row 0 moved from preamble into the header, giving header row `[0]`;
  this is correct for Table 2 because row 0 is the visible
  `Outcome | Numbers | HR...` header.

## Changed Extracted Grids

### 1. `papers_from_laha/GOLD BioAge and depression- Associations with mortality among depressed NHANES participants (2005–2018).pdf` - `GOLD BioAge and depression- Associations with mortality among depressed NHANES participants (2005–2018)-p4-t0`

Shape: `50x7 -> 50x7`

```text
old row 0: Characteristic | Total Gompertz law-based biological age (GOLD BioAge), year |  |  |  |  | p-Value
old row 1:  |  | Q1(<=32.7) | Q2(32.8-49.5) | Q3(49.6-65.6) | Q4(>=65.7) |
new row 0: Characteristic | Total | Gompertz law-based biological age (GOLD BioAge), year |  |  |  | p-Value
new row 1:  |  | Q1(<=32.7) | Q2(32.8-49.5) | Q3(49.6-65.6) | Q4(>=65.7) |
```

Assessment: improvement. `Total` is a standalone column; GOLD BioAge spans
Q1-Q4. The schema builder now preserves that mixed leaf/span structure.

### 2. `papers_from_laha/Lead exposure as a contributor to the Black–White racial disparity in blood pressure- evidence from NHANES 1988–1994 and 2017–2020.pdf` - `Lead exposure as a contributor to the Black–White racial disparity in blood pressure- evidence from NHANES 1988–1994 and 2017–2020-p4-t0`

Shape: `27x3 -> 27x3`

```text
old row 1:  | White participants Black participants |
new row 1:  | White participants | Black participants
```

Assessment: improvement.

### 3. `papers_from_laha/Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf` - `Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis-p2-t0`

Shape: `56x9 -> 56x9`

```text
old row 0: Characteristic | Planetary | health diet score | quintiles in US | NHANES | Planetary | health diet | score quintiles | in UKB
new row 0: Characteristic | Planetary health diet score quintiles in US NHANES |  |  |  | Planetary health diet score quintiles in UKB |  |  |
```

Assessment: improvement. The base page now represents the two visible
spanning groups.

### 4. `papers_from_laha/Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf` - `Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis-p3-t0`

Shape: `17x9 -> 17x9`

```text
old row 0: Characteristic | Planetary health diet score quintiles in US NHANES Planetary health diet score quintiles in UKB |  |  |  |  |  |  |
old row 1:  | Quintile 1 Quintile 2 Quintile 3 Quintile 4 Quintile 1 Quintile 2 Quintile 3 Quintile 4 |  |  |  |  |  |  |
old row 2:  | (10-35), (35-43), (43-51), (51-95), (17-52), (52-60), (60-68), (68-110), |  |  |  |  |  |  |
new row 0: Characteristic | Planetary health diet score quintiles in US NHANES |  |  |  | Planetary health diet score quintiles in UKB |  |  |
new row 1:  | Quintile 1 | Quintile 2 | Quintile 3 | Quintile 4 | Quintile 1 | Quintile 2 | Quintile 3 | Quintile 4
new row 2:  | (10-35), | (35-43), | (43-51), | (51-95), | (17-52), | (52-60), | (60-68), | (68-110),
```

Assessment: improvement and the primary fix. p2-t0 and p3-t0 now integrate as
one resolved Table 1.

### 5. `papers_from_laha/Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf` - `Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis-p5-t0`

Shape: `17x6 -> 17x6`

```text
old row 0: Outcome | Numbers HR (95% CI) I2% PBegg value PEgger value Model |  |  |  |
new row 0: Outcome | Numbers | HR (95% CI) | I2% | PBegg value | PEgger value Model
```

Assessment: improvement. Row 0 is the Table 2 header, not preamble.

### 6. `papers_from_laha/The prevalence and mortality risks of PRISm and COPD in the United States from NHANES 2007–2012.pdf` - `The prevalence and mortality risks of PRISm and COPD in the United States from NHANES 2007–2012-p4-t0`

Shape: `27x9 -> 27x9`

```text
old row 0:  | Overall 2007-2012 |  | 2007-2008 (N = 4237) 2009-2010 (N = 4783) 2011-2012 (N = 4308) |  |  |  |  |
new row 0:  | Overall 2007-2012 |  | 2007-2008 (N = 4237) |  | 2009-2010 (N = 4783) |  | 2011-2012 (N = 4308) |
```

Assessment: improvement. Survey-cycle groups now align with `% (N)` / `95% CI`
leaf pairs.

### 7. `papers_from_laha/The prevalence and mortality risks of PRISm and COPD in the United States from NHANES 2007–2012.pdf` - `The prevalence and mortality risks of PRISm and COPD in the United States from NHANES 2007–2012-p7-t0`

Shape: `30x9 -> 30x9`

```text
old row 0:  | All-Cause Mortality Cancer |  |  |  | Cardiovascular Diseases Chronic Lower Respiratory |  |  |
new row 0:  | All-Cause Mortality |  | Cancer |  | Cardiovascular Diseases |  | Chronic Lower Respiratory |
```

Assessment: improvement. Outcome groups now align with hazard-ratio / CI leaf
pairs.

### 8. `papers_from_laha/cobaltpaper.pdf` - `cobaltpaper-p4-t0`

Shape: `27x5 -> 27x5`

```text
old row 1: Dyslipidemia Q1 | Q2 Q3 Q4 P for |  |  |
new row 1: Dyslipidemia Q1 | Q2 | Q3 | Q4 | P for
```

Assessment: extracted grid improves, but schema grouping remains a review
case.

### 9. `papers_from_johnny/gallstones.pdf` - `gallstones-p5-t0`

Shape: `53x5 -> 53x5`

```text
old row 0: Variables | Overall Gallstones |  |  | P-value
new row 0: Variables | Overall | Gallstones |  | P-value
```

Assessment: improvement.

### 10. `papers_from_johnny/gallstones.pdf` - `gallstones-p6-t0`

Shape: `32x5 -> 32x5`

```text
old row 0: Variables | Overall Gallstones |  |  | P-value
new row 0: Variables | Overall | Gallstones |  | P-value
```

Assessment: improvement.

### 11. `papers_from_johnny/hypertension.pdf` - `hypertension-p5-t0`

Shape: `47x7 -> 47x7`

```text
old row 1: Characteristics | Total Healthy diet and Healthy diet but Unhealthy diet and Unhealthy diet P value |  |  |  |  |
new row 1: Characteristics | Total | Healthy diet and Healthy diet but Unhealthy diet and Unhealthy diet P value |  |  |  |
```

Assessment: partial improvement. `Total` separates correctly, but the four
lifestyle groups remain partially collapsed and need later schema/extraction
review.

### 12. `papers_from_laha/mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017.pdf` - `mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017-p5-t0`

Shape: `16x6 -> 16x6`

```text
old row 0:  | Overall 1 Low 1 Moderate 1 High 1 |  |  |  |
new row 0:  | Overall 1 | Low 1 | Moderate 1 | High 1 |
```

Assessment: improvement.

### 13. `papers_from_laha/mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017.pdf` - `mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017-p6-t0`

Shape: `31x6 -> 31x6`

```text
old row 0:  | Overall 1 Low 1 Moderate 1 High 1 |  |  |  |
new row 0:  | Overall 1 | Low 1 | Moderate 1 | High 1 |
```

Assessment: improvement.

### 14. `papers_from_laha/mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017.pdf` - `mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017-p7-t0`

Shape: `13x6 -> 13x6`

```text
old row 0:  | Overall 1 Low 1 Moderate 1 High 1 |  |  |  |
new row 0:  | Overall 1 | Low 1 | Moderate 1 | High 1 |
```

Assessment: improvement.

### 15. `papers_from_laha/mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017.pdf` - `mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017-p8-t0`

Shape: `32x6 -> 32x6`

```text
old row 0:  | Overall 1 Robust 1 Pre-Frail 1 Frail 1 |  |  |  |
new row 0:  | Overall 1 | Robust 1 | Pre-Frail 1 | Frail 1 |
```

Assessment: improvement.

### 16. `papers_from_johnny/pad.pdf` - `pad-p5-t0`

Shape: `49x4 -> 49x4`

```text
old row 0: Variables | Overall PAD P-value |  |
new row 0: Variables | Overall | PAD | P-value
```

Assessment: improvement.

### 17. `papers_from_johnny/periodontitis.pdf` - `periodontitis-p8-t0`

Shape: `44x10 -> 44x10`

```text
old row 0: 0-1 healthy | 2-3 healthy lifestyle factors 4-6 healthy lifestyle factors Each additional healthy |  |  |  |  |  |  |  |
new row 0: 0-1 healthy | 2-3 healthy lifestyle factors |  |  | 4-6 healthy lifestyle factors |  |  | Each additional healthy |  |
```

Assessment: improvement. The three grouped lifestyle-factor columns now align
with OR / 95% CI / p leaf triples. `periodontitis-p11-t0` remains the accepted
non-table boxed note failure.

## Follow-Up

- `papers_from_laha/cobaltpaper.pdf` p4-t0 and
  `papers_from_johnny/hypertension.pdf` p5-t0 are the remaining visible
  partials from this change. Both improved at the extracted-grid level but
  still have header grouping issues that should be handled as general mixed
  header-stack work, not by paper-specific text rules.
- A real-paper regression test would be valuable for
  `papers_from_laha/Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf`
  p2-t0/p3-t0: assert matching extracted header rows, matching column schema
  labels/groups, and one integrated resolved Table 1.
