# Cell Text Annotations

Artifact for superscripts, subscripts, and small marker symbols attached to
extracted table cells, including row labels and column headers.

## Purpose

Keep visual marker evidence separate from cell text and value parsing.

The parser should preserve:

- raw cell text in `extracted_tables.json`
- visual marker evidence in `cell_text_annotations.json`
- normalized text and parsed values unchanged until a later explicit consumer is added

## Known Gap And Required Consumer

The sidecar identifies attached glyph geometry, but the same glyph can still be
embedded in the extracted cell string, for example a p-value ending in a
superscript marker. Detection alone therefore does not yet give downstream
header and value parsing clean base text.

The required logical candidate representation should carry:

- unchanged source `raw_text`
- marker-free `base_text`
- the annotation IDs and visible glyphs associated with the removed characters

Marker removal must be supported by exact character/span geometry. If the
source characters cannot be associated reliably, the glyph remains in
`base_text` and a diagnostic is recorded. `ExtractedTable.text` is never
rewritten. Header assembly, row-label interpretation, and value parsing may use
`base_text`; footnote resolution continues to use the linked marker records.

## File

```text
outputs/papers/<paper_stem>/cell_text_annotations.json
```

Sparse table-level artifact:

```json
[
  {
    "table_id": "paper-p5-t0",
    "page_num": 5,
    "n_rows": 12,
    "n_cols": 5,
    "annotations": [
      {
        "annotation_id": "paper-p5-t0:marker:0",
        "row_idx": 4,
        "col_idx": 4,
        "text": "b",
        "glyph_key": "letter:b",
        "annotation_type": "superscript",
        "text_latex": "^{b}",
        "bbox": [506.2, 214.1, 510.4, 218.3],
        "attached_to_text": "<0.001",
        "source_cell_id": "paper-p5-t0:r4:c4",
        "source_char_indices": [942],
        "source_span_references": [
          {"line_id": "page-5-line-31", "span_index": 2}
        ],
        "font_names": ["MyriadPro-Regular"],
        "font_sizes": [5.6],
        "confidence": 0.91
      }
    ],
    "metadata": {
      "source": "pymupdf_char_geometry",
      "coordinate_frame": "page"
    }
  }
]
```

Recommended `annotation_type` values:

- `superscript`
- `subscript`
- `inline_marker`
- `unknown_marker`

## Detection

Detection is geometry-first:

- character bbox within or near an extracted table cell bbox
- smaller glyph height than nearby text
- raised or lowered position relative to the local text run
- close attachment to adjacent text
- correct coordinate frame

Inline marker detection also allows same-height trailing glyphs when they are
attached to numeric or comparator-like text, including values containing `±`.
This covers marker-font symbols that a PDF exposes as ordinary-looking
characters, while still keeping subscript notation such as `S_I` and `AIR_g`
as `subscript` annotations rather than footnote anchors.

Annotation metadata may include source fonts and raw glyph text when extraction
normalized a symbol-font character. That metadata is diagnostic evidence only;
the annotation `text` remains the visible marker text used by downstream
footnote linking.

Each detected annotation is also the canonical early marker occurrence. Its
`annotation_id` distinguishes repeated uses of the same glyph, while
`glyph_key` provides shared Unicode-normalized identity for later footer
matching. `source_char_indices` and `source_span_references` resolve into
`paper_positioned_document.json`; `source_cell_id` is a physical cell
association, not a later logical header/body attachment. Marker meaning is not
decided here, and the source glyph is not removed from cell text.

For rotated or sideways-transformed tables, annotation `bbox` values use the
same coordinate frame as the table cell bboxes, recorded in table-level
`metadata.coordinate_frame`. The extractor persists the transform source bbox
and rotation direction so page characters can be transformed into that frame
before cell matching.

For transformed frames, annotation table metadata also records the transform
inputs used by detection: `geometry_transform_source_bbox`,
`geometry_transform_transposed`, `geometry_transform_applied`, and
`rotation_direction`. Missing transform inputs are reported in
`metadata.diagnostics`.

Do not use paper-specific vocabulary.

## R Surface

R loads this parse artifact through `load_paper_outputs()` and exposes:

- `cell_text_annotations_df(outputs, table_number = NULL, table_index = NULL)`
- `show_cell_text_annotations(paper_dir, table_number = 1L, table_index = NULL)`

R should display persisted evidence only, not infer marker meaning.

Column-header LaTeX rendering should be derived later by joining this artifact
to `ColumnHeaderSchema`; it should not be hard-coded into extraction.

## First Implementation

1. Add R loading and compact inspection helpers.
2. Extend support for rotated/local-coordinate refined tables.
3. Leave normalization, value parsing, and footnote linking unchanged until an explicit consumer is added.
