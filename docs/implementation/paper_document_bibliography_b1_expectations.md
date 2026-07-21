# B1 Bibliography Expectations

This is the inspection baseline for B2/B3. It is not exact block segmentation.
PDF pages are one-based. Numbered terminal values are source evidence; no exact
count is asserted for unnumbered bibliographies. The current 1,350 parsed
entries are regression output only.

## Corpus inventory

| Source PDF | Expected PDF pages | Numbering expectation | Visually checked form |
|---|---:|---|---|
| `An atlas of exposome–phenome associations in health and disease risk.pdf` | 9–10 and 14 | two `References` regions; 1–42, then 43–54 | two columns; separated regions |
| `An environment-wide association study (EWAS) on type 2 diabetes mellitus.pdf` | 9–10 | 1–59 | — |
| `Association between anthropometric indices and chronic kidney disease- Insights from NHANES 2009–2018.pdf` | 17–20 | 1–43 | single column |
| `Association between metabolic score for insulin resistance (METS-IR) and hypertension- a cross-sectional study based on NHANES 2007–2018.pdf` | 9–10 | 1–33 | — |
| `Asthma prevalence among United States population insights from NHANES data analysis.pdf` | 9–10 | 1–62 | — |
| `Ethnic Differences in the Relationship Between Insulin Sensitivity and Insulin Response.pdf` | 7–8 | 1–44 | three columns |
| `GOLD BioAge and depression- Associations with mortality among depressed NHANES participants (2005–2018).pdf` | 7–8 | unnumbered; no exact count asserted | two columns; partial-page start |
| `Helicobacter pylori infection in the United States beyond NHANES- a scoping review of seroprevalence estimates by racial and ethnic groups.pdf` | 12–13 | 1–80 | two columns |
| `Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009.pdf` | 11–12 | 1–24 | — |
| `Lead exposure as a contributor to the Black–White racial disparity in blood pressure- evidence from NHANES 1988–1994 and 2017–2020.pdf` | 9–10 | 1–35 | — |
| `NutritionEx.pdf` | 10–11 | 1–41 | — |
| `Role of Estimated Glucose Disposal Rate in Staging and Death Risk of Cardiovascular-Kidney-Metabolic Syndrome- Insights from NHANES 1999-2018.pdf` | 10 | 1–33 | two columns |
| `Sarcopenia.pdf` | 11–12 | 1–61 | — |
| `Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf` | 9–10 | `REFERENCES AND NOTES`; 1–58 | two columns |
| `Systemic inflammation markers and the prevalence of hypertension- A NHANES cross-sectional study.pdf` | 10–11 | 1–37 | — |
| `The prevalence and mortality risks of PRISm and COPD in the United States from NHANES 2007–2012.pdf` | 10–11 | 1–68 | — |
| `Uses of NHANES Biomarker Data for Chemical Risk Assessment- Trends, Challenges, and Opportunities.pdf` | 7–9 | unnumbered; no exact count asserted | three columns; partial-page start |
| `cardiovascular.pdf` | 9–10 | 1–36 | — |
| `cobaltpaper.pdf` | 6–7 | 1–49 | two columns; partial-page start |
| `fld.pdf` | 11–12 | 1–39 | — |
| `gallstones.pdf` | 12–13 | 1–73 | — |
| `hypertension.pdf` | 8–9 | 1–54 | two columns |
| `mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017.pdf` | 11–13 | 1–40 | — |
| `metabolic.pdf` | 10–12 | 1–52 | two columns; partial-page start/end |
| `pad.pdf` | 12–13 | 1–47 | — |
| `periodontis2.pdf` | 8–9 | 1–20 | single column |
| `periodontitis.pdf` | 12 | 1–38 | — |
| `stroke.pdf` | 12–14 | 1–82 | — |

## Current regression mismatches

- `An atlas of exposome–phenome associations in health and disease risk.pdf`:
  current output stops at reference 42 on PDF page 10; the second `References`
  region on PDF page 14 contains references 43–54.
- `Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf`:
  current output has 47 entries, numbered 1–46 plus one unnumbered entry; the
  source has references 1–58 on PDF pages 9–10.

## B2/B3 acceptance use

- B2 must find every listed region without claiming other content on a partial
  page.
- B3 must reproduce explicit numbered sequences. Unnumbered entry counts and
  exact block boundaries must come from canonical block evidence and fail
  closed when unresolved.
- Extraction masks must derive from accepted bibliography ownership and cover
  no other page content.
