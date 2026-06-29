---
name: single-paper-review-commands
description: Use when the user asks for the command to parse one local Epiconnector testpaper and the interactive R code to inspect extracted, normalized, resolved, header, continuation, footnote, citation-marker, and semantic outputs. Trigger for requests like "code to run and inspect", "start on the first paper", "give me the parse command", "show the R code to view extraction", "how many tables did we get", "check headers/continuations", or "review this paper from the checklist".
---

# Single Paper Review Commands

## Workflow

1. Resolve the paper path.
   - If the user says "first", "next", or gives a checklist ID, use
     `docs/implementation/real_paper_testing_guide.md`.
   - Paths in that guide are relative to
     `/Users/robert/Projects/Epiconnector/testpapers`.
   - Verify the referenced PDF exists before giving the command.

2. Give one paste-ready Python parse command.
   - Assume the user's shell is already at the repo root.
   - Do not include `cd` commands.
   - Prefer `python3 -m table1_parser.cli parse`.
   - Use a review-specific output root under ignored `outputs/`, such as
     `outputs/corpus_review_C1_1`.
   - If the request follows a just-run fix or a named paper discussion, use a
     descriptive output root such as `outputs/helicobacter_review_YYYYMMDD`.
   - State the resulting paper output directory, which is always:
     `<outdir>/papers/<pdf-stem>`.

3. Give interactive R code.
   - Assume R is started from the repo root.
   - Do not include shell `cd` commands.
   - Source the existing inspection helpers:
     `R/inspect_paper_outputs.R` and `R/visualize_table_from_json.R`.
   - Use `paper_dir <- "<outdir>/papers/<pdf-stem>"`.
   - Load outputs with `x <- load_paper_outputs(paper_dir)`.
   - Start with extraction and status views before semantic views.
   - Use `table_index = 0L` for first-pass debugging of failed or oddly
     numbered papers. Use `table_number = 1L` only when the table number is
     known and stable.
   - Include table-count/overview code before single-table inspection.
   - Include `show_column_header_trees(paper_dir)` when the user is checking
     whether continuation-page headers match.
   - Include annotation and footnote-link data-frame code when superscripts,
     citations, or bibliography markers are part of the discussion.
   - Treat `[No variables]` as a semantic-parser result, not as a reason to
     repeat semantic variable views. Switch to source-grid, header-tree,
     resolved-continuation, and annotation inspection.
   - If `length(x$table_definitions)` is smaller than
     `length(x$extracted_tables)` or `length(x$normalized_tables)`, do not call
     semantic helpers such as `show_table_structure()` for source-fragment
     indexes that do not have a table definition.
   - Present R commands as several numbered, self-contained code blocks for
     cut-and-paste use. Do not put the whole R review in one large block.
     Each block should do one inspection task and assume prior blocks have
     already been run.
   - Do not rediscover helper names unless a call fails. Standard helpers live
     in `R/inspect_paper_outputs.R` and `R/visualize_table_from_json.R`.

## Standard R Blocks

Use this compact table overview after loading `x`:

```r
table_overview <- data.frame(
  table_index = seq_along(x$extracted_tables) - 1L,
  table_id = vapply(x$extracted_tables, function(t) as.character(t$table_id %||% ""), character(1)),
  page_num = vapply(x$extracted_tables, function(t) as.integer(t$page_num %||% NA_integer_), integer(1)),
  n_rows = vapply(x$extracted_tables, function(t) as.integer(t$n_rows %||% NA_integer_), integer(1)),
  n_cols = vapply(x$extracted_tables, function(t) as.integer(t$n_cols %||% NA_integer_), integer(1)),
  title = vapply(x$extracted_tables, function(t) as.character(t$title %||% ""), character(1)),
  stringsAsFactors = FALSE
)
table_overview
```

Use this resolved-continuation block when checking whether pages/fragments were
integrated:

```r
resolved <- read_json_file(file.path(paper_dir, "resolved_tables.json"))
length(resolved$resolved_tables %||% list())
lapply(resolved$resolved_tables %||% list(), function(rt) rt$source_table_ids)
```

Use this semantic definition block before calling semantic table helpers:

```r
semantic_overview <- data.frame(
  table_index = seq_along(x$table_definitions) - 1L,
  table_id = vapply(x$table_definitions, function(t) as.character(t$table_id %||% ""), character(1)),
  variable_count = vapply(x$table_definitions, function(t) length(t$variables %||% list()), integer(1)),
  stringsAsFactors = FALSE
)
semantic_overview
```

Use this citation-marker block when row-label superscripts matter:

```r
ann <- cell_text_annotations_df(x)
ann[ann$col_idx == 0L, c("table_index", "page_num", "row_idx", "text", "annotation_type", "attached_to_text")]

anchors <- footnote_anchors_df(x)
links <- footnote_links_df(x)
citation_anchors <- anchors[anchors$source_role == "row_label" & anchors$glyph_kind == "number", ]
citation_links <- links[match(citation_anchors$anchor_id, links$anchor_id), ]
data.frame(
  table_index = citation_anchors$table_index,
  page_num = citation_anchors$page_num,
  row_idx = citation_anchors$row_idx,
  glyph = citation_anchors$glyph_raw,
  attached_to_text = citation_anchors$attached_to_text,
  link_status = citation_links$link_status,
  link_basis = citation_links$link_basis,
  notes = citation_links$notes,
  stringsAsFactors = FALSE
)
```

## Response Shape

Keep the response short and directly usable:

````markdown
Python parse command:

```bash
python3 -m table1_parser.cli parse "<absolute-pdf-path>" --outdir "<review-output-root>"
```

Expected output directory:
`<review-output-root>/papers/<pdf-stem>`

Interactive R review:

1. Load helpers and outputs:

```r
source("R/inspect_paper_outputs.R")
source("R/visualize_table_from_json.R")

paper_dir <- "<review-output-root>/papers/<pdf-stem>"
x <- load_paper_outputs(paper_dir)
```

2. Count extracted tables:

```r
table_overview <- data.frame(
  table_index = seq_along(x$extracted_tables) - 1L,
  table_id = vapply(x$extracted_tables, function(t) as.character(t$table_id %||% ""), character(1)),
  page_num = vapply(x$extracted_tables, function(t) as.integer(t$page_num %||% NA_integer_), integer(1)),
  n_rows = vapply(x$extracted_tables, function(t) as.integer(t$n_rows %||% NA_integer_), integer(1)),
  n_cols = vapply(x$extracted_tables, function(t) as.integer(t$n_cols %||% NA_integer_), integer(1)),
  title = vapply(x$extracted_tables, function(t) as.character(t$title %||% ""), character(1)),
  stringsAsFactors = FALSE
)
table_overview
```

3. Check resolved continuation provenance:

```r
resolved <- read_json_file(file.path(paper_dir, "resolved_tables.json"))
length(resolved$resolved_tables %||% list())
lapply(resolved$resolved_tables %||% list(), function(rt) rt$source_table_ids)
```

4. Open extracted and normalized grids:

```r
visualize_table_from_json(file.path(paper_dir, "extracted_tables.json"))
visualize_table_from_json(file.path(paper_dir, "normalized_tables.json"))
```

5. Inspect processing and source-fragment headers:

```r
summarize_table_processing(paper_dir)
show_paper_table_inventory(paper_dir)
show_column_header_trees(paper_dir)
```

6. Check semantic definitions before using semantic table views:

```r
semantic_overview <- data.frame(
  table_index = seq_along(x$table_definitions) - 1L,
  table_id = vapply(x$table_definitions, function(t) as.character(t$table_id %||% ""), character(1)),
  variable_count = vapply(x$table_definitions, function(t) length(t$variables %||% list()), integer(1)),
  stringsAsFactors = FALSE
)
semantic_overview
```

7. Inspect the first semantic table only if variables exist:

```r
if (nrow(semantic_overview) > 0L && semantic_overview$variable_count[[1]] > 0L) {
  show_table_processing(paper_dir, table_index = 0L)
  show_parse_quality(paper_dir, table_index = 0L)
  show_table_structure(
    paper_dir,
    table_index = 0L,
    max_rows = 40L,
    include_raw_header_rows = TRUE
  )
} else {
  message("No semantic variables; inspect source grids, header trees, and annotations instead.")
}
```

8. Inspect row-label superscripts and citation-like markers:

```r
ann <- cell_text_annotations_df(x)
ann[ann$col_idx == 0L, c("table_index", "page_num", "row_idx", "text", "annotation_type", "attached_to_text")]

anchors <- footnote_anchors_df(x)
links <- footnote_links_df(x)
citation_anchors <- anchors[anchors$source_role == "row_label" & anchors$glyph_kind == "number", ]
citation_links <- links[match(citation_anchors$anchor_id, links$anchor_id), ]
data.frame(
  table_index = citation_anchors$table_index,
  page_num = citation_anchors$page_num,
  row_idx = citation_anchors$row_idx,
  glyph = citation_anchors$glyph_raw,
  attached_to_text = citation_anchors$attached_to_text,
  link_status = citation_links$link_status,
  link_basis = citation_links$link_basis,
  notes = citation_links$notes,
  stringsAsFactors = FALSE
)
```
````

## Review Notes

When the user is starting a checklist item, include the checklist ID and failure
reason from `docs/implementation/real_paper_testing_guide.md` if available.
Do not diagnose the paper before it is parsed and inspected in the current
review output.
