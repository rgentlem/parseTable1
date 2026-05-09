# Column Header Schema Design

## Purpose

Column interpretation needs a parser-native artifact before downstream objects
such as `TableDefinition`, `ParsedTable`, or any tableone-style projection make
the column structure look final.

The goal of this design is to add a typed column header tree / column schema
artifact that represents what the parser believes the table columns are, how
multi-row headers attach to those columns, and what raw extracted evidence
supports each relationship.

There are two major customers:

- parser semantics, especially `TableDefinition` and later value parsing
- an eventual tableone-oriented projection layer that needs a stored summary
  structure before it can print a tableone-like view

This artifact should answer:

- which normalized columns are real parser-facing leaf columns
- which header row supplies each leaf label
- which higher header cells span one or more leaves
- which raw cells and coordinates support each inferred leaf, group, and
  parent-child relationship
- which parts are missing, degraded, or ambiguous

It should not parse values and should not infer final epidemiologic semantics by
itself. It is a structural and provenance artifact that later semantic stages
consume.

## Pipeline Position

The target position is after normalization and before value-free semantic
definition:

```text
ExtractedTable -> NormalizedTable -> ColumnHeaderSchema -> TableDefinition -> ParsedTable
```

`NormalizedTable` remains the cleaned row/column grid. `ColumnHeaderSchema`
becomes the explicit column-structure model built from that grid plus optional
raw extraction evidence. `TableDefinition` can then consume a column schema
instead of rebuilding header context locally.

The artifact should be written by `table1-parser parse` as:

```text
outputs/papers/<paper_stem>/column_header_schemas.json
```

The file should contain one direct serialized `ColumnHeaderSchema` object per
normalized table, in normalized-table order.

## Non-Goals

This design does not attempt to:

- fix all bad header-row detection in normalization
- merge continuation fragments into one logical table
- infer row variables or categorical levels
- parse displayed values
- decide tableone/R object shape
- use an LLM to invent or repair missing headers

Continuation compatibility checks are an important consumer, but they are not
the primary design driver. The primary design driver is a durable, inspectable
column model that downstream parser stages can trust or reject explicitly.

## Relationship To Tableone-Style Projection

A tableone-style object is not the same thing as a column header schema. The
schema does not store summary values and should not decide how to print a table.

However, it should be designed with that later customer in mind. Whether a
summary comes from parsed paper cells or from individual-level data, the system
eventually needs a stored summary object before a print method can render it.
Printing should be a view over a computable object, not the place where column
meaning or summary structure is inferred.

The expected future relationship is:

```text
ColumnHeaderSchema + TableDefinition + ParsedTable
  -> stored observed summary object
  -> tableone-style print/render method
```

For summaries recomputed from individual-level data, the analogous flow is:

```text
ColumnHeaderSchema + TableDefinition + individual-level data mapping
  -> stored recomputed summary object
  -> tableone-style print/render method
```

In both cases, `ColumnHeaderSchema` supplies the column axis:

- row-label column vs summary/statistic columns
- overall columns
- grouped/stratified columns
- higher-level spanning labels
- printed leaf labels and source provenance

The stored summary object should own the summary values, statistic types,
denominators, and display-ready-but-structured cells. The print method should
only render that object.

## Core Concepts

### Leaf Columns

A leaf column is a parser-facing normalized column that may carry body content.
The schema should keep the row-label column as a leaf-like column with
`is_row_label_column = true`, because it participates in header alignment and
downstream column identity. Data columns should have `is_value_column = true`.

Leaf columns are inferred from:

1. normalized column indices
2. body-row non-empty evidence
3. the header row closest to the body

If normalization supplies no usable header rows, or only title/caption-like
header rows, the schema builder may infer a local header stack from rows above
the first strongly numeric body row. This fallback should remain conservative:
it records diagnostics and raw cell evidence in `ColumnHeaderSchema` rather
than rewriting `NormalizedTable`.

The closest-to-body header row supplies the leaf label. If that cell is blank,
the leaf label stays blank and the schema records a diagnostic. The parser
should not silently promote an upper spanning group to the leaf label unless no
leaf header row exists at all.

### Header Groups

Header groups are cells from higher header rows that span one or more leaf
columns. They preserve upper-header structure as explicit group records and
group-to-leaf relationships.

Common cases:

- repeated group labels across adjacent columns, such as `Severity of AL, %`
  repeated over statistic leaves
- a single non-empty cell followed by blank cells until the next non-empty
  header cell
- one upper label per leaf, such as `Q1`, `Q2`, `Q3`, `Q4` above threshold
  leaves
- multi-level stacks, such as `Severity -> >=3 mm -> %`

Header groups should be flat records with IDs, not nested Python-only objects,
so R consumers can turn them into data frames without bespoke tree walking.

### Relationships

Every inferred attachment between a header group and a leaf column should be a
separate relationship record. A group spanning four leaves produces four
relationship records.

This is more verbose than a nested tree, but it is easier to validate, inspect,
diff, and consume from R. It also makes provenance explicit at the relationship
level rather than only at the group level.

### Evidence

Every leaf, group, and relationship should reference evidence records. Evidence
records preserve:

- normalized row and column indices
- original extracted row and column indices when known
- raw extracted text when available
- normalized/cleaned text used by parser logic
- bounding box coordinates when available
- page number when available
- source artifact, such as `extracted_cell`, `metadata_table_cells`, or
  `normalized_cleaned_row`

If raw extracted evidence is unavailable, the schema may still be built from
`NormalizedTable.metadata["cleaned_rows"]`, but diagnostics must say that raw
coordinates are missing.

## Proposed Canonical Models

The exact field names can be refined during implementation, but the canonical
shape should follow this structure.

```python
class ColumnHeaderCellEvidence(BaseModel):
    evidence_id: str
    table_id: str
    row_idx: int
    col_idx: int
    original_row_idx: int | None = None
    original_col_idx: int | None = None
    raw_text: str | None = None
    cleaned_text: str
    bbox: tuple[float, float, float, float] | None = None
    page_num: int | None = None
    source: Literal[
        "extracted_cell",
        "metadata_table_cells",
        "normalized_cleaned_row",
    ]


class ColumnHeaderLeaf(BaseModel):
    leaf_id: str
    table_id: str
    col_idx: int
    original_col_idx: int | None = None
    is_row_label_column: bool = False
    is_value_column: bool = True
    leaf_header_row_idx: int | None = None
    leaf_label: str
    leaf_name: str
    body_nonempty_row_indices: list[int] = []
    evidence_ids: list[str] = []
    coordinate_left: float | None = None
    coordinate_center: float | None = None
    coordinate_right: float | None = None


class ColumnHeaderGroup(BaseModel):
    group_id: str
    table_id: str
    row_idx: int
    label: str
    name: str
    col_start: int
    col_end: int
    leaf_col_indices: list[int]
    evidence_ids: list[str] = []
    inference_rule: Literal[
        "repeated_label_span",
        "single_cell_blank_span",
        "single_leaf_group",
        "explicit_cell_span",
    ]
    confidence: float | None = None


class ColumnHeaderRelationship(BaseModel):
    relationship_id: str
    table_id: str
    parent_group_id: str
    child_leaf_id: str
    leaf_col_idx: int
    evidence_ids: list[str] = []
    confidence: float | None = None


class ColumnHeaderSchema(BaseModel):
    schema_id: str
    table_id: str
    n_cols: int
    label_col_idx: int | None = 0
    header_rows_considered: list[int] = []
    body_rows_considered: list[int] = []
    leaf_header_row_idx: int | None = None
    leaves: list[ColumnHeaderLeaf] = []
    groups: list[ColumnHeaderGroup] = []
    relationships: list[ColumnHeaderRelationship] = []
    evidence: list[ColumnHeaderCellEvidence] = []
    diagnostics: list[str] = []
    confidence: float | None = None
```

## Inference Rules

### 1. Build a Parser-Facing Grid

Use `NormalizedTable.metadata["cleaned_rows"]` as the parser-facing text grid.
If it is missing or malformed, return a degraded schema with diagnostics rather
than crashing.

Raw extraction evidence should be joined by table ID and normalized row/column
mapping when an `ExtractedTable` is available. Prefer
`NormalizedTable.metadata["source_col_indices"]` for the normalized-to-original
column map when it is present. Older or degraded normalized tables may require
falling back to `dropped_leading_cols`, `dropped_trailing_cols`, and
`column_repairs`.

### 2. Choose Leaf Columns

Start with the normalized column range `0..n_cols-1`.

For each column, record body evidence from `body_rows`. A column can still be a
leaf when body evidence is sparse if it has a leaf-header cell. A column should
not be invented solely from a higher header group.

Column `0` is the default label column unless existing normalization metadata
later supplies a better label-column index.

### 3. Choose the Leaf Header Row

Choose the header row closest to the body:

1. prefer the maximum row in `header_rows` that is before the first body row
2. otherwise use the maximum row in `header_rows`
3. if no header rows exist, set `leaf_header_row_idx = None`

When there is no leaf header row, leaves should still exist from body columns,
but their labels should be blank or generated as low-confidence placeholders
with diagnostics.

### 4. Build Leaf Labels

For each leaf column, take the cleaned cell from the leaf header row at that
column. Preserve a direct evidence reference to the raw extracted cell when
available.

Do not place upper group text into `leaf_label`. Upper rows belong in
`ColumnHeaderGroup` records and relationships.

When geometry shows that a short leading text fragment in a leaf-band cell lies
to the left of the boundary between adjacent leaf columns, the schema builder
may attach that fragment to the preceding leaf and keep the source cell as
evidence. This is a coordinate-based repair for extractor cell-boundary drift,
not a vocabulary-based header interpretation.

### 5. Attach Higher Header Rows

Process header rows above the leaf header row from bottom to top or top to
bottom, but preserve the original row index in every group.

For each higher header row:

- ignore rows that are only continuation markers, captions, or table-title text
  when normalization has clearly misclassified them as headers
- collapse adjacent repeated labels into one `repeated_label_span` group
- let a non-empty cell span following blank cells until the next non-empty cell
  only when the span covers real leaves and does not cross another explicit
  group boundary
- create `single_leaf_group` records for one-label-per-leaf upper rows
- record a diagnostic instead of forcing a span when the evidence is ambiguous

Every group-to-leaf attachment becomes a `ColumnHeaderRelationship`.

### 6. Preserve Coordinates

Coordinates should be taken from raw extracted `TableCell.bbox` first. If those
are unavailable, use normalized metadata such as `table_cells` when present. If
neither is available, keep the relationship but record missing coordinate
evidence.

Coordinates should not be normalized away in the primary evidence record. If a
consumer needs normalized page/table coordinates, it can derive them or use an
additional convenience profile.

## Validation Rules

Validation should ensure:

- every leaf `col_idx` is within `0..n_cols-1`
- every group span is contiguous in normalized column space
- every relationship points to an existing group and leaf
- every relationship leaf column is included in the parent group's
  `leaf_col_indices`
- evidence IDs referenced by leaves, groups, and relationships exist
- no group spans zero leaves
- no raw coordinates are invented when source evidence lacks coordinates

Validation failures should produce structured errors or diagnostics. A single
bad table should not crash the whole parse.

## Consumers

### `TableDefinition`

`TableDefinition` should use `ColumnHeaderSchema` to derive column descriptors:

- leaf label comes from `ColumnHeaderLeaf.leaf_label`
- shared context comes from related `ColumnHeaderGroup` labels
- per-column `header_path` comes from the schema's group path plus leaf label
- table-level `header_spans` preserve displayable multirow group and leaf spans
- `column_label` in `TableDefinition` is the leaf label, not the flattened path
- statistic columns and group columns are classified after the schema is built

This keeps `TableDefinition` semantic. It should not own the raw mechanics of
header-tree recovery.

### `ParsedTable`

`ParsedTable` should continue to consume `TableDefinition` for semantic column
roles. It should not need to rebuild header trees.

### Stored Summary And Tableone Projection

A later tableone-facing layer should consume the column schema instead of
reconstructing column structure from printed labels. Its first output should be
a stored summary object, not a print-only rendering.

That summary object should preserve:

- column leaf IDs and group relationship IDs from `ColumnHeaderSchema`
- row variable and level IDs from `TableDefinition`
- source parsed values or recomputed individual-level summaries
- statistic type, denominator, estimate, secondary estimate, and display text
- enough metadata to distinguish observed paper summaries from recomputed
  summaries

This keeps tableone-style printing honest: the print method can format a
summary object, while parser inference remains in parser artifacts.

### Continuation Compatibility

Continuation checks should eventually compare column schemas rather than
independent local header summaries. Useful schema-level checks include:

- same leaf count
- compatible row-label column
- compatible leaf labels when repeated headers exist
- compatible group paths over value leaves
- compatible raw/header coordinate evidence

This is a consumer of the design, not the reason for the design.

### R Inspection

R helpers should be able to load:

- leaves as one data frame
- groups as one data frame
- relationships as one data frame
- evidence as one data frame

Printed R methods can show the tree view, but the loaded object should preserve
the flat records.

## Test Strategy

Tests should cover both structurally difficult cases and ordinary tables.

Use compact in-repo fixtures, not full PDF outputs or large generated files.
When tests need Eke coverage, create small Eke-derived normalized/extracted
table slices that preserve the header structure and coordinate pattern without
checking in the full paper artifacts.

Required tests:

- Eke Table 1-derived fixture with a prevalence-style multi-column header,
  body/value columns, raw header-cell bboxes, and table-title rows that must not
  become spanning groups
- Eke Table 2-derived fixture with two higher-level case-definition groups
  spanning multiple prevalence category leaves
- a simple one-row Table 1 header such as `Characteristic`, `Overall`, `RA`,
  `P-value`
- a multi-row grouped header such as `Cobalt quartile` over `Q1` and `Q2`
- an extra-wide repaired header stack such as `Severity -> >=3 mm -> %/SE`
- a table with no reliable header rows, which should produce a degraded schema
  rather than invented structure
- a non-descriptive or result-style table so the schema builder does not
  overfit to Table 1-only assumptions

Regression expectations should assert:

- leaf labels come from the closest-to-body header row
- upper rows become groups, not leaf labels
- repeated upper labels collapse into spans
- each group-to-leaf relationship has evidence
- raw text and bbox coordinates are preserved when available
- missing raw evidence is explicit in diagnostics

## Implementation Plan

1. Add Pydantic schemas in `table1_parser/schemas/column_header_schema.py`.
2. Add deterministic assembly in a separate parser module, for example
   `table1_parser/column_header_schema.py`.
3. Add validation for schema integrity.
4. Write `column_header_schemas.json` from `table1-parser parse`.
5. Refactor `TableDefinition` column assembly to consume the schema.
6. Update continuation compatibility checks to consume schema-derived column
   headers and coordinate evidence after the primary schema contract is stable.
7. Add R inspection helpers after the JSON contract has tests.

The implementation should be staged so step 4 can land before changing
`TableDefinition` behavior if needed. That makes the artifact inspectable before
it becomes parser-critical.

## Open Questions

- Should placeholder leaf names be blank strings or generated names such as
  `column_3`? The model can support either, but diagnostics must distinguish
  generated names from printed labels.
- Should label-column detection remain hardcoded to column `0` initially, or
  should it consume normalization repair metadata from the first implementation?
- Should coordinate convenience fields use page coordinates only, or should the
  schema also store normalized table-relative coordinates?
- Should `column_header_schemas.json` include every table family immediately,
  or only tables routed toward descriptive parsing? The preferred default is
  every normalized table, because column structure is family-neutral.
