# AGENTS.md

This repository contains a Python package for extracting and parsing **Table 1-style epidemiology tables** from PDF documents.

The system works as a multi-stage parser:
1. Extract tables from PDFs.
2. Normalize them into a structured intermediate representation.
3. Parse them into variables, categorical levels, column roles, and values.
4. Use deterministic heuristics plus LLM assistance where needed.
5. Output normalized structured representations of the table.

The full architecture specification is in:

docs/design/codex_build_spec.md

Agents should always read that file before implementing features.

For parsing design intentions and newer semantic-table planning notes, also read:

docs/design/design_index.md

Before starting parser work, also check:

docs/implementation/parser_todo.md

Use this file as the persistent implementation ToDo list. When work resolves, changes, or creates an important parser priority, update the ToDo list in the same change so project context does not get lost. Keep detailed epidemiology-table reasoning and implementation planning there or in a linked implementation note, not in the high-level design docs unless the schema, artifact contract, or pipeline design actually changes.

When changing CLI behavior, persisted outputs, schema shape, markdown-context handling, or design assumptions, update the relevant `docs/*.md` files in the same change. Keep the design docs current.

If you change the implemented parse flow, the order of pipeline stages, the purpose of an intermediate artifact, or the paper-level/table-level outputs written by `table1-parser parse`, also update:

- `docs/design/paper_parse_walkthrough.md`

This document is the human-readable explanation of how one paper is processed end to end, so it must stay aligned with the actual implementation.

If you change paper-level variable search, section-priority logic, or any planned/implemented `paper_variable_inventory.json` artifact, also update:

- `docs/design/paper_variable_inventory.md`

---

# Project Goals

The package should:

- Detect Table 1 tables in epidemiology PDFs
- Extract the table grid
- Normalize row and column text
- Identify variables and categorical levels
- Identify column meanings
- Extract values into normalized long format

This is a **research-oriented parsing system**, not just a PDF table extractor.

---

# Output And Inspection Philosophy

The project is not designed around chat-style interaction with users.

Primary outputs should be:

- machine-readable parse artifacts
- stable Python and R data structures
- R-native inspection objects with print, summary, and data-frame methods
- computable artifacts that can support later analysis, validation, reporting, and review workflows

Human-readable output should generally be a view over structured artifacts, not the artifact itself.

In practice:

- JSON is the transport layer, not the conceptual model
- major paper-level and table-level concepts should have explicit schema objects
- R helpers should return structured objects invisibly where appropriate
- print methods should make those objects easy to review without hiding inference inside display code
- reports should be generated from persisted artifacts and structured R/Python objects
- CLI prose should remain minimal and should not be the only place where important parse decisions are represented

When adding new capabilities, prefer designs that create stable computable artifacts first, then add human-readable inspection or reporting views on top.

---

# Architectural Principles

Agents must follow these design principles.
Extraction, normalization, heuristics, LLM interpretation, and validation must remain separate modules.

## Repository size limits

Agents must not vendor third-party libraries.
Do not generate large files (>1 MB) in the repository.
Do not generate large example datasets or logs.

### Separation of responsibilities

Extraction, normalization, heuristics, LLM interpretation, and validation must be separate modules.

Never combine them into one step.

Pipeline structure should be:

PDF → ExtractedTable → NormalizedTable → TableDefinition → ParsedTable

### Intermediate schema

All extractors must produce the same canonical structure:

ExtractedTable

Interpretation must operate on:

NormalizedTable

Final results must be:

ParsedTable

Important cross-language rule:

- major semantic artifacts must be designed as clear objects in both Python and R
- JSON is the transport layer, not the conceptual model
- schema shapes should stay explicit, stable, and unambiguous across both languages

### Deterministic-first approach

Use rule-based parsing wherever possible.

LLM usage should be limited to semantic disambiguation, not raw extraction.

Paper-level candidate variable inventories are a first-class design artifact for later cross-table consistency.
Keep them explicit, inspectable, and easy to consume from R.

### No paper-specific parsing shortcuts

Parser behavior must be designed to generalize across papers, journals, diseases, cohorts, exposures, surveys, and statistical presentations. Do not solve a failing paper by inventing a vocabulary shortcut.

Do not add token lists such as particular disease names, survey names, outcome labels, exposure labels, statistic words, journal-specific phrases, or one-paper wording to decide parser structure. That does not generalize and usually turns one paper's extraction artifact into a hidden rule.

For all parser stages, prefer evidence that is structural, typed, and portable:

- horizontal rules and row bounds
- cell bounding boxes, text positions, and span/coverage
- adjacency of physical rows and columns
- body/value/header boundary evidence
- repeated, blank-spanned, or aligned cells as layout signals
- row and column density, indentation, and value-region shape
- schema-level constraints and validation failures
- paper-level artifacts that aggregate evidence explicitly

Domain vocabulary can be used only as weak semantic evidence after the structural parse is established, and it must not define rows, columns, spans, grouping, wrapping, continuation, or table boundaries by itself.

For multi-row column headers specifically: rows below the horizontal rule that separates headers from data are leaf-column headers; if that leaf-header area has multiple physical rows, treat them first as wrapped text for the same leaf headers. Rows above that rule may become spanning groups only when their cells cover multiple lower-level leaves or groups. If additional rules split higher header bands, process those bands recursively by geometry. Do not promote a physical row into a semantic hierarchy level just because it contains recognizable words.

### LLM safety rules

When the LLM is used:

- It must never invent rows or columns
- It must only refer to rows that exist in the table
- It must return structured JSON
- All results must be validated before being accepted
- LLM prompts should remain scoped to one table at a time
- Cross-table consistency should come from separate paper-level artifacts, not from multi-table prompting

### Preserve raw data

Raw extracted cell values must never be discarded.

Normalized values must always preserve the original text.

---

# Coding Requirements

## Python version

Use:

Python 3.11+

### Function Design & Patterns
- **No Single-Use Helpers**: NEVER extract logic into a separate helper function if it is only used once within a single parent function.
- **Inline Logic**: Keep one-time logic inline to maintain readability and reduce "jumping" between function definitions.
- **Exception**: Only extract one-time logic if it significantly improves readability of a complex algorithm (e.g., more than 20 lines of distinct logic) and comment it clearly.

## Typing

Use full type hints everywhere.

Public functions must include type hints.

## Data models

Structured data must use **Pydantic models**.

Avoid unstructured dictionaries where possible.

## File organization

Follow the structure defined in:

docs/design/codex_build_spec.md

Do not collapse modules into one file.

## Tests

All modules must be testable.

---

# Style Guidelines

Prefer:

- small, focused modules
- pure functions where possible
- clear docstrings
- explicit data models

Avoid:

- global state
- large monolithic classes
- hidden side effects

---

# Error Handling

Extraction pipelines must fail gracefully.

If a table cannot be parsed:

- return a structured error
- do not crash the pipeline

---

# What Agents Should NOT Do

Do not:

- attempt to solve the entire pipeline in one module
- skip schema definitions
- rely entirely on LLM interpretation
- assume all tables have identical structure

Table 1 formats vary across journals.

The system must be robust to variation.

---
