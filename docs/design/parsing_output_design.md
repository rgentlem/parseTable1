# Parsing Output and JSON Design

This document describes the JSON artifacts used by the Table 1 parser, the canonical typed models behind them, and the design rules that should govern future output changes.

The short version is:

- table data stays JSON-first
- each pipeline phase has its own schema
- raw extracted content is preserved
- canonical objects must be unambiguous in both Python and R
- row and column references stay stable across phases
- trace/debug wrappers are not the same thing as canonical parsed outputs
- mixed-table papers may eventually route into different semantic families after normalization

## Required Reading Before Changing Outputs

Before changing JSON outputs or schemas, always read:

- `AGENTS.md`
- `docs/design/codex_build_spec.md`
- `docs/design/paper_markdown_spec.md` when changing markdown-context outputs

Those files define the main development criteria:

- keep extraction, normalization, heuristics, LLM interpretation, and validation as separate modules
- preserve the pipeline shape `PDF -> ExtractedTable -> TableBoundaryProposal -> TableRegion -> NormalizedTable -> ColumnHeaderSchema -> BodyElementCandidates / BodyRowLabelCandidates -> ResolvedTableSet -> TableDefinition -> ParsedTable`
- keep tables in structured JSON rather than switching to Markdown-first representations
- preserve raw extracted data and original text
- use deterministic parsing first and LLM refinement only for semantic disambiguation
- require strict JSON from the LLM and validate it before accepting it

## Canonical Models vs Persisted Files

There are two related but different concepts in this repository:

1. Canonical typed structures
   These are currently implemented largely with models in
   `table1_parser/schemas/` and
   `table1_parser/llm/variable_plausibility_schemas.py`. Their use of Pydantic
   is an implementation choice under review, not part of the artifact contract.

2. Persisted JSON files
   These are CLI outputs or trace/debug artifacts written to disk.

Some JSON files are direct dumps of canonical models. Others are wrapper files that add timestamps and nest the real payload under keys like `payload`, `response`, or `interpretation`.

## Cross-Language Object Principle

This repository should treat cross-language object design as a first-order principle.

The real semantic objects are the canonical typed structures used by the parser and by downstream R tooling.
JSON is the transport format between those environments, not the conceptual source of truth.

That means every important persisted artifact should be designed so that:

- it can be instantiated as a clear typed object in Python
- it can be loaded as a clear, unambiguous object in R
- field meanings remain stable across languages
- row-oriented records can be converted into R data frames without bespoke restructuring
- IDs and coordinates remain explicit rather than implied by list position alone

When designing or revising schemas:

- prefer explicit named fields over positional conventions
- prefer flat arrays of records over deeply nested ad hoc objects
- use IDs to link related records instead of relying on language-specific object identity
- keep enum-like string vocabularies stable and documented
- avoid shapes that are easy in Python but ambiguous or awkward in R

This principle applies to `TableDefinition`, `ParsedTable`, paper-context artifacts, `paper_variable_inventory.json`, and `paper_table_inventory.json`.

## Output Layers

| Layer | Canonical type | Current file status | Main purpose |
| --- | --- | --- | --- |
| Extraction | `ExtractedTable` | Written now as `extracted_tables.json` by `extract` and `parse` | Preserve raw table grid and cell provenance |
| Boundary proposal | `TableBoundaryProposal` | Written now as `table_boundary_proposals.json` by `parse` | Persist canonical geometry alternatives used to establish or compare provisional body intervals, plus review concerns and selected edges |
| Table region ownership | `TableRegion` | Written now as `table_regions.json` by `parse` | Persist row roles around the geometry-defined body: headers above it and footer/note bands below it, before normalization consumes them |
| Body occupancy | `BodyOccupancyTable` | Written now as `body_occupancy.json` by `parse` | Persist raw physical-body-line occupancy in character-width-derived x bins plus exact font-qualified zero-gap evidence, without smoothing or downstream grid changes |
| Leaf-column candidates | `LeafColumnCandidateTable` | Written now as `leaf_column_candidates.json` by `parse` | Persist provisional stub/value bands from exact zero-occupancy gaps at least two observed table-font spaces wide, with supporting unmerged rule endpoints, without changing the extracted grid |
| Header-structure candidates | `HeaderStructureCandidate` | Written now as `header_structure_candidates.json` by `parse` | Persist positioned leaf/header evidence, preserving a complete flat canonical header cell-for-cell and otherwise classifying one-leaf labels and contiguous multileaf groups from observed anchors, per-band evidence, and individual partial rules; retain linked marker IDs plus raw/base node text, unresolved fragments, and post-assignment diagnostics without changing the accepted column schema |
| Cell text annotations | `CellTextAnnotationTable` | Written now as `cell_text_annotations.json` by `parse` | Preserve superscript, subscript, and small marker geometry as extraction-side evidence without rewriting raw cell text |
| Normalization | `NormalizedTable` | Written now as `normalized_tables.json` by `normalize` and `parse` | Clean rows, apply table-region row ownership when available, and derive row features |
| Column header schema | `ColumnHeaderSchema` | Written now as `column_header_schemas.json` by `parse` | Persist parser-native leaf columns, spanning header groups, group-to-leaf relationships, raw cell evidence, and coordinates before semantic column projection |
| Body element candidates | `BodyElementCandidate` | Written now as `body_element_candidates.json` by `parse` | Persist logical body-value candidates, linked marker IDs, and raw/base text built over the settled column grid without changing extracted or normalized physical cells |
| Body row-label candidates | `BodyRowLabelCandidate` | Written now as `body_row_label_candidates.json` by `parse` | Persist logical body row-label candidates, linked marker IDs, and raw/base text built over adjacent physical source rows without changing extracted or normalized physical rows |
| Resolved table set | `ResolvedTableSet` | Written now as `resolved_tables.json` by `parse` | Persist the semantic working table list after continuation resolution while preserving `normalized_tables.json` as full source evidence |
| Table 1 continuation inspection | `Table1ContinuationGroup`, `NormalizedTable` | Written now as `table1_continuation_groups.json` and `merged_table1_tables.json` by `parse` | Persist source-fragment grouping and merged normalized-row review views for explicit or strongly inferred Table 1 continuations |
| Continuation column compatibility | `TableContinuationColumnCheck` | Written now as `table_continuation_column_checks.json` by `parse` | Persist schema-derived source-fragment column-header compatibility checks for explicit or strongly inferred descriptive continuations |
| Table routing | `TableProfile` | Written now as `table_profiles.json` by `parse` | Persist provisional deterministic parser-route decisions |
| Paper table inventory | `PaperTableInventory`, `PaperTableRecord` | Written now as `paper_table_inventory.json` by `parse` | Persist deterministic taxonomy predictions for the resolved semantic table list |
| Table definition | `TableDefinition` | Written now as `table_definitions.json` by `parse` | Persist value-free row-variable, level, and column semantics |
| Continued variable integration | `TableDefinition` | Written now as `continued_variable_integrations.json` by `parse` | Persist a source-fragment review view for compatible continued Table 1 fragments; this is not consumed by canonical semantic parsing now that `resolved_tables.json` feeds `TableDefinition` and `ParsedTable` |
| Parsed source-cell values | `ParsedCellValue` | Written now as `parsed_cell_values.json` by `parse` | Persist source-grid or candidate-derived value components keyed by table and row/column indices before semantic row/column value joins |
| Paper context | `PaperPositionedDocument`, `PaperDocument`, `PaperSection`, `PaperTableMention`, `PaperVisual`, `PaperVisualReference`, `TableContext` | Written now as `paper_positioned_document.json`, `paper_document.json`, `paper_markdown.md`, `paper_sections.json`, `paper_table_mentions.json`, `paper_visual_inventory.json`, `paper_references.json`, and `table_contexts/*.json` by `parse` | Persist one shared positioned-text pass, canonical prose/residual block ownership, prose-only section and Markdown views, document-owned non-prose context joined to raw positioned evidence, pre-extraction table mention classification, actual in-paper visual objects, anchored table/figure references, and per-table retrieval bundles |
| Paper bibliography | `PaperBibliography`, `BibliographyEntry`, `BibliographyReferenceMention` | Written now as `paper_bibliography.json` by `parse` | Persist the paper's own bibliography entries, numbered or unnumbered, and link observed numeric reference markers through their stable cell-annotation IDs to numbered entries without creating a cross-paper citation-management layer |
| Paper style profile | `PaperStyleProfile`, `PaperStyleDimension`, `PaperStyleCheck`, `PaperStyleEvidence` | Written now as `paper_style_profile.json` by `parse` | Persist document-level counts, examples, and consistency checks for footnote-marker, bibliography, caption-placement, and visual-reference conventions without changing extraction or link decisions |
| Paper variable inventory | `PaperVariableInventory`, `VariableMention`, `VariableCandidate` | Written now as `paper_variable_inventory.json` by `parse` | Persist the paper-level candidate variable reference list with explicit text/table provenance |
| Variable-plausibility LLM review | `LLMVariablePlausibilityTableReview` | Written now as `table_variable_plausibility_llm.json` by `review-variable-plausibility` when LLM config is available | Persist table-local QA scores for variable label/type/level plausibility without rewriting the deterministic definition |
| Variable-plausibility debug monitoring | `LLMVariablePlausibilityMonitoringReport`, `LLMVariablePlausibilityCallRecord` | Written only when `LLM_DEBUG=true` as `llm_variable_plausibility_debug/<timestamp>/llm_variable_plausibility_monitoring.json` plus per-table trace files | Persist per-table timing, payload-size, status, and raw-response debug evidence for the standalone review command |
| Variable-plausibility per-table trace files | wrapper JSON files | Written only when `LLM_DEBUG=true` as `variable_plausibility_llm_input.json`, `variable_plausibility_llm_metrics.json`, `variable_plausibility_llm_output.json`, and `variable_plausibility_llm_review.json` | Preserve prompt payloads, metrics, raw provider responses, and validated plausibility reviews for inspection |
| Final parsed output | `ParsedTable` | Written now as `parsed_tables.json` by `parse` | Validated downstream structured table data |
| Table processing status | `TableProcessingStatus`, `TableProcessingAttempt` | Written now as `table_processing_status.json` by `parse` | Persist resolved-table rescue attempts, source fragment IDs and diagnostics, terminal failure stage, and failure reason without overloading semantic artifacts |
| Parse quality diagnostics | `ParseQualityReport` | Written now as `parse_quality_reports.json` by `parse` | Persist deterministic row, column, and value-pattern diagnostics without changing parse behavior |
| Paper footnotes | `PaperFootnotes` | Written now as `paper_footnotes.json` by `parse` | Persist table-local footer regions owned by final `TableRegion.footer_note_rows` or the final rule's `TableBoundaryProposal.following_text_line_ids`, footnote anchors keyed by their source `CellTextAnnotation.annotation_id` with annotation type preserved, separate positioned definition-marker evidence, and explicit glyph-key links whose cross-fragment scope comes only from accepted final `ResolvedTableSet` membership, without rewriting table text or parsed values |
| Paper page furniture | `PaperPageFurniture` | Written now as `paper_page_furniture.json` by `parse` | Persist repeated page text observations, clusters, and ignored regions used near the front of document processing to mask document construction, extraction, cell annotations, and document-linked footer detection before downstream artifacts are built |

Design note for future multitable support:

- after `ResolvedTableSet`, mixed papers may route through a provisional `TableProfile` stage before final semantics are chosen
- long term, parser route should be derived from or explicitly consistent with the broader `paper_table_inventory.json` table category; it should not become an unrelated second taxonomy
- descriptive characteristic tables may continue using `TableDefinition` and `ParsedTable`
- estimate-result tables may later use sibling artifacts such as `EstimateTableDefinition` and `ParsedEstimateTable`
- this family split should be explicit in schemas and persisted files rather than hidden inside one overloaded parser

## Coordinate and Identity Rules

These rules matter because later stages refer back to earlier stages.

- `table_id` is the stable table identifier for one extracted table.
- `row_idx` values are zero-based row indices in the table grid.
- `TableRegion` row assignments, `header_rows`, and `body_rows` are lists of
  those same grid row indices. In current parse output, `header_rows` should
  mean the table's column-header band, not a page header or table caption.
- `row_start`, `row_end`, and level `row_idx` values refer to the same row-index space, not to a separate body-only counter.
- `col_idx` is a zero-based column index in the normalized table grid after any edge-column trimming performed during normalization.

This stability is important because the LLM layer is required to reference existing rows only and must never invent new rows or columns.

## 1. `extracted_tables.json`

Current CLI path:

```text
outputs/papers/<paper_stem>/extracted_tables.json
```

This file is written by:

- `table1-parser extract`
- `table1-parser parse`

Top-level shape:

```json
[
  {
    "...": "one ExtractedTable object"
  }
]
```

Canonical model:

- `ExtractedTable`
- child models: `TableCell`, `TableCaptionRegion`, `TableCaptionBinding`

Top-level design components:

- `table_id`: stable ID for this extracted table
- `source_pdf`: source PDF path or identifier
- `page_num`: 1-based source page number
- `title`: detected table title when available
- `caption`: detected caption when available
- `n_rows`, `n_cols`: extracted grid dimensions
- `cells`: flat list of `TableCell` objects
- `extraction_backend`: extractor name, currently `pymupdf4llm`
- `metadata`: extractor-specific extensions

Important current `metadata` keys produced by extraction may include:

- `candidate_score`
- `caption_source`
- `caption_region`
- `caption_binding`
- `table_number`
- `is_continuation`
- `continuation_of_table_number`
- `table_numbering_audit`
- `explicit_grid_refined_from_words`
- `grid_refinement_source`
- `geometry_coordinate_frame`
- `geometry_transform_source_bbox`
- `geometry_transform_transposed`
- `geometry_transform_applied`
- `orientation_strategy`
- `sideways_candidate`
- `sideways_detection_signals`
- `candidate_visual_object_barrier_bbox`
- `caption_detection_space`
- `table_cells`
- `first_column_text_x0_by_row`
- `page_furniture_overlap`
- `page_furniture_mask`
- `trailing_non_table_rows`
- `table_positioned_evidence`
- `canonical_grid_selection`

`metadata.canonical_grid_selection` records the accepted row and column source,
selected boundaries and bands, and structured diagnostics.
`positioned_grid_validation` records repeated header-cell bboxes that are wholly
contained by different occupancy leaves when that hard conflict rejects
otherwise equal-count positioned cell ownership.

`metadata.table_positioned_evidence` is a compact, typed table-local projection
of `paper_positioned_document.json`. It records the candidate page-space bbox,
positioned line IDs, line/span references, page-local word and character
indices, individual rule-segment indices, and the text-mask artifacts applied
before projection. Each source-reference list has a positionally aligned list
of canonical bboxes or rule segments. `canonical_transform` records the source
bbox, orientation, and six-value affine matrix used to map page coordinates
into the table's `paper_text_orientation_group` frame. Candidate, evidence,
caption, and structural-scope bounds are retained in both page and canonical
coordinates. The structural scope is only the union of evidence and caption
bounds; its rule segments remain individual unclassified records.

`metadata.candidate_visual_object_barrier_bbox` records the canonical bbox of
an image object that constrained caption-and-rule candidate construction. When
the image begins below the canonical table bbox, `TableRegion` may use its top
edge as a hard terminal boundary for adjacent external footer text. The field
does not expand the candidate, evidence, structural-scope, or extracted-table
bbox.

The projection duplicates geometry only, not text or font payloads. Consumers
resolve those through the source references into the shared PyMuPDF artifact.
Upright and rotated tables expose the same canonical fields; upright tables use
an identity transform. This record does not classify rows, columns, or rules
and does not change the extracted grid.

`metadata.caption_region` records the complete caption assembled from
`paper_document.json` joined to positioned lines: its source mention, ordered source line IDs, preserved
line text, page-space union bbox, canonical orientation-group bbox, orientation,
and column. `metadata.caption_binding` records the above/below assignment,
distance, mention and orientation-group IDs, and canonical table/caption bboxes.
Caption discovery and binding do not use PyMuPDF4LLM text boxes or page-text
fallbacks. A caption must have line-initial table-label evidence and bind to the
table in the same canonical geometry. Adjacent caption lines stop at the first
table rule without merging or promoting partial rule segments. These metadata
records do not remove caption-like rows from the extracted grid; later region
ownership handles that separately.

`TableCell` design components:

- `row_idx`, `col_idx`: grid location
- `text`: raw extracted cell text
- `page_num`: optional page reference
- `bbox`: optional bounding box `(x0, y0, x1, y1)`
- `extractor_name`: optional per-cell provenance
- `confidence`: optional cell-level confidence

Design intent:

- this is the canonical extraction contract
- raw values are preserved here
- extractor-specific details belong in `metadata`, not in renamed top-level fields
- literal displayed captions should be preserved even for continuations such as `Table 1 (continued)`
- continuation linkage belongs in metadata, not in synthetic renamed titles such as `Table 1a`
- numbering audits are for inspection only; they must not be used to silently drop extracted tables
- explicit PyMuPDF4LLM table boxes are rough region hints; the canonical extracted grid must come from positioned PyMuPDF words, characters, and rule geometry
- extraction may refine a coarse explicit backend grid when word geometry inside the table bbox, together with strong horizontal boundaries, supports a better row/column structure; if positioned PyMuPDF geometry cannot rebuild the grid, the backend cell grid is not emitted as a normal extracted table
- full-width horizontal-rule metadata should be based on continuous drawn
  line/rule geometry, not filled row highlighting or background shading
- discontinuous same-y rule segments are ordinary horizontal-rule evidence, not
  full-width boundary rules; visible gaps are preserved as header-structure
  evidence
- collapsed-grid word-position refinement chooses value-column anchors from repeated value-like numeric positions rather than one-off digit-bearing label tokens; when needed, it preserves a left label anchor and pulls nonnumeric label fragments back from value columns on rows whose only right-side value is a trailing statistic such as a p-value
- when explicit column boundaries are absent, the first row-label/value boundary should come from the observed physical gap before the repeated first value-column anchor
- extraction must remain a visual/coordinate-faithful artifact: if a printed value or row label is split across physical cells or physical rows, `ExtractedTable` keeps those cells and coordinates as printed; logical reconstruction belongs to `body_element_candidates.json`, `body_row_label_candidates.json`, and later semantic/value parsing, not to extraction grid mutation
- hline-led word-position refinement can rebuild small or large ruled explicit tables from PyMuPDF words when full-width rules provide stronger row-band evidence than the PyMuPDF4LLM cell grid; this records `metadata.grid_refinement_source = "hline_word_positions"` and preserves the original backend grid in refinement metadata
- bbox-word positioned refinement can rebuild ordinary explicit table boxes from PyMuPDF words when no stronger hline/value-matrix path fires; this records `metadata.grid_refinement_source = "pymupdf_positioned_bbox_words"` and `metadata.canonical_extraction_layer = "pymupdf_positioned_geometry"`
- rotated explicit tables may be refined in a table-local normalized coordinate frame; when that happens, `table_cells`, `row_bounds`, and `horizontal_rules` describe that local frame rather than raw page coordinates, while `geometry_transform_source_bbox`, `geometry_transform_transposed`, and `geometry_transform_applied` record the transform input needed to map page characters into the same frame
- for explicit PyMuPDF4LLM tables, extraction may record `first_column_text_x0_by_row` so normalization can infer visible row-label indentation from word positions rather than full cell boundaries; this metadata supports row classification only and does not replace cell bboxes
- text-position fallback candidates may preserve parser-facing cell text bounding boxes in `table_cells`; for these candidates, first-column cell boxes are based on the recovered text extents and can also support indentation-sensitive row classification
- text-position fallback caption collection may keep a short following caption line with the table label, and may also keep an immediately following lowercase sentence fragment that completes the caption with terminal punctuation; this prevents wrapped caption tails from entering the table grid as row zero
- text-position fallback column anchors should prefer an early stable header/value prefix when later noisy rows would merge clearly separated value columns; visible repeated value positions near the top of the table are stronger evidence than page-margin or wrapped-body artifacts later on the page
- explicit rotated-grid refinement may record a PyMuPDF directional text-block
  union bbox as the source table region. This source bbox defines the column
  before coordinate transformation, so a rotated table and its footer can stay
  together while upright article text in another page column is excluded.
- repeated page furniture is detected before extraction and passed into the
  extractor as ignored regions. Extraction records
  `metadata.page_furniture_overlap.has_overlap` and related cluster IDs when a
  candidate bbox touches ignored furniture; it records
  `metadata.page_furniture_mask` when positioned words, chars, or explicit-grid
  rows are actually removed.
- extraction removes explicit trailing continuation-page cues such as
  `(Table 1 continues on next page)` or a standalone final `Continued` row only
  when the cue row contains no table-value cells. The removed range and raw cue
  text are recorded in `metadata.trailing_non_table_rows`; the positioned line
  remains in the shared document evidence. Broad footer/furniture cleanup
  belongs to the earlier page-furniture mask, not to value-gap trailing-row
  heuristics.

### `cell_text_annotations.json`

`cell_text_annotations.json` is the sparse extraction-side marker occurrence
inventory. Each table record contains visual superscript, subscript, and
attached-symbol candidates detected from shared PyMuPDF character geometry.
Every occurrence has a stable annotation ID, canonical glyph key, physical
source-cell ID, bbox, source character indices, source line/span references,
and font evidence. These records preserve visual identity and provenance only:
they do not remove glyphs from raw text or decide whether a marker is a
footnote, citation, mathematical notation, unit exponent, or artifact. Later
footer resolution consumes the same glyph keys. After header/body candidates
exist, their `marker_ids` link back to these occurrences. Candidate `base_text`
removes only an exactly aligned character/span occurrence; `raw_text` and the
annotation sidecar remain unchanged.

## 2. `table_boundary_proposals.json`

`table_boundary_proposals.json` records provisional geometry evidence in the
canonical orientation-group frame. Each table record includes canonical table,
caption, row, stub, and value bounds; retained rule-level candidates with
references to individual unmerged source segments; adjacent row indices; rule
coverage; immediate font-change evidence; and review concerns. Repeated body
rule patterns remain available in `table_positioned_evidence` and are not
copied into this smaller proposal artifact.

The artifact also records the header/body and internal body/footer row edges
selected by `TableRegion` beside the retained alternatives. It does not judge a
selected edge unsupported merely because the compact proposal omitted that
candidate. Footer ownership itself is decided only by `TableRegion`.

A final retained rule may record
`following_text_line_ids`, `following_text_bbox`, and
`following_text_styles`. These fields reference the immediate, canonically
positioned adjacent band below the rule. Same-font continuation lines allow
font-size jitter of at most 0.2 PDF points. Known captions, later tables, and
section headings stop the band. The text remains uninterpreted. `TableRegion`
adds `body_footer` only after the unified typography, prose-continuity, and
preceding-data checks accept that exact band. External footnote harvesting can
consume it but cannot broaden or requalify it.

Each proposal also records `credible_rule_geometry` and
`coherent_positioned_grid`. The proposal is built before row-region ownership.
If both are false, `TableRegion` fails closed with empty header/body/footer
bands, and normalization preserves that decision rather than invoking its
standalone header detector. Selected region edges are attached to the proposal
afterward for inspection.

## Body Occupancy Diagnostic

After `TableRegion` has made the single footer-ownership decision,
`body_occupancy.json` records the selected body interval before normalization.
Each `BodyOccupancyTable` records the
canonical table-local x extent, a character-width-derived bin width, physical
body-line provenance and bounds, a raw binary line-by-bin matrix, per-bin line
counts and proportions, and exactly linked marker occurrences excluded from
the calculation. It also records the dominant body font and size, the median
observed space-glyph width for that style, whether that width came from the
table evidence or the paper-wide positioned document, and exact internal
zero-occupancy intervals at least two such spaces wide. Wrapped lines remain
distinct physical lines.

The artifact is evidence only. It does not smooth counts, fill gaps, choose
columns, alter `ExtractedTable`, or feed normalization or semantic parsing.
Qualified exact-gap counts may choose among already-proposed body intervals,
with the largest interval winning a tie. Marker exclusions require exact
`source_char_indices`; unmatched markers remain visible and are reported rather
than removed by proximity.

## Leaf-Column Candidate Diagnostic

`leaf_column_candidates.json` is built directly from `body_occupancy.json` and
the canonical unmerged rule segments referenced by `ExtractedTable`. Exact
character-box gaps with no ordinary body character are separator candidates
only when their width is at least twice the median observed space width for the
dominant table font and size. This avoids dependence on the arbitrary origin of
the diagnostic x bins. Separator midpoints define contiguous provisional band
extents, with the leftmost band identified as the stub candidate. Individual
horizontal-rule endpoints are attached only when they fall inside a separator.

The artifact does not use token starts, header text, expected column counts,
value syntax, or semantic vocabulary. It does not select or rewrite the
`ExtractedTable` grid and has no downstream consumer. A table with no complete
font-qualified zero-occupancy gap records
`no_qualified_zero_occupancy_column_separator` and emits no provisional grid
rather than receiving a guessed split.

## Header-Structure Candidate Diagnostic

`header_structure_candidates.json` normally aligns positioned header words
with the provisional leaf bands, with one preliminary leaf per occupancy band.
After canonical extraction, a complete flat header is preserved directly when
there is exactly one header row, every selected canonical column already has a
non-empty extracted cell, and the selected axis is supported by the local leaf
count. That row yields one evidence record and one leaf per canonical cell; it
is not regrouped by a word-height gap threshold.

Incomplete and multilevel headers retain the provisional path. Positioned
header runs attach to the band with greatest horizontal overlap; multiple runs
assigned to the same band are assembled in visual order. This lets fragments
such as `OR` and `95% CI` describe one leaf when body occupancy provides no
separator between them. The candidate also retains source text evidence,
multicolumn groups built from individual partial rules, explicit group-to-leaf
relationships, and wrapped fragments assembled only when horizontal overlap
and intervening-rule geometry support the join.

Header marker attachments record the marker ID, source evidence IDs, all
candidate leaf or group node IDs, an optional selected node, and a status of
`linked`, `ambiguous`, or `unresolved`. The parser does not fall back to the
same-row or nearest leaf when exact source-line and marker-bbox evidence cannot
identify one node. Leaf and group nodes expose `raw_text`, `base_text`, and
`marker_ids`; exact text alignment removes the linked occurrence from
`base_text`, while uncertain alignment retains it and adds a root candidate
concern.

Outside a complete flat canonical header, words from one intact header run
that cross candidate band boundaries are not divided. The artifact records
`header_evidence_words_cross_occupancy_bands` with the source evidence ID and
affected bands. A band without attached header text is also explicit. These
signals support later Phase F review but do not create, merge, or split leaves.

This artifact is diagnostic only. It is not consumed by `TableRegion`,
normalization, `ColumnHeaderSchema`, continuation resolution, or semantic
parsing.

## 3. `table_regions.json`

Current CLI path:

```text
outputs/papers/<paper_stem>/table_regions.json
```

This file is written by:

- `table1-parser parse`

Top-level shape:

```json
[
  {
    "...": "one TableRegion object"
  }
]
```

Canonical model:

- `TableRegion`
- child model: `TableRegionRow`

Design intent:

- persist structural region ownership anchored by body geometry before normalization
- distinguish page headers, table captions/titles, column-header bands, body
  rows, and footer/note bands as separate concepts
- use extracted table-entry geometry first: row bounds, cell boxes when row
  bounds are missing, horizontal rules, and full-width horizontal rules
- use extracted title/caption text only to validate rows already separated by
  geometry as caption candidates, not to repair normalized headers later
- provide a single source for downstream consumers that need table row
  ownership; normalization, column-header schema assembly, footnote harvesting,
  and continuation checks should not each rediscover those regions independently

Important fields:

- `caption_rows`, `preamble_rows`, `column_header_rows`, `body_rows`, and
  `footer_note_rows`: row-index lists in extracted-table row space
- `row_regions`: one role assignment per extracted row with detection basis and
  confidence
- `horizontal_rules` and `full_width_horizontal_rules`: rule evidence used by
  the region detector. `horizontal_rules` may include discontinuous same-y rule
  positions, while `full_width_horizontal_rules` is limited to continuous
  near-edge-to-near-edge rules.
- `diagnostics`: structured notes when rows are unassigned or fallback logic was
  needed

## 4. `NormalizedTable` JSON

Current status:

- canonical intermediate model
- written by the `normalize` CLI command as `normalized_tables.json`

Current CLI path:

```text
outputs/papers/<paper_stem>/normalized_tables.json
```

This file is written by:

- `table1-parser normalize`
- `table1-parser parse`

Top-level shape:

```json
[
  {
    "...": "one NormalizedTable object"
  }
]
```

The file is a direct serialization of:

- `NormalizedTable.model_dump(mode="json")`

Top-level design components:

- `table_id`, `title`, `caption`
- `header_rows`: row indices classified as header rows
- `body_rows`: row indices classified as body rows
- `row_views`: list of `RowView` objects for body rows
- `n_rows`, `n_cols`
- `metadata`

`RowView` design components:

- `row_idx`
- `raw_cells`
- `first_cell_raw`
- `first_cell_normalized`
- `first_cell_alpha_only`
- `nonempty_cell_count`
- `numeric_cell_count`
- `has_trailing_values`
- `indent_level`
- `likely_role`

Important current `metadata` keys produced by normalization:

- `source_page_num`
- `extraction_backend`
- `caption_source`
- `table_number`
- `is_continuation`
- `continuation_of_table_number`
- `table_numbering_audit`
- `cleaned_rows`
- `dropped_leading_cols`
- `dropped_trailing_cols`
- `source_col_indices`
- `column_repairs`
- `header_detection`
- `header_body_split_rule_comparison`
- `indentation_informative`
- `text_cleaning_provenance`

Design intent:

- normalization should add deterministic structure without losing raw text
- `cleaned_rows` may support later prompting and debugging, but raw cell text still lives in extraction output
- `row_views` are the compact per-row features that later heuristic and LLM stages consume
- saved normalized tables can be reloaded as formal downstream input
- `dropped_leading_cols` and `dropped_trailing_cols` remain zero-valued
  compatibility metadata; normalization no longer removes physical columns
- `source_col_indices` is the identity map from every normalized column to the
  same original extracted column
- when wide horizontal boundaries sit just slightly above or below the first
  extracted text line, `TableRegion` may still use them as the top table
  boundary; minor geometry jitter should not suppress obvious header/body
  bracketing
- header/body separation is selected once in `TableRegion`; normalization
  requires that artifact and copies its row ownership without inference
- when a value-region data anchor begins after several header-like rows,
  `TableRegion` may use that first value row as the header/body boundary and
  exclude a sparse leading caption or note tail from both selected row sets
- normalization does not drop sparse nonmatrix columns, trailing nondata
  columns, sparse structural stub columns, or split row-label field columns;
  those physical columns remain in the normalized grid
- normalization does not merge label-only continuation rows into valued rows. Wrapped body row labels are represented later as `body_row_label_candidates.json`, preserving source rows and cells.
- normalization does not merge split value fragments or synthesize visual value
  columns from newline-stacked cells; those relationships belong in body
  element candidates, parsed value components, or earlier extraction fixes
- normalization records a non-operative comparison of structural header/body
  evidence for inspection; it does not use that comparison to revise the
  `TableRegion` decision
- when full-width horizontal rules identify a header band, `metadata.header_detection` may record `preamble_rows` above that band and `separator_body_support` explaining whether the body starts with a value-dense row or with a sparse parent/reference row followed by value rows
- those repairs should be driven by row-style expectations and body-value patterns, not by paper-specific header templates
- normalization may also repair a small set of extractor-facing glyph-to-Unicode failures in parser-facing text, such as a broken replacement character before a numeric threshold becoming `<=`
- these symbol repairs belong in normalized text only; the original extracted cell text remains preserved in `ExtractedTable`
- these repairs are meant to recover known PDF-extractor symbol failures, not to infer a general source-file encoding
- `text_cleaning_provenance` should record table-level counts of comparator symbols that were observed directly in the surviving normalized grid versus reconstructed from known extractor glyph-failure rules

Conservative repair rule:

- when a value-region anchor provides the selected body boundary, normalization may treat the non-empty rows above that anchor as `header_rows`; sparse leading note/caption tails are kept in `cleaned_rows` for provenance but excluded from both header and body rows
- repair diagnostics should live in `metadata` rather than replacing the canonical `NormalizedTable` fields

## 4. `column_header_schemas.json`

Current status:

- canonical structural column-schema models exist now
- written by the `parse` CLI command
- consumed by deterministic `TableDefinition` column assembly

Current CLI path:

```text
outputs/papers/<paper_stem>/column_header_schemas.json
```

Top-level shape:

```json
[
  {
    "...": "one ColumnHeaderSchema object"
  }
]
```

Canonical model:

- `ColumnHeaderSchema`
- child models: `ColumnHeaderLeaf`, `ColumnHeaderGroup`,
  `ColumnHeaderRelationship`, `ColumnHeaderCellEvidence`

Design components:

- `leaves`
  record one parser-facing normalized column each, including the row-label
  column, leaf header label, body-row indices with non-empty cells, optional
  original column index, and optional coordinate summary
- `groups`
  record higher header labels spanning one or more leaf columns
- `relationships`
  record each group-to-leaf attachment explicitly
- `evidence`
  records normalized row/column references, raw extracted text when available,
  parser-facing cleaned text, page number, and cell bounding boxes when
  available
- `diagnostics`
  records degraded or missing evidence, skipped title-like header rows, blank
  leaf labels, and missing coordinate evidence

When normalized header rows are absent or title-like, the schema builder may
infer a header stack from the rows above the first strongly numeric body row.
This is still a column-schema computation: it preserves raw header-cell
evidence and records diagnostics rather than changing the normalized table.

Design intent:

- column-header recovery is a first-class parser artifact, not hidden inside
  `TableDefinition`
- leaf labels come from the header row closest to the body
- higher header rows become spanning groups with explicit relationships to leaf
  columns
- an internal horizontal rule within the header band may separate value-region
  spanning headers above the rule from wrapped leaf labels below it; the row
  label column may remain labeled above that rule and outside those value
  groups
- when a value-region group header is split into adjacent text fragments and
  omits the row-label column, cell geometry may split the group row at a large
  horizontal gap rather than forcing the fragments into one all-column label
- raw extracted cells and coordinates are preserved whenever they are available
- missing raw evidence is explicit rather than silently invented
- the schema can later support stored summary/tableone-style projection by
  providing a stable column axis before any print method renders a table

## 5. `resolved_tables.json`

Current status:

- canonical schema models exist now
- in-memory singleton/continuation-candidate resolver and column-gated
  integration exists now
- written by the `parse` CLI command
- consumed by `TableProfile`, `TableDefinition`, and `ParsedTable`
- `parsed_cell_values.json` remains source-fragment keyed and is joined to
  resolved parsed rows through `ResolvedRowProvenance`

Current CLI path:

```text
outputs/papers/<paper_stem>/resolved_tables.json
```

Top-level shape:

```json
{
  "source_artifact": "normalized_tables.json",
  "working_artifact": "resolved_tables.json",
  "resolved_tables": [],
  "decisions": [],
  "source_tables": [],
  "notes": []
}
```

Canonical model:

- `ResolvedTableSet`
- child models: `ResolvedTable`, `SourceTableResolution`,
  `TableResolutionDecision`, `ResolvedRowProvenance`, `IntegrationBoundary`,
  `DroppedSourceRow`, `ColumnSchemaCompatibilityDecision`

Design components:

- `source_artifact`
  records that `normalized_tables.json` remains the complete normalized source
  record
- `working_artifact`
  records the persisted resolved-table artifact name
- `resolved_tables`
  records the shorter semantic working set, including unchanged singleton
  tables and accepted integrated continuations
- `decisions`
  records why fragments were accepted, rejected, or passed through unchanged
- `source_tables`
  records one index entry per normalized source table, including whether a
  fragment became a singleton, base fragment, continuation fragment, or rejected
  continuation, with source page evidence when available
- `row_provenance`
  maps every retained resolved row back to source table ID, source table index,
  source row index, and source page when available
- `column_schema_decisions`
  records continuation compatibility decisions derived from
  `ColumnHeaderSchema`

Each `ResolvedTable` embeds one parser-facing `NormalizedTable` under its
`table` field. For a singleton, that embedded table is the source normalized
table. For an accepted continuation, the embedded table keeps the parent header
rows, appends accepted continuation body rows, records dropped continuation
header/non-body rows in `integration_boundaries`, and records every retained
row in `row_provenance`.

Artifact relationships:

- `normalized_tables.json` remains the full ordered source-fragment record.
- `column_header_schemas.json` remains source-fragment keyed. When semantic
  parsing consumes an integrated resolved table, the parser carries forward the
  accepted parent schema as the resolved column schema in memory.
- `parsed_cell_values.json` remains source-fragment keyed, because values are
  parsed from original normalized cells before semantic row joins.
- `parse_quality_reports.json` remains source-fragment keyed, because it
  diagnoses each normalized extraction/normalization result.
- `table_profiles.json`, `paper_table_inventory.json`,
  `table_definitions.json`, `parsed_tables.json`, and
  `table_processing_status.json` are resolved-table keyed.
- `table1_continuation_groups.json`, `merged_table1_tables.json`,
  `table_continuation_column_checks.json`, and
  `continued_variable_integrations.json` are source-fragment review artifacts.
  They do not feed canonical semantic parsing.

Design intent:

- insert a canonical working table set between normalization and semantic
  parsing for continued tables
- preserve `normalized_tables.json` unchanged as source evidence
- keep `parsed_cell_values.json` keyed to source normalized table fragments
  while joining semantic parsed values through resolved-row provenance
- require `ColumnHeaderSchema` as the column compatibility model
- treat existing continuation artifacts as review/provenance inputs or derived
  views, not as alternate semantic table lists
- fail closed by keeping rejected continuation fragments inspectable as
  singleton resolved tables with diagnostics
- avoid making R-side inspection objects the canonical continuation resolver

## 6. Table 1 Continuation Inspection Artifacts

Current status:

- canonical inspection schemas exist now
- written by the `parse` CLI command
- not consumed by the default `TableDefinition` or `ParsedTable` builders

Current CLI paths:

```text
outputs/papers/<paper_stem>/table1_continuation_groups.json
outputs/papers/<paper_stem>/table_continuation_column_checks.json
outputs/papers/<paper_stem>/merged_table1_tables.json
outputs/papers/<paper_stem>/continued_variable_integrations.json
```

Canonical structures:

- `Table1ContinuationGroup`
- child model: `Table1ContinuationMember`
- merged table artifact: `NormalizedTable`

Design components:

- `table1_continuation_groups.json`
  records explicit and strongly inferred Table 1 continuation candidates, their source table indices, source table IDs, schema-derived column headers, decision reasons, and merge/skip diagnostics
- `merged_table1_tables.json`
  records one merged `NormalizedTable` per accepted group, preserving normalized cleaned rows and source-row provenance in `metadata.table1_continuation_merge`
- `continued_variable_integrations.json`
  records one source-fragment review `TableDefinition` per compatible continuation group, preserving integrated variables, boundary decisions, row provenance, and tableone-style metadata in `metadata`; boundary decisions may reinterpret leading continuation body rows that were not standalone `DefinedVariable` records; this artifact is not a canonical semantic input

Design intent:

- handle explicit Table 1 continuation evidence, such as `Table 1 (continued)` or extractor continuation metadata for table number 1
- also inspect an uncaptained, unnumbered table-like fragment on the next page after Table 1 when it has body rows and a plausible grid
- require compatible schema-derived column headers before writing a merged table artifact
- ignore non-Table 1 continuations, including later result tables that happen to span pages
- preserve source table IDs and row indices so the merged view is auditable from the original `normalized_tables.json`
- keep the merged-row and integrated-variable artifacts as source-fragment review views now that `resolved_tables.json` is the semantic working set
- build `continued_variable_integrations.json` from source-fragment table definitions, not from resolved semantic table definitions, so it remains an auditable old-view artifact rather than a second semantic parse path

The merged normalized table keeps the base table rows and appends continuation body rows after dropping continuation-only header/title rows. Its row indices are local to the merged artifact, while provenance records map each merged row back to the original table ID and original row index.

### Demographic Continuation Column Checks

`table_continuation_column_checks.json` records explicit continuation fragments
whose parent or continuation has a descriptive source-table profile, including
tables whose logical Table 1-style content is not numbered as Table 1.
It also records uncaptained, unnumbered adjacent fragments when the closest
prior numbered fragment is demographic and the page order supports a
continuation candidate.

This artifact:

- requires clear continuation evidence or a narrow adjacent-page uncaptained continuation candidate before checking a pair
- compares the continuation to the closest prior fragment for the same table number
- records normalized column-count agreement
- records column-header agreement using `ColumnHeaderSchema`
- fails compatibility with a structured diagnostic when a usable column-header schema is missing, rather than reconstructing column meaning from normalized rows
- does not merge tables or change `TableDefinition`, `ParsedTable`, or processing-status behavior

The public helper can also consume paper-table taxonomy categories when they
are supplied, but the current `parse` CLI writes this source-fragment review
artifact using source-table profiles so it stays indexed to
`normalized_tables.json`.

## 7. `table_definitions.json`

Current status:

- canonical value-free semantic intermediate
- written by the `parse` CLI command

Current CLI path:

```text
outputs/papers/<paper_stem>/table_definitions.json
```

Top-level shape:

```json
[
  {
    "...": "one TableDefinition object"
  }
]
```

Canonical model:

- `TableDefinition`
- child models: `DefinedVariable`, `DefinedLevel`, `ColumnDefinition`, `DefinedColumn`

Top-level design components:

- `table_id`, `title`, `caption`
- `variables`
- `column_definition`
- `metadata`
- `notes`
- `overall_confidence`

`TableDefinition` column assembly now consumes `ColumnHeaderSchema` when that
artifact is available. It still owns semantic roles such as `overall`, `group`,
`p_value`, and `smd`; it no longer needs to recover the header tree directly
from normalized rows.

`ColumnDefinition.columns` contains semantic value/statistic columns and omits
the row-label column. `ColumnDefinition.header_spans` is a displayable header
projection and includes the row-label leaf span, so the full table header axis
can be rendered without reaching back into raw normalized header rows.

`DefinedVariable` design components:

- `variable_name`
- `variable_label`
- `variable_type`
- `row_start`, `row_end`
- `levels`
- `units_hint`
- `summary_style_hint`
- `confidence`

`DefinedLevel` design components:

- `level_name`
- `level_label`
- `row_idx`
- `confidence`

`ColumnDefinition` design components:

- `grouping_label`
- `grouping_name`
- `group_count`
- `columns`
- `header_spans`
- `confidence`

`DefinedColumn` design components:

- `col_idx`
- `column_name`
- `column_label`
- `header_leaf_id`
- `header_leaf_label`
- `header_group_ids`
- `header_group_labels`
- `header_path`
- `inferred_role`
- `grouping_variable_hint`
- `group_level_label`
- `group_level_name`
- `group_order`
- `statistic_subtype`
- `confidence`

Design intent:

- persist the row and column semantics needed for later SQL-query generation
- stay value-free so database-matching and query-building can happen before value parsing
- keep row and column references tied to the normalized table index space
- provide a deterministic baseline before optional LLM refinement is introduced
- keep `variable_name` search-oriented for variable rows, including stripping summary/unit decorations where useful
- keep `level_name` semantically distinct for categorical levels, preserving threshold and range syntax such as `< 1.3`, `1.3-1.8`, and `>1.8`
- model grouped columns explicitly enough to distinguish the overall population column, grouped data columns, and trailing statistic columns
- preserve grouped-column level labels and left-to-right order so downstream matching can reconstruct the table's column grouping structure
- keep multirow column headers structural: parent groups are stored in `header_spans`, per-column paths are stored in `header_path`, and `column_label` remains the leaf label instead of a fragile flattened header string

## 8. Paper Context Artifacts

Current status:

- written by the `parse` CLI command
- derived from one shared PyMuPDF positioned-text document pass, not from the
  table grid and not from a separate backend markdown path

Current CLI paths:

```text
outputs/papers/<paper_stem>/paper_positioned_document.json
outputs/papers/<paper_stem>/paper_document.json
outputs/papers/<paper_stem>/paper_markdown.md
outputs/papers/<paper_stem>/paper_sections.json
outputs/papers/<paper_stem>/paper_table_mentions.json
outputs/papers/<paper_stem>/paper_bibliography.json
outputs/papers/<paper_stem>/paper_style_profile.json
outputs/papers/<paper_stem>/paper_visual_inventory.json
outputs/papers/<paper_stem>/paper_references.json
outputs/papers/<paper_stem>/paper_variable_inventory.json
outputs/papers/<paper_stem>/table_contexts/table_<n>_context.json
```

Canonical structures:

- `PaperPositionedDocument`
- child models: `PaperPositionedPage`, `PaperPositionedLine`,
  `PaperPositionedSpan`, `PaperPositionedVisualComponent`
- `PaperDocument` declarative artifact shape; its initial implementation is a
  plain projection rather than a new model hierarchy
- `PaperSection`
- `PaperTableMention`
- `PaperBibliography`
- child models: `BibliographyEntry`, `BibliographyReferenceMention`
- `PaperStyleProfile`
- child models: `PaperStyleDimension`, `PaperStyleCheck`, `PaperStyleEvidence`
- `PaperVisual`
- `PaperVisualReference`
- `PaperVariableInventory`
- child models: `VariableMention`, `VariableCandidate`
- `TableContext`
- child model: `RetrievedPassage`

Design components:

- `paper_positioned_document.json`
  shared whole-paper PyMuPDF positioned text pass with page sizes, visual lines,
  span text, bboxes, font names, font sizes, flags, line direction/orientation,
  words, characters, horizontal rule segments, compact raster/vector visual
  components, and raw/cleaned text. Visual components preserve only stable ID,
  kind, page-space bbox, source index, optional nesting level, and optional
  drawing-sequence range; they do not classify figures. The extended drawing
  hierarchy supplies visual-component evidence only. `rule_segments` and
  `stroked_rule_segments` continue to consume the ordinary `get_drawings()`
  records; extended clip, group, and separately exposed nested records do not
  enter either rule projection. A line's
  `has_bold` field records only that at least one source span is bold; it is not
  a line-wide style classification and does not make the line a heading or a
  table caption. Downstream
  paper-context, extraction, and annotation stages should consume this artifact
  or a typed projection of it instead of reopening the PDF for another
  positioned-geometry pass.
- `paper_document.json`
  canonical ownership projection over the existing filtered block registry. It
  preserves block geometry and source identity, orders current prose candidates
  as segments and paragraphs, owns established bibliography and figure blocks
  through entities, and assigns all other blocks to `unassigned_block_ids`.
  Each populated orientation group also
  carries block-layout evidence: `layout_kind`, ordered
  `layout_regions`, exact positive `candidate_gutters`, leaf-column track bboxes,
  region-level `block_placements`, and `layout_diagnostics`. Exact block top
  and bottom events establish atomic vertical intervals. Gutters persist by
  positive x-intersection, become dormant under one-sided occupancy, and may
  refine one lane without ending a region when another track persists. A block
  crossing a gutter receives a spanning placement instead of suppressing that
  gutter globally. Layout input contains every ordinary block plus one opaque
  composite-bbox unit for each accepted figure; figure-member blocks remain in
  the registry but do not participate independently. Every placement records
  one ordinary block or figure entity ID plus its inclusive start and exclusive
  end column, and placements are ordered by start column, canonical top, and
  source order. A region transition occurs only when all established tracks
  close, and it never cuts a structural unit. `layout_kind` follows the actual
  region/column shape mechanically; `empty` identifies an orientation group
  whose retained text blocks are all hidden members of a figure placed in
  another group. The flattened placements define the ordinary-block order
  presented to first-pass prose identification; figure units are skipped
  without inspecting their components.
  Accepted figure scopes are canonical `figure` entities. Each records the
  explicit figure label, ordered caption block IDs, bound above-caption
  raster/vector component references, assigned internal block IDs, exact
  component-union bbox, and exact figure-plus-caption composite bbox.
  Binding requires positive horizontal overlap and no competing caption claim.
  Internal blocks require positive page-space intersection with the exact
  component/caption envelope; no drawing sequence, extraction order, page-width
  threshold, or overlap percentage participates. `structure` contains one
  two-field record for every page: its page number and ordered structural-unit
  IDs. Those IDs exactly flatten the page's existing orientation-group order,
  layout-region order, and ordered placements. It exposes each figure entity
  exactly once and does not expose its caption or internal blocks independently.
  The source block and positioned-evidence registries remain unchanged.
  Rejected detections alone remain in
  `figure_scope_rejections`. Gutter and block-layout evidence consumes each
  accepted figure as one opaque entity bbox.
  `bibliography_region_candidates` is another non-operative view over the same
  registry. Each candidate stores an explicit heading line/block, the ordered
  block IDs downstream from that heading in block-layout order, prose-conflict
  block IDs, and structural evidence. It changes no ownership or extraction
  mask. The operative per-heading item walk consumes those ordered ordinary
  blocks, records numbered, current unnumbered, and accepted indentation-
  continuation line evidence, and stops at the first unsupported block.
  Accepted blocks become bibliography entity components, and masks derive from
  that ownership. Retired B3/B4 comparison fields are not persisted. The
  legacy page-wide column metadata remains classification evidence. Steps 4–5
  present the same ordered ordinary blocks to the established prose and
  bibliography rules. Bibliography heading discovery, numbered starts,
  continuation evidence, and the retained unnumbered route skip figure units
  and no longer receive a competing global line or registry-block order. Item,
  ownership, and extraction-mask rules are unchanged. Its prose segments directly supply the
  persisted section and Markdown views. Prose ownership is derived only from upright
  source continuity, observed column extent, one font name with a
  largest-minus-smallest line font-size span below 0.5, sentence evidence,
  confirmed headings, and unfinished prose crossing a page, column, or observed
  spanning-layout boundary. An already-marked full-width block is treated as
  spanning but cannot independently establish paragraph evidence; one spanning
  residual block may sit between unfinished accepted prose and its continuation.
  Arbitrary body blocks are not promoted into headings, and opaque font names
  are not interpreted. The
  descriptive `has_bold_text` note never assigns a heading role or qualifies a
  caption candidate. A heading requires every visible line span to be bold and
  a font strictly larger than the dominant paper body font. Entirely bold source
  blocks containing completed sentence prose are excluded, and no heading-name
  vocabulary participates in general heading detection. Exact whole-line
  bibliography parser does not promote heading roles or split blocks. Ordinary
  prose input blocks are ordered by page, orientation group, layout region,
  start column, canonical top, and retained source order; their lines retain
  source order. Contextual adjacency cannot cross page or orientation-group
  boundaries.
- `paper_markdown.md`
  prose-only Markdown view rendered from the headings and paragraphs in
  `PaperDocument.prose.segments`; there is no second inference path or
  `pymupdf4llm.to_markdown()` fallback
- `paper_sections.json`
  exact JSON view of `PaperDocument.prose.segments`, preserving ordered heading
  block IDs and paragraph IDs, block IDs, and text without separate role
  inference
- `paper_table_mentions.json`
  pre-extraction table mention records derived from `PaperDocument` blocks
  joined to positioned lines,
  including whether each `Table N` line is likely a caption candidate,
  continuation label, or prose reference, with the source line ID and bbox.
  Extraction consumes this artifact and rejects proposed caption lines by bbox
  overlap, so a prose sentence split across lines, such as `is shown in`
  followed by `Table 5.`, cannot seed a text-position table candidate even when
  raw and normalized glyph representations differ.

The positioned document, orientation-aware text stream, extracted tables,
normalized tables, and resolved continuation set are cumulative artifacts.
Canonical orientation is a derived coordinate projection, not a rewrite of raw
PDF geometry or extracted cell text. R consumers should retain raw
positioned/extracted records alongside normalized and continuation-resolved
views.
- `paper_bibliography.json`
  per-paper bibliography entries extracted from the positioned text stream
  before table extraction, plus table-cell numeric reference markers linked to
  those entries after cell-text annotations are available
- `paper_style_profile.json`
  per-paper style summary built from existing text, footnote, bibliography,
  visual-inventory, and visual-reference artifacts; this records likely marker,
  reference-list, caption, and table/figure mention conventions as counts and
  examples for review, plus consistency checks such as numbered-bibliography
  alignment
- `paper_visual_inventory.json`
  paper-level inventory of actual in-paper tables and figure captions, keyed by
  stable visual IDs such as `paper_visual:table:1`, with optional canonical
  `doi` and positioned `doi_source_line_id` fields and reference-check status
  fields showing whether the visual has at least one non-self text reference
- `paper_references.json`
  prose mentions of tables and figures, anchored to section/paragraph/character positions and resolved against the visual inventory when possible
- `paper_variable_inventory.json`
  paper-level variable-search artifact with broad mention-level records and a stricter consolidated candidate-variable list
- `table_contexts/*.json`
  per-table retrieval bundles keyed by `table_id` and internal extraction-order `table_index`; R-facing inspection should resolve these by the paper's `table_number` where available

`TableContext` design components:

- `table_id`, internal `table_index`, `table_label`
- `title`, `caption`
- `row_terms`
- `column_terms`
- `grouping_terms`
- `methods_like_section_ids`
- `results_like_section_ids`
- `reference_ids`
- `resolved_visual_ids`
- `passages`

`RetrievedPassage` design components:

- `passage_id`
- `section_id`
- `heading`
- `text`
- `match_type`
- `score`

Design intent:

- keep paper-level context in the same per-paper output directory
- keep the candidate variable reference list explicit and easy to load in both Python and R
- preserve a distinction between broad harvested mentions and the narrower promoted candidate list
- support future LLM semantic interpretation with compact retrieved evidence
- help readers distinguish references to actual in-paper tables and figures from unresolved or bibliographic mentions
- avoid tying retrieval to exact section names like `Methods`
- preserve `paper_markdown.md` and `paper_sections.json` as exact prose views
  over `PaperDocument.prose`
- preserve a JSON-first, inspectable context path alongside the table path

Variation note:

- papers may use different section names, heading levels, and table-reference styles
- that variation should be handled in section parsing and retrieval, not by
  introducing a second markdown extraction path
- `docs/design/paper_markdown_spec.md` is the design reference for this artifact

## 9. `table_variable_plausibility_llm.json`

Current status:

- written by `review-variable-plausibility` when LLM configuration is available
- deterministic `parse` never writes this file
- written as an empty list when the review command runs but no tables are eligible or no review result is returned

Current CLI path:

```text
outputs/papers/<paper_stem>/table_variable_plausibility_llm.json
```

Canonical model:

- `LLMVariablePlausibilityTableReview`

Top-level shape:

```json
[
  {
    "...": "one LLMVariablePlausibilityTableReview object"
  }
]
```

Design components:

- `table_id`
- `variables`
- `notes`
- `overall_plausibility`

Design intent:

- preserve `table_definitions.json` as the deterministic baseline artifact
- keep the LLM review narrow and table-local
- preserve each supplied variable identity exactly and add `plausibility_score`
- validate the LLM output before writing this file
- keep this review separate from deterministic parse outputs so it cannot silently rewrite them

Debug-only companion artifacts:

- when `LLM_DEBUG=true`, `review-variable-plausibility` also writes a timestamped debug run under:

```text
outputs/papers/<paper_stem>/llm_variable_plausibility_debug/<timestamp>/
  llm_variable_plausibility_monitoring.json
  table_0/
    variable_plausibility_llm_input.json
    variable_plausibility_llm_metrics.json
    variable_plausibility_llm_output.json
    variable_plausibility_llm_review.json
```

- `llm_variable_plausibility_monitoring.json` summarizes every table's review status, including skipped-not-eligible tables
- per-table trace files are written only for tables that actually reached the provider call path

## 10. Variable-Plausibility Debug Trace Files

Current status:

- written only when `LLM_DEBUG=true`
- debug artifacts, not stable downstream interfaces

Current per-table file names:

- `variable_plausibility_llm_input.json`
- `variable_plausibility_llm_metrics.json`
- `variable_plausibility_llm_output.json`
- `variable_plausibility_llm_review.json`

Current top-level wrappers:

```json
{
  "report_timestamp": "...",
  "table_id": "...",
  "payload": {
    "...": "variable-plausibility LLM prompt payload"
  }
}
```

```json
{
  "table_id": "...",
  "status": "success",
  "elapsed_seconds": 1.23
}
```

```json
{
  "report_timestamp": "...",
  "table_id": "...",
  "response": {
    "...": "raw structured LLM response"
  }
}
```

```json
{
  "report_timestamp": "...",
  "table_id": "...",
  "review": {
    "...": "LLMVariablePlausibilityTableReview"
  }
}
```

Design intent:

- preserve the exact review payload, monitoring metrics, raw provider output, and validated review for inspection
- keep these files separate from canonical pipeline outputs such as `table_definitions.json`, `table_variable_plausibility_llm.json`, and `parsed_tables.json`
- preserve stable variable identity fields so disagreements can be audited safely
- keep the prompt payload compact; the saved input wrapper currently uses short payload keys such as `table` and `vars`

## 11. `body_element_candidates.json`

Current status:

- canonical candidate schema exists now
- written by the `parse` CLI command as `body_element_candidates.json`

This artifact records logical body-value candidates after `ColumnHeaderSchema`
has settled the column leaves and value columns. It does not rewrite
`ExtractedTable` or `NormalizedTable`.

Current CLI path:

```text
outputs/papers/<paper_stem>/body_element_candidates.json
```

This file is written by:

- `table1-parser parse`

Top-level record design components:

- `candidate_id`
- `source_table_index`
- `source_table_id`
- `anchor_row_idx`
- `anchor_col_idx`
- `kind`
- `candidate_text`
- `raw_text`
- `base_text`
- `marker_ids`
- `raw_fragments`
- `source_cells`
- `reason`
- `confidence`
- `notes`

`source_cells` design components:

- `source_table_index`
- `source_table_id`
- `row_idx`
- `col_idx`
- `original_row_idx`
- `original_col_idx`
- `text`
- `cleaned_text`
- `bbox`
- `page_num`

Initial candidate kinds include:

- `single_cell`
- `same_column_vertical_continuation`
- `row_sequence_reconstruction`

Design rules:

- build candidates only after the column grid is available from
  `ColumnHeaderSchema`
- keep every candidate traceable to one or more physical source cells
- take `source_cells[*].text`, `raw_fragments`, and `raw_text` from the exact
  matching `ExtractedTable` cell text rather than normalized cleaned rows
- allow one source cell to contribute to adjacent candidates when a PDF row
  prints the tail of one value and the start of the next value in the same
  physical cell
- do not use candidate reconstruction to assign physical columns, physical
  rows, or cell bounding boxes
- attach an occurrence only through its stable physical source-cell ID and
  only when that source cell belongs to one logical candidate
- use marker-free `base_text`/`candidate_text` for value-component parsing,
  while preserving `raw_text`, `raw_fragments`, and `source_cells` for
  inspection
- join `anchor_col_idx` to the projected schema leaf; final semantic values
  obtain the leaf ID, groups, and header path from that schema column rather
  than duplicating those fields in this candidate artifact

### `body_row_label_candidates.json`

Current status:

- canonical candidate schema exists now
- written by the `parse` CLI command as `body_row_label_candidates.json`

This sibling artifact records logical body row-label candidates after
`ColumnHeaderSchema` has settled row-label and value columns. It does not
rewrite `ExtractedTable` or `NormalizedTable`; it gives row classification and
`TableDefinition` a candidate label assembled from adjacent physical source
rows.

Current CLI path:

```text
outputs/papers/<paper_stem>/body_row_label_candidates.json
```

Top-level record design components:

- `candidate_id`
- `source_table_index`
- `source_table_id`
- `anchor_row_idx`
- `anchor_col_idx`
- `kind`
- `candidate_label`
- `raw_text`
- `base_text`
- `marker_ids`
- `raw_fragments`
- `source_cells`
- `continuation_row_indices`
- `reason`
- `confidence`
- `notes`

Initial candidate kind:

- `vertical_label_continuation`

Design rules:

- build candidates only after the column grid is available from
  `ColumnHeaderSchema`
- require adjacent body rows, an anchor row with values, continuation rows with
  label-column text, and empty value columns in those continuation rows
- keep every candidate traceable to one or more physical source cells
- attach markers only after the vertical label candidate exists; ordinary
  single-row labels remain linked only to their physical cells until they have
  a logical candidate
- do not use label reconstruction to assign physical columns, physical rows, or
  cell bounding boxes

## 12. `parsed_cell_values.json`

Current status:

- canonical component schema exists now
- written by the `parse` CLI command as `parsed_cell_values.json`

This artifact records parsed source-cell value components before row and column
semantics are joined onto those values. It is intentionally index-keyed rather
than semantic-label-keyed.

For candidate-derived records, component parsing consumes the candidate's
marker-free `base_text`, while `raw_value` preserves the candidate's unchanged
`raw_text`. Residual glyphs retained for lack of distinct occurrence evidence
remain visible in `base_text` and in the candidate's diagnostics.

Current CLI path:

```text
outputs/papers/<paper_stem>/parsed_cell_values.json
```

This file is written by:

- `table1-parser parse`

Top-level record design components:

- `source_table_index`
- `source_table_id`
- `row_idx`
- `col_idx`
- `raw_value`
- `element_candidate_id`
- `raw_fragments`
- `source_cells`
- `parse_pattern`
- `components`
- `confidence`
- `notes`

`components` design components:

- `kind`
- `value`
- `raw_fragment`
- `relation`
- `confidence`
- `notes`

Initial component kinds include:

- `count`
- `percent`
- `mean`
- `sd`
- `median`
- `q1`
- `q3`
- `min`
- `max`
- `estimate`
- `se`
- `p_value`
- `missing`
- `text`
- `unknown`

Design rules:

- preserve `raw_value` as the parser-facing value string that was parsed; for
  multi-cell body element candidates, preserve the printed source fragments in
  `raw_fragments` and `source_cells`
- use parser-facing cleaned text only for matching and numeric extraction
- do not duplicate variable names, level labels, column names, or header paths
  in this artifact
- select source cells from normalized body rows and schema-derived value columns
  when `ColumnHeaderSchema` is available
- keep ambiguous shapes such as `x (y)` conservative until later semantic
  context can distinguish `mean` plus `sd` from `estimate` plus `se`
- rely on the canonical typed schema for field shape and controlled component
  kinds;
  do not introduce a separate validation-report artifact until known failure
  modes justify it

This artifact is a source component layer. `ParsedTable.values` is the joined
semantic view over these components and continues to be written to
`parsed_tables.json`.

## 12. `ParsedTable` JSON

Current status:

- canonical final schema exists now
- written by the `parse` CLI command as `parsed_tables.json`

This should be treated as the main downstream table representation.

Current CLI path:

```text
outputs/papers/<paper_stem>/parsed_tables.json
```

This file is written by:

- `table1-parser parse`

Top-level design components:

- `table_id`
- `title`
- `caption`
- `variables`
- `columns`
- `values`
- `notes`
- `overall_confidence`

`variables` design components:

- `variable_name`
- `variable_label`
- `variable_type`
- `row_start`
- `row_end`
- `levels`
- `confidence`

`columns` design components:

- `col_idx`
- `column_name`
- `column_label`
- `inferred_role`
- `confidence`

`values` design components:

- `source_table_index`
- `source_table_id`
- `row_idx`
- `col_idx`
- `variable_name`
- `variable_label`
- `level_label`
- `column_name`
- `column_label`
- `header_leaf_id`
- `header_leaf_label`
- `header_group_ids`
- `header_group_labels`
- `header_path`
- `raw_value`
- `parse_pattern`
- `components`
- `confidence`
- `notes`

The canonical value payload is `components`. Each component preserves a typed
piece of the printed value such as `count`, `percent`, `mean`, `sd`,
`estimate`, `se`, `median`, `q1`, `q3`, `p_value`, `missing`, `text`, or
`unknown`. The semantic value layer may refine ambiguous source components
using `TableDefinition` context; for example, a source `estimate` plus
ambiguous uncertainty component can become semantic `mean` plus `sd` when the
variable has a `mean_sd` summary hint.

No scalar compatibility aliases are included in the canonical value record.
Consumers should read `components` directly rather than expecting fields such
as `value_type`, `parsed_numeric`, or `parsed_secondary_numeric`.

Why `values` are long-format:

- one row per table cell is easier to validate
- it supports downstream filtering and export
- it joins semantic row/column interpretation to source-cell component parsing
- it preserves the original `raw_value`

Design note for future value parsing:

- parser-facing symbol canonicalization should be applied internally before regex matching and numeric parsing
- canonicalization must not replace the stored `raw_value`
- current parser-facing matching treats a spaced numeric `6` between two numeric tokens as a PDF-extracted plus/minus glyph for uncertainty components, while preserving the original `raw_value`
- for Table 1 categorical `n (%)` cells, the intended first interpretation is:
  - component `count` = count
  - component `percent` = percent
- count-percent consistency checks should be soft heuristics, not hard validity requirements
- count-percent consistency checks should operate on `components`
- the overall-column 100% rule should be limited to columns that are truly `overall` or clearly equivalent, while subgroup columns may legitimately sum to their share of the full study population instead of 100

This is the richest JSON design in the repo because it joins variable semantics, column semantics, and cell-level values into one validated representation.

## 13. `table_processing_status.json`

Current status:

- canonical status schema exists now
- written by the `parse` CLI command as `table_processing_status.json`

Current CLI path:

```text
outputs/papers/<paper_stem>/table_processing_status.json
```

This file is written by:

- `table1-parser parse`

Top-level design components:

- `table_id`
- `source_table_ids`
- `status`
- `failure_stage`
- `failure_reason`
- `attempts`
- `source_fragment_diagnostics`
- `notes`

`attempts` design components:

- `stage`
- `name`
- `considered`
- `ran`
- `succeeded`
- `note`

Design intent:

- key status records to the resolved semantic table IDs written in `table_definitions.json` and `parsed_tables.json`
- preserve source-fragment IDs and source-fragment diagnostics so integrated continuations remain auditable against `normalized_tables.json` and `parse_quality_reports.json`
- record which existing rescue and repair paths were considered
- record which ones actually ran
- record whether a table ended as `ok`, `rescued`, or `failed`
- make empty descriptive-table parses explicit failures rather than silent success
- do not label a structurally matrix-like real table as a non-table artifact
  solely because the current Table 1 semantic parser cannot infer variables;
  preserve it with an explicit unsupported-route note and let
  `paper_table_inventory.json` categorize it as `data_presentation` when the
  broader taxonomy evidence supports that category

## 14. `parse_quality_reports.json`

Current status:

- canonical diagnostic schema exists now
- written by the `parse` CLI command as `parse_quality_reports.json`
- inspection artifact only; it does not alter table definitions or parsed tables

Current CLI path:

```text
outputs/papers/<paper_stem>/parse_quality_reports.json
```

Canonical model:

- `ParseQualityReport`
- child models: `ParseQualitySummary`, `DiagnosticItem`

Top-level design components:

- `table_id`
- `summary`
- `table_diagnostics`
- `row_diagnostics`
- `column_diagnostics`

Design intent:

- expose deterministic quality signals for every normalized table considered by `parse`
- make column-determination problems inspectable, including weak p-value columns, mostly empty columns, and group/overall columns with low value-pattern recognition
- report header/body split disagreements when both structural candidates exist and choose different body starts; suppress this warning when the horizontal-rule body start only precedes the first value row by expected variable/section-header rows with no recognized value pattern, and keep the full candidate details in `normalized_tables.json`
- keep softer quality warnings separate from `table_processing_status.json`, which records coarse pass/fail outcomes and rescue attempts
- preserve parse behavior: warnings and errors in this artifact do not halt parsing and do not rewrite `table_definitions.json` or `parsed_tables.json`
- keep obvious non-table layout artifacts from reaching semantic parsing: early extraction guards suppress reference-section, front-matter, and weak source-order-impossible pseudo-tables, while `table_processing_status.json` remains responsible for failed candidates that survive extraction but cannot support a known table route
- support R-side inspection and corpus review before making higher-risk changes such as consolidated Table 1 parsing
- treat representative real-paper parsing checks as an important complement to unit tests, because deterministic table heuristics often fail on structural variants that synthetic tests do not cover

## 15. `paper_table_inventory.json`

Current status:

- canonical paper-level taxonomy schema exists now
- written by the `parse` CLI command as `paper_table_inventory.json`
- inspection and routing-support artifact only; it does not alter table definitions or parsed tables

Current CLI path:

```text
outputs/papers/<paper_stem>/paper_table_inventory.json
```

Canonical models:

- `PaperTableInventory`
- child model: `PaperTableRecord`

Top-level design components:

- `paper_id`
- `tables`

Each table record contains:

- `table_id`
- `table_number`
- `table_category`
- `category_confidence`
- `category_evidence`
- `continuation_of_table_number`
- `table_family`
- `processing_status`
- `failure_reason`
- `title`
- `caption`

Allowed `table_category` values:

- `demographic_description`
- `analysis_outputs`
- `data_presentation`
- `general`
- `unknown`
- `non_table_artifact`

Design intent:

- use the paper's table number as the public conceptual identifier where available
- keep continuation as `continuation_of_table_number`, with `null` when the table is not a continuation
- choose only one max-score category and persist only the chosen category, confidence, and evidence
- prioritize effect or estimate columns for `analysis_outputs`; p-values and model labels alone should not override a demographic-description classification
- recognize wide numeric matrices with threshold/statistic headers as `data_presentation`, especially when normalization has already expanded an extra-wide value column into visual value columns
- treat `table_category` as the broader concept that should drive parser-route selection once it is available; current `table_family` output is an earlier provisional route signal, not an independent semantic category
- keep this artifact deterministic and computable so R can expose it as a data frame or print method later

## 16. `paper_page_furniture.json`

Current status:

- canonical paper-level page-furniture schema exists now
- written by the `parse` CLI command as `paper_page_furniture.json`
- built before paper context parsing, table extraction, cell text annotation,
  and document-linked footer detection
- passed to positioned-text consumers as page-coordinate ignored regions before
  they group, classify, or persist downstream artifacts

Current CLI path:

```text
outputs/papers/<paper_stem>/paper_page_furniture.json
```

Canonical model:

- `PaperPageFurniture`
- child models: `PageFurnitureTextObservation`, `PageFurnitureCluster`, `PageFurnitureRegion`

Top-level design components:

- `paper_id`
- `source_pdf`
- `observations`
- `clusters`
- `ignored_regions`
- `metadata`

Design intent:

- record repeated page text using normalized text plus stable page-relative position
- preserve raw page text in observations
- store generic ignored regions without classifying them as header, footer, watermark, or boilerplate
- expose thresholds and diagnostics in `metadata`
- provide extraction, cell-text annotation, and footer-detection code with
  page regions to suppress

## Trace Wrappers vs Canonical Payloads

A simple rule:

- wrapper files are for debugging and auditability
- canonical payloads are for stable programmatic interfaces

Wrapper files currently include:

- `variable_plausibility_llm_input.json`
- `variable_plausibility_llm_metrics.json`
- `variable_plausibility_llm_output.json`
- `variable_plausibility_llm_review.json`

Canonical payloads currently include:

- `ExtractedTable`
- `NormalizedTable`
- `Table1ContinuationGroup`
- `TableDefinition`
- `LLMVariablePlausibilityTableReview`
- `ParsedTable`

The final parse/export path should prefer canonical model dumps, with wrapper files used only when explicit trace/debug output is wanted.

## Controlled Vocabularies and Current Gaps

Several fields use constrained string vocabularies rather than free text.

Current canonical examples:

- `ParsedVariable.variable_type`: `continuous`, `categorical`, `binary`, `unknown`
- `ParsedColumn.inferred_role`: `group`, `overall`, `p_value`, `statistic`, `unknown`
- `RowView.likely_role`: `header`, `variable`, `level`, `statistic`, `note`, `unknown`

There is one important stage-to-stage mismatch in the current repository:

- heuristic column-role guesses support `comparison_group` and `smd`
- the current LLM interpretation and final `ParsedColumn` schema do not expose those labels directly

That means developers should not assume every heuristic enum value maps 1:1 into the final parsed schema. If this area is expanded later, it should be done deliberately and across all affected schemas and docs together.

## Recommended Rules for Future JSON Design

When adding or revising output files:

- keep one pipeline stage per JSON artifact
- do not merge extraction, normalization, heuristics, and final parsed output into one catch-all object
- preserve raw text and stable row/column coordinates
- keep core semantic fields explicit and stable
- reserve `metadata` for backend-specific or stage-specific extensions
- prefer typed arrays of records over free-form nested dictionaries
- make timestamps and trace metadata wrapper-level concerns, not core schema fields
- distinguish clearly between inspection artifacts and downstream analysis artifacts

## Related but Separate JSON: Synthetic Truth Files

The synthetic generator writes `*_truth.json` files through `table1_parser.synthetic.truth_writer`.

Those files are evaluation artifacts, not parser runtime outputs. Their top-level design is different because they store synthetic ground truth for testing, including:

- `document_title`
- `table_caption`
- `columns`
- `header_rows`
- `rows`
- `variables`
- `value_records`
- `layout_features`

They are useful as reference material for expected parsed structure, but they should not be confused with the runtime parse/export contract.
