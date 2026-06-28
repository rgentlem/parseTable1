# Paper Footnotes Artifact

Design contract for paper-level footnote anchors, definitions, and links.

## Purpose

`paper_footnotes.json` preserves footnote evidence without changing table text,
normalized rows, parsed values, or symbol semantics.

It links visual glyph anchors to candidate footnote definitions when there is
enough local evidence, while keeping unresolved and ambiguous cases explicit.

## File

```text
outputs/papers/<paper_stem>/paper_footnotes.json
```

The parser should write a valid empty artifact when no candidates are found.

## Top-Level Shape

```json
{
  "paper_id": "paper-stem",
  "source_pdf": "paper.pdf",
  "anchors": [],
  "definitions": [],
  "links": [],
  "metadata": {
    "source_artifacts": [],
    "diagnostics": []
  }
}
```

## Anchor Record

An anchor is a glyph attached to a table cell, header, caption, figure caption,
page note, or body-text span.

Required fields:

- `anchor_id`
- `glyph_raw`
- `glyph_key`
- `glyph_kind`
- `glyph_codepoints`
- `source_scope`
- `source_id`
- `page_num`
- `confidence`

Optional fields:

- `table_id`
- `visual_id`
- `row_idx`
- `col_idx`
- `source_role`
- `text_context`
- `attached_to_text`
- `bbox`
- `coordinate_frame`
- `source_artifact`
- `notes`

Allowed `source_scope` values:

- `table_cell`
- `table_caption`
- `table_note`
- `figure_caption`
- `page_note`
- `body_text`

For table cells and headers, use `source_scope = "table_cell"` and distinguish
`source_role` values such as `body_cell`, `row_label`, or `column_header`.

## Definition Record

A definition is a candidate explanatory note that may define one or more glyphs.

Required fields:

- `definition_id`
- `glyph_raw`
- `glyph_key`
- `glyph_kind`
- `glyph_codepoints`
- `source_scope`
- `source_id`
- `page_num`
- `raw_text`
- `clean_text`
- `confidence`

Optional fields:

- `definition_text`
- `table_id`
- `visual_id`
- `bbox`
- `line_index`
- `source_artifact`
- `notes`

Definition candidates may be built from typed source lines before they are
promoted into definition records. Source lines should preserve raw text, page,
optional bbox and page height, source scope, source ID, table ID, visual ID, and
source artifact. These input lines are not a persisted top-level artifact.
The parse command now builds these source lines from PyMuPDF page text geometry,
then classifies local candidates as table notes or page-bottom notes.

`raw_text` preserves extracted text. `clean_text` is normalized only enough to
support matching and review. `definition_text` may drop the leading glyph when
that split is unambiguous.

## Link Record

A link records the relationship between one anchor and zero, one, or multiple
candidate definitions.

Required fields:

- `link_id`
- `anchor_id`
- `glyph_key`
- `link_status`
- `candidate_definition_ids`
- `link_basis`
- `confidence`

Optional fields:

- `definition_id`
- `scope_distance`
- `notes`

Allowed `link_status` values:

- `resolved`
- `ambiguous`
- `unresolved`

`definition_id` is present only for resolved links. Ambiguous links keep all
candidates in `candidate_definition_ids`. Unresolved links keep the anchor
visible with an empty candidate list.

## Glyph Fields

The glyph fields are evidence, not interpretation.

- `glyph_raw`: exact visible marker text
- `glyph_key`: canonical key used for matching
- `glyph_kind`: broad type, such as `letter`, `number`, `symbol`, `asterisk`,
  or `unknown`
- `glyph_codepoints`: Unicode codepoints for `glyph_raw`
- `confidence`: confidence for the glyph detection or definition split

`glyph_key` should normalize common presentation variants, such as superscript
digits to plain number keys, case variants to lowercase letter keys, and common
symbols to stable names. Keep `glyph_raw` and `glyph_codepoints` unchanged.
Do not encode footnote meaning in `glyph_key`.

## Linking Rule

Initial linking should prefer matches in this order:

1. same table
2. same visual object
3. same page
4. paper-level fallback

Record the chosen evidence in `link_basis`. Do not drop lower-confidence or
ambiguous evidence when it is useful for review.

## Current Consumption Status

`paper_footnotes.json` is review evidence only. Downstream parser stages should
not consume footnote links to rewrite table text, parsed values, row semantics,
or column semantics yet.

Real-paper review showed useful same-table resolved links, but also unresolved
p-value markers, ambiguous repeated glyph definitions, and noisy page-note
candidates from journal/download boilerplate and repeated marginal text. Treat
all links as inspectable evidence until page-note pruning and repeated-text
handling are stronger.

## R Surface

R loads this artifact as data first, then exposes review helpers.

Current R helpers:

- `footnote_anchors_df()`
- `footnote_definitions_df()`
- `footnote_links_df()`
- `show_paper_footnotes()`

Tableone-aligned object:

- `ObservedFootnotes`
- `Anchors`
- `Definitions`
- `Links`
- `MetaData`

`ObservedTableOne` attaches table-specific records as `Footnotes`.
