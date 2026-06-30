# Parse Quality Reports Artifact Design

## Purpose

Persist deterministic parse-quality diagnostics as a normal `table1-parser parse` output artifact.

The parser already has diagnostics for row classification, column interpretation, value-pattern recognition, and broad table-quality warnings.
The current gap is observability: these diagnostics exist as code-level reports, but they are not written by the parse command in the per-paper output directory.

This design adds a stable inspection artifact without changing extraction, normalization, table definitions, parsed tables, LLM behavior, or Table 1 continuation merging.

## Proposed Artifact

File name:

```text
outputs/papers/<paper_stem>/parse_quality_reports.json
```

Canonical type:

- `ParseQualityReport`
- child models:
  - `ParseQualitySummary`
  - `DiagnosticItem`

Top-level shape:

```json
[
  {
    "...": "one ParseQualityReport object per normalized table"
  }
]
```

One report should be written for every `NormalizedTable` considered by the deterministic parse pipeline.

## Pipeline Position

The report should be built after normalized tables are available and after the deterministic row/column heuristics needed for diagnostics can be computed.

Conceptually:

```text
NormalizedTable
  -> row classifications
  -> variable blocks
  -> column role guesses
  -> ParseQualityReport
```

This artifact is an inspection and quality-control side output.
It must not become an input to the default parser unless a later design explicitly says so.

## Inputs

Each report should be built from:

- the source `NormalizedTable`
- `classify_rows(table)`
- `group_variable_blocks(table)`
- column role guesses from the deterministic column-role path
- optionally the matching `ExtractedTable`, when source PDF provenance is useful

The report should not call an LLM.
It should not run a new parser stage.
It should reuse the deterministic signals the parser already computes.

## Intended Diagnostics

The artifact should expose existing diagnostics such as:

- high unknown-row fraction
- no variable blocks in a non-trivial table
- missing row labels with populated values
- level rows without plausible parent rows
- categorical parent rows without following levels
- low recognized value-pattern rate
- suspicious header-row count
- header-rule/content disagreement
- header/body split disagreement when the validated hline separator and the
  first value-region anchor both exist but choose different body starts
- normalization edge-column cleanup
- mostly empty columns
- p-value columns with too few p-value-like entries
- group/overall columns with low recognizable value-pattern density
- multiple row/column warnings suggesting broad parse-quality issues

Column diagnostics are especially important because incorrect column roles can make the final parsed values look structurally clean while assigning them to the wrong semantic columns.

## Non-Goals

This artifact should not:

- fail or halt parsing
- change `table_definitions.json`
- change `parsed_tables.json`
- consolidate Table 1 continuations
- adjudicate semantic meaning with an LLM
- replace `table_processing_status.json`
- introduce paper-specific or domain-specific rules

The first implementation should be observability-only.

## Relationship To Existing Artifacts

`table_processing_status.json` records whether each table passed or failed the deterministic parse and which rescue/repair paths were attempted.

`parse_quality_reports.json` should record softer quality signals even when the parse technically succeeds.

Examples:

- a table can have `status = ok` but still have a weak p-value column
- a table can produce variables and values but still have suspicious header detection
- a table can parse successfully while several columns have low value-pattern recognition

These artifacts should remain separate because processing status is a coarse pipeline outcome, while parse quality is a diagnostic inspection layer.

## R Inspection Requirements

R-side inspection should load the new artifact optionally.

Suggested additions:

- `load_paper_outputs()` includes `parse_quality_reports`
- `summarize_table_processing()` may include:
  - table diagnostic warning/error counts
  - row warning/error counts
  - column warning/error counts
- a focused helper:
  - `show_parse_quality(paper_dir, table_index = 0L)`

The focused helper should print:

- summary counts
- table-level diagnostics
- row diagnostics
- column diagnostics

Column diagnostics should be easy to scan because they are the main current blind spot.

## Design Constraints

- Keep the persisted shape as a direct Pydantic JSON dump.
- Keep one report per normalized table.
- Preserve `table_id` as the join key to `normalized_tables.json`, `table_definitions.json`, `parsed_tables.json`, and `table_processing_status.json`.
- Use row and column indices from the normalized table coordinate system.
- Avoid trace wrappers or timestamps outside the existing `ParseQualityReport` model.
- Treat the artifact as stable enough for R inspection, but not as a final quality score.

## Implementation Notes

This is a design spec, not a detailed implementation plan.

A later implementation should update:

- `table1_parser/cli.py`
- `R/inspect_paper_outputs.R`
- CLI/R tests
- `docs/design/parsing_output_design.md`
- `docs/design/paper_parse_walkthrough.md`
- `docs/r_visualization.md`

The implementation should not modify core parser behavior unless a separate design change is approved.

## Open Questions

- Should warning/error counts be duplicated into `table_processing_status.json`, or only shown through R inspection?
- Should parse-quality reports eventually include a compact `overall_quality` field?
- Should column-role confidence from `TableDefinition.column_definition` be included in diagnostics, or should the report continue using lower-level role guesses?
- Should diagnostics for merged Table 1 inspection artifacts be written separately once semantic consolidation is attempted?
