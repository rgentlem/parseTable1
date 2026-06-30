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
- `cell_text_annotations.json`
- `normalized_tables.json`
- `column_header_schemas.json`
- `resolved_tables.json`
- `table1_continuation_groups.json`
- `table_continuation_column_checks.json`
- `merged_table1_tables.json`
- `table_profiles.json`
- `paper_table_inventory.json`
- `table_definitions.json`
- `continued_variable_integrations.json`
- `parsed_cell_values.json`
- `parsed_tables.json`
- `table_processing_status.json`
- `parse_quality_reports.json`
- `paper_footnotes.json`
- `paper_page_furniture.json`
- `paper_markdown.md`
- `paper_sections.json`
- `paper_visual_inventory.json`
- `paper_references.json`
- `paper_variable_inventory.json`
- `table_contexts/table_<n>_context.json`
- `table_variable_plausibility_llm.json` when `review-variable-plausibility` is run
- `llm_variable_plausibility_debug/...` when variable-plausibility debug tracing is enabled

Some of these are per-table artifacts. Others are paper-level context artifacts.

`cell_text_annotations.json` records superscript, subscript, and small marker
geometry by table cell when compatible PyMuPDF character geometry and extracted
cell bboxes are available. It does not change the raw extracted grid.

`paper_page_furniture.json` records repeated page text observations, recurrence
clusters, and generic ignored regions for footnote suppression. It is written
even when no repeated page furniture is found.

`paper_footnotes.json` records detected footnote anchors, candidate definitions,
and glyph-key links as a paper-level review artifact. It is written even when no
anchors or definitions are found.
Definition candidates are fed by PyMuPDF page text lines with bbox and page-height
provenance so table-local notes and page-bottom notes can be classified
deterministically before glyph-key linking. Repeated page-furniture regions are
used first to suppress overlapping table-cell anchors and definition candidate
lines.

## Why There Are Multiple Versions Of A Table

The parser deliberately keeps several versions of the same table because each stage answers a different question.

- `ExtractedTable` answers: what did the PDF extractor recover?
- `NormalizedTable` answers: what cleaned table structure should downstream logic reason over?
- `ColumnHeaderSchema` answers: how do normalized columns, leaf headers, and higher spanning header groups relate?
- `ResolvedTableSet` answers: which normalized fragments form the semantic working table list?
- `TableProfile` answers: what kind of table does this appear to be?
- `PaperTableInventory` answers: what broad paper-level category was assigned to each table number?
- `TableDefinition` answers: what do the rows and columns mean, before we parse values?
- `ParsedTable` answers: what final variables, levels, columns, and values did we infer?

If the system skipped these stages and wrote only one final output, it would be much harder to debug extraction errors, normalization repairs, header mistakes, row-type mistakes, and value-parsing mistakes.

## High-Level Flow

The current implemented flow for `parse` is:

```text
PDF
  -> extracted tables
  -> normalized tables
  -> column header schemas
  -> resolved tables
  -> parsed source-cell values
  -> table profiles over resolved tables
  -> table definitions over resolved tables
  -> parsed tables
  -> table processing statuses over resolved tables
  -> parse quality reports
  -> Table 1 continuation inspection artifacts over source fragments
  -> paper page furniture
  -> paper footnotes

PDF
  -> paper markdown
  -> paper sections
  -> paper variable inventory
  -> per-table context bundles

TableDefinition.variables
  -> optional standalone variable-plausibility LLM review
```

Two points matter here.

First, the table pipeline and the paper-context pipeline are related but separate.

Second, the optional LLM path is now separate from `parse`. `parse` stays deterministic, while `review-variable-plausibility` writes an additional QA-style artifact.

The parse command also writes a table-level processing-status artifact so rescue attempts and terminal failures are explicit.

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

For some explicit tables, the backend cell grid is too coarse even though the page still contains enough geometry to do better. When a table shows strong grouped-header signals, such as repeated `Model 1`, `Model 2`, `Model 3` blocks plus wide horizontal boundaries, extraction can now refine the explicit backend grid using word positions inside the table bounding box. If the backend table box starts just below a true full-width top rule, extraction may expand the word clip up to that rule so the grouped header row is not lost before column-header schema construction.

For collapsed explicit grids, word-position refinement treats stable value columns as repeated value-like numeric anchors. This prevents label text such as `Q1-Q3`, `kg/m2`, or biomarker names containing digits from creating fake columns. Rows with a trailing statistic and only nonnumeric fragments to its left can also be repaired from right to left so long first-column labels remain a single row label.

That refinement is no longer limited to upright tables. For rotated explicit tables, extraction can normalize the clipped word and rule coordinates into a table-local upright frame, rebuild the row/column grid there, and then write the improved grid into `ExtractedTable` while preserving the original rotation metadata separately.

Some PDFs draw visually landscape tables sideways on portrait pages without setting
page-level rotation. For those pages, extraction may detect dominant vertical table
text, transform the page geometry into a table-readable coordinate frame, run
caption and layout detection in that transformed frame, and write a normal
`ExtractedTable` with orientation metadata such as `orientation_strategy`,
`sideways_candidate`, and `caption_detection_space`. This happens before
normalization so downstream stages still consume ordinary table objects.

The extractor still scores candidates, but the score is now diagnostic rather than a hard keep-drop gate for explicit extracted tables. The current rule is:

- deduplicate exact candidate collisions
- preserve explicit extracted table candidates in stable page/index order
- record confidence and caption signals in metadata instead of silently dropping low-scoring tables
- allow explicit-table grid refinement when rule and word geometry clearly support a better internal column structure
- suppress backend table-like boxes once the document has entered a `References` or bibliography section, because reference lists are document metadata rather than epidemiology tables; any future reference parser should consume them as atomic citation records, not tokenized table cells
- require page-text-layout fallback candidates to have a real table-number/caption signal unless their reconstructed grid has strong table geometry: at least three columns, at least four rows, a header-like top row, stable multi-column alignment, and multiple rows with data-like trailing cells
- when a text-position fallback caption wraps onto the next line, keep a short caption continuation line with the table label, and also keep a lowercase sentence fragment ending in punctuation with the caption instead of treating it as the first table row
- when text-position fallback builds column anchors, prefer an early stable table prefix if using the full page would collapse separated value columns because of later wrapped rows, page-margin text, or other noisy numeric positions
- trim trailing footer or watermark rows from explicit and text-position candidates when they appear after the final numeric value-matrix row and structural clues show they are outside the table, such as multiple blank rows, a large vertical gap, or text spread across many columns without table-like values; the trim is recorded in `metadata.trailing_non_table_rows`

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

For rotated refinements, the recovered `table_cells`, `row_bounds`, and `horizontal_rules` may be expressed in a table-local normalized coordinate frame rather than the original page frame. That is intentional: later stages use those values as structural boundaries. Extraction records `geometry_transform_source_bbox`, `geometry_transform_transposed`, and `geometry_transform_applied` so later annotation code can transform page characters into the same coordinate frame when needed.

For explicit tables, extraction may also record the visible first-word x-position for each first-column row label. This exists because backend cell boxes often describe the full column boundary, while the actual text inside that cell may be indented. Normalization uses that compact word-position metadata for indentation inference while preserving the original cell boxes as grid geometry.

For text-position fallback and sideways-transformed candidates, extraction may preserve recovered cell text bounding boxes directly in `table_cells`. These boxes are in the same coordinate frame as the recovered grid and allow normalization to infer row-label indentation even when the backend did not emit explicit table cells.

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

It can also handle a rarer structural variant where the leftmost column is not empty but is only a sparse stub for section labels such as broad row groups, while the next column contains the actual row labels and the remaining columns contain values. In that case normalization may drop the sparse stub column, suppress stub-only rows, shift the real label column left, and merge the stub plus label text for rows where both cells together form one label.

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
When the first dense numeric value row is a stronger structural signal than
the initial detector, normalization can use it as the body boundary and treat
the non-empty rows above it as the header band. A sparse leading caption or
note tail above that band remains preserved in `metadata.cleaned_rows`, but it
is excluded from both `header_rows` and `body_rows`.

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

#### 3.8 Repair Sparse Stub Label Columns

Some extracted grids contain a sparse first column whose only purpose is to hold section-like row stubs, while the actual variable names are in the next column. These rows can otherwise cause the downstream parser to see blank row labels for most data rows.

Normalization can repair this only when the evidence is strong:

- the first column is sparse and does not contain value-like cells
- at least one first-column-only stub row is present
- the second column is dense and label-like
- many rows have a blank first column, a label-like second column, and value-like cells to the right
- the right-side columns look like the data region

When this fires, normalization:

- suppresses pure stub rows from `body_rows`
- shifts the second column into the row-label position
- merges first-column and second-column text for rows where both pieces form one label
- records the repair evidence in `metadata.column_repairs.sparse_stub_label_column`

This is intentionally a structural repair. It should not depend on exact words such as `Outcomes` or `Covariates`.

#### 3.9 Repair Split Row-Label Field Columns

Some PDF table extractors split the single logical row-label field across two adjacent columns. Typical examples are categorical levels that appear in the second extracted column while parent variables appear in the first, or labels such as `Married/` plus `Living with partner` split across the first two columns.

Normalization can merge this two-column row-label field when strong row-pattern evidence shows that:

- the second column repeatedly contains row-label fragments
- data-like values begin to the right of the first two columns
- shifted rows or many merged first-plus-second label fragments are present

When this fires, normalization:

- shifts second-column label fragments into the first column
- merges first-column and second-column fragments when both contain label text
- records the repair evidence in `metadata.column_repairs.split_row_label_field_columns`

This repair preserves raw extracted text in `ExtractedTable`; it only changes the parser-facing normalized grid.

#### 3.10 Repair Embedded Label Tails And Vertical Continuations

Some extracted grids keep the visual value columns intact but split row labels awkwardly.

Two recurring cases are:

- a label tail is embedded in the first value cell with a count, for example `<100%` plus `FPL 625`
- a row label wraps onto the next extracted row while the values stay on the first row, for example `All (NHANES` followed by `2009 to 2012)`
- a row label starts on a label-only row and finishes on the following valued row, for example `SI (31025 min21` followed by `per pmol/L)`

Normalization can repair these only when the row context is strong:

- embedded label-tail repair requires a label-like first cell, a label-tail-plus-count pattern in the first value cell, and additional value-like cells to the right
- vertical continuation repair requires a label-only row after a valued row plus punctuation, footnote, lowercase/digit-start, or phrase-continuation cues
- leading label-fragment repair requires the label-only row itself to show unfinished-label evidence, such as an unmatched parenthesis or trailing phrase connector, before it can merge into the following valued row

When these fire, normalization:

- moves the embedded label tail back into the row-label cell while leaving the count in the value column
- appends vertical continuation text to the preceding valued row's label, or prepends a leading label fragment to the following valued row's label
- suppresses consumed continuation rows from `body_rows`
- records repair evidence in `metadata.column_repairs.embedded_label_count_cells` and `metadata.column_repairs.vertical_label_continuations`

These repairs improve row-label integrity before row signatures and variable grouping are built. They do not assign a table category by themselves.

#### 3.11 Expand Extra-Wide Stacked Value Columns

Some upright, visually wide data tables can be collapsed by extraction into a row-label cell plus one broad value-region cell. The visual table is still multi-column; the broad extracted cell may preserve those visual columns as a stable newline-delimited stack.

Normalization can expand that collapsed value-region cell only when the evidence is strong:

- several rows share the same stack width
- the stacked body tokens are mostly numeric value-like tokens
- top header stacks can be aligned to the same width or cleanly repeated over paired leaf columns

When this fires, normalization:

- keeps the first extracted column as the row-label field
- splits the broad value-region cell into separate parser-facing columns
- repeats coarser shared header labels over their leaf value/statistic columns
- chunks dense multi-line header stacks into one label per expanded value column
- records the recovered header band and first value row as boundary evidence
- records the repair evidence in `metadata.column_repairs.extra_wide_value_column`

This treats the visual table as a normal multi-column table while preserving the original collapsed cell text in `ExtractedTable`.

#### 3.12 Select Header Bands From Structural Boundaries

Some extracted table fragments begin with a stray caption tail or note row,
followed by a compact multi-row header and then a value region. Normalization
first tries validated full-width horizontal separator rules. If no separator
candidate is available, it can use the first row-label-plus-value-region anchor
as the header/body boundary.

When this fires, normalization:

- promotes the non-empty rows above the selected structural boundary into `header_rows`
- trims a sparse leading note/caption tail out of the promoted header band
- starts `body_rows` at the first structural body row
- records the boundary source in `metadata.header_detection`

This is a structural boundary decision, not a semantic interpretation of the
header words. Tables without usable rules or a clear value-region anchor still
fall back to content scoring.

#### 3.13 Drop Columns Emptied By Repair

If a split-value repair empties a helper column across the table, normalization can drop that now-empty column and rerun header detection on the repaired grid.

This keeps the normalized grid closer to the logical table structure that the later parser actually wants.

#### 3.14 Decide Whether Indentation Is Informative

For some papers, first-column indentation clearly helps distinguish parent rows from level rows.

For other papers, small horizontal shifts are just extraction noise.

Normalization records whether indentation appears informative enough to matter later.

### What `NormalizedTable` Contains

At the end of normalization, each table has:

- `header_rows`
- `body_rows`
- `row_views`
- `metadata.cleaned_rows`
- `metadata.source_col_indices`
- edge-column repair information
- header-detection diagnostics
- indentation diagnostics
- text-cleaning provenance

### Why `NormalizedTable` Exists

This artifact is where the table becomes parser-friendly without yet becoming fully semantic.

That separation matters because many downstream mistakes are really normalization mistakes, not semantic mistakes.

`source_col_indices` preserves the original extracted column behind each
surviving normalized column when that identity is still computable. Later
column-schema evidence should use this map before trying to reconstruct column
identity from repair summaries.

## Step 4: Build `ColumnHeaderSchema`

After normalization, the parser builds a parser-native column-header schema for
each normalized table and writes `column_header_schemas.json`.

This artifact keeps column structure explicit before `TableDefinition` assigns
semantic roles. It records:

- one leaf record per normalized column, including the row-label column
- the header row closest to the body as the source of leaf labels
- higher header rows as spanning groups over leaves
- group-to-leaf relationships as explicit records
- raw extracted header-cell text and coordinates when available
- diagnostics for blank leaf labels, skipped title-like header rows, and
  missing coordinate evidence

If the normalized header rows are absent or only contain title/caption text,
this stage can infer a header stack from rows above the first strongly numeric
body row. That fallback is recorded in schema diagnostics and does not rewrite
`NormalizedTable`.

Within the leaf-header band, the schema builder may use cell coordinates to
repair a short leading fragment that was extracted into the next column even
though it lies left of the adjacent leaf boundary. The repair is structural and
keeps the moved-from cell as evidence; it should not depend on recognizing
paper-specific words.

The schema builder also uses rule and coordinate evidence inside the header
band. A horizontal rule between header rows can mark the rows below it as the
wrapped leaf-header stack while keeping higher rows as spanning groups. The
row-label column is allowed to sit outside value-region group headers, since
those group headers often describe only subsets of the data columns. If a
value-region group header is extracted as adjacent text fragments, a large
horizontal gap can split those fragments into separate groups.

For dense multirow headers, sparse rows after an internal rule are not
automatically treated as leaf labels. The schema builder trims sparse group
rows from the inferred leaf stack, keeps them available as higher header
groups, and can expand repeated single-cell group labels leftward when the
physical extraction placed a centered spanning header into the right-hand leaf
of a two-column span. This keeps headers such as survey-cycle groups,
prevalence-estimate groups, and statistic/unit leaves separate.

`TableDefinition.column_definition` now carries that structure forward. Each
defined column stores a leaf `column_label`, a top-to-bottom `header_path`, the
supporting header group IDs and labels, and table-level `header_spans` that can
render multirow column headers without reconstructing them from flattened text.
The semantic `columns` list remains value/statistic-column oriented, while
`header_spans` also includes the row-label leaf so displays keep the full
header axis, including labels such as `Characteristic` or `Variable`.

The schema is deliberately not a tableone object and does not store summary
values. It supplies the column axis that later semantic and stored-summary
objects can consume.

Why this exists:

- multi-row headers should be recoverable as structured leaf columns and spanning groups
- `TableDefinition` should classify column semantics from a shared column model
  rather than rebuilding header structure locally
- later tableone-style rendering needs a stored summary object before printing,
  and that object will need a stable column axis

## Step 5: Resolve Continuation Fragments

After normalization and column-schema construction, the parser builds
`resolved_tables.json`.

This artifact is the semantic working table set. It starts from every
normalized source table and promotes either:

- singleton resolved tables for ordinary source tables
- integrated resolved tables when a continuation candidate has clear identity
  evidence, an unambiguous parent fragment, and matching `ColumnHeaderSchema`
  columns
- rejected continuation singletons when a candidate fails closed

The resolver preserves `normalized_tables.json` unchanged as the complete
source record. Every retained resolved row maps back to source table ID, source
table index, source row index, source role, and page evidence when available.

`TableProfile`, `TableDefinition`, and `ParsedTable` consume this resolved
working list. For an integrated continuation, the parent headers are carried
forward only after the schema compatibility decision is accepted, continuation
body rows are appended in source order, and dropped continuation header or
non-body rows are recorded in the integration boundary.

The parser still writes the older continuation inspection artifacts for review.
Those artifacts remain useful for checking source-fragment continuation
evidence, but they are no longer the canonical semantic table list.

From this point forward, the semantic table count is the length of
`resolved_tables[*]`, not the length of `normalized_tables.json`. That means
`table_profiles.json`, `table_definitions.json`, `parsed_tables.json`,
`paper_table_inventory.json`, and `table_processing_status.json` use resolved
table IDs. Source-fragment artifacts still use original normalized table IDs
and are joined back through `resolved_tables.json` provenance when needed.

When parse outputs are written, the parser also checks whether explicit or
narrow inferred source-fragment continuations have compatible columns.

This inspection path does not try random integrations. A
continuation fragment must already have clear continuation evidence for a
specific table number, or be an uncaptained, unnumbered adjacent-page fragment
after a likely descriptive table, before the parser compares it to the closest
prior fragment for that table number.

The parser writes:

- `table_continuation_column_checks.json`
  records normalized column-count agreement, schema-derived column-header agreement,
  and an overall compatible/incompatible/no-parent status

The same parse still checks whether the paper appears to have a Table 1 continuation.

This stage is intentionally narrow. It only considers Table 1, and it only accepts a merge when the continuation evidence is explicit or strongly inferred and the schema-derived column headers are compatible.

Current examples of continuation evidence include:

- extractor metadata indicating a continuation of table number 1
- title or caption text such as `Table 1 (continued)`
- a continuation marker in the first normalized rows
- an uncaptained, unnumbered table-like fragment on the next page after Table 1

When the evidence is compatible, the parser writes two inspection artifacts:

- `table1_continuation_groups.json`
  records the source table IDs, table indices, column-header comparison, merge decision, and diagnostics
- `merged_table1_tables.json`
  records an artifact-only `NormalizedTable` that appends continuation body rows to the base Table 1 rows

The merged artifact preserves source-row provenance in `metadata.table1_continuation_merge`.
That lets a human inspect a single logical Table 1 view while still tracing every merged row back to the original normalized table and row index.

For compatible continuation groups, the parser may also write
`continued_variable_integrations.json`. This older artifact is retained as a
review view over source fragments while `resolved_tables.json` is the semantic
input to table definitions and parsed values. It is built from source-fragment
table definitions, not from the resolved semantic definitions, so it remains an
auditable old-view artifact rather than a second semantic parse path.

Continuation header comparison is schema-only: the continuation artifacts use
`ColumnHeaderSchema` through the parser's column-header tooling and do not
reconstruct column meaning from normalized header rows. If a usable schema is
missing, compatibility fails with a structured diagnostic instead of falling
back to a cruder comparison. Coordinate profiles remain separate diagnostics
and do not override matching column headers with matching normalized column
counts.

## Step 6: Provisional Table Routing With `TableProfile`

Once the resolved working table list exists, the parser builds a `TableProfile`
for each resolved table.

This is an early routing stage. It asks questions like:

- does this table look like one of the parser families currently implemented?
- should the current Table 1-style semantic parser run?

The current repository is centered on Table 1 style descriptive tables, but mixed-table papers exist. `TableProfile` is the stage that prevents the system from pretending every table belongs to the same family.

`TableProfile` is narrower than the paper table inventory because it is built earlier and currently represents parser-route support, not the complete table taxonomy. A wide numeric data matrix can still have `table_family = "unknown"` if it is neither a descriptive-characteristics table nor an estimate-results table. The broader `paper_table_inventory.json` stage can still categorize that same object as `data_presentation` using shape, numeric density, threshold/statistic headers, and normalization repair evidence.

The intended long-term direction is that the broad table category drives route selection once that category is available. In other words, `table_family` should be treated as a provisional route signal and should remain consistent with `table_category`, not as an unrelated second concept.

Why this stage exists:

- it keeps mixed-table handling explicit
- it lets the deterministic parser decide whether an LLM step is even relevant

## Step 7: Build `TableDefinition`

`TableDefinition` is the value-free semantic interpretation of each resolved
table.

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
- one-row binary indicator rows, where a single `n (%)` row reports the counted state and the complementary state is implicit
- count-percent categorical level continuations, where value-pattern continuity can preserve levels under an `n (%)` parent even when indentation is unavailable or unreliable
- variable labels
- normalized variable names
- row spans
- units hints
- summary-style hints

For columns:

- label column vs data columns
- overall vs group vs p-value vs trend vs SMD style columns
- grouped-column structure when it can be inferred

Column structure now comes from `ColumnHeaderSchema`. That means
`TableDefinition` can focus on semantic roles and grouping labels instead of
owning the mechanics of leaf-header and spanning-group recovery.

One implemented heuristic detail is worth calling out explicitly:

- a row with empty group columns but populated test or statistic columns can still be a variable header
- if that row is followed by plausible child levels such as `Yes` and `No`, it should be treated as a new variable, not as another level under the previous variable
- continuous-summary rows can be recognized when a PDF extracts the plus/minus glyph as a spaced `6`, such as `25.9 6 3.6`; the raw cell text remains unchanged

This matters for printed Table 1 layouts where the parent row carries only the p-value or trend-test result and the level rows carry the group counts.

### Why `TableDefinition` Exists

This is one of the most important design choices in the project.

The parser does not jump directly from a normalized grid to parsed numeric values because it is useful to have a stable semantic layer that describes what the table means before any value parsing happens.

This makes it easier to:

- inspect row and column meaning independently of value parsing
- support downstream matching and R-side table objects
- compare deterministic semantics with future LLM semantics

## Step 8: Parse Source-Cell Value Components

After `ColumnHeaderSchema` exists, the parser builds `parsed_cell_values.json`
from source normalized table body cells in schema-derived value columns.

This is deliberately earlier than the final semantic value join. Each record is
keyed by:

- source table index
- source table ID
- row index
- column index

The record stores the original printed cell string plus typed components such as
`count`, `percent`, `estimate`, `se`, `mean`, `sd`, `median`, `q1`, `q3`,
`p_value`, `missing`, `text`, or `unknown`.

It does not store variable names, level labels, column names, or header paths.
Those semantics belong to `TableDefinition` and `ColumnHeaderSchema`.

This early component layer is useful for two reasons:

- continuation handling remaps already-parsed source values by row and column
  provenance instead of reparsing display strings after fragments are joined
- paper-review diagnostics can later assess per-column value-pattern anomalies,
  possible typos, and suspicious inconsistencies without depending on a fully
  successful semantic parse

Ambiguous shapes such as `52.3 (14.1)` remain conservative until semantic
context can distinguish `mean (SD)` from `estimate (SE)`.

## Step 9: Build `ParsedTable`

`ParsedTable` is the final deterministic structured table output.

This stage combines:

- the resolved normalized table grid
- the table definition
- source-cell value components

and produces normalized long-format value records.

### What Happens Here

The parser walks the semantic row and column structure and joins each relevant
displayed cell to its source `ParsedCellValue` record. For singleton resolved
tables this is usually the same row index. For integrated continuations, the
join uses `ResolvedRowProvenance` so a resolved row can still point back to
the original source table fragment and source row. It then attaches variable,
level, column, and header-path semantics to the already parsed component
payload.

Examples include:

- count and percent components
- mean and standard deviation components
- median, q1, and q3 components
- p-value components with inequality relations
- scalar count or estimate components

Some source component shapes are deliberately conservative. For example,
`52.3 (14.1)` is parsed in `parsed_cell_values.json` as an estimate plus an
ambiguous uncertainty component unless source context already resolves it. In
this semantic join stage, a variable-level summary hint such as `mean_sd` can
refine those components into `mean` plus `sd` while preserving the source
record provenance and raw printed value.

### Why `ParsedTable` Is Separate From `TableDefinition`

Because row and column semantics can be right even when value parsing is wrong, and vice versa.

Keeping these apart makes debugging much more honest.

`ParsedTable.values` is now the component-aware long-format semantic view.
`components` is the canonical value payload. Scalar compatibility aliases such
as `value_type`, `parsed_numeric`, and `parsed_secondary_numeric` are not part
of the canonical value record.
`parsed_tables.json` is not replaced by `parsed_cell_values.json`; it is the
joined semantic view over source components.

## Step 10: Build Parse Quality Reports

The parser also writes `parse_quality_reports.json`.

This is an inspection artifact built from deterministic row classifications, variable blocks, column-role guesses, and value-pattern recognition.
It is meant to answer questions like:

- are many rows still classified as unknown?
- did a p-value column mostly contain p-value-like values?
- are inferred group or overall columns mostly numeric/statistical?
- did header detection or normalization emit suspicious structural signals?
- do the full-width hline separator and first value-region anchor disagree on
  where the table body starts?

This step does not change `table_definitions.json` or `parsed_tables.json`.
It exists so column and row problems are visible even when the table technically parses.

## Step 11: Build Paper Page Furniture

The parser writes `paper_page_furniture.json`.

This paper-level artifact collects PyMuPDF page text lines, normalizes text only
for matching, clusters repeated text in stable page-relative positions, and emits
generic ignored regions. The footnote stage uses those regions to suppress
overlapping definition candidate lines and table-cell anchors before linking.

## Step 12: Build Paper-Level Document Context

The parser also builds a paper-level context representation from the whole document.

This is separate from table extraction.

The current paper-context path is:

```text
PDF -> paper_markdown.md -> paper_sections.json -> paper_visual_inventory.json -> paper_references.json -> paper_variable_inventory.json -> table_contexts/*.json
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

### `paper_visual_inventory.json`

The parser builds a paper-level inventory of actual in-paper visual objects.

For tables, this starts from extracted table titles and captions and links back to `table_id` when possible.

For figures, the current implemented scope is caption inventory from markdown-derived text. Figure image extraction is intentionally separate and can later populate artifact paths without changing the reference schema.

This inventory is the check that prevents every prose mention of `Figure X` from being treated as an in-paper figure reference.

After references are resolved, each visual is annotated with a reference-check status. Standard in-paper tables and figures should have at least one resolved prose reference outside the visual object itself. Caption-like mentions such as `Table 1. Baseline characteristics` and extracted table-body text do not satisfy this check. Supplementary tables and figures are exempt.

### `paper_references.json`

The parser scans all paper sections for table and figure mentions such as `Table 1`, `Table1`, `Fig. 2`, and compound mentions like `Figures 2A and 2B`.

Each reference keeps a stable reference ID, section and paragraph anchor fields, character offsets, and compact anchor text. By default the anchor text is the sentence containing the mention plus one preceding and one following sentence when available.

References are resolved against `paper_visual_inventory.json` when possible. Mentions that do not match an actual in-paper visual remain explicit as `unresolved` or `external_or_bibliographic` rather than being dropped.

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
- resolved paper-level table reference IDs when available

This produces per-table passages and term lists that can later support standalone review workflows or future semantic interpretation.

## Step 13: Optional Variable-Plausibility LLM Review

The separate `review-variable-plausibility` command can run a narrow LLM review using:

- the deterministic `TableDefinition.variables`
- merged table title/caption text
- attached level labels, units hints, and summary-style hints

This produces `table_variable_plausibility_llm.json`.

Current implemented scope:

- score whether a variable label and `variable_type` fit together
- score whether categorical levels look sensible for the named variable
- preserve the supplied variables exactly and add `plausibility_score`

This command does not rewrite the deterministic table definition.

When `LLM_DEBUG=true`, the review command also writes `llm_variable_plausibility_debug/...`.

Why this stage is optional:

- deterministic structure should do as much as possible first
- LLM use should be focused on ambiguity, not raw PDF recovery
- review calls should be inspectable and skippable

## Step 14: Write Table Processing Status

After deterministic parsing, the parser writes `table_processing_status.json`.

This artifact records:

- the resolved semantic table ID
- the normalized source table IDs that contributed to that status record
- which existing rescue or repair paths were considered
- which ones ran
- source-fragment diagnostics carried forward from parse-quality and resolution artifacts
- whether the table ended as `ok`, `rescued`, or `failed`
- the terminal failure stage and failure reason when rescue was exhausted

If a broad extracted value cell was expanded into visual value columns during normalization, that repair is recorded as an `extra_wide_value_column_repair` attempt rather than treating the original newline-stacked extraction as an unrecovered collapsed grid.

For integrated continuations, status is resolved-table keyed. Source-fragment
warnings remain inspectable through `source_table_ids` and
`source_fragment_diagnostics` rather than becoming separate semantic table
statuses.

## What A Human Should Inspect First

When a parse looks wrong, inspect the outputs in this order.

1. `extracted_tables.json`
   If the raw grid is already wrong, stop here. The problem is extraction.

2. `normalized_tables.json`
   If the raw grid was usable but header rows, edge trimming, split-value repair, or cleaned text are wrong, the problem is normalization.

3. `resolved_tables.json`
   If one logical table spans pages, inspect this to see whether fragments were integrated, rejected, or left as singletons, and how resolved rows map back to source table rows.

4. `table_continuation_column_checks.json`
   If a source fragment has explicit or narrow inferred continuation evidence, inspect this to see whether the normalized column count and schema-derived column headers are compatible.

5. `table1_continuation_groups.json`, `merged_table1_tables.json`, and `continued_variable_integrations.json`
   Inspect these older review artifacts when you need a source-fragment view of continuation candidates, merged rows, or boundary reinterpretation evidence.

6. `table_profiles.json`
   If the table was routed to the wrong family, the problem is in routing.

7. `paper_table_inventory.json`
   If a table is assigned to the wrong broad category, inspect this artifact's chosen category, confidence, and evidence.

8. `table_definitions.json`
   If row meanings or column meanings are wrong, the problem is in the semantic heuristics.

9. `parsed_cell_values.json`
   If the printed cell components are wrong before semantic labels are attached, the problem is in source-cell value parsing.

10. `parsed_tables.json`
   If source-cell components and row/column meanings are right but the final values are wrong, the problem is in the semantic value join.

11. `table_processing_status.json`
   If a table is empty or incomplete, inspect this next to see which rescue paths were attempted and where failure was recorded.

12. `parse_quality_reports.json`
   If the parse succeeded but the columns, p-values, headers, or row classifications look suspicious, inspect this artifact for deterministic quality warnings.

13. `paper_footnotes.json`
   If superscripts, subscripts, or note markers matter, inspect this artifact for anchors, candidate definitions, and resolved, ambiguous, or unresolved glyph-key links.

14. `paper_page_furniture.json`
   If repeated page headers, footers, watermarks, or download notices may be contaminating note extraction, inspect this artifact for recurring clusters and ignored regions.

15. `paper_markdown.md`, `paper_sections.json`, `paper_visual_inventory.json`, `paper_references.json`, `paper_variable_inventory.json`, and `table_contexts/*.json`
   If semantic context retrieval is weak, inspect these next.

16. `table_variable_plausibility_llm.json`
   If deterministic variables were reasonable but the plausibility review looks wrong, the issue is in prompting, provider behavior, or validation for the standalone review command.

## Why This Pipeline Shape Is Worth Keeping

The system is intentionally not "PDF in, one JSON out."

The multiple stages are not accidental complexity. They are what make the parser inspectable and research-friendly.

This separation gives the project:

- raw extraction provenance
- parser-facing structural cleanup
- resolved continuation provenance plus source-fragment continuation inspection
- explicit routing for mixed-table papers
- value-free semantics before value parsing
- optional standalone variable plausibility review
- deterministic parse-quality diagnostics
- easier debugging when a paper fails in only one part of the pipeline

That is the main reason the project can support both engineering work and research iteration without collapsing all errors into one opaque final output.
