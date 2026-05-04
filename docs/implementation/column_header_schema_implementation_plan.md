# Column Header Schema Implementation Plan

This document turns `docs/design/column_header_schema.md` into an implementation
sequence.

The goal is to add a parser-native column header schema artifact before
investing more in downstream projection objects. The first implementation should
make column structure inspectable and testable. Later phases can make it
parser-critical.

## Design Inputs

Read these before implementation:

- `docs/design/column_header_schema.md`
- `docs/design/parsing_output_design.md`
- `docs/design/paper_parse_walkthrough.md`
- `docs/design/table_definition_schema.md`
- `docs/implementation/parser_todo.md`

The implementation must preserve the existing separation:

```text
ExtractedTable -> NormalizedTable -> ColumnHeaderSchema -> TableDefinition -> ParsedTable
```

## Current Code Touchpoints

The main implementation seams are:

- `table1_parser/schemas/__init__.py`
  Export the new Pydantic models.
- `table1_parser/schemas/column_header_schema.py`
  New canonical schema models.
- `table1_parser/column_header_schema.py`
  New deterministic assembly and payload serialization functions.
- `table1_parser/validation/column_header_schema.py`
  New structural validation for schema integrity.
- `table1_parser/cli.py`
  Build and write `column_header_schemas.json`.
- `table1_parser/heuristics/table_definition_columns.py`
  Later refactor so `TableDefinition` consumes `ColumnHeaderSchema` instead of
  independently flattening headers.
- `table1_parser/table_continuation_columns.py`
  Later consumer for schema-based compatibility checks.
- `R/inspect_paper_outputs.R` and related R helpers
  Later inspection support once the JSON contract is stable.

## Phase 1: Schema And Validator

Add `table1_parser/schemas/column_header_schema.py` with the canonical models
from the design:

- `ColumnHeaderCellEvidence`
- `ColumnHeaderLeaf`
- `ColumnHeaderGroup`
- `ColumnHeaderRelationship`
- `ColumnHeaderSchema`

Implementation details:

- Use Pydantic models and explicit literal vocabularies.
- Keep IDs as stable strings; do not rely on list position.
- Keep rows and columns in normalized-table index space.
- Include original row/column indices when known.
- Preserve raw text and bbox evidence when available.
- Represent missing evidence with `None` and diagnostics, not invented values.

Add exports in `table1_parser/schemas/__init__.py`.

Add `table1_parser/validation/column_header_schema.py` with one public function:

```python
def validate_column_header_schema(schema: ColumnHeaderSchema) -> ColumnHeaderSchema:
    ...
```

Validation should check:

- leaf column indices are within table bounds
- group spans are non-empty and contiguous
- relationship group and leaf IDs exist
- relationship leaf columns are included in the parent group
- referenced evidence IDs exist
- no duplicate IDs exist within one schema

Validation should raise for impossible internal schema construction in unit
tests. The builder should catch degraded input before it creates invalid models.

Tests:

- `tests/test_schemas.py`
  Smoke test creation and JSON serialization.
- `tests/test_column_header_schema.py`
  Validator rejects invalid relationships, duplicate IDs, and out-of-range
  columns.

## Phase 2: Deterministic Builder, Artifact-Only

Add `table1_parser/column_header_schema.py` with public functions:

```python
def build_column_header_schema(
    table: NormalizedTable,
    extracted_table: ExtractedTable | None = None,
) -> ColumnHeaderSchema:
    ...

def build_column_header_schemas(
    tables: list[NormalizedTable],
    extracted_tables: list[ExtractedTable] | None = None,
) -> list[ColumnHeaderSchema]:
    ...

def column_header_schemas_to_payload(
    schemas: list[ColumnHeaderSchema],
) -> list[dict[str, object]]:
    ...
```

The first pass should be artifact-only. It should not change `TableDefinition`,
`ParsedTable`, continuation checks, or processing-status behavior.

Builder behavior:

1. Read `NormalizedTable.metadata["cleaned_rows"]`.
   If missing or malformed, return a degraded schema with leaves from `n_cols`,
   no groups, and diagnostics.
2. Choose `leaf_header_row_idx` from the header row closest to the body.
3. Create one leaf per normalized column.
4. Mark column `0` as the label column for the first implementation.
5. Use the leaf header row cell as `leaf_label`.
6. Use body rows to populate `body_nonempty_row_indices`.
7. Build evidence records from matching `ExtractedTable.cells` when possible.
8. Fall back to normalized cleaned-row evidence when raw cells or coordinates
   are unavailable.
9. Attach higher header rows as groups over leaf columns.
10. Build `flattened_signature` as a review and compatibility convenience.
11. Validate the schema before returning it.

Span inference should start conservatively:

- collapse adjacent repeated labels into `repeated_label_span` groups
- create `single_leaf_group` records for upper-row labels that clearly map to
  one leaf
- allow `single_cell_blank_span` only when a non-empty cell is followed by
  blanks and the inferred span ends before the next non-empty cell
- record diagnostics rather than forcing a span across ambiguous boundaries

Coordinate handling:

- prefer `ExtractedTable.cells[*].bbox`
- if unavailable, read `NormalizedTable.metadata["table_cells"]`
- if still unavailable, record `missing_coordinate_evidence`
- do not normalize page coordinates in the primary evidence record

Tests:

- simple one-row Table 1 header:
  `Characteristic`, `Overall`, `RA`, `P-value`
- multi-row grouped header:
  `Cobalt quartile` over `Q1` and `Q2`
- extra-wide repaired stack:
  `Severity -> >=3 mm -> %/SE`
- degraded no-header table
- non-descriptive/result-style table
- Eke-derived compact Table 1 and Table 2 slices

The Eke-derived tests should be compact normalized/extracted table fixtures, not
full paper artifacts or large JSON files.

## Phase 3: CLI Artifact

Extend `PaperParseArtifacts` in `table1_parser/cli.py` with:

```python
column_header_schemas: list[ColumnHeaderSchema]
```

Build the schemas immediately after normalization:

```text
extracted_tables -> normalized_tables -> column_header_schemas
```

Write:

```text
outputs/papers/<paper_stem>/column_header_schemas.json
```

The artifact should be a direct JSON array of
`ColumnHeaderSchema.model_dump(mode="json")` payloads.

After this phase, update:

- `docs/design/parsing_output_design.md`
- `docs/design/paper_parse_walkthrough.md`
- `docs/design/parsing_process.md`

Tests:

- CLI parse test confirms `column_header_schemas.json` is written.
- Output payload validates back into `ColumnHeaderSchema`.
- Artifact order matches `normalized_tables.json`.

Risk control:

- Do not change `table_definitions.json` or `parsed_tables.json` yet.
- Existing parse tests should continue to pass unchanged except for expected
  new output-file assertions.

## Phase 4: TableDefinition Consumer Refactor

Once the artifact is stable, refactor deterministic column assembly.

Change column-definition APIs in a backward-compatible way first:

```python
def build_column_definition(
    table: NormalizedTable,
    column_schema: ColumnHeaderSchema | None = None,
) -> ColumnDefinition:
    ...
```

Then thread schemas through:

```python
def build_table_definition(
    table: NormalizedTable,
    column_schema: ColumnHeaderSchema | None = None,
) -> TableDefinition:
    ...

def build_table_definitions(
    tables: list[NormalizedTable],
    column_schemas: list[ColumnHeaderSchema] | None = None,
) -> list[TableDefinition]:
    ...
```

`table_definition_columns.py` should convert a `ColumnHeaderSchema` into the
existing internal `HeaderDescriptor` concept:

- `leaf_label` comes from the leaf record
- `shared_context_label` comes from related group labels
- `column_label` is derived from group path plus leaf label
- row-label column is skipped using schema metadata

Keep the old direct-normalized-table path as a temporary fallback until tests
show schema-based output is stable.

Tests:

- existing `tests/test_table_definition.py` should still pass
- add explicit tests that TableDefinition column labels and group levels come
  from the schema, not from ad hoc header flattening
- add a regression where upper-row group labels must not replace blank leaf
  labels unless the table truly lacks a leaf header row

Documentation after this phase:

- Update `docs/design/table_definition_schema.md` if any persisted
  `TableDefinition` fields change.
- Update `docs/design/paper_parse_walkthrough.md` because the implemented parse
  flow now uses `ColumnHeaderSchema` to build `TableDefinition`.

## Phase 5: Continuation Compatibility Consumer

After `TableDefinition` uses the schema, update
`table1_parser/table_continuation_columns.py` to consume schema signatures and
relationships.

This phase should compare:

- leaf count
- row-label column
- leaf labels when present
- group paths for value columns
- schema evidence records

Tests:

- existing continuation column tests still pass
- one continuation with omitted repeated headers is accepted only when the
  schema-derived column signatures are compatible
- one continuation with incompatible schema-derived signatures remains incompatible

## Phase 6: R Inspection And Stored Summary Prep

After the JSON contract is stable, add R loading and inspection helpers.

R helper goals:

- load `column_header_schemas.json`
- expose leaves, groups, relationships, and evidence as data frames
- print a compact tree view without hiding inference in display code

Do not implement the full tableone projection in this phase. The immediate
tableone-facing goal is to make the column axis available to a future stored
summary object.

Future summary object requirements:

- reference `ColumnHeaderLeaf.leaf_id`
- reference `ColumnHeaderGroup.group_id` or relationship IDs where needed
- distinguish observed paper summaries from recomputed individual-level
  summaries
- store summary values before any print/render method formats them

## Test Fixture Strategy

Keep fixtures compact and in code where practical.

Do not check in:

- full Eke paper parse outputs
- large extracted-table JSON files
- large generated PDFs or logs

Preferred Eke fixtures:

- small `NormalizedTable` objects with 4 to 8 columns and 3 to 6 rows
- matching `ExtractedTable` cells only for header rows and one body row when
  coordinate provenance is needed
- hand-written bboxes with stable simple coordinates

Fixture coverage:

- Eke Table 1-like prevalence columns
- Eke Table 2-like case-definition group spans
- ordinary one-row descriptive tables
- multi-row grouped exposure headers
- repaired extra-wide value columns
- degraded no-header tables
- non-descriptive/result-style tables

## Verification Commands

Run focused tests while developing:

```bash
pytest tests/test_schemas.py tests/test_column_header_schema.py tests/test_table_definition.py tests/test_table_continuation_columns.py
```

Run broader parser checks before finalizing implementation:

```bash
pytest
```

For docs-only phases, at minimum run:

```bash
git diff --check
```

## Done Criteria

The implementation is complete when:

- `column_header_schemas.json` is written by `table1-parser parse`
- schema payloads validate as Pydantic models
- raw text and coordinates are preserved when available
- missing evidence is explicit in diagnostics
- `TableDefinition` consumes the schema for column descriptors
- continuation checks can use the schema without duplicating header flattening
- R can inspect the schema as structured leaves/groups/relationships/evidence
- docs describe the implemented parse flow and artifact contract

If the work is split across pull requests, the minimum useful first PR is:

- schema models
- deterministic artifact-only builder
- CLI output
- focused tests
- output and walkthrough docs updated
