# Table Definition Scope

This document defines the scope for a new intermediate artifact between `NormalizedTable` and `ParsedTable`.

Working name:

- `TableDefinition`

## Purpose

`TableDefinition` is intended to capture the semantic structure of a Table 1 without including the printed cell values.

It is meant for downstream matching against a known database schema, where the next tool needs to identify:

- which variables appear as rows
- which variables are categorical
- what the categorical levels are
- how the table columns were constructed
- which database variables may correspond to the printed row and column labels

## Position in the Pipeline

Proposed pipeline:

```text
PDF -> ExtractedTable -> NormalizedTable -> TableDefinition -> ParsedTable
```

In this design:

- `NormalizedTable` remains structural and row-oriented
- `TableDefinition` becomes the value-free semantic interpretation
- `ParsedTable` remains the final output with cell-level values

## What `TableDefinition` Should Contain

At minimum:

- `table_id`
- `title`
- `caption`
- row-variable definitions
- categorical levels where present
- column definitions
- grouping/stratification hints
- notes
- confidence fields

For row variables, it should preserve both:

- paper-facing labels
- normalized matching-friendly labels

For categorical variables, it should include:

- parent variable label
- level labels
- source row indices
- level matching names that do not collapse semantically distinct thresholds, ranges, or comparator-prefixed categories

For columns, it should include:

- printed column headers
- inferred role such as `overall`, `group`, `comparison_group`, `p_value`, `unknown`
- source column indices
- any inferred grouping concept, such as disease status or exposure status

## What It Should Not Contain

`TableDefinition` should not contain:

- raw cell values for the table body
- parsed numeric values
- long-format `ValueRecord` entries
- final analysis-ready value output

This is intentional. The artifact is for semantic table structure, not for extracted statistics.

## Primary Use Case

The main intended use is handoff to another tool that maps paper labels onto a known database schema.

That downstream tool should be able to use `TableDefinition` to:

- propose candidate database variable names for row variables
- propose candidate coded values for categorical levels
- infer which database variable likely defines the table columns

## Design Requirements

- preserve source row and column indices
- preserve original printed labels
- include normalized labels for matching
- preserve meaning-bearing comparator and range syntax in categorical level matching names
- remain independent from cell-value extraction
- remain compatible with deterministic-first parsing
- allow later LLM refinement only for semantic ambiguity

## Non-Goals

This scope does not include:

- implementing the schema yet
- changing the CLI yet
- adding final validation rules yet
- adding value extraction logic
- deciding the exact final file layout for exports

## Output Relationship

The intended relationship is:

- `NormalizedTable` explains table structure
- `TableDefinition` explains table meaning without values
- `ParsedTable` explains table meaning with values

## Next Step

The next implementation step should be to define the minimal typed schema for
`TableDefinition` and a small assembly layer that builds it from heuristic and
optional LLM interpretation outputs.
