# parseTable1 R S7 Inspection Plan

This document describes the implementation plan for an R-first component that
consumes parser JSON artifacts and constructs S7 inspection objects for resolved
Table 1-style outputs.

The target object is defined in:

- `docs/design/observed_tableone_component.md`

## Goal

Implement an R-side package layer that reads parser JSON artifacts and returns
S7 objects for paper- and table-level inspection. The R layer consumes JSON only;
it must not parse PDFs, repair extraction, or reinterpret partial artifacts as
complete tables.

Required table-level inputs are:

- `resolved_tables.json`
- `table_definitions.json`
- `parsed_tables.json`

Optional inputs such as `normalized_tables.json`, `paper_footnotes.json`, and
`table_processing_status.json` may be retained as source artifacts or
diagnostic context.

The implementation should live in the repository's `R/` directory and be written as package-oriented reusable functions rather than only as ad hoc scripts.

## Scope

Implement:

1. shared JSON-reading helpers in R
2. S7 classes for one paper output directory and one resolved logical table
3. fail-closed validation for required JSON artifacts
4. one base-R `data.frame` row per resolved column
5. explicit multicolumn-header group views derived from header spans
6. row, value, and diagnostic accessors
7. package documentation and a vignette

Do not implement yet:

- subject-level data reconstruction
- exact recreation of `tableone::CreateTableOne()` inputs
- a full R package release process
- a full coercion into the upstream `tableone` internal class structure
- advanced continuous-summary repair beyond what current JSON supports

## Input Contract

The implementation should rely on saved JSON files, not Python imports.

Required input files:

- `outputs/papers/<paper_stem>/resolved_tables.json`
- `outputs/papers/<paper_stem>/table_definitions.json`
- `outputs/papers/<paper_stem>/parsed_tables.json`

Optional input file:

- `outputs/papers/<paper_stem>/normalized_tables.json`

Builder code should match tables by:

1. `table_index` when called on a paper directory
2. `table_id` when explicit objects are already loaded

## Recommended R File Layout

Initial package-oriented file layout inside `R/`:

- `R/pt1_json_io.R`
  shared JSON and list helper functions
- `R/observed_table_one.R`
  constructor, validator, builder, and print method

Later likely additions:

- `R/observed_table_one_compare.R`
- `R/observed_table_one_print.R`
- `R/observed_table_one_stats.R`

## Core Functions

### JSON I/O helpers

Recommended reusable helpers:

- `pt1_read_json_file(path)`
- `pt1_read_optional_json(path)`
- `pt1_unwrap_trace_payload(x)`
- `pt1_unwrap_table_array(x)`
- `pt1_load_json_array(path)`

These should be package-safe and should not execute script logic on import.

### Constructor And Validator

Recommended core object functions:

- `read_pt1_paper(paper_dir)`
- `pt1_table(x, table_index = 0L)`
- `validate_pt1_table(x)`
- `pt1_column_groups(x)`
- `pt1_columns(x)`
- `pt1_rows(x)`
- `pt1_values(x)`
- `pt1_diagnostics(x)`

The constructors should return S7 objects. Stored tabular views should be base R
`data.frame` objects; do not introduce tidyverse dependencies.

The table validator should check:

- presence of `table_id`
- positive resolved `n_rows` and `n_cols`
- complete `header_spans`
- exactly one leaf span for every resolved column
- one row in `columns` for every resolved column
- base R `data.frame` views for groups, columns, rows, values, and diagnostics

## Detailed Assembly Rules

### Row Assembly

Take row and semantic information from `table_definition$variables`.

The row view should preserve:

- variable rows
- categorical level rows
- row indices
- parent-variable links for levels
- variable type and printed label

Do not synthesize unprinted levels, original `factorVars`, or source-data
display settings.

### Column assembly

Use `table_definition$column_definition$header_spans` as the structural source.
The R layer must construct:

- one row per multicolumn group span
- one row per resolved leaf column, including the row-label column

Each leaf column record should preserve its ancestor group path. If every
resolved column does not have exactly one leaf span, table construction should
fail with a structured diagnostic.

### Value Assembly

Take values from `parsed_tables.json`. The value view should remain long and
cell-oriented:

- `row_idx`
- `col_idx`
- `variable_name`
- `level_label`
- `raw_value`
- typed component summary from parser value components
- confidence

Statistics such as p-values remain ordinary value rows tied to statistic
columns; a later view can filter them by `pt1_columns(x)$measure_kind` or
column role.

## Handling Current Parser Limitations

The current JSON artifacts do not fully reconstruct all `tableone` numeric internals.

Known limitations to tolerate:

- only two numeric value slots are currently preserved
- some variables that look categorical in print may still be typed imperfectly upstream
- missingness is not always present as a first-class parsed field
- sample sizes may appear as a printed row rather than column metadata

The R code should therefore:

- preserve raw strings
- preserve parser confidence
- avoid inventing unavailable structure
- keep notes for anything unresolved

## Package Orientation

The R package should remain base R plus narrowly scoped imports such as
`jsonlite` and `S7`. Do not use tidyverse packages in the implementation or
vignettes.

Even before a full R package is published, code in `R/` should move toward package style:

- reusable functions only
- no command-line execution in package files
- stable function names
- no hidden dependence on sourcing order

Existing standalone inspection scripts can remain, but new component code should be package-ready.

## Suggested Development Sequence

### Phase 1

- add `pt1_json_io.R`
- add `observed_table_one.R`
- implement constructor and validator
- implement builder from already-loaded lists

### Phase 2

- implement builder from paper output directories
- add compact print method
- test against existing outputs in `outputs/papers/`

### Phase 3

- improve handling of count rows and denominator extraction
- improve support for `median [IQR]` and `median [range]`
- add comparison helpers for repeated parser runs

### Phase 4

- decide whether to coerce into a stricter `tableone`-like R object
- if yes, implement that as a separate adapter layer, not inside the base builder

## Testing Strategy

Near-term smoke testing can be done with `Rscript` against saved parser outputs.

Recommended checks:

- object construction from `outputs/papers/cobaltpaper`
- object construction from `outputs/papers/OPEandRA`
- validation failure on malformed input
- stable ordering of variables and columns
- correct separation of continuous, categorical, and statistic blocks

Later, if an R package structure is formalized, these should move into `tests/testthat/`.

## Documentation Requirements

Keep these docs in sync with implementation:

- `docs/design/observed_tableone_component.md`
- `docs/implementation/observed_tableone_r_plan.md`
- `docs/design/design_index.md`
- `docs/r_visualization.md`

## Initial Repository Change For This Phase

For this phase, the repository should gain:

- one design doc
- one implementation plan
- package-oriented R helpers for JSON loading and `PT1Paper`/`PT1Table` construction

This is enough to establish the R-side component without changing the Python parser or its JSON schema.

Initial package-oriented repository files that should now exist:

- `DESCRIPTION`
- `NAMESPACE`
- `.Rbuildignore`

These are intentionally minimal and should expand as the R package becomes less provisional.
