# Parser ToDo

This is the persistent implementation ToDo list for parser work. Agents should check it before changing extraction, normalization, row/column semantics, table routing, value parsing, diagnostics, or R inspection helpers. Update it when a task is completed, reprioritized, split, or superseded.

Keep detailed implementation notes and epidemiology-table reasoning here or in linked implementation documents. Keep high-level design docs focused on stable pipeline shape, schemas, persisted artifact contracts, and durable architecture decisions.

## Current Priorities

Current corpus-driven hardening guide:
`docs/implementation/real_paper_testing_guide.md`. Use it for the ordered
real-paper review loop across extraction, normalization, continuation handling,
table semantics, footnote/reference artifacts, and mixed-family routing. The
current retained reference run is `outputs/testpapers_batch_20260708_header_group_upstream_fix`.

Fallback/removal inventory:
`docs/implementation/fallback_inventory.md`. Do not add new fallback tools or
downstream repair layers to compensate for weak extraction. Prefer fixing
positioned extraction, caption/table-region ownership, page-furniture filtering,
and explicit schema artifacts; fail closed with diagnostics when geometry is
insufficient.

1. [x] Add a parser-native column header schema artifact.
   Build `ColumnHeaderSchema` between `NormalizedTable` and `TableDefinition` so leaf columns, higher spanning header groups, group-to-leaf relationships, raw cell evidence, and coordinates are explicit before any tableone-style projection.
   Design note: `docs/design/column_header_schema.md`.
   Implementation plan: `docs/implementation/column_header_schema_implementation_plan.md`.
   This should become the primary column model consumed by `TableDefinition` and any later stored summary/tableone projection; continuation compatibility is an important later consumer, but not the main design driver.
   Initial implementation is in place: `table1-parser parse` writes `column_header_schemas.json`, `TableDefinition` consumes it, continuation checks use schema-derived column headers, and tests cover Eke-like Table 1/Table 2 structures plus non-problem tables.
   Follow-up: Eke Tables 1-2 show that multi-line header stacks can produce wrong parent paths when rule-banded header rows are extracted as many short text fragments. The current parser now repairs obvious split estimate/uncertainty value columns, drops sparse non-matrix page-text columns and empty separator columns, removes tall/narrow numeric margin text before grid construction, keeps adjacent header text runs together, only merges wrapped leaf rows after geometry-based header inference, preserves normalized-to-original column identity in `source_col_indices`, moves short leading leaf fragments across adjacent column boundaries when structural or coordinate evidence supports it, trims sparse group rows out of the leaf-header stack, and persists `TableDefinition.column_definition.header_spans` plus per-column `header_path` so JSON no longer relies on flattened multirow labels. Remaining work should expose ambiguous leaf-band fragment assignments as structured candidates that deterministic code or later LLM inference can adjudicate; do not hard-code paper-specific vocabulary.

2. [ ] Make continuations semantically real.
   One logical Table 1 spanning pages should feed `TableDefinition` and `ParsedTable`, rather than leaving page-level and continuation-page parses as separate semantic outputs.
   Design note: `docs/design/table_continuation_resolution.md`.
   Variable integration design: `docs/design/separated_variable_description_integration.md`.
   Implementation spec: `docs/implementation/continued_variable_integration_implementation_spec.md`.
   First diagnostic step implemented: `table_continuation_column_checks.json` checks explicit and narrow inferred uncaptained adjacent-page `demographic_description` continuations for column count and schema-derived column-header compatibility without changing parser inputs. `table1_continuation_groups.json` can also report an uncaptained next-page Table 1 fragment, but merged artifacts are still inspection-only and are skipped when normalized columns or schema-derived column headers are incompatible.
   Continued-variable integration now writes `continued_variable_integrations.json` as a source-fragment inspection artifact made of existing `TableDefinition` objects with integrated `DefinedVariable` records plus integration provenance and tableone-style metadata. Canonical semantic continuation handling now goes through `resolved_tables.json`.
   Boundary handling now preserves and reinterprets leading continuation body rows before the first standalone continuation variable, so body rows that are ambiguous without the prior fragment can still attach as levels when compatible column and parent-variable context supports it.
   Follow-up: Planetary Health Table 1 now integrates p2-t0 and p3-t0 as one resolved Table 1. The shared PyMuPDF word/rule header-span repair keeps sparse upper group headers as spanning cells while preserving dense repeated leaf headers, so both fragments expose the same visible 9-column header structure before `ColumnHeaderSchema` comparison. The current upstream header-grid rule derives spanning-group evidence from word start columns, not glyph right edges, and requires ordered non-overlapping spans; this preserves tight wrapped leaf headers such as periodontitis p6-t0. Merged continuation artifacts remain source-fragment review views; canonical semantic parsing consumes `resolved_tables.json`.
   Current implementation checklist: `docs/implementation/project_completion_priorities_draft.md`.
   Resolved-table design contract G1.1-G1.5 is in place: `ResolvedTableSet` and child Pydantic models define `resolved_tables.json`, `normalized_tables.json` remains the full source record, and current continuation artifacts are documented as review/provenance inputs or derived views.
   Initial resolver G1.6 is in place: `build_resolved_table_set()` consumes all normalized tables in source order and returns singleton or integrated `ResolvedTable` records with source-table index entries, table-resolution decisions, and row provenance.
   Continuation identity gate G1.7 is in place: explicit continuation metadata, explicit `Table N (continued)` title/caption or leading-row text, and uncaptained adjacent-page fragments after numbered tables are recorded as continuation candidates. They still fail closed as singleton resolved tables with `rejected_continuation` decisions until parent matching and column gates are implemented.
   Parent selection G1.8 is in place: continuation candidates record the closest earlier non-continuation same-number parent when page order and available orientation metadata are compatible. Missing or ambiguous parent choices remain rejected singleton resolved tables until later resolver gates accept integration.
   Column-gated in-memory integration G1.9-G1.12 is in place: the resolver accepts optional `ColumnHeaderSchema` records, uses schema-derived comparison labels as the only column compatibility model, rejects missing or incompatible schemas with `ColumnSchemaCompatibilityDecision`, carries forward parent headers only after a schema match, and appends continuation body rows while recording dropped continuation non-body rows in `IntegrationBoundary`.
   Resolver provenance and source indexing G1.13-G1.15 are in place: retained rows record source table ID, source table index, source row index, source role, and page evidence when available; the source-table index records singleton fragments, consumed base fragments, consumed continuation fragments, and rejected continuation candidates; rejected continuations remain singleton resolved tables with diagnostics.
   Parser wiring G1.16-G1.20 is in place: `table1-parser parse` writes `resolved_tables.json`, builds `TableProfile` and `TableDefinition` over resolved working tables, keeps `parsed_cell_values.json` source-fragment keyed, and joins source value components into `ParsedTable.values` through resolved-row provenance. Remaining work includes continuation-level semantic hardening, status/source-fragment diagnostics, and corpus review.
   Continuation hardening G1.21-G1.23 is in place: accepted continuation body rows feed ordinary resolved-table row/level grouping, so leading continuation count/percent rows can attach to an open categorical parent from the base fragment; `table_processing_status.json` is keyed to resolved semantic tables and carries source table IDs plus structured source-fragment diagnostics; `continued_variable_integrations.json` is retained only as a source-fragment review artifact built from source-fragment definitions and is not consumed by canonical semantic parsing.
   Documentation/artifact contract G1.24-G1.27 is in place: `parsing_output_design.md` records the `resolved_tables.json` contract and source-fragment versus resolved-table artifact relationships; `paper_parse_walkthrough.md` shows resolved tables as the semantic input to profiles, definitions, parsed tables, paper table inventory, and status; no R inspection docs were changed because no real R inspection surface was added.
   Verification G1.28-G1.33 is in place: focused resolved-table regressions cover accepted explicit continuations, schema-rejected continuation candidates, continuation level attachment to a base-fragment parent, and unrelated same-column tables remaining separate. The latest retained full 27-PDF run is `outputs/testpapers_batch_20260708_header_group_upstream_fix`; use that output for current footnote and corpus inspection.
   Recent caption-continuation update: explicit extraction now binds table
   captions one-to-one by page geometry above or below the table before using
   caption text as table identity. A strong uncaptained fragment immediately
   before a below-captioned fragment can now integrate as the prefix of that
   logical table when `ColumnHeaderSchema` comparison matches. In the Asthma
   NHANES paper, page 4 and page 5 now resolve as one Table 1, while page 5
   Table 2 and page 6 Table 3 keep their own below-table captions.

3. [x] Keep paper-page-furniture filtering near the front of document processing.
   `paper_page_furniture.json` is now built before paper markdown,
   layout-aware text streaming, section parsing, bibliography extraction, and
   table extraction. It is also supplied before cell text annotation and
   footnote PDF-block collection. Repeated page-furniture lines are removed
   from `paper_markdown.md` and `paper_text_stream.json`; `paper_sections.json`
   are derived from the PyMuPDF layout-aware stream when available, and the
   artifact is supplied to the extractor as explicit ignore regions.
   Repeated page-furniture words and chars are removed before text-position,
   rescue, rotated, or sideways reconstruction consumes them, and explicit-grid
   rows are removed only when most populated cell bboxes are mostly inside
   ignored regions. Extraction records `metadata.page_furniture_overlap` when a
   candidate touches ignored regions and `metadata.page_furniture_mask` when
   evidence was removed.
   Implementation plan: `docs/implementation/paper_page_furniture_implementation_plan.md`.
   Design contract, Pydantic schemas, positioned page-text collection,
   matching-text normalization, edge-band recurrence clustering,
   `paper_page_furniture.json` parse output, R inspection helpers, real-paper
   review, early-filtered cell text annotation and footnote PDF-block
   collection, and early extraction masking are in place.
   Recent table-mention update: `paper_table_mentions.json` is now built from
   the page-furniture-filtered layout-aware text stream before table extraction.
   It classifies `Table N` lines as caption candidates, continuation labels, or
   prose references and is passed into text-position fallback extraction so a
   prose reference split across lines cannot seed a table candidate. The
   fallback also rejects numeric-anchor grids when the supposed value region is
   mostly multi-word prose fragments.

4. [x] Retire broad trailing-row cleanup where page-furniture masking owns the issue.
   `metadata.trailing_non_table_rows` is now limited to explicit trailing
   continuation-page notes. Broad large-gap/text-spread trimming after the final
   value row was removed so footer/page-furniture cleanup is owned by the early
   page-furniture mask rather than by a second heuristic path.

5. [ ] Make table-region ownership the single source of caption/header/body/footer truth.
   Initial implementation is in place: `table_regions.json` is built after
   extraction and cell-text annotation, before normalization. `TableRegion`
   records geometry-derived caption rows, preamble rows, column-header rows,
   body rows, footer-note rows, row-role assignments, rule evidence,
   confidence, and diagnostics. Normalization consumes
   `TableRegion.column_header_rows` and `TableRegion.body_rows` when available,
   and extracted-table footnote footer harvesting now prefers
   `TableRegion.footer_note_rows`.
   Caption ownership is now established earlier for explicit table boxes:
   caption candidates are linked by nearest compatible table geometry above or
   below the box, and `metadata.caption_binding` records placement, distance,
   and bbox evidence. `TableRegion` still owns row regions inside each
   extracted table, while extracted-table title/caption fields carry the visual
   table identity.
   Current canonical extraction update: explicit PyMuPDF4LLM table boxes are
   treated only as rough table-region hints. The extracted grid is rebuilt from
   positioned PyMuPDF words, characters, and full-width rules through the
   hline, value-matrix, or bbox-word geometry paths before normalization sees
   the table. `layout_source = "pymupdf4llm_json"` may still identify the
   source of the rough box, but `canonical_extraction_layer =
   "pymupdf_positioned_geometry"` marks tables whose rows/cells/header geometry
   are owned by PyMuPDF positioned extraction. If positioned reconstruction
   cannot build a credible grid from the rough box, the explicit backend table
   is not emitted as an extracted table.
   Current verification run:
   `outputs/testpapers_batch_20260708_header_group_upstream_fix` parsed 27/27 PDFs,
   emitted 66 extracted tables, used `pymupdf_positioned_geometry` for all 66,
   and had 0 backend JSON grid survivors. The test suite no longer keeps
   backend-grid survival fixtures as acceptable parser behavior.
   Positioned row-grid construction now keeps parenthesized numeric expressions
   together from open parenthesis through matching close parenthesis and derives
   the first row-label/value boundary from the observed gap before the repeated
   first value-column anchor, rather than from a fake midpoint between the
   leftmost row-label text and the first value column.
   This preserves the Planetary Health p2 -> p3 continuation and the MDPI p5
   -> p6 continuation without schema-level continuation enrichment.
   Remaining follow-up: Planetary p2 and p3 still use mixed candidate paths
   even though both emit PyMuPDF-positioned geometry, so the next extraction
   hardening step should make the continuation fragment follow the same
   canonical positioned path instead of relying on the PyMuPDF4LLM rough-box
   path.
   Follow-up: migrate column-header schema rescue logic and remaining
   continuation/header compatibility review paths to trust `TableRegion`
   rather than repairing title/caption contamination locally. Harden column
   geometry for Eke Table 2 p6 -> p7, where row-region ownership is now clean
   but normalized column counts still differ. Add R inspection helpers only
   after the Python artifact stabilizes.

6. [ ] Align parser route with table taxonomy.
   `table_category` should drive routing once it is available. Current `table_family` is better understood as an early provisional parser-route signal; decide whether to rename, replace, or derive it from the paper table inventory.
   Recent update: obvious OR/CI estimate-result tables without title/caption
   signals now route through `TableProfile.table_family = "estimate_results"`
   when repeated effect+CI headers and estimate-CI range cells provide
   structural support. In the latest corpus run, Asthma p6-t0 moved from
   `non_table_layout_candidate` to `analysis_outputs`.

7. [ ] Add first-class support for data matrices.
   Tables categorized as `data_presentation` need a sibling semantic model/parser instead of being forced through Table 1 descriptive semantics or left as only normalized grids.
   Recent update: wide matrix-like real tables without title/caption signals are
   no longer marked as `non_table_layout_candidate` solely because Table 1
   variable semantics fail. They remain `ok` with
   `matrix_like_table_without_supported_semantic_route` status notes and can be
   categorized as `data_presentation`. Helicobacter p5-t0, p6-t0, and p7-t0 now
   follow this path.

8. [ ] Model value semantics beyond count/percent.
   Add explicit handling for weighted population sizes, prevalence/percent estimates, age-standardized estimates, standard errors, and `N/A`/not-estimable values where appropriate.
   Design note: `docs/design/parsed_value_components.md`.
   Implementation plan: `docs/implementation/parsed_value_components_implementation_plan.md`.
   Direction: parse source-table cells into index-keyed value-component records before continuation fragments are joined. Do not duplicate row/column labels or variable names in the cell-value artifact; attach semantics later by joining on source/integrated row and column provenance.
   Add the component artifact early in the parse flow, after `ColumnHeaderSchema` and before semantic row/column value joins, so later paper-review diagnostics can assess value patterns without depending on a completed semantic parse.
   Do not preserve the old two-slot `ValueRecord` shape as canonical if it blocks the right design. The semantic value layer should become a component-aware joined view over source cell components, row/level semantics, and column semantics.
   Later paper typo/error review should consume the component layer, `ColumnHeaderSchema`, and `ParsedTable.values` once real review workflows identify concrete repeated checks. Do not add generic per-column profile artifacts or helper surfaces before those failure modes are known.
   Recent update: `ParsedTable.values` now preserves source-table provenance, row/column semantics, header paths, parse patterns, and typed value components without scalar compatibility aliases. Count-percent checks now operate on components, and `parsed_cell_values.json` records source-grid components without duplicating semantic row or column labels. The earlier validation-report and parsed-value-column-profile sidecars were removed as over-scoped for the current data-structure goal.
9. [ ] Strengthen parent/level reasoning.
   Use table-local evidence such as repeated level blocks, blank or sparse parent rows, indentation, header value roles, continuation boundaries, and value-region shape. Indentation should be one strong signal, not the only signal.

10. [ ] Clean up benign PDF text artifacts cautiously.
   Some text-based PDFs include spreadsheet-like artifacts that should be normalized without hiding extraction evidence. Known examples:
   - U+FEFF zero-width no-break/BOM characters embedded in extracted table cells, likely from spreadsheet copy/paste into the source document. These currently survive into row labels such as Planetary Health rows with invisible trailing characters.
   - Single-row split label tails such as `Coronary heart disease, n` plus adjacent `(\%)`/`(%)` in the next cell when the fragment is physically adjacent to the row label and clearly before the first value column.
   Recent update: footnote-suffixed p-values such as `<0.001a` now count as p-value tokens for word-position column anchoring and value parsing, so a far-right p-value cluster is not collapsed into the last data column.
   Sidecar: `docs/design/cell_text_annotations.md` defines `cell_text_annotations.json` for superscript, subscript, and small-marker geometry; parse now populates page-coordinate cell-bbox annotations when PyMuPDF char geometry is available, and R inspection loads and displays the sidecar. Implementation checklist is in `docs/implementation/cell_text_annotations_implementation_plan.md`. Keep this separate from symbol canonicalization and value parsing.
   Footnote follow-up: `docs/design/paper_footnotes.md` defines the `paper_footnotes.json` artifact contract, and `docs/implementation/paper_footnotes_implementation_plan.md` tracks the staged work. Core Python schemas, anchor/definition inventories, PyMuPDF text-block definition sources, glyph canonicalization, deterministic links, parse output, R data-frame helpers, `ObservedFootnotes` attachment, and real-PDF smoke passes are in place. Review found resolved, unresolved, and ambiguous real examples; links remain review-only and should not be consumed downstream until page-note boilerplate and repeated marginal text pruning are stronger.
   Recent footnote update: table-local note lines can now define markers after leading explanatory prose, including embedded and bracketed markers such as `significance. a Represents ... b Represents ...` and `[a] ... [b] ...`. This resolves the `metabolic` Table 1 p-value superscripts against the local Chi-square and Kruskal-Wallis definitions while keeping links as review evidence only.
   Recent footer update: statistical-significance footer lines can now define repeated asterisk runs such as `* P value < 0.05, ** P value < 0.01, *** P value < 0.001`, and anchors attached to p-values preserve the visible asterisk count. This resolves the `stroke` Table 1-3 asterisk superscripts.
   Recent symbol-footer update: known symbol markers such as `†`, `‡`, and `*` can now define any non-empty local footer text without semantic checks on the definition body. This resolves `cardiovascular` Table 1 double-dagger links and the anthropometric CKD dagger/star footer links; p-value semantics remain limited to the explicit conventional fallback for unresolved asterisk anchors.
   Recent extracted-footer update: `paper_footnotes.json` now builds table-note definition source lines from extracted footer rows after the final value-matrix row, appending adjacent continuation rows in extracted row order. Same-table extracted footer definitions are preferred over duplicate same-table PDF-text definitions, which protects multiline rotated-table footers such as Eke Table 2.
   Recent footer-block update: `paper_footnotes.json` now harvests PyMuPDF page text as contiguous blocks and classifies complete table-local footer blocks by table bbox adjacency and horizontal overlap before definition parsing. Continuation-group visual IDs are carried into footnote scoping, so a footer on a terminal uncaptioned fragment can resolve anchors from the earlier fragment of the same visual table. This resolves the Planetary Health Table 1 `*`, `†`, `‡`, and `§` links.
   Recent footer-finder update: table-local extracted footers are now persisted in `paper_footnotes.json` under `footers` and surfaced in R through `footnote_footers_df()` and `show_paper_footnotes()`. `find_table_footer_rows()` uses existing row bounds plus full-width/horizontal rule geometry first, accepting rows below a rule only when the rule lies at or below the last value-matrix row and the region contains definition-like rows; otherwise it falls back to rows after the last value-matrix row. This keeps Eke page 4 body rows out of the footer while preserving the page 5 and page 7 footer regions for review.
   Recent PDF-footer artifact update: filtered PyMuPDF blocks classified as table-local footers are now also persisted as unsplit `footers` records before definition splitting. This keeps metabolic and stroke from showing table-note definitions with an empty footer review artifact. R footnote review filters now match the selected table's visual ID as well as its fragment table ID, so Eke Table 1 and Table 2 reviews include footers found on their continued fragments without treating `Table 1. (continued)` as definition text.
   Recent math/unit update: numeric superscripts and subscripts in expressions like `10^9`, `10^6`, `m^2`, `kg/m^2`, `CO₂`, `I²`, and `×10^9/L` are rejected before `FootnoteAnchor` creation. Subscript annotations are now generally suppressed as non-footnote anchors, including single-letter notation such as `S_I`/`AIR_g` and multi-letter subscript words such as `P_Begg`/`P_Egger`. They remain visible in `cell_text_annotations.json` with original glyph case; `paper_footnotes.json` records suppression counts in `math_unit_anchor_suppression_count`, `subscript_anchor_suppression_count`, and `word_like_subscript_anchor_suppression_count`.
   Recent symbol-font update: PyMuPDF char extraction now applies font-qualified Unicode normalization before word/grid reconstruction for known embedded symbol-font codes such as `±`, `×`, `−`, and `<`. Inline marker detection accepts same-height trailing glyphs attached to numeric/comparator text including `±` values and preserves marker font metadata. In the focused Ethnic Differences run, `S_I` and `AIR_g` remain suppressed subscript annotations, while the marker-font `x` resolves against the local `xP < ...` footer definition.
   Recent p-value-star update: after math/unit rejection and explicit local footnote linking, `*`, `**`, and `***` attached to p-value cells/columns receive structured conventional fallback meanings with thresholds `10^-1`, `10^-2`, and `10^-3`. Explicit footer definitions override the fallback, and R-facing output exposes whether the interpretation was explicit or conventional.
   Bibliographic reference follow-up: `paper_bibliography.json` now preserves the paper's own bibliography entries, numbered or unnumbered, from the PyMuPDF layout-aware text stream and links numeric table-cell study/source/header markers to numbered entries when no local table-note definition exists. The footnote linker suppresses citation-like numeric table-cell markers with matching numbered bibliography entries from table-footnote link counts, while the original marker evidence remains visible in `cell_text_annotations.json` and linked in `paper_bibliography.json`. Reference-list extraction uses one layout stream: read page, then column, then vertical position; start entries at the column left edge, with either a numeric label or the first author/organization line; keep indented rows open across column and page breaks; and fall back to markdown-derived sections only when the positioned text stream cannot produce entries. The current full 27-PDF run, `outputs/testpapers_batch_20260708_header_group_upstream_fix`, has 1370 bibliography entries, 0 empty bibliographies, and 0 bibliography diagnostics.
   Future work: harvest numeric bibliography reference markers from body text and captions into the same per-paper artifact, then validate one-to-one coverage for numbered lists: every observed numeric reference marker should resolve to a numbered bibliography entry, and every numbered bibliography entry should have at least one observed marker. Add author-year body citation harvesting separately against preserved unnumbered entries. Record coverage gaps as diagnostics without introducing any cross-paper citation-management layer.
   Footnote-style update: `paper_footnotes.json` now splits local caption/footer definitions from structured marker evidence before falling back to text parsing. PyMuPDF footer blocks are built from positioned characters, and extracted footer rows can use `cell_text_annotations.json` when a raised superscript marker begins the first populated footer cell. Raw damaged strings where the marker runs into the following word are preserved as source text but do not define the marker. Extracted footer rows can still contribute weaker text evidence from confirmed statistical marker prefixes such as `xP < ...`. Structured marker evidence is merged with ordinary symbol markers in the same footer block, so an upright `* p < 0.05` definition is not dropped just because the same block also contains a raised `†` definition, as in the anthropometric CKD Table 1 footer. Textual marker definitions such as `The asterisk indicates ...` remain valid local definition evidence. The parser also preserves symbol-block splitting across variable whitespace before `†`, `‡`, `§`, and similar markers, while avoiding all-caps acronym false splits such as `eGFR`; vertical-bar glyph artifacts attached to rotated numeric cells are suppressed as non-footnote symbols. Current page-furniture handling filters positioned text before PDF definition blocks are built; the full 27-PDF run, `outputs/testpapers_batch_20260708_header_group_upstream_fix`, records `page_furniture_filter_stage = before_pdf_definition_block_construction` for all papers, has 387 resolved footnote links, 0 inferred, 0 unresolved, and 0 ambiguous links, and `paper_style_profile.json` footnote-link coverage passes for all 27 papers.
   Treat these as normalization follow-ups, not emergency parser changes. Preserve raw extraction, add focused repairs with provenance, and avoid broad rules that could merge real value columns into labels.

11. [ ] Add known-failure regression fixtures.
   Create stable real-paper or minimal extracted-table fixtures for specific failures and structural variants that have actually mattered in parser review. Focus on cases that protect parser behavior from silent regressions, not broad unit testing for its own sake. For value components, cover only the patterns and artifact contracts that are tied to real failures or review workflows.
   Recent cleanup: removed broad scaffold/schema/provider/synthetic/display smoke tests and kept the suite focused on parser structural regressions, artifact contracts, and LLM identity-safety checks. Future tests should continue to justify themselves as known-failure protections or important artifact contracts.

12. [ ] Improve R inspection workflow.
   Provide R-native review objects and display methods that make variables, levels, columns, parse notes, category/route decisions, and diagnostics easy to inspect during corpus review.
   Current direction: defer new R helper work until real usage of the component-native artifacts shows which views are needed. Decide whether `ObservedTableOne` remains the right R inspection object before extending it. Any R surface should consume canonical components directly and should not require parser scalar compatibility aliases. Avoid many tiny specialized helpers unless repeated review workflows justify them.
   Recent update: `show_table_structure()` now treats structured header spans, per-column header paths, and deterministic variable row spans as the default structure view, including the row-label leaf column from `ColumnHeaderSchema`, while raw normalized header rows remain opt-in provenance/debug evidence through `include_raw_header_rows = TRUE`.

## Notes

- Do not mark a task complete just because one narrow case has been patched. Mark it complete only when the repo has a general implementation and tests for the intended scope.
- If a task expands into multiple concrete implementation steps, add subitems or link to a dedicated implementation note.
- Recent rotated extraction update: explicit rotated-grid refinement now prefers
  PyMuPDF directional text-block geometry as the source table region before
  coordinate transformation. This keeps a rotated table plus footer together when
  they occupy one column of a two-column page and excludes upright article text in
  the other column.
- Recent document-processing update: repeated page furniture is built near the
  front of parse processing and passed to paper text streaming, markdown
  filtering, table extraction, cell text annotation, and footnote PDF-block
  collection before those stages build downstream artifacts. Broad trailing
  large-gap/text-spread cleanup after the final value row has been retired;
  `metadata.trailing_non_table_rows` now records only explicit trailing
  continuation-page notes.
- Recent extraction guardrail: reference/bibliography section detection now combines backend payload text with PyMuPDF page text before table detection and carries the section stop into fallback extraction, so bibliography pages cannot enter the table pipeline just because the primary JSON payload missed the section heading.
- Recent paper-context update: `paper_text_stream.json` now records
  layout-aware, page-furniture-filtered PyMuPDF text lines, page-level
  `column_boundaries` and `column_bands`, and orders pages as page, column, then
  y-position for any detected column count. `paper_sections.json` and
  bibliography entry extraction consume this stream when available, while
  `paper_markdown.md` remains a filtered backend-markdown evidence artifact and
  is no longer authoritative for document order.
- Recent document-structure follow-up: page furniture should remove repeated
  running headers, footers, watermarks, and other recurring non-content. It
  should not classify one-off section headings. Add a coarse document-outline
  layer that preserves original headings while mapping them into broad roles
  such as abstract, introduction/background, methods, results, discussion,
  conclusion, references, and other.
- Recent extraction guardrail: sparse trailing table-continuation notes such as `(Table 1 continues on next page)` are removed and recorded in `metadata.trailing_non_table_rows`; post-header notes such as `(Continued from previous page)` remain provenance rows but are excluded from normalized `body_rows`.
- Recent extraction update: rotated word-position refinement fails closed when a small backend grid would expand into an implausibly wide table. More than 30 columns is rejected for rotated collapsed-grid recovery, and 13-30 columns requires separator-rule support. Newer PyMuPDF4LLM can emit a mixed-orientation table box containing both upright article text and a rotated table; extraction now derives a separate rotated-block candidate from the contiguous vertical PyMuPDF text block inside that box and lets candidate deduplication choose the recovered table region. The retained full-corpus run now includes the Ethnic Differences recovery and its resolved subscript/marker-font false footnote issues.
- Recent value-matrix geometry update: explicit-grid refinement can derive
  column boundaries from repeated numeric value anchors before using header text
  starts. The row-label/value split is taken from the observed per-row gap before
  the value run, so the left mostly-text column stays intact without keying on a
  header word such as `Characteristics`.
- Recent front-matter extraction update: table candidate detection now builds a
  coarse Abstract-to-Introduction interval from positioned PyMuPDF text. An
  uncaptained backend table-like box inside that interval is suppressed unless
  it has explicit table identity or strong value-matrix evidence. This keeps
  article-info/abstract layout grids out of `extracted_tables.json`; in the
  GOLD paper, the false page-1 `ARTICLE INFO`/`ABSTRACT` pseudo-table is no
  longer extracted, while real tables begin on page 4.
- Recent candidate-order update: final table-candidate selection now applies a
  source-order plausibility check to weak unnumbered candidates. A weak
  unnumbered candidate before a confirmed Table 1, or between consecutive
  confirmed numbered tables such as Table 3 and Table 4, is suppressed because
  it has no plausible table-number slot. Strong unnumbered candidates remain so
  continuation and semantic stages can decide them from geometry and schema;
  adjacent row-label/numeric fragments after a numbered table are also retained
  as possible continuations.
- Recent table-region normalization update: empty-column pruning after
  normalization repairs now uses region-owned header/body rows when available.
  Footer/note rows remain available in extraction and table-region artifacts,
  but they cannot keep a footer-only column alive in the normalized data grid.
- Recent normalization update: header/body selection now uses validated full-width separator rules first, first value-region anchors second, and content scoring only as fallback. Full-width separator evidence is derived from stroked rule geometry so filled row highlighting/background shading does not create false hlines. Future work still needs a more principled model for data/estimate tables without clear separator or value-anchor evidence, rather than adding more ordered special cases.
- Recent column-schema update: full-width hlines inside an already selected header band now split upper spanning-group rows from lower wrapped leaf-header rows. Cardiovascular Table 2 keeps body start row 7 while using rows 4-6 as leaf labels and rows 0-3 as training/testing cohort groups.
- Recent normalization update: dense row-by-row full-width rules no longer disable hline separator detection. Fully ruled tables should still use hlines as boundary proposals, then choose the boundary that preserves a multicolumn group row plus its single-column leaf-label row above any row-label-only body parent. This fixes the Table 3 continuation in `Association between anthropometric indices and chronic kidney disease: Insights from NHANES 2009–2018`, where page 11 and page 12 now share the same `Model 1`/`Model 2`/`Model 3` column schema and integrate as one resolved table.
- Recent hline-led extraction update: for credible ruled table candidates with
  full-width stroked horizontal rules, extraction now treats the
  PyMuPDF4LLM grid as only a rough region and rebuilds row/column structure
  from positioned PyMuPDF words inside the ruled band. The first internal
  full-width rule supplies the header/body separator when both sides contain
  text; value-column anchors come from repeated body value positions; upper
  header cells can span adjacent blank value columns. The same sparse-versus-
  dense header-cluster repair is shared with text-position fallback, so base
  pages and continuation pages do not diverge solely because one came from
  fallback and the other came from a backend explicit table box. In the latest retained
  run this fixes GOLD Table 3 (`p5-t0`) as a 5-row, 3-column table with
  `Adjusted Model` spanning `OR (95%CI)` and `p-value`. Downstream
  TableDefinition semantics for small estimate-result tables remain separate
  follow-up work.
- Earlier review update: `outputs/testpapers_footer_blocks_20260701_final`
  recorded 27 PDF command successes, 447 footnote links, 375 resolved links, 54
  inferred links, 7 ambiguous links, 11 unresolved links, 39 math/unit anchor
  suppressions, 2 word-like subscript suppressions, 56 PDF text blocks
  classified as table footers, and 48 page-furniture definition-block
  suppressions from the older late-filter path. Current page-furniture handling
  filters positioned text before footnote definition blocks are built.
  `parse_quality_reports.json` reports
  `header_body_split_rule_disagreement` when the hline and value-anchor
  candidates both exist and disagree, except when the hline body start only
  precedes the first value row by expected variable/section-header rows with no
  recognized value pattern.
- Recent bibliography baseline update:
  `docs/implementation/real_paper_testing_guide.md` now uses
  `outputs/testpapers_batch_20260708_header_group_upstream_fix` as the current
  retained run: 27 PDF command successes, 0 empty bibliographies, 0
  bibliography diagnostics, 1370 bibliography entries, 22 numbered
  bibliography papers, 5 unnumbered bibliography papers, and 0 mixed
  numbering-style papers. The same run has 381 resolved / 0 inferred / 0
  unresolved / 0 ambiguous footnote links.
- Recent front-matter guard check:
  `outputs/testpapers_batch_20260706_frontmatter_guard` recorded 27/27 parse
  command successes. GOLD no longer has the page-1 pseudo-table; the remaining
  failed table statuses in that run are periodontis2 p6-t0, periodontitis
  p11-t0, PRISm/COPD p4-t0, and Mediterranean Diet/Frailty p3-t0.
