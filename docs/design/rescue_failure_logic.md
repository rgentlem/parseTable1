# Rescue Failure Logic

## Purpose

Define a structured way to:

- run all relevant existing rescue paths for a table
- record which rescue paths were considered and which actually ran
- mark a table as failed when rescue is exhausted and the result is still unusable

This is a control-flow and status-tracking design only.

It does **not** add new parsing methods.
It does **not** invent new extraction or semantic strategies.
It only standardizes how existing rescue logic is applied and how outcomes are recorded.

## Scope

Applies to the existing pipeline:

```text
PDF -> ExtractedTable -> NormalizedTable -> TableProfile -> TableDefinition -> ParsedTable
```

This design covers:

- extraction rescue sequencing
- normalization repair sequencing
- definition-level adequacy checks
- explicit table-level failure reporting

## Non-Goals

- no new extraction algorithms
- no new normalization heuristics
- no new semantic parsing methods
- no new LLM behaviors
- no paper-level retry logic

## Terms

### Repair

A conservative local correction inside the current stage.

Examples:
- merge split `n (%)` columns
- drop empty helper columns after repair
- repair known extractor glyph failures

### Rescue

Retry or reuse an **existing** recovery path because the current artifact is inadequate.

Examples:
- replace a low-quality explicit table with an existing text-layout candidate
- run existing explicit-grid refinement from word geometry
- run existing semantic interpretation when already available and eligible

### Failure

The table remains unusable after all relevant existing rescues have been tried.

## Core Rule

For a strong Table 1 / descriptive table candidate:

- zero variables is failure unless rescue succeeds
- zero usable non-label columns is failure unless rescue succeeds

An empty parse must not be treated as success.

## Adequacy Checks

Each stage gets a simple adequacy check.

### Extraction Adequacy

Extraction is inadequate when any of these hold:

- grid is effectively collapsed to one row
- grid has too few effective columns for a descriptive table
- one label cell contains many concatenated row labels
- one value cell contains many concatenated values

### Normalization Adequacy

Normalization is inadequate when any of these hold:

- no body rows
- only one body row for a descriptive table
- no usable non-label data columns

### TableDefinition Adequacy

Definition is inadequate when any of these hold:

- `len(variables) == 0`
- no usable non-label columns
- descriptive table candidate but only placeholder or unknown structure remains

### ParsedTable Adequacy

Parsed output is inadequate when:

- variables and usable columns exist
- but zero values are produced

## Rescue Order

Rescue should be attempted in a fixed order using existing logic only.

### 1. Extraction Stage

If extraction is inadequate, try all relevant existing extraction rescues in order:

1. explicit-grid refinement already available in the extractor
2. low-quality explicit-candidate replacement with existing text-layout rescue
3. existing page-level text-layout fallback when applicable

Rule:
- if the table is upright, collapsed, and descriptive/Table 1-like, existing explicit-grid refinement logic should be allowed to run
- descriptive tables should not be excluded from rescue just because they do not look like model/estimate tables

If extraction remains inadequate after those existing paths, mark extraction failure.

### 2. Normalization Stage

Run the current normalization flow and existing repairs.

If normalization is still inadequate after current repairs, mark normalization failure.

No new normalization rescue methods are introduced here.

### 3. TableDefinition Stage

Build the deterministic definition using the current logic.

If definition is inadequate:

- use the existing semantic interpretation path only if it is already eligible
- otherwise fail immediately

If deterministic plus existing semantic rescue still yields zero variables or zero usable columns for a descriptive table, mark definition failure.

### 4. ParsedTable Stage

Build parsed values using the current logic.

If variables and usable columns exist but zero values are produced, mark parsed-table failure.

## Rescue Tracking

Each table should carry a stable rescue-status record.

This can live in table metadata or a sibling per-table status artifact.
The key requirement is that it is explicit and structured.

### Required Fields

```json
{
  "status": "ok | rescued | failed",
  "failure_stage": "extraction | normalization | table_definition | parsed_table | null",
  "failure_reason": "string | null",
  "attempts": [
    {
      "stage": "extraction | normalization | table_definition | parsed_table",
      "name": "string",
      "considered": true,
      "ran": true,
      "succeeded": true,
      "note": "string | null"
    }
  ]
}
```

## Required Attempt Names

Use stable names for existing paths.

### Extraction

- `explicit_grid_refinement`
- `low_quality_candidate_text_layout_rescue`
- `page_text_layout_fallback`

### Normalization

- `edge_column_trim`
- `glyph_repair`

### TableDefinition

- `deterministic_definition`

### ParsedTable

- `deterministic_value_parse`

## Failure Reasons

Use stable failure reasons.

### Extraction

- `collapsed_grid_unrecovered`
- `insufficient_table_structure_after_extraction`

### Normalization

- `no_body_rows_after_normalization`
- `collapsed_body_after_normalization`
- `no_usable_columns_after_normalization`

### TableDefinition

- `no_variables_for_descriptive_table`
- `no_columns_for_descriptive_table`
- `unresolved_descriptive_structure`

### ParsedTable

- `no_values_after_parse`

## Expectations

### Descriptive / Table 1-like Tables

These have strict failure behavior.

If they end with:
- no variables
- no usable columns
- or no values after successful semantics

the table must be marked failed.

### Unknown Tables

Unknown tables may remain best-effort.
Failure rules may be looser.

## Implementation Constraint

This design should be implemented by:

- reusing current stage entry points
- reusing current rescue paths
- adding adequacy checks
- adding structured attempt/failure tracking

It should **not** be implemented by adding a new parallel rescue subsystem or a new family of parser methods.

## Immediate Minimum Change

The first required behavior change is:

- if a descriptive or Table 1-like table reaches `TableDefinition` with zero variables or zero usable columns, mark it failed and record which existing rescue paths were tried

That single rule prevents the most misleading current behavior: silent empty success.
