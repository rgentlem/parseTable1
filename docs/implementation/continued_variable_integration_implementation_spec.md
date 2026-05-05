# Continued Variable Integration Implementation Spec

Design note:

- `docs/design/separated_variable_description_integration.md`

## Goal

Implement deterministic integration of variable descriptions across continued
table fragments after column compatibility has passed.

The first implementation should create an inspectable artifact. It should not
change value parsing until the artifact is stable.

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

Prerequisites:

- `ColumnHeaderSchema` comparison passed for the continued pair
- source fragments have `TableDefinition.variables`
- source fragments have row evidence in `NormalizedTable.row_views`

## New Schema

Add `table1_parser/schemas/continued_variable_integration.py`.

Models:

```python
class IntegratedRowProvenance(BaseModel):
    integrated_row_idx: int
    source_table_index: int
    source_table_id: str
    source_row_idx: int
    source_page_num: int | None = None
    source_kind: Literal["variable", "level"]
    source_name: str | None = None
    source_label: str | None = None
    indent_level: int | None = None
    likely_role: str | None = None
    first_cell_raw: str | None = None
    first_cell_normalized: str | None = None
    nonempty_cell_count: int | None = None
    numeric_cell_count: int | None = None
    has_trailing_values: bool | None = None


class VariableBoundaryDecision(BaseModel):
    boundary_id: str
    base_table_index: int
    continuation_table_index: int
    decision: Literal["unchanged", "attached_levels", "rejected"]
    parent_variable_name: str | None = None
    attached_level_count: int = 0
    confidence: float | None = None
    reasons: list[str] = Field(default_factory=list)


class ContinuedVariableIntegration(BaseModel):
    integration_id: str
    source_table_indices: list[int]
    source_table_ids: list[str]
    columns: list[DefinedColumn]
    variables: list[DefinedVariable]
    row_provenance: list[IntegratedRowProvenance]
    boundary_decisions: list[VariableBoundaryDecision]
    diagnostics: list[str] = Field(default_factory=list)
    confidence: float | None = None
```

Export from `table1_parser/schemas/__init__.py`.

## New Module

Add `table1_parser/continued_variable_integration.py`.

Public functions:

```python
def build_continued_variable_integrations(
    normalized_tables: list[NormalizedTable],
    table_definitions: list[TableDefinition],
    column_header_schemas: list[ColumnHeaderSchema],
    table1_continuation_groups: list[Table1ContinuationGroup],
) -> list[ContinuedVariableIntegration]:
    ...


def continued_variable_integrations_to_payload(
    integrations: list[ContinuedVariableIntegration],
) -> list[dict[str, object]]:
    ...
```

## Algorithm

For each continuation group with `merge_decision == "merge"`:

1. Confirm all source table indices exist.
2. Confirm source schemas match source table IDs.
3. Confirm the group reports matching column headers.
4. Use base `TableDefinition.column_definition.columns` as `columns`.
5. Convert each fragment variable list into source-tagged records.
6. Add row provenance for every variable and level from `row_views`.
7. Concatenate the variable lists in source order.
8. Reassess only the boundary between adjacent fragments.
9. If the final base variable is a categorical parent and the first
   continuation variables are its levels, rewrite those continuation variables
   as levels of the base parent.
10. Stop rewriting at the first true new variable.
11. Leave all non-boundary variables unchanged.
12. Emit a `VariableBoundaryDecision`.

## Boundary Evidence

Use structural evidence only:

- base variable reaches the end of its fragment
- base variable has no levels or incomplete levels
- base row is parent-like or sparse
- continuation row has value cells
- continuation row indentation is compatible with a level
- continuation row lacks its own child levels
- row role suggests level-like or variable-like structure
- row order remains valid after rewrite

Do not use paper-specific vocabulary.

## CLI Artifact

Write:

```text
outputs/papers/<paper_stem>/continued_variable_integrations.json
```

Add it to `PaperParseArtifacts` and write it during `table1-parser parse`.

Do not feed it into `ParsedTable` in the first implementation.

## R Inspection

Extend `load_paper_outputs()` with:

- `continued_variable_integrations`

Add compact helpers:

- `summarize_continued_variable_integrations(paper_dir)`
- `show_continued_variable_integration(paper_dir, integration_index = 0L)`

The R helper should print boundary decisions and row provenance. It should not
recompute integration.

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

Add focused unit tests for:

- concatenation with no boundary rewrite
- all levels starting in the continuation fragment
- levels split across both fragments
- continuation starts with a true new variable
- indentation supports level rewrite
- indentation reset stops rewrite
- row provenance exists for every integrated variable and level
- integration is skipped when column comparison did not pass

Add one R smoke test for the inspection helper.
