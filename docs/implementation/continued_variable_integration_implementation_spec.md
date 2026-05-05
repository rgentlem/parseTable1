# Continued Variable Integration Implementation Spec

Design note:

- `docs/design/separated_variable_description_integration.md`

## Goal

Implement deterministic integration of variable descriptions across continued
table fragments after column compatibility has passed.

Use existing parser objects:

- `NormalizedTable`
- `RowView`
- `Table1ContinuationGroup`
- `TableDefinition`
- `ColumnDefinition`
- `DefinedVariable`
- `DefinedLevel`

Do not add separate schema classes for this feature. The persisted integration
artifact is a list of `TableDefinition` objects with integrated variables and
metadata.

## Placement

Run after:

```text
NormalizedTable -> ColumnHeaderSchema -> TableDefinition
```

Run before:

```text
ParsedTable value parsing
LLM inference
ObservedTableOne construction
```

The first implementation writes an inspectable artifact and does not change
value parsing.

## Artifact

Write:

```text
outputs/papers/<paper_stem>/continued_variable_integrations.json
```

Each item is a `TableDefinition`:

- `table_id`: base table ID plus `-continued-variable-integration`
- `column_definition`: copied from the base `TableDefinition`
- `variables`: concatenated and boundary-adjusted `DefinedVariable` records
- `metadata`: integration and tableone-style metadata
- `notes`: integration notes and diagnostics

## TableDefinition Metadata

Add optional `metadata: dict[str, Any]` to `TableDefinition`.

Use two metadata blocks:

```text
metadata.continued_variable_integration
metadata.tableone
```

`metadata.continued_variable_integration` contains parser provenance:

- `group_id`
- `source_table_indices`
- `source_table_ids`
- `column_headers`
- `row_provenance`
- `boundary_decisions`
- `diagnostics`

`metadata.tableone` is concordant with `../tableone` `MetaData`:

- `vars`
- `logiFactors`
- `varFactors`
- `varNumerics`
- `percentMissing`
- `varLabels`

Structural row evidence belongs in `row_provenance`, not in tableone-style
metadata.

## Module

Add `table1_parser/continued_variable_integration.py`.

Public functions:

```python
def build_continued_variable_integrations(
    normalized_tables: list[NormalizedTable],
    table_definitions: list[TableDefinition],
    table1_continuation_groups: list[Table1ContinuationGroup],
) -> list[TableDefinition]:
    ...


def continued_variable_integrations_to_payload(
    integrations: list[TableDefinition],
) -> list[dict[str, object]]:
    ...
```

## Algorithm

For each group where `merge_decision == "merge"` and columns match:

1. Use the base table's `ColumnDefinition`.
2. Copy each fragment's `DefinedVariable` records.
3. Remap row indices into one integrated row sequence.
4. Build row provenance from `NormalizedTable.row_views`.
5. Concatenate variables in source order.
6. Reassess only the boundary between adjacent fragments.
7. If the last base variable is a categorical parent and leading continuation
   variables are its levels, rewrite those variables as `DefinedLevel` records.
8. Stop rewriting at the first true new variable.
9. Leave all non-boundary variables unchanged.
10. Recompute `metadata.tableone` from the integrated variables.

## Boundary Evidence

Use structural evidence only:

- base variable reaches the end of its fragment
- base row is parent-like or sparse
- base variable has no levels or incomplete levels
- continuation row has value cells
- continuation row indentation is compatible with a level
- continuation row lacks its own child levels
- row role suggests level-like or variable-like structure
- row order remains valid after rewrite

Do not use paper-specific vocabulary.

## R Inspection

Extend `load_paper_outputs()` with:

- `continued_variable_integrations`

Add:

- `summarize_continued_variable_integrations(paper_dir)`
- `show_continued_variable_integration(paper_dir, integration_index = 0L)`

R should print boundary decisions and row provenance. It should not recompute
integration.

## Later Consumer

After artifact review, update semantic consumers in a separate change:

- `ParsedTable` should use integrated variables for integrated continuations.
- `ObservedTableOne` should build `ContTable`, `CatTable`, and `MetaData` from
  integrated variables when available.

When this changes parse flow, update:

- `docs/design/paper_parse_walkthrough.md`
- `docs/design/parsing_output_design.md`
- `docs/r_visualization.md`

## Tests

Add tests for:

- concatenation with no boundary rewrite
- all levels starting in the continuation fragment
- levels split across both fragments
- continuation starts with a true new variable
- indentation supports level rewrite
- row provenance for every integrated variable and level
- integration skipped when the group is not merged
- R inspection smoke test
