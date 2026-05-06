# Separated Variable Description Integration

Prerequisite: run only for continued-table pairs whose `ColumnHeaderSchema` comparison has passed.

## Stage

Run after per-fragment normalization and deterministic variable extraction.
Run before value-frame construction and before any LLM inference.

Do not parse display text. Use the object shape exposed by:

```r
show_table_structure(paper_dir, table_index = 0L)
```

Canonical inputs:

- `columns`
- `variables`
- normalized body-row evidence at continuation boundaries

`columns` are post-normalization column records from the canonical header
projection. After the prerequisite passes, keep the base columns as the logical
column set for the integrated table.

`variables` are `TableDefinition` records with:

- `variable_name`
- `variable_label`
- `variable_type`
- `row_start`
- `row_end`
- `levels`
- `summary_style_hint`
- `units_hint`
- `confidence`

Each level preserves `level_name`, `level_label`, `row_idx`, and `confidence`.

## Output

Return an integrated variable-description artifact:

- `source_table_ids`
- `columns`
- `variables`
- `row_provenance`
- `integration_boundaries`
- `diagnostics`
- `confidence`

Each provenance record should include source table index/ID, source row index,
integrated row index, page number when available, original variable or level
name when available, and structural row evidence needed at the boundary:
indentation, row role, nonempty/value-cell counts, and first-cell text.

The downstream observed object should keep the `../tableone` style:

- `ContTable`: observed continuous rows and values
- `CatTable`: observed categorical variables, printed levels, and values
- `MetaData`: `vars`, `logiFactors`, `varFactors`, `varNumerics`,
  `varLabels`, and parser provenance

## Integration Task

1. Read variables from Table X.
2. Read variables from Table X continued.
3. Concatenate the two variable lists in source order, preserving source table
   and row provenance for every variable and level.
4. Reassess only the boundary between the fragments, including unclaimed
   leading continuation body rows before the first standalone continuation
   variable.
5. Ask whether the concatenated sequence changes the interpretation of the last
   base variable or the first continuation variables.
6. If the last base variable is a categorical parent and the first continuation
   body rows are its levels, rewrite those continuation rows as levels.
7. Stop rewriting as soon as the continuation reaches a true new variable.
8. When rewriting a parent:
   - keep base `variable_name` and `variable_label`
   - append levels in source order
   - extend `row_end`
   - set `variable_type = "categorical"` when levels are attached
   - preserve every source row in provenance
9. Leave all non-boundary variables unchanged.
10. Recompute variable order and tableone-style metadata from the integrated
   variable list.

## Reject Attachment When

- no open parent exists
- the continuation clearly starts a new variable
- boundary reinterpretation creates invalid row order or overlapping spans
- levels duplicate existing levels without supporting evidence
- confidence would be lower than keeping fragments separate

## Minimum Tests

- concatenation without boundary reinterpretation preserves both fragments
- all levels start in the continuation fragment
- levels are split across both fragments
- continuation starts with a new standalone variable
- unmatched continuation variables are preserved
- row provenance maps every integrated variable and level
