# Separated Variable Description Integration

Prerequisite: run only for Table X / Table X continued pairs whose
`ColumnHeaderSchema` comparison has passed.

## Canonical Inputs

Use the table-structure representation returned by:

```r
show_table_structure(paper_dir, table_index = 0L)
```

The integration input is:

- `columns`
- `variables`

`variables` are the canonical `TableDefinition` variable records:

- `variable_name`
- `variable_label`
- `variable_type`
- `row_start`
- `row_end`
- `levels`
- `summary_style_hint`
- `units_hint`
- `confidence`

`levels` preserve:

- `level_name`
- `level_label`
- `row_idx`
- `confidence`

## Target Shape

Adopt the `../tableone` style early:

- `ContTable`: observed continuous variable rows and values
- `CatTable`: observed categorical variables, printed levels, and values
- `MetaData`: `vars`, `logiFactors`, `varFactors`, `varNumerics`,
  `varLabels`, plus parser provenance

This is an observed-table object, not a reconstruction of subject-level data.

## Task

1. Extract variables from Table X.

2. Extract variables from Table X continued.

3. Find the trailing open variable in Table X:
   - categorical or unknown
   - parent-like row
   - no levels or incomplete levels
   - row span reaches the fragment end

4. Find leading continuation levels:
   - level-like rows at the start of Table X continued
   - weak or missing parent label
   - better interpreted as levels than standalone variables

5. Attach leading continuation levels to the open variable.

6. Update the integrated variable:
   - keep Table X `variable_name` and `variable_label`
   - append continuation levels in source order
   - set `row_end` to the last attached level
   - set `variable_type = "categorical"` when levels are attached
   - preserve source provenance for each row

7. Keep unmatched continuation variables as new variables.

8. Return:
   - integrated `variables`
   - unchanged `columns`
   - source-row provenance
   - diagnostics

## Reject Attachment When

- no open variable exists
- the continuation clearly starts a new variable
- row spans become invalid
- duplicate levels lack supporting evidence

## Minimum Tests

- parent in Table X, all levels in Table X continued
- parent in Table X, levels split across both fragments
- continuation starts with a new standalone variable
- unmatched continuation variables are preserved
- attached levels retain source table and row provenance
