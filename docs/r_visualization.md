# R Visualization

The repository includes small base-R helpers for visually inspecting parser JSON output.

File:

- [`R/visualize_table_from_json.R`](../R/visualize_table_from_json.R)
- [`R/inspect_paper_outputs.R`](../R/inspect_paper_outputs.R)
- [`R/pt1_json_io.R`](../R/pt1_json_io.R)
- [`R/observed_table_one.R`](../R/observed_table_one.R)
- manual pages in [`man/`](../man)

## Table Display Helper

The table display helper can display:

- stored normalized-table JSON such as `normalized_tables.json`
- row-oriented semantic debug payload JSON such as `table_definition_llm_input.json`
  these payloads currently use compact keys such as `rows`, `vars`, and `passages`
- parsed-table-style JSON that contains `variables`, `columns`, and `values`
- trace wrapper files that store the actual payload under `payload`, `interpretation`, or `response`

It is intended only for human inspection.

## Command-line usage

```bash
Rscript R/visualize_table_from_json.R outputs/papers/cobaltpaper/normalized_tables.json
```

## Interactive R usage

From the repo root:

```r
source("R/visualize_table_from_json.R")
options(width = 200)
visualize_table_from_json("outputs/papers/cobaltpaper/normalized_tables.json")
```

## Paper Output Inspection Helper

The paper-output inspection helper is for comparing deterministic and row-focused LLM semantics and reading the supporting paper context.

Public functions:

- `load_paper_outputs(paper_dir)`
- `show_paper_variable_mentions(paper_dir, role_hint = NULL, source_type = NULL, mention_role = NULL)`
- `show_paper_variable_candidates(paper_dir, min_priority = NULL)`
- `show_table_structure(paper_dir, table_index = 0L, variant = "deterministic", max_rows = NULL)`
- `compare_table_definitions(paper_dir, table_index = 0L)`
- `compare_table_definition_runs(paper_dir_a, paper_dir_b, table_index = 0L, variant_a = "deterministic", variant_b = "llm", label_a = NULL, label_b = NULL)`
- `list_llm_semantic_debug_runs(paper_dir)`
- `summarize_llm_semantic_monitoring(paper_dir, run_id = NULL)`
- `show_table_context(paper_dir, table_index = 0L, match_type = NULL)`
- `show_llm_evidence(paper_dir, table_index = 0L)`

These helpers use the same per-paper output directory already written by `table1-parser parse`.

### Interactive usage

From the repo root:

```r
source("R/inspect_paper_outputs.R")

x <- load_paper_outputs("outputs/papers/cobaltpaper")
show_paper_variable_candidates("outputs/papers/cobaltpaper")
show_paper_variable_mentions("outputs/papers/cobaltpaper", source_type = "text_based", mention_role = "variable")
show_table_structure("outputs/papers/cobaltpaper", table_index = 1L)
compare_table_definitions("outputs/papers/cobaltpaper", table_index = 0L)
compare_table_definition_runs(
  "outputs/no_llm/papers/Nephro",
  "outputs/with_llm/papers/Nephro",
  table_index = 0L,
  variant_a = "deterministic",
  variant_b = "llm",
  label_a = "no_llm",
  label_b = "with_llm_llm"
)
list_llm_semantic_debug_runs("outputs/with_llm/papers/Nephro")
summarize_llm_semantic_monitoring("outputs/with_llm/papers/Nephro")
show_table_context("outputs/papers/cobaltpaper", table_index = 0L, match_type = "table_reference")
show_llm_evidence("outputs/papers/cobaltpaper", table_index = 0L)
```

What these are for:

- `show_paper_variable_mentions(...)`
  print the raw mention-level evidence records from `paper_variable_inventory.json`, including `mention_role` and `canonical_label`
- `show_paper_variable_candidates(...)`
  print the merged candidate-variable records from `paper_variable_inventory.json`, including canonical labels and promotion metadata
- `show_table_structure(...)`
  print one saved table's normalized rows, deterministic columns, and row-variable definitions together
- `compare_table_definitions(...)`
  compare deterministic syntax-first row semantics with the LLM semantic interpretation
- `compare_table_definition_runs(...)`
  compare any two saved `table_definitions` variants, including cross-run comparisons such as `no_llm` deterministic vs `with_llm` semantic LLM
- `list_llm_semantic_debug_runs(...)`
  list timestamped semantic-debug runs written when `LLM_DEBUG=true`
- `summarize_llm_semantic_monitoring(...)`
  print a compact table of per-table semantic LLM status, elapsed time, payload size, and error fields for one debug run
- `show_table_context(...)`
  inspect the retrieved passages for one table
- `show_llm_evidence(...)`
  resolve variable- and level-level `evidence_passage_ids` in the LLM output back to the actual retrieved passages

Current limitation:

- the context helpers currently expose `section_id`, `heading`, `passage_id`, and passage text
- they do not yet expose page-number or line-number anchors
- the paper-variable inventory is currently a Phase 1 search artifact and does not yet alter table-context retrieval or LLM prompts
- raw mentions are intentionally broader than promoted candidates; ranges, levels, and artifacts may still appear in `show_paper_variable_mentions(...)`
- the current semantic LLM pass is row-only; columns remain deterministic

## Observed TableOne Helper

The repository now also includes package-oriented R helpers for constructing an observed, print-canonical semantic object from parser JSON outputs.

Main functions:

- `build_observed_table_one(table_definition, parsed_table, normalized_table = NULL, provenance = NULL)`
- `build_observed_table_one_from_paper_dir(paper_dir, table_index = 0L)`

Purpose:

- consume `table_definitions.json` and `parsed_tables.json`
- preserve printed row and column semantics in R
- separate continuous, categorical, and statistic blocks
- avoid pretending that the original subject-level dataset can be recovered

Example:

```r
source("R/pt1_json_io.R")
source("R/observed_table_one.R")

x <- build_observed_table_one_from_paper_dir("outputs/papers/cobaltpaper", table_index = 0L)
print(x)
```

Example output:

```text
Age [units: years]
  original: Age (years), mean (SD)

Sex
  original: Sex, n (%)
  levels:
    Male
    Female
```

### Notes on cleaning

- label cleaning is conservative
- units are preserved when they appear meaningful
- summary suffixes such as `n (%)` and `mean (SD)` are removed from the display name when appropriate
- the original label and original level labels are preserved in the returned structure

## Example Workflow

This is the simplest end-to-end workflow for one PDF:

1. Generate parser outputs with semantic debug artifacts enabled:

```bash
LLM_DEBUG=true table1-parser parse testpapers/OPEandRA.pdf
```

This creates a directory such as:

```text
outputs/papers/OPEandRA/llm_semantic_debug/<timestamp>/table_0/
```

2. Inspect the semantic input payload visually:

```bash
Rscript R/visualize_table_from_json.R outputs/papers/OPEandRA/llm_semantic_debug/<timestamp>/table_0/table_definition_llm_input.json
```

3. Do the same in interactive R if preferred:

```r
source("R/visualize_table_from_json.R")
options(width = 200)

visualize_table_from_json("outputs/papers/OPEandRA/llm_semantic_debug/<timestamp>/table_0/table_definition_llm_input.json")
```

## Notes

- Both helpers use base R only.
- The inspection helpers are documented with small future-compatible `.Rd` files under `man/`.
- It requires the `jsonlite` package.
- Level rows are indented for readability when that structure is present.
- Increasing `options(width = ...)` can make wide tables easier to inspect in the console.
