# Paper Text Reading-Order Repair

Status: deferred until the current caption/footer regression is resolved and
checkpointed. This document is a plan, not approval to change parser logic.

## Observed failure

In
`Role of Estimated Glucose Disposal Rate in Staging and Death Risk of Cardiovascular-Kidney-Metabolic Syndrome- Insights from NHANES 1999-2018.pdf`,
PDF page 4, printed Table 1, two-column article prose is followed by a table
caption and a full-width table.

The raw positioned evidence has the correct block sequence:

```text
block 3: left-column prose
block 4: right-column prose
block 6: Table 1 caption
table content
```

Block 3 ends with `Similarly, participants with higher eGDR values were`.
Block 4 continues that sentence and ends with `increasing eGDR levels.`. The
caption begins in block 6.

`paper_text_stream.json` currently describes the whole page as one column and
orders its individual lines by vertical position. That incorrectly places the
unfinished last line of block 3 immediately before the caption. The table-
mention classifier then treats that false adjacency as prose continuity and
rejects the caption.

## Goal

Establish one reading order from the existing `PaperPositionedDocument`
evidence and publish it through the existing `PaperTextStream`. Do not add a
second PDF pass, alternate text stream, fallback extraction route, or parallel
reading-order artifact.

Mixed-layout pages must support a change in layout down the page, including:

```text
two-column prose
-> spanning caption or other block
-> full-width table, figure, or prose
```

## Implementation checkpoints

- [ ] Audit raw PyMuPDF block order and geometric block relationships on the
      focused page before changing behavior.
- [ ] Compare block order with the present page-wide column order on corpus
      pages whose output would change. Treat PyMuPDF block order as evidence,
      not automatically as authority.
- [ ] Replace individual-line page-wide ordering in
      `build_paper_text_stream()` with block- or layout-region-aware ordering.
- [ ] Keep lines within their positioned source block and order them by their
      existing block-local line identity.
- [ ] Order side-by-side prose blocks in reading order before a later spanning
      block. Determine this from positioned block topology and overlap, without
      adding a fixed point-distance tolerance.
- [ ] Allow column structure to differ between vertical regions of the same
      page. Do not force one `column_count` decision over both article prose and
      a full-width table.
- [ ] Preserve each source line ID, block index, line index, bbox, spans, font
      evidence, orientation, and page identity unchanged.
- [ ] Emit the final order only through the existing `PaperTextStream` and
      update its existing column metadata so it does not contradict that
      order.
- [ ] Remove or align the old page-wide ordering path in the same approved
      change; do not leave competing order calculations.
- [ ] Update `docs/design/paper_parse_walkthrough.md` if the implemented stream
      ordering or metadata contract changes.

## Focused acceptance check

- [ ] On PDF page 4 of the named paper, block 3 is followed by block 4, and
      block 4 is followed by the block 6 caption.
- [ ] The caption's preceding prose line is `increasing eGDR levels.`.
- [ ] Printed Table 1 is again detected with its caption, physical grid,
      closing rule, and footer ownership intact.

## Corpus comparison

- [ ] Run all 28 PDFs into a fresh output directory.
- [ ] Compare `paper_text_stream.json`, `paper_sections.json`,
      `paper_table_mentions.json`, `paper_bibliography.json`,
      `paper_visual_inventory.json`, `extracted_tables.json`,
      `table_boundary_proposals.json`, `table_regions.json`, and
      `paper_footnotes.json` with the retained baseline.
- [ ] Report every changed paper using its exact PDF filename, PDF page, and
      printed table number where applicable.
- [ ] Do not accept the change merely because caption detection improves;
      section, bibliography, figure, footer, and table reading order must also
      remain correct.

## Relationship to the current `has_bold` work

The current working-tree change renames `bold_like` to `has_bold` and removes
bold presence as automatic caption or heading evidence. It correctly restores
the mixed-font footer in
`The prevalence and mortality risks of PRISm and COPD in the United States from NHANES 2007–2012.pdf`,
PDF page 7, printed Table 2.

The subsequent focused continuation change now rejects sentence continuity
when the last visible span of the preceding line and the first visible span of
the current line change font or bold state. This restores printed Table 1 on
PDF page 4 of the eGDR paper as a 48 x 7 table with its closing rule and footer.

That narrow correction does **not** repair the underlying reading order. The
stream still places the unfinished left-column line next to the caption instead
of completing the right column first. The project in this document remains
necessary for sections, bibliography, references, captions, figures, and other
consumers that need the actual page reading order rather than a font-based
barrier to false adjacency.
