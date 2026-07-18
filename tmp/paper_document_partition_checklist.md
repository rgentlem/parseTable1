# Goal: Build the Canonical PaperDocument Partition

Identify headings, paragraphs, and sections directly from positioned PDF source
blocks and their layout. Move the established prose candidates into the
canonical `PaperDocument`, with every other retained block initially preserved
as residual.

Then inspect the residual registry block by block and represent supported
material as entities with distinct heading, caption, content, and footer
components. Material that cannot yet be assigned remains residual.

`paper_markdown.md` should be rendered from the prose reading order only. It
should not be a full-paper text dump.

## Decided Architecture

- [x] Keep `PaperPositionedDocument` as the unchanged source of positioned
      lines, blocks, typography, orientation, and geometry.
- [x] Preserve source-block identity and block-local line order.
- [x] Expose ordered `PaperTextBlock` records.
- [x] Build current sections directly from ordered blocks.
- [x] Render current Markdown from the same ordered blocks.
- [x] Establish conservative prose candidates using positioned block layout.
- [x] Define the canonical prose, entity, and residual structure in
      `docs/design/paper_document_plan_and_contract.md`.
- [ ] Atomically move the established prose candidates into `PaperDocument`
      and place every other retained block in its residual registry.
- [ ] Populate the distinct entity structure inside canonical `PaperDocument`
      from residual, non-prose blocks; do not create a parallel owner.
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
- [x] Existing design documents previously described Markdown and the text
      stream as full-paper views; the Bullet 2 artifact documentation now
      defines Markdown and sections as prose-only `PaperDocument` views while
      recording the still-pending stream-consumer migration.

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
- [ ] `PaperPositionedDocument` must preserve raw extractor evidence, including
      imperfect grouping or text; accepted corrections must not overwrite it.
- [x] `PaperDocument` is the corrected canonical representation. Consumers must
      use its text, roles, order, and ownership rather than reconstructing the
      document from raw positioned lines.
- [x] No second PDF text pass, competing reading-order stream, fallback
      extractor, vocabulary shortcut, or unapproved numeric layout tolerance
      may be added. The one approved tolerance is the within-block font-size
      span below.

## Iteration Discipline

- [x] First establish prose candidates using general positioned block and layout
      rules.
- [x] Replace `PaperTextStream` with `PaperDocument` without adding new
      classification logic during the migration.
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
        the accepted font-span baseline. The `PaperDocument` migration will
        verify that this evidence is preserved when prose ownership and its
        derived views are populated.

## Step 3: Replace PaperTextStream with PaperDocument

- [x] Build and persist `PaperDocument` from the existing filtered blocks and
      current prose-candidate decisions. Populate prose, leave entities empty,
      and place every other block in unassigned residual.
  - [x] The focused run in
        `outputs/paper_document_step3_bullet1_minimal_20260718` completed for
        `Journal of Periodontology - 2015 - Eke - Update on Prevalence of
        Periodontitis in Adults in the United States  NHANES 2009.pdf`, `Role
        of Estimated Glucose Disposal Rate in Staging and Death Risk of
        Cardiovascular-Kidney-Metabolic Syndrome- Insights from NHANES
        1999-2018.pdf`, `cardiovascular.pdf`, `cobaltpaper.pdf`, and
        `mdpi-The Relationship Between a Mediterranean Diet and Frailty in
        Older Adults- NHANES 2007–2017.pdf`. Every retained block is assigned
        exactly once to prose or residual, all entities are empty, and all
        existing compared text, section, Markdown, and table artifacts are
        unchanged. The only all-file comparison difference is the generated
        timestamp in `parse_quality_reports.json`.
- [x] Generate `paper_sections.json` and `paper_markdown.md` solely from
      `PaperDocument.prose`.
  - [x] In
        `outputs/paper_document_step3_bullet2_prose_views_20260718`, the five
        focused papers preserve the Bullet 1 ownership counts;
        `paper_sections.json` exactly equals the prose segment list and
        `paper_markdown.md` exactly renders its headings and paragraphs. No
        rotated or residual block enters either view. Only these two intended
        views and generated quality-report timestamps differ from the Bullet 1
        output.
- [x] Move existing non-prose consumers from `PaperTextStream` to
      `PaperDocument` block ownership plus line/span evidence from
      `PaperPositionedDocument`, without changing their decisions.
  - [x] Preserve the accepted block role in `PaperDocument`.
  - [x] Read canonical text, block order, and ownership from `PaperDocument`.
  - [x] Join source IDs to `PaperPositionedDocument` only for raw typography,
        characters, rules, and original PDF geometry.
  - [x] Do not introduce a corrected positioned-document copy or another full
        paper stream.
  - [x] The five-paper run in
        `outputs/paper_document_step3_bullet3_first_pass_20260718` preserves
        prose sections and Markdown byte-for-byte and preserves table grids,
        captions, table mentions, and footnote/footer decisions. Differences
        are limited to the new block role, source-provenance names, generated
        timestamps, and three retired-stream `full_width_line` diagnostic
        notes whose exact block geometry remains in `PaperDocument`.
- [x] Remove the `PaperTextStream` model, builder, JSON artifact, imports, and
      provenance labels once no consumer remains.
  - [x] The 28-PDF corpus run in
        `outputs/testpapers_batch_paper_document_step3_bullet4_20260718`
        completed without parser failures. It produced 92 extracted tables and
        81 final parsed tables. Against the retained Bullet 3 corpus checkpoint,
        all substantive JSON and Markdown content is unchanged; differences are
        limited to generated timestamps, the intended provenance rename, and
        removal of `paper_text_stream.json`. Prose/residual ownership remains
        complete and disjoint, and no rotated block is prose.

## Step 4: Resolve Residual Blocks into Entities

- [ ] Inspect every unassigned block with its page-local geometry, source order,
      typography, orientation, column membership, intervening blocks, and
      nearby established prose or entities.
- [ ] Introduce line-preserving split proposals for mixed residual blocks and
      component-assembly proposals for fragmented material before either kind
      of proposal changes the registry or ownership.
- [ ] Allow evidence-backed canonical text correction without changing the raw
      positioned source; record the source evidence and correction basis.
- [ ] Keep table-cell text correction in the specialized table artifacts, with
      both raw and canonical values, rather than duplicating the grid in
      `PaperDocument`.
- [ ] First identify and assemble captions from residual blocks without
      reopening accepted prose.
- [ ] Then inspect what remains for entity heading, content, footer,
      bibliography, supplementary, or unresolved ownership.
- [ ] Populate `PaperDocument.entities` from unassigned residual blocks; do not
      create a parallel entity-ownership artifact.
- [ ] Support initial entity kinds:
  - [ ] table
  - [ ] figure
  - [ ] box
  - [ ] bibliography
  - [ ] supplementary data
- [ ] Distinguish main and supplementary scope; represent a supplementary
      table as a table entity with supplementary scope.
- [ ] Give every entity distinct components for:
  - [ ] heading
  - [ ] caption
  - [ ] content
  - [ ] note/footer
- [ ] Make components own ordered block IDs whose page, line, orientation, and
      bounds come from the canonical block registry.
- [ ] Link structured content through typed artifact references rather than
      duplicating table grids, figure assets, or bibliography entries.
- [ ] Link table entities to `ExtractedTable` rather than duplicating the grid.
- [ ] Use current table extraction only to interpret or link residual blocks.
- [ ] Reject or diagnose any proposed table/footer ownership that overlaps
      frozen prose.
- [ ] Detect figure captions from residual positioned blocks rather than prose
      sections.
- [ ] Link figures to image geometry only when direct structural evidence
      exists.
- [ ] Add boxes only when direct block/rule/bound evidence establishes them.
- [ ] Make a strong general geometry-based effort to resolve residual blocks,
      while leaving genuinely uncertain material explicitly unassigned.
- [ ] Defer any LLM review until later; it may propose ownership only for
      unassigned blocks and may not override frozen prose or established
      entity ownership.
- [ ] After the first residual-assignment pass, review the observed assignments
      and residuals before deciding whether a separate reflective mechanism is
      useful. Keep any such mechanism inspectable and non-operative until its
      purpose is supported by corpus evidence.

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
      while making `PaperDocument` the final owner of its heading and entry
      blocks and linking its structured entry artifact.
- [ ] Allow pre-extraction table mentions to retain positioned source IDs even
      when their blocks are later classified as entity material.

## Step 6: Update and Retire Artifact Contracts

- [x] Record the approved canonical plan and downstream contracts in
      `docs/design/paper_document_plan_and_contract.md` and require it from
      `AGENTS.md`.
- [x] Update `paper_markdown_spec.md` to define Markdown as prose-oriented.
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
- [x] Remove documentation describing final Markdown as a full-paper view.

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
