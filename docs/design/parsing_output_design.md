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
   These are the Pydantic models in `table1_parser/schemas/` and `table1_parser/llm/variable_plausibility_schemas.py`.

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

This principle applies to `TableDefinition`, `ParsedTable`, paper-context artifacts, `paper_variable_inventory.json`, and `paper_table_inventory.json`.

## Output Layers

| Layer | Canonical type | Current file status | Main purpose |
| --- | --- | --- | --- |
| Extraction | `ExtractedTable` | Written now as `extracted_tables.json` by `extract` and `parse` | Preserve raw table grid and cell provenance |
| Normalization | `NormalizedTable` | Written now as `normalized_tables.json` by `normalize` and `parse` | Clean rows, detect headers, derive row features |
| Column header schema | `ColumnHeaderSchema` | Written now as `column_header_schemas.json` by `parse` | Persist parser-native leaf columns, spanning header groups, group-to-leaf relationships, raw cell evidence, and coordinates before semantic column projection |
| Table 1 continuation inspection | `Table1ContinuationGroup`, `NormalizedTable` | Written now as `table1_continuation_groups.json` and `merged_table1_tables.json` by `parse` | Persist artifact-only grouping and merged normalized rows for explicit Table 1 continuations without altering the main parse |
| Continuation column compatibility | `TableContinuationColumnCheck` | Written now as `table_continuation_column_checks.json` by `parse` | Persist diagnostic column-signature and coordinate compatibility checks for explicit `demographic_description` continuations without altering the main parse |
| Table routing | `TableProfile` | Written now as `table_profiles.json` by `parse` | Persist provisional deterministic parser-route decisions |
| Paper table inventory | `PaperTableInventory`, `PaperTableRecord` | Written now as `paper_table_inventory.json` by `parse` | Persist one deterministic taxonomy prediction per table-like object |
| Table definition | `TableDefinition` | Written now as `table_definitions.json` by `parse` | Persist value-free row-variable, level, and column semantics |
| Paper context | `PaperSection`, `PaperVisual`, `PaperVisualReference`, `TableContext` | Written now as `paper_markdown.md`, `paper_sections.json`, `paper_visual_inventory.json`, `paper_references.json`, and `table_contexts/*.json` by `parse` | Persist markdown sections, actual in-paper visual objects, anchored table/figure references, and per-table retrieval bundles, with only conservative glyph repair in the markdown text |
| Paper variable inventory | `PaperVariableInventory`, `VariableMention`, `VariableCandidate` | Written now as `paper_variable_inventory.json` by `parse` | Persist the paper-level candidate variable reference list with explicit text/table provenance |
| Variable-plausibility LLM review | `LLMVariablePlausibilityTableReview` | Written now as `table_variable_plausibility_llm.json` by `review-variable-plausibility` when LLM config is available | Persist table-local QA scores for variable label/type/level plausibility without rewriting the deterministic definition |
| Variable-plausibility debug monitoring | `LLMVariablePlausibilityMonitoringReport`, `LLMVariablePlausibilityCallRecord` | Written only when `LLM_DEBUG=true` as `llm_variable_plausibility_debug/<timestamp>/llm_variable_plausibility_monitoring.json` plus per-table trace files | Persist per-table timing, payload-size, status, and raw-response debug evidence for the standalone review command |
| Variable-plausibility per-table trace files | wrapper JSON files | Written only when `LLM_DEBUG=true` as `variable_plausibility_llm_input.json`, `variable_plausibility_llm_metrics.json`, `variable_plausibility_llm_output.json`, and `variable_plausibility_llm_review.json` | Preserve prompt payloads, metrics, raw provider responses, and validated plausibility reviews for inspection |
| Final parsed output | `ParsedTable` | Written now as `parsed_tables.json` by `parse` | Validated downstream structured table data |
| Table processing status | `TableProcessingStatus`, `TableProcessingAttempt` | Written now as `table_processing_status.json` by `parse` | Persist rescue attempts, terminal failure stage, and failure reason without overloading semantic artifacts |
| Parse quality diagnostics | `ParseQualityReport` | Written now as `parse_quality_reports.json` by `parse` | Persist deterministic row, column, and value-pattern diagnostics without changing parse behavior |

Design note for future multitable support:

- after `NormalizedTable`, mixed papers may route through a provisional `TableProfile` stage before final semantics are chosen
- long term, parser route should be derived from or explicitly consistent with the broader `paper_table_inventory.json` table category; it should not become an unrelated second taxonomy
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
- `orientation_strategy`
- `sideways_candidate`
- `sideways_detection_signals`
- `caption_detection_space`
- `table_cells`
- `first_column_text_x0_by_row`

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
- collapsed-grid word-position refinement chooses value-column anchors from repeated value-like numeric positions rather than one-off digit-bearing label tokens; when needed, it preserves a left label anchor and pulls nonnumeric label fragments back from value columns on rows whose only right-side value is a trailing statistic such as a p-value
- rotated explicit tables may be refined in a table-local normalized coordinate frame; when that happens, `row_bounds` and `horizontal_rules` describe that local frame rather than raw page coordinates
- for explicit PyMuPDF4LLM tables, extraction may record `first_column_text_x0_by_row` so normalization can infer visible row-label indentation from word positions rather than full cell boundaries; this metadata supports row classification only and does not replace cell bboxes
- text-position fallback candidates may preserve parser-facing cell text bounding boxes in `table_cells`; for these candidates, first-column cell boxes are based on the recovered text extents and can also support indentation-sensitive row classification

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
- `source_col_indices`
- `column_repairs`
- `header_detection`
- `indentation_informative`
- `text_cleaning_provenance`

Design intent:

- normalization should add deterministic structure without losing raw text
- `cleaned_rows` may support later prompting and debugging, but raw cell text still lives in extraction output
- `row_views` are the compact per-row features that later heuristic and LLM stages consume
- saved normalized tables can be reloaded as formal downstream input
- `source_col_indices` records, for each normalized column, the corresponding
  original extracted column when that identity is still well-defined; entries
  may be `null` after repairs that merge, synthesize, or expand columns
- when wide horizontal boundaries sit just slightly above or below the first extracted text line, header detection may still use them as the top table boundary; minor geometry jitter should not suppress obvious header/body bracketing
- normalization may apply conservative structural repairs when extraction has clearly split one logical value across adjacent columns
- normalization may also drop a sparse structural stub column when strong row-pattern evidence shows that the next column is the true row-label field and columns to the right are the value region
- normalization may also merge two adjacent row-label field columns when the second column repeatedly contains label fragments and data-like values clearly begin to the right
- normalization may also move an embedded count out of the first value column when that cell contains the tail of a row label plus a count-like value, recording evidence in `metadata.column_repairs.embedded_label_count_cells`
- normalization may also merge label-only continuation rows into the preceding valued row when punctuation, footnote, or phrase-continuation cues show that the visual row label wrapped vertically, recording evidence in `metadata.column_repairs.vertical_label_continuations`
- normalization may also expand a collapsed extracted value-region cell back into many visual value columns when that cell repeatedly contains a stable newline-delimited stack of numeric values; this repairs an extractor artifact where an upright wide data table has been flattened in the raw grid even though the visual table is multi-column
- those repairs should be driven by row-style expectations and body-value patterns, not by paper-specific header templates
- normalization may also repair a small set of extractor-facing glyph-to-Unicode failures in parser-facing text, such as a broken replacement character before a numeric threshold becoming `<=`
- these symbol repairs belong in normalized text only; the original extracted cell text remains preserved in `ExtractedTable`
- these repairs are meant to recover known PDF-extractor symbol failures, not to infer a general source-file encoding
- `text_cleaning_provenance` should record table-level counts of comparator symbols that were observed directly in the surviving normalized grid versus reconstructed from known extractor glyph-failure rules

Conservative repair rule:

- when a categorical block implies `n (%)` values and adjacent cells are strongly consistent with `count` plus parenthesized percent fragments, normalization may merge those fragments back into one cell before later semantic stages run
- when a broad extracted value cell contains a repeated fixed-width stack of mostly numeric tokens across several rows, normalization may split that stack into separate value columns, repeat coarser shared header labels over their leaf columns, and record the evidence in `metadata.column_repairs.extra_wide_value_column`
- when that repair reveals a strongly header-like first body row, normalization may promote that row into `header_rows`
- when a first column is sparse, value-free, and mostly section-like while the second column is dense and label-like, normalization may suppress pure stub rows, shift the second column into the row-label position, and merge first-plus-second labels for rows where both pieces form one label
- when a single logical row-label field is split across the first two columns, normalization may shift second-column level labels left and merge first-plus-second label fragments before row signatures are built; this can be supported by shifted label rows or by many merged first-plus-second label fragments with values clearly starting to the right
- when only the tail of a label is embedded in the first value cell, normalization may merge that label tail back into column 0 while leaving the count in the value column
- when a label-only continuation row wraps below a valued row, normalization may append the continuation text to the preceding row label and suppress the continuation row from `body_rows`
- repair diagnostics should live in `metadata` rather than replacing the canonical `NormalizedTable` fields

## 3. `column_header_schemas.json`

Current status:

- canonical structural column-schema models exist now
- written by the `parse` CLI command
- consumed by deterministic `TableDefinition` column assembly

Current CLI path:

```text
outputs/papers/<paper_stem>/column_header_schemas.json
```

Top-level shape:

```json
[
  {
    "...": "one ColumnHeaderSchema object"
  }
]
```

Canonical model:

- `ColumnHeaderSchema`
- child models: `ColumnHeaderLeaf`, `ColumnHeaderGroup`,
  `ColumnHeaderRelationship`, `ColumnHeaderCellEvidence`

Design components:

- `leaves`
  record one parser-facing normalized column each, including the row-label
  column, leaf header label, body-row indices with non-empty cells, optional
  original column index, and optional coordinate summary
- `groups`
  record higher header labels spanning one or more leaf columns
- `relationships`
  record each group-to-leaf attachment explicitly
- `evidence`
  records normalized row/column references, raw extracted text when available,
  parser-facing cleaned text, page number, and cell bounding boxes when
  available
- `flattened_signature`
  is a convenience view over the schema for quick comparison and compatibility
  checks; it is not the conceptual model
- `diagnostics`
  records degraded or missing evidence, skipped title-like header rows, blank
  leaf labels, and missing coordinate evidence

When normalized header rows are absent or title-like, the schema builder may
infer a header stack from the rows above the first strongly numeric body row.
This is still a column-schema computation: it preserves raw header-cell
evidence and records diagnostics rather than changing the normalized table.

Design intent:

- column-header recovery is a first-class parser artifact, not hidden inside
  `TableDefinition`
- leaf labels come from the header row closest to the body
- higher header rows become spanning groups rather than being flattened too
  early
- raw extracted cells and coordinates are preserved whenever they are available
- missing raw evidence is explicit rather than silently invented
- the schema can later support stored summary/tableone-style projection by
  providing a stable column axis before any print method renders a table

## 4. Table 1 Continuation Inspection Artifacts

Current status:

- canonical inspection schemas exist now
- written by the `parse` CLI command
- not consumed by the default `TableDefinition` or `ParsedTable` builders

Current CLI paths:

```text
outputs/papers/<paper_stem>/table1_continuation_groups.json
outputs/papers/<paper_stem>/table_continuation_column_checks.json
outputs/papers/<paper_stem>/merged_table1_tables.json
```

Canonical models:

- `Table1ContinuationGroup`
- child model: `Table1ContinuationMember`
- merged table artifact: `NormalizedTable`

Design components:

- `table1_continuation_groups.json`
  records explicit Table 1 continuation candidates, their source table indices, source table IDs, column signatures, decision reasons, and merge/skip diagnostics
- `merged_table1_tables.json`
  records one merged `NormalizedTable` per accepted group, preserving normalized cleaned rows and source-row provenance in `metadata.table1_continuation_merge`

Design intent:

- handle only explicit Table 1 continuation evidence, such as `Table 1 (continued)` or extractor continuation metadata for table number 1
- require compatible normalized column signatures before writing a merged table artifact
- ignore non-Table 1 continuations, including later result tables that happen to span pages
- preserve source table IDs and row indices so the merged view is auditable from the original `normalized_tables.json`
- keep the merge artifact inspection-only until a later change deliberately wires it into semantic parsing
- avoid changing existing `table_definitions.json`, `parsed_tables.json`, or `table_processing_status.json` behavior as a side effect

The merged normalized table keeps the base table rows and appends continuation body rows after dropping continuation-only header/title rows. Its row indices are local to the merged artifact, while provenance records map each merged row back to the original table ID and original row index.

### Demographic Continuation Column Checks

`table_continuation_column_checks.json` records explicit continuation fragments
whose parent or continuation has the paper-table taxonomy category
`demographic_description`, including tables whose logical Table 1-style content
is not numbered as Table 1.

This artifact:

- requires clear continuation evidence before checking a pair
- compares the continuation to the closest prior fragment for the same table number
- records normalized column-count agreement
- records column-header signature agreement when headers are present, using
  `ColumnHeaderSchema.flattened_signature` when the schema is available
- records coordinate profiles from extracted cell bounding boxes when available
- reports column-coordinate status as compatible, possibly compatible, incompatible, missing, or partial
- does not merge tables or change `TableDefinition`, `ParsedTable`, or processing-status behavior

The public helper can fall back to the provisional `TableProfile` family
`descriptive_characteristics` when no paper-table taxonomy is available, but
the `parse` CLI artifact uses `paper_table_inventory.json` categories.

## 5. `table_definitions.json`

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

`TableDefinition` column assembly now consumes `ColumnHeaderSchema` when that
artifact is available. It still owns semantic roles such as `overall`, `group`,
`p_value`, and `smd`; it no longer needs to recover the header tree directly
from normalized rows.

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

## 5. Paper Context Artifacts

Current status:

- written by the `parse` CLI command
- derived from `pymupdf4llm` markdown, not from the table grid itself

Current CLI paths:

```text
outputs/papers/<paper_stem>/paper_markdown.md
outputs/papers/<paper_stem>/paper_sections.json
outputs/papers/<paper_stem>/paper_visual_inventory.json
outputs/papers/<paper_stem>/paper_references.json
outputs/papers/<paper_stem>/paper_variable_inventory.json
outputs/papers/<paper_stem>/table_contexts/table_<n>_context.json
```

Canonical models:

- `PaperSection`
- `PaperVisual`
- `PaperVisualReference`
- `PaperVariableInventory`
- child models: `VariableMention`, `VariableCandidate`
- `TableContext`
- child model: `RetrievedPassage`

Design components:

- `paper_markdown.md`
  raw markdown extracted from the full paper
- `paper_sections.json`
  markdown-derived sections with heading level and simple role hints
- `paper_visual_inventory.json`
  paper-level inventory of actual in-paper tables and figure captions, keyed by stable visual IDs such as `paper_visual:table:1`, with reference-check status fields showing whether the visual has at least one non-self text reference
- `paper_references.json`
  prose mentions of tables and figures, anchored to section/paragraph/character positions and resolved against the visual inventory when possible
- `paper_variable_inventory.json`
  paper-level variable-search artifact with broad mention-level records and a stricter consolidated candidate-variable list
- `table_contexts/*.json`
  per-table retrieval bundles keyed by `table_id` and internal extraction-order `table_index`; R-facing inspection should resolve these by the paper's `table_number` where available

`TableContext` design components:

- `table_id`, internal `table_index`, `table_label`
- `title`, `caption`
- `row_terms`
- `column_terms`
- `grouping_terms`
- `methods_like_section_ids`
- `results_like_section_ids`
- `reference_ids`
- `resolved_visual_ids`
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
- help readers distinguish references to actual in-paper tables and figures from unresolved or bibliographic mentions
- avoid tying retrieval to exact section names like `Methods`
- preserve `paper_markdown.md` as the paper-level markdown artifact, allowing only conservative glyph repair, and move derived structure into `paper_sections.json`
- preserve a JSON-first, inspectable context path alongside the table path

Variation note:

- papers may use different section names, heading levels, and table-reference styles
- that variation should be handled in section parsing and retrieval, not by redefining the meaning of `paper_markdown.md` beyond conservative glyph repair
- `docs/design/paper_markdown_spec.md` is the design reference for this artifact

## 6. `table_variable_plausibility_llm.json`

Current status:

- written by `review-variable-plausibility` when LLM configuration is available
- deterministic `parse` never writes this file
- written as an empty list when the review command runs but no tables are eligible or no review result is returned

Current CLI path:

```text
outputs/papers/<paper_stem>/table_variable_plausibility_llm.json
```

Canonical model:

- `LLMVariablePlausibilityTableReview`

Top-level shape:

```json
[
  {
    "...": "one LLMVariablePlausibilityTableReview object"
  }
]
```

Design components:

- `table_id`
- `variables`
- `notes`
- `overall_plausibility`

Design intent:

- preserve `table_definitions.json` as the deterministic baseline artifact
- keep the LLM review narrow and table-local
- preserve each supplied variable identity exactly and add `plausibility_score`
- validate the LLM output before writing this file
- keep this review separate from deterministic parse outputs so it cannot silently rewrite them

Debug-only companion artifacts:

- when `LLM_DEBUG=true`, `review-variable-plausibility` also writes a timestamped debug run under:

```text
outputs/papers/<paper_stem>/llm_variable_plausibility_debug/<timestamp>/
  llm_variable_plausibility_monitoring.json
  table_0/
    variable_plausibility_llm_input.json
    variable_plausibility_llm_metrics.json
    variable_plausibility_llm_output.json
    variable_plausibility_llm_review.json
```

- `llm_variable_plausibility_monitoring.json` summarizes every table's review status, including skipped-not-eligible tables
- per-table trace files are written only for tables that actually reached the provider call path

## 7. Variable-Plausibility Debug Trace Files

Current status:

- written only when `LLM_DEBUG=true`
- debug artifacts, not stable downstream interfaces

Current per-table file names:

- `variable_plausibility_llm_input.json`
- `variable_plausibility_llm_metrics.json`
- `variable_plausibility_llm_output.json`
- `variable_plausibility_llm_review.json`

Current top-level wrappers:

```json
{
  "report_timestamp": "...",
  "table_id": "...",
  "payload": {
    "...": "variable-plausibility LLM prompt payload"
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
  "review": {
    "...": "LLMVariablePlausibilityTableReview"
  }
}
```

Design intent:

- preserve the exact review payload, monitoring metrics, raw provider output, and validated review for inspection
- keep these files separate from canonical pipeline outputs such as `table_definitions.json`, `table_variable_plausibility_llm.json`, and `parsed_tables.json`
- preserve stable variable identity fields so disagreements can be audited safely
- keep the prompt payload compact; the saved input wrapper currently uses short payload keys such as `table` and `vars`

## 8. `ParsedTable` JSON

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

## 9. `table_processing_status.json`

Current status:

- canonical status schema exists now
- written by the `parse` CLI command as `table_processing_status.json`

Current CLI path:

```text
outputs/papers/<paper_stem>/table_processing_status.json
```

This file is written by:

- `table1-parser parse`

Top-level design components:

- `table_id`
- `status`
- `failure_stage`
- `failure_reason`
- `attempts`
- `notes`

`attempts` design components:

- `stage`
- `name`
- `considered`
- `ran`
- `succeeded`
- `note`

Design intent:

- record which existing rescue and repair paths were considered
- record which ones actually ran
- record whether a table ended as `ok`, `rescued`, or `failed`
- make empty descriptive-table parses explicit failures rather than silent success
- treat broad newline-stacked value cells as rescued when `metadata.column_repairs.extra_wide_value_column` successfully expands them into visual value columns

## 10. `parse_quality_reports.json`

Current status:

- canonical diagnostic schema exists now
- written by the `parse` CLI command as `parse_quality_reports.json`
- inspection artifact only; it does not alter table definitions or parsed tables

Current CLI path:

```text
outputs/papers/<paper_stem>/parse_quality_reports.json
```

Canonical model:

- `ParseQualityReport`
- child models: `ParseQualitySummary`, `DiagnosticItem`

Top-level design components:

- `table_id`
- `summary`
- `table_diagnostics`
- `row_diagnostics`
- `column_diagnostics`

Design intent:

- expose deterministic quality signals for every normalized table considered by `parse`
- make column-determination problems inspectable, including weak p-value columns, mostly empty columns, and group/overall columns with low value-pattern recognition
- keep softer quality warnings separate from `table_processing_status.json`, which records coarse pass/fail outcomes and rescue attempts
- preserve parse behavior: warnings and errors in this artifact do not halt parsing and do not rewrite `table_definitions.json` or `parsed_tables.json`
- allow `table_processing_status.json` to mark obvious non-table layout artifacts, such as article-info/abstract boxes emitted as explicit backend tables, as failed non-semantic candidates while preserving them in extraction and normalization artifacts
- support R-side inspection and corpus review before making higher-risk changes such as consolidated Table 1 parsing
- treat representative real-paper parsing checks as an important complement to unit tests, because deterministic table heuristics often fail on structural variants that synthetic tests do not cover

## 11. `paper_table_inventory.json`

Current status:

- canonical paper-level taxonomy schema exists now
- written by the `parse` CLI command as `paper_table_inventory.json`
- inspection and routing-support artifact only; it does not alter table definitions or parsed tables

Current CLI path:

```text
outputs/papers/<paper_stem>/paper_table_inventory.json
```

Canonical models:

- `PaperTableInventory`
- child model: `PaperTableRecord`

Top-level design components:

- `paper_id`
- `tables`

Each table record contains:

- `table_id`
- `table_number`
- `table_category`
- `category_confidence`
- `category_evidence`
- `continuation_of_table_number`
- `table_family`
- `processing_status`
- `failure_reason`
- `title`
- `caption`

Allowed `table_category` values:

- `demographic_description`
- `analysis_outputs`
- `data_presentation`
- `general`
- `unknown`
- `non_table_artifact`

Design intent:

- use the paper's table number as the public conceptual identifier where available
- keep continuation as `continuation_of_table_number`, with `null` when the table is not a continuation
- choose only one max-score category and persist only the chosen category, confidence, and evidence
- prioritize effect or estimate columns for `analysis_outputs`; p-values and model labels alone should not override a demographic-description classification
- recognize wide numeric matrices with threshold/statistic headers as `data_presentation`, especially when normalization has already expanded an extra-wide value column into visual value columns
- treat `table_category` as the broader concept that should drive parser-route selection once it is available; current `table_family` output is an earlier provisional route signal, not an independent semantic category
- keep this artifact deterministic and computable so R can expose it as a data frame or print method later

## Trace Wrappers vs Canonical Payloads

A simple rule:

- wrapper files are for debugging and auditability
- canonical payloads are for stable programmatic interfaces

Wrapper files currently include:

- `variable_plausibility_llm_input.json`
- `variable_plausibility_llm_metrics.json`
- `variable_plausibility_llm_output.json`
- `variable_plausibility_llm_review.json`

Canonical payloads currently include:

- `ExtractedTable`
- `NormalizedTable`
- `Table1ContinuationGroup`
- `TableDefinition`
- `LLMVariablePlausibilityTableReview`
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
