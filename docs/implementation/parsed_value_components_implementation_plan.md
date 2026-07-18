# Parsed Value Components Implementation Plan

This document is the step-through implementation plan for adding first-class
parsed value components to the Table 1 parser.

The design contract is:

- `docs/design/parsed_value_components.md`
- `docs/design/value_parsing_spec.md`
- `docs/design/observed_tableone_component.md`

The local tableone reference implementation is:

- `/Users/robert/Projects/Epiconnector/tableone`

Runtime compatibility can also be checked against the installed R package with:

```r
library(tableone)
packageVersion("tableone")
```

## Goal

Store each printed cell as typed numeric/text components while preserving the
raw printed cell string.

Examples:

- `34 (45%)` becomes separate `count` and `percent` components.
- `52.1 (11.3)` becomes separate primary and uncertainty components, then is
  interpreted as `mean` plus `sd` or `estimate` plus `se` only when table or row
  context supports that interpretation.
- `<0.001` becomes a `p_value` component with relation `<`.

The raw value remains canonical. Formatted strings such as `n (%)` or
`mean (SD)` are display views over components, not the stored truth.

## Progress Checklist

Use this checklist to track progress across sessions.

- [ ] Phase 0: lock in early pipeline placement and diagnostic hook points.
- [x] Phase 1: add Python schemas for parsed cell values and components.
- [x] Phase 2: build the source-cell component parser.
- [x] Phase 3: write `parsed_cell_values.json` from `table1-parser parse`.
- [x] Phase 4: redesign the semantic value layer around components.
- [x] Phase 5: keep component validation lean.
- [x] Phase 6: defer per-column profile/anomaly artifacts.
- [x] Phase 7A: remove scalar compatibility aliases from canonical values.
- [ ] Phase 7: decide and, if needed, build a component-native R inspection view.
- [ ] Phase 8: usage review before adding display helpers.
- [ ] Phase 9: add known-failure regression fixtures.
- [ ] Phase 10: update user-facing and architecture docs.
- [ ] Acceptance criteria met.

## Tableone Compatibility Target

The local `tableone` package stores components separately and renders display
strings late:

- `TableOne` is a list with `ContTable`, `CatTable`, and `MetaData`.
- `CatTable` level data stores `freq` and `percent` separately.
- `ContTable` stores fields such as `mean`, `sd`, `median`, `p25`, `p75`,
  `min`, and `max` separately.
- print helpers create strings such as `freq (percent)`, `mean (SD)`, and
  `median [IQR]` only for display.

`parseTable1` should follow that separation without trying to reconstruct
subject-level data or a literal upstream `CreateTableOne()` call.

## Non-Goals

Do not:

- replace `raw_value` with normalized display text
- duplicate variable names, level labels, or column labels inside
  `parsed_cell_values.json`
- infer row or column semantics inside the source-cell component artifact
- make `ParsedTable.values` a breaking schema migration in the first pass
- solve ambiguous `x (y)` cells with paper-specific vocabulary shortcuts
- force every printed percentage to behave like a within-column percentage

## Architecture Rule

Value parsing remains separate from extraction, normalization, row semantics,
column semantics, and validation.

The intended flow is:

```text
ExtractedTable
-> NormalizedTable
-> ColumnHeaderSchema
-> parsed_cell_values.json
-> TableDefinition
-> ParsedTable component join
-> optional component-native R inspection view
```

For continuation work, source-cell components are parsed before semantic table
fragments are joined. Continuation integration should remap component records by
source row and column provenance instead of reparsing rendered strings.

This placement is intentionally early. Component parsing should happen after the
parser knows the canonical value columns from `ColumnHeaderSchema`, but before
row-variable integration and before `ParsedTable` joins values to semantic row
and column labels. That gives later diagnostics access to printed cell
components without forcing those diagnostics to depend on a completed semantic
parse.

## Current State

Current Python value parsing lives mostly in:

- `table1_parser/parse/value_parser.py`
- `table1_parser/heuristics/value_pattern_detector.py`
- `table1_parser/schemas/parsed_table.py`

Current canonical `ValueRecord` uses typed `components` plus row/column
semantics and source provenance. Scalar compatibility aliases such as
`value_type`, `parsed_numeric`, and `parsed_secondary_numeric` are intentionally
not part of the canonical model.

Current R observed-table construction lives mainly in:

- `R/observed_table_one.R`

It currently consumes `parsed_tables.json` and projects the two numeric slots
into `ContTable`, `CatTable`, and `statistics`-like lists.

## Phase 0: Pipeline Placement And Diagnostic Hooks

Checklist:

- [ ] Confirm `ColumnHeaderSchema` is available before component parsing.
- [ ] Define component parsing as a source-table operation over
  `NormalizedTable` body cells and schema-derived value columns.
- [ ] Keep component parsing independent of `TableDefinition` row-variable
  semantics.
- [ ] Add a stable in-memory bundle field for `parsed_cell_values`.
- [ ] Add a future-facing diagnostics interface that can consume component
  records by source table and column.
- [ ] Document that full typo/error detection is a later diagnostics layer, not
  part of the first component parser.

Diagnostic hook shape:

- a column-level component profile can summarize component patterns by
  `source_table_id` and `col_idx`
- profile entries should use `ColumnHeaderSchema` leaf IDs where available
- profile entries should store counts of component kinds, parse patterns,
  missing/not-estimable cells, unparsed cells, and relation-bearing p-values
- future anomaly detectors can compare profiles within a table column, across
  sibling columns, or across continuation fragments
- anomaly output should be structured diagnostics, not corrected table data

Potential future anomaly examples:

- a mostly `count` plus `percent` column contains one impossible free-text cell
- a mostly `estimate` plus `se` column contains one `count` plus `percent` cell
- a categorical block has one sibling level whose percent is implausible for
  the available denominator
- one subgroup column has a different component pattern from its sibling
  columns
- a p-value column contains non-p-value cells outside known blank/header rows

These hooks are meant to support later paper typo/error review while preserving
the parser's rule that raw extracted values are not silently corrected.

## Phase 1: Add Python Schemas

Checklist:

- [x] Add `table1_parser/schemas/parsed_cell_value.py`.
- [x] Add `ValueComponentKind`.
- [x] Add `ValueRelation`.
- [x] Add `ValueComponent`.
- [x] Add `ParsedCellValue`.
- [x] Export new models from `table1_parser/schemas/__init__.py`.
- [x] Add schema serialization tests.

Phase 1 completion note:

- schema-level field constraints and controlled vocabularies are in place
- cross-artifact validation, such as table ID matching and row/column range
  checks against `NormalizedTable`, is implemented in Phase 5

Add a dedicated schema module, likely:

```text
table1_parser/schemas/parsed_cell_value.py
```

Add models:

```python
ValueComponentKind = Literal[
    "count",
    "percent",
    "mean",
    "sd",
    "median",
    "q1",
    "q3",
    "min",
    "max",
    "estimate",
    "se",
    "p_value",
    "missing",
    "text",
    "unknown",
]

ValueRelation = Literal["=", "<", "<=", ">", ">="]
```

```python
class ValueComponent(BaseModel):
    kind: ValueComponentKind
    value: float | str | None = None
    raw_fragment: str | None = None
    relation: ValueRelation | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)
```

```python
class ParsedCellValue(BaseModel):
    source_table_index: int = Field(ge=0)
    source_table_id: str
    row_idx: int = Field(ge=0)
    col_idx: int = Field(ge=0)
    raw_value: str
    parse_pattern: str | None = None
    components: list[ValueComponent] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)
```

Export these models from `table1_parser/schemas/__init__.py`.

Validation rules:

- [ ] `source_table_index` points to an existing normalized source table.
- [ ] `source_table_id` matches that table.
- [ ] `row_idx` and `col_idx` are in range.
- [ ] `raw_value` matches the corresponding normalized cell text after the same
  parser-facing cleaning view used by existing value parsing.
- [ ] non-empty parsed records have at least one component.
- [ ] numeric component values are numeric JSON values, not formatted strings.
- [ ] inequality signs live in `relation`, not in `kind`.

## Phase 2: Build A Component Parser

Checklist:

- [x] Add `table1_parser/parse/cell_value_components.py`.
- [x] Add `parse_cell_value_components(...)`.
- [x] Add `build_parsed_cell_values(...)`.
- [x] Add `parsed_cell_values_to_payload(...)`.
- [x] Reuse canonical text cleaning and existing value-pattern detection.
- [x] Preserve raw cell text exactly in the output record.
- [x] Emit conservative notes for ambiguous `x (y)` cells.

Phase 2 completion note:

- component parsing is available as an in-memory parser API
- source-indexed `ParsedCellValue` records can be built from `NormalizedTable`
  body rows with optional value-column filtering
- `parsed_cell_values.json` is not written yet; that remains Phase 3 work

Add a parser module, likely:

```text
table1_parser/parse/cell_value_components.py
```

Add focused public functions:

- `parse_cell_value_components(...)`
- `build_parsed_cell_values(...)`
- `parsed_cell_values_to_payload(...)`

Reuse:

- `table1_parser.text_cleaning.clean_text`
- `table1_parser.heuristics.value_pattern_detector.detect_value_pattern`

Initial cell shapes to support:

- [x] integer/count only: `412`
- [x] count and percent: `412 (48.2)` and `412 (48.2%)`
- [x] mean or estimate with parenthesized uncertainty: `52.3 (14.1)`
- [x] mean or estimate with plus/minus uncertainty: `52.3 +/- 14.1`,
  `52.3 ± 14.1`
- [x] PDF plus/minus extraction artifact: `25.9 6 3.6`
- [x] dash-separated uncertainty: `47.2 - 2.1`
- [x] median with IQR: `52.3 (40.1, 65.2)` and later bracket variants
- [x] p-values with optional relation: `<0.001`, `p=0.02`
- [x] missing or not-estimable tokens: `NA`, `N/A`, `not estimable`, `-`
- [x] free text fallback

Important ambiguity rule:

- A source-cell parser should recognize the shape of `52.3 (14.1)`, but should
  not always force `sd` versus `se` without supporting row, header, or table
  context.
- If the context is not available, emit conservative components and notes, or
  use `estimate` plus `unknown` rather than pretending the second value is known
  to be an SD.
- Later semantic attachment can refine `estimate`/`unknown` to `mean`/`sd` or
  `estimate`/`se` using `TableDefinition.summary_style_hint`,
  `ColumnHeaderSchema`, statistic-column roles, or other structural context.

Do not add disease names, journal names, survey names, or one-paper labels to
decide component structure.

## Phase 3: Write `parsed_cell_values.json`

Checklist:

- [x] Add `parsed_cell_values` to the parse artifact bundle.
- [x] Build component records after `ColumnHeaderSchema` creation.
- [x] Write `outputs/papers/<paper_stem>/parsed_cell_values.json`.
- [x] Keep `parsed_tables.json` unchanged in this phase.
- [x] Update CLI tests to assert that the artifact is written.

Phase 3 completion note:

- `table1-parser parse` now writes `parsed_cell_values.json`
- component records are built from normalized body rows and
  `ColumnHeaderSchema` value leaves
- at Phase 3 completion, the existing `parsed_tables.json` writer remained
  unchanged; Phase 4 has since migrated it to a component-aware semantic value
  layer

Add a new parse artifact:

```text
outputs/papers/<paper_stem>/parsed_cell_values.json
```

The artifact should be a flat list of `ParsedCellValue` records.

Selection rule:

- [x] emit records for non-empty source cells in source normalized table body
  rows
- [x] restrict to parser value columns using `ColumnHeaderSchema` leaves when
  available
- [x] preserve source row and column indices exactly
- [x] do not attach variable names, level labels, column names, or header paths

CLI changes:

- [x] extend the parse artifact bundle with `parsed_cell_values`
- [x] write `parsed_cell_values.json` in `table1-parser parse`
- [x] keep existing `parsed_tables.json` output unchanged
- [x] update CLI tests to assert that the new artifact is written

## Phase 4: Redesign The Semantic Value Layer

Checklist:

- [x] Decide the new canonical semantic value schema.
- [x] Decide whether the schema lives inside `ParsedTable.values`, alongside it,
  or in a new joined semantic artifact.
- [x] Preserve source provenance from `ParsedCellValue` records in the semantic
  value layer.
- [x] Attach row-variable, level, and column semantics by joining to
  `TableDefinition` and `ColumnHeaderSchema`.
- [x] Store typed components as the semantic payload instead of forcing values
  into two numeric slots.
- [x] Remove legacy two-slot aliases from the canonical value schema.
- [x] Move or redesign count-percent consistency checks so they operate on
  components rather than old `parsed_numeric` slots.
- [x] Update tests around the chosen semantic value contract.

This phase is a design migration, not a compatibility-preservation task.
Backward compatibility is useful only if it does not block the right data
structure. The previous `ValueRecord` shape is too narrow to be the canonical
model for printed Table 1 values.

Preferred direction:

- `parsed_cell_values.json` remains the early source-grid component artifact
- the semantic value layer should be a joined view over those components
- each semantic value record should preserve source table, row, and column
  provenance
- row-variable and level semantics should come from `TableDefinition`
- column semantics should come from `ColumnHeaderSchema` /
  `TableDefinition.column_definition`
- typed components should remain explicit and structured

Candidate semantic value record shape:

```python
class SemanticValueRecord(BaseModel):
    source_table_index: int
    source_table_id: str
    row_idx: int
    col_idx: int
    variable_name: str | None = None
    variable_label: str | None = None
    level_label: str | None = None
    column_name: str | None = None
    column_label: str | None = None
    header_leaf_id: str | None = None
    raw_value: str
    parse_pattern: str | None = None
    components: list[ValueComponent] = Field(default_factory=list)
    confidence: float | None = None
    notes: list[str] = Field(default_factory=list)
```

Open design decisions:

- `ValueRecord` remains the model name for now, but its contract is now a
  component-aware semantic value record.
- The semantic value schema lives inside `ParsedTable.values`.
- Scalar compatibility aliases are removed from the canonical payload.
- R code should consume `components` directly if a component-native inspection
  view is built.
- Statistic columns such as p-values use typed components where possible;
  future SMD-specific semantics can extend the same component structure.

What is not required:

- preserving exact old `parsed_tables.json` shape if it blocks the better
  component design
- forcing `count` plus `percent`, `estimate` plus `se`, or median/IQR cells into
  two slots
- treating composite strings such as `mean_sd` or `count_pct` as the semantic
  payload

## Phase 5: Keep Component Validation Lean

Checklist:

- [x] Use explicit typed records for component shape and controlled component
  kinds.
- [x] Preserve explicit source table, row, column, raw value, parse pattern,
  confidence, and notes on every parsed source-cell value.
- [x] Do not add a separate validation-report artifact or strict validation
  class without a known failure mode that requires it.
- [x] Keep parser-facing validation close to the code path that creates or joins
  values.

Phase 5 completion note:

- The separate parsed-cell validation module was removed during scope cleanup.
- Component records rely on the schema plus explicit source indices rather than
  a second validation/reporting subsystem.

## Phase 6: Defer Per-Column Profile And Anomaly Artifacts

Checklist:

- [x] Remove the implemented `parsed_value_column_profiles.json` sidecar.
- [x] Remove the `ParsedValueColumnProfile` and anomaly schema classes.
- [x] Keep later typo/error review as a future consumer of
  `parsed_cell_values.json`, `ColumnHeaderSchema`, and `ParsedTable.values`.
- [x] Do not add per-column profile helpers until real paper review identifies
  concrete repeated checks.

Phase 6 completion note:

- The component layer itself is the current hook for future column assessment.
- Dedicated column-profile or anomaly artifacts are deferred until known review
  failures justify them.

## Phase 7A: Remove Scalar Compatibility Aliases

Checklist:

- [x] Remove `value_type` from canonical `ValueRecord`.
- [x] Remove `parsed_numeric` from canonical `ValueRecord`.
- [x] Remove `parsed_secondary_numeric` from canonical `ValueRecord`.
- [x] Remove component-to-scalar projection code from Python parsed-table
  assembly.
- [x] Remove obsolete scalar parser tests.
- [x] Update Python tests to assert component values directly.
- [x] Update parse-output docs to state that `components` is the only canonical
  value payload.

Phase 7A completion note:

- `ParsedTable.values[*].components` is now the only parsed value payload in
  the canonical Python schema.
- Evidence and provenance remain: source table, source row/column, raw printed
  value, parse pattern, header path, confidence, and notes.
- R code that still expects old scalar fields is intentionally treated as a
  future migration target, not a constraint on the canonical parser schema.

## Phase 7: Decide On A Component-Native R Inspection View

This phase is optional. `ObservedTableOne` is the current R-side inspection
object, not the parser's conceptual model. It matters only if we want an
R-native review/export surface for printed Table 1 artifacts.

Checklist:

- [ ] Decide whether `ObservedTableOne` remains the right R object name and
  shape, or whether a smaller component-native inspection view is preferable.
- [ ] If R work proceeds, consume canonical `components` from `parsed_tables.json`
  directly.
- [ ] Do not require `parsed_numeric`, `parsed_secondary_numeric`,
  `parsed_count`, `parsed_percent`, or other scalar compatibility aliases.
- [ ] Preserve evidence and provenance needed for review: source table, row,
  column, raw value, parse pattern, header identity, components, confidence, and
  notes.
- [ ] Treat `parsed_cell_values.json` as an optional inspection sidecar, not an
  alternate truth state.
- [ ] Do not add matrix/helper functions until real component-artifact usage
  shows which views are repeatedly needed.

The R object should mirror tableone's useful separation of data components
without claiming to be a subject-level `CreateTableOne()` result, but this is a
design principle rather than a requirement to implement R helpers now.

## Phase 8: Usage Review Before Adding Display Helpers

Do not implement R display helpers in this phase. We need real use of the
component-native artifacts before deciding which helper views are actually
worth maintaining. Avoid adding many small specialized functions whose behavior
is only motivated by one hypothetical display need.

Checklist:

- [ ] Run component-native outputs on a small set of real papers already used
  during parser review.
- [ ] Record concrete review tasks that are hard with raw values plus
  components.
- [ ] Decide whether any helper should be a general view over components rather
  than a narrow function for one printed format.
- [ ] Keep `raw_value` as the source-of-record for inspection and comparison.
- [ ] Defer R rendering helpers until repeated usage shows that they remove real
  review friction.

Possible later helper directions, only if usage supports them:

- a compact component summary for one parsed table
- a general component matrix view by component kind
- a normalized display renderer for comparison/export after its requirements are
  clear

## Phase 9: Known-Failure Regression Fixtures

This phase is not a broad unit-test expansion. The goal is to protect the
specific failures and structural variants that motivated the component parser,
using examples that would catch real parser regressions. Add tests only when
they encode a known failure, a documented real-paper pattern, or a core artifact
contract that would be costly to break silently.

Checklist:

- [ ] Identify the real or minimal extracted-table examples that exposed known
  failures.
- [ ] Add regression fixtures for the component patterns that currently matter:
  `n (%)`, `x (y)`, p-values with relations, missing/not-estimable cells, and
  plus/minus uncertainty when those patterns have caused real failures.
- [ ] Add parse-level regression coverage for artifact presence and source
  provenance only where a silent break would damage downstream review.
- [ ] Add semantic-value regression coverage for the component-native
  `ParsedTable.values` contract, especially that scalar compatibility aliases
  do not return.
- [ ] Add column-level diagnostic regression coverage only after those
  diagnostics are designed from known review failures.
- [ ] Do not add R tests until an R inspection surface is deliberately designed
  from real usage.
- [ ] Do not add tests simply to cover every helper or branch.

Optional local compatibility check:

```r
library(tableone)
d <- data.frame(
  g = factor(c("A", "A", "B", "B", "B")),
  age = c(10, 12, 20, 22, 24),
  sex = factor(c("F", "M", "F", "F", "M"))
)
x <- CreateTableOne(
  vars = c("age", "sex"),
  strata = "g",
  data = d,
  factorVars = "sex",
  addOverall = TRUE
)
names(x)
colnames(x$ContTable[[1]])
names(x$CatTable[[1]][[1]])
```

This should remain an implementation reference for data-structure separation,
not a hard dependency for Python regression fixtures and not a reason to add R
helper work before usage demands it.

## Phase 10: Documentation Updates

Checklist:

- [ ] Update parse output documentation.
- [ ] Update paper parse walkthrough.
- [ ] Update observed tableone component documentation.
- [ ] Update R visualization documentation.
- [ ] Update parser ToDo with completed and remaining component work.

When implemented, update:

- [ ] `docs/design/parsing_output_design.md`
- [ ] `docs/design/paper_parse_walkthrough.md`
- [ ] `docs/design/observed_tableone_component.md`
- [ ] `docs/implementation/parser_todo.md`
- [ ] `docs/r_visualization.md`

If the parse command writes `parsed_cell_values.json`, document the artifact in
the parse output list and in the paper-level walkthrough.

If an R inspection view is changed or replaced, document the component-native
fields and any display-only views it creates from canonical components.

## Acceptance Criteria

The first complete implementation is done when:

- [ ] `table1-parser parse` writes `parsed_cell_values.json`
- [ ] `parsed_tables.json` or its successor has a deliberate component-aware
  semantic value contract
- [ ] raw values are unchanged in existing artifacts
- [ ] `ParsedCellValue` records are index-keyed and do not duplicate row or column
  semantic labels
- [ ] future column-level diagnostics remain driven by known review failures,
  not hypothetical helper surfaces
- [ ] known-failure regression fixtures pass
- [ ] docs and parser ToDo are updated

## Later Migration

After the additive artifact is stable, consider a deliberate schema migration:

- make `ParsedTable.values` a semantic joined view over components
- add continuation-aware remapping from source component records to integrated
  table rows
- add richer validation reports for denominator logic, weighted estimates,
  not-estimable cells, and conflicting component interpretations
- add optional export adapters for closer tableone-like R displays

Do not perform that migration in the first pass.
