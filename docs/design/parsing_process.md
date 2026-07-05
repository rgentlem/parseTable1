# Parsing Process Overview

This project parses epidemiology tables in stages. The goal is to keep each stage small, inspectable, and reliable.

## Intended Process

The implemented parser pipeline is:

```text
PDF -> ExtractedTable -> NormalizedTable -> ColumnHeaderSchema -> ResolvedTableSet -> TableDefinition -> ParsedTable
```

For continued tables, the resolved stage can integrate compatible source
fragments before semantic parsing:

```text
NormalizedTable + ColumnHeaderSchema -> ResolvedTableSet -> TableProfile/TableDefinition -> ParsedTable
```

`ResolvedTableSet` is the canonical working list for singleton tables and
accepted integrated continuations. It is written by `table1-parser parse` as
`resolved_tables.json`. It is not a replacement for `normalized_tables.json`,
which remains the complete normalized source record.

In plain terms:

- `ExtractedTable` is what the PDF extraction layer found
- `NormalizedTable` is the cleaned and organized version used for interpretation
- `ColumnHeaderSchema` is the explicit leaf-column and spanning-header model
- `ResolvedTableSet` is the table list consumed by semantic parsing
- `TableDefinition` is the value-free semantic structure used for database matching and later parsing
- `ParsedTable` is the final structured result with variables, levels, columns, and values

For mixed-table papers, the planned future pipeline adds a routing stage:

```text
PDF -> ExtractedTable -> NormalizedTable -> TableProfile -> family-specific definition -> family-specific parsed output
```

See `docs/design/multitable_architecture_spec.md`.

For CLI use, `table1-parser parse` is intended to be the main user command. It should run the pipeline once and write every currently available stage artifact for the paper.

## What `NormalizedTable` Means

A `NormalizedTable` is the intermediate representation between raw extraction and final parsing.

It keeps the table structure, but makes it easier to interpret by:

- separating header rows from body rows
- cleaning cell text
- preserving raw row content
- computing row-level signals such as:
  - whether a row has trailing values
  - whether the first cell looks like a variable label
  - indentation level when it can be inferred

It does not yet decide the final meaning of the table.

For example, a `NormalizedTable` can represent:

- which rows are likely headers
- what the cleaned rows look like
- which rows belong to the body

But it does not yet fully decide:

- which row starts a variable
- which rows are levels under that variable
- what each value means numerically

## What Happens After Normalization

Later stages use the `NormalizedTable` to make progressively stronger interpretations:

- deterministic column-schema assembly records leaf columns, spanning header groups, and raw evidence
- deterministic continuation resolution builds the `ResolvedTableSet`
- deterministic routing classifies the resolved table family
- deterministic heuristics build a `TableDefinition` from resolved tables using
  the column schema
- paper markdown is chunked into sections and table-focused retrieval bundles
- a paper-level variable inventory collects candidate variables from text, captions, and tables
- optional LLM interpretation can later refine ambiguous structure
- validation checks that the interpretation is consistent with the real table
- final assembly produces a `ParsedTable`

## Why This Separation Matters

This separation keeps the parser safer and easier to debug.

- extraction errors can be inspected separately
- normalization can preserve the original table while cleaning it
- heuristics can stay deterministic
- LLM use can be limited to ambiguity instead of raw extraction
- final parsed output can be validated before it is accepted

## For Users

If you are looking at parser outputs:

- `table1-parser parse path/to/paper.pdf` is the main entry point and currently writes `extracted_tables.json`, `normalized_tables.json`, `column_header_schemas.json`, `resolved_tables.json`, `table_profiles.json`, `paper_table_inventory.json`, `table_definitions.json`, `parsed_cell_values.json`, `parsed_tables.json`, `paper_page_furniture.json`, `paper_markdown.md`, `paper_text_stream.json`, `paper_sections.json`, `paper_footnotes.json`, `paper_bibliography.json`, `paper_style_profile.json`, `paper_visual_inventory.json`, `paper_references.json`, `paper_variable_inventory.json`, and per-table context JSON files
- `extract` and `normalize` remain useful for inspecting a single stage in isolation

- raw extraction output answers: "What table did the PDF extractor recover?"
- normalized output answers: "What cleaned table structure will the parser reason over?"
- column-header-schema output answers: "Which leaf columns and spanning header groups did the parser infer, what raw evidence supports them, and did it need to recover headers when normalized header rows were missing or title-like?"
- table-profile output answers: "What table family did the deterministic router infer, and should semantic LLM run?"
- paper-table-inventory output answers: "What broad table category did the deterministic taxonomy assign to each paper table number?"
- table-definition output answers: "What row variables, levels, and columns did the deterministic parser infer?"
- paper-context output answers: "What document sections, visual references, and passages are relevant to this table?"
- paper-style output answers: "What marker, bibliography, caption, and visual-reference conventions does this paper appear to use?"
- paper-variable-inventory output answers: "What candidate variables recur across the paper text and tables?"
- parsed output answers: "What variables, levels, columns, and values did the system finally infer?"
