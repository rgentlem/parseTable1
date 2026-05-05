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
   Follow-up: Eke Tables 1-2 show that multi-line header stacks can produce wrong parent paths when rule-banded header rows are extracted as many short text fragments. The current parser now repairs obvious split estimate/uncertainty value columns, drops sparse non-matrix page-text columns and empty separator columns, removes tall/narrow numeric margin text before grid construction, keeps adjacent header text runs together, only merges wrapped leaf rows after geometry-based header inference, preserves normalized-to-original column identity in `source_col_indices`, and uses leaf-band coordinates to move short leading fragments across adjacent column boundaries when the geometry supports it. Remaining work should expose ambiguous leaf-band fragment assignments as structured candidates that deterministic code or later LLM inference can adjudicate; do not hard-code paper-specific vocabulary.

2. [ ] Make continuations semantically real.
   One logical Table 1 spanning pages should feed `TableDefinition` and `ParsedTable`, rather than leaving page-level and continuation-page parses as separate semantic outputs.
   Design note: `docs/design/table_continuation_resolution.md`.
   Variable integration design: `docs/design/separated_variable_description_integration.md`.
   Implementation spec: `docs/implementation/continued_variable_integration_implementation_spec.md`.
   First diagnostic step implemented: `table_continuation_column_checks.json` checks explicit and narrow inferred uncaptained adjacent-page `demographic_description` continuations for column count and schema-derived column-header compatibility without changing parser inputs. `table1_continuation_groups.json` can also report an uncaptained next-page Table 1 fragment, but merged artifacts are still inspection-only and are skipped when normalized columns or schema-derived column headers are incompatible.
   Follow-up: Planetary Health Table 1 now exposes its uncaptained next-page fragment as a continuation candidate, its wrapped lowercase caption tail is kept in the caption instead of table row zero, the top value-region group labels are recovered using the internal header rule plus a large geometry gap, and the base page uses early stable value anchors to preserve the visible 9-column structure. Merged continuation artifacts remain inspection-only; making them feed semantic parsing is still separate continuation-resolution work.

3. [ ] Align parser route with table taxonomy.
   `table_category` should drive routing once it is available. Current `table_family` is better understood as an early provisional parser-route signal; decide whether to rename, replace, or derive it from the paper table inventory.

4. [ ] Add first-class support for data matrices.
   Tables categorized as `data_presentation` need a sibling semantic model/parser instead of being forced through Table 1 descriptive semantics or left as only normalized grids.

5. [ ] Model value semantics beyond count/percent.
   Add explicit handling for weighted population sizes, prevalence/percent estimates, age-standardized estimates, standard errors, and `N/A`/not-estimable values where appropriate.

6. [ ] Strengthen parent/level reasoning.
   Use table-local evidence such as repeated level blocks, blank or sparse parent rows, indentation, header value roles, continuation boundaries, and value-region shape. Indentation should be one strong signal, not the only signal.

7. [ ] Add golden-paper regression tests.
   Create stable real-paper fixtures with expected table categories, parser routes, variables, levels, columns, and selected value records for Eke-like cases and other known structural variants.

8. [ ] Improve R inspection workflow.
   Provide R-native review objects and display methods that make variables, levels, columns, parse notes, category/route decisions, and diagnostics easy to inspect during corpus review.
   Current direction: `ObservedTableOne` exposes tableone-style `ContTable`, `CatTable`, and `MetaData` fields as the early R surface, while preserving lower-case compatibility aliases. R helpers should access variables and columns through canonical table-definition accessors rather than repeated direct list traversal.

## Notes

- Do not mark a task complete just because one narrow case has been patched. Mark it complete only when the repo has a general implementation and tests for the intended scope.
- If a task expands into multiple concrete implementation steps, add subitems or link to a dedicated implementation note.
