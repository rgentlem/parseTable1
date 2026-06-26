# Parser ToDo

This is the persistent implementation ToDo list for parser work. Agents should check it before changing extraction, normalization, row/column semantics, table routing, value parsing, diagnostics, or R inspection helpers. Update it when a task is completed, reprioritized, split, or superseded.

Keep detailed implementation notes and epidemiology-table reasoning here or in linked implementation documents. Keep high-level design docs focused on stable pipeline shape, schemas, persisted artifact contracts, and durable architecture decisions.

## Current Priorities

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
   Continued-variable integration now writes `continued_variable_integrations.json` as an inspection artifact made of existing `TableDefinition` objects with integrated `DefinedVariable` records plus integration provenance and tableone-style metadata. It is not yet consumed by value parsing.
   Boundary handling now preserves and reinterprets leading continuation body rows before the first standalone continuation variable, so body rows that are ambiguous without the prior fragment can still attach as levels when compatible column and parent-variable context supports it.
   Follow-up: Planetary Health Table 1 now exposes its uncaptained next-page fragment as a continuation candidate, its wrapped lowercase caption tail is kept in the caption instead of table row zero, the top value-region group labels are recovered using the internal header rule plus a large geometry gap, and the base page uses early stable value anchors to preserve the visible 9-column structure. Merged continuation artifacts remain inspection-only; making them feed semantic parsing is still separate continuation-resolution work.

3. [ ] Add paper-level repeated marginal text and watermark detection.
   The current extraction-time trailing-row trim is a necessary local guard, but repeated download notices, watermarks, page furniture, and marginal text should also be assessed across the whole paper once. A future paper-level artifact should identify repeated non-table text signatures and/or page regions, then extraction can ignore those regions consistently while keeping the table-local boundary trim as a fallback for one-off spillover.

4. [ ] Align parser route with table taxonomy.
   `table_category` should drive routing once it is available. Current `table_family` is better understood as an early provisional parser-route signal; decide whether to rename, replace, or derive it from the paper table inventory.

5. [ ] Add first-class support for data matrices.
   Tables categorized as `data_presentation` need a sibling semantic model/parser instead of being forced through Table 1 descriptive semantics or left as only normalized grids.

6. [ ] Model value semantics beyond count/percent.
   Add explicit handling for weighted population sizes, prevalence/percent estimates, age-standardized estimates, standard errors, and `N/A`/not-estimable values where appropriate.
   Design note: `docs/design/parsed_value_components.md`.
   Direction: parse source-table cells into index-keyed value-component records before continuation fragments are joined. Do not duplicate row/column labels or variable names in the cell-value artifact; attach semantics later by joining on source/integrated row and column provenance.
   Recent update: deterministic value-pattern and value parsing now recognize `mean_sd` cells where the PDF extracted the plus/minus glyph as a spaced `6`, while preserving the original raw value text.

6. [ ] Strengthen parent/level reasoning.
   Use table-local evidence such as repeated level blocks, blank or sparse parent rows, indentation, header value roles, continuation boundaries, and value-region shape. Indentation should be one strong signal, not the only signal.

7. [ ] Clean up benign PDF text artifacts cautiously.
   Some text-based PDFs include spreadsheet-like artifacts that should be normalized without hiding extraction evidence. Known examples:
   - U+FEFF zero-width no-break/BOM characters embedded in extracted table cells, likely from spreadsheet copy/paste into the source document. These currently survive into row labels such as Planetary Health rows with invisible trailing characters.
   - Single-row split label tails such as `Coronary heart disease, n` plus adjacent `(\%)`/`(%)` in the next cell when the fragment is physically adjacent to the row label and clearly before the first value column.
   Recent update: footnote-suffixed p-values such as `<0.001a` now count as p-value tokens for word-position column anchoring and value parsing, so a far-right p-value cluster is not collapsed into the last data column.
   Sidecar: `docs/design/cell_text_annotations.md` defines `cell_text_annotations.json` for superscript, subscript, and small-marker geometry; parse now populates page-coordinate cell-bbox annotations when PyMuPDF char geometry is available, and R inspection loads and displays the sidecar. Implementation checklist is in `docs/implementation/cell_text_annotations_implementation_plan.md`. Keep this separate from symbol canonicalization and value parsing.
   Treat these as normalization follow-ups, not emergency parser changes. Preserve raw extraction, add focused repairs with provenance, and avoid broad rules that could merge real value columns into labels.

8. [ ] Add golden-paper regression tests.
   Create stable real-paper fixtures with expected table categories, parser routes, variables, levels, columns, and selected value records for Eke-like cases and other known structural variants.

9. [ ] Improve R inspection workflow.
   Provide R-native review objects and display methods that make variables, levels, columns, parse notes, category/route decisions, and diagnostics easy to inspect during corpus review.
   Current direction: `ObservedTableOne` exposes tableone-style `ContTable`, `CatTable`, and `MetaData` fields as the early R surface, while preserving lower-case compatibility aliases. R helpers should access variables and columns through canonical table-definition accessors rather than repeated direct list traversal.
   Recent update: `show_table_structure()` now treats structured header spans, per-column header paths, and deterministic variable row spans as the default structure view, including the row-label leaf column from `ColumnHeaderSchema`, while raw normalized header rows remain opt-in provenance/debug evidence through `include_raw_header_rows = TRUE`.

## Notes

- Do not mark a task complete just because one narrow case has been patched. Mark it complete only when the repo has a general implementation and tests for the intended scope.
- If a task expands into multiple concrete implementation steps, add subitems or link to a dedicated implementation note.
- Recent extraction guardrail: explicit and text-position candidates now trim structurally trailing non-table rows after the final numeric value-matrix row when footer/watermark evidence is present, recording `metadata.trailing_non_table_rows`. Keep future footer handling structural and page-geometry driven rather than source- or publisher-specific.
