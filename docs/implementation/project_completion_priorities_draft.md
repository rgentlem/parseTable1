# Project Completion Priorities Draft

This is a draft project-level review of the largest remaining work needed to
move `parseTable1` toward completion. It is based on the current parser TODOs,
design documents, and the latest real-paper corpus run.

This is primarily a review document for discussion and revision. Priority 1
also includes a checkbox implementation outline because it is the next chosen
work item.

## Evidence Used

- `docs/implementation/parser_todo.md`
- `docs/design/table_continuation_resolution.md`
- `docs/implementation/continued_variable_integration_implementation_spec.md`
- `docs/design/multitable_architecture_spec.md`
- `docs/implementation/multitable_implementation_plan.md`
- Testpaper batch run:
  - corpus: `/Users/robert/Projects/Epiconnector/testpapers`
  - output: `outputs/testpapers_batch_20260629_140704`
  - PDFs: 27
  - command-level failures: 0

The batch run shows that the parser now runs across the corpus, but table-level
completion is still mixed:

```text
table_processing_status:
  ok: 39
  rescued: 36
  failed: 12

table_profiles:
  descriptive_characteristics: 33
  estimate_results: 20
  unknown: 34

paper_table_categories:
  demographic_description: 33
  analysis_outputs: 28
  data_presentation: 9
  non_table_artifact: 8
  general: 2
  unknown: 7
```

## 1. Make Continuations Semantically Real

The parser now writes a resolved continuation working set consumed by
`TableDefinition` and `ParsedTable`. The remaining continuation work is mainly
hardening downstream status/diagnostic behavior and proving difficult
real-paper cases.

The current state includes:

- `table1_continuation_groups.json`
- `merged_table1_tables.json`
- `table_continuation_column_checks.json`
- `continued_variable_integrations.json`

These remain useful review artifacts, while `resolved_tables.json` is now the
semantic working table list.

Completion likely requires a canonical resolved table stage:

```text
NormalizedTable + ColumnHeaderSchema -> ResolvedTableSet -> TableProfile/TableDefinition -> ParsedTable
```

The hard parts are:

- deciding when a continuation fragment is truly part of a prior table
- using `ColumnHeaderSchema` as the compatibility gate
- preserving row and source-table provenance through integration
- carrying headers forward only after column compatibility is established
- making value parsing consume integrated rows rather than page-level fragments
- keeping `normalized_tables.json` as full source evidence while using a
  shorter resolved working set for semantic parsing

This is completion-scale because it changes the main parser input to semantic
stages, not just a downstream display.

### Implementation Checklist

Goal: promote continued-table handling from inspection artifacts to the
canonical working table set consumed by semantic parsing, while preserving
`normalized_tables.json` as full source evidence.

#### Design Contract

- [x] **G1.1** Confirm that the new working stage is
  `NormalizedTable + ColumnHeaderSchema -> ResolvedTableSet -> TableProfile/TableDefinition -> ParsedTable`.
- [x] **G1.2** Define a Pydantic `ResolvedTableSet` schema with explicit records for
  resolved tables, source-table participation, integration boundaries,
  resolution decisions, column-compatibility decisions, and row provenance.
- [x] **G1.3** Decide the persisted artifact name and shape, expected to be
  `resolved_tables.json`, and document that it is the semantic working set.
- [x] **G1.4** Keep `normalized_tables.json` unchanged as the complete normalized source
  record.
- [x] **G1.5** Treat the current continuation artifacts as review/provenance inputs or
  derived views, not as alternate semantic table lists.

Implementation note: G1.1-G1.5 are implemented as the schema and artifact
contract in `table1_parser/schemas/resolved_table.py`,
`docs/design/codex_build_spec.md`, `docs/design/parsing_process.md`,
`docs/design/table_continuation_resolution.md`, and
`docs/design/parsing_output_design.md`. Later checked steps wired the artifact
into the parse command and semantic parser inputs.

#### Resolver Behavior

- [x] **G1.6** Build a resolver that starts from all normalized tables in source order
  and returns a shorter resolved working list.

Implementation note: G1.6 is implemented in
`table1_parser/resolved_tables.py` as a source-order
resolver. It creates `ResolvedTableSet`, `ResolvedTable`,
`SourceTableResolution`, `TableResolutionDecision`, and row-provenance records
for every normalized source table. Later checked steps now add continuation
identity, parent selection, column gates, row integration, provenance, and
fail-closed rejected continuation handling.
- [x] **G1.7** Require a continuation identity gate before considering integration:
  explicit extractor metadata, explicit `Table N (continued)` evidence, or the
  already narrow adjacent-page continuation evidence.

Implementation note: G1.7 records continuation identity evidence inside
`build_resolved_table_set()` for explicit continuation metadata, explicit
`Table N (continued)` title/caption or leading-row text, and uncaptained
adjacent-page fragments after a numbered table. These candidates still fail
closed to singleton resolved tables with `rejected_continuation` decisions until
G1.8-G1.15 implement parent selection, column compatibility, and row
integration.
- [x] **G1.8** Locate the closest compatible parent fragment for the same logical table
  number, rejecting ambiguous parent choices.

Implementation note: G1.8 records parent selection in continuation decisions.
The resolver selects the closest earlier non-continuation source table with the
same logical table number when page order and available orientation metadata are
compatible. It rejects missing or ambiguous parent choices, including multiple
same-number parent candidates on the same closest source page. Candidates still
remain singleton resolved tables until column compatibility and row integration
are implemented.
- [x] **G1.9** Use `ColumnHeaderSchema` as the only column compatibility model.
- [x] **G1.10** Reject integration with a structured diagnostic when parent or
  continuation column schemas are missing, weak, or incompatible.
- [x] **G1.11** Carry forward parent headers only after the column-schema compatibility
  decision is accepted.
- [x] **G1.12** Append continuation body rows in source order, dropping only
  continuation-only title/caption/repeated-header rows with recorded reasons.

Implementation note: G1.9-G1.12 are implemented in
`build_resolved_table_set()`. The resolver accepts an optional
`column_header_schemas` list, compares parent and continuation columns only via
`ColumnHeaderSchema`, records `ColumnSchemaCompatibilityDecision`, rejects
missing or mismatched schemas, and integrates a continuation only after column
count and schema-derived comparison labels match. Accepted continuations replace
the parent singleton with an integrated resolved table that keeps parent
headers, appends continuation `body_rows`, and records dropped continuation
non-body rows in an `IntegrationBoundary`.
- [x] **G1.13** Preserve every retained row's source table ID, source table index, source
  row index, and page evidence when available.
- [x] **G1.14** Record consumed fragments, rejected continuation candidates, and singleton
  tables in one source-table index.
- [x] **G1.15** Fail closed: rejected or orphaned continuation fragments remain
  inspectable as singleton resolved tables with diagnostics.

Implementation note: G1.13-G1.15 are implemented in the in-memory resolver.
`ResolvedRowProvenance` now records retained-row source table ID, source table
index, source row index, source role, and page evidence when available, using
table-level `source_page_num` with optional row-level
`metadata.source_row_page_nums` fallback. `SourceTableResolution` is the single
source-table index for singleton tables, consumed base fragments, consumed
continuation fragments, and rejected continuations. Rejected continuations stay
in `resolved_tables` as singleton records with rejected decisions, source-index
entries, column diagnostics when available, and row provenance marked as
`rejected_continuation`.

#### Parser Wiring

- [x] **G1.16** Keep implementation direct and minimal: prefer extending the existing
  pipeline stages over adding helper layers that are not reused or clearly
  necessary for readability.
- [x] **G1.17** Write `resolved_tables.json` during `table1-parser parse` after
  normalization and `ColumnHeaderSchema` construction.
- [x] **G1.18** Feed resolved-table `NormalizedTable` objects, not raw normalized
  fragments, into `TableProfile`.
- [x] **G1.19** Feed the same resolved working tables into `TableDefinition`.
- [x] **G1.20** Feed resolved tables and their row provenance into parsed value assembly,
  including `parsed_cell_values.json` joins and `ParsedTable.values`.

Implementation note: G1.16-G1.20 are implemented in the `parse` flow.
`table1-parser parse` builds `ResolvedTableSet` after source
`ColumnHeaderSchema` construction, writes `resolved_tables.json`, then builds
`TableProfile`, `TableDefinition`, and `ParsedTable` from resolved working
tables. `parsed_cell_values.json` remains source-fragment keyed by
`normalized_tables.json`; semantic `ParsedTable.values` join those source
components through `ResolvedRowProvenance` so integrated continuation rows keep
resolved row semantics and original source-fragment provenance. Existing
source-fragment continuation artifacts remain review views.
- [x] **G1.21** Ensure categorical levels that begin on a continuation page can attach to
  a parent variable from the base fragment through ordinary row/level logic.
- [x] **G1.22** Make table-processing status refer to resolved semantic tables while
  preserving source-fragment diagnostics.
- [x] **G1.23** Decide whether `continued_variable_integrations.json` remains a temporary
  review artifact, becomes derived from `resolved_tables.json`, or is removed
  after the resolved stage replaces its role.

Implementation note: G1.21-G1.23 are implemented without adding a second
semantic path. Accepted continuation body rows are already appended in the
resolved `NormalizedTable`, so the ordinary `TableDefinition` row/level grouper
attaches leading continuation count/percent rows to an open base-fragment
categorical parent. `table_processing_status.json` is resolved-table keyed and
now carries `source_table_ids` plus structured `source_fragment_diagnostics`
from source parse-quality and resolution diagnostics. The older
`continued_variable_integrations.json` artifact remains a source-fragment
review view only; it is built from source-fragment table definitions and is not
consumed by canonical `TableDefinition` or `ParsedTable` assembly.

#### Documentation And Artifacts

- [x] **G1.24** Update `docs/design/parsing_output_design.md` with the
  `resolved_tables.json` artifact contract and its relationship to existing
  continuation artifacts.
- [x] **G1.25** Update `docs/design/paper_parse_walkthrough.md` to show the resolved stage
  as the parser input to profiles, definitions, and parsed values.
- [x] **G1.26** Update `docs/implementation/parser_todo.md` as substeps are completed,
  split, or deferred.
- [x] **G1.27** Update R inspection documentation only if a real inspection surface is
  added. Do not add R helpers before usage shows the needed views.

Implementation note: G1.24-G1.27 are documentation/artifact-contract steps.
`docs/design/parsing_output_design.md` now states the direct
`resolved_tables.json` schema role and which outputs are source-fragment keyed
versus resolved-table keyed. `docs/design/paper_parse_walkthrough.md` now
describes the resolved stage as the semantic table list consumed by profiles,
definitions, parsed tables, paper table inventory, and processing status.
`docs/implementation/parser_todo.md` records the completed documentation
substeps. No R inspection surface was added, so no R inspection documentation
was changed for G1.27.

#### Verification

- [x] **G1.28** Run a focused known-failure regression for an explicit continuation with
  matching columns that should become one semantic table.
- [x] **G1.29** Run a focused known-failure regression where a continuation-like fragment
  is rejected because column schemas are incompatible.
- [x] **G1.30** Run a focused known-failure regression where continuation rows become
  levels of a base-fragment parent variable.
- [x] **G1.31** Run a focused known-failure regression proving unrelated tables with
  similar columns are not integrated.
- [x] **G1.32** Run the full `/Users/robert/Projects/Epiconnector/testpapers` corpus after
  the stage is wired into parser outputs.
- [x] **G1.33** Compare table-level status and continuation-related artifacts against the
  latest batch output, not only command exit status.

Implementation note: G1.28-G1.31 are covered by focused regressions in
`tests/test_resolved_tables.py`: matching explicit continuations become one
resolved semantic table, incompatible continuation schemas fail closed as
rejected singleton continuations, continuation rows attach as levels of a
base-fragment parent variable, and unrelated tables with similar columns remain
separate singletons. G1.32-G1.33 were run against 27 PDFs from
`/Users/robert/Projects/Epiconnector/testpapers` with output in
`outputs/testpapers_batch_20260629_152920`. All 27 parse commands succeeded
and all required core artifacts were present. Compared with
`outputs/testpapers_batch_20260629_140704`, failure reasons were unchanged, the
source-fragment continuation review artifacts were stable
(`table1_continuation_groups`: 3 merge/3 skip;
`table_continuation_column_checks`: 4 compatible/2 incompatible;
`continued_variable_integrations`: 3; `merged_table1_tables`: 3), and the new
resolved stage produced 5 integrated continuations, 5 rejected continuation
decisions, and 77 singleton resolved tables.

#### Scope Guardrails

- Do not infer continuation solely from matching columns or plausible row
  labels.
- Do not reconstruct column identity from flattened header strings once
  `ColumnHeaderSchema` exists.
- Do not invent parent rows or synthetic variables for continuation
  fragments.
- Do not add single-use helper functions, broad unit-test expansion, or
  tests that are not tied to a known failure or artifact contract.
- Do not make R-side objects the canonical place where continuation
  resolution happens.

## 2. Finish The Multi-Family Table Architecture

The parser is strongest for descriptive characteristic tables. The corpus shows
many other table-like objects:

- 20 routed as `estimate_results`
- 34 routed as `unknown`
- 28 categorized as `analysis_outputs`
- 9 categorized as `data_presentation`

Completion likely requires first-class support for at least:

- descriptive characteristics
- estimate/model-result tables
- data-presentation matrices, or an explicit unsupported semantic artifact for
  them

The hard parts are:

- aligning `table_family` with the broader `paper_table_inventory`
  `table_category`
- avoiding Table 1 row/level heuristics for estimate-result tables
- defining value-free estimate-table semantics
- parsing estimate values, intervals, model columns, p-values, and reference
  rows into a sibling artifact rather than forcing them into `ParsedTable`
- deciding what an unsupported-but-recognized table should persist

This is completion-scale because it expands the parser from a Table 1-style
descriptive parser into a mixed epidemiology-table parser with family-specific
semantic outputs.

## 3. Corpus-Driven Hardening Of Extraction, Normalization, And Semantics

The current corpus run succeeded at the command level, but 12 table-level
records still failed. The failure reasons were not one narrow bug:

- `non_table_layout_candidate`
- `insufficient_table_structure_after_extraction`
- `no_variables_for_descriptive_table`

Completion likely requires an explicit real-paper review loop:

1. Pick a failing or rescued table.
2. Identify the first bad artifact.
3. Fix the earliest responsible stage.
4. Add a narrow regression only when it captures a real failure mode.
5. Re-run the corpus and compare table-level status, not just command exit.

The hard areas are:

- distinguishing real tables from non-table layout candidates
- extraction and normalization of difficult layouts
- parent/level reasoning when indentation or row sparsity is weak
- ambiguous leaf-header assignment in multi-row headers
- repeated page furniture, notes, and marginal text that contaminate table
  boundaries
- preserving raw evidence while adding structural repairs

This is completion-scale because parser reliability depends on many structural
failure modes interacting across extraction, normalization, column schema, row
semantics, and value parsing.

## Important Work Not In The Top Three

These remain important, but they are not the largest completion blockers.

- R inspection helpers should follow real usage. The current direction is to
  avoid adding many small specialized helpers before review workflows prove
  they are needed.
- General unit-test expansion is not a goal. Regression coverage should be tied
  to known failures or important artifact contracts.
- Value-component diagnostics for typo/error review should consume the existing
  component layer later, once concrete review patterns are known.

## Suggested Reading Order

If this review is accepted as a useful summary, the next useful reading order is:

1. `docs/implementation/parser_todo.md`
2. `docs/design/table_continuation_resolution.md`
3. `docs/design/multitable_architecture_spec.md`
4. Latest batch outputs under `outputs/testpapers_batch_*`
