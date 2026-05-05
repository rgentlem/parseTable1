# PyMuPDF Text-Layout Migration Checklist

Keep the implementation tight. Do not sprawl this across many large helpers or verbose wrapper layers. Reuse the existing reconstruction logic where possible, move only what is necessary, and minimize added lines. The goal is parity with the current behavior, not a large framework rewrite.

## Goal

Add the current unruled-table and collapsed-label fallback behavior to the PyMuPDF / PyMuPDF4LLM path.

## Preserve These Behaviors

- Reconstruct unruled tables from positioned text
- Restore collapsed first-column labels
- Handle shifted label columns
- Preserve `row_bounds` metadata
- Preserve `horizontal_rules` metadata where feasible
- Keep explicit `pymupdf4llm` table boxes as the primary extraction path

## Keep The Code Tight

- Reuse current logic instead of rewriting it
- Move shared logic into one small backend-agnostic module
- Keep PyMuPDF-specific extraction in one small adapter module
- Do not create large abstractions unless they remove duplication immediately
- Do not add new configuration unless it is needed for parity
- Do not touch unrelated parsing, normalization, or LLM modules

## Files To Add

## `table1_parser/extract/layout_fallback.py`

Add one small shared module for geometry-to-grid fallback.

Move only the reusable logic here:

- `_vertical_overlap`
- `_restore_text_from_chars`
- `_restore_word_text`
- `_group_words_into_lines`
- `_cluster_positions`
- `_is_numeric_like`
- `_looks_like_collapsed_label_token`
- `_build_rows_from_line_segment`
- `_segment_lines_into_tables`

Add one public function:

- `build_text_layout_candidates(...)`

This module should not import alternate extraction backends directly.

## `table1_parser/extract/pymupdf_page_adapter.py`

Add one small PyMuPDF adapter module.

Responsibilities:

- words from `page.get_text("words")`
- chars from `page.get_text("rawdict")`
- horizontal rules from `page.get_drawings()`
- page text extraction

Return normalized records that `layout_fallback.py` can consume.

## Files To Refactor

## `table1_parser/extract/table_detector.py`

Keep this file small and focused on shared detector primitives.

Keep:

- `DetectedTableCandidate`
- `_normalize_cell`
- `_normalize_rows`
- `_is_rectangular`
- `_text_ratio`
- `_numeric_ratio`
- `_collapse_later_columns`
- `_find_table_line`
- `score_candidate`

Move page-object-specific fallback logic out.

## `table1_parser/extract/pymupdf4llm_extractor.py`

Extend the existing extractor.

New behavior:

- use `pymupdf4llm.to_json(...)` first
- build explicit table candidates from `box["table"]`
- for pages with no usable explicit table boxes, use PyMuPDF words/chars/drawings to build fallback candidates
- merge and score candidates
- preserve provenance in metadata

Metadata target:

- explicit tables: `layout_source = "pymupdf4llm_json"`
- text-layout fallback: `layout_source = "pymupdf_text_positions"`

Do not run fallback blindly on pages that already have good explicit table boxes.

## Files To Leave Alone For Now

- `table1_parser/extract/pymupdf4llm_extractor.py`
- `table1_parser/extract/pdf_loader.py`

Keep them during the migration for regression comparison. Do not expand them.

## Tests To Add

## `tests/test_layout_fallback.py`

Port the current geometry-to-grid behavior into backend-agnostic unit tests.

Required coverage:

- unruled table reconstruction
- collapsed long-label restoration
- collapsed short-label restoration
- shifted label-column restoration

## `tests/test_pymupdf_adapter.py`

Add small unit tests for:

- word extraction normalization
- char extraction normalization
- horizontal drawing extraction
- empty or missing geometry tolerance

## `tests/test_extraction.py`

Add integration tests for the PyMuPDF fallback path.

Required coverage:

- when `pymupdf4llm.to_json(...)` has no table boxes, extractor still returns a table
- returned tables still report `extraction_backend == "pymupdf4llm"`
- fallback path marks `layout_source == "pymupdf_text_positions"`
- recovered labels match expected output
- `row_bounds` is populated
- `horizontal_rules` is populated when drawings support it

Keep current `pymupdf4llm` tests during this phase as the comparison baseline.

## `tests/test_normalization.py`

Add or update one test to confirm PyMuPDF fallback metadata still drives downstream header detection correctly.

## Suggested Order

1. Add `layout_fallback.py`
2. Add `tests/test_layout_fallback.py`
3. Add `pymupdf_page_adapter.py`
4. Add `tests/test_pymupdf_adapter.py`
5. Extend `pymupdf4llm_extractor.py`
6. Add PyMuPDF fallback integration tests
7. Add one downstream normalization regression test
8. Compare on real fallback-heavy PDFs
9. Keep the extraction path `pymupdf4llm`-only

## Acceptance Criteria

- PyMuPDF explicit table extraction still works
- Unruled-table fallback works on PyMuPDF
- Collapsed-label recovery works on PyMuPDF
- Shifted-label recovery works on PyMuPDF
- `row_bounds` survives into normalization
- `horizontal_rules` survives or is acceptably approximated
- No material regression on representative PDFs
- Added code stays compact and localized
