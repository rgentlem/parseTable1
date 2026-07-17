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
  "footers": [],
  "definitions": [],
  "links": [],
  "metadata": {
    "source_artifacts": [],
    "diagnostics": []
  }
}
```

## Footer Record

A footer is a table-local footer region detected from extracted table geometry
or from positioned `paper_text_stream.json` line groups that were classified as
local table footers.
It is persisted so R review can validate the footer boundary before reviewing
definition splitting or anchor links. Footer records preserve the unsplit raw
region; definition records split marker meanings from that same region.

Required fields:

- `footer_id`
- `table_id`
- `page_num`
- `source_scope`
- `source_artifact`
- `detection_basis`
- `start_row_idx`
- `end_row_idx`
- `raw_text`
- `rows`

Optional fields:

- `visual_id`
- `notes`

Each `rows` item records:

- `row_idx`
- `raw_cells`
- `text`

Footer detection consumes established ownership rather than rediscovering it.
Rows inside the extracted grid come only from the matching final
`TableRegion.footer_note_rows`. If the visual footer is outside that grid,
`paper_text_stream.json` supplies only the positioned lines named by the final
`body_footer` candidate's `TableBoundaryProposal.following_text_line_ids`.
`TableRegion` has already accepted those adjacent final-rule lines using
mandatory typography, positioned prose continuity, and preceding-data
evidence; the footnote stage does not decide ownership again. They are
persisted with
`source_artifact = "paper_text_stream.json"` and
`detection_basis = "table_boundary_final_rule_following_lines"`. Source line
IDs, bounding boxes, font evidence, and unsplit raw text remain available.

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
Table-cell anchors should come from cell text annotations that were already
built from page-furniture-filtered character geometry. Their `anchor_id` is
exactly the source `CellTextAnnotation.annotation_id`, not a second positional
identity. Anchor notes retain the source annotation type, such as
`superscript`, while that stable ID joins directly to the complete source
character indices, span references, fonts, bbox, and attachment evidence in
`cell_text_annotations.json`. A candidate without an annotation ID is omitted
with a diagnostic rather than assigned a fallback ID.

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
- Subscript annotations remain inspectable in `cell_text_annotations.json` but
  should not be promoted to `FootnoteAnchor` records. Table footnote anchors
  should come from superscript markers, inline markers, captions, or footer
  definitions, not from subscript notation. Preserve the original glyph case in
  the annotation and any retained `glyph_raw` evidence for debugging.
- Multi-letter alphabetic subscript text such as `P_Begg` or `P_Egger` is one
  example of this general subscript suppression rule; letter footnote markers
  are single visible superscript or inline glyphs.

## Marker Interpretation

This artifact does not infer marker meaning. After math/unit notation has been
rejected, observed superscripts and inline markers are carried forward as
anchors and linked only to explicit candidate definitions. If no explicit
definition is found, the link remains unresolved. Conventional meanings, such
as p-value significance-star thresholds, belong in a later interpretation layer
that consumes the preserved anchors, table-local note blocks, and explicit
definition evidence.

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
- `marker_evidence_type`
- `marker_bbox`
- `marker_confidence`
- `marker_metadata`
- `table_id`
- `visual_id`
- `bbox`
- `line_index`
- `source_artifact`
- `notes`

Definition candidates are built only from source blocks that have already been
scoped as table-local metadata, caption text, or another explicit local note
source. Generic body-text and page-bottom blocks are not promoted to table-note
definitions in this artifact. Source blocks should preserve raw text, page,
optional bbox and page height, source scope, source ID, table ID, visual ID, and
source artifact. Extracted table footer regions are persisted in `footers`;
definition source lines are then built from the matching final
`TableRegion.footer_note_rows`. Within that region, a row that starts or embeds
a definition marker opens a table-note block, and adjacent following rows
without a new marker are appended as continuation text until the next marker
block.
`paper_text_stream.json` provides page-furniture-filtered visual lines with
line bbox, page/column order, dominant font name, dominant font size, minimal
span records, and document-level font-style counts.
`find_table_footer_definition_lines()`
consumes only the positioned lines already attached to the final retained rule
through `TableBoundaryProposal.following_text_line_ids`. It uses exact raised
marker geometry, table-local type size, and physical line count to decide
whether that one adjacent band is a footer. Same-font size variation of at most
0.2 PDF points remains one band so harmless 8.0/7.9-point jitter cannot truncate
a definition paragraph. The retained group is persisted in `footers` before it
is split into definition records. This keeps review artifacts aligned when the
extraction grid omits a visual table footer but the layout-aware text stream
captures it, without scanning arbitrary text below the table bbox.
An exact standalone visual-object DOI ending in `.tNNN` or `.gNNN` terminates
this adjacent group before the DOI line. The line remains unchanged in
`paper_text_stream.json` and belongs to the matching caption-bearing
`PaperVisual`; it is not footer or definition text.
A one-character definition marker qualifies as smaller and raised when its
font is at most 86% of the line's dominant size and its vertical center is
raised by at least 12% of that size. At the beginning of a physical source line
it does not depend on punctuation from the preceding line; an embedded marker
still requires a preceding definition boundary. The definition record keeps
the marker's source line ID, bbox, font sizes, and physical-line-start flag.
Final `ResolvedTableSet` membership supplies shared visual identity for accepted
continued fragments, including uncaptioned terminal fragments. A terminal
footer can therefore resolve anchors on an earlier fragment only when both
source table IDs belong to the same accepted `integrated_continuation`.
Rejected continuation candidates do not receive that shared scope. The older
`Table1ContinuationGroup` review artifact is not consumed by the footnote path.
Remaining page-text blocks are not consumed by `paper_footnotes.json`; a later
paper-note layer can own them if needed.
Candidate source blocks may start with a marker, or may contain embedded marker
definitions after preceding abbreviation or significance prose, such as
`significance. a Represents ... b Represents ...`. When the visual PDF has a
superscript marker but PyMuPDF raw text runs that marker into the following
word, the split is driven by positioned character evidence: a smaller raised
glyph at a definition boundary. The damaged extracted word is kept only as
source text provenance. Extracted-table footer rows can also contribute weaker
marker evidence when a confirmed footer cell starts or embeds a marker-shaped
prefix such as a symbol run or a letter before a statistical expression.
Bracketed and parenthesized markers such as `[a]` and `(a)` are canonicalized
to the visible glyph before matching.

Caption text contributes definitions only from a trailing explicit symbol
block that begins after completed caption prose at a punctuation boundary. The
same symbol-block parser used for local notes then splits that suffix, including
markers attached directly to their bodies such as `*p < 0.05`. The complete
caption remains the definition's `raw_text`. Captions are not scanned with the
older broad letter/number marker regex: ordinary prose after a colon, years,
abbreviations, and symbols that decorate the caption itself are not definition
evidence.

Known symbol markers such as `†`, `‡`, `§`, `¶`, `#`, brace-like marker glyphs,
and asterisk runs are structural footnote-definition evidence when they start a
local table/footer definition and are followed by any non-empty definition
body. Do not require the body to contain p-value wording or other semantic
vocabulary. Vertical-bar glyphs observed as superscript/small annotations are
suppressed from the anchor inventory as non-footnote artifacts unless stronger
local definition evidence later justifies treating them as table-note markers.
Statistical footer lines can define repeated asterisk runs such as `*`, `**`,
and `***` in one comma-separated line; these are split into separate definition
records with `asterisk:1`, `asterisk:2`, and `asterisk:3` glyph keys. P-value
semantics are not inferred by this artifact.
Distinct symbol markers in one contiguous footer block, such as `* Race ...
†Education ... ‡Smoking ... §Income ...`, are split into separate definition
records without requiring whitespace between the glyph and definition body.
Textual marker definitions such as `The asterisk indicates ...` are canonical
definition evidence for a single `*` marker when they appear in a local footer
block.
Page-furniture filtering is not a late definition-candidate cleanup step:
PDF-derived definition blocks must be built from already filtered positioned
characters. Extracted-table footer rows are already table-local source evidence;
they come from extracted tables that have received the same page-furniture mask
before grid construction.

`raw_text` preserves extracted text. `clean_text` is normalized only enough to
support matching and review. `definition_text` may drop the leading glyph when
that split is unambiguous. When multiple definitions come from one table footer
block, each definition keeps the full footer block in `raw_text` and the marker
specific meaning in `definition_text`. When a split came from structured marker
evidence, the definition record carries `marker_evidence_type`, marker bbox,
marker confidence, and available marker metadata such as font size or footer
row/column position.

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
2. same accepted visual object or resolved continuation membership
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

For two different table fragment IDs, the second rank is available only when
the final `ResolvedTableSet` places both IDs in one accepted integrated table.
Printed table-number equality or a rejected continuation decision is not enough.
The persisted `scope_distance` remains `same_visual`, preserving the existing
link ranking and inspection contract.

If no explicit definition exists for `*`, `**`, or `***`, the linker should
leave the anchor unresolved. Conventional p-value-star thresholds should be
handled by a later interpretation layer, not by the footnote extraction/link
artifact. When a caption or footer explicitly prints those thresholds, the
link resolves to that preserved source text; the parser does not infer a
threshold the PDF did not state.

## Current Consumption Status

`paper_footnotes.json` is review evidence only. Downstream parser stages should
not consume footnote links to rewrite table text, parsed values, row semantics,
or column semantics yet.

Real-paper review showed useful same-table resolved links, but also unresolved
p-value markers, ambiguous repeated glyph definitions, and noisy page-note
candidates from journal/download boilerplate and repeated marginal text. The
page-furniture artifact now suppresses repeated page-region noise before
table-cell annotations and PDF definition blocks are built, but links remain
inspectable evidence rather than downstream parse inputs.

Metadata records the page-furniture filter stage:

- `page_furniture_filter_stage`

Metadata also records pre-footnote suppression counts:

- `math_unit_anchor_suppression_count`
- `subscript_anchor_suppression_count`
- `word_like_subscript_anchor_suppression_count`

## R Surface

R loads this artifact as data first, then exposes review helpers.

Current R helpers:

- `footnote_anchors_df()`
- `footnote_footers_df()`
- `footnote_definitions_df()`
- `footnote_links_df()`
- `show_paper_footnotes()`

When filtered by `table_number` or `table_index`, R helpers match both the
selected fragment `table_id` and the paper visual ID. This matters for
continued tables: a footer may live on `Table 1. (continued)` while anchors or
the public review request refer to the first Table 1 fragment.
Shared visual IDs across source fragments come from accepted
`ResolvedTableSet` membership; rejected continuations remain outside that
review scope.

Tableone-aligned object:

- `ObservedFootnotes`
- `Footers`
- `Anchors`
- `Definitions`
- `Links`
- `MetaData`

`ObservedTableOne` attaches table-specific records as `Footnotes`.
