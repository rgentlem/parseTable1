# Cell Text Annotations Implementation Plan

Short checklist for implementing `cell_text_annotations.json`.

Design note: `docs/design/cell_text_annotations.md`.
Rotated-table follow-up: `docs/implementation/rotated_cell_text_annotations_implementation_plan.md`.

## Ground Rules

- Keep this as an extraction-side sidecar.
- Do not rewrite raw cell text.
- Do not change normalization or value parsing in the first pass.
- Do not link markers to footnote definitions yet.

## Steps

1. [x] Schema and payload
   - Add `CellTextAnnotation` and `CellTextAnnotationTable` Pydantic models.
   - Export them from `table1_parser.schemas`.
   - Add a payload helper for JSON serialization.

2. [x] Empty artifact wiring
   - Add `cell_text_annotations` to `PaperParseArtifacts`.
   - Write `cell_text_annotations.json` from `parse`.
   - Start with an empty list when no annotations are detected.

3. [x] Character evidence
   - Extend PyMuPDF char extraction to preserve useful span metadata when available.
   - Keep at least text, bbox, font size or char height, and page number.
   - Preserve existing char fields used by grid refinement.

4. [x] Cell-bbox detection
   - Match chars to extracted table cells using cell bboxes.
   - Flag likely superscripts/subscripts by vertical offset and small glyph size.
   - Include row-label and column-header cells, not only body value cells.
   - Record `inline_marker` when attachment is clear but vertical evidence is weak.
   - Emit table-level diagnostics when cell bboxes or coordinate frames are missing.

5. [x] R loading
   - Add required `cell_text_annotations` path in `paper_output_paths()`.
   - Load it in `load_paper_outputs()`.
   - Add `cell_text_annotations_df(...)`.
   - Add `show_cell_text_annotations(...)`.
   - Leave LaTeX header rendering as a later consumer of this artifact plus `ColumnHeaderSchema`.

6. [x] Real-paper annotation tests
   - Parse the real `metabolic.pdf` fixture.
   - Verify `cell_text_annotations.json` has annotations.
   - Verify R loads and displays the saved annotations.
   - Keep R fixtures limited to the current artifact contract, not synthetic annotation behavior.

7. [x] Real-paper example scan
   - Ran all PDFs in `testpapers/papers_from_johnny`.
   - Annotation-rich examples: `stroke.pdf`, `Sarcopenia.pdf`, `metabolic.pdf`, `cardiovascular.pdf`.
   - This directory has superscript and inline-marker examples, but no subscript-heavy paper.

## Later

- Support rotated/local-coordinate refined tables; checklist:
  `docs/implementation/rotated_cell_text_annotations_implementation_plan.md`.
- Add a real subscript-heavy paper when one is available.
- Link markers to footnote text.
- Let normalization or value parsing consume annotations explicitly.
