# LLM Semantic Inference Phase

This document scopes the current row-focused semantic phase: using an LLM to interpret row semantics from the deterministic table structure and the surrounding paper text.

See also:

- `docs/design/paper_markdown_spec.md`

## Goal

Add an optional LLM-driven semantic interpretation stage that can:

- interpret row-variable meaning
- interpret categorical levels
- use paper context to challenge or support deterministic output
- preserve strict row safety

This phase is not for raw extraction or value parsing.

## Core Principle

Use two interpreters:

- deterministic parser for syntax and stable structure
- LLM interpreter for semantics and paper context

Both should speak. The system should preserve agreement and disagreement rather than hiding one behind the other.

One more principle is important:

- semantic LLM prompts should remain scoped to one table at a time
- paper-wide consistency should come from separate paper-level artifacts, not from prompting on multiple tables together

## Safety Rule

The LLM must never:

- invent rows
- invent values
- refer to row indices not present in the normalized table

The deterministic pipeline remains the source of structural truth.

## Pipeline Position

Target future flow:

```text
PDF
-> ExtractedTable
-> NormalizedTable
-> deterministic TableDefinition
-> paper_sections.json
-> paper_variable_inventory.json
-> document-context retrieval
-> LLM semantic TableDefinition
-> comparison / adjudication
-> flagged combined output
```

## Two PDF Views

Use two parallel views of the same paper:

1. Table syntax view

- extracted table grid
- normalized rows and headers
- deterministic row and column heuristics

2. Document context view

- `pymupdf4llm` markdown
- section headings
- paragraphs near table references
- table notes and footnotes

The first view supports syntax. The second supports semantics.

## Why Use `pymupdf4llm` Markdown

Markdown should be used for document context because it is easier to:

- identify headings and subheadings
- chunk the paper into sections
- retrieve passages mentioning `Table X`
- retrieve local prose around variable names and column labels
- send readable evidence to the LLM

It should not replace the structured table extraction path.

The persisted markdown artifact is `paper_markdown.md`. Its design intent and variation rules are defined in `docs/design/paper_markdown_spec.md`.

## Output Layout

The document-context artifacts should live in the same per-paper output directory as the table artifacts:

```text
outputs/papers/<paper_stem>/
  extracted_tables.json
  normalized_tables.json
  table_definitions.json
  paper_markdown.md
  paper_sections.json
  paper_variable_inventory.json
  table_contexts/
    table_0_context.json
    table_1_context.json
```

This keeps all paper-specific artifacts together and avoids recomputing markdown extraction.

When `LLM_DEBUG=true`, semantic-LLM debug artifacts should be written under a timestamped run directory inside the paper output directory, for example:

```text
outputs/papers/<paper_stem>/llm_semantic_debug/20260324T101500Z/
  llm_semantic_monitoring.json
  table_0/
    table_definition_llm_input.json
    table_definition_llm_metrics.json
    table_definition_llm_output.json
    table_definition_llm_interpretation.json
```

This keeps debug monitoring opt-in and prevents one debug run from overwriting another.

## Two-Phase Paper Context Strategy

The paper-context side should be split into two phases.

### Phase 1: Document Search and Variable Inventory

Before stronger interpretation, the system builds a paper-level candidate-reference list of variables.

This phase should:

- search likely prose sections for variable mentions
- prioritize abstract-like, methods-like, and conclusion-like sections
- harvest variable-like labels from tables, titles, and captions
- exclude or strongly deprioritize references / bibliography content
- save a structured `paper_variable_inventory.json` artifact

This inventory should be a first-class paper-level artifact, not a hidden debug output.

### Phase 2: Table-Focused Retrieval and Interpretation

After the paper-level variable inventory exists, each table can still build its own focused retrieval bundle and LLM prompt.

The LLM should receive:

- one table's normalized body rows
- one table's deterministic row definitions
- one table's retrieved passages
- the relevant subset of paper-level candidate variables

## Context Retrieval

For each `Table X`, retrieve:

- the table title and caption
- table footnotes / notes
- passages that mention `Table X`
- passages that mention row labels or close variants
- passages that mention column labels or grouping terms
- likely methods-like sections
- likely results-like sections

Keep the context small and evidence-oriented.

## Section Semantics

Do not rely on exact heading names like `Methods`.

Papers may use headings such as:

- `Methods`
- `Materials and Methods`
- `Study Design`
- `Study Population`
- `Measurements`
- `Covariates`
- `Exposure Assessment`
- `Statistical Analysis`
- `Patients and Methods`

Use deterministic heading extraction first, then let the LLM classify which sections are most likely:

- methods-like
- variable-definition sections
- subgroup-definition sections
- model-description sections
- results sections relevant to `Table X`

The LLM should therefore help identify methods-like sections from headings and short excerpts, rather than relying on exact section names.

This variation is expected and should be treated as normal, not as a special-case failure.

## LLM Inputs

The LLM should receive:

- normalized body rows
- deterministic row definitions
- caption and footnotes
- retrieved evidence passages with stable passage IDs
- the relevant subset of `paper_variable_inventory.json`

Those passages may come from differently named but methods-like, results-like, or model-description sections.

Current simplification:

- the semantic LLM input should omit deterministic `units_hint` and `summary_style_hint`
- the semantic LLM output should not try to re-derive per-variable units or summary-style labels
- those hints remain deterministic concerns for later value parsing

## Modularization

Keep the LLM phase split into small modules:

- `table1_parser/context/`
  markdown extraction, section parsing, paper-level variable inventory building, and `Table X` retrieval
- `table1_parser/llm/`
  semantic schemas, prompt building, and provider calls
- `table1_parser/adjudication/`
  deterministic vs LLM comparison and flagged combined output
- `table1_parser/validation/`
  row/column safety checks for LLM output

Do not combine retrieval, prompting, adjudication, and validation into one file.

Monitoring expectation:

- semantic debug output should record per-table timing
- it should record payload-size proxies such as row counts, passage counts, and prompt character counts
- it should preserve raw structured LLM responses when a provider call succeeds
- it should preserve failure status and error text when a call times out or validation fails

Inventory expectation:

- the paper-level candidate variable inventory should preserve where each mention came from
- text-based mentions should preserve section identity and heading
- the inventory should be easy to inspect from R as a mention-level table and a candidate-level table

## LLM Outputs

The LLM should return a value-free semantic interpretation that includes:

- row-linked variable judgments
- row-linked level judgments
- evidence passage references
- confidence
- explicit disagreement with deterministic output where relevant

It should not spend output capacity on:

- per-variable `units_hint`
- per-variable `summary_style_hint`

The LLM should be allowed to say:

- this row is not a variable
- these rows are levels under a parent variable
- the deterministic interpretation does not fit the paper context

## Adjudication

Persist three artifacts:

- deterministic `table_definitions.json`
- LLM `table_definitions_llm.json`
- adjudicated `table_definitions_adjudicated.json`

The adjudicated output should preserve:

- deterministic view
- LLM view
- agreement / disagreement flags
- chosen interpretation
- evidence references

## Good LLM Tasks

- resolve whether a row is a parent variable or a section label
- resolve whether following rows are levels
- identify likely row-level grouping concepts from caption and paper text
- spot semantic conflicts in deterministic output

## Out of Scope

Do not use the LLM in this phase for:

- raw PDF extraction
- row or column invention
- numeric value parsing
- database matching
- SQL generation

## Success Criteria

This phase is successful when the system can:

- retrieve paper context relevant to `Table X`
- let the LLM interpret semantics using that context
- preserve strict table-index safety
- expose deterministic / LLM agreement and disagreement clearly
- support later database matching and R-based inspection
