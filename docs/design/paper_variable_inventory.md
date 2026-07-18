# Paper Variable Inventory

This document describes the implemented Phase 1 paper-level variable-inventory stage and the intended later uses of that artifact.

The purpose of this stage is to identify likely variable references across the paper and preserve them in a structured artifact before any stronger cross-table interpretation is attempted.

## Important Design Decision

The paper should have a prominent, explicit candidate-reference list of variables.

This is not a minor debug artifact. It is a first-class paper-level semantic artifact that should:

- be easy to inspect
- be saved at the top level of the paper output directory
- preserve provenance from text and tables
- support later one-table-at-a-time semantic interpretation
- be easy to consume from R

The project should treat this candidate-reference list as a major design decision for cross-table consistency.

It should also be treated as a cross-language object, not just a JSON blob.

- Python should have a clear typed model for it
- R should have a clear object/table representation for it
- JSON should act only as the transport format between those environments

## Goal

Build a paper-level inventory of likely variables from:

- paper text
- table titles
- table captions
- deterministic table variable labels
- deterministic table grouping labels when they appear variable-like

This inventory should help later table-level interpretation stay consistent across a paper without asking the LLM to interpret multiple tables in one prompt.

## Core Principle

Keep LLM prompting table-scoped.

- one table should be presented to the LLM at a time
- cross-table consistency should come from paper-level artifacts, not from multi-table prompting

The paper-level variable inventory is therefore a context artifact, not a replacement for per-table `TableDefinition`.

The object-design principle for this artifact is equally important:

- the inventory must be unambiguous in both Python and R
- mention-level and candidate-level records must have stable field meanings
- the file should be structured so it can be read directly into R inspection tools without custom deep parsing

## Two-Phase Plan

### Phase 1: Document Search and Inventory Building

This phase should:

- search the paper text for likely variable mentions
- harvest likely variable names from table artifacts
- preserve where each mention came from
- save a structured per-paper artifact

This phase should not yet try to fully interpret:

- whether two similar labels are truly the same biomedical concept
- whether a variable is exposure, outcome, confounder, subgroup, or model covariate
- whether one table's semantic interpretation should override another

The output of this phase is a conservative evidence inventory.

### Phase 2: Interpretation and Cross-Table Use

Later phases may use the inventory to:

- improve per-table retrieval
- improve table-level semantic LLM prompting
- support cross-table consistency checks
- support later paper-level variable adjudication

That later interpretation phase should remain separate from the first search-and-save phase.

## Position In The Current Pipeline

Current flow:

```text
PDF
-> paper_positioned_document.json
-> paper_document.json
-> paper_markdown.md + paper_sections.json
-> ExtractedTable
-> NormalizedTable
-> deterministic TableDefinition
-> paper_variable_inventory.json
-> per-table context bundles
-> one-table-at-a-time semantic LLM interpretation
```

This keeps:

- table structure local to each table
- variable searching global to the paper
- semantic interpretation local to one table at a time

## Text Sources To Search

The document-search phase should look for likely variable references in:

- abstract-like sections
- methods-like sections
- discussion-like or conclusion-like sections
- results-like sections
- table titles
- table captions
- deterministic table variable labels

Priority should be highest for:

- abstract-like sections
- methods-like sections
- conclusion-like or discussion-like sections

Secondary priority:

- results-like sections

Lower priority:

- other body sections with no clear role

## Sections To Exclude Or Deprioritize

The first inventory pass should not search the references or bibliography for variables.

It should also strongly deprioritize or exclude:

- acknowledgements
- author information
- funding statements
- conflict-of-interest sections
- supplementary navigation text that is not part of the paper body

The goal is to capture paper-semantic variable mentions, not every noun phrase in the PDF.

## Inventory Inputs

### Text-Based Mentions

Text-based mentions should be extracted from section paragraphs and labeled as text-derived evidence.

Each text-derived mention should preserve:

- the section it was found in
- the section heading
- the role hint for that section
- the paragraph-level evidence text or snippet

### Table-Derived Mentions

Table-derived mentions should come from:

- `TableDefinition.variables[*].variable_label`
- `TableDefinition.variables[*].variable_name`
- table title text
- table caption text
- `column_definition.grouping_label`
- `column_definition.grouping_name`

These should preserve the table they came from.

Important implementation rule:

- mention harvesting may stay broad
- candidate promotion must be much stricter than mention harvesting

The artifact is intentionally split this way:

- `mentions` are the audit trail of what was observed
- `candidates` are the consolidated paper-level variable list

## Artifact Path

Current output path:

```text
outputs/papers/<paper_stem>/paper_variable_inventory.json
```

This should be a paper-level artifact written next to:

- `paper_positioned_document.json`
- `paper_document.json`
- `paper_markdown.md`
- `paper_sections.json`
- `table_definitions.json`
- `table_contexts/*.json`

It should not be hidden inside a debug-only directory or nested deeply under table-specific outputs.

## Proposed Artifact Shape

The artifact should preserve both raw mentions and merged candidate variables.

It should also stay easy to load into R without bespoke JSON surgery.

That means:

- `mentions` should be a flat array of record-like objects
- `candidates` should be a flat array of record-like objects
- nested evidence should be kept shallow
- repeated IDs should be used instead of deeply nested structures when possible

Suggested top-level shape:

```json
{
  "paper_id": "paper_stem_or_other_identifier",
  "mentions": [
    {
      "...": "one raw mention record"
    }
  ],
  "candidates": [
    {
      "...": "one merged variable candidate"
    }
  ]
}
```

## Proposed Mention Record

Suggested fields:

- `mention_id`
- `raw_label`
- `normalized_label`
- `source_type`
- `mention_role`
- `canonical_label`
- `section_id`
- `heading`
- `role_hint`
- `paragraph_index`
- `evidence_text`
- `table_id`
- `table_index`
- `table_label`
- `priority_weight`
- `confidence`
- `notes`

Suggested `source_type` values:

- `text_based`
- `table_variable_label`
- `table_variable_name`
- `table_title`
- `table_caption`
- `table_grouping_label`

Interpretation notes:

- `text_based` means the mention was found in paper prose
- text-based mentions should always preserve the section location
- table-derived mentions should always preserve table identity
- `mention_role` should distinguish likely variables from levels, range bins, and artifacts
- a mention can be preserved in `mentions` even when it is intentionally excluded from `candidates`

## Proposed Candidate Record

Suggested fields:

- `candidate_id`
- `preferred_label`
- `canonical_label`
- `normalized_label`
- `canonical_label_source`
- `promotion_basis`
- `alternate_labels`
- `supporting_mention_ids`
- `source_types`
- `section_ids`
- `section_role_hints`
- `table_ids`
- `table_indices`
- `text_support_count`
- `table_support_count`
- `filtered_mention_count`
- `priority_score`
- `confidence`
- `interpretation_status`
- `notes`

Suggested `interpretation_status` values for the first phase:

- `uninterpreted`
- `merged_conservatively`
- `needs_review`

The first phase should prefer conservative merging and leave harder semantic consolidation for the later interpretation phase.

Current implementation rule:

- `candidates` should contain likely variables, not every harvested mention
- levels such as `Male` and `Female` must remain context-sensitive rather than globally banned
- range bins such as `25-30` should remain mention-level evidence, not candidate variables
- decorated table labels such as `BMI group (kg/m2), n (%)` should consolidate to a cleaner variable identity such as `BMI`

## R Accessibility Requirements

This artifact should be designed so that an R user can load it quickly and inspect it as two table-like data frames:

- one mention-level table
- one candidate-level table

Design requirements for R access:

- keep the file at the paper-root output level
- keep `mentions` and `candidates` row-oriented
- preserve IDs such as `mention_id`, `candidate_id`, `section_id`, and `table_id`
- prefer scalar fields and short vector fields over deeply nested objects

Matching Python requirements:

- define explicit typed models for mention-level and candidate-level records
- keep field names stable across serialization boundaries
- do not rely on Python-only object nesting patterns that are awkward to interpret in R

Planned downstream support should include a small R helper that can:

- load `paper_variable_inventory.json`
- return mention-level and candidate-level tables
- filter by section role, source type, mention role, or table index

## Section Priority Model

The first inventory pass should encode section priority explicitly.

Suggested priority ordering:

1. `abstract_like`
2. `methods_like`
3. `discussion_like` or `conclusion_like`
4. `results_like`
5. `unknown`

This priority should affect:

- ranking of candidate mentions
- merge confidence
- later selection of inventory entries for per-table prompting

The current implementation also uses section priority as part of candidate promotion.
High-priority text support is allowed to promote a candidate even when the table labels are messy.

## Conservative Merge Rules

The first phase should merge mentions conservatively.

Safe merge signals may include:

- canonical-label match after deterministic reduction
- repeated appearance across high-priority sections and table labels
- agreement between deterministic `variable_name` and text support

Unsafe merges should be deferred when:

- two labels differ in a clinically meaningful qualifier
- one label appears to be a subgroup while another is a main variable
- abbreviations are ambiguous
- two labels overlap lexically but may refer to different measurements

When uncertain, preserve multiple candidates rather than forcing a merge.

Current implementation note:

- aggressive consolidation is appropriate for adornments such as units, `n (%)`, `mean (SD)`, trailing `group`, and trailing `quintiles`
- aggressive consolidation is not appropriate for labels that might be true variables in one paper and levels in another; those require context-aware classification

## How Later Table-Level LLM Calls Should Use This Artifact

Later semantic LLM calls should still be scoped to one table.

For one table, the prompt may receive:

- the normalized table
- the deterministic `TableDefinition`
- the per-table retrieved passages
- the subset of paper-variable-inventory candidates that are relevant to that table

The inventory should act as soft supporting evidence, not as structural truth.

It must not let the LLM:

- invent rows
- invent columns
- infer variables that are not grounded in the current table rows

## Why This Stage Is Useful

This stage helps because papers usually describe a coherent family of variables across:

- the abstract
- methods
- conclusions or discussion
- descriptive tables
- model tables
- captions

Capturing that paper-level evidence early should make later semantic interpretation more consistent while keeping the prompt architecture safe and modular.

## Non-Goals

This stage should not:

- parse final numeric values
- replace `TableDefinition`
- replace `TableContext`
- force a single global ontology for the paper
- use the references section as a variable source
- send multiple tables in one LLM prompt

## Related Documents

- `docs/design/paper_markdown_spec.md`
- `docs/design/llm_semantic_inference_phase.md`
- `docs/design/table_definition_scope.md`
- `docs/design/paper_parse_walkthrough.md`
