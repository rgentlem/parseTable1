# Table One Epidemiological Description Model

This document defines the table family that the Table 1 parser and R-side
semantic objects should represent first.

The target is an epidemiological description table: a printed table that
describes the analytic sample, cases, participants, or study population. It is
not a model-results table, assay matrix, generic data table, or figure-like
layout.

## Scope Rule

A table is in scope only when:

- rows describe characteristics of the study population or cases
- columns describe the overall population, population strata, or comparison
  statistics for those strata
- cells contain descriptive summaries of those row characteristics

If rows are model terms, outcomes, regression contrasts, biomarkers measured
across assays, time-series measurements, or arbitrary data matrix entries, the
table should not be represented as this Table One model.

## Core Components

| Component | What it represents |
| --- | --- |
| **Population / denominator** | The analytic sample being described; often includes total N and subgroup N. |
| **Columns** | Usually overall sample plus strata: exposure groups, treatment groups, comparison groups, or case/control status depending on design. |
| **Rows** | Baseline or descriptive variables: demographics, clinical variables, social variables, exposures, potential confounders, effect modifiers, and variables used in the main analysis. |
| **Cells** | Descriptive statistics only: categorical variables as `n (%)`; continuous variables as `mean (SD)` or `median (IQR/range)`; missingness where relevant. |
| **Footnotes** | Denominators, percent convention, missing-data handling, weighting, transformations, units, and definitions of derived variables. |

## Conceptual Shape

The R-side semantic object should start from this shape:

```text
TableOneDescription
  population
  column_axis
  row_axis
  body
  footnotes
  provenance
```

`ObservedTableOne` can be a projection or compatibility surface over this
model, but the conceptual model should remain about the printed
epidemiological description table.

## Population / Denominator

Population records describe who is summarized.

Examples:

- all participants
- cases and controls
- exposed and unexposed groups
- treatment arms
- quartiles or other study-defined strata
- weighted survey population

The denominator may be printed in a title, column header, row, cell, or
footnote. It should be represented explicitly when available rather than
treated only as part of a display string.

## Columns

Columns describe population summaries and table-level statistics.

Common column roles:

- `overall`
- `stratum`
- `case_group`
- `control_group`
- `treatment_group`
- `exposure_group`
- `comparison_statistic`
- `p_value`
- `p_trend`
- `smd`

Column identity should come from `ColumnHeaderSchema` and
`TableDefinition.column_definition`, not from ad hoc string reconstruction in
R.

## Rows

Rows describe characteristics or structure within the description table.

Common row roles:

- `section`
- `sample_size`
- `numeric_variable`
- `categorical_variable`
- `categorical_level`
- `attached_detail`
- `missingness`
- `note_like`
- `unknown`

Rows should preserve the printed label and source row index. Variable and level
records should contain only what was printed or directly supported by parser
artifacts.

For now, Table One variable rows should be understood as two main semantic
types:

- numeric variables
- categorical variables

Numeric variables are usually represented by one dense row. The row label names
the measured quantity, and population-summary columns usually contain
continuous summaries such as `mean (SD)` or `median (IQR/range)`. If a p-value
column is present, the numeric variable row typically contains the p-value.

Categorical variables are usually represented by a parent row followed by one
row per printed category level. The parent row names the category. It often has
a p-value in a p-value column and otherwise has empty population-summary cells.
The level rows contain the observed distribution across population-summary
columns, usually integer counts with percentages. In survey-weighted,
imputed, or otherwise weighted analyses, counts or denominators may be
real-valued rather than integer-valued.

Rows such as `Missing`, `Unknown`, `Not reported`, or similar nonresponse
details are not necessarily separate variables. They usually attach to the
nearest preceding variable or categorical block unless stronger table evidence
shows that they define a standalone characteristic.

## Cells

Cells contain observed descriptive summaries.

Allowed value families:

- `count`
- `percent`
- `count_percent`
- `mean_sd`
- `median_iqr`
- `median_range`
- `p_value`
- `smd`
- `missing`
- `text`
- `unknown`

The stored payload should remain component-native. For example, `34 (45%)`
should store separate `count` and `percent` components while preserving the raw
printed cell.

## Footnotes

Footnotes are part of the table interpretation, not decoration.

They can define:

- denominators
- whether percentages are column, row, weighted, or unweighted percentages
- missing-data conventions
- survey weighting
- transformations
- units
- abbreviations
- derived-variable definitions
- statistical-test definitions

Footnotes should remain linked evidence. They should not rewrite the printed
cell text unless a later, explicit interpretation layer consumes them.

## Validation Direction

Validation should be based on row role plus column role.

Examples:

- `categorical_level` rows in population-summary columns should contain
  `count`, `percent`, or `count_percent`
- `categorical_variable` parent rows should usually have empty
  population-summary cells and may have a p-value
- `numeric_variable` rows in population-summary columns should contain
  `mean_sd`, `median_iqr`, or `median_range`
- `p_value` columns should contain p-values or missing/text placeholders, not
  counts and percentages
- `p_value` cells usually belong on numeric variable rows or categorical parent
  rows, not on every categorical level row
- `section` rows should usually have empty value cells
- sample-size rows should usually contain counts
- `attached_detail` and `missingness` rows should inherit context from the
  nearest compatible preceding variable or categorical block

This keeps validation tied to the epidemiological description model rather
than treating each cell as meaningful without row and column context.
