# Parsing Output and JSON Design

This document describes the JSON artifacts used by the Table 1 parser, the canonical typed models behind them, and the design rules that should govern future output changes.

The short version is:

- table data stays JSON-first
- each pipeline phase has its own schema
- raw extracted content is preserved
- canonical objects must be unambiguous in both Python and R
- row and column references stay stable across phases
- trace/debug wrappers are not the same thing as canonical parsed outputs
- mixed-table papers may eventually route into different semantic families after normalization

## Required Reading Before Changing Outputs

Before changing JSON outputs or schemas, always read:

- `AGENTS.md`
- `docs/design/codex_build_spec.md`
- `docs/design/paper_markdown_spec.md` when changing markdown-context outputs

Those files define the main development criteria:

- keep extraction, normalization, heuristics, LLM interpretation, and validation as separate modules
- preserve the pipeline shape `PDF -> ExtractedTable -> NormalizedTable -> TableDefinition -> ParsedTable`
- keep tables in structured JSON rather than switching to Markdown-first representations
- preserve raw extracted data and original text
- use deterministic parsing first and LLM refinement only for semantic disambiguation
- require strict JSON from the LLM and validate it before accepting it

## Canonical Models vs Persisted Files

There are two related but different concepts in this repository:

1. Canonical typed models
   These are the Pydantic models in `table1_parser/schemas/` and `table1_parser/llm/semantic_schemas.py`.

2. Persisted JSON files
   These are CLI outputs or trace/debug artifacts written to disk.

Some JSON files are direct dumps of canonical models. Others are wrapper files that add timestamps and nest the real payload under keys like `payload`, `response`, or `interpretation`.

## Cross-Language Object Principle

This repository should treat cross-language object design as a first-order principle.

The real semantic objects are the canonical typed structures used by the parser and by downstream R tooling.
JSON is the transport format between those environments, not the conceptual source of truth.

That means every important persisted artifact should be designed so that:

- it can be instantiated as a clear typed object in Python
- it can be loaded as a clear, unambiguous object in R
- field meanings remain stable across languages
- row-oriented records can be converted into R data frames without bespoke restructuring
- IDs and coordinates remain explicit rather than implied by list position alone

When designing or revising schemas:

- prefer explicit named fields over positional conventions
- prefer flat arrays of records over deeply nested ad hoc objects
- use IDs to link related records instead of relying on language-specific object identity
- keep enum-like string vocabularies stable and documented
- avoid shapes that are easy in Python but ambiguous or awkward in R

This principle applies to `TableDefinition`, `ParsedTable`, paper-context artifacts, and `paper_variable_inventory.json`.

## Output Layers

| Layer | Canonical type | Current file status | Main purpose |
| --- | --- | --- | --- |
| Extraction | `ExtractedTable` | Written now as `extracted_tables.json` by `extract` and `parse` | Preserve raw table grid and cell provenance |
| Normalization | `NormalizedTable` | Written now as `normalized_tables.json` by `normalize` and `parse` | Clean rows, detect headers, derive row features |
| Table routing | `TableProfile` | Written now as `table_profiles.json` by `parse` | Persist deterministic family routing and LLM-gating decisions |
| Table definition | `TableDefinition` | Written now as `table_definitions.json` by `parse` | Persist value-free row-variable, level, and column semantics |
| Paper context | `PaperSection`, `TableContext` | Written now as `paper_markdown.md`, `paper_sections.json`, and `table_contexts/*.json` by `parse` | Persist markdown sections and per-table retrieval bundles, with only conservative glyph repair in the markdown text |
| Paper variable inventory | `PaperVariableInventory`, `VariableMention`, `VariableCandidate` | Written now as `paper_variable_inventory.json` by `parse` | Persist the paper-level candidate variable reference list with explicit text/table provenance |
| Semantic LLM table definition | `LLMSemanticTableDefinition` | Written now as `table_definitions_llm.json` by `parse` when LLM config is available | Persist row-focused value-free semantic interpretation grounded in table indices and retrieved paper context |
| Semantic LLM debug monitoring | `LLMSemanticMonitoringReport`, `LLMSemanticCallRecord` | Written only when `LLM_DEBUG=true` as `llm_semantic_debug/<timestamp>/llm_semantic_monitoring.json` plus per-table trace files | Persist per-table timing, payload-size, status, and raw-response debug evidence |
| Semantic LLM per-table trace files | wrapper JSON files | Written only when `LLM_DEBUG=true` as `table_definition_llm_input.json`, `table_definition_llm_metrics.json`, `table_definition_llm_output.json`, and `table_definition_llm_interpretation.json` | Preserve prompt payloads, metrics, raw provider responses, and validated semantic interpretations for inspection |
| Final parsed output | `ParsedTable` | Written now as `parsed_tables.json` by `parse` | Validated downstream structured table data |

Design note for future multitable support:

- after `NormalizedTable`, mixed papers may route through a `TableProfile` stage before final semantics are chosen
- descriptive characteristic tables may continue using `TableDefinition` and `ParsedTable`
- estimate-result tables may later use sibling artifacts such as `EstimateTableDefinition` and `ParsedEstimateTable`
- this family split should be explicit in schemas and persisted files rather than hidden inside one overloaded parser

## Coordinate and Identity Rules

These rules matter because later stages refer back to earlier stages.

- `table_id` is the stable table identifier for one extracted table.
- `row_idx` values are zero-based row indices in the table grid.
- `header_rows` and `body_rows` are lists of those same grid row indices.
- `row_start`, `row_end`, and level `row_idx` values refer to the same row-index space, not to a separate body-only counter.
- `col_idx` is a zero-based column index in the normalized table grid after any edge-column trimming performed during normalization.

This stability is important because the LLM layer is required to reference existing rows only and must never invent new rows or columns.

## 1. `extracted_tables.json`

Current CLI path:

```text
outputs/papers/<paper_stem>/extracted_tables.json
```

This file is written by:

- `table1-parser extract`
- `table1-parser parse`

Top-level shape:

```json
[
  {
    "...": "one ExtractedTable object"
  }
]
```

Canonical model:

- `ExtractedTable`
- child model: `TableCell`

Top-level design components:

- `table_id`: stable ID for this extracted table
- `source_pdf`: source PDF path or identifier
- `page_num`: 1-based source page number
- `title`: detected table title when available
- `caption`: detected caption when available
- `n_rows`, `n_cols`: extracted grid dimensions
- `cells`: flat list of `TableCell` objects
- `extraction_backend`: extractor name, currently `pymupdf4llm`
- `metadata`: extractor-specific extensions

Important current `metadata` keys produced by extraction may include:

- `candidate_score`
- `caption_source`
- `table_number`
- `is_continuation`
- `continuation_of_table_number`
- `table_numbering_audit`
- `explicit_grid_refined_from_words`
- `grid_refinement_source`
- `geometry_coordinate_frame`

`TableCell` design components:

- `row_idx`, `col_idx`: grid location
- `text`: raw extracted cell text
- `page_num`: optional page reference
- `bbox`: optional bounding box `(x0, y0, x1, y1)`
- `extractor_name`: optional per-cell provenance
- `confidence`: optional cell-level confidence

Design intent:

- this is the canonical extraction contract
- raw values are preserved here
- extractor-specific details belong in `metadata`, not in renamed top-level fields
- literal displayed captions should be preserved even for continuations such as `Table 1 (continued)`
- continuation linkage belongs in metadata, not in synthetic renamed titles such as `Table 1a`
- numbering audits are for inspection only; they must not be used to silently drop extracted tables
- extraction may refine a coarse explicit backend grid when word geometry inside the table bbox, together with strong horizontal boundaries, supports a better row/column structure
- rotated explicit tables may be refined in a table-local normalized coordinate frame; when that happens, `row_bounds` and `horizontal_rules` describe that local frame rather than raw page coordinates

## 2. `NormalizedTable` JSON

Current status:

- canonical intermediate model
- written by the `normalize` CLI command as `normalized_tables.json`

Current CLI path:

```text
outputs/papers/<paper_stem>/normalized_tables.json
```

This file is written by:

- `table1-parser normalize`
- `table1-parser parse`

Top-level shape:

```json
[
  {
    "...": "one NormalizedTable object"
  }
]
```

The file is a direct serialization of:

- `NormalizedTable.model_dump(mode="json")`

Top-level design components:

- `table_id`, `title`, `caption`
- `header_rows`: row indices classified as header rows
- `body_rows`: row indices classified as body rows
- `row_views`: list of `RowView` objects for body rows
- `n_rows`, `n_cols`
- `metadata`

`RowView` design components:

- `row_idx`
- `raw_cells`
- `first_cell_raw`
- `first_cell_normalized`
- `first_cell_alpha_only`
- `nonempty_cell_count`
- `numeric_cell_count`
- `has_trailing_values`
- `indent_level`
- `likely_role`

Important current `metadata` keys produced by normalization:

- `source_page_num`
- `extraction_backend`
- `caption_source`
- `table_number`
- `is_continuation`
- `continuation_of_table_number`
- `table_numbering_audit`
- `cleaned_rows`
- `dropped_leading_cols`
- `dropped_trailing_cols`
- `header_detection`
- `indentation_informative`
- `text_cleaning_provenance`

Design intent:

- normalization should add deterministic structure without losing raw text
- `cleaned_rows` may support later prompting and debugging, but raw cell text still lives in extraction output
- `row_views` are the compact per-row features that later heuristic and LLM stages consume
- saved normalized tables can be reloaded as formal downstream input
- when wide horizontal boundaries sit just slightly above or below the first extracted text line, header detection may still use them as the top table boundary; minor geometry jitter should not suppress obvious header/body bracketing
- normalization may apply conservative structural repairs when extraction has clearly split one logical value across adjacent columns
- those repairs should be driven by row-style expectations and body-value patterns, not by paper-specific header templates
- normalization may also repair a small set of extractor-facing glyph-to-Unicode failures in parser-facing text, such as a broken replacement character before a numeric threshold becoming `<=`
- these symbol repairs belong in normalized text only; the original extracted cell text remains preserved in `ExtractedTable`
- these repairs are meant to recover known PDF-extractor symbol failures, not to infer a general source-file encoding
- `text_cleaning_provenance` should record table-level counts of comparator symbols that were observed directly in the surviving normalized grid versus reconstructed from known extractor glyph-failure rules

Conservative repair rule:

- when a categorical block implies `n (%)` values and adjacent cells are strongly consistent with `count` plus parenthesized percent fragments, normalization may merge those fragments back into one cell before later semantic stages run
- when that repair reveals a strongly header-like first body row, normalization may promote that row into `header_rows`
- repair diagnostics should live in `metadata` rather than replacing the canonical `NormalizedTable` fields

## 3. `table_definitions.json`

Current status:

- canonical value-free semantic intermediate
- written by the `parse` CLI command

Current CLI path:

```text
outputs/papers/<paper_stem>/table_definitions.json
```

Top-level shape:

```json
[
  {
    "...": "one TableDefinition object"
  }
]
```

Canonical model:

- `TableDefinition`
- child models: `DefinedVariable`, `DefinedLevel`, `ColumnDefinition`, `DefinedColumn`

Top-level design components:

- `table_id`, `title`, `caption`
- `variables`
- `column_definition`
- `notes`
- `overall_confidence`

`DefinedVariable` design components:

- `variable_name`
- `variable_label`
- `variable_type`
- `row_start`, `row_end`
- `levels`
- `units_hint`
- `summary_style_hint`
- `confidence`

`DefinedLevel` design components:

- `level_name`
- `level_label`
- `row_idx`
- `confidence`

`ColumnDefinition` design components:

- `grouping_label`
- `grouping_name`
- `group_count`
- `columns`
- `confidence`

`DefinedColumn` design components:

- `col_idx`
- `column_name`
- `column_label`
- `inferred_role`
- `grouping_variable_hint`
- `group_level_label`
- `group_level_name`
- `group_order`
- `statistic_subtype`
- `confidence`

Design intent:

- persist the row and column semantics needed for later SQL-query generation
- stay value-free so database-matching and query-building can happen before value parsing
- keep row and column references tied to the normalized table index space
- provide a deterministic baseline before optional LLM refinement is introduced
- keep `variable_name` search-oriented for variable rows, including stripping summary/unit decorations where useful
- keep `level_name` semantically distinct for categorical levels, preserving threshold and range syntax such as `< 1.3`, `1.3-1.8`, and `>1.8`
- model grouped columns explicitly enough to distinguish the overall population column, grouped data columns, and trailing statistic columns
- preserve grouped-column level labels and left-to-right order so downstream matching can reconstruct the table's column grouping structure

## 4. Paper Context Artifacts

Current status:

- written by the `parse` CLI command
- derived from `pymupdf4llm` markdown, not from the table grid itself

Current CLI paths:

```text
outputs/papers/<paper_stem>/paper_markdown.md
outputs/papers/<paper_stem>/paper_sections.json
outputs/papers/<paper_stem>/paper_variable_inventory.json
outputs/papers/<paper_stem>/table_contexts/table_<n>_context.json
```

Canonical models:

- `PaperSection`
- `PaperVariableInventory`
- child models: `VariableMention`, `VariableCandidate`
- `TableContext`
- child model: `RetrievedPassage`

Design components:

- `paper_markdown.md`
  raw markdown extracted from the full paper
- `paper_sections.json`
  markdown-derived sections with heading level and simple role hints
- `paper_variable_inventory.json`
  paper-level variable-search artifact with broad mention-level records and a stricter consolidated candidate-variable list
- `table_contexts/*.json`
  per-table retrieval bundles keyed by `table_id` and `table_index`

`TableContext` design components:

- `table_id`, `table_index`, `table_label`
- `title`, `caption`
- `row_terms`
- `column_terms`
- `grouping_terms`
- `methods_like_section_ids`
- `results_like_section_ids`
- `passages`

`RetrievedPassage` design components:

- `passage_id`
- `section_id`
- `heading`
- `text`
- `match_type`
- `score`

Design intent:

- keep paper-level context in the same per-paper output directory
- keep the candidate variable reference list explicit and easy to load in both Python and R
- preserve a distinction between broad harvested mentions and the narrower promoted candidate list
- support future LLM semantic interpretation with compact retrieved evidence
- avoid tying retrieval to exact section names like `Methods`
- preserve `paper_markdown.md` as the paper-level markdown artifact, allowing only conservative glyph repair, and move derived structure into `paper_sections.json`
- preserve a JSON-first, inspectable context path alongside the table path

Variation note:

- papers may use different section names, heading levels, and table-reference styles
- that variation should be handled in section parsing and retrieval, not by redefining the meaning of `paper_markdown.md` beyond conservative glyph repair
- `docs/design/paper_markdown_spec.md` is the design reference for this artifact

## 5. `table_definitions_llm.json`

Current status:

- written by `parse` when semantic LLM configuration is available
- skipped with a warning when semantic LLM is not disabled but configuration is missing
- skipped when `--no-llm-semantic` is used

Current CLI path:

```text
outputs/papers/<paper_stem>/table_definitions_llm.json
```

Canonical model:

- `LLMSemanticTableDefinition`

Top-level shape:

```json
[
  {
    "...": "one LLMSemanticTableDefinition object"
  }
]
```

Design components:

- `table_id`
- `variables`
- `notes`
- `overall_confidence`

Design intent:

- let the LLM speak about row semantics using deterministic row structure plus retrieved paper context
- preserve `table_definitions.json` as the deterministic baseline artifact
- keep row references tied to the normalized table index space
- validate the LLM output before writing this file
- keep per-variable `units_hint` and `summary_style_hint` out of the semantic LLM contract for now

Debug-only companion artifacts:

- when `LLM_DEBUG=true`, `parse` also writes a timestamped debug run under:

```text
outputs/papers/<paper_stem>/llm_semantic_debug/<timestamp>/
  llm_semantic_monitoring.json
  table_0/
    table_definition_llm_input.json
    table_definition_llm_metrics.json
    table_definition_llm_output.json
    table_definition_llm_interpretation.json
```

- `llm_semantic_monitoring.json` summarizes every table's semantic-LLM status, including skipped tables
- per-table trace files are written only for tables that actually reached the semantic LLM call path

## 6. Semantic Debug Trace Files

Current status:

- written only when `LLM_DEBUG=true`
- debug artifacts, not stable downstream interfaces

Current per-table file names:

- `table_definition_llm_input.json`
- `table_definition_llm_metrics.json`
- `table_definition_llm_output.json`
- `table_definition_llm_interpretation.json`

Current top-level wrappers:

```json
{
  "report_timestamp": "...",
  "table_id": "...",
  "payload": {
    "...": "semantic LLM prompt payload"
  }
}
```

```json
{
  "table_id": "...",
  "status": "success",
  "elapsed_seconds": 1.23
}
```

```json
{
  "report_timestamp": "...",
  "table_id": "...",
  "response": {
    "...": "raw structured LLM response"
  }
}
```

```json
{
  "report_timestamp": "...",
  "table_id": "...",
  "interpretation": {
    "...": "LLMSemanticTableDefinition"
  }
}
```

Design intent:

- preserve the exact semantic LLM payload, monitoring metrics, raw provider output, and validated interpretation for inspection
- keep these files separate from canonical pipeline outputs such as `table_definitions.json`, `table_definitions_llm.json`, and `parsed_tables.json`
- preserve stable row references so semantic disagreements can still be audited safely
- keep the prompt payload compact; the saved input wrapper currently uses short payload keys such as `rows`, `vars`, and `passages`

## 7. `ParsedTable` JSON

Current status:

- canonical final schema exists now
- written by the `parse` CLI command as `parsed_tables.json`

This should be treated as the main downstream table representation.

Current CLI path:

```text
outputs/papers/<paper_stem>/parsed_tables.json
```

This file is written by:

- `table1-parser parse`

Top-level design components:

- `table_id`
- `title`
- `caption`
- `variables`
- `columns`
- `values`
- `notes`
- `overall_confidence`

`variables` design components:

- `variable_name`
- `variable_label`
- `variable_type`
- `row_start`
- `row_end`
- `levels`
- `confidence`

`columns` design components:

- `col_idx`
- `column_name`
- `column_label`
- `inferred_role`
- `confidence`

`values` design components:

- `row_idx`
- `col_idx`
- `variable_name`
- `level_label`
- `column_name`
- `raw_value`
- `value_type`
- `parsed_numeric`
- `parsed_secondary_numeric`
- `confidence`

Why `values` are long-format:

- one row per table cell is easier to validate
- it supports downstream filtering and export
- it separates semantic row/column interpretation from numeric parsing
- it preserves the original `raw_value`

Design note for future value parsing:

- parser-facing symbol canonicalization should be applied internally before regex matching and numeric parsing
- canonicalization must not replace the stored `raw_value`
- for Table 1 categorical `n (%)` cells, the intended first interpretation is:
  - `parsed_numeric` = count
  - `parsed_secondary_numeric` = percent
- count-percent consistency checks should be soft heuristics, not hard validity requirements
- the overall-column 100% rule should be limited to columns that are truly `overall` or clearly equivalent, while subgroup columns may legitimately sum to their share of the full study population instead of 100

This is the richest JSON design in the repo because it joins variable semantics, column semantics, and cell-level values into one validated representation.

## Trace Wrappers vs Canonical Payloads

A simple rule:

- wrapper files are for debugging and auditability
- canonical payloads are for stable programmatic interfaces

Wrapper files currently include:

- `table_definition_llm_input.json`
- `table_definition_llm_metrics.json`
- `table_definition_llm_output.json`
- `table_definition_llm_interpretation.json`

Canonical payloads currently include:

- `ExtractedTable`
- `NormalizedTable`
- `TableDefinition`
- `LLMSemanticTableDefinition`
- `ParsedTable`

The final parse/export path should prefer canonical model dumps, with wrapper files used only when explicit trace/debug output is wanted.

## Controlled Vocabularies and Current Gaps

Several fields use constrained string vocabularies rather than free text.

Current canonical examples:

- `ParsedVariable.variable_type`: `continuous`, `categorical`, `binary`, `unknown`
- `ParsedColumn.inferred_role`: `group`, `overall`, `p_value`, `statistic`, `unknown`
- `ValueRecord.value_type`: `count`, `percent`, `mean_sd`, `median_iqr`, `text`, `unknown`
- `RowView.likely_role`: `header`, `variable`, `level`, `statistic`, `note`, `unknown`

There is one important stage-to-stage mismatch in the current repository:

- heuristic column-role guesses support `comparison_group` and `smd`
- the current LLM interpretation and final `ParsedColumn` schema do not expose those labels directly

That means developers should not assume every heuristic enum value maps 1:1 into the final parsed schema. If this area is expanded later, it should be done deliberately and across all affected schemas and docs together.

## Recommended Rules for Future JSON Design

When adding or revising output files:

- keep one pipeline stage per JSON artifact
- do not merge extraction, normalization, heuristics, and final parsed output into one catch-all object
- preserve raw text and stable row/column coordinates
- keep core semantic fields explicit and stable
- reserve `metadata` for backend-specific or stage-specific extensions
- prefer typed arrays of records over free-form nested dictionaries
- make timestamps and trace metadata wrapper-level concerns, not core schema fields
- distinguish clearly between inspection artifacts and downstream analysis artifacts

## Related but Separate JSON: Synthetic Truth Files

The synthetic generator writes `*_truth.json` files through `table1_parser.synthetic.truth_writer`.

Those files are evaluation artifacts, not parser runtime outputs. Their top-level design is different because they store synthetic ground truth for testing, including:

- `document_title`
- `table_caption`
- `columns`
- `header_rows`
- `rows`
- `variables`
- `value_records`
- `layout_features`

They are useful as reference material for expected parsed structure, but they should not be confused with the runtime parse/export contract.
