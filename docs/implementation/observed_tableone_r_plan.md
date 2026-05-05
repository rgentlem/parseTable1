# ObservedTableOne R Implementation Plan

This document describes the implementation plan for an R-first component that consumes parser JSON artifacts and constructs an observed, print-canonical semantic object for one Table 1.

The target object is defined in:

- `docs/design/observed_tableone_component.md`

## Goal

Implement an R-side builder that reads:

- `table_definitions.json`
- `parsed_tables.json`
- optionally `normalized_tables.json`

and returns an `ObservedTableOne` object for one table.

The implementation should live in the repository's `R/` directory and be written as package-oriented reusable functions rather than only as ad hoc scripts.

## Scope

Implement:

1. shared JSON-reading helpers in R
2. an `ObservedTableOne` S3 constructor
3. validation for the constructed object
4. a builder from one `TableDefinition` + one `ParsedTable`
5. a convenience builder from one paper output directory
6. a compact print method for interactive inspection
7. basic documentation in `docs/` and small package-oriented R files

Do not implement yet:

- subject-level data reconstruction
- exact recreation of `tableone::CreateTableOne()` inputs
- a full R package release process
- a full coercion into the upstream `tableone` internal class structure
- advanced continuous-summary repair beyond what current JSON supports

## Input Contract

The implementation should rely on saved JSON files, not Python imports.

Required input files:

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

### Constructor and validator

Recommended core object functions:

- `new_observed_table_one(...)`
- `validate_observed_table_one(x)`
- `print.ObservedTableOne(x, ...)`

The constructor should build a named list and assign class `ObservedTableOne`.
It should expose tableone-style `ContTable`, `CatTable`, and `MetaData` fields,
with the existing lower-case fields retained as compatibility aliases.

The validator should check:

- presence of `table_id`
- list-shaped `metadata`
- list-shaped `columns`
- list-shaped `continuous`
- list-shaped `categorical`
- list-shaped `statistics`
- coherent variable ordering

### Builders

Recommended public builders:

- `build_observed_table_one(table_definition, parsed_table, normalized_table = NULL, provenance = NULL)`
- `build_observed_table_one_from_paper_dir(paper_dir, table_index = 0L)`

Recommended internal helpers:

- `build_observed_metadata(table_definition, parsed_table)`
- `build_observed_columns(table_definition, parsed_table)`
- `build_observed_continuous(table_definition, parsed_table)`
- `build_observed_categorical(table_definition, parsed_table)`
- `build_observed_statistics(parsed_table, columns)`

## Detailed Assembly Rules

### Metadata assembly

Take row and semantic information from `table_definition`.

Populate:

- `vars`
- `logiFactors`
- `varFactors`
- `varNumerics`
- `percentMissing`
- `varLabels`
- variable order from `table_definition$variables`
- variable labels and names from the same
- row spans from `row_start` and `row_end`
- variable type from `variable_type`
- summary style and units from `summary_style_hint` and `units_hint`
- printed levels from `levels`
- grouping info from `column_definition`, which must be derived from `ColumnHeaderSchema`

Do not synthesize:

- unprinted levels
- upstream `factorVars`
- original display settings

### Column assembly

Prefer `table_definition$column_definition$columns` as the semantic source, and
require that those columns come from the parser's `ColumnHeaderSchema` path.
Observed-table code should not rebuild column meaning from local header text.

If a column exists in `parsed_table$columns` but not in the definition, preserve it as best-effort fallback.

Columns should remain in left-to-right printed order.

### Continuous assembly

Use variables whose `variable_type` is `continuous` or whose printed row is currently represented as a single non-level row.

Collect matching `parsed_table$values` records where:

- `level_label` is `NULL`
- column is not a statistic column

Preserve:

- raw cell text
- parsed numeric slots
- row and column coordinates
- summary style hint from `table_definition`

### Categorical assembly

Use variables with printed `levels`.

Collect matching `parsed_table$values` records keyed by:

- `variable_name`
- `level_label`
- `row_idx`
- `col_idx`

Preserve only printed levels.

### Statistics assembly

Use `parsed_table$columns` and `table_definition$column_definition$columns` to identify statistic columns such as:

- `p_value`
- `smd`

Collect value records for those columns into a separate `statistics` block.

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
- package-oriented R helpers for JSON loading and `ObservedTableOne` construction

This is enough to establish the R-side component without changing the Python parser or its JSON schema.

Initial package-oriented repository files that should now exist:

- `DESCRIPTION`
- `NAMESPACE`
- `.Rbuildignore`

These are intentionally minimal and should expand as the R package becomes less provisional.
