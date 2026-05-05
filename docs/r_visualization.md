# R Visualization

The repository includes small base-R helpers for visually inspecting parser JSON output.

Files:

- [`R/visualize_table_from_json.R`](../R/visualize_table_from_json.R)
- [`R/inspect_paper_outputs.R`](../R/inspect_paper_outputs.R)
- [`R/pt1_json_io.R`](../R/pt1_json_io.R)
- [`R/observed_table_one.R`](../R/observed_table_one.R)

## Table Display Helper

The table display helper can display:

- stored normalized-table JSON such as `normalized_tables.json`
- compact LLM review payload JSON such as `variable_plausibility_llm_input.json`
- parsed-table-style JSON that contains `variables`, `columns`, and `values`
- trace wrapper files that store the actual payload under `payload`, `review`, or `response`

It is intended only for human inspection.

## Paper Output Inspection Helper

The paper-output inspection helper is for reading deterministic parse artifacts, paper-context artifacts, and the optional variable-plausibility review output.

Public functions:

- `load_paper_outputs(paper_dir)`
- `summarize_table_processing(paper_dir)`
- `paper_table_inventory_list(papers_dir = file.path("outputs", "papers"))`
- `show_paper_table_inventory(paper_dir)`
- `show_table_processing(paper_dir, table_number = 1L)`
- `show_parse_quality(paper_dir, table_number = 1L)`
- `summarize_table1_continuations(paper_dir)`
- `summarize_table_continuation_column_checks(paper_dir)`
- `show_table_continuation_column_check(paper_dir, check_index = 0L)`
- `show_merged_table1(paper_dir, group_index = 0L, max_rows = 30L)`
- `show_paper_variable_mentions(paper_dir, role_hint = NULL, source_type = NULL, mention_role = NULL)`
- `show_paper_variable_candidates(paper_dir, min_priority = NULL)`
- `show_paper_visuals(paper_dir, visual_kind = NULL)`
- `show_paper_references(paper_dir, reference_kind = NULL, reference_label = NULL, resolution_status = NULL)`
- `show_table_structure(paper_dir, table_number = 1L, max_rows = NULL)`
- `llm_variable_plausibility_df(outputs, table_number = NULL)`
- `show_llm_variable_plausibility(paper_dir, table_number = 1L)`
- `list_llm_variable_plausibility_debug_runs(paper_dir)`
- `summarize_llm_variable_plausibility_monitoring(paper_dir, run_id = NULL)`
- `show_table_context(paper_dir, table_number = 1L, match_type = NULL)`

These helpers use the same per-paper output directory written by `table1-parser parse` and, when run, `table1-parser review-variable-plausibility`.

## Observed TableOne Helper

`R/observed_table_one.R` builds an `ObservedTableOne` object from parser JSON.
The object exposes tableone-style `ContTable`, `CatTable`, and `MetaData`
fields, while preserving lower-case compatibility aliases. Its columns come
from `TableDefinition.column_definition`, which is built from
`ColumnHeaderSchema`.

### Interactive usage

```r
source("R/inspect_paper_outputs.R")

x <- load_paper_outputs("outputs/papers/cobaltpaper")
summarize_table_processing("outputs/papers/cobaltpaper")
show_paper_table_inventory("outputs/papers/cobaltpaper")
show_table_processing("outputs/papers/cobaltpaper", table_number = 1L)
show_parse_quality("outputs/papers/cobaltpaper", table_number = 1L)
summarize_table1_continuations("outputs/papers/cobaltpaper")
summarize_table_continuation_column_checks("outputs/papers/cobaltpaper")
show_table_continuation_column_check("outputs/papers/cobaltpaper", check_index = 0L)
show_merged_table1("outputs/papers/cobaltpaper", group_index = 0L, max_rows = 20L)
show_paper_variable_candidates("outputs/papers/cobaltpaper")
show_paper_variable_mentions("outputs/papers/cobaltpaper", source_type = "text_based", mention_role = "variable")
show_paper_visuals("outputs/papers/cobaltpaper", visual_kind = "figure")
show_paper_references("outputs/papers/cobaltpaper", resolution_status = "resolved")
show_table_structure("outputs/papers/cobaltpaper", table_number = 1L)
llm_variable_plausibility_df(x)
show_llm_variable_plausibility("outputs/papers/cobaltpaper", table_number = 1L)
list_llm_variable_plausibility_debug_runs("outputs/papers/cobaltpaper")
summarize_llm_variable_plausibility_monitoring("outputs/papers/cobaltpaper")
show_table_context("outputs/papers/cobaltpaper", table_number = 1L, match_type = "table_reference")
```

### Corpus-Level Usage

For multiple parsed papers, prefer a named list rather than one large combined data frame. This keeps each paper's table numbers and long titles grouped under the paper they came from.

```r
source("R/inspect_paper_outputs.R")

taxonomy_by_paper <- paper_table_inventory_list("outputs/papers")
names(taxonomy_by_paper)
taxonomy_by_paper[["cobaltpaper"]]
```

Each list element is the same data frame returned by `paper_table_inventory_df(load_paper_outputs(paper_dir))`.

Typical corpus review patterns:

```r
# Count predicted table categories within each paper.
lapply(taxonomy_by_paper, function(x) table(x$table_category, useNA = "ifany"))

# Inspect all tables that were left unknown without materializing the whole corpus.
lapply(taxonomy_by_paper, function(x) x[x$table_category == "unknown", , drop = FALSE])

# Find papers that have at least one Table 1 continuation.
Filter(
  function(x) any(!is.na(x$continuation_of_table_number)),
  taxonomy_by_paper
)
```

What these are for:

- `show_table_structure(...)`
  print one saved table's normalized rows, deterministic columns, and row-variable definitions together; invisibly returns the normalized table, table definition, canonical columns, and canonical variables
- `show_paper_table_inventory(...)`
  print one row per table taxonomy prediction, including table number, category, confidence, continuation parent, and evidence; when present, also prints compact continuation column-check statuses for possible demographic-description integrations
- `paper_table_inventory_list(...)`
  return a named list with one table-taxonomy data frame per paper directory
- `summarize_table1_continuations(...)`
  print one row per detected Table 1 continuation group, including merge/skip decision and source table IDs
- `summarize_table_continuation_column_checks(...)`
  print one row per explicit demographic-description continuation column check, including column-count, schema-derived column-header status, and overall compatibility status
- `show_table_continuation_column_check(...)`
  print one continuation column check in detail, including schema-derived column headers and diagnostics
- `show_parse_quality(...)`
  print deterministic table, row, and column diagnostics, including column-role warnings such as weak p-value columns
- `show_merged_table1(...)`
  print the artifact-only merged Table 1 rows with source table and source row provenance
- `show_paper_visuals(...)`
  print actual in-paper table and figure objects, including captions, reference-check status, text reference IDs, and future figure artifact paths when available
- `show_paper_references(...)`
  print anchored table and figure mentions, including whether each mention resolved to an in-paper visual
- `llm_variable_plausibility_df(...)`
  convert the saved variable-plausibility review into one row per variable
- `show_llm_variable_plausibility(...)`
  print normalized rows, deterministic variables, and the LLM plausibility review together, with reviewed levels nested under each categorical variable
- `list_llm_variable_plausibility_debug_runs(...)`
  list timestamped review-debug runs written when `LLM_DEBUG=true`
- `summarize_llm_variable_plausibility_monitoring(...)`
  print a compact table of per-table review status, elapsed time, payload size, and error fields for one debug run

`load_paper_outputs(...)` now also includes:

- `parsed_tables`
- `table_processing_status`
- `parse_quality_reports`
- `paper_table_inventory`
- `table1_continuation_groups`
- `table_continuation_column_checks`
- `merged_table1_tables`
- `table_variable_plausibility_llm`
- `paper_visual_inventory`
- `paper_references`

## Example Workflow

1. Generate deterministic parser outputs:

```bash
table1-parser parse testpapers/OPEandRA.pdf
```

Use `table_number` in public inspection helpers. The parser may keep extraction-order indices internally for provenance, but the paper's table number is the conceptual selector.

```r
source("R/inspect_paper_outputs.R")
show_table_structure("outputs/papers/OPEandRA", table_number = 1L)
show_parse_quality("outputs/papers/OPEandRA", table_number = 1L)
```

2. Run the optional variable-plausibility review with debug tracing enabled:

```bash
LLM_DEBUG=true table1-parser review-variable-plausibility testpapers/OPEandRA.pdf
```

This creates a directory such as:

```text
outputs/papers/OPEandRA/llm_variable_plausibility_debug/<timestamp>/table_0/
```

3. Inspect the review input payload visually:

```bash
Rscript R/visualize_table_from_json.R outputs/papers/OPEandRA/llm_variable_plausibility_debug/<timestamp>/table_0/variable_plausibility_llm_input.json
```

4. Or inspect the saved review in interactive R:

```r
source("R/inspect_paper_outputs.R")
options(width = 200)

show_llm_variable_plausibility("outputs/papers/OPEandRA", table_number = 1L)
```

## Notes

- Both helpers use base R only.
- They require the `jsonlite` package.
- The variable-plausibility review is an inspection artifact, not a replacement for `table_definitions.json`.
