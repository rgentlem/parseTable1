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
- `table_regions.json`
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
- `paper_bibliography.json`
- `paper_style_profile.json`
- `paper_page_furniture.json`
- `paper_markdown.md`
- `paper_text_stream.json`
- `paper_sections.json`
- `paper_table_mentions.json`
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

`table_regions.json` records geometry-derived ownership for each extracted
table before normalization: caption/title rows, preamble rows, column-header
bands, body rows, footer/note bands, and row-level role assignments. It is
built from extracted table entries, row bounds, cell bboxes when needed, and
horizontal rules after page-furniture filtering. Table captions and titles are
represented here as table identity/component evidence, not as column headers.

`paper_page_furniture.json` records repeated page text observations, recurrence
clusters, and generic ignored regions. It is built before paper markdown,
layout-aware text streaming, section parsing, bibliography extraction, and
table extraction. Repeated page-furniture lines are removed from
`paper_markdown.md` and `paper_text_stream.json`; `paper_sections.json` and
bibliography entries are derived from the layout-aware text stream when
available. The same artifact is passed into table extraction, cell text
annotation, and footnote PDF-block collection as an early geometry mask. It is
written even when no repeated page furniture is found.

`paper_footnotes.json` records detected table-local footer regions, footnote
anchors, candidate definitions, and glyph-key links as a paper-level review
artifact. It is written even when no anchors or definitions are found.
Definition candidates are fed first by footer rows preserved in
`extracted_tables.json`: `find_table_footer_rows()` prefers rows below a
bottom table rule that is itself below the last value-matrix row, then falls
back to rows after the last value-matrix row when rule evidence is unavailable.
Rows that start a marker definition are grouped with adjacent continuation rows
in extracted row order. Confirmed footer rows can carry marker-start evidence
from cell-text annotation geometry when a raised marker begins the first
populated footer cell; raw extracted strings that visually run the marker into
the next word are preserved as provenance but do not define the marker.

PyMuPDF contiguous page text blocks are the positioned PDF source, not isolated
page lines. These blocks are built from normalized positioned characters after
page-furniture filtering, so font-qualified Unicode recovery and glyph geometry
are still available when a visual marker is collapsed into neighboring text.
A table-footer finder uses table bboxes, horizontal overlap, vertical
adjacency, and continuation-group visual identity to classify complete PDF text
blocks as table-local footer blocks before glyph-key linking. PDF-classified
table-footer blocks are also persisted as unsplit `footers` records, so review
can inspect the same raw footer region that later produces split definition
records.
Remaining PDF text blocks can still become page-bottom notes. Candidate blocks
may start with a marker or contain embedded marker definitions after nearby
explanatory prose. If extracted text visually collapses a superscript marker
into the following definition word, the definition split is based on the
smaller raised marker glyph recorded in PyMuPDF character geometry or
`cell_text_annotations.json`, not on the malformed word itself.
Textual marker definitions such as `The asterisk indicates ...` remain valid
local definition evidence. A single table-footer block can yield several
definition records, for example `*`, `†`, `‡`, `§`, `**`, and `***`
definitions. Repeated page furniture should not enter this stage: table rows,
cell-character annotations, and PDF definition blocks are all derived from
early-filtered geometry.
R footnote review helpers filter by table fragment ID and by paper visual ID,
so a table-number review includes footer records found on continued fragments
such as `Table 1. (continued)` without treating the continuation label itself as
a footnote definition.
Numeric table-cell bibliography markers are removed from table-footnote link
counts when they have no local table-note definition and match the paper's
bibliography entries; they are represented instead through
`paper_bibliography.json`.

`paper_bibliography.json` records the paper's own bibliography entries,
numbered or unnumbered, and observed numeric reference markers linked to
numbered entries. Bibliography entries are extracted from layout-aware,
page-furniture-filtered `paper_text_stream.json` before table extraction, with
markdown-derived sections retained as fallback. The layout reader uses one
entry-boundary workflow: read page, column, then vertical position; start a new
entry when the row returns to the column's left edge, either at a numeric label
or at the first author/organization text in a hanging-indent list; keep indented
rows as continuations across column and page boundaries. Table-cell
reference-marker links are added later after cell text annotations are
available.

`paper_table_mentions.json` is built from the page-furniture-filtered
layout-aware text stream before table extraction. It records each observed
`Table N` mention as a caption candidate, continuation label, or prose
reference, preserving line IDs, local context, and cue evidence such as a
previous line ending in `shown in`. Text-position table fallback consumes this
artifact so a prose reference line cannot become the start of a table candidate.

`paper_style_profile.json` summarizes the document's observed conventions for
footnote markers, bibliography/reference-list style, table caption placement,
figure caption evidence, and table/figure prose references. It is built from
the existing text-stream, table, footnote, bibliography, visual-inventory, and
visual-reference artifacts. It also records consistency checks, such as whether
a predicted numbered bibliography actually has numbered entries. It is review
evidence only; it does not rewrite footnote links or bibliography entries.
Numeric unit/exponent superscripts and subscripts such as `10^9`, `m^2`,
`CO₂`, and `I²` are suppressed before footnote-anchor creation and counted in
metadata. Multi-letter subscript words such as `P_Begg` and `P_Egger` are also
kept out of the footnote anchor inventory.
P-value asterisk markers without explicit definitions can be emitted as
structured `inferred` links with conventional threshold meanings.

## Why There Are Multiple Versions Of A Table

The parser deliberately keeps several versions of the same table because each stage answers a different question.

- `ExtractedTable` answers: what did the PDF extractor recover?
- `TableRegion` answers: which extracted rows and columns belong to captions,
  column headers, body content, and footer notes by geometry?
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
  -> paper page furniture
  -> paper text stream / markdown / sections / bibliography
  -> extracted tables
  -> cell text annotations
  -> table regions
  -> normalized tables
  -> column header schemas
  -> resolved tables
  -> parsed source-cell values
  -> Table 1 continuation inspection artifacts over source fragments
  -> paper footnotes
  -> table profiles over resolved tables
  -> table definitions over resolved tables
  -> parsed tables
  -> table processing statuses over resolved tables
  -> parse quality reports
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

Before table extraction, the parser builds repeated page-furniture regions from
positioned page text. The extraction layer receives those regions and is
responsible for finding likely tables in the remaining PDF geometry and
recovering a raw grid for each one.

Conceptually, this stage does four things:

1. inspect the PDF page layout
2. remove repeated page-furniture words, chars, and explicit-grid rows by bbox
3. find table candidates
4. build `ExtractedTable` objects for the deduplicated candidates

The current extractor uses `pymupdf4llm` as the main backend. It tries to recover explicit table boxes and table cell grids from the backend JSON output. When that is not enough, it can fall back to text-position-based layout reconstruction.

Extraction also uses early, coarse document-structure landmarks when available.
If positioned page text identifies an Abstract heading followed by an
Introduction heading, the y-interval between them is treated as front matter.
Uncaptioned backend table boxes inside that interval are suppressed unless they
carry real table identity or strong value-matrix evidence. This prevents
article-info/abstract page layouts from entering the table pipeline as pseudo
tables while keeping the decision at the extraction stage where candidate
ownership belongs.

For some explicit tables, the backend cell grid is too coarse even though the page still contains enough geometry to do better. When a table has credible full-width horizontal rules, extraction can treat the backend grid as a rough table region, rebuild the row grid from positioned PyMuPDF words inside the ruled band, and let the rules define the header/body split. If the backend table box starts just below a true full-width top rule or ends just above a true bottom rule, extraction may expand the word clip to those rules so header or final body rows are not lost before column-header schema construction. This hline-led path is not limited by table size; it is meant for small ruled tables as well as larger grids when the rule geometry is stronger than the backend cell grid.

When a table shows strong grouped-header signals, such as repeated `Model 1`, `Model 2`, `Model 3` blocks plus wide horizontal boundaries, extraction can also refine the explicit backend grid using word positions inside the table bounding box.

For collapsed explicit grids, word-position refinement treats stable value columns as repeated value-like numeric anchors. The left row-label region is inferred from the observed gap before the repeated value run, not from a literal header such as `Characteristics`. This prevents label text such as `Q1-Q3`, `kg/m2`, or biomarker names containing digits from creating fake columns, while keeping a mostly text left column intact when the numeric matrix starts to its right. Rows with a trailing statistic and only nonnumeric fragments to its left can also be repaired from right to left so long first-column labels remain a single row label.

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
- suppress weak unnumbered candidates when their document position is impossible relative to confirmed numbered tables, such as before Table 1 or between consecutive Table 3 and Table 4 candidates, while preserving adjacent possible continuations for later schema checks
- allow explicit-table grid refinement when rule and word geometry clearly support a better internal column structure
- suppress backend table-like boxes once the document has entered a `References` or bibliography section, because reference lists are document metadata rather than epidemiology tables; any future reference parser should consume them as atomic citation records, not tokenized table cells
- suppress uncaptained backend table-like boxes inside the Abstract-to-Introduction front-matter interval unless they have real table identity or strong value-matrix evidence
- require page-text-layout fallback candidates to have a real table-number/caption signal unless their reconstructed grid has strong table geometry: at least three columns, at least four rows, a header-like top row, stable multi-column alignment, and multiple rows with data-like trailing cells
- when a text-position fallback caption wraps onto the next line, keep a short caption continuation line with the table label, and also keep a lowercase sentence fragment ending in punctuation with the caption instead of treating it as the first table row
- when text-position fallback builds column anchors, prefer an early stable table prefix if using the full page would collapse separated value columns because of later wrapped rows, page-margin text, or other noisy numeric positions
- for explicit rotated-grid refinement, prefer PyMuPDF directional text-block
  bboxes as the source-region boundary before coordinate transformation. On
  two-column pages this keeps the rotated table plus its footer in one source
  column while excluding upright article text in the other column.
- if a backend explicit table box mixes upright article text with a rotated
  table, derive a separate rotated-block candidate from the contiguous vertical
  PyMuPDF text block inside that box and let normal candidate deduplication
  choose between the original mixed box and the recovered rotated table.
- remove repeated page furniture before candidate refinement. Extraction records
  `metadata.page_furniture_overlap` when a candidate bbox touches an ignored
  region and `metadata.page_furniture_mask` when words, chars, or rows were
  actually removed.
- trailing continuation-page notes such as `(Table 1 continues on next page)` may
  still be removed and recorded in `metadata.trailing_non_table_rows`; broad
  footer/furniture cleanup is handled by the earlier page-furniture mask.

This matters for papers with table continuations, odd numbering, or weak captions. A bad score should generally be inspectable, not silently destructive; the exception is a weak unnumbered candidate whose source-order position is already inconsistent with the confirmed table sequence and that does not look like an adjacent continuation.

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

For mixed backend boxes repaired into rotated-block candidates, extraction also
records `orientation_strategy`, `rotated_block_candidate`, and the
`source_mixed_table_bbox` so review can see that the final table came from a
geometry-derived subregion rather than the full backend table box.

For explicit tables, extraction may also record the visible first-word x-position for each first-column row label. This exists because backend cell boxes often describe the full column boundary, while the actual text inside that cell may be indented. Normalization uses that compact word-position metadata for indentation inference while preserving the original cell boxes as grid geometry.

For text-position fallback and sideways-transformed candidates, extraction may preserve recovered cell text bounding boxes directly in `table_cells`. These boxes are in the same coordinate frame as the recovered grid and allow normalization to infer row-label indentation even when the backend did not emit explicit table cells.

### Why `ExtractedTable` Exists

This is the audit trail for extraction.

If a value is wrong here, the problem is in extraction, not in later semantic logic.

If a value is correct here but wrong later, the problem is in normalization or parsing.

That distinction is one of the main reasons the project keeps intermediate artifacts.

## Step 3: Table Region Ownership

The table-region stage converts extracted table geometry into explicit row
ownership before normalization changes the parser-facing grid.

This stage consumes `ExtractedTable` objects plus their available geometry:
cell boxes, row bounds, table bboxes, full-width and ordinary horizontal rules,
and already-filtered page context. For ruled tables, horizontal rules define
the major candidate bands. Rows above the first table rule can become
caption/title or preamble rows; rows between table rules become the
column-header band; rows below the header/body rule become the body; rows below
a bottom body rule become footer/note rows. When rule evidence is incomplete,
the stage falls back to value-region anchors and records lower confidence.

This stage deliberately separates three concepts that should not share one
generic "header" label:

- page headers are page-furniture candidates and should already be filtered
- table captions/titles identify a table but are not column headers
- column-header bands are the rows that define the table's column axis

`NormalizedTable` consumes these region decisions when available. Footnote
harvesting can also consume `footer_note_rows` from this artifact instead of
independently rediscovering extracted footer rows.

## Step 4: Normalization

Normalization converts each `ExtractedTable` into a `NormalizedTable`.

This is the first stage that prepares the table for interpretation, but it still avoids making strong semantic claims such as "this row is definitely a categorical parent variable" or "this cell definitely means a count and percent."

### What Normalization Does

Normalization currently performs several practical cleanup steps.

#### 4.1 Build A Stable Row Grid

The extracted cells are reassembled into a row-major grid.

This gives the downstream logic a stable rectangular structure to reason over.

#### 4.2 Trim Obviously Non-Informative Edge Columns

Some extracted tables contain junk leading or trailing columns, often because the PDF layout has an empty margin column, a rule fragment, or other extractor noise.

Normalization can conservatively drop:

- a mostly non-informative leading column
- a mostly empty trailing column

It can also handle a rarer structural variant where the leftmost column is not empty but is only a sparse stub for section labels such as broad row groups, while the next column contains the actual row labels and the remaining columns contain values. In that case normalization may drop the sparse stub column, suppress stub-only rows, shift the real label column left, and merge the stub plus label text for rows where both cells together form one label.

Why this happens here:

- it is a structural cleanup, not a semantic inference
- later row and column interpretation is cleaner when the table edges are already sane

#### 4.3 Produce Parser-Facing Cleaned Rows

Normalization builds `metadata.cleaned_rows`, which is the parser-facing text version of the table.

This cleaned form is used by downstream heuristics, prompting, and debugging.

The shared text cleaning layer currently does things like:

- collapse whitespace
- normalize symbol variants such as dash forms and comparator forms
- repair a narrow set of known extractor glyph failures

One example of that last category is a broken replacement character such as `�0.12` being repaired to `<=0.12` in parser-facing text.

Some symbol-font repairs happen earlier, during PyMuPDF character extraction,
because font context is needed to know that an extracted character such as `6`
is really `±` or that a symbol-font comma is really `<`. Those repairs feed
word/grid reconstruction and preserve raw glyph provenance on character
records. Parser-facing text cleaning remains the later table-text normalization
layer.

Important design rule:

- raw extracted cell text is still preserved earlier in `ExtractedTable`
- cleaned parser-facing text belongs in normalization and later stages

#### 4.4 Record Text Cleaning Provenance

Normalization now also records `metadata.text_cleaning_provenance`.

This is a table-level audit summary showing, for the surviving normalized grid:

- which comparator symbols were observed directly
- which comparator symbols were reconstructed from known extractor glyph-failure rules
- which repair rules fired
- how many cells needed glyph repair

This exists because parser-facing cleanup is useful, but it should not be invisible.

#### 4.5 Apply Table-Region Header And Body Rows

When `table_regions.json` is available, normalization consumes its
`column_header_rows` and `body_rows` directly. Caption/title rows, preamble
rows, and footer/note rows remain preserved in `metadata.cleaned_rows`, but
they are excluded from `header_rows` and `body_rows`.

The older cleaned-grid detector remains a fallback for callers that normalize
tables without a `TableRegion` artifact. It is no longer the primary owner of
caption/header/body/footer region decisions in the parse pipeline.

This is an important turning point in the parse, because many later steps assume the system already knows which rows are header material and which rows are body material.

Why the split is still visible here:

- it is still structural
- later semantic steps need this split
- it is easier to debug when region decisions are visible before full semantic interpretation

#### 4.6 Build Row Signatures

For each body row, normalization builds a `RowView`.

`RowView` is a compact row-level feature record. It keeps:

- raw row cells for the body row
- cleaned first-cell forms
- whether the row has trailing values
- simple numeric density signals
- indentation when it can be inferred

This gives later heuristics a small and inspectable summary of the row rather than forcing every heuristic to re-derive low-level row facts from scratch.

#### 4.7 Repair Split Count-Percent Columns

Some tables are extracted with one logical `n (%)` value split across two adjacent columns, such as:

```text
199    (11.5%)
```

Normalization can conservatively merge those back into one logical cell when the surrounding row pattern strongly supports that interpretation.

This is one of the main reasons normalization exists as a real stage rather than a trivial cleanup wrapper.

It is not just prettifying text. It is repairing table structure in a controlled way before semantic interpretation starts.

#### 4.8 Repair Sparse Stub Label Columns

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

#### 4.9 Repair Split Row-Label Field Columns

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

#### 4.10 Repair Embedded Label Tails And Vertical Continuations

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

When `TableRegion` is available, column-shape cleanup uses region-owned header
and body rows as the evidence set for empty-column pruning. Footer/note rows
remain preserved in `ExtractedTable` and `table_regions.json`, but they do not
keep an otherwise empty data-grid column alive in `NormalizedTable`.

#### 4.11 Expand Extra-Wide Stacked Value Columns

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

#### 4.12 Preserve Region Boundary Provenance

Normalization copies the table-region source, confidence, caption rows,
preamble rows, footer/note rows, and diagnostics into
`metadata.header_detection` when a `TableRegion` was supplied. This makes the
region decision visible beside the normalized grid while keeping the canonical
region artifact in `table_regions.json`.

If no `TableRegion` was supplied, normalization can still use the legacy
rule/value-anchor/content fallback and records that fallback source in
`metadata.header_detection`.

#### 4.13 Drop Columns Emptied By Repair

If a split-value repair empties a helper column across the table, normalization
can drop that now-empty column and then reapply the supplied table-region row
ownership. If no region artifact is available, it reruns the legacy header/body
fallback on the repaired grid.

This keeps the normalized grid closer to the logical table structure that the later parser actually wants.

#### 4.14 Decide Whether Indentation Is Informative

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

## Step 5: Build `ColumnHeaderSchema`

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
When a repeated leaf-header sequence such as `% (N)` / `95% CI` recurs across
the value region, that sequence can partition sparse or centered upper headers
into group spans. The rule does not override upper rows that already contain
adjacent repeated labels, because those rows supply their own repeated-label
span evidence.

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

## Step 6: Resolve Continuation Fragments

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

## Step 7: Provisional Table Routing With `TableProfile`

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

## Step 8: Build `TableDefinition`

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

## Step 9: Parse Source-Cell Value Components

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

## Step 10: Build `ParsedTable`

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

## Step 11: Build Parse Quality Reports

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

## Step 12: Write Paper Page Furniture

The parser writes the `paper_page_furniture.json` artifact that was built before
paper context parsing and table extraction.

This paper-level artifact collects PyMuPDF page text lines, normalizes text only
for matching, clusters repeated text in stable page-relative positions, and emits
generic ignored regions. Paper text streaming, markdown filtering, table
extraction, cell text annotation, and footnote PDF-block collection use those
regions before downstream artifacts are built.

## Step 13: Build Paper-Level Document Context

The parser also builds a paper-level context representation from the whole document.

This is separate from table extraction.

The current paper-context path is:

```text
PDF -> paper_page_furniture.json -> paper_text_stream.json -> paper_markdown.md -> paper_sections.json -> paper_table_mentions.json -> paper_bibliography.json -> paper_visual_inventory.json -> paper_references.json -> paper_style_profile.json -> paper_variable_inventory.json -> table_contexts/*.json
```

### `paper_markdown.md`

This is the full-paper backend markdown artifact, produced from `pymupdf4llm`.

It is not the canonical table grid.

It is used for:

- section detection
- table mention retrieval
- variable-term retrieval
- future semantic grounding

Only conservative glyph repair and repeated page-furniture line removal are
allowed here. This artifact is not meant to become the canonical paper-order
model.

### `paper_text_stream.json`

This is the layout-aware full-paper text stream. It is built from positioned
PyMuPDF lines, applies `paper_page_furniture.json`, detects page-level column
bands, and orders text as page, column, then vertical position for any detected
column count. It also records per-line bbox, page, column, role, and page-level
column diagnostics plus `column_boundaries` and `column_bands`.

### `paper_sections.json`

The layout-aware stream is rendered to lightweight markdown and split into a
linear list of sections, with simple role hints such as methods-like or
results-like. If positioned text cannot be read, the parser falls back to
filtered `paper_markdown.md`.

This gives the parser a document structure that is easier to retrieve from than raw markdown alone.

### `paper_table_mentions.json`

The parser scans `paper_text_stream.json` for `Table N` mentions before table
extraction. Each record keeps the table number, source line ID, local context
line IDs, source-line text, cue, and whether the mention is a `caption_candidate`,
`continuation_label`, or `prose_reference`.

This artifact is used as extraction evidence, not as a table source. A line
beginning with `Table 5.` is rejected as a fallback table start when the previous
line makes the sentence read as `... is shown in Table 5.`. Bold-like or
heading-like text-stream evidence is preserved in line notes and can support a
caption candidate, but it does not by itself create a table.

### `paper_bibliography.json`

The parser extracts the paper's bibliography entries from the positioned text
stream before table extraction begins, falling back to layout-stream-derived
sections only when the positioned stream cannot produce entries. Reference-list
pages are read as page, column, then vertical position; entries remain open
across column and page breaks until the next left-edge entry start is found.
For numbered lists that start may be a bracketed, dotted, or bare numeric label;
for author-year lists it may be the first author/organization line with
following hanging-indent continuations. This artifact is per-paper only: it
keeps labels and raw/clean entry text as separate entities without DOI lookup,
author normalization, cross-paper deduplication, or any corpus-level reference
store.

After table extraction and cell text annotation, numeric table-cell markers that
look like bibliography references can be linked to those bibliography entries.
For example, numeric superscripts attached to study/source row labels should be
represented here rather than counted as unresolved table footnotes when no local
table-note definition exists.

### `paper_style_profile.json`

The parser builds a compact style summary from existing paper-level artifacts.

It records:

- likely footnote marker family, with counts by numeric, letter, symbol,
  asterisk, and unknown markers
- likely bibliography/reference-list style, including numbered versus
  unnumbered/hanging-indent lists
- likely table caption placement, using extracted-table caption metadata and
  nearby positioned text lines
- figure caption text evidence, with an explicit note that figure geometry is
  not extracted yet
- prose table/figure reference wording and resolution-status counts

Each dimension keeps `likely_style`, `confidence`, count dictionaries, compact
evidence examples, and notes. The profile also has `checks` that compare the
style inference with parsed artifact reality, including bibliography numbering,
footnote link coverage, caption-placement coverage, figure-geometry
availability, and visual-reference resolution. This gives later
footnote/linking work an inspectable document-style signal without embedding
journal-specific rules in the link resolver.

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

## Step 14: Optional Variable-Plausibility LLM Review

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

## Step 15: Write Table Processing Status

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

If a structurally wide matrix-like real table is outside the current
descriptive/estimate parser routes, status should preserve it as a real table
with an unsupported-route note instead of calling it a non-table layout
artifact. The broader `paper_table_inventory.json` category can then expose it
as `data_presentation` for later family-specific parsing work.

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
   If superscripts, subscripts, or note markers matter, inspect this artifact for detected table-local footer regions, anchors, candidate definitions, math/unit suppression metadata, and resolved, ambiguous, inferred, or unresolved glyph-key links.

14. `paper_bibliography.json`
   If numeric study/source markers look like bibliography references, inspect this artifact for the paper's fixed reference-list entries, observed marker links, and per-paper coverage diagnostics.

15. `paper_page_furniture.json`
   If repeated page headers, footers, watermarks, or download notices may be contaminating extraction or note parsing, inspect this artifact for recurring clusters and ignored regions.

16. `paper_markdown.md`, `paper_text_stream.json`, `paper_sections.json`, `paper_visual_inventory.json`, `paper_references.json`, `paper_variable_inventory.json`, and `table_contexts/*.json`
   If semantic context retrieval is weak, inspect these next.

17. `table_variable_plausibility_llm.json`
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
