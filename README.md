# parseTable1

Research-oriented tooling for extracting, normalizing, heuristically interpreting, and LLM-refining Table 1-style epidemiology tables from PDFs.

## Current Status

- The main user command is now `table1-parser parse`, which runs the available pipeline stages once and writes all currently available paper outputs.
- The `extract` and `normalize` commands are still available for stage-specific inspection and debugging.
- `TableDefinition` is now implemented as a deterministic, value-free semantic representation of the table structure.
- `ParsedTable` is now emitted as the final structured value layer, with conservative numeric parsing and soft Table 1 `n (%)` heuristics.
- The repository also contains heuristic interpretation, diagnostics, and LLM-oriented developer tooling.

## Basic Idea

The goal of this project is to parse Table 1-style tables from epidemiology papers into structured representations that can be inspected, validated, and used by downstream tools.

The intended pipeline is:

```text
PDF -> ExtractedTable -> NormalizedTable -> TableDefinition -> ParsedTable
```

Each stage has a different purpose:

- `ExtractedTable`
  Raw table extraction from the PDF. This preserves the recovered grid, cell text, page information, and extraction metadata.

- `NormalizedTable`
  A cleaned and organized version of the extracted table. This separates header rows from body rows, preserves row structure, and computes row-level signals that help later interpretation.

- `TableDefinition`
  The value-free semantic stage. This captures which variables appear in the rows, which ones are categorical, what their levels are, and how the columns were constructed, without including the table's printed values.

- `ParsedTable`
  The final semantic output. This combines variable definitions, column meanings, and parsed table values into a structured format.

This separation is intentional. It keeps extraction, normalization, semantic interpretation, and final value output distinct, which makes the system easier to debug and safer to extend.

At the moment, the repository can persist:

- `ExtractedTable`
- `NormalizedTable`
- `TableDefinition`
- `ParsedTable`
- paper-level markdown context
- paper-level variable inventory

Today, a single call to `table1-parser parse` writes those artifacts from one extraction pass.
When LLM configuration is available, the same `parse` call also writes row-focused semantic LLM table definitions.

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
outputs/papers/<paper_stem>/table_profiles.json
outputs/papers/<paper_stem>/table_definitions.json
outputs/papers/<paper_stem>/parsed_tables.json
outputs/papers/<paper_stem>/paper_markdown.md
outputs/papers/<paper_stem>/paper_sections.json
outputs/papers/<paper_stem>/paper_variable_inventory.json
outputs/papers/<paper_stem>/table_contexts/table_0_context.json
```

If semantic LLM configuration is available, it also writes:

```text
outputs/papers/<paper_stem>/table_definitions_llm.json
```

For example:

```bash
table1-parser parse testpapers/cobaltpaper.pdf
```

This writes the extraction, normalization, table-definition, final parsed-table, and paper-context outputs in one run. When configured, it also writes row-focused semantic LLM table-definition output.

To suppress semantic LLM inference explicitly:

```bash
table1-parser parse path/to/paper.pdf --no-llm-semantic
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
table1-parser extract testpapers/cobaltpaper.pdf
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
table1-parser extract path/to/paper.pdf --outdir results
```

This writes to:

```text
results/papers/<paper_stem>/extracted_tables.json
```

If you want just the normalization stage:

```bash
table1-parser normalize path/to/paper.pdf
```

By default this writes JSON to:

```bash
outputs/papers/<paper_stem>/normalized_tables.json
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
compare_table_definitions("outputs/papers/cobaltpaper", table_index = 0L)
show_paper_variable_candidates("outputs/papers/cobaltpaper")
show_paper_variable_mentions("outputs/papers/cobaltpaper", source_type = "text_based", mention_role = "variable")
show_table_context("outputs/papers/cobaltpaper", table_index = 0L)
show_llm_evidence("outputs/papers/cobaltpaper", table_index = 0L)
```

These helpers are meant to make it easier to inspect the paper-level candidate variable inventory, distinguish broad mentions from promoted candidates, compare deterministic syntax-first row semantics with LLM semantics, and inspect the retrieved supporting passages.

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
      table_profiles.json
      table_definitions.json
      parsed_tables.json
      table_definitions_llm.json
      paper_markdown.md
      paper_sections.json
      paper_variable_inventory.json
      table_contexts/
        table_0_context.json
```

This keeps outputs for each paper in a separate directory and leaves room for trace and interpretation-stage outputs.
The `parse` command is intended to populate this directory with every available stage output from a single pipeline run.
When `LLM_DEBUG=true`, semantic LLM debug artifacts are written under `outputs/papers/<paper_stem>/llm_semantic_debug/<timestamp>/`.

## How To Read The Outputs

The easiest way to inspect one paper is:

1. start with `normalized_tables.json` to see the cleaned table structure
2. read `table_profiles.json` to see how each table was routed
3. read `table_definitions.json` to see the deterministic row and column interpretation
4. read `paper_variable_inventory.json` to see the paper-level candidate variable reference list
5. read `parsed_tables.json` to see the final structured values
6. read `table_definitions_llm.json` when present to see the context-aware row interpretation
7. use `paper_sections.json` and `table_contexts/*.json` to see the paper passages that support the semantic interpretation

In practice:

- `extracted_tables.json`
  best for raw PDF recovery, page numbers, and extracted captions
- `normalized_tables.json`
  best for stable row and column indices
- `table_definitions.json`
  best for the syntax-first semantic baseline
- `paper_variable_inventory.json`
  best for the paper-level candidate variable list and text/table provenance
- `table_profiles.json`
  best for understanding whether a table was treated as descriptive, estimate-like, or unknown
- `parsed_tables.json`
  best for the final structured row, column, and value output
- `table_definitions_llm.json`
  best for the paper-context-aware row-semantic view

## Syntax vs Semantics

The repository keeps syntax and semantics separate.

- syntax
  what rows and columns physically exist in the table
  main files: `extracted_tables.json`, `normalized_tables.json`
- semantics
  what the rows mean and which levels belong under them
  main files: `table_definitions.json`, `table_definitions_llm.json`

The deterministic and LLM semantic files both refer back to the same `table_id` and row-index space. Columns remain deterministic in the current LLM design.

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
  - retrieved `passages`

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
- they do not yet provide page anchors or line numbers inside the paper markdown

## How To Judge The LLM Output

The LLM output should be treated as an additional semantic interpreter, not hidden ground truth.

To evaluate it:

1. compare `table_definitions.json` with `table_definitions_llm.json`
2. check whether they point to the same rows
3. inspect the `evidence_passage_ids` in the LLM file
4. look up those passage IDs in the matching `table_contexts/table_<n>_context.json`
5. read the surrounding section in `paper_sections.json` when needed

Helpful signals already present in the LLM output:

- `evidence_passage_ids`
  which retrieved passages support a semantic claim
- `disagrees_with_deterministic`
  whether the LLM is explicitly challenging the deterministic interpretation

Current limitation:

- there is not yet an adjudicated merged output
- for now, users compare `table_definitions.json` and `table_definitions_llm.json` directly

## LLM Configuration

The semantic LLM parse path uses environment-variable-based configuration. If the variables are present, `parse` runs semantic LLM table-definition inference by default. If they are missing, `parse` warns and continues with deterministic outputs only. Use `--no-llm-semantic` to turn that path off explicitly.

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
export LLM_TIMEOUT_SECONDS=180
export LLM_MAX_RETRIES=2
export LLM_DEBUG=false
export LLM_SDK_DEBUG=false
```

More detail:

- [`docs/design/llm_integration.md`](docs/design/llm_integration.md)
- [`docs/implementation/llm_setup.md`](docs/implementation/llm_setup.md)

## Developer Tools

The repository also includes internal scripts for pipeline inspection, diagnostics, and synthetic data generation.

Pipeline summary:

```bash
python3 scripts/debug_pipeline.py testpapers/cobaltpaper.pdf
```

Diagnostics:

```bash
python3 scripts/debug_quality_report.py testpapers/cobaltpaper.pdf
```

Semantic LLM debug artifacts are written by `table1-parser parse` when `LLM_DEBUG=true`. The per-run directory contains `llm_semantic_monitoring.json` plus per-table files such as `table_definition_llm_input.json`, `table_definition_llm_metrics.json`, `table_definition_llm_output.json`, and `table_definition_llm_interpretation.json`.

## JSON Contracts

The repository keeps the table pipeline JSON-first. The current output and intermediate JSON design is documented in:

- [`docs/design/parsing_output_design.md`](docs/design/parsing_output_design.md)

For the current semantic LLM path, the main contract model is `table1_parser.llm.semantic_schemas.LLMSemanticTableDefinition`.
