# Column Grouping Semantics Plan

This document describes the next deterministic improvement for `TableDefinition` column semantics.

## Goal

Infer column meaning from the table's grouping structure rather than from isolated header strings.

The implementation should answer:

- whether the table has grouped data columns
- whether one column is an overall or full-population column
- what grouping variable likely defines the grouped columns
- how many grouped columns there are
- what each grouped column's level label is
- whether trailing columns are statistical test columns

This plan is intentionally general. It should support:

- disease-status groupings such as `RA` and `non-RA`
- ordinal groupings such as quartiles or tertiles
- multi-level categorical groupings
- compound grouped labels that represent combinations of binary factors

## Persisted Schema Changes

Extend `DefinedColumn` with optional grouping metadata:

- `group_level_label`
- `group_level_name`
- `group_order`
- `statistic_subtype`

Extend `ColumnDefinition` with:

- `group_count`

These fields should remain optional so existing outputs continue to validate.

## Deterministic Analysis Model

Before assembling `DefinedColumn` objects, the column builder should first derive an internal grouping analysis that partitions columns into:

- the row-label column
- overall column(s)
- grouped data columns
- trailing statistical or test columns

The analysis should also carry:

- `grouping_variable_label`
- `grouping_variable_name`
- ordered grouped-column level guesses
- statistic subtype guesses for trailing test columns

This structure can remain internal to the heuristic module for now.

## Header Interpretation Rules

Use `ColumnHeaderSchema` to build per-column header descriptors.

For each column derive:

- the full paper-facing header text
- the normalized matching-friendly header name
- the leaf header text
- the top-level shared header context when present

For multi-row headers, preserve leaf headers, spanning groups, and group-to-leaf relationships while inferring grouping.

## Column Partition Rules

1. Treat column `0` as the row-label column when it is empty or label-like.
2. Detect trailing statistical columns first using strong cues such as:
   - `P`
   - `P-value`
   - `P for trend`
   - `trend`
   - `SMD`
3. Among remaining data columns, detect an overall column.
   - Prefer explicit labels like `Overall`, `All`, or `Total`.
   - Otherwise, when several grouped columns follow, allow the first substantive data column to act as the overall column.
4. Treat the remaining contiguous data columns as grouped columns.

## Grouping Variable Inference

Infer the grouping variable conservatively from:

1. caption or title text such as `by RA status`
2. shared upper-header context across grouped columns
3. repeated level families in the grouped leaf headers

If the grouped block is clear but the grouping variable is not, persist grouped columns and group levels anyway while leaving the grouping variable empty.

## Group-Level Semantics

For each grouped column persist:

- `group_level_label`: paper-facing grouped-column label
- `group_level_name`: normalized matching-friendly form
- `group_order`: left-to-right order within the grouped block

Do not hardcode quartile-specific fields. Quartiles should emerge as one ordinary grouped-column family.

## Statistical Column Semantics

Keep the current `inferred_role` enum for now, but preserve richer distinctions in `statistic_subtype`.

Planned subtype values:

- `p_value`
- `p_trend`
- `smd`
- `statistic_unknown`

This allows multiple trailing p-style columns to remain distinct without a larger schema rewrite.

## Implementation Steps

1. Extend the `TableDefinition` schema with the new optional fields.
2. Refactor deterministic column assembly to run a grouping-analysis pass before building `DefinedColumn` records.
3. Improve overall-column, grouped-block, and trailing-stat-column detection.
4. Populate grouped-column level metadata and `group_count`.
5. Preserve paper-facing `column_label` while building cleaner but semantically distinct `column_name`.
6. Add focused tests for:
   - disease-status grouping
   - ordinal quartile-style grouping
   - multi-row headers with shared upper context
   - multiple trailing statistical columns
7. Update the design docs so the persisted JSON contract matches the implementation.

## Success Criteria

After this change, `table_definitions.json` should carry enough column metadata for downstream tooling to distinguish:

- the overall population column
- grouped columns and their levels
- the likely grouping variable
- multiple statistical columns with different meanings
