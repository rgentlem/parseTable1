# parseTable1

Research-oriented tooling for extracting, normalizing, heuristically interpreting, and optionally reviewing Table 1-style epidemiology tables from PDFs.

## Current Status

- The main user command is now `table1-parser parse`, which runs the available pipeline stages once and writes all currently available paper outputs.
- The `extract` and `normalize` commands are still available for stage-specific inspection and debugging.
- `ColumnHeaderSchema` is now the canonical column-axis artifact and the only supported basis for comparing or interpreting columns after normalization.
- `TableDefinition` is now implemented as a deterministic, value-free semantic representation of the table structure.
- `ParsedTable` is now emitted as the final structured value layer, with conservative numeric parsing and soft Table 1 `n (%)` heuristics.
- The repository also contains heuristic interpretation, diagnostics, paper-context artifacts, R inspection helpers, and a standalone LLM variable-plausibility review command.

## Real-Paper Review Status

The current real-paper review guide is:

- [`docs/implementation/real_paper_testing_guide.md`](docs/implementation/real_paper_testing_guide.md)

That file is the ordered checklist for corpus-driven review. It records the
current reference run, the papers to inspect next, and the known failure groups.

Current reference baseline:

```text
outputs/testpapers_footer_blocks_20260701_final
```

That run parsed the 27-PDF corpus under
`/Users/robert/Projects/Epiconnector/testpapers` with no command failures and
no missing core artifacts. At this point the table parser is being treated as
the current baseline: the next review work is focused on the remaining
footnote/reference artifacts, especially false-positive footnote anchors,
numeric citation-like markers, ambiguous repeated footer definitions, and
unresolved table references.

The extraction layer still uses the `pymupdf4llm` backend with raw PyMuPDF word,
character, and rule-geometry refinements for difficult cases. A later extraction
push should move difficult ruled or rotated tables toward a more direct
raw-PyMuPDF geometry path instead of adding downstream table-parsing fixes for
bad extracted grids.

## Basic Idea

The goal of this project is to parse Table 1-style tables from epidemiology papers into structured representations that can be inspected, validated, and used by downstream tools.

The intended pipeline is:

```text
PDF -> ExtractedTable -> NormalizedTable -> ColumnHeaderSchema -> TableDefinition -> ParsedTable
```

Each stage has a different purpose:

- `ExtractedTable`
  Raw table extraction from the PDF. This preserves the recovered grid, cell text, page information, and extraction metadata.

- `NormalizedTable`
  A cleaned and organized version of the extracted table. This separates header rows from body rows, preserves row structure, and computes row-level signals that help later interpretation.

- `ColumnHeaderSchema`
  The canonical column-header model. It records leaf columns, multicolumn spanning headers, group-to-leaf relationships, row-label columns, raw evidence, and coordinates where available.

- `TableDefinition`
  The value-free semantic stage. This captures which variables appear in the rows, which ones are categorical, what their levels are, and how the columns were constructed from `ColumnHeaderSchema`, without including the table's printed values.

- `ParsedTable`
  The final semantic output. This combines variable definitions, column meanings, and parsed table values into a structured format.

This separation is intentional. It keeps extraction, normalization, semantic interpretation, and final value output distinct, which makes the system easier to debug and safer to extend.

At the moment, the repository can persist:

- `ExtractedTable`
- `NormalizedTable`
- `ColumnHeaderSchema`
- `TableProfile`
- `TableDefinition`
- `ParsedTable`
- `TableProcessingStatus`
- paper-level markdown context
- paper-level variable inventory
- per-table paper-context bundles
- optional LLM variable-plausibility reviews

Today, a single call to `table1-parser parse` writes those artifacts from one extraction pass.
The `parse` command is deterministic and does not call an LLM. Optional LLM review is run separately with `table1-parser review-variable-plausibility`.

## Install

Clone the repository and enter the project directory:

```bash
git clone <repo-url>
cd parseTable1
```

```bash
python3 -m pip install -e .
```

## Quick Start

Run the available parse pipeline once and write all current stage outputs:

```bash
table1-parser parse path/to/paper.pdf
```

By default this writes:

```text
outputs/papers/<paper_stem>/extracted_tables.json
outputs/papers/<paper_stem>/normalized_tables.json
outputs/papers/<paper_stem>/column_header_schemas.json
outputs/papers/<paper_stem>/table_profiles.json
outputs/papers/<paper_stem>/table_definitions.json
outputs/papers/<paper_stem>/parsed_tables.json
outputs/papers/<paper_stem>/table_processing_status.json
outputs/papers/<paper_stem>/paper_markdown.md
outputs/papers/<paper_stem>/paper_sections.json
outputs/papers/<paper_stem>/paper_visual_inventory.json
outputs/papers/<paper_stem>/paper_references.json
outputs/papers/<paper_stem>/paper_variable_inventory.json
outputs/papers/<paper_stem>/table_contexts/table_0_context.json
```

For example:

```bash
table1-parser parse path/to/paper.pdf
```

This writes the extraction, normalization, column-header-schema, table-profile, table-definition, final parsed-table, processing-status, visual-reference, and paper-context outputs in one run.

To run the optional LLM variable-plausibility review:

```bash
table1-parser review-variable-plausibility path/to/paper.pdf
```

When LLM provider configuration is available, this reruns the deterministic pipeline and writes:

```text
outputs/papers/<paper_stem>/table_variable_plausibility_llm.json
```

The review is intentionally narrow. It scores whether each deterministic variable label, type, and categorical level structure looks plausible for an epidemiology Table 1. It does not rewrite `table_definitions.json`.

To write debug payloads and monitoring records for the review:

```bash
LLM_DEBUG=true table1-parser review-variable-plausibility path/to/paper.pdf
```

If you want just the raw extraction stage:

```bash
table1-parser extract path/to/paper.pdf
```

By default this writes JSON to:

```bash
outputs/papers/<paper_stem>/extracted_tables.json
```

For example:

```bash
table1-parser extract path/to/paper.pdf
```

produces:

```text
outputs/papers/cobaltpaper/extracted_tables.json
```

If you want the JSON on stdout instead of a file:

```bash
table1-parser extract path/to/paper.pdf --stdout
```

If you want a different root output directory:

```bash
table1-parser parse path/to/paper.pdf --outdir results
```

This writes to:

```text
results/papers/<paper_stem>/
```

The `extract`, `normalize`, `parse`, and `review-variable-plausibility` commands all accept `--outdir`.

If you want just the normalization stage:

```bash
table1-parser normalize path/to/paper.pdf
```

By default this writes JSON to:

```bash
outputs/papers/<paper_stem>/normalized_tables.json
```

The normalization JSON can also be printed to stdout:

```bash
table1-parser normalize path/to/paper.pdf --stdout
```

## R Visualization

The repository includes small base-R helpers for visual inspection of normalized, parsed, and trace-oriented JSON files.

```bash
Rscript R/visualize_table_from_json.R outputs/papers/cobaltpaper/normalized_tables.json
```

From an interactive R session:

```r
source("R/visualize_table_from_json.R")
options(width = 200)
visualize_table_from_json("outputs/papers/cobaltpaper/normalized_tables.json")
```

More detail:

- [`docs/design/parsing_process.md`](docs/design/parsing_process.md)
- [`docs/r_visualization.md`](docs/r_visualization.md)
- [`docs/design/parsing_output_design.md`](docs/design/parsing_output_design.md)

For paper-level inspection there is also:

```r
source("R/inspect_paper_outputs.R")
taxonomy_by_paper <- paper_table_inventory_list("outputs/papers")
summarize_table_processing("outputs/papers/cobaltpaper")
show_paper_table_inventory("outputs/papers/cobaltpaper")
show_table_structure("outputs/papers/cobaltpaper", table_number = 1L)
show_table_processing("outputs/papers/cobaltpaper", table_number = 1L)
show_paper_variable_candidates("outputs/papers/cobaltpaper")
show_paper_variable_mentions("outputs/papers/cobaltpaper", source_type = "text_based", mention_role = "variable")
show_table_context("outputs/papers/cobaltpaper", table_number = 1L)
```

Use `table_number` for public inspection. Extraction-order indices are retained only as low-level provenance/debug handles.

If `review-variable-plausibility` has been run:

```r
source("R/inspect_paper_outputs.R")
outputs <- load_paper_outputs("outputs/papers/cobaltpaper")
llm_variable_plausibility_df(outputs, table_number = 1L)
show_llm_variable_plausibility("outputs/papers/cobaltpaper", table_number = 1L)
list_llm_variable_plausibility_debug_runs("outputs/papers/cobaltpaper")
summarize_llm_variable_plausibility_monitoring("outputs/papers/cobaltpaper")
```

These helpers are meant to make it easier to inspect the paper-level candidate variable inventory, processing status, deterministic table structure, optional LLM variable-plausibility review, and table-context retrieval artifacts.

## Output Layout

The default root output directory is:

```text
outputs
```

Under that, outputs are organized by paper:

```text
outputs/
  papers/
    cobaltpaper/
      extracted_tables.json
      normalized_tables.json
      column_header_schemas.json
      table_profiles.json
      table_definitions.json
      parsed_tables.json
      table_processing_status.json
      paper_markdown.md
      paper_sections.json
      paper_visual_inventory.json
      paper_references.json
      paper_variable_inventory.json
      table_contexts/
        table_0_context.json
      table_variable_plausibility_llm.json        # when review-variable-plausibility is run
      llm_variable_plausibility_debug/            # when LLM_DEBUG=true
```

This keeps outputs for each paper in a separate directory and leaves room for trace and interpretation-stage outputs.
The `parse` command is intended to populate this directory with every deterministic stage output from a single pipeline run.
The `review-variable-plausibility` command adds the optional review artifact and any review debug files.
When `LLM_DEBUG=true`, variable-plausibility review debug artifacts are written under `outputs/papers/<paper_stem>/llm_variable_plausibility_debug/<timestamp>/`.

## How To Read The Outputs

The easiest way to inspect one paper is:

1. start with `extracted_tables.json` if the recovered table grid looks wrong
2. read `normalized_tables.json` to see the cleaned table structure
3. read `column_header_schemas.json` to see the canonical column axis before interpreting any column roles
4. read `table_profiles.json` to see how each table was routed
5. read `table_definitions.json` to see the deterministic row and column interpretation
6. read `paper_visual_inventory.json` and `paper_references.json` to see actual in-paper tables/figures and anchored prose mentions
7. read `paper_variable_inventory.json` to see the paper-level candidate variable reference list
8. read `parsed_tables.json` to see the final structured values
9. read `table_processing_status.json` to see whether each table parsed cleanly, was rescued, or failed
10. use `paper_sections.json` and `table_contexts/*.json` separately when you want to inspect the paper-context artifacts that may support later grounding work
11. read `table_variable_plausibility_llm.json` when present to see the optional LLM variable-plausibility review

In practice:

- `extracted_tables.json`
  best for raw PDF recovery, page numbers, and extracted captions
- `normalized_tables.json`
  best for stable row and column indices
- `column_header_schemas.json`
  best for column interpretation, including multicolumn headers, spanning groups, wrapped leaf headers, omitted continuation headers, and row-label columns outside value-region header groups
- `table_definitions.json`
  best for the syntax-first semantic baseline
- `paper_variable_inventory.json`
  best for the paper-level candidate variable list and text/table provenance
- `table_profiles.json`
  best for understanding whether a table was treated as descriptive, estimate-like, or unknown
- `parsed_tables.json`
  best for the final structured row, column, and value output
- `table_processing_status.json`
  best for understanding parse outcome, rescue attempts, and failure reasons
- `table_variable_plausibility_llm.json`
  best for reviewing LLM plausibility scores for deterministic variables, types, and levels

## Syntax vs Semantics

The repository keeps syntax and semantics separate.

- syntax
  what rows and columns physically exist in the table
  main files: `extracted_tables.json`, `normalized_tables.json`, `column_header_schemas.json`
- semantics
  what the rows mean and which levels belong under them
  main files: `table_definitions.json`, `parsed_tables.json`

`ColumnHeaderSchema` is the required bridge from syntax to column semantics. It is the only supported source for comparing or interpreting columns after normalization. This matters most for multicolumn headers, where a visible group label can span several lower-level columns, leaf labels can wrap over several physical rows, and continuation fragments can omit repeated headers. Parser tools, R inspection helpers, observed-table data-frame construction, and LLM context builders should consume this schema or a typed object derived from it rather than rebuilding column meaning from local header text.

The deterministic semantic files refer back to the same `table_id` and row-index space. The optional LLM review also preserves those variable identities, but it is a QA artifact rather than a replacement semantic definition.

The paper-level variable inventory is complementary rather than competitive with those table-level artifacts. It is the paper-scoped candidate reference list that later semantic work can consult while still keeping one table at a time in the LLM prompt.

## Finding Captions And Supporting Context

If you want to find the table caption or where the paper refers to a table:

- `extracted_tables.json`
  contains the extracted `title`, `caption`, and source `page_num`
- `table_definitions.json`
  carries `title` and `caption` forward into the value-free semantic layer
- `table_contexts/table_<n>_context.json`
  carries:
  - `table_label`
  - `title`
  - `caption`
  - linked `reference_ids`
  - linked `resolved_visual_ids`
  - retrieved `passages`
- `paper_visual_inventory.json`
  lists actual in-paper table and figure objects, including table IDs, figure captions, and whether each visual has a non-self text reference
- `paper_references.json`
  lists anchored table and figure mentions and marks each as `resolved`, `unresolved`, `external_or_bibliographic`, or `ambiguous`

The most useful passages for table references are usually those with:

- `match_type = "table_reference"`

Each retrieved passage includes:

- `passage_id`
- `section_id`
- `heading`
- `text`

You can use `section_id` to find the broader section in `paper_sections.json`.

Current limitation:

- the context files currently provide section IDs, headings, and passage text
- visual references provide section, paragraph, and character anchors, but not yet page anchors or line numbers inside the paper markdown

## How To Judge The LLM Review

The LLM variable-plausibility review should be treated as an inspection artifact, not hidden ground truth.

To evaluate it:

1. inspect `table_definitions.json` first to understand the deterministic variables and levels
2. inspect `table_variable_plausibility_llm.json` or use `show_llm_variable_plausibility(...)` in R
3. review low-scoring variables and their notes
4. check whether categorical variables have sensible child levels and whether binary variables look like one-row indicators
5. inspect `normalized_tables.json` if the LLM is reacting to a row that was misclassified before the review

Current limitation:

- the review does not change `table_definitions.json`
- for now, users inspect the deterministic parse and the plausibility review side by side

## LLM Configuration

The deterministic `parse` command does not call an LLM.

The optional `review-variable-plausibility` command uses environment-variable-based configuration. If provider setup is missing, it skips provider calls with a setup warning and writes an empty review artifact.

Minimum OpenAI setup:

```bash
export LLM_PROVIDER=openai
export OPENAI_API_KEY=your_api_key_here
export OPENAI_MODEL=gpt-4.1-mini
export LLM_TEMPERATURE=0
export LLM_TIMEOUT_SECONDS=60
export LLM_MAX_RETRIES=2
export LLM_DEBUG=false
export LLM_SDK_DEBUG=false
```

Minimum Qwen setup:

```bash
export LLM_PROVIDER=qwen
export DASHSCOPE_API_KEY=your_api_key_here
export QWEN_MODEL=qwen-plus
export QWEN_BASE_URL=https://dashscope.aliyuncs.com/api/v1
export LLM_TEMPERATURE=0
export LLM_TIMEOUT_SECONDS=60
export LLM_MAX_RETRIES=2
export LLM_DEBUG=false
```

More detail:

- [`docs/design/llm_integration.md`](docs/design/llm_integration.md)
- [`docs/implementation/llm_setup.md`](docs/implementation/llm_setup.md)

## Developer Tools

The repository also includes internal scripts for pipeline inspection, diagnostics, and synthetic data generation.

Pipeline summary:

```bash
python3 scripts/debug_pipeline.py path/to/paper.pdf
```

Diagnostics:

```bash
python3 scripts/debug_quality_report.py path/to/paper.pdf
```

Variable-plausibility LLM debug artifacts are written by `table1-parser review-variable-plausibility` when `LLM_DEBUG=true`. The per-run directory contains `llm_variable_plausibility_monitoring.json` plus per-table files such as `variable_plausibility_llm_input.json`, `variable_plausibility_llm_metrics.json`, `variable_plausibility_llm_output.json`, and `variable_plausibility_llm_review.json`.

## JSON Contracts

The repository keeps the table pipeline JSON-first. The current output and intermediate JSON design is documented in:

- [`docs/design/parsing_output_design.md`](docs/design/parsing_output_design.md)

For the current LLM review path, the main contract models are in `table1_parser.llm.variable_plausibility_schemas`.
