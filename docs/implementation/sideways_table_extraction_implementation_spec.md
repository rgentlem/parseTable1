# Sideways Table Extraction Implementation Spec

## Goal

Implement deterministic extraction support for visually landscape tables that are
drawn sideways on portrait PDF pages.

Design reference:

- `docs/design/sideways_table_extraction_design.md`

The motivating regression paper is the Journal of Periodontology NHANES
periodontitis paper in `../testpapers/papers_from_laha`. Tables 1 and 2 are present
in the PDF text, but current extraction treats pages 4 to 7 as uncaptioned collapsed
layout candidates.

## Scope

This change belongs in the extraction layer.

It should produce better `ExtractedTable` objects before normalization, without
changing the downstream meanings of `NormalizedTable`, `TableDefinition`, or
`ParsedTable`.

## Files To Update

Core extraction:

- `table1_parser/extract/pymupdf4llm_extractor.py`
- `table1_parser/extract/layout_fallback.py`
- `table1_parser/extract/pymupdf_page_adapter.py` only if full-page line-direction
  extraction needs a small adapter extension

Tests:

- `tests/test_extraction.py`
- optionally a small fixture-style test using synthetic sideways word geometry

Docs:

- `docs/design/paper_parse_walkthrough.md` if the parse walkthrough needs to mention
  sideways extraction metadata
- `docs/design/parsing_output_design.md` if new persisted metadata fields are added
  as normal output expectations

## Constraints

- Do not add paper-specific logic.
- Do not use the LLM for grid reconstruction.
- Do not merge continuation tables in this change.
- Do not replace the existing upright extraction path.
- Preserve raw text and table metadata.
- Keep extraction deterministic and inspectable.
- Avoid single-use helper functions unless the inline code would become materially
  harder to read.

## Current Code Context

The existing extractor already has two relevant pieces:

- `_infer_table_orientation_metadata(...)` in
  `table1_parser/extract/pymupdf4llm_extractor.py`
  detects rotated text inside a candidate bbox using PyMuPDF line directions.
- `_refine_explicit_table_candidate_grid(...)` can rebuild collapsed explicit grids,
  including a rotated path that uses
  `normalize_positioned_geometry_for_rotation(...)`.

That is not enough for this failure because caption detection and candidate
construction still happen primarily in page coordinates. Tables 1 and 2 need a
sideways full-page or page-region candidate path so captions and body geometry are
interpreted in the same transformed coordinate system.

## Implementation Steps

### 1. Add Sideways Page Detection

In `PyMuPDF4LLMExtractor._detect_table_candidates(...)`, after page words/chars/rules
are loaded, compute a conservative sideways-page signal.

Candidate signals:

- page is portrait by page rect width/height
- page-level rotation is absent or zero
- clipped or page-level line directions are mostly vertical
- raw page text contains a table caption such as `Table N`
- pymupdf4llm explicit table boxes on the page are collapsed or low quality
- word/block geometry contains many narrow/tall text runs

The first implementation can keep this simple:

- use page rect as a full-page bbox
- call the existing line-direction extraction against that bbox
- classify the page as sideways when vertical directions dominate with high
  confidence and the page text has at least one table caption

Record candidate diagnostics in metadata:

- `sideways_candidate`
- `sideways_detection_signals`
- `orientation_strategy`

### 2. Build A Transformed Page Geometry View

For sideways pages, create a transformed geometry view before running text-layout
candidate construction.

Reuse the existing coordinate idea in
`normalize_positioned_geometry_for_rotation(...)`, but apply it to the relevant page
or page-region geometry rather than only an explicit table bbox.

Inputs:

- `page_words`
- `page_chars`
- `page_rule_segments`
- full page bbox or a conservative content bbox
- dominant vertical direction: `vertical_text_up` or `vertical_text_down`

Outputs:

- transformed words
- transformed chars
- transformed rule segments
- transformed bbox

The transformed word list should allow `build_word_lines(...)` and
`build_text_layout_candidates(...)` to see the visual table rows in normal row-major
order.

### 3. Build Sideways Text-Layout Candidates

Call `build_text_layout_candidates(...)` with transformed words/chars/rules.

Use a distinct layout source:

```text
sideways_text_positions
```

The resulting candidates should have:

- caption detection in transformed coordinates
- row grids built from transformed text lines
- `caption_detection_space = "transformed_coordinates"`
- `geometry_coordinate_frame = "page_sideways_transformed"` or equivalent
- `orientation_strategy = "sideways_transformed"`

Do not discard the original upright candidates at this point. Add sideways candidates
to the same page candidate pool and let scoring/selection choose the better table
candidate.

### 4. Transfer Sideways Metadata Into Extracted Tables

When `_build_extracted_table(...)` serializes a selected sideways candidate, preserve
the metadata fields needed for R and JSON inspection:

- `orientation_strategy`
- `sideways_candidate`
- `sideways_detection_signals`
- `caption_detection_space`
- `geometry_coordinate_frame`
- `grid_refinement_source`
- `table_number`
- `is_continuation`
- `continuation_of_table_number`

If transformed coordinates are stored as cell bboxes, make that clear through
`geometry_coordinate_frame`. Do not pretend transformed bboxes are normal page
coordinates.

### 5. Continuation Handling

Caption-driven continuation should work through the existing
`_table_caption_metadata(...)` and `score_candidate(...)` path for captions like:

```text
Table 1. (continued)
```

For this implementation, support only conservative continuation evidence:

- caption explicitly says continued, or
- adjacent page is sideways, has compatible table geometry, has no new table number,
  and follows a numbered table candidate from the immediately previous page

If the second case is implemented, set:

- `is_continuation = TRUE`
- `continuation_of_table_number = <previous table number>`
- `table_number = <previous table number>`
- diagnostic evidence in `sideways_detection_signals` or a continuation-specific
  metadata field

Do not merge the continuation grid with the parent table here.

### 6. Acceptance Rules

Sideways candidates should only replace or outrank collapsed upright candidates when
there is clear improvement.

Recommended acceptance checks:

- candidate has caption or conservative continuation evidence
- row count is at least 4
- column count is at least 3
- multiple body rows have numeric values in trailing columns
- candidate has fewer large concatenated cells than the upright explicit candidate
- candidate score is higher than the matching collapsed candidate

Avoid accepting uncaptioned sideways candidates unless their geometry is very strong
and adjacent-page continuation evidence is present.

### 7. Preserve Existing Rescue Behavior

Keep `_rescue_low_quality_page_candidates(...)` and existing text-layout fallback
behavior intact.

The sideways path should be additive:

1. build explicit pymupdf4llm candidates
2. optionally build sideways transformed candidates for that same page
3. run existing low-quality rescue logic
4. select top candidates as usual

If a sideways transformed candidate is better, it should be selected naturally through
score and metadata. If not, existing behavior should remain available.

## Tests

### Unit Tests

Add focused tests in `tests/test_extraction.py`.

Minimum synthetic tests:

1. A portrait page with vertical line directions and a sideways `Table 1` caption
   produces a candidate with:
   - `metadata$table_number == 1`
   - `metadata$orientation_strategy == "sideways_transformed"`
   - `metadata$caption_detection_space == "transformed_coordinates"`
   - a non-collapsed grid

2. A sideways `Table 1. (continued)` caption preserves:
   - `metadata$table_number == 1`
   - `metadata$is_continuation == TRUE`
   - `metadata$continuation_of_table_number == 1`

3. An upright page with ordinary table geometry does not receive sideways metadata
   and still follows the existing extraction path.

4. A page with vertical text but no table caption does not create a false positive
   unless the strong continuation rule applies.

### Real-Paper Regression Check

Run the deterministic parser on the Journal of Periodontology paper:

```bash
table1-parser parse "../testpapers/papers_from_laha/Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009.pdf"
```

Inspect:

- `outputs/papers/<paper_stem>/extracted_tables.json`
- `outputs/papers/<paper_stem>/normalized_tables.json`
- `outputs/papers/<paper_stem>/table_processing_status.json`
- `outputs/papers/<paper_stem>/paper_table_inventory.json`

Expected results:

- Table 1 first page has `table_number = 1`
- Table 1 continuation has `continuation_of_table_number = 1`
- Table 2 first page has `table_number = 2`
- Table 2 continuation has `continuation_of_table_number = 2` if conservative
  continuation evidence is sufficient
- Tables 1 and 2 have separated rows and numeric columns rather than giant
  concatenated cells

### Regression Scan

Run the extraction/parser tests:

```bash
pytest tests/test_extraction.py -q
pytest tests/test_normalization.py -q
pytest tests/test_r_inspection.py -q
```

Run a small real-paper scan on representative papers in `../testpapers`:

- the Journal of Periodontology sideways-table paper
- the CKD NHANES paper
- the Lead exposure NHANES paper
- the GOLD BioAge depression paper
- one ordinary upright paper with good current extraction

The scan should check for:

- no loss of existing detected table numbers
- no new obvious false-positive uncaptioned tables
- no decrease in table count for ordinary upright papers unless clearly justified
- R inspection helpers still resolve tables by `table_number`

## Documentation Updates

If new metadata fields are persisted, update:

- `docs/design/parsing_output_design.md`
- `docs/design/paper_parse_walkthrough.md`
- `docs/r_visualization.md` only if R helpers expose the new fields directly

At minimum, document that sideways extraction is an extraction-time orientation
strategy and that downstream parsed artifacts remain normal table objects.

## Out Of Scope For First Implementation

- merging continued tables
- using visual OCR/image rendering
- interpreting boldface or font weight
- taxonomy changes
- LLM validation
- paper-specific table repair

## Review Questions

- Should transformed cell bboxes remain in transformed coordinates with explicit
  metadata, or should we transform them back to page coordinates before serialization?
- Should adjacent-page continuation inference be included in the first implementation,
  or should we initially require explicit `continued` captions only?
- Should sideways candidates be included in `extracted_tables.json` when they lose to
  upright candidates, or only surfaced through diagnostics?

