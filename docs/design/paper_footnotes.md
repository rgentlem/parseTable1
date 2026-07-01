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
Table-cell anchors whose page-coordinate bbox overlaps repeated page furniture
are suppressed before linking and counted in metadata.

## Pre-Footnote Classification

Footnote anchor detection should be downstream of a small set of stronger
non-footnote classifications. The first required classification is mathematical
or unit notation. If a superscript/subscript glyph is best explained as part of
a number, formula, measurement unit, or exponent, it should not be promoted to a
`FootnoteAnchor`.

Initial math/unit exponent rule:

- Apply before glyph-key matching and before unresolved-link creation.
- Use only structural text evidence from the annotation and attached cell text,
  not paper-specific vocabulary.
- Treat a numeric superscript or subscript as math/unit notation when it is
  directly attached to a numeric base or unit-like expression. Portable examples
  include `10^9`, `10^6`, `m^2`, `cm^3`, `kg/m^2`, `mL/min/1.73m^2`, `x10^9/L`,
  `×10^9/L`, `CO₂`, and single-letter exponent/statistic notation such as
  `I²`.
- Evidence can come from `attached_to_text` ending in a numeric base, a
  multiplication-by-ten pattern, a slash-separated unit expression, or a
  letter-unit token immediately before the superscript.
- This classification should be conservative. If the same glyph has a local
  table-note definition and the surrounding text is not unit/formula-like, keep
  it as a footnote anchor.
- Suppressed math/unit markers should remain inspectable through
  `cell_text_annotations.json`; a future metadata counter or dedicated
  annotation classification field may expose how many candidate anchors were
  rejected for this reason.
- Multi-letter alphabetic subscript text such as `P_Begg` or `P_Egger` remains
  inspectable in `cell_text_annotations.json` but should not be promoted to a
  `FootnoteAnchor`; letter footnote markers are single visible glyphs.

## P-Value Significance Stars

After math/unit notation has been rejected, asterisks attached to p-value cells
should be treated as statistical-significance markers even when no explicit
footer definition is found.

Initial p-value star rule:

- Apply only when the anchor is attached to a p-value cell, p-value column, or
  p-value-like text such as `<0.001`, `0.04`, `P value`, `_p_`, or a column
  whose `ColumnHeaderSchema` leaf/header path identifies it as a p-value.
- Preserve the ordinary footnote-linking path first. If a local table/footer
  definition exists for `*`, `**`, or `***`, link to it and use the explicit
  definition as the source of meaning.
- If no explicit definition exists, emit a structured fallback interpretation
  rather than leaving the marker as an unresolved footnote. The fallback should
  record that the meaning is conventional and inferred from p-value context.
- The conventional fallback is:
  - `*`: p-value threshold at `10^-1`
  - `**`: p-value threshold at `10^-2`
  - `***`: p-value threshold at `10^-3`
- Do not apply this fallback to asterisks attached to row labels, captions,
  bibliography/source names, non-p-value numeric cells, or prose unless the
  p-value context is explicit.
- Keep the visual marker evidence unchanged in `cell_text_annotations.json`.
  Any downstream R object should expose both the observed marker and whether its
  meaning came from an explicit table definition or the conventional fallback.

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

Definition candidates may be built from typed source blocks before they are
promoted into definition records. Source blocks should preserve raw text, page,
optional bbox and page height, source scope, source ID, table ID, visual ID, and
source artifact. These input blocks are not a persisted top-level artifact.
The parse command builds source blocks first from extracted table footer rows,
then from PyMuPDF page text geometry. Extracted-table footer rows are identified
structurally: after the last value-matrix row, a row that starts or embeds a
definition marker opens a table-note block, and adjacent following rows without
a new marker are appended as continuation text until the next marker block.
PyMuPDF geometry is consumed as contiguous text blocks rather than isolated
lines. `find_table_footer_definition_blocks()` classifies complete PDF text
blocks as table-local footer blocks when they sit just below a table bbox,
overlap the table horizontally, and do not cross into the next table region.
Continuation-group identity can supply the parent visual ID for an uncaptioned
continued fragment, so a footer on the terminal fragment can resolve anchors on
earlier fragments of the same visual table. Remaining page-text blocks can be
classified as page-bottom notes.
Candidate source blocks may start with a marker, or may contain embedded marker
definitions after preceding abbreviation or significance prose, such as
`significance. a Represents ... b Represents ...`. Bracketed and
parenthesized markers such as `[a]` and `(a)` are canonicalized to the visible
glyph before matching.

Known symbol markers such as `†`, `‡`, `§`, `¶`, `#`, `|`, and asterisk runs
are structural footnote-definition evidence when they start a local table/footer
definition and are followed by any non-empty definition body. Do not require the
body to contain p-value wording or other semantic vocabulary. Statistical
footer lines can define repeated asterisk runs such as `*`, `**`, and `***` in
one comma-separated line; these are split into separate definition records with
`asterisk:1`, `asterisk:2`, and `asterisk:3` glyph keys. P-value semantics are
special only for the conventional fallback applied to unresolved asterisk
anchors after explicit definition matching fails.
Distinct symbol markers in one contiguous footer block, such as `* Race ...
†Education ... ‡Smoking ... §Income ...`, are split into separate definition
records without requiring whitespace between the glyph and definition body.
Before candidate promotion, page-text blocks overlapping
`paper_page_furniture.json` ignored regions are suppressed and counted in
metadata. Extracted-table footer rows are already table-local source evidence
and are not suppressed by page-furniture geometry.

`raw_text` preserves extracted text. `clean_text` is normalized only enough to
support matching and review. `definition_text` may drop the leading glyph when
that split is unambiguous. When multiple definitions come from one table footer
block, each definition keeps the full footer block in `raw_text` and the marker
specific meaning in `definition_text`.

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
- `inferred_meaning`
- `scope_distance`
- `notes`

Allowed `link_status` values:

- `resolved`
- `ambiguous`
- `inferred`
- `unresolved`

`definition_id` is present only for resolved links. Ambiguous links keep all
candidates in `candidate_definition_ids`. Unresolved links keep the anchor
visible with an empty candidate list. Inferred links have no definition ID and
carry an `inferred_meaning` object.

`inferred_meaning` is used only when a stronger non-footnote classification and
explicit definition matching have already run. The first supported inference is
`p_value_significance` from `conventional_p_value_star`, with fields for
`meaning_text`, `marker_count`, numeric `p_value_threshold`,
`threshold_notation`, and evidence strings. This preserves the observed marker
while distinguishing conventional interpretation from explicit table-footer
definitions.

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

Numeric superscripts attached to row-label cells are often bibliographic
citations, especially in study/source tables. Do not resolve these through
paper-level footnote fallback. They should link only to a local table/visual
definition; otherwise leave them unresolved with a note that they may be
bibliographic references. Bibliography matching should be handled by a separate
citation/reference artifact, not by the footnote linker.

If no explicit definition exists for `*`, `**`, or `***`, the linker may emit an
`inferred` link only when the anchor is a body-cell asterisk in p-value context.
The conventional thresholds are `10^-1`, `10^-2`, and `10^-3`, respectively.
Explicit same-table, same-visual, same-page, or paper-level definitions always
take precedence over this fallback.

## Current Consumption Status

`paper_footnotes.json` is review evidence only. Downstream parser stages should
not consume footnote links to rewrite table text, parsed values, row semantics,
or column semantics yet.

Real-paper review showed useful same-table resolved links, but also unresolved
p-value markers, ambiguous repeated glyph definitions, and noisy page-note
candidates from journal/download boilerplate and repeated marginal text. The
page-furniture artifact now suppresses repeated page-region noise before
linking, but links remain inspectable evidence rather than downstream parse
inputs.

Metadata records the page-furniture filter:

- `page_furniture_anchor_suppression_count`
- `page_furniture_suppressed_anchor_cluster_ids`
- `page_furniture_definition_line_suppression_count`
- `page_furniture_suppressed_definition_cluster_ids`

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
