# Column Header Schema Design

## Purpose

Column interpretation needs a parser-native artifact before downstream objects
such as `TableDefinition`, `ParsedTable`, or any tableone-style projection make
the column structure look final.

The goal of this design is to add a typed column header tree / column schema
artifact that represents what the parser believes the table columns are, how
multi-row headers attach to those columns, and what raw extracted evidence
supports each relationship.

The implemented Phase J path makes this artifact a direct projection of the
matching `HeaderStructureCandidate`. Candidate `base_text`, node IDs,
evidence IDs, canonical bounds, groups, and group-to-leaf relationships are
preserved. Schema construction does not choose header rows or reconstruct
leaf/group geometry.

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
ExtractedTable -> TableRegion -> NormalizedTable -> ColumnHeaderSchema -> TableDefinition -> ParsedTable
```

`TableRegion` supplies geometry-owned caption/header/body/footer row bands when
available. `NormalizedTable` remains the cleaned row/column grid.
`ColumnHeaderSchema` becomes the explicit column-structure model built from
that grid plus optional raw extraction evidence. `TableDefinition` can then
consume a column schema instead of rebuilding header context locally.

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

When continuation identity is already established, compatibility may use the
leaf-only schema if the continuation repeats every leaf and column but omits a
parent spanning-group row. The resolved table inherits the parent's complete
tree only after that exact leaf match. A conflicting continuation group is not
discarded or overridden.

An adjacent continuation may also inherit locally blank candidate terminal
labels when its complete one-to-one physical-column alignment, nonblank labels,
and repeated group spans uniquely align with the parent. The candidate retains
the blank local label and parent table, terminal node, page, and structural
evidence. Schema construction consumes that effective candidate only for this
provenance-bearing case; it does not alter the physical grid or infer missing
text independently.

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

### Terminal Header Nodes And Column Roles

A terminal header node is the lowest semantic header node mapped to one
parser-facing physical column. `HeaderStructureCandidate.physical_col_idx`
makes that mapping explicit; neither a physical band nor a cell bbox is itself
a semantic leaf.

Descriptor and value are later semantic roles on those mapped columns. A table
may ultimately have more than one descriptor column, and a terminal node may
remain role-unknown when structural evidence is insufficient. The current
`ColumnHeaderSchema` builder still marks physical column zero as
`is_row_label_column = true` and the remaining columns as
`is_value_column = true`; this is an explicit implementation limitation to be
removed in Step 7 of the canonical positioned-evidence unification checklist,
not a physical-grid rule.

Terminal header nodes are inferred from:

1. an explicit physical-column index
2. body-row non-empty evidence
3. the header row closest to the body

If normalization supplies no usable header rows, or only title/caption-like
header rows, the schema builder may infer a local header stack from rows above
the first strongly numeric body row. This fallback should remain conservative:
it records diagnostics and raw cell evidence in `ColumnHeaderSchema` rather
than rewriting `NormalizedTable`.

The closest-to-body header row supplies the terminal label. If that cell is
blank, the label stays blank and the schema records a diagnostic. The parser
should not silently promote an upper spanning group to the leaf label unless no
leaf header row exists at all.

One geometric exception is a direct row-spanning leaf. When a column is blank
in the lowest leaf row, has a positioned label in an upper header row, and is
not covered by that row's multicolumn group, the upper label belongs directly
to that leaf. It must not be folded into an adjacent leaf or forced into the
spanning group. For example, a ten-column severity group may sit beside direct
`Mean PPD mm` and `SD` leaves whose labels are vertically shallower.

When a rule inside the header band separates upper text from lower leaf labels,
that rule is structural evidence. This includes partial horizontal rules that
span only the value columns. Rows below such a value-region rule form the leaf
header band; rows above it become group/statistic headers and must not be
concatenated into the leaf labels.

### Header Groups

Header groups are cells from higher header rows that span one or more leaf
columns. They preserve upper-header structure as explicit group records and
group-to-leaf relationships.

Common cases:

- repeated group labels across adjacent columns, such as `Severity of AL, %`
  repeated over statistic leaves
- sparse upper labels aligned over a repeated leaf-header sequence, such as
  `% (N)` / `95% CI` repeated under survey-cycle group labels
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
- source artifact; projected positioned evidence uses
  `header_structure_candidate`

The matching candidate is required in the canonical path. Missing candidates
or incomplete axes produce a fail-closed schema with diagnostics; they never
trigger reconstruction from normalized strings.

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
        "header_structure_candidate",
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

## Projection Rules

1. Match the candidate to the normalized table by `table_id`.
2. Require candidate header/body rows to equal the normalized region-owned rows.
3. Project exactly one schema leaf from each candidate leaf at the same
   canonical index.
4. Use cleaned candidate `base_text` for structural labels; derive
   parser-facing names only afterward.
5. Preserve candidate leaf, group, relationship, and evidence IDs so marker
   attachments remain joinable without another mapping layer.
6. Project each candidate group over exactly its candidate leaf coverage.
7. Retain positioned raw text and canonical bounds in schema evidence.
8. Derive body non-empty row indices as a non-operative view over the preserved
   normalized grid.
9. Return a diagnostic, zero-confidence schema when the candidate is missing,
   mismatched, or internally incomplete. Do not reconstruct a substitute
   header.

## Validation Rules

Validation requires:

- complete leaf coverage of `0..n_cols-1`
- leaf and evidence coordinates within the schema column axis
- every referenced evidence, leaf, and group ID to exist
- every group to span at least two contiguous leaves
- no crossing group spans
- exactly one group-to-leaf relationship for every projected group member
- relationship leaf indices to agree with their referenced leaves and groups

Invalid candidate projections remain explicit fail-closed artifacts. A
validation failure must not activate another builder or repair pass.

## Consumers

### `TableDefinition`

`TableDefinition` should use `ColumnHeaderSchema` to derive column descriptors:

- leaf label comes from `ColumnHeaderLeaf.leaf_label`
- shared context comes from related `ColumnHeaderGroup` labels
- per-column `header_path` comes from the schema's group path plus leaf label
- table-level `header_spans` preserve displayable multirow group and leaf spans
- `header_spans` include the row-label leaf, while semantic `DefinedColumn`
  records remain limited to value/statistic columns
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

The comparison view may canonicalize harmless display-fragment punctuation,
such as a standalone hyphen split across adjacent leaf-header fragments in
`(% - SE)`, while leaving the stored leaf labels, group labels, and evidence
unchanged. This supports continuation compatibility without merging physical
columns or rewriting `NormalizedTable`.

This is a consumer of the design, not the reason for the design.

### R Inspection

R helpers should be able to load:

- leaves as one data frame
- groups as one data frame
- relationships as one data frame
- evidence as one data frame

Printed R methods can show the tree view, but the loaded object should preserve
the flat records.

## Corpus Validation

The retained Phase J Step 5 checkpoint is
`outputs/testpapers_batch_phase_j_step5_final_20260715`. Across 28 PDFs and
91 source grids, candidate and schema structures agree exactly for 663 leaves,
115 groups, and 376 relationships, with no marker-node, evidence-reference,
coverage, or crossing-span mismatch.

Continuation reporting must count both outcomes of the compatibility gate. The
current corpus has 13 recognized continuation candidates: 12 accepted
integrations and one rejected candidate. The rejected candidate is
`periodontis2.pdf`, PDF pages 10–11, printed Table 1; its projected column
paths remain inconsistent, so it correctly fails closed.
