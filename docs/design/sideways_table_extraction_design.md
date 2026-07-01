# Sideways Table Extraction Design

## Purpose

Some PDFs contain wide tables that are visually landscape, but the PDF page itself is
still portrait and has no page-level rotation. In these files, the table text is
drawn sideways inside an otherwise portrait page. The extractor must treat this as a
layout problem, not as a downstream parsing problem.

This design covers how to detect and extract those sideways tables while preserving
the existing parser architecture:

PDF -> ExtractedTable -> NormalizedTable -> TableDefinition -> ParsedTable

## Motivating Failure

The Journal of Periodontology NHANES periodontitis paper has this pattern. The PDF
pages containing Tables 1 and 2 report portrait page geometry and `rotation=0`, but
the table content is sideways.

Current behavior:

- Table 1 first page is extracted as an uncaptioned failed layout candidate.
- Table 1 continuation is extracted as another uncaptioned failed layout candidate.
- Table 2 first page is extracted as an uncaptioned failed layout candidate.
- Table 2 continuation is extracted as another uncaptioned failed layout candidate.
- The captions are visible in raw text, but not attached to the table candidates.
- Body rows and columns are collapsed into large cells because the extractor is using
  the page axes instead of the table axes.

This cannot be repaired reliably in normalization or semantic parsing because the
canonical grid is already wrong.

## Design Goals

- Detect sideways table content even when the PDF page is not marked as rotated.
- Build table candidates in the table's visual coordinate system.
- Match captions in the same coordinate system used for table detection.
- Return a normal `ExtractedTable` object so downstream stages do not need to know
  whether the source table was upright or sideways.
- Preserve raw cell text and extraction metadata.
- Support continued tables using the paper's table number as the stable identifier.
- Keep the path deterministic and inspectable.

## Non-Goals

- Do not add paper-specific rules for the Journal of Periodontology paper.
- Do not use the LLM to reconstruct raw table grids.
- Do not change `NormalizedTable`, `TableDefinition`, or `ParsedTable` semantics.
- Do not treat table images as the primary representation for parsing.
- Do not merge continued tables in this extraction step.

## Sideways Content Detection

The extractor should add a page-level or candidate-level check for sideways table
geometry. A page can be considered a sideways-table candidate when several of these
signals are present:

- The page has portrait dimensions and `rotation=0`.
- Text blocks that contain table/caption language are narrow in x and tall in y.
- A `Table N` or `Table N. (continued)` caption appears as a vertical strip.
- PyMuPDF exposes text blocks whose line directions match a vertical text stream
  (`vertical_text_up` or `vertical_text_down`), and those blocks occupy a distinct
  page column or region from upright body text.
- Numeric-heavy table body text is arranged in repeated vertical bands.
- Candidate table content spans a large part of the y axis but only a limited x band
  per logical row or group.
- Standard upright extraction produces a collapsed grid with few columns and large
  multi-line cells.

The detection should be conservative. A sideways extraction path should be attempted
when there is a plausible table/caption signal, or when collapsed-grid diagnostics
strongly suggest that row and column axes are transposed.

## Coordinate Strategy

For sideways candidates, the extractor should create a transformed layout view before
table detection.

Conceptually:

- Use the original PDF words/blocks as the source of truth.
- Prefer explicit PyMuPDF text-block geometry with matching line direction to
  define the sideways table region. This is especially important on two-column
  pages where a rotated table plus footer occupies one column and ordinary article
  text occupies the other.
- Rotate or transpose their bounding boxes into a visual table coordinate system.
- Run caption detection and table-grid construction in that transformed coordinate
  system.
- Build cells from the transformed geometry.
- Store enough metadata to identify that sideways extraction was used.

The resulting `ExtractedTable` should still use normal row and column ordering. The
downstream pipeline should receive the same conceptual object it receives for upright
tables.

## Caption And Table Number Handling

Caption detection must run in the same coordinate system as table detection. For
sideways pages, looking for captions in untransformed page coordinates is not enough.

Expected behavior:

- `Table 1.` on the first page should attach `table_number=1`.
- `Table 1. (continued)` should attach `table_number=1` and continuation metadata.
- `Table 2.` should attach `table_number=2`.
- A following page with compatible geometry and no new table number may be marked as
  a continuation when the evidence is strong.

Continuation metadata should use the actual paper table number, not the extracted
table list index.

## Grid Reconstruction Requirements

The sideways extraction path should produce a usable grid before normalization.

For Table 1-like wide descriptive tables, the grid should preserve:

- the left characteristic/variable column
- grouped column headers
- repeated subcolumns such as `n`, weighted `n`, percent, and standard error
- body rows as separate rows rather than large concatenated cells

For Table 2-like wide prevalence/category tables, the grid should preserve:

- the left characteristic/variable column
- category header groups
- repeated numeric subcolumns
- separate body rows and level rows

The extractor does not need to infer final semantic roles here. It only needs to
return a faithful structured grid.

## Quality Gates

A sideways table candidate should be accepted only when the rebuilt grid is clearly
better than the collapsed upright candidate.

Useful acceptance signals:

- more plausible column count
- more plausible row count
- fewer very large concatenated cells
- stable multi-column alignment
- numeric values distributed across trailing columns
- caption or continuation evidence attached
- header-like top rows preserved

If the sideways path does not improve the candidate, the extractor should keep the
existing result and record diagnostics.

## Diagnostics

Extraction metadata should make this inspectable from JSON and R.

Recommended metadata fields:

- `orientation_strategy`: `upright` or `sideways_transformed`
- `sideways_candidate`: boolean
- `sideways_detection_signals`: short list of matched signals
- `grid_refinement_source`: include sideways extraction/refinement when used
- `caption_detection_space`: `page_coordinates` or `transformed_coordinates`
- `continuation_of_table_number`: integer or null

These diagnostics should be written as normal parse artifacts rather than only being
available in logs.

## Testing Expectations

Add a targeted regression test or inspection fixture for the Journal of
Periodontology NHANES paper without committing large generated outputs.

Minimum expectations:

- Table 1 is detected with `table_number=1`.
- Table 1 continuation is detected as a continuation of table 1.
- Table 2 is detected with `table_number=2`.
- Table 2 continuation is detected as a continuation of table 2 when supported by
  caption or geometry evidence.
- Extracted grids for Tables 1 and 2 have separate rows and meaningful numeric
  columns rather than collapsed text cells.
- Existing upright table extraction behavior does not regress on representative
  papers in `testpapers`.

## Implementation Order

1. Add diagnostics that expose when a candidate looks sideways/collapsed.
2. Add the coordinate transformation path for sideways candidates.
3. Run caption detection and table detection in transformed coordinates.
4. Return normal `ExtractedTable` objects with orientation metadata.
5. Add continuation metadata based on table number and adjacent-page evidence.
6. Add focused tests and run a small real-paper regression scan.

## Design Decision

Sideways tables should be handled in the extraction layer. The parser should not try
to infer a table from already-collapsed cells, because that would mix extraction with
semantic reconstruction and would make the result less inspectable.
