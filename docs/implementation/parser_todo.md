# Parser ToDo

This is the persistent implementation ToDo list for parser work. Agents should check it before changing extraction, normalization, row/column semantics, table routing, value parsing, diagnostics, or R inspection helpers. Update it when a task is completed, reprioritized, split, or superseded.

Keep detailed implementation notes and epidemiology-table reasoning here or in linked implementation documents. Keep high-level design docs focused on stable pipeline shape, schemas, persisted artifact contracts, and durable architecture decisions.

## Current Priorities

1. [ ] Add a parser-native column header schema artifact.
   Build `ColumnHeaderSchema` between `NormalizedTable` and `TableDefinition` so leaf columns, higher spanning header groups, group-to-leaf relationships, raw cell evidence, and coordinates are explicit before any tableone-style projection.
   Design note: `docs/design/column_header_schema.md`.
   This should become the primary column model consumed by `TableDefinition` and any later stored summary/tableone projection; continuation compatibility is an important later consumer, but not the main design driver.

2. [ ] Make continuations semantically real.
   One logical Table 1 spanning pages should feed `TableDefinition` and `ParsedTable`, rather than leaving page-level and continuation-page parses as separate semantic outputs.
   Design note: `docs/design/table_continuation_resolution.md`.
   First diagnostic step implemented: `table_continuation_column_checks.json` checks explicit `demographic_description` continuations for column-count, header-signature, and coordinate compatibility without changing parser inputs.

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

## Notes

- Do not mark a task complete just because one narrow case has been patched. Mark it complete only when the repo has a general implementation and tests for the intended scope.
- If a task expands into multiple concrete implementation steps, add subitems or link to a dedicated implementation note.
