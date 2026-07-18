# Goal: Build the Paper's Prose Reading Order First

Identify headings, paragraphs, and sections directly from positioned PDF source
blocks and their layout. Freeze that prose reading order before using table,
figure, box, caption, or footer parsing.

After prose is established, represent the residual document material as
separate entities with distinct caption, content, note/footer, and metadata
components.

`paper_markdown.md` should be rendered from the prose reading order only. It
should not be a full-paper text dump.

## Decided Architecture

- [x] Keep `PaperPositionedDocument` as the unchanged source of positioned
      lines, blocks, typography, orientation, and geometry.
- [x] Preserve source-block identity and block-local line order.
- [x] Expose ordered `PaperTextBlock` records.
- [x] Build current sections directly from ordered blocks.
- [x] Render current Markdown from the same ordered blocks.
- [ ] Determine which source blocks are prose using block layout alone.
- [ ] Freeze accepted prose before entity classification.
- [ ] Build a prose-oriented reading-order structure whose segments correspond
      to document sections or subsections.
- [ ] Build a separate entity inventory from residual, non-prose blocks.
- [ ] Keep entity captions separate from entity content.
- [ ] Keep entity notes, footers, and metadata separate from both prose and
      entity content.

## Current Observations

- [x] The current 28-paper stream contains 36,518 positioned text lines in
      4,674 ordered blocks.
- [x] Most candidate entity material is block-contained: 1,605 current blocks
      are wholly associated with table/caption/footer evidence, while only
      three blocks mix associated and other lines.
- [x] Existing table/footer ownership cannot define prose safely. It currently
      claims real article prose in at least these cases:
  - [x] `cardiovascular.pdf`, PDF page 5, printed Table 2:
        `Performance of models`.
  - [x] `Journal of Periodontology - 2015 - Eke - Update on Prevalence of
        Periodontitis in Adults in the United States  NHANES 2009.pdf`, PDF
        page 10, printed Table 5: `years old.`
  - [x] `fld.pdf`, PDF page 6, printed Table 2: a twelve-line article paragraph.
- [x] These ownership errors support the prose-first design: correctly
      identified prose must remain prose regardless of a later table/footer
      claim.
- [x] Figure-caption discovery currently scans completed section content. That
      is unsuitable once sections become prose-only.
- [x] Existing design documents still describe Markdown and the text stream as
      full-paper views.

## Invariants

- [ ] The prose classifier must not consume `ExtractedTable`, `TableRegion`,
      `TableBoundaryProposal`, accepted footer IDs, or semantic table parsing.
- [ ] Prose must be identified positively from positioned block and layout
      evidence.
- [ ] A block not accepted as prose must remain residual; it must not
      automatically become an entity.
- [ ] Later entity parsing may classify residual blocks but may not remove or
      reclaim accepted prose.
- [ ] A conflict between accepted prose and a later entity claim must produce a
      diagnostic against the entity claim.
- [ ] Every retained block and line must preserve its source identity and
      geometry.
- [ ] No second PDF text pass, competing reading-order stream, fallback
      extractor, vocabulary shortcut, or unapproved numeric layout tolerance
      may be added. The one approved tolerance is the within-block font-size
      span below.

## Iteration Discipline

- [ ] First make prose reading order broadly correct using general positioned
      block and layout rules.
- [ ] Then identify captions from the residual blocks without reopening
      accepted prose.
- [ ] Once captions are broadly correct, inspect and classify what remains.
- [ ] Do not interrupt a general stage to recover isolated residual cases.
- [ ] Investigate a narrower case only after the applicable general rule and
      corpus evidence fail to resolve it.

## Step 1: Establish the Block-Layout Input

- [x] Build one shared positioned-document pass.
- [x] Apply repeated page-furniture filtering before block reading order.
- [x] Keep each source block contiguous.
- [x] Keep lines in block-local source order.
- [x] Split source blocks only at confirmed heading/body transitions.
- [x] Audit the fields required for prose classification:
  - [x] page and orientation group
  - [x] source block index
  - [x] page-space and canonical block bbox
  - [x] ordered line IDs
  - [x] dominant and span-level typography on the referenced lines
  - [x] block column assignment and orientation-group column bands
  - [x] heading/body role
- [x] Confirm that all required evidence comes from
      `PaperPositionedDocument` or its existing block projection.

## Step 2: Classify Prose from Blocks

- [x] Define positive evidence for a prose block.
- [x] Restrict prose candidates to upright orientation groups.
- [x] Use participation in a column-local reading flow.
- [x] Use block-local line continuity and source order.
- [x] Use compatibility with observed body typography.
- [x] Use confirmed headings to open section-level prose flow.
- [x] Allow prose to continue across consecutive source blocks in the same
      layout region.
- [x] Run the first-pass classifier across all 28 PDFs.
- [ ] Accept the first-pass classifier. The corpus comparison failed:
  - [ ] 86 new headings appeared across 20 papers; at least 43 are plainly
        captions, table notes/data, author text, DOI text, or page furniture.
  - [ ] Eight tables in seven papers lost or shortened footer evidence because
        false headings stopped the footer scan.
  - [ ] `cardiovascular.pdf`, PDF page 5, printed Table 2, still rejects the
        genuine `Performance of models` prose block because its source block
        contains a heading-style first line followed by body-style sentences.
  - [x] `fld.pdf`, PDF page 6, printed Table 2, retains the known article prose.
  - [x] The Eke paper, PDF page 10, printed Table 5, retains the known article
        prose.
  - [x] All 486 rotated blocks remain residual.
- [ ] Accept the connected-flow correction tested in
      `outputs/prose_flow_first_pass_20260718`. The focused first pass failed
      and no further correction was attempted:
  - [x] Remove the rule that promoted an arbitrary different-style body block
        before prose into a heading.
  - [x] All four `NutritionEx.pdf` figure captions tested on PDF pages 3, 7,
        and 8 remain residual.
  - [x] The Eke prose on PDF page 10, printed Table 5, and both parts of the
        `fld.pdf` prose continuation on PDF page 6, printed Table 2, remain
        accepted.
  - [ ] In `Asthma prevalence among United States population insights from
        NHANES data analysis.pdf`, the caption for printed Table 2 on PDF page
        5 joins the following same-layout article prose, and the caption for
        printed Table 3 on PDF page 6 joins the first article-prose block on
        PDF page 7. Both captions therefore remain false prose candidates.
  - [ ] The section paragraphs and headings tested in `cobaltpaper.pdf` on PDF
        pages 2, 4, and 5 become residual because they are isolated by tables
        or by headings that the earlier permissive rule had itself invented.
  - [ ] `cardiovascular.pdf`, PDF page 5, printed Table 2, still rejects the
        genuine `Performance of models` source block because it mixes heading
        and body typography.
- [ ] Accept the narrow exact-geometry correction tested in
      `outputs/prose_flow_geometry_first_pass_20260718`. The rerun also failed
      and no further correction was attempted:
  - [x] The captions for printed Tables 1 and 2 on PDF page 5 and printed Table
        3 on PDF page 6 of the asthma paper all remain residual.
  - [ ] The real prose following printed Table 2 on PDF page 5 and printed
        Table 3 on PDF page 7 of the asthma paper also becomes residual because
        neither block gains independent prose ownership after its caption is
        disconnected.
  - [ ] The Eke PDF-page-10/printed-Table-5 prose becomes residual. Its two
        consecutive source blocks have the same exact left edge but different
        content-dependent right edges, so exact block-union width is not a
        valid column-flow identity.
  - [x] Both parts of the `fld.pdf` PDF-page-6/printed-Table-2 prose
        continuation remain accepted.
  - [ ] The tested `cobaltpaper.pdf` and `cardiovascular.pdf` prose remains
        residual as in the preceding failed pass.
- [x] Accept the page/column-only continuation pass as the conservative corpus
      candidate in
      `outputs/prose_page_column_continuation_first_pass_20260718`:
  - [x] Remove exact block-bbox equality from prose-flow decisions.
  - [x] Permit a non-independent continuation only after unfinished accepted
        prose crosses a page or column boundary.
  - [x] Keep the asthma captions for printed Tables 1 and 2 on PDF page 5 and
        printed Table 3 on PDF page 6 residual while accepting their following
        article-prose blocks.
  - [x] Accept both parts of the `fld.pdf` PDF-page-6/printed-Table-2 column
        continuation.
  - [x] Accept the Eke PDF-page-10/printed-Table-5 prose. Visual rendering and
        source evidence confirm that `page-10-line-19`, `years old.`, is
        upright with direction `[1.0, 0.0]`; the only rotated page-10 block is
        the far-right DOI/license strip with direction `[0.0, 1.0]`, and it
        remains residual.
  - [x] Accept the tested `cobaltpaper.pdf` article paragraphs.
  - [x] Defer independent confirmation of the tested `cobaltpaper.pdf`
        headings; they remain preserved as residual after removal of the
        permissive body-to-heading promotion.
  - [x] Defer `cardiovascular.pdf`, PDF page 5, printed Table 2: the publisher
        encoded the semibold `Performance of models` heading and regular prose
        in one source block, which remains preserved as residual.
  - [x] Review preserved residual blocks as a later focused stage rather than
        weakening the current prose classifier before corpus comparison.
- [x] Accept the approved body-font correction as the Step 2 corpus
      checkpoint:
  - [x] Require one font name per body block and
        `largest line font size - smallest line font size < 0.5`; approval was
        supplied with `APPROVE_LAYOUT_TOLERANCE`.
  - [x] Keep the block style keyed by its font name and largest reported line
        size; do not add another recovery or inference path.
  - [x] Recover the intended MDPI and exposome-atlas prose without changing any
        of the other 26 papers' prose decisions.
  - [x] Keep all newly accepted blocks free of caption-leading and known
        page-furniture text.
  - [x] Defer the already-known false prose candidates and isolated residual
        prose until the next applicable general stage; do not broaden this
        correction.
- [x] Support a layout change down the page, including:
  - [x] full-width title or abstract followed by columns
  - [x] two-column prose followed by a spanning residual block
  - [x] prose resuming below a spanning residual block
  - [x] full-width prose after columns
- [x] Preserve legitimate short prose blocks and sentence continuations.
- [x] Keep uncertain blocks residual instead of guessing.
- [x] Do not use table labels, figure labels, statistical vocabulary, disease
      names, or expected semantic content to identify prose.
  - [x] The minimal transition support uses the existing `full_width_line`
        observation inside the non-operative prose-candidate pass. It adds no
        schema, helper, tolerance, semantic vocabulary, or alternate ordering
        path. The 28-PDF run in
        `outputs/testpapers_batch_prose_layout_transition_20260718` leaves all
        candidate sets and 196 compared downstream artifacts byte-identical to
        the accepted font-span baseline. Step 3 will determine whether this
        support works when producing the prose reading-order structure.

## Step 3: Produce the Prose Reading-Order Structure

- [ ] Decide whether to evolve `PaperTextStream` into the canonical prose
      structure or replace it atomically with `PaperReadingOrder`.
- [ ] Do not persist both an old full-paper stream and a new prose stream.
- [ ] Treat positioned source blocks as atomic layout evidence, not as
      reading-order segments.
- [ ] Make each reading-order segment a heading-delimited section or
      subsection.
- [ ] Give each segment complete sentence-bearing paragraph text: normally
      multiple paragraphs, with one paragraph allowed for a short section.
- [ ] Store the ordered prose blocks and paragraphs owned by each segment.
- [ ] Store source line IDs and geometry for every retained block.
- [ ] Store residual block and line IDs for later entity classification.
- [ ] Build sections only from accepted prose blocks.
- [ ] Render `paper_markdown.md` only from accepted prose blocks.
- [ ] Verify that every section body block belongs to the prose structure.
- [ ] Verify that Markdown is an exact view of the same ordered prose blocks.
- [ ] Keep the complete source text available in
      `paper_positioned_document.json`.

## Step 4: Build Entities from Residual Blocks

- [ ] Define a `PaperEntityInventory` or atomically evolve the existing visual
      inventory into the broader entity structure.
- [ ] Support initial entity kinds:
  - [ ] table
  - [ ] figure
  - [ ] box
- [ ] Give every entity distinct components for:
  - [ ] caption
  - [ ] content
  - [ ] note/footer
  - [ ] metadata such as a visual-object DOI
- [ ] Store source block IDs, line IDs, page, orientation, and bounds for each
      component.
- [ ] Link table entities to `ExtractedTable` rather than duplicating the grid.
- [ ] Use current table extraction only to interpret or link residual blocks.
- [ ] Reject or diagnose any proposed table/footer ownership that overlaps
      frozen prose.
- [ ] Detect figure captions from residual positioned blocks rather than prose
      sections.
- [ ] Link figures to image geometry only when direct structural evidence
      exists.
- [ ] Add boxes only when direct block/rule/bound evidence establishes them.
- [ ] Leave residual material unclassified when no entity is established.

## Step 5: Align Downstream Consumers

- [ ] Make prose visual-reference collection scan prose sections only.
- [ ] Ensure real prose such as `Table 1 shows...` remains in the reading
      structure.
- [ ] Prevent entity captions from becoming prose references.
- [ ] Make paper-variable inventory consume prose sections plus explicit table
      definitions.
- [ ] Make table-context retrieval consume prose sections.
- [ ] Make footnote processing consume entity note/footer components.
- [ ] Make style profiling consume entity captions and metadata.
- [ ] Keep bibliography extraction early enough to protect table extraction,
      while preserving its own structured entry artifact.
- [ ] Allow pre-extraction table mentions to retain positioned source IDs even
      when their blocks are later classified as entity material.

## Step 6: Update and Retire Artifact Contracts

- [ ] Update `paper_markdown_spec.md` to define Markdown as prose-oriented.
- [ ] Update `paper_parse_walkthrough.md` with the prose-first processing order.
- [ ] Update `parsing_output_design.md` with the prose and entity structures.
- [ ] Update `paper_visual_references.md` for residual entity captions and
      metadata.
- [ ] Update `paper_footnotes.md` so footer interpretation consumes entity
      components rather than defining prose exclusion.
- [ ] Update `paper_bibliography.md` for the revised document-context flow.
- [ ] Update variable-inventory and semantic-context documentation.
- [ ] Supersede the completed/stale portions of
      `paper_text_reading_order_repair.md`.
- [ ] Update `parser_todo.md` after each approved checkpoint.
- [ ] Remove documentation describing final Markdown as a full-paper view.

## Step 7: Focused Validation

- [ ] In `Role of Estimated Glucose Disposal Rate in Staging and Death Risk of
      Cardiovascular-Kidney-Metabolic Syndrome- Insights from NHANES
      1999-2018.pdf`, PDF page 4, printed Table 1:
  - [ ] read the left prose column before the right prose column
  - [ ] keep the complete prose sentence in reading order
  - [ ] leave the spanning caption and table blocks residual
  - [ ] later represent the caption and table as entity components
- [ ] In `cardiovascular.pdf`, PDF page 5, printed Table 2, retain
      `Performance of models` as prose despite the current footer claim.
- [ ] In `Journal of Periodontology - 2015 - Eke - Update on Prevalence of
      Periodontitis in Adults in the United States  NHANES 2009.pdf`, PDF page
      10, printed Table 5, retain `years old.` in its prose continuation.
- [ ] In `fld.pdf`, PDF page 6, printed Table 2, retain the twelve-line article
      paragraph as prose despite the current footer claim.
- [ ] Verify prose around captions printed below tables.
- [ ] Verify prose around rotated tables.
- [ ] Verify prose before and after figures and boxes.
- [ ] Verify that uncertain residual blocks do not enter Markdown.

## Step 8: Full-Corpus Validation

- [x] Run all 28 PDFs with bounded parallel workers.
- [x] Write the accepted comparison run to
      `outputs/testpapers_batch_prose_font_span_20260718`.
- [x] Confirm every parse command completes.
- [x] Accept the font-span correction as the current non-operative corpus
      checkpoint:
  - [x] Preserve all 4,674 blocks and mark 774 as prose candidates, up from
        729 in the exact-font baseline.
  - [x] Keep all 486 rotated blocks residual.
  - [x] Preserve the existing 92 extracted tables, 313 sections, and the same
        single known Helicobacter table-definition failure. The
        `prose_candidate` flag remains non-operative and has no downstream
        consumer.
  - [x] `mdpi-The Relationship Between a Mediterranean Diet and Frailty in
        Older Adults- NHANES 2007–2017.pdf` increases from 1 to 17 accepted
        blocks and retains 23,260 of 49,228 upright text characters.
  - [x] `An atlas of exposome–phenome associations in health and disease
        risk.pdf` increases from 13 to 42 accepted blocks and retains 33,949 of
        83,268 upright text characters.
  - [x] Confirm that these are the only two papers whose prose decisions
        change. They add 59 prose continuations or section headings/content
        and drop 14 former non-prose candidates, for a net increase of 45;
        none of the additions is caption-leading or known page furniture.
  - [x] Confirm that extracted tables, normalized tables, table definitions,
        parsed tables, existing sections, and existing Markdown are identical
        to the exact-font baseline.
  - [ ] Known non-prose candidates remain for the next general stage:
        `Asthma prevalence among United States population insights from NHANES
        data analysis.pdf`, PDF page 10, retains its Open Access license;
        `An environment-wide association study (EWAS) on type 2 diabetes
        mellitus.pdf`, PDF page 9, retains two supplemental-object
        descriptions; and `Uses of NHANES Biomarker Data for Chemical Risk
        Assessment- Trends, Challenges, and Opportunities.pdf`, PDF page 4,
        has one source block that begins with the Figure 4 caption and continues
        with real article prose.
- [ ] Confirm every accepted prose line occurs exactly once.
- [ ] Confirm every section block belongs to accepted prose.
- [ ] Confirm Markdown exactly matches the accepted prose blocks.
- [ ] Confirm later table/footer claims cannot remove accepted prose.
- [ ] Confirm residual blocks remain available for entity classification.
- [ ] Confirm real prose references to tables and figures remain.
- [ ] Confirm caption-derived references and variable mentions do not enter
      prose-derived artifacts.
- [ ] Confirm table extraction and semantic artifacts remain unchanged during
      the prose-classification phase.
- [ ] Report every unexpected change using the exact PDF filename, PDF page,
      and printed table number.
