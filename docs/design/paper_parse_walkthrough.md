# Paper Parse Walkthrough

This document explains, in human terms, what happens when this project parses one paper and why it keeps several intermediate versions of each table.

It is a companion to:

- `docs/design/parsing_process.md` for the short overview
- `docs/design/parsing_output_design.md` for the canonical artifact contract

The goal here is not to restate every schema field. The goal is to explain the flow of work from one PDF to the saved outputs, and to make clear why the parser does not jump straight from PDF text to a final structured table.

## One Paper, Many Artifacts

The main user-facing command is:

```bash
table1-parser parse path/to/paper.pdf
```

For one paper, this writes a paper output directory:

```text
outputs/papers/<paper_stem>/
```

Today that directory may contain:

- `extracted_tables.json`
- `normalized_tables.json`
- `table_profiles.json`
- `table_definitions.json`
- `parsed_tables.json`
- `paper_markdown.md`
- `paper_sections.json`
- `paper_variable_inventory.json`
- `table_contexts/table_<n>_context.json`
- `table_definitions_llm.json` when semantic LLM inference runs
- `llm_semantic_debug/...` when semantic LLM debug tracing is enabled

Some of these are per-table artifacts. Others are paper-level context artifacts.

## Why There Are Multiple Versions Of A Table

The parser deliberately keeps several versions of the same table because each stage answers a different question.

- `ExtractedTable` answers: what did the PDF extractor recover?
- `NormalizedTable` answers: what cleaned table structure should downstream logic reason over?
- `TableProfile` answers: what kind of table does this appear to be?
- `TableDefinition` answers: what do the rows and columns mean, before we parse values?
- `ParsedTable` answers: what final variables, levels, columns, and values did we infer?

If the system skipped these stages and wrote only one final output, it would be much harder to debug extraction errors, normalization repairs, header mistakes, row-type mistakes, and value-parsing mistakes.

## High-Level Flow

The current implemented flow for `parse` is:

```text
PDF
  -> extracted tables
  -> normalized tables
  -> table profiles
  -> table definitions
  -> parsed tables

PDF
  -> paper markdown
  -> paper sections
  -> paper variable inventory
  -> per-table context bundles

normalized table + table definition + table context
  -> optional semantic LLM table definition
```

Two points matter here.

First, the table pipeline and the paper-context pipeline are related but separate.

Second, the optional semantic LLM path currently produces an additional semantic artifact. It does not replace the deterministic parsed table path by default.

## Step 1: CLI Entry And Paper Setup

The CLI first validates that the PDF exists and determines the output directory.

At this point, nothing semantic has happened yet. The system is just deciding whether it can run and where to write artifacts.

Why this is separate:

- it keeps command failures simple and predictable
- it avoids half-written outputs when the input path is wrong

## Step 2: Table Extraction

The extraction layer is responsible for finding likely tables in the PDF and recovering a raw grid for each one.

Conceptually, this stage does three things:

1. inspect the PDF page layout
2. find table candidates
3. build `ExtractedTable` objects for the deduplicated candidates

The current extractor uses `pymupdf4llm` as the main backend. It tries to recover explicit table boxes and table cell grids from the backend JSON output. When that is not enough, it can fall back to text-position-based layout reconstruction.

For some explicit tables, the backend cell grid is too coarse even though the page still contains enough geometry to do better. When a table shows strong grouped-header signals, such as repeated `Model 1`, `Model 2`, `Model 3` blocks plus wide horizontal boundaries, extraction can now refine the explicit backend grid using word positions inside the table bounding box.

That refinement is no longer limited to upright tables. For rotated explicit tables, extraction can normalize the clipped word and rule coordinates into a table-local upright frame, rebuild the row/column grid there, and then write the improved grid into `ExtractedTable` while preserving the original rotation metadata separately.

The extractor still scores candidates, but the score is now diagnostic rather than a hard keep-drop gate for explicit extracted tables. The current rule is:

- deduplicate exact candidate collisions
- preserve explicit extracted table candidates in stable page/index order
- record confidence and caption signals in metadata instead of silently dropping low-scoring tables
- allow explicit-table grid refinement when rule and word geometry clearly support a better internal column structure

This matters for papers with table continuations, odd numbering, or weak captions. A bad score should be inspectable, not silently destructive.

### What `ExtractedTable` Contains

`ExtractedTable` is the raw table-facing artifact. It keeps:

- `table_id`
- page number
- detected title and caption when available
- detected table-number and continuation metadata in `metadata` when a caption supports it
- row and column counts
- raw cell text
- optional cell bounding boxes
- extractor metadata

This is the parser's record of what came out of the PDF layer.

That does not always mean “what one backend reported verbatim.” If the backend emits one fused model column but the table bbox, word positions, and wide horizontal rules clearly support a better grid, extraction may refine that grid before writing `ExtractedTable`.

For rotated refinements, the recovered `row_bounds` and `horizontal_rules` may be expressed in a table-local normalized coordinate frame rather than the original page frame. That is intentional: later stages use those values as structural boundaries, not as page-annotation coordinates.

### Why `ExtractedTable` Exists

This is the audit trail for extraction.

If a value is wrong here, the problem is in extraction, not in later semantic logic.

If a value is correct here but wrong later, the problem is in normalization or parsing.

That distinction is one of the main reasons the project keeps intermediate artifacts.

## Step 3: Normalization

Normalization converts each `ExtractedTable` into a `NormalizedTable`.

This is the first stage that prepares the table for interpretation, but it still avoids making strong semantic claims such as "this row is definitely a categorical parent variable" or "this cell definitely means a count and percent."

### What Normalization Does

Normalization currently performs several practical cleanup steps.

#### 3.1 Build A Stable Row Grid

The extracted cells are reassembled into a row-major grid.

This gives the downstream logic a stable rectangular structure to reason over.

#### 3.2 Trim Obviously Non-Informative Edge Columns

Some extracted tables contain junk leading or trailing columns, often because the PDF layout has an empty margin column, a rule fragment, or other extractor noise.

Normalization can conservatively drop:

- a mostly non-informative leading column
- a mostly empty trailing column

Why this happens here:

- it is a structural cleanup, not a semantic inference
- later row and column interpretation is cleaner when the table edges are already sane

#### 3.3 Produce Parser-Facing Cleaned Rows

Normalization builds `metadata.cleaned_rows`, which is the parser-facing text version of the table.

This cleaned form is used by downstream heuristics, prompting, and debugging.

The shared text cleaning layer currently does things like:

- collapse whitespace
- normalize symbol variants such as dash forms and comparator forms
- repair a narrow set of known extractor glyph failures

One example of that last category is a broken replacement character such as `�0.12` being repaired to `<=0.12` in parser-facing text.

Important design rule:

- raw extracted cell text is still preserved earlier in `ExtractedTable`
- cleaned parser-facing text belongs in normalization and later stages

#### 3.4 Record Text Cleaning Provenance

Normalization now also records `metadata.text_cleaning_provenance`.

This is a table-level audit summary showing, for the surviving normalized grid:

- which comparator symbols were observed directly
- which comparator symbols were reconstructed from known extractor glyph-failure rules
- which repair rules fired
- how many cells needed glyph repair

This exists because parser-facing cleanup is useful, but it should not be invisible.

#### 3.5 Detect Header Rows

Normalization separates header rows from body rows.

The detector uses the cleaned grid and, when available, row geometry such as row bounds and horizontal rules.

This is an important turning point in the parse, because many later steps assume the system already knows which rows are header material and which rows are body material.

Why header detection belongs here:

- it is still structural
- later semantic steps need this split
- it is easier to debug when header decisions are visible before full semantic interpretation

#### 3.6 Build Row Signatures

For each body row, normalization builds a `RowView`.

`RowView` is a compact row-level feature record. It keeps:

- raw row cells for the body row
- cleaned first-cell forms
- whether the row has trailing values
- simple numeric density signals
- indentation when it can be inferred

This gives later heuristics a small and inspectable summary of the row rather than forcing every heuristic to re-derive low-level row facts from scratch.

#### 3.7 Repair Split Count-Percent Columns

Some tables are extracted with one logical `n (%)` value split across two adjacent columns, such as:

```text
199    (11.5%)
```

Normalization can conservatively merge those back into one logical cell when the surrounding row pattern strongly supports that interpretation.

This is one of the main reasons normalization exists as a real stage rather than a trivial cleanup wrapper.

It is not just prettifying text. It is repairing table structure in a controlled way before semantic interpretation starts.

#### 3.8 Drop Columns Emptied By Repair

If a split-value repair empties a helper column across the table, normalization can drop that now-empty column and rerun header detection on the repaired grid.

This keeps the normalized grid closer to the logical table structure that the later parser actually wants.

#### 3.9 Decide Whether Indentation Is Informative

For some papers, first-column indentation clearly helps distinguish parent rows from level rows.

For other papers, small horizontal shifts are just extraction noise.

Normalization records whether indentation appears informative enough to matter later.

### What `NormalizedTable` Contains

At the end of normalization, each table has:

- `header_rows`
- `body_rows`
- `row_views`
- `metadata.cleaned_rows`
- edge-column repair information
- header-detection diagnostics
- indentation diagnostics
- text-cleaning provenance

### Why `NormalizedTable` Exists

This artifact is where the table becomes parser-friendly without yet becoming fully semantic.

That separation matters because many downstream mistakes are really normalization mistakes, not semantic mistakes.

## Step 4: Table Routing With `TableProfile`

Once a table has been normalized, the parser builds a `TableProfile`.

This is a routing and eligibility stage. It asks questions like:

- does this table look descriptive or estimate-like?
- should semantic LLM interpretation run for this table?

The current repository is centered on Table 1 style descriptive tables, but mixed-table papers exist. `TableProfile` is the stage that prevents the system from pretending every table belongs to the same family.

Why this stage exists:

- it keeps mixed-table handling explicit
- it lets the deterministic parser decide whether an LLM step is even relevant

## Step 5: Build `TableDefinition`

`TableDefinition` is the value-free semantic interpretation of the normalized table.

This means it tries to answer:

- which rows represent variables?
- which rows are levels under a variable?
- which columns are group columns, overall columns, or statistic columns?

But it does not yet parse all displayed values into final numeric records.

### What `TableDefinition` Tries To Recover

For rows:

- continuous variable rows
- categorical parent rows
- child level rows
- variable labels
- normalized variable names
- row spans
- units hints
- summary-style hints

For columns:

- label column vs data columns
- overall vs group vs p-value vs trend vs SMD style columns
- grouped-column structure when it can be inferred

One implemented heuristic detail is worth calling out explicitly:

- a row with empty group columns but populated test or statistic columns can still be a variable header
- if that row is followed by plausible child levels such as `Yes` and `No`, it should be treated as a new variable, not as another level under the previous variable

This matters for printed Table 1 layouts where the parent row carries only the p-value or trend-test result and the level rows carry the group counts.

### Why `TableDefinition` Exists

This is one of the most important design choices in the project.

The parser does not jump directly from a normalized grid to parsed numeric values because it is useful to have a stable semantic layer that describes what the table means before any value parsing happens.

This makes it easier to:

- inspect row and column meaning independently of value parsing
- support downstream matching and R-side table objects
- compare deterministic semantics with future LLM semantics

## Step 6: Build `ParsedTable`

`ParsedTable` is the final deterministic structured table output.

This stage combines:

- the normalized table grid
- the table definition
- value parsing heuristics

and produces normalized long-format value records.

### What Happens Here

The parser walks the semantic row and column structure and tries to parse each relevant displayed cell into a structured value record.

Examples include:

- count and percent pairs
- mean and standard deviation pairs
- median and IQR style summaries
- p-values
- scalar counts

### Why `ParsedTable` Is Separate From `TableDefinition`

Because row and column semantics can be right even when value parsing is wrong, and vice versa.

Keeping these apart makes debugging much more honest.

## Step 7: Build Paper-Level Document Context

The parser also builds a paper-level context representation from the whole document.

This is separate from table extraction.

The current paper-context path is:

```text
PDF -> paper_markdown.md -> paper_sections.json -> paper_variable_inventory.json -> table_contexts/*.json
```

### `paper_markdown.md`

This is the full-paper markdown context artifact, produced from `pymupdf4llm`.

It is not the canonical table grid.

It is used for:

- section detection
- table mention retrieval
- variable-term retrieval
- future semantic grounding

Only conservative glyph repair is allowed here. This artifact is not meant to become a second normalization pipeline.

### `paper_sections.json`

The markdown is split into a linear list of sections, with simple role hints such as methods-like or results-like.

This gives the parser a document structure that is easier to retrieve from than raw markdown alone.

### `paper_variable_inventory.json`

The parser then builds a paper-level candidate reference list of variables.

This artifact records:

- raw mention-level evidence from prioritized prose sections
- variable-like labels harvested from deterministic table definitions
- mentions found in table titles and captions
- conservative merged candidate variables with provenance back to mentions

This is a Phase 1 search artifact, not a final interpretation layer. It is intended to stay easy to inspect in both Python and R.

### `table_contexts/*.json`

For each table, the parser builds a focused context bundle using:

- the section list
- the table title and caption
- variable labels
- grouping labels

This produces per-table passages and term lists that can later support semantic interpretation.

## Step 8: Optional Semantic LLM Interpretation

If enabled and eligible, the parser can run semantic LLM inference using:

- compact body-row hints
- compact deterministic variable spans
- the per-table paper context

This produces `table_definitions_llm.json`.

Current implemented scope:

- interpret row variables
- interpret categorical levels under those variables
- attach supporting evidence passages

Columns remain deterministic in this phase.

This is not the same thing as raw extraction or generic OCR assistance. It is a later semantic interpretation phase grounded in already extracted table structure.

Why this stage is optional:

- deterministic structure should do as much as possible first
- LLM use should be focused on ambiguity, not raw PDF recovery
- semantic calls should be inspectable and skippable

## What A Human Should Inspect First

When a parse looks wrong, inspect the outputs in this order.

1. `extracted_tables.json`
   If the raw grid is already wrong, stop here. The problem is extraction.

2. `normalized_tables.json`
   If the raw grid was usable but header rows, edge trimming, split-value repair, or cleaned text are wrong, the problem is normalization.

3. `table_profiles.json`
   If the table was routed to the wrong family or LLM eligibility looks wrong, the problem is in routing.

4. `table_definitions.json`
   If row meanings or column meanings are wrong, the problem is in the semantic heuristics.

5. `parsed_tables.json`
   If row and column meanings are right but the final values are wrong, the problem is in value parsing.

6. `paper_markdown.md`, `paper_sections.json`, `paper_variable_inventory.json`, and `table_contexts/*.json`
   If semantic context retrieval is weak, inspect these next.

7. `table_definitions_llm.json`
   If deterministic semantics were reasonable but the semantic LLM output is poor, the issue is in context retrieval, prompting, provider behavior, or validation.

## Why This Pipeline Shape Is Worth Keeping

The system is intentionally not "PDF in, one JSON out."

The multiple stages are not accidental complexity. They are what make the parser inspectable and research-friendly.

This separation gives the project:

- raw extraction provenance
- parser-facing structural cleanup
- explicit routing for mixed-table papers
- value-free semantics before value parsing
- optional document-grounded semantic interpretation
- easier debugging when a paper fails in only one part of the pipeline

That is the main reason the project can support both engineering work and research iteration without collapsing all errors into one opaque final output.
