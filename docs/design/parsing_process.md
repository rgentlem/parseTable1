# Parsing Process Overview

This project parses epidemiology tables in stages. The goal is to keep each stage small, inspectable, and reliable.

## Intended Process

The implemented parser pipeline is:

```text
PDF -> ExtractedTable -> TableBoundaryProposal -> TableRegion -> NormalizedTable -> ColumnHeaderSchema -> ResolvedTableSet -> TableDefinition -> ParsedTable
```

After `TableRegion`, `parse` also writes `body_occupancy.json`,
`leaf_column_candidates.json`, `header_structure_candidates.json`, and
`token_start_evidence.json` as diagnostic side artifacts. They use positioned
table evidence in the canonical orientation-group frame but are not consumed
by normalization or semantic parsing. Token starts are measured only for
tables already carrying candidate refinement signals and do not define
separators. The same raw occupancy calculation is used transiently before
`TableRegion` is finalized only when multiple canonical body intervals remain
plausible.

The early document stages have a strict order:

```text
PDF
-> PaperPositionedDocument
-> page-furniture detection and masking
-> filtered text stream
-> section identification
-> careful bibliography parsing
-> table candidate extraction
```

Page furniture is therefore removed before section, bibliography, or table
identification. Bibliography-owned lines and regions are established before
table extraction and passed into it as exclusion evidence.

The required next structural refinement to the table path is:

```text
ExtractedTable
-> CellTextAnnotations
-> TableBoundaryProposal
-> TableRegion
-> BodyOccupancy
-> LeafColumnCandidate
-> HeaderStructureCandidate
-> NormalizedTable
-> ColumnHeaderSchema
```

`TableBoundaryProposal` records
canonical row bounds, unmerged rule-segment references, stub/value coverage,
font changes, alternative boundary roles, and the selected `TableRegion` edges
for comparison. It is built before `TableRegion`. If credible rule geometry
and a coherent positioned grid are both absent, no row split is manufactured.
Otherwise `TableRegion` uses a single supported body/footer model directly; if
multiple canonical body intervals remain plausible, raw body occupancy chooses
among those models, with the largest interval winning a qualified exact-gap
tie. A gap qualifies only when no ordinary body character occupies it and it
is at least two observed spaces wide in the dominant table font and size.
Selected edges are then attached to the proposal for inspection.
`HeaderStructureCandidate` is now an evidence-preserving first pass over
positioned header spans, individual rule segments, and candidate physical
columns. Each occupancy band defines one preliminary leaf. Intact positioned
header runs attach to the leaf with greatest horizontal overlap, and multiple
runs may stack on the same leaf. Individual partial rules define multicolumn
groups over those leaves. Header words crossing candidate band boundaries are
retained as diagnostics rather than being split into new columns. Marker
occurrences attach only to source-supported leaf or group nodes.
The artifact remains provisional and has no downstream consumer. A later phase
may let `TableRegion` and `ColumnHeaderSchema` validate and consume it instead
of rebuilding an unrelated header model.

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
- `CellTextAnnotations` preserves attached marker geometry without changing
  the raw extracted grid; a planned linked-text view will additionally expose
  marker-free base text while retaining the marker association
- `HeaderStructureCandidate` is the provisional LaTeX-like header structure
  aligned with body occupancy and positioned marker evidence
- `TableBoundaryProposal` is geometry-only evidence for reviewing the current
  caption/start, header/body, and body/footer boundaries
- `TableRegion` is the geometry-derived ownership model for captions,
  column-header bands, body rows, and footer/note bands, including footer
  marker-row evidence from cell-text annotation geometry
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

- consuming `TableRegion` row ownership when available, including the
  distinction between table captions, column-header bands, body rows, and
  footer/note bands
- cleaning cell text
- preserving raw row content
- computing row-level signals such as:
  - whether a row has trailing values
  - whether the first cell looks like a variable label
  - indentation level when it can be inferred

It does not yet decide the final meaning of the table.

For example, a `NormalizedTable` can represent:

- which rows belong to the column-header band
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
- the positioned paper text stream is rendered into markdown-like sections and
  table-focused retrieval bundles
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

- `table1-parser parse path/to/paper.pdf` is the main entry point and currently writes `extracted_tables.json`, `table_boundary_proposals.json`, `table_regions.json`, `body_occupancy.json`, `leaf_column_candidates.json`, `header_structure_candidates.json`, `token_start_evidence.json`, `normalized_tables.json`, `column_header_schemas.json`, `body_element_candidates.json`, `body_row_label_candidates.json`, `resolved_tables.json`, `table_profiles.json`, `paper_table_inventory.json`, `table_definitions.json`, `parsed_cell_values.json`, `parsed_tables.json`, `paper_page_furniture.json`, `paper_markdown.md`, `paper_text_stream.json`, `paper_sections.json`, `paper_footnotes.json`, `paper_bibliography.json`, `paper_style_profile.json`, `paper_visual_inventory.json`, `paper_references.json`, `paper_variable_inventory.json`, and per-table context JSON files
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
