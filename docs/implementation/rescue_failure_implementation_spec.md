# Rescue Failure Implementation Spec

## Goal

Implement structured rescue sequencing and table-level failure tracking using existing methods only.

## Rules

- Do not add new rescue algorithms.
- Do not add new parser methods.
- Reuse current extraction, normalization, semantic, and parse paths.
- Record what was considered, what ran, and what failed.
- A descriptive / Table 1-like table with zero variables or zero usable columns must fail unless an existing rescue succeeds.

## Required Checks

### Extraction inadequate if:
- collapsed to one row
- too few effective columns
- concatenated label block or value block

### Normalization inadequate if:
- no body rows
- one body row for descriptive table
- no usable non-label columns

### TableDefinition inadequate if:
- `len(variables) == 0`
- no usable non-label columns

### ParsedTable inadequate if:
- variables and usable columns exist
- but zero values are produced

## Rescue Order

1. Extraction
   - `explicit_grid_refinement`
   - `low_quality_candidate_text_layout_rescue`
   - `page_text_layout_fallback`

2. Normalization
   - run current normalization repairs only

3. TableDefinition
   - deterministic definition
   - existing semantic interpretation if already eligible

4. ParsedTable
   - deterministic value parse only

## Required Behavior

- Run all relevant existing rescue paths in fixed order.
- Do not stop after the first path unless adequacy is restored.
- If adequacy is not restored, mark the table failed.
- Do not emit silent empty success for descriptive tables.

## Tracking Record

Add a stable per-table status record with:

```json
{
  "status": "ok | rescued | failed",
  "failure_stage": "extraction | normalization | table_definition | parsed_table | null",
  "failure_reason": "string | null",
  "attempts": [
    {
      "stage": "string",
      "name": "string",
      "considered": true,
      "ran": true,
      "succeeded": true,
      "note": "string | null"
    }
  ]
}
```

## Stable Attempt Names

- `explicit_grid_refinement`
- `low_quality_candidate_text_layout_rescue`
- `page_text_layout_fallback`
- `edge_column_trim`
- `glyph_repair`
- `deterministic_definition`
- `deterministic_value_parse`

## Stable Failure Reasons

- `collapsed_grid_unrecovered`
- `insufficient_table_structure_after_extraction`
- `no_body_rows_after_normalization`
- `collapsed_body_after_normalization`
- `no_usable_columns_after_normalization`
- `no_variables_for_descriptive_table`
- `no_columns_for_descriptive_table`
- `unresolved_descriptive_structure`
- `no_values_after_parse`

## Minimum First Change

Implement this first:

- if a descriptive / Table 1-like table reaches `TableDefinition` with zero variables or zero usable columns, mark it failed and record all attempted existing rescues
