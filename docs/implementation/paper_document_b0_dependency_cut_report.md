# B0 Dependency-Cut Report

Comparison:

- baseline: `outputs/testpapers_batch_b1_expectations_20260720`
- candidate: `outputs/testpapers_batch_b0_dependency_cut_20260720`
- result: 28/28 PDFs completed; no failed paper

## Canonical block changes

| Source PDF | PDF page | Source block | Change |
|---|---:|---:|---|
| `An environment-wide association study (EWAS) on type 2 diabetes mellitus.pdf` | 9 | 12 | heading -> body |
| `Association between metabolic score for insulin resistance (METS-IR) and hypertension- a cross-sectional study based on NHANES 2007–2018.pdf` | 9 | 13 | heading/body split removed; 40-line body block |
| `Ethnic Differences in the Relationship Between Insulin Sensitivity and Insulin Response.pdf` | 7 | 3 | heading/body split removed; 49-line body block |
| `GOLD BioAge and depression- Associations with mortality among depressed NHANES participants (2005–2018).pdf` | 7 | 17 | heading -> body |
| `Helicobacter pylori infection in the United States beyond NHANES- a scoping review of seroprevalence estimates by racial and ethnic groups.pdf` | 12 | 2 | heading/body split removed; 83-line body block |
| `Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009.pdf` | 11 | 3 | heading -> body |
| `NutritionEx.pdf` | 10 | 15 | heading/body split removed; 41-line body block |
| `Sarcopenia.pdf` | 11 | 6 | heading/body split removed; 41-line body block |
| `Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf` | 9 | 4 | body/heading split removed; 6-line body block |
| `Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf` | 9 | 5 | heading/body split removed; 22-line body block |
| `Systemic inflammation markers and the prevalence of hypertension- A NHANES cross-sectional study.pdf` | 10 | 10 | heading -> body |
| `The prevalence and mortality risks of PRISm and COPD in the United States from NHANES 2007–2012.pdf` | 10 | 10 | heading/body split removed; 42-line body block |
| `Uses of NHANES Biomarker Data for Chemical Risk Assessment- Trends, Challenges, and Opportunities.pdf` | 7 | 5 | heading -> body |
| `cardiovascular.pdf` | 9 | 15 | heading/body split removed; 43-line body block |
| `cobaltpaper.pdf` | 6 | 6 | heading -> body |
| `fld.pdf` | 11 | 17 | heading/body split removed; 37-line body block |
| `gallstones.pdf` | 12 | 7 | heading/body split removed; 37-line body block |
| `hypertension.pdf` | 8 | 16 | heading/body split removed; 74-line body block |
| `metabolic.pdf` | 10 | 19 | heading/body split removed; 11-line body block |
| `pad.pdf` | 12 | 17 | heading/body split removed; 43-line body block |
| `periodontitis.pdf` | 12 | 5 | heading/body split removed; 35-line body block |
| `stroke.pdf` | 12 | 17 | heading/body split removed; 37-line body block |

Totals: 22 source groups in 21 PDFs, comprising 16 removed splits and six role
changes. Canonical block count changes from 4,674 to 4,658.

## Prose and downstream changes

- `Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf`, triggered on PDF page 9: 215 prose lines added and 191 removed; prose blocks 20 -> 13.
- `hypertension.pdf`, triggered on PDF page 8: 196 prose lines added and 201 removed; prose blocks 11 -> 14.
- Changed derived artifacts: `paper_markdown.md` and `paper_sections.json` in
  two PDFs; `paper_variable_inventory.json` in 20; `paper_references.json` and
  `paper_style_profile.json` in two each; `paper_visual_inventory.json` in one;
  and two Science-paper table contexts.
- All 1,350 bibliography entries are identical. All extraction, table-region,
  footnote, normalized-table, table-definition, and parsed-table artifacts are
  identical apart from generated quality-report timestamps.

All block IDs and source-line ownership are unique; prose/entity/residual
ownership is disjoint and complete; block-layout placement coverage is exact.
