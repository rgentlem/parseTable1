# Codex Build Spec

This is the top-level architecture specification for parser implementation work.
Read this document with `AGENTS.md` before changing extraction, normalization,
column interpretation, row semantics, value parsing, LLM review, R inspection, or
observed-table outputs.

## Current Canonical Pipeline

The parser is a staged system. Each stage has its own responsibility and its own
typed artifacts:

```text
PDF
-> ExtractedTable
-> TableRegion
-> NormalizedTable
-> ColumnHeaderSchema
-> BodyElementCandidates
-> BodyRowLabelCandidates
-> ResolvedTableSet
-> TableDefinition
-> ParsedTable
```

The stages must remain separate:

- `ExtractedTable` preserves the raw recovered grid, raw cell text, page
  information, cell bounding boxes where available, and extraction metadata.
- `TableRegion` records structural row roles anchored by body geometry and
  columns before normalization: table caption/title rows, preamble rows,
  column-header bands, body rows, and footer/note bands. It is built from
  extracted table entries, row/cell geometry, horizontal rules, and cell-text
  annotation marker geometry after page furniture has already been filtered.
- `NormalizedTable` performs structural cleanup, header/body row separation,
  row-level feature extraction, and normalization-time repairs while preserving
  source text provenance. When a `TableRegion` is available, normalization must
  consume its row-region decisions instead of rediscovering captions, column
  headers, body rows, or footer rows from cleaned strings.
- `ColumnHeaderSchema` is the canonical column-axis artifact. It records leaf
  columns, row-label columns, spanning header groups, group-to-leaf
  relationships, raw header evidence, source row/column evidence, and
  coordinates where available.
- `BodyElementCandidates` is the first logical body-value layer. It is built
  after the column grid is settled by `ColumnHeaderSchema`; it proposes
  candidate value elements from one or more physical source cells while
  preserving the physical grid and source-cell provenance.
- `BodyRowLabelCandidates` is the sibling logical body-label layer. It is built
  after the column grid is settled by `ColumnHeaderSchema`; it proposes
  candidate row labels from adjacent physical body rows while preserving the
  physical grid and source-cell provenance.
- `ResolvedTableSet` is the paper-level semantic working set. It preserves
  singleton tables, integrates accepted continuation fragments, rejects weak
  continuation candidates as inspectable singletons, and records source-row
  provenance.
- `TableDefinition` interprets row variables, categorical levels, and semantic
  column roles from resolved `NormalizedTable` objects plus
  `ColumnHeaderSchema`, without extracting values.
- `ParsedTable` combines the normalized grid, table definition, and value
  parsing into final structured value records.

The current geometry path also writes three inspectable geometry artifacts after
`TableRegion`: `body_occupancy.json`, `leaf_column_candidates.json`, and
`header_structure_candidates.json`.
`HeaderStructureCandidate` preserves
preliminary leaves, partial-rule groups, wrapped fragments, source-supported
marker attachments, and cross-band header diagnostics. Preliminary leaves are
defined by exact zero-occupancy gaps at least two observed space-glyph widths
wide in the dominant table font and size; positioned header text attaches to
the resulting bands but does not create additional physical columns.
Body occupancy and leaf candidates participate in canonical extraction;
header-structure candidates remain post-extraction evidence and do not rewrite
the physical grid. None of these artifacts feeds normalization-time geometry
repair.

For continued-table work, the confirmed semantic working path is:

```text
NormalizedTable + ColumnHeaderSchema
-> ResolvedTableSet
-> TableProfile/TableDefinition
-> ParsedTable
```

`ResolvedTableSet` is the paper-level working set that promotes singleton
normalized tables or accepted integrated continuations before semantic parsing.
`table1-parser parse` writes this working set to `resolved_tables.json` and
feeds resolved tables into table profiles, table definitions, and parsed table
assembly. Existing continuation outputs remain review/provenance artifacts.

## Mandatory Page-Furniture Filtering Rule

`paper_positioned_document.json` must be built as the first shared
whole-document positioned-text pass when `table1-parser parse` starts.
`paper_page_furniture.json` must then be built from that shared evidence before
any stage derives paper text, markdown, sections, bibliography entries, visual
references, table candidates, cell text annotations, footnote definition lines,
style profiles, variable inventories, or table contexts.

Every stage that consumes positioned PDF text, words, characters, or extracted
grid rows must receive the paper-page-furniture artifact and apply its ignored
regions before deriving downstream artifacts. Page-furniture filtering is an
early document-processing invariant, not a late cleanup path.

If a new source path needs page text, lines, spans, words, characters, or rule
segments, consume
`PaperPositionedDocument` or a typed projection of it instead of opening the PDF
for another positioned-geometry pass. Thread `PaperPageFurniture` into that
path and filter the source geometry before grouping, classification, linking,
or artifact construction. Do not add downstream exceptions that remove headers,
footers, download notices, marginal text, or other repeated furniture after
those strings have already entered bibliography, section, table, footnote, or
annotation artifacts.

## Mandatory Column-Header Rule

`ColumnHeaderSchema` is the only parser-approved mechanism for comparing or
interpreting columns after normalization.

Every current and future tool that needs column meaning, column compatibility,
column alignment, grouped-column context, statistic-column detection, observed
table data-frame construction, R inspection, or LLM prompt context must consume
`ColumnHeaderSchema` or an explicit typed object derived from it.

Tools must not reconstruct column identity from ad hoc normalized header rows,
raw string concatenation, positional list names, or locally invented header
summaries once `ColumnHeaderSchema` is available. If the needed column schema is
missing or inadequate, the tool should fail closed with a structured diagnostic
rather than silently comparing or interpreting columns by another method.

This rule is especially important for multicolumn headers. Epidemiology tables
often use header bands where one visible label spans several lower-level columns,
where repeated group labels define adjacent blocks, where leaf headers wrap over
multiple physical rows, or where the row-label column sits outside value-region
group headers. Continuation pages may also omit or abbreviate those headers.
Those layouts cannot be interpreted safely by reading a single header row or by
constructing local string summaries. Tools must use the leaf columns,
spanning-group records, group-to-leaf relationships, and raw evidence preserved
in `ColumnHeaderSchema`.

Continuation and table-integration work should treat column alignment as a
precondition. Once the column-header tool has established compatible columns,
integration may combine row sequences and preserve row/cell provenance, but row
integration should not invent a separate column model.

Observed-table and R-side data frames should be materialized after row labels,
levels, and variable types are settled. Those data frames should keep row and
cell provenance back to `NormalizedTable` and, where available, `ExtractedTable`,
while using the column definitions produced from `ColumnHeaderSchema`.

The detailed column schema design lives in:

- `docs/design/column_header_schema.md`
- `docs/implementation/column_header_schema_implementation_plan.md`
- `docs/design/paper_parse_walkthrough.md`

## Historical Phase 1 Scaffold

The original scaffold task below is retained for historical context. Current
parser work should follow the canonical pipeline and column-header rule above.

---

# Task

Implement **Phase 1 only** of the project.

Do not implement later phases yet.

Phase 1 focuses on **project scaffolding and schemas**.

---

# Phase 1 Scope

Create the basic Python package structure and core data models.

Implement:

1. Package scaffold
2. Configuration module
3. Pydantic schemas
4. CLI scaffold
5. Basic tests

Do NOT implement:

- PDF extraction
- normalization
- heuristic parsing
- LLM integration
- validation pipeline

Those belong to later phases.

---

# Required Directory Structure

Create this package layout:

table1_parser/
  __init__.py
  cli.py
  config.py

  schemas/
    extracted_table.py
    normalized_table.py
    parsed_table.py

tests/

---

# Schemas to Implement

Implement Pydantic models for:

### TableCell
Fields:

row_idx  
col_idx  
text  
page_num (optional)  
bbox (optional)  
extractor_name (optional)  
confidence (optional)

---

### ExtractedTable

Fields:

table_id  
source_pdf  
page_num  
title  
caption  
n_rows  
n_cols  
cells (list of TableCell)  
extraction_backend  
metadata

---

### RowView

Fields:

row_idx  
raw_cells  
first_cell_raw  
first_cell_normalized  
first_cell_alpha_only  
nonempty_cell_count  
numeric_cell_count  
has_trailing_values  
indent_level  
likely_role

---

### NormalizedTable

Fields:

table_id  
title  
caption  
header_rows  
body_rows  
row_views  
n_rows  
n_cols  
metadata

---

### ParsedLevel

Fields:

label  
row_idx

---

### ParsedVariable

Fields:

variable_name  
variable_label  
variable_type  
row_start  
row_end  
levels  
confidence

---

### ParsedColumn

Fields:

col_idx
column_name
column_label
inferred_role
confidence

---

### ValueRecord

Fields:

source_table_index
source_table_id
row_idx
col_idx
variable_name
variable_label
level_label
column_name
column_label
header_leaf_id
header_leaf_label
header_group_ids
header_group_labels
header_path
raw_value
parse_pattern
components
confidence
notes

`components` is the canonical value payload. Do not add scalar compatibility
aliases such as `value_type`, `parsed_numeric`, or `parsed_secondary_numeric`
to the canonical schema.

---

### ParsedTable

Fields:

table_id  
title  
caption  
variables  
columns  
values  
notes  
overall_confidence

---

# CLI Stub

Create a CLI command using typer or argparse.

Command:

table1-parser

Subcommands:

extract
parse

For Phase 1 these commands should only print:

"Feature not implemented yet"

---

# Config Module

Create `config.py` with configuration settings such as:

default_extraction_backend  
llm_model  
max_table_candidates  
heuristic_confidence_threshold

Use a Pydantic settings class.

---

# Verification

This repository intentionally has no pytest suite. Parser changes are verified
through explicitly approved real-paper checks.

---

# Deliverables

After Phase 1:

The repository should contain:

- working Python package
- Pydantic schemas
- CLI stub
- config module

The code should import correctly and install locally.

---

# Coding Style

Follow rules in AGENTS.md:

- type hints everywhere
- Pydantic models
- modular structure
- docstrings on public classes

---

# Final Instruction

Implement Phase 1 only.

Do not add extraction or parsing logic yet.
