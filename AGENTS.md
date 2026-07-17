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

When working on documentation about Table 1 parsing, Table One semantics, or
R-side Table One inspection objects, also read:

docs/design/table_one_epidemiological_description.md

This Markdown design note provides context for documentation-level decisions
about what Table 1 represents. It is not, by itself, approval to change parser
logic.

Before starting parser work, also check:

docs/implementation/parser_todo.md

Use this file as the persistent implementation ToDo list. When work resolves, changes, or creates an important parser priority, update the ToDo list in the same change so project context does not get lost. Keep detailed epidemiology-table reasoning and implementation planning there or in a linked implementation note, not in the high-level design docs unless the schema, artifact contract, or pipeline design actually changes.

## Parser Logic Approval Gate

Do not change parser logic without explicit user approval for the specific
logic change. This includes extraction, normalization, table-region ownership,
header/body splitting, column geometry, row/column repair, bibliography
parsing, footnote parsing, diagnostics that alter pass/fail interpretation,
semantic table definition, value parsing, continuation handling, and R/Python
inspection behavior that changes how parser decisions are interpreted.

Before implementing parser logic changes, first report:

- the observed failure or design problem
- the exact files/functions likely involved
- the proposed logic change
- why the change is structural rather than ad hoc
- what existing fallback, repair, or competing path would be removed or aligned
- which real-paper checks and pytest commands would be run

Then wait for explicit approval before editing code. Investigation, read-only
analysis, artifact inspection, documentation-only clarification, and test runs
are allowed without approval. If the user explicitly says to implement a named
logic change, that counts as approval only for that described change; do not
expand the scope without asking again.

## Numeric Layout Tolerance Gate

Do not add, restore, adjust, extend, or newly rely on a numeric layout
tolerance in parser logic unless the user explicitly includes the exact,
case-sensitive magic keyword:

```text
APPROVE_LAYOUT_TOLERANCE
```

This additional gate applies even when the user otherwise asks to implement or
fix the parser. Without the magic keyword, agents may audit and propose a
numeric tolerance, but they must not implement it.

Numeric layout tolerances include fixed or derived thresholds involving PDF
points, x/y distances, line or row gaps, bbox offsets, near-equality windows,
font-size multiples, line-height multiples, overlap slop, or similar geometric
allowances. Do not replace one prohibited tolerance with another numeric
formulation.

Prefer exact, typed structural evidence instead: PDF text-block and line
identity, consecutive source order, font family and font-size transitions,
orientation groups, drawn-rule crossings, candidate and structural-scope
ownership, positioned heading/caption/DOI roles, and other explicit source
artifacts.

An existing numeric tolerance may be removed when the user explicitly approves
its removal; the magic keyword is not required to remove it. Changing its
value, moving it, restoring it, or using it in another decision path does
require the magic keyword.

When changing CLI behavior, persisted outputs, schema shape, markdown-context handling, or design assumptions, update the relevant `docs/*.md` files in the same change. Keep the design docs current.

When updating or replacing a process, also remove, retire, or explicitly align
all remaining artifacts, methods, docs, metadata fields, tests, and inspection
paths from previous, less comprehensive approaches. Do not leave parallel
cleanup or inference paths in place unless they have a clearly documented,
non-overlapping purpose.

If you change the implemented parse flow, the order of pipeline stages, the purpose of an intermediate artifact, or the paper-level/table-level outputs written by `table1-parser parse`, also update:

- `docs/design/paper_parse_walkthrough.md`

This document is the human-readable explanation of how one paper is processed end to end, so it must stay aligned with the actual implementation.

If you change paper-level variable search, section-priority logic, or any planned/implemented `paper_variable_inventory.json` artifact, also update:

- `docs/design/paper_variable_inventory.md`

---

# Local Epiconnector Project Context

This package lives inside the broader local project directory:

- `/Users/robert/Projects/Epiconnector`

Agents should treat that directory as local project context, not only the
`parseTable1` repository. When making parser design decisions, look for relevant
examples, prior work, or reference behavior in the broader Epiconnector
directory.

Important sibling paths:

- `/Users/robert/Projects/Epiconnector/parseTable1`
  - Python package repository for this parser.
- `/Users/robert/Projects/Epiconnector/tableone`
  - Local checkout/reference implementation for tableone-style data structures
    and display separation.
- `/Users/robert/Projects/Epiconnector/testpapers`
  - Standard real-paper PDF corpus for parser testing and review.

## Real-Paper Test Corpus

When asked to run examples, real papers, all papers, or the corpus, use:

```text
/Users/robert/Projects/Epiconnector/testpapers
```

Find PDFs recursively under that directory. Do not assume only one
subdirectory.

Also include the package example PDF:

```text
/Users/robert/Projects/Epiconnector/parseTable1/inst/extdata/NutritionEx.pdf
```

This is the single canonical copy used for corpus testing and future R
vignettes. Do not duplicate it under `testpapers`. The complete current corpus
is therefore 27 external PDFs plus this package example, for 28 PDFs total.
Installed R code can locate it with
`system.file("extdata", "NutritionEx.pdf", package = "parseTable1")`.

For broad parser changes, prefer testing against this corpus when practical,
especially before commits that change parse outputs, schemas, value parsing,
normalization, or table semantics.

When running multiple real-paper PDFs from the corpus, including the package
example above, use bounded parallel
workers by default so available CPU cores are used efficiently. A reasonable
default is up to 6 concurrent `table1-parser parse` processes, capped by the
number of PDFs and available cores. Use a serial run only when debugging a
single failure, reproducing ordering-sensitive behavior, or when parallelism is
causing resource problems.

### Paper naming in reports

Never identify a corpus paper to the user by an author surname, an internal
paper ID, a directory stem, or an invented abbreviation. Always give the exact
source PDF filename, the verified PDF page number, and the printed table number
when available. An internal table ID may be included only after that complete
identification. If a filename is unwieldy, repeat it anyway unless the user has
explicitly chosen a shorter name in the current discussion.

## Parser Output Directory

The parser writes generated outputs under:

```text
/Users/robert/Projects/Epiconnector/parseTable1/outputs
```

`outputs/` is generated program output and is gitignored. It should not be
treated as source code or committed.

When running batch tests on `testpapers`, write to a fresh ignored output
subdirectory such as:

```text
outputs/testpapers_batch_<timestamp>
```

or another clearly named batch directory. Existing outputs may be from earlier
runs and should not be assumed current unless just regenerated.

After a fresh batch or focused real-paper output run succeeds and the user does
not ask to preserve prior runs, remove older generated output directories so
`outputs/` contains only the current run needed for inspection. Do not delete
source PDFs, files under `/Users/robert/Projects/Epiconnector/testpapers`, or
any non-generated project files.

## Commit Hygiene

Do not stage or commit generated files under `outputs/`.

Before committing parser changes, report:

- which testpaper PDFs were run
- which output directory was used
- which papers failed, if any
- whether `pytest` passed

Before staging or committing changes for GitHub, explicitly check whether new
tests are needed for the work being committed. If new tests may be needed, stop
and describe the proposed tests, what behavior they protect, and why they are
worth adding. Do not implement those tests until the user gives specific
permission.

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

### No new fallback tools

Do not add fallback tools, rescue passes, downstream repair layers, or alternate
inference paths to compensate for weak extraction. The project direction is
accurate, layout-aware extraction first: page furniture, captions, table
regions, row/column geometry, horizontal rules, cell bounding boxes, and
structured artifacts should be correct near the front of the pipeline.

Treat wrong extraction as the highest-priority defect. Every bad extraction
usually creates multiple downstream errors in normalization, header schemas,
footnote linking, continuation handling, and semantic parsing. Do not fix those
secondary symptoms first. Identify the earliest artifact where the table,
caption, row, column, or cell geometry became wrong, then repair that extraction
or ownership step directly.

When extraction is wrong, improve the canonical extraction or region-ownership
stage. Do not add a later patch that guesses around the defect from cleaned
strings, paper-specific words, or semantic expectations. If a table cannot be
extracted accurately, fail closed with structured diagnostics and preserved raw
evidence.

Any temporary fallback that remains necessary must have a clearly documented
non-overlapping purpose, provenance metadata, real-paper evidence, and a
retirement criterion in:

```text
docs/implementation/fallback_inventory.md
```

### Preserve extraction unless evidence requires change

The primary project maxim is: extract accurately, then do nothing to the
extraction unless strong direct evidence shows that a change is necessary.

- Preserve extracted cells, coordinates, physical rows, physical columns, and
  source text by default.
- Treat disagreement with downstream semantics, expected table shape, or a
  preferred interpretation as a diagnostic, not as evidence that extraction
  should be rewritten.
- Require hard PDF evidence before changing extraction: positioned
  line/span/character geometry, individual rule segments, PDF tags, or another
  equally direct source artifact.
- Introduce new geometric evidence first as a non-operative, inspectable
  artifact. Validate it across the real-paper corpus before allowing it to
  alter extraction or row/column ownership.
- When evidence is absent or ambiguous, preserve the extract and fail closed
  with structured diagnostics. Do not guess, smooth, merge, shift, or repair
  the physical grid.
- Any approved extraction change must preserve raw provenance and demonstrate
  that corpus differences occur only in the intended direction.

### Use shared positioned PDF evidence

Parser work should make full use of PyMuPDF line/span/character evidence:
text, bounding boxes, block and line indices, font names, font sizes, flags,
writing direction when available, and page/column geometry. Do not replace
this with ad hoc cleaned-string rules when line/span evidence can answer the
question structurally.

Prefer one shared PDF text/geometry pass per document that collects the
positioned evidence needed by page furniture, captions, table extraction,
section text, bibliography, footnotes, and table metadata. Avoid adding
independent document parses that rebuild overlapping line/block/font views
unless there is a documented reason. If a second pass is temporarily necessary,
record why it exists and what artifact or refactor will retire it.

The staged direction for this redesign is:

1. First define or reuse a single positioned-text artifact that preserves the
   line/span/font/character fields needed by downstream consumers.
2. Then consume that artifact for narrow footer/table-metadata detection,
   using font change plus geometry below the table or ending horizontal rule.
3. Only after that artifact is stable should broader extraction, caption,
   bibliography, or semantic-routing cleanup move onto it.

This direction is architectural guidance, not blanket approval to change parser
logic. Parser logic changes still require the approval gate above.

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

In this local environment, use `python3` for Python commands. `python` may not
be available on `PATH`.

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

Do not create new tests without specific user permission. To request permission,
explain exactly what behavior the test would cover and why that coverage is
worth adding.

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
