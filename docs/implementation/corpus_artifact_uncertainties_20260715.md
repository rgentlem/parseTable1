# Corpus Artifact Gaps and Uncertainties

Status: deferred review inventory.

This note records everything missed, incomplete, or deliberately left uncertain
in the retained 28-PDF run:

```text
outputs/testpapers_batch_phase_k_step5_guarded_final_20260715
```

It is not approval to change parser logic. Each prospective correction still
requires inspection of the earliest affected artifact and the parser-logic
approval report required by `AGENTS.md`.

## Counting boundary

The corpus has 91 physical table fragments and 78 resolved logical tables. The
difference is exactly 13 accepted continuation integrations. There are
therefore 78 processing statuses but 91 source-fragment quality reports. These
count differences are expected and are not missing output.

The older continuation review artifacts cover only a narrower subset: 9 column
checks, 6 groups, 6 merged Table 1 records, and 6 continued-variable
integrations. The canonical result is the 13 integrations in
`resolved_tables.json`; the smaller review counts are not rejected canonical
tables.

## Extraction and physical-geometry uncertainties

### Papers with no extracted target table

Both papers produced complete paper-level artifacts but no physical table
object. Review is needed only if either paper is expected to contain an
in-scope extractable table.

- `An atlas of exposome–phenome associations in health and disease risk.pdf`
- `Uses of NHANES Biomarker Data for Chemical Risk Assessment- Trends,
  Challenges, and Opportunities.pdf`

### Rotated marker geometry is unsupported

All 17 rotated table fragments explicitly report
`unsupported_coordinate_frame:paper_text_orientation_group`. They produce no
`CellTextAnnotation` records, so superscript, subscript, and inline-marker
coverage is currently limited to the 74 upright tables. The affected sources
are:

- `Journal of Periodontology - 2015 - Eke - Update on Prevalence of
  Periodontitis in Adults in the United States  NHANES 2009.pdf`, PDF pages
  5–8, printed Tables 1–2.
- `periodontis2.pdf`, PDF pages 11–19, printed Tables 1–5 and their continuation
  fragments.
- `Ethnic Differences in the Relationship Between Insulin Sensitivity and
  Insulin Response.pdf`, PDF page 6, printed Table 1.
- `Helicobacter pylori infection in the United States beyond NHANES- a scoping
  review of seroprevalence estimates by racial and ethnic groups.pdf`, PDF
  pages 6–8, apparently fragments of printed Table 1.

The existing focused implementation note is
`docs/implementation/rotated_cell_text_annotations_implementation_plan.md`.

### Header candidates that remain uncertain

- Forty-seven blank-leaf concerns remain. Thirty-four are the ordinary blank
  stub leaf at column 0; 13 occur in non-stub leaves and have not been
  individually accepted as intentional.
- `periodontis2.pdf`, PDF page 19, printed Table 5 has one
  `unresolved_upper_header_run` and two unreferenced header-evidence records.
- `mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older
  Adults- NHANES 2007–2017.pdf`, PDF page 10, printed Table 5 has two markers
  whose exact character alignment was insufficient for safe removal. Their
  glyphs correctly remain in `base_text`, with
  `marker_base_text_retained_without_exact_alignment` diagnostics.
- One `periodontis2.pdf` continuation fragment on PDF page 14 inherits eight
  otherwise blank continuation leaf labels. The inheritance is explicit and
  diagnostic rather than a rebuilt schema.

### Boundary alternatives and deliberately unowned rows

- Forty-four tables expose more than one header/body boundary candidate.
- Seventeen regions selected one body interval from competing geometric
  models; two selected by explicit boundary evidence.
- Seventeen rotated proposals also report unsupported row-geometry frames.
- Seven physical rows remain `unknown` rather than being forced into the table:
  - `(Continued from previous page)` in the Helicobacter pylori PDF on PDF
    pages 7 and 8.
  - `(Continued)` in `Science-Advanaced-Planetary Health Diet and risk of
    mortality and chronic diseases- Results from US NHANES, UK Biobank, and a
    meta-analysis.pdf`, PDF page 4; the printed table number was not recovered.
  - Two repeated caption rows for printed Table 3 on PDF page 15 and two for
    printed Table 4 on PDF page 17 of `periodontis2.pdf`.

These rows are preserved as uncertain non-body material. One separate trailing
`Continued` row was correctly removed from printed Table 1 on PDF page 5 of
`Asthma prevalence among United States population insights from NHANES data
analysis.pdf` and retained in `metadata.trailing_non_table_rows`.

## Continuation and visual-identity uncertainties

Four resolved table objects have no corresponding table record in
`paper_visual_inventory.json`:

- `Ethnic Differences in the Relationship Between Insulin Sensitivity and
  Insulin Response.pdf`, PDF page 6, printed Table 1. The extracted label is
  malformed as `Table 1d`.
- Three fragments from `Helicobacter pylori infection in the United States
  beyond NHANES- a scoping review of seroprevalence estimates by racial and
  ethnic groups.pdf`, PDF pages 6–8. The terminal fragment carries printed
  Table 1, while the earlier fragments have no recovered table number. They
  appear likely to share one visual identity but currently remain three
  resolved singleton tables.

The visual inventory contains only 27 figure records while prose scanning finds
360 figure references. Of 667 total visual references, 429 are unresolved: 301
figure references and 128 table references. Twenty-three papers have at least
one unresolved visual reference. This is primarily incomplete visual/caption
inventory coverage, not evidence that physical table cells are wrong.

Five inventoried visuals have no matching prose reference:

- Figures 3 and 4 in `Role of Estimated Glucose Disposal Rate in Staging and
  Death Risk of Cardiovascular-Kidney-Metabolic Syndrome- Insights from NHANES
  1999-2018.pdf`; their PDF page was not recovered in the visual record.
- `cardiovascular.pdf`, PDF page 6, printed Table 2.
- `mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older
  Adults- NHANES 2007–2017.pdf`, PDF page 6, printed Table 2 and PDF page 8,
  printed Table 3.

Two additional figure records are explicitly supplementary-exempt, not missed
references.

Fifteen visual records carry DOI values. Other positioned DOI lines were
deliberately left unassigned when they did not satisfy the exact standalone
visual-object suffix and caption-adjacency requirements.

## Footnote and bibliography uncertainties

The 433 upright cell annotations partition exactly into 400 promoted footnote
anchors, 30 mathematical or unit suppressions, and 3 subscript suppressions.
Of the 400 links, 387 resolve and 13 remain unresolved.

All 13 unresolved links are numeric table-cell markers in `NutritionEx.pdf`:

- PDF page 6, printed Table 1: one marker attached to `p-value`.
- PDF page 7, printed Tables 2–3: twelve markers attached to `OR` or `95%CI`.

They are explicitly diagnosed as possible bibliography references and remain
available to the bibliography artifact. The bibliography independently has 13
table-cell mentions and resolves all 13, so these should not be turned into
local footnotes without direct local-definition evidence.

## Downstream semantic uncertainty

Geometry completion does not imply complete semantic interpretation:

- 19 of 78 table profiles have family `unknown`.
- 9 of 78 paper-table inventory records have category `unknown`.
- 50 of 877 variables have type `unknown`.
- 632 of 13,855 parsed value components have kind `unknown`.
- 62 of 78 logical tables have processing status `rescued`; 20 of those carry
  at least one error-level quality diagnostic. No logical table failed.
- Across 91 source-fragment quality reports there are 593 warnings, 73 errors,
  and 64 informational diagnostics.

The largest diagnostic classes are `unknown_row` (398),
`missing_label_with_values` (91), `parent_without_levels` (64),
`suspicious_header_row_count` (31), `multiple_quality_warnings` (27),
`low_value_pattern_recognition` (24), and
`non_numeric_statistical_column` (21). These are downstream semantic/value
quality findings and are not, by themselves, authority to rewrite extraction.

Particularly weak semantic outputs include:

- `Association between metabolic score for insulin resistance (METS-IR) and
  hypertension- a cross-sectional study based on NHANES 2007–2018.pdf`, PDF
  pages 7–8, printed Tables 2–4.
- `Helicobacter pylori infection in the United States beyond NHANES- a scoping
  review of seroprevalence estimates by racial and ethnic groups.pdf`, PDF
  pages 6–8, printed Table 1.
- `mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older
  Adults- NHANES 2007–2017.pdf`, PDF page 4, printed Table 1.
- `The prevalence and mortality risks of PRISm and COPD in the United States
  from NHANES 2007–2012.pdf`, PDF page 5, printed Table 1.
- `An environment-wide association study (EWAS) on type 2 diabetes
  mellitus.pdf`, PDF page 7, printed Table 1, which has the lowest final parsed
  table confidence at 0.549.

Any future semantic work should first confirm that the physical cells, row
ownership, leaf paths, and continuation identity are already correct, then
change the earliest genuinely weak semantic stage rather than patching final
values.
