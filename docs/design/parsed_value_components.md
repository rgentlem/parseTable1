# Parsed Value Components Design

This document defines a value-parsing artifact that records parsed table-cell
contents before continuation fragments are joined.

The goal is to parse body value element candidates once, preserve the printed
source fragments, and store the parsed numeric components in an
index-addressable structure that can later be aligned with
`ColumnHeaderSchema`, `TableDefinition`, continuation row provenance, and
R/tableone-style display objects.

## Motivation

Continuation handling is easier if cell values are parsed before fragments are
semantically joined. A continuation fragment may not know that its leading rows
belong to a parent variable on the previous page, but each printed cell can
still be parsed locally.

Therefore:

- body element candidate construction should run after `ColumnHeaderSchema`,
  before component parsing
- cell-value parsing should run on each candidate from each normalized source
  table fragment
- value records should be keyed by source table and grid indices
- continuation integration should remap already-parsed values by row provenance
- variable names, level labels, column labels, and header paths should be
  attached later by joining against semantic artifacts

## Non-Goals

This artifact must not:

- duplicate row labels, column labels, variable names, level labels, or header
  paths in each cell record
- use composite semantic value types such as `count_percent` as the payload
- rely on tableone internals or try to reconstruct subject-level data
- replace `raw_value` with normalized or reformatted text
- infer variable or column meaning by itself

## Artifact

Proposed filename:

```text
outputs/papers/<paper_stem>/parsed_cell_values.json
```

The artifact is a flat list of cell records. Each record is addressed only by
source table identity plus row and column indices:

```python
class ParsedCellValue(BaseModel):
    source_table_index: int
    source_table_id: str
    row_idx: int
    col_idx: int
    raw_value: str
    element_candidate_id: str | None = None
    raw_fragments: list[str] = []
    source_cells: list[BodyElementSourceCell] = []
    parse_pattern: str | None = None
    components: list[ValueComponent] = []
    confidence: float | None = None
    notes: list[str] = []
```

```python
class ValueComponent(BaseModel):
    kind: ValueComponentKind
    value: float | str | None = None
    raw_fragment: str | None = None
    relation: Literal["=", "<", "<=", ">", ">="] | None = None
    confidence: float | None = None
```

`row_idx` and `col_idx` are the candidate anchor indices in the source
normalized table. They are enough for alignment. When a candidate spans
multiple physical cells, `raw_fragments` and `source_cells` preserve the
printed evidence. Row and column labels belong in `TableDefinition` and
`ColumnHeaderSchema`, not in this artifact.

## Component Semantics

`components` is the semantic payload. Each component states what one part of
the printed cell means.

Initial component kinds:

- `count`
- `percent`
- `mean`
- `sd`
- `median`
- `q1`
- `q3`
- `estimate`
- `se`
- `p_value`
- `missing`
- `text`
- `unknown`

Composite forms such as `count_percent` are not component kinds. If a cell
prints `34 (45%)`, the components are:

```json
[
  {"kind": "count", "value": 34, "raw_fragment": "34"},
  {"kind": "percent", "value": 45, "raw_fragment": "45%"}
]
```

This treats `count` and `percent` symmetrically. Both are spelled out as
component kinds; neither is privileged as the primary value.

## Parse Pattern

`parse_pattern` records how the parser recognized the cell shape. It is
diagnostic provenance, not the semantic payload.

Examples:

- `integer`
- `count_parenthesized_percent`
- `mean_parenthesized_sd`
- `mean_plusminus_sd`
- `median_bracket_iqr`
- `estimate_dash_se`
- `p_value`
- `missing`
- `free_text`

Downstream consumers should use `components[*].kind` for semantics. They may
use `parse_pattern` for diagnostics, confidence adjustment, or display notes.

## Examples

Count and percent:

```json
{
  "source_table_index": 0,
  "source_table_id": "tbl-1",
  "row_idx": 23,
  "col_idx": 4,
  "raw_value": "34 (45%)",
  "parse_pattern": "count_parenthesized_percent",
  "components": [
    {"kind": "count", "value": 34, "raw_fragment": "34"},
    {"kind": "percent", "value": 45, "raw_fragment": "45%"}
  ],
  "confidence": 0.95,
  "notes": []
}
```

Estimate and standard error:

```json
{
  "source_table_index": 0,
  "source_table_id": "tbl-1",
  "row_idx": 12,
  "col_idx": 3,
  "raw_value": "47.2 - 2.1",
  "parse_pattern": "estimate_dash_se",
  "components": [
    {"kind": "estimate", "value": 47.2, "raw_fragment": "47.2"},
    {"kind": "se", "value": 2.1, "raw_fragment": "2.1"}
  ],
  "confidence": 0.9,
  "notes": []
}
```

P-value with inequality:

```json
{
  "source_table_index": 0,
  "source_table_id": "tbl-1",
  "row_idx": 18,
  "col_idx": 6,
  "raw_value": "<0.001",
  "parse_pattern": "p_value",
  "components": [
    {"kind": "p_value", "value": 0.001, "raw_fragment": "<0.001", "relation": "<"}
  ],
  "confidence": 0.98,
  "notes": []
}
```

Not estimable:

```json
{
  "source_table_index": 0,
  "source_table_id": "tbl-1",
  "row_idx": 27,
  "col_idx": 8,
  "raw_value": "N/A",
  "parse_pattern": "missing",
  "components": [
    {"kind": "missing", "value": null, "raw_fragment": "N/A"}
  ],
  "confidence": 0.95,
  "notes": []
}
```

## Continuation Flow

The continuation-aware flow should be:

```text
NormalizedTable fragments
-> ColumnHeaderSchema
-> body_element_candidates.json
-> parsed_cell_values.json
-> TableDefinition fragments
-> continued_variable_integrations.json
-> remapped value frame for integrated table
-> ObservedTableOne / tableone-style display
```

Value parsing happens before joining. Semantic attachment happens after
joining:

1. Build source-fragment body element candidates over schema-derived value
   columns.
2. Parse each candidate's `candidate_text` into component records.
3. Keep records keyed by `source_table_index`, `source_table_id`, `row_idx`,
   and `col_idx`.
4. Build continuation row provenance during variable integration.
5. Remap source value records to integrated row indices using provenance.
6. Join remapped value records to variables, levels, and columns by index.

This avoids reparsing display strings and avoids forcing a continuation fragment
to know its parent variable before the continuation boundary is interpreted.

## Possible TableOne-Style Projection

If later usage shows that an R inspection object is needed, it should be a
projection over:

- `ColumnHeaderSchema` / `TableDefinition.column_definition`
- `TableDefinition.variables`
- parsed value components
- continuation row provenance when present

The value artifact should not store display labels. R code can build labelled
matrices or data frames by joining indices to the semantic artifacts, but helper
functions should be added only for repeated review workflows rather than
hypothetical display formats. Possible views include:

- counts matrix from `kind == "count"`
- percents matrix from `kind == "percent"`
- estimates matrix from `kind == "estimate"` or `kind == "mean"`
- uncertainty matrix from `kind == "se"`, `kind == "sd"`, `q1`, `q3`
- p-value/statistic columns from `kind == "p_value"` or other statistic kinds

Any display layer can render cells such as `34 (45%)` or `47.2 (2.1)` from
components and metadata without treating that rendered string as the stored
truth.

## Later Review Hooks

The component layer is intended to support later paper-review diagnostics, such
as column-level checks for suspicious mixtures, unknown components, missing
values, or likely typographical errors. Those diagnostics should be added only
when real review work identifies concrete failure modes. They should consume
`parsed_cell_values.json`, `ColumnHeaderSchema`, and `ParsedTable.values`
rather than introducing a separate profile artifact by default.

For now, schema validation is limited to the Pydantic component models and the
explicit source table, row, and column indices stored on each record. Do not add
a separate validation-report artifact or strict validation class unless it is
needed to catch a known parser failure.

## Semantic Join In `ParsedTable.values`

`ParsedTable.values` is the component-aware semantic value layer. It joins the
source-grid component records to row-variable, level, column, and header-path
semantics from `TableDefinition` and `ColumnHeaderSchema`.

The canonical semantic payload is:

- source provenance: `source_table_index`, `source_table_id`, `row_idx`,
  `col_idx`
- row and column semantics: variable, level, column label, leaf header, group
  headers, and header path
- source value evidence: `raw_value`, `parse_pattern`, `components`
- review evidence: `confidence`, `notes`

No scalar compatibility aliases are part of the canonical semantic value
record. New tableone-style projections, continuation work, and anomaly
diagnostics should consume `components` directly.
