# TableDefinition Implementation Plan

This document guides the next phase: building a value-free semantic stage that defines the rows and columns of a Table 1 in a form suitable for downstream SQL-query generation.

## Goal

Implement `TableDefinition` as the stage between `NormalizedTable` and `ParsedTable`.

This phase should answer:

- which variables define the table rows
- which of those variables are categorical
- what the categorical levels are
- what the columns represent
- what grouping or stratifying variable likely defines the columns

This phase should not extract or parse the printed values.

The expected downstream use is:

- `TableDefinition` identifies the paper-facing row and column semantics
- an R-based intermediary can use that structure to query the database
- existing R visualization tooling can then help inspect matched variables, categories, and retrieved results

## Pipeline Position

Target pipeline:

```text
PDF -> ExtractedTable -> NormalizedTable -> TableDefinition -> ParsedTable
```

For now, `parse` should continue to run once and write all available artifacts. After this phase, that should include `table_definitions.json`.

## Main Output

Add a new canonical schema:

- `table1_parser/schemas/table_definition.py`

and a new persisted file:

- `outputs/papers/<paper_stem>/table_definitions.json`

The file should be a JSON array of direct `TableDefinition.model_dump(mode="json")` payloads.

## Required Semantics

Each `TableDefinition` should preserve:

- `table_id`
- `title`
- `caption`
- row variable definitions
- categorical levels where present
- column definitions
- grouping hints
- confidence fields
- notes

Each row variable should preserve both:

- the printed label from the paper
- a normalized label suitable for matching to database fields
- for variable rows, that matching label may strip summary-style and unit decorations such as `n (%)`, `mean (SD)`, or parenthetical units

Each categorical level should preserve both:

- the printed level label
- a normalized label suitable for matching to coded category values
- that level matching label must still preserve meaning-bearing comparator and range syntax such as `< 1.3`, `1.3-1.8`, `>1.8`, `<High school`, and `>High school`

Each column should preserve both:

- the printed column label
- a normalized label suitable for matching to a database grouping variable
- grouped-column level metadata when a table has subgroup columns
- distinct statistic-column semantics when multiple trailing test columns are present

## Scope for This Phase

Implement:

1. Minimal typed schema for `TableDefinition`
2. Deterministic row-structure inference from `NormalizedTable`
3. Deterministic column inference from normalized headers
4. Validation of the `TableDefinition`
5. CLI export from `table1-parser parse`
6. Tests and docs

Do not implement:

- value extraction
- `ParsedTable`
- LLM refinement
- database matching itself
- SQL generation itself

This phase should prepare for those later steps by emitting a structure that is easy for an R workflow to consume.

## Recommended Modules

- `table1_parser/schemas/table_definition.py`
- `table1_parser/heuristics/table_definition_rows.py`
- `table1_parser/heuristics/table_definition_columns.py`
- `table1_parser/heuristics/table_definition_builder.py`
- `table1_parser/validation/table_definition.py`

If LLM refinement is added in this phase, keep it separate from deterministic heuristics.

## Deterministic Row Inference

Use `NormalizedTable` signals first:

- `header_rows`
- `body_rows`
- `row_views`
- cleaned rows
- indentation information

Infer at least:

- variable rows
- level rows
- section/header-like rows inside the body
- count rows such as `n`

Row-name normalization should differ by row role:

- variable-row matching names may simplify paper labels for search and downstream matching
- level-row matching names must not collapse semantically distinct thresholds, ranges, or comparator-prefixed categories

Expected row outcomes:

- continuous variable with no levels
- categorical variable with one or more levels
- binary variable represented as levels or a single summary row
- unknown/ambiguous variable

## Deterministic Column Inference

Use normalized header rows and column text to infer:

- `overall`
- subgroup column
- comparison group column
- `p_value`
- `smd`
- `unknown`

Column inference should first build a general grouping analysis that partitions columns into:

- the row-label column
- any overall/full-sample column
- grouped data columns
- trailing statistic/test columns

Also try to infer the grouping concept, such as:

- disease status
- exposure category
- case/control status
- quartile group

The output should carry, when inferable:

- a grouping variable label and normalized name
- the number of grouped columns
- a paper-facing and normalized grouped-column level for each grouped column
- a left-to-right group order
- a statistic subtype for trailing test columns such as `p_value`, `p_trend`, or `smd`

The result should support downstream matching to the database field that created the table columns.

That downstream matching layer may live in R, so the output should stay simple, explicit, and JSON-first.

## LLM Role in the Next Phase

LLM use is expected to be valuable, but it is not part of this implementation phase.

The deterministic `TableDefinition` built in this phase should become the baseline result. In the next phase, an optional LLM refinement layer can be added on top of that baseline and turned on or off for evaluation.

Target future flow:

```text
NormalizedTable -> deterministic TableDefinition -> optional LLM-refined TableDefinition -> validation
```

When added, LLM use should be optional and only for semantic ambiguity.

Use the LLM to refine:

- whether a row is a parent variable or a section label
- whether nearby rows are categorical levels under a parent variable
- what the column grouping concept most likely is
- messy multi-row header interpretation

Do not use the LLM to:

- invent rows
- invent columns
- infer values
- replace deterministic extraction or normalization

The future implementation should make it easy to compare:

- deterministic-only output
- deterministic + LLM-refined output

so the project can assess whether the LLM adds useful signal.

## Validation Requirements

Validation should ensure:

- all referenced `row_idx` values exist
- all referenced `col_idx` values exist
- level rows belong to a valid parent variable
- variable row spans are coherent
- column roles are internally consistent
- LLM refinement does not introduce rows or columns absent from the normalized table

## CLI Requirements

Update `table1-parser parse` so it writes:

- `extracted_tables.json`
- `normalized_tables.json`
- `table_definitions.json`

from one pipeline run.

`extract` and `normalize` should remain available as stage-specific commands.

## Test Requirements

Add tests for:

- `TableDefinition` schema validation
- deterministic row-variable grouping
- categorical level extraction
- column-role inference
- grouping-variable hints
- validation failures for bad row/column references
- `parse` writing `table_definitions.json`

Use the sample papers in `testpapers/` where helpful.

## Success Criteria

This phase is successful when a user can run:

```bash
table1-parser parse path/to/paper.pdf
```

and obtain a `table_definitions.json` file that is suitable for a downstream tool to:

- identify candidate database fields for row variables
- identify candidate coded values for categorical levels
- identify the database field likely used to construct the table columns
- hand the result to an R-based database-query and visualization workflow

without relying on table cell values.
