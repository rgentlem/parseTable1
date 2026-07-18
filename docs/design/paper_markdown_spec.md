# Paper Markdown Spec

This document defines `paper_markdown.md`, the prose-only paper view written by
`table1-parser parse`.

## Purpose

`paper_markdown.md` presents the narrative paper content in reading order. It
is a human-readable view of `PaperDocument.prose`; it is not a full-paper text
dump and is not an extraction source.

Captions, tables, figures, boxes, bibliography entries, supplementary material,
accepted page furniture, and unresolved residual blocks do not belong in this
view. A prose reference such as `Table 1 shows ...` remains because its block is
narrative prose.

## Source and Construction

The source path is:

```text
paper_positioned_document.json
  -> paper_page_furniture.json
  -> paper_document.json
  -> paper_markdown.md
```

`PaperPositionedDocument` remains the raw text and geometry evidence.
`paper_markdown.md` is rendered only from the ordered
segments, heading block IDs, and paragraphs in `PaperDocument.prose`.

For each prose segment, the renderer emits:

1. each owned heading block as a level-two Markdown heading;
2. each owned paragraph's stored text in order.

Segments and paragraphs are separated by blank lines. The renderer performs no
ownership inference, section-role inference, caption filtering, or semantic
cleanup. Block selection has already occurred in `PaperDocument`.

There is no second PDF pass and no `pymupdf4llm.to_markdown(...)` fallback.

## Output Path

```text
outputs/papers/<paper_stem>/paper_markdown.md
```

## Contract with Sections

`paper_sections.json` is the JSON view of the same
`PaperDocument.prose.segments` list. It preserves:

- `segment_id`;
- ordered `heading_block_ids`;
- ordered paragraphs with `paragraph_id`, `block_ids`, and `text`.

Markdown and sections must therefore contain the same prose in the same order.
Neither artifact may independently add a block or include an ID from
`unassigned_block_ids` or an entity component.

## Design Rules

- Keep `PaperDocument` as the sole owner of prose membership and order.
- Preserve paragraph text; clean only heading whitespace for Markdown display.
- Do not reproduce table grids, captions, notes, or other residual material.
- Do not infer paper roles from heading vocabulary in either output renderer.
- Keep exact text, line identity, and geometry available through
  `paper_document.json` and `paper_positioned_document.json`, not by expanding
  Markdown metadata.
- Update this document whenever the prose, section, or Markdown artifact
  contract changes.

## Current Boundary

The persisted section and Markdown views now consume `PaperDocument.prose`.
Non-prose consumers also use `PaperDocument` blocks plus joined raw positioned
evidence. Prose visual-reference, variable-inventory, and table-context stages
still use the legacy in-memory `PaperSection` view; their later alignment must
not change the prose classification or these two persisted views.
