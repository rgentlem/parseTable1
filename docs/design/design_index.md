# Design Index

This file is a guide for coding agents and developers who need the main design-intent documents for this repository.

Read `AGENTS.md` first.

Then use the documents below as needed.

## Core Architecture

- `docs/design/codex_build_spec.md`
  Core project architecture and original schema/build spec.

- `docs/design/parsing_process.md`
  Short user-facing overview of the intended pipeline:
  `PDF -> ExtractedTable -> NormalizedTable -> TableDefinition -> ParsedTable`

- `docs/design/paper_parse_walkthrough.md`
  Human-readable walkthrough of the full `parse` command, including paper-level context artifacts and the reasons each intermediate table version exists.

- `docs/design/parsing_output_design.md`
  Current JSON artifact design, canonical models, and output-file intent.

- `docs/design/paper_document_plan_and_contract.md`
  Approved plan and durable contract for atomically replacing the full-paper
  text stream with one canonical interpreted `PaperDocument` that owns the
  block registry, narrative prose, document entities, and unresolved residual.

- `docs/implementation/paper_document_block_layout_implementation_plan.md`
  Accepted Steps 0–5 record for the non-operative block-first layout candidate:
  orientation-local regions, leaf lanes, spanning placements, and focused plus
  corpus validation without changing operative document order or ownership.

- `docs/implementation/paper_document_prose_flow_and_block_bibliography_plan.md`
  Active bibliography implementation plan: remove the block-construction
  dependency on line parsing, detect numbered bibitem blocks, retain the current
  unnumbered route, then cut ownership over atomically.

- `docs/design/cell_text_annotations.md`
  Extraction-side sidecar artifact for superscripts, subscripts, and small marker symbols attached to table cells.

- `docs/design/paper_footnotes.md`
  Contract for `paper_footnotes.json`: anchors, table-local footer metadata,
  definitions, glyph-key links, source scopes, suppression metadata, and R surface.

- `docs/design/paper_page_furniture.md`
  Contract for `paper_page_furniture.json`: repeated page text observations, clusters, ignored regions, and structural recurrence evidence.

- `docs/implementation/cell_text_annotations_implementation_plan.md`
  Short checklist for implementing the cell text annotation artifact, CLI output, R loading, and focused tests.

- `docs/implementation/rotated_cell_text_annotations_implementation_plan.md`
  Short checklist for supporting cell-text annotations on rotated or table-local geometry.

- `docs/implementation/paper_footnotes_implementation_plan.md`
  Short checklist for paper-level footnote anchors, definitions, glyph-key links, and tableone-aligned R inspection objects.

- `docs/implementation/paper_page_furniture_implementation_plan.md`
  Short checklist for detecting repeated page furniture and using it to protect footnote harvesting from watermarks, repeated headers/footers, marginal text, and download boilerplate.

- `docs/design/rescue_failure_logic.md`
  Structured rescue ordering, adequacy checks, and failure tracking for collapsed or empty table parses.

- `docs/design/parse_quality_reports_artifact.md`
  Design for writing deterministic row/column/value-pattern diagnostics as a normal parse artifact without changing parser behavior.

- `docs/design/table_continuation_resolution.md`
  Planned successor design for resolving explicit continued table fragments into a single working table artifact before semantic table definition, including schema-derived column compatibility gates and source provenance.

- `docs/design/separated_variable_description_integration.md`
  Succinct design for integrating variable labels and levels split across compatible continued table fragments.

- `docs/implementation/continued_variable_integration_implementation_spec.md`
  Concrete implementation spec for the continued-table variable integration artifact, boundary reinterpretation algorithm, provenance, CLI output, R inspection, and tests.

- `docs/design/column_header_schema.md`
  Design for a parser-native column header tree / column schema artifact between `NormalizedTable` and `TableDefinition`, preserving leaf columns, spanning header groups, raw cell evidence, and coordinates before downstream semantic projection or stored tableone-style summary rendering.

- `docs/design/collapsed_grid_refinement_scope.md`
  Narrow scope for consolidating the duplicated rotated/upright collapsed-grid refinement logic in the extractor.

- `docs/design/sideways_table_extraction_design.md`
  Design for detecting and extracting visually landscape tables drawn sideways on portrait PDF pages, including caption matching in transformed coordinates.

- `docs/design/categorical_block_state_scope.md`
  Narrow scope for stateful categorical-block tracking and standalone one-row-binary detection in deterministic row classification.

- `docs/design/split_label_column_repair_design_spec.md`
  Normalization-stage design for merging left-side row-label fragments that were split into two adjacent columns.

- `docs/implementation/fallback_inventory.md`
  Inventory of fallback, rescue, and downstream repair paths targeted for
  retirement as extraction becomes more accurate.

- `docs/design/value_parsing_spec.md`
  Planned symbol canonicalization and Table 1 `n (%)` parsing heuristics for the later value-parsing path.

- `docs/design/parsed_value_components.md`
  Design for index-keyed parsed-cell-value artifacts with typed value components before continuation fragments are semantically joined.

- `docs/implementation/parsed_value_components_implementation_plan.md`
  Stepwise implementation plan for writing component-native parsed value artifacts, semantic component joins, scope-limited validation, deferred diagnostics, and optional R inspection views.

- `docs/design/multitable_architecture_spec.md`
  Planned routing stage, descriptive-vs-estimate table families, and estimate-table schemas for mixed-table papers.

- `docs/implementation/multitable_implementation_plan.md`
  Stepwise implementation plan for `TableProfile`, LLM gating, and later estimate-table parsing.

## Value-Free Semantic Stage

- `docs/design/table_definition_scope.md`
  Scope for the proposed intermediate `TableDefinition` stage between `NormalizedTable` and `ParsedTable`.

- `docs/design/table_definition_schema.md`
  Proposed typed schema design for `TableDefinition` and related records.

- `docs/design/observed_tableone_component.md`
  Design for the downstream R-first, print-canonical semantic object built from parser JSON outputs.

- `docs/design/table_one_epidemiological_description.md`
  Scope and conceptual component model for Table One as an epidemiological description table: population, columns, rows, cells, and footnotes.

- `docs/implementation/table_definition_implementation_plan.md`
  Implementation plan for the SQL-query-oriented `TableDefinition` phase, including row-variable, categorical-level, and column-definition goals.

- `docs/implementation/column_grouping_semantics_plan.md`
  Focused implementation plan for the newer grouped-column semantics work inside deterministic `TableDefinition` assembly.

- `docs/implementation/column_header_schema_implementation_plan.md`
  Concrete implementation plan for adding `ColumnHeaderSchema`, writing `column_header_schemas.json`, then refactoring `TableDefinition`, continuation checks, and R inspection to consume the parser-native column model.

- `docs/implementation/parse_quality_reports_implementation_spec.md`
  Concrete implementation steps for writing `parse_quality_reports.json` and exposing deterministic quality diagnostics in R.

- `docs/implementation/normalized_column_repair_plan.md`
  Focused implementation plan for conservative normalization-time repair of split value columns and missed header rows.

- `docs/implementation/collapsed_grid_refinement_implementation_plan.md`
  Narrow implementation plan for consolidating duplicated rotated/upright collapsed-grid refinement logic in the extractor.

- `docs/implementation/table_geometry_reconstruction_checklist.md`
  Ordered checklist for table-local marker inventory, body occupancy evidence,
  leaf-column candidates, preliminary LaTeX-like header structure, canonical
  extraction, marker attachment, footer resolution, and corpus verification.

- `docs/implementation/sideways_table_extraction_implementation_spec.md`
  Concrete implementation plan for extracting visually landscape tables drawn sideways on portrait pages.

- `docs/implementation/categorical_block_state_implementation_spec.md`
  Focused implementation steps for categorical-block state and standalone one-row-binary detection in deterministic heuristics.

- `docs/implementation/split_label_column_repair_implementation_spec.md`
  Focused implementation steps for merging split left-side label columns during normalization.

## Supporting References

- `docs/design/paper_markdown_spec.md`
  Contract for the prose-only `paper_markdown.md` and `paper_sections.json`
  views over `PaperDocument.prose`, with raw text and geometry retained in the
  positioned-document artifacts.

- `docs/design/paper_visual_references.md`
  Planned paper-level visual-object and visual-reference artifacts for resolving table/figure mentions to actual in-paper tables and figures, preserving stable anchors for nearby text access, and later linking figure-image artifacts.

- `docs/design/paper_bibliography.md`
  Contract for `paper_bibliography.json`: per-paper bibliography entries plus
  observed numeric reference markers linked to those entries.

- `docs/design/paper_style_profile.md`
  Contract for `paper_style_profile.json`: per-paper summary of observed
  footnote-marker, bibliography, caption-placement, and visual-reference style
  conventions.

- `docs/implementation/paper_visual_references_implementation_plan.md`
  Stepwise implementation plan for visual-reference schemas, visual inventory, deterministic reference scanning and resolution, CLI artifacts, table-context links, and R inspection helpers.

- `docs/design/paper_variable_inventory.md`
  Planned paper-level variable-search and inventory artifact for cross-table consistency support.

- `docs/design/llm_integration.md`
  Current LLM integration and trace-artifact behavior.

- `docs/design/llm_semantic_inference_phase.md`
  Future-phase design for markdown-based semantic interpretation and adjudication. This is not the current implemented LLM path.

- `docs/implementation/llm_semantic_cli_changes.md`
  Historical implementation notes for the older parse-time semantic LLM plan.

- `docs/implementation/llm_semantic_inference_steps.md`
  Historical checklist for the older semantic inference phase.

- `docs/r_visualization.md`
  How current JSON outputs are inspected in R.

## RFCs

- `docs/rfcs/0001-nhanes-extension.md`
  Draft proposal for an optional NHANES-specific extension layer that consumes core parser outputs without embedding NHANES assumptions in the generic Table 1 pipeline.

## When To Read These

- If you are changing extraction, normalization, heuristics, LLM parsing, validation, or final exports:
  read `docs/design/codex_build_spec.md` and `docs/design/parsing_output_design.md`.
  If those changes alter the implemented paper parse flow or the role of any intermediate artifact, also update `docs/design/paper_parse_walkthrough.md`.

- If you are changing continued-table grouping, merged table artifacts, resolved semantic table sets, or source-table provenance for continuations:
  read `docs/design/table_continuation_resolution.md`.
  If the resolved table set becomes parser input, also update `docs/design/parsing_output_design.md` and `docs/design/paper_parse_walkthrough.md`.

- If you are changing symbol normalization, parser-facing text canonicalization, or categorical `n (%)` value parsing:
  read `docs/design/value_parsing_spec.md`.

- If you are changing mixed-table routing, LLM gating by table family, or estimate-result table parsing:
  read `docs/design/multitable_architecture_spec.md`.
  For concrete sequencing, also read `docs/implementation/multitable_implementation_plan.md`.

- If you are working on the new value-free semantic stage for database matching:
  read `docs/design/column_header_schema.md`, `docs/implementation/column_header_schema_implementation_plan.md`, `docs/design/table_definition_scope.md`, `docs/design/table_definition_schema.md`, and `docs/implementation/table_definition_implementation_plan.md`.

- If you are working on the downstream R-side component that consumes `table_definitions.json` and `parsed_tables.json`:
  read `docs/design/observed_tableone_component.md` and `docs/implementation/observed_tableone_r_plan.md`.

- If you are updating user-facing explanations of the pipeline:
  read `docs/design/parsing_process.md` and `docs/design/paper_parse_walkthrough.md`.
  Keep both documents aligned with the current implementation, not just the intended architecture.

- If you are changing positioned text streaming, rendered markdown views, section parsing, table/figure reference collection, or table-context retrieval:
  first read `docs/design/paper_document_plan_and_contract.md`, then read
  `docs/design/paper_markdown_spec.md`, `docs/design/paper_visual_references.md`,
  `docs/design/paper_variable_inventory.md`, and
  `docs/design/llm_semantic_inference_phase.md`.

- If you are changing paper-level variable search, section-priority logic, or cross-table semantic support:
  read `docs/design/paper_variable_inventory.md`, `docs/design/paper_markdown_spec.md`, and `docs/design/llm_semantic_inference_phase.md`.
