# Table Definition Pydantic Schema

This document proposes the Pydantic models for the value-free semantic stage named `TableDefinition`.

It is intentionally close to the existing `ParsedTable` schema, but excludes cell values.

## Proposed Models

### `DefinedLevel`

Represents one categorical level under a row variable.

Suggested fields:

- `level_name: str`
- `level_label: str`
- `row_idx: int`
- `confidence: float | None = None`

Notes:

- `level_label` preserves the paper-facing label
- `level_name` is the matching-friendly form used for downstream level matching
- unlike `variable_name`, `level_name` must preserve meaning-bearing comparator and range syntax such as `< 1.3`, `1.3-1.8`, and `>1.8`
- this also applies to comparator-prefixed textual levels such as `<High school` and `>High school`

### `DefinedVariable`

Represents one row variable in the table.

Suggested fields:

- `variable_name: str`
- `variable_label: str`
- `variable_type: Literal["continuous", "categorical", "binary", "unknown"] = "unknown"`
- `row_start: int`
- `row_end: int`
- `levels: list[DefinedLevel] = []`
- `units_hint: str | None = None`
- `summary_style_hint: str | None = None`
- `confidence: float | None = None`

Notes:

- `variable_label` is the printed label from the paper
- `variable_name` is the normalized label used for downstream matching
- `variable_name` may strip summary/unit decorations from variable rows, such as `n (%)`, `mean (SD)`, or parenthetical unit suffixes, before normalization
- this variable-row stripping behavior does not apply to `level_name`
- `units_hint` can capture things like `years` or `kg/m2`
- `summary_style_hint` can capture cues such as `mean_sd`, `median_iqr`, or `count_pct`

### `DefinedColumn`

Represents one semantic table column.

Suggested fields:

- `col_idx: int`
- `column_name: str`
- `column_label: str`
- `inferred_role: Literal["overall", "group", "comparison_group", "p_value", "smd", "unknown"] = "unknown"`
- `grouping_variable_hint: str | None = None`
- `group_level_label: str | None = None`
- `group_level_name: str | None = None`
- `group_order: int | None = None`
- `statistic_subtype: str | None = None`
- `confidence: float | None = None`

Notes:

- `column_label` preserves the printed header
- `column_name` is the normalized matching-friendly form
- `grouping_variable_hint` is the best guess for what defines the subgrouping, such as `ra_status`
- `group_level_label` preserves the paper-facing label for one grouped column, such as `RA`, `non-RA`, `Q1`, or `Q4`
- `group_level_name` is the matching-friendly grouped-column level form
- `group_order` preserves the left-to-right order of grouped columns
- `statistic_subtype` keeps multiple test columns distinct, for example `p_value` versus `p_trend`

### `ColumnDefinition`

Represents the overall column design of the table.

Suggested fields:

- `grouping_label: str | None = None`
- `grouping_name: str | None = None`
- `group_count: int | None = None`
- `columns: list[DefinedColumn] = []`
- `confidence: float | None = None`

Notes:

- this allows the table to carry a table-level guess like `RA status` or `Diabetes status`
- individual `DefinedColumn` records still preserve per-column roles and labels
- `group_count` records how many grouped data columns were inferred, separate from any overall or statistic columns

### `TableDefinition`

Represents the semantic definition of the table without values.

Suggested fields:

- `table_id: str`
- `title: str | None = None`
- `caption: str | None = None`
- `variables: list[DefinedVariable] = []`
- `column_definition: ColumnDefinition`
- `metadata: dict[str, Any] = {}`
- `notes: list[str] = []`
- `overall_confidence: float | None = None`

Notes:

- `metadata` is for stage-specific extensions such as continued-variable
  integration provenance and tableone-style metadata; core row and column
  semantics remain in the explicit fields above

## Why This Shape

This shape supports the main downstream task:

- map printed row variables to database variables
- map printed level labels to coded category values
- identify the likely database variable used to create the table columns

It also stays cleanly separate from `ParsedTable`, which should still own:

- `ValueRecord`
- parsed numeric values
- long-format cell-level output

## Suggested File Location

When implemented, the schema should live in a separate module such as:

- `table1_parser/schemas/table_definition.py`

This keeps the stages separate:

- `normalized_table.py`
- `table_definition.py`
- `parsed_table.py`

## Non-Goals for This Schema

This proposal does not include:

- database variable matches
- database table names
- extracted cell values
- numeric summaries
- final validation logic

Those belong to later stages or to external matching tools.
