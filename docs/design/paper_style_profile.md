# Paper Style Profile

`paper_style_profile.json` summarizes document-level conventions that affect
footnotes, citations, captions, and visual references. It is a review and
planning artifact. It does not rewrite extracted table text, resolve footnote
links, or decide bibliography entries by itself.

The profile is built after the parser has already built the underlying evidence
artifacts:

```text
paper_text_stream.json
extracted_tables.json
paper_footnotes.json
paper_bibliography.json
paper_visual_inventory.json
paper_references.json
-> paper_style_profile.json
```

The intent is similar to `paper_page_furniture.json`: collect repeated
structural evidence once, expose counts and examples, and let downstream review
or later deterministic stages use that evidence without adding paper-specific
exceptions.

## Dimensions

The artifact records five style dimensions:

- `footnote_marker_style`
  Counts observed footnote anchors and definitions by marker family: numeric,
  letter, symbol, asterisk, or unknown. It also records source scopes,
  link-status counts, and definition-prefix formats such as space-, colon-,
  bracket-, or parenthesis-prefixed definitions.

- `bibliography_reference_style`
  Counts whether the paper bibliography is numbered, unnumbered/hanging-indent,
  mixed, or absent. It also records bibliography label formats and observed
  numeric reference-marker link statuses.

- `table_caption_placement`
  Uses extracted-table caption metadata plus nearby positioned text lines to
  estimate whether table captions appear above or below table bodies.

- `figure_caption_evidence`
  Records figure caption text observed through the current visual inventory or
  text stream. Figure image geometry is not extracted yet, so figure caption
  placement remains geometry-unavailable rather than inferred.

- `visual_reference_style`
  Counts prose table/figure reference wording, such as `Table 1`, plural table
  references, `Fig. 1`, and `Figure 1`, along with visual-reference resolution
  statuses.

Each dimension includes:

- `likely_style`
- `confidence`
- `count_by_style`
- `count_by_source`
- `secondary_counts`
- compact supporting `evidence`
- `notes`

If no evidence exists for a dimension, the likely style is `unknown` with zero
confidence.

## Checks

The artifact also includes `checks`, which compare inferred style against the
available parse reality. These checks are deliberately simple and inspectable.

Current checks include:

- `bibliography_numbering_alignment`
  If the likely bibliography style is numbered/indexed, this verifies that
  bibliography entries actually carry `reference_number` values. If the likely
  style is unnumbered/hanging-indent, it reports the numbered versus unnumbered
  entry counts.

- `footnote_link_coverage`
  Reports whether the inferred footnote marker style still leaves unresolved or
  ambiguous links in `paper_footnotes.json`.

- `table_caption_placement_coverage`
  Reports how many extracted tables have known versus unknown caption
  placement.

- `figure_caption_geometry_availability`
  Reports figure caption evidence while making clear that figure geometry is
  not extracted yet.

- `visual_reference_resolution_coverage`
  Reports unresolved or ambiguous table/figure prose references.

## Non-Goals

This artifact does not:

- decide whether a specific anchor should be linked to a specific definition
- classify repeated page furniture
- extract figure images
- normalize bibliography authors
- add cross-paper citation management

Those remain separate parser responsibilities.
