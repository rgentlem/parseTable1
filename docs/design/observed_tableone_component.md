# Observed TableOne Component Design

This document defines an R-first component for representing a parsed Table 1 as an observed, print-canonical semantic object.

The component exists to support two related goals:

- preserve the semantic structure of a printed Table 1 in a form convenient for R workflows
- reconstruct a `tableone`-like summary object from parser JSON outputs without pretending that the original subject-level data can be recovered

## Core Decision

For this component, the printed table is canonical.

This is different from the original `tableone` package workflow.

In `tableone`, the canonical source is usually a subject-level dataset plus arguments such as:

- `vars`
- `strata`
- `factorVars`
- `showAllLevels`
- `nonnormal`
- `exact`

In `parseTable1`, none of those inputs are reliably available.

What we reliably have is:

- the printed table grid
- the parser-native column-header schema, including multicolumn header groups
- row and column semantics inferred from that printed table
- parsed cell values extracted from that printed table

The R-side component must therefore be designed around observed output, not guessed original inputs.

## Relationship To Existing Pipeline

The existing pipeline remains:

```text
PDF -> ExtractedTable -> NormalizedTable -> ColumnHeaderSchema -> TableDefinition -> ParsedTable
```

The proposed R-side component is downstream of the JSON artifacts written by the parser.

Recommended conceptual flow:

```text
column_header_schemas.json + table_definitions.json + parsed_tables.json (+ normalized_tables.json when useful)
-> ObservedTableOne
```

This keeps the Python parser and the R reconstruction layer separate.

## Main Purpose

`ObservedTableOne` should be the R-side semantic container for one printed Table 1.

It should:

- preserve printed row meaning
- preserve printed column meaning
- separate continuous summaries from categorical summaries
- preserve printed statistics columns such as p-values and SMDs
- preserve only metadata that is supported by the observed printed table or safely inferred from it

It should not:

- reconstruct the original subject-level dataframe
- claim knowledge of unprinted factor levels
- claim knowledge of original `tableone` call arguments
- invent display settings that were not visible in the printed table

## Design Principles

### Print-canonical

All semantics must be grounded in what was printed.

If a detail was not printed and cannot be safely inferred from parser outputs, it should remain unknown.

### JSON-first input

The component should consume the parser's JSON artifacts, not internal Python objects.

JSON is the transport layer, not the semantic model.
The artifacts should therefore be shaped so they can be interpreted unambiguously in both Python and R.

Primary inputs:

- `table_definitions.json`
- `parsed_tables.json`

Secondary optional input:

- `normalized_tables.json`

### R-first implementation

All code for this component should be written in R.

The long-term goal is an R package that reads parser outputs and constructs inspection- and export-ready R objects.

### Observed metadata only

Metadata must describe what was observed in the printed table, not what might have been used to generate it originally.

### Separate summary families

Continuous summaries, categorical summaries, and statistics columns should remain structurally separate.

This mirrors the useful distinction in `tableone`, while staying grounded in the printed table.

## Proposed Object

Working R class name:

- `ObservedTableOne`

Recommended top-level structure:

- `table_id`
- `title`
- `caption`
- `ContTable`
- `CatTable`
- `MetaData`
- `metadata`
- `columns`
- `continuous`
- `categorical`
- `statistics`
- `provenance`
- `notes`
- `overall_confidence`

This should be implemented as an S3 object backed by a named list.
`ContTable`, `CatTable`, and `MetaData` should be the tableone-style access
surface. The lower-case fields may remain as compatibility aliases while the
object matures.

## `metadata`

`metadata` should capture table-level and variable-level information that is supported by the printed table.

Recommended fields:

- `vars`
- `logiFactors`
- `varFactors`
- `varNumerics`
- `percentMissing`
- `varLabels`
- `variable_order`
- `variables`
- `grouping_label`
- `grouping_name`
- `overall_column_present`
- `statistic_columns`
- `source_json`

Each variable metadata entry should preserve:

- `variable_name`
- `variable_label`
- `variable_type`
- `row_start`
- `row_end`
- `summary_style_hint`
- `units_hint`
- `printed_levels`
- `confidence`

### What belongs in `printed_levels`

Only levels that were actually printed should be stored.

Each printed level should preserve:

- `level_name`
- `level_label`
- `row_idx`
- `confidence`

### What should not be modeled as canonical metadata

Do not store these as though they were known source truth:

- original `factorVars`
- original `showAllLevels`
- original `cramVars`
- original `exact`
- original `nonnormal`
- original factor reference levels when not printed
- unprinted levels dropped from the printed table

If later heuristics suggest such information, that can be stored only as optional evidence or notes, not as canonical metadata.

## `columns`

`columns` should describe the printed non-label columns in left-to-right order.
The column axis should come from `ColumnHeaderSchema` or from
`TableDefinition.column_definition` records that were built from that schema.
Observed-table code should not compare or interpret columns by reconstructing
header text locally.

Each column entry should preserve:

- `col_idx`
- `column_name`
- `column_label`
- `header_leaf_id`
- `header_leaf_label`
- `header_group_ids`
- `header_group_labels`
- `header_path`
- `role`
- `grouping_variable_hint`
- `group_level_label`
- `group_level_name`
- `group_order`
- `statistic_subtype`
- `confidence`

For multirow printed headers, `column_label` is the leaf label. Parent
headers should be read from `header_path` on each column and from
`MetaData$column_header_spans`, which mirrors
`TableDefinition.column_definition.header_spans`. R-side observed-table code
should use those stored spans for tableone-style spanners rather than
reconstructing hierarchy by splitting flattened labels.

Column roles should remain close to the current parser semantics:

- `overall`
- `group`
- `comparison_group`
- `p_value`
- `smd`
- `unknown`

## `continuous`

`continuous` should contain only variables that are represented as continuous summaries in the printed table.

Recommended structure:

- `variables`
- `values`

Each continuous value entry should preserve:

- `variable_name`
- `row_idx`
- `column_name`
- `col_idx`
- `raw_value`
- `summary_style_hint`
- parsed numeric slots supported by the current JSON
- `confidence`

At present, the parser only guarantees two numeric slots:

- `parsed_numeric`
- `parsed_secondary_numeric`

This is enough for `mean (SD)` and many `n (%)`-style cells, but not enough for full `median`, `p25`, `p75`, `min`, `max` recovery. The R component should preserve the raw value and tolerate incomplete numeric detail.

## `categorical`

`categorical` should contain variables with printed level rows.

Recommended structure:

- `variables`
- `values`

Each categorical value entry should preserve:

- `variable_name`
- `level_label`
- `row_idx`
- `column_name`
- `col_idx`
- `raw_value`
- parsed count when available
- parsed percent when available
- `confidence`

No unprinted levels should be invented.

## `statistics`

`statistics` should preserve printed statistic columns separately from data columns.

Typical entries:

- p-values
- p for trend
- SMD

Each entry should preserve:

- `variable_name`
- `row_idx`
- `column_name`
- `col_idx`
- `raw_value`
- `statistic_type`
- parsed numeric value when available
- `confidence`

## `provenance`

The component should record where its data came from.

Recommended fields:

- `table_definition_source`
- `parsed_table_source`
- `normalized_table_source`
- `table_index`
- `builder_version`

This is especially useful when comparing repeated parser runs.

## Mapping From Existing JSON

Primary mapping:

- `table_definitions.json`
  - row semantics
  - level semantics
  - column semantics
  - grouping hints
  - summary-style hints
- `parsed_tables.json`
  - printed values
  - long-format value records
  - parsed numeric slots

Optional support from `normalized_tables.json`:

- extra row-label context
- extra header context
- potential future support for observed missingness rows or header `n=` strings

## Non-Goals

This component is not trying to:

- recreate `CreateTableOne()` inputs
- infer original factor coding
- reconstruct subject-level observations
- correct parser mistakes by silently inventing table content

It is a semantic container for the printed artifact.

## Why This Fits The Repository

This design aligns with the current project goals:

- it keeps extraction, normalization, semantic interpretation, and downstream use separate
- it relies on persisted JSON artifacts rather than hidden in-memory coupling
- it supports an R-based downstream workflow without moving parser logic into R prematurely

It also fits the current state of the repo:

- Python remains the parser
- R becomes the consumer of parser JSON and the home for downstream semantic tooling

## Future Extensions

Likely future additions:

- richer continuous summary parsing in R for `median [IQR]` and `median [range]`
- R printers for `ObservedTableOne`
- comparison helpers for multiple parser runs
- optional coercion from `ObservedTableOne` into a `tableone`-like display object

Those should be layered on top of this observed-table contract, not mixed into the parser core.
