# Table Continuation Resolution Design

## Purpose

Some printed epidemiology tables span more than one extracted table fragment. A
continuation fragment may contain category levels whose parent variable was
printed only in the prior fragment. In those cases, row semantics cannot be
interpreted correctly until the fragments are resolved into one logical table.

This design promotes continuation handling from an inspection-only merged view
to a deterministic table-set refinement stage:

```text
NormalizedTable + ColumnHeaderSchema
-> ResolvedTableSet
-> TableProfile/TableDefinition
-> ParsedTable
```

The goal is not to merge arbitrary similar-looking tables. Resolution is only
attempted when the second fragment is already identified as a continuation of a
specific table, and when its columns are identical to or safely alignable with
the parent fragment.

## Current State

The parser writes a canonical resolved working set:

- `resolved_tables.json`

It also writes Table 1 continuation inspection artifacts:

- `table1_continuation_groups.json`
- `merged_table1_tables.json`

The parser also writes a first diagnostic column-compatibility artifact for
explicit `demographic_description` continuations:

- `table_continuation_column_checks.json`

These artifacts are useful for review, but they are not consumed by
`TableDefinition` or `ParsedTable`. The semantic parser consumes
`resolved_tables.json` instead.

The resolved stage exists because interpreting every extracted fragment
separately is insufficient when:

- the base fragment contains a categorical parent row
- the continuation fragment contains levels for that parent
- the continuation omits repeated headers
- the continuation repeats only partial headers
- the continuation has the same logical columns but slightly different detected
  grid coordinates

The semantic parser needs one best-current table list, not every extracted
fragment treated as a separate semantic table.

## Non-Goals

This stage must not:

- guess integrations between unrelated tables
- infer continuation solely from matching columns or row-label patterns
- invent parent labels or value columns
- use shading, fonts, or cosmetic PDF features as semantic evidence
- replace or discard raw extraction and normalization artifacts
- make R-side inspection the canonical source of parse behavior

R can provide rich review tools, but canonical resolution should happen in
Python so CLI outputs, persisted artifacts, tests, and downstream parsers use
the same table set.

## Core Model

The paper-level resolved table-set artifact is:

```text
outputs/papers/<paper_stem>/resolved_tables.json
```

`resolved_tables.json` contains:

- all promoted semantic tables used by downstream parsing
- continuation-resolution decisions
- column-alignment decisions
- a source-table index showing which normalized fragments were consumed,
  unchanged, or rejected

Raw `normalized_tables.json` remains the complete source record. The resolved
artifact is the shorter working set.

Conceptually:

```python
class ResolvedTableSet(BaseModel):
    source_artifact: str
    working_artifact: str
    resolved_tables: list[ResolvedTable]
    decisions: list[TableResolutionDecision]
    source_tables: list[SourceTableResolution]
    notes: list[str]


class ResolvedTable(BaseModel):
    table_id: str
    resolution_type: Literal["singleton", "integrated_continuation"]
    logical_table_number: int | None
    title: str | None
    caption: str | None
    table: NormalizedTable
    source_table_ids: list[str]
    row_provenance: list[ResolvedRowProvenance]
    integration_boundaries: list[IntegrationBoundary]
    column_schema_decisions: list[ColumnSchemaCompatibilityDecision]
    confidence: float
    notes: list[str]
```

The implemented schema contract lives in:

- `table1_parser/schemas/resolved_table.py`

The initial in-memory resolver lives in:

- `table1_parser/resolved_tables.py`

It creates singleton resolved-table records in source order, records
continuation identity evidence, records closest-parent selection decisions,
applies `ColumnHeaderSchema` compatibility, and creates integrated
resolved tables when column count and schema-derived comparison labels match.
It also records retained-row provenance, source-table index entries for
singletons/consumed fragments/rejected continuations, and keeps rejected
continuation candidates inspectable as singleton resolved tables with
diagnostics.
`table1-parser parse` writes this artifact and feeds resolved tables into
`TableProfile`, `TableDefinition`, and `ParsedTable` assembly.
The paper-footnote stage also consumes this final artifact. Anchors and
definitions on different source fragments share continuation scope only when
their source table IDs belong to the same accepted integrated resolved table.
Rejected continuation candidates cannot link across fragments merely because
they print the same table number. The older Table 1 continuation artifacts
remain review views and are not canonical footnote inputs.
Categorical levels that begin on an accepted continuation fragment are handled
by ordinary resolved-table row/level parsing: once the continuation body rows
are appended after a schema match, `TableDefinition` sees one row sequence and
can attach a boundary-leading row to an open categorical parent from the base
fragment only when at least one non-stub cell contains a compatible data value.
Stub-only informational text is not attached as a continuation level.

The embedded `table` should preserve the parser-facing `NormalizedTable` shape
so existing semantic builders can migrate with limited disruption:

```text
build_table_profiles(resolved_tables[*].table)
build_table_definitions(resolved_tables[*].table)
build_parsed_tables(resolved_tables[*].table, table_definitions)
```

## Resolution Flow

### 1. Start With All Normalized Fragments

The resolver receives the full ordered list of `NormalizedTable` objects.

No source table is removed from `normalized_tables.json`. Resolution only
creates a new working list and records how each source fragment participated.

### 2. Apply a Continuation Identity Gate

The resolver may only create an integration candidate when the later fragment
has clear continuation evidence for a specific table.

Accepted evidence can include:

- extractor metadata: `is_continuation = true`
- extractor metadata: `continuation_of_table_number = N`
- caption or title text such as `Table N (continued)`
- a continuation marker in the first normalized rows when it names the table
  number
- conservative adjacent-page continuation evidence already recorded by the
  extractor

Matching columns, matching row labels, or a plausible semantic continuation are
not enough by themselves.

If a continuation fragment cannot be tied to a specific earlier table, it is not
integrated. It remains a singleton resolved table with a diagnostic note such as
`orphan_continuation`.

### 3. Locate the Parent Fragment

For a continuation of `Table N`, the parent should be the closest earlier
non-continuation fragment for `Table N`, or the current integrated resolved
table for `Table N` if prior continuation fragments have already been accepted.

If multiple candidates exist, prefer the one with:

- same logical table number
- closest source order before the continuation
- compatible extraction orientation
- compatible page sequence
- compatible title or caption stem

Ambiguous parent selection should reject integration rather than pick a weak
candidate.

### 4. Check Column Schema Compatibility

Column compatibility is the first structural gate after continuation identity.
The resolver should not integrate row labels until the continuation grid can be
matched to the parent column schema.

```python
class ColumnSchemaCompatibilityDecision(BaseModel):
    base_table_id: str
    continuation_table_id: str
    status: Literal[
        "match",
        "rejected",
        "schema_missing",
    ]
    base_column_headers: list[str]
    continuation_column_headers: list[str]
    normalized_column_count_match: bool
    decision_reason: str
    warnings: list[str]
```

Compatibility must use `ColumnHeaderSchema` through the parser's column-header
tooling. The resolver must not reconstruct a separate header comparison from
normalized rows when the schema is missing or weak. Missing schema evidence is a
parser failure for this purpose and should reject integration with a structured
diagnostic.

Accepted evidence:

- explicit continuation identity
- same normalized column count
- matching schema-derived column headers

Rejected evidence:

- missing parent or continuation column schema
- different normalized column count
- different schema-derived column headers

### 5. Carry Forward Headers Only After Schema Match

Many continuation fragments omit repeated headers or print abbreviated headers.
Header carry-forward is allowed only after schema compatibility is accepted.

The continuation body should be projected onto the parent column model when:

- the continuation is an accepted continuation of the parent
- its schema-derived columns match the parent columns
- repeated continuation header rows can be dropped safely
- omitted headers can be inherited without changing value-column order

The resolver must not silently shift values into different column meanings.

### 6. Integrate Rows

Once identity and columns pass, the resolver can build one logical table.

The integrated table should:

- keep the base fragment's title, caption, header rows, and column structure
- append continuation body rows in source order
- drop continuation-only title, caption, and repeated-header rows
- record each dropped continuation row with a reason
- preserve every retained row's source table ID and source row index
- record source-boundary positions inside the integrated row sequence

Row integration should not assign semantics by itself. Its job is to present
one coherent normalized grid to the existing row and table-definition logic.

This matters because the row classifier can then see cases such as:

```text
<base fragment>
Education
  Less than high school
  High school/GED

<continuation fragment>
  More than high school
```

The continuation level should be visible after the parent row in the logical
table. The resolver should not synthesize a new `Education` row in the
continuation fragment.

At the semantic boundary, the first retained continuation row must contain a
compatible value in at least one data column before it can extend the open
parent variable. A row containing only stub text remains separate evidence or a
separate row; it is not treated as a level merely because it begins a continued
fragment.

### 7. Promote a Working Table Set

The resolver produces a shorter working list:

- accepted integrated continuations become one `ResolvedTable`
- source fragments consumed by an integrated continuation are marked
  `consumed_by`
- unrelated source fragments pass through as singleton `ResolvedTable` objects
- rejected continuation candidates pass through as singleton tables with
  diagnostics

`TableDefinition` and `ParsedTable` should consume only `resolved_tables`.

This is a promotion step, not a destructive deletion step. Inspection tools can
always look back to `normalized_tables.json` and the provenance maps.

## Source Table Index

Each source normalized table should have one source-index entry:

```python
class SourceTableResolution(BaseModel):
    source_table_id: str
    source_table_index: int
    source_page_num: int | None
    role: Literal[
        "singleton",
        "base_fragment",
        "continuation_fragment",
        "rejected_continuation",
    ]
    resolved_table_id: str | None
    consumed_by: str | None
    decision_id: str | None
    notes: list[str]
```

This lets review tools answer:

- Which extracted fragments became the semantic table?
- Which fragments were left alone?
- Which continuation fragments were rejected?
- Why was a source table not parsed independently?

## Semantic Diagnostics

After structural resolution, the parser can compare semantic diagnostics for
the integrated table against the unintegrated fragments. This should be a
secondary confidence check, not the primary merge gate.

Useful diagnostics include:

- fewer level rows without a preceding parent
- fewer categorical parents with no levels
- lower unknown-row fraction
- preserved or improved column-role confidence
- no new value-column shape failures
- no duplicated repeated-header rows in the body

If semantic diagnostics get worse, the resolver may reject the candidate even
when structural gates pass.

## Python and R Responsibilities

Python should own canonical resolution because it determines which table grid is
passed to semantic parsing and persisted parse outputs.

R should provide inspection helpers over `resolved_tables.json`, such as:

- print the working table list
- show source fragments consumed by a resolved table
- display column alignment as data frames
- compare original and resolved row grids
- jump from a resolved row to source table/page/row
- summarize rejected continuation candidates and reasons

R may be useful for prototyping review views, but it should not create an
alternate canonical table list that differs from Python outputs.

## Failure Modes

The resolver should fail closed.

Reject integration when:

- continuation identity is weak or absent
- parent table is missing or ambiguous
- column schemas are missing or incompatible
- continuation appears rotated or transformed differently from the parent in a
  way that cannot be normalized
- continuation rows look like a new table rather than a continuation body
- accepting the merge would create duplicate or shifted value columns

Rejected candidates should still be recorded in `resolved_tables.json`.

## Implementation Sequence

1. Define Pydantic models for resolved table sets, source-table roles,
   integration decisions, row provenance, and column alignment.
2. Replace the inspection-only continuation pair with, or add alongside it, a
   single `resolved_tables.json` artifact.
3. Initially support explicit continuations only.
4. Initially require exact or conservative alignable column compatibility.
5. Make `TableProfile`, `TableDefinition`, and `ParsedTable` consume the
   resolved working table list.
6. Preserve compatibility inspection outputs temporarily if useful, but keep
   them as source-fragment review views. They must not become alternate inputs
   to `TableDefinition` or `ParsedTable`.
7. Add R inspection helpers for resolved tables and column alignment decisions.

When this flow becomes implemented behavior, update:

- `docs/design/paper_parse_walkthrough.md`
- `docs/design/parsing_output_design.md`
- R inspection documentation
- CLI artifact tests

## Required Tests

Minimum regression coverage should include:

- explicit continuation with matching coordinates is promoted
- explicit continuation with shifted value columns is rejected
- continuation without repeated headers uses parent headers only after column
  alignment passes
- category levels in a continuation attach to a parent row from the base
  fragment after downstream table-definition parsing
- unrelated tables with similar columns are not considered for integration
- source row provenance maps every resolved row to the original table and row
- rejected continuations remain inspectable
- missing coordinate evidence requires strict fallback header/text evidence
- multi-page continuations preserve source order and boundary metadata
