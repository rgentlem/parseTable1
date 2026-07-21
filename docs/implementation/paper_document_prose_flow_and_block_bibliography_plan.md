# Block-Based Bibliography Implementation Plan

## Scope

Active after the accepted Step 5 endpoint in
`docs/implementation/paper_document_block_layout_implementation_plan.md`, which
was abandoned after Steps 0–5. This plan does not supersede deleted steps.

Goal: replace numbered-bibliography reconstruction with ordered lines from
canonical `PaperDocument` blocks. Retain the current parser only for explicitly
unnumbered bibliographies. The prose-flow goal is removed.

B2 comparison baseline:
`outputs/testpapers_batch_b0_dependency_cut_20260720`.
This plan is not parser-logic approval. Numeric layout tolerances remain barred
without `APPROVE_LAYOUT_TOLERANCE`.

Execution order:

```text
B0 audit -> B1 expectations -> approved B0 cut -> B2 -> B3 -> B4 -> B5 -> B6
```

## B0 Dependency Cut

Current:

```text
positioned lines -> line bibliography parser -> heading relabel/block split
-> PaperDocument blocks -> block layout
```

Required:

```text
positioned evidence -> furniture filtering -> canonical blocks -> block layout
-> bibliography region -> entries -> ownership -> extraction mask
```

Files/functions:

- `table1_parser/context/paper_document_builder.py`
  - `build_paper_document()` and its bibliography-driven relabel/split
- `table1_parser/paper_bibliography.py`
  - `build_bibliography_entries_from_layout_lines()` and visual-row helpers
  - `build_bibliography_entries_from_sections()`
- `table1_parser/cli.py`
  - the section-derived fallback
- `table1_parser/extract/pymupdf_extractor.py`
  - `_bibliography_evidence_masks_by_page()`

B0 audit, with no code change:

- [x] List every block whose role, line partition, or prose ownership depends
      on bibliography-heading output.
- [x] Map every bibliography source line to its canonical block and prose owner.
- [x] Report each conflict by exact PDF filename and verified PDF page.

Audit result: all 4,958 bibliography source lines mapped once to 598 canonical
blocks. Bibliography output changes 22 source groups in 21 PDFs. It also leaves
382 bibliography lines in 31 prose-owned blocks across three PDFs. No code was
changed. Detailed counts remain in the B0 run record.

After B1 and separate approval:

- [x] Build canonical blocks/layout before the legacy bibliography call.
- [x] Prevent legacy output from changing block role, split, or prose ownership.
- [x] Keep the legacy parser only as the temporary output path through B3.
- [x] Run focused checks and all 28 PDFs; report every changed block, prose
      segment, Markdown section, and bibliography entry.
- [x] Stop for review before B2.

B0 candidate: `outputs/testpapers_batch_b0_dependency_cut_20260720` completed
28/28 PDFs. The cut merges 16 bibliography-induced block splits and changes six
single-block roles, covering 22 source groups in 21 PDFs. Prose line ownership
changes only in the Science paper and `hypertension.pdf`; all 1,350 bibliography
entries and all extraction, normalized-table, and parsed-table artifacts are
unchanged. Derived prose/document consumers change and require review before
B2. Exact comparison: `paper_document_b0_dependency_cut_report.md`.

## Contracts

Ownership:

- `PaperDocument.blocks` is the only block registry.
- Prose ownership is frozen during non-operative B2/B3/B4/B5 candidate work.
- At B6, confirmed bibliography blocks are atomically reassigned from
  provisional prose or residual to the bibliography entity.
- Uncertain blocks remain unassigned.
- Region detection, entry segmentation, and masking are separate decisions.
- A region/entry candidate neither owns blocks nor masks extraction.
- Masks derive only from accepted bibliography ownership.

Whole-block B3 candidate:

- current bibliography-entry line IDs are locator evidence only;
- every located canonical block is retained whole;
- located blocks on PDF pages before the earliest B2 heading page are retained
  and reported as upstream false positives; and
- no other located block is rejected or refined.

No second stream, alternate owner, PDF pass, invented text, or duplicated
line/block is permitted. Numbered and unnumbered routes must not compete.

## B1 Independent Expectations

- [x] Record corpus page ranges and explicit terminal reference numbers where
      the source provides them. Exact block and unnumbered-entry boundaries are
      not inspection assumptions.
- [x] Cover numbered, unnumbered, multi-column, cross-page, multi-block-entry,
      and multi-entry-block forms where present.
- [x] Record page-level extraction-mask expectations. Masks must cover only
      accepted bibliography heading/content blocks, including on partial pages.
- [x] Treat the current 1,350 entries only as regression output, not truth.

Expectations: `paper_document_bibliography_b1_expectations.md`.

## B2 Region Candidate

- [x] Start from explicit bibliography-heading evidence and search downstream
      first: from the heading block onward in that page's block-layout order,
      then through larger PDF page numbers in the same orientation.
- [x] Store ordered block IDs plus structural evidence only.
- [x] Emit conflicts for prose-owned candidate blocks; do not reclaim them.
- [x] Preserve unresolved blocks for later review.
- [x] Do not use visual rows, line x/y clustering, hanging-indent thresholds,
      or the section fallback.
- [x] Test B1 cases plus PDF page 1 of
      `Uses of NHANES Biomarker Data for Chemical Risk Assessment- Trends,
      Challenges, and Opportunities.pdf`.
- [x] Stop for region approval before B3.

B2 candidate: `outputs/testpapers_batch_b2_region_candidate_20260720`
completed 28/28 PDFs. `paper_document.json` records 29 non-operative candidates:
one for each PDF plus the second atlas heading on PDF page 14. An explicit
heading must begin its canonical block. The candidates record 31 prose-conflict
block references without changing ownership. The biomarker-risk PDF has no
candidate on PDF page 1. Removing the new candidate field makes every document
identical to B0; every other substantive artifact is unchanged.

## B3 Whole-Block Mapping Candidate

- [x] Map every current bibliography entry's `source_line_ids` to canonical
      blocks.
- [x] Retain every touched block in full and in canonical order.
- [x] Report any touched block on a PDF page before the earliest B2 heading
      page as an upstream false positive; make no other exclusion.
- [x] Do not split blocks, reconstruct entries, or inspect indentation.
- [x] Do not change bibliography entries, ownership, or extraction masks.
- [x] Run focused checks on the atlas, Science, GOLD BioAge, and Lead-exposure
      PDFs, then stop before a corpus run.

B3 candidate: `outputs/b3_whole_block_focused_20260720` completed all four
focused PDFs. Every legacy source line mapped, no upstream false-positive block
was found, and removing the B3 field reproduces B2 except for generated report
timestamps. `An atlas of exposome–phenome associations in health and disease
risk.pdf` maps three blocks on PDF pages 9–10 and none under its second heading
on PDF page 14. In `Science-Advanaced-Planetary Health Diet and risk of
mortality and chronic diseases- Results from US NHANES, UK Biobank, and a
meta-analysis.pdf`, the locator misses the PDF-page-10 block containing
references 47–50; later legacy line IDs touch blocks containing references
51–58. Its final PDF-page-10 touched block also retains 12 known
acknowledgements/ancillary lines. No corrective logic was added. The corpus was
not run.

## B4 Bibitem Block Candidate

- [x] Add `find_numbered_bibliography_item_starts(block)`: scan every ordered
      source line for a leading reference number; junk does not stop the scan.
- [x] From each B2 heading, retain the first contiguous number sequence and all
      whole blocks from its first start through its last start.
- [x] If no numbered sequence exists, use the current unnumbered entries to
      locate whole blocks. Do not change entries, ownership, or masks.
- [x] Use no geometry for this candidate. Indentation remains the only permitted
      geometry when later assembling continuation lines into an item.
- [x] Compare B4 block IDs and numbered starts with B3 and B1 on the same four
      PDFs, then stop before a corpus run.

B4 candidate: `outputs/b4_bibitem_block_focused_20260720` completed all four
PDFs. The atlas finds 1–54 but spans 38 blocks on PDF pages 9–14, including 35
blocks absent from B3 between references 42 and 43. GOLD BioAge follows the
unnumbered route and matches B3's four blocks on PDF pages 7–8. Lead exposure
finds 1–35 but omits the PDF-page-10 continuation-only block after reference
35. Science Advances finds 1–58, adds the missing PDF-page-10 block containing
references 47–50, omits the continuation-only block after reference 58, and
does not claim the acknowledgements block. Removing the B4 field reproduces B3;
all other substantive artifacts are unchanged. The corpus was not run.

## B5 Per-Heading Bibitem Walk

- [x] Return block-level item evidence, not a Boolean: numbered starts and line
      IDs, current unnumbered-entry line IDs, and permitted indentation-based
      continuation line IDs.
- [x] From each accepted `References` heading, inspect subsequent blocks in
      canonical order. Retain a whole block when it contains item or
      continuation evidence; allow unrelated lines inside that block.
- [x] Stop that heading's region at the first block with no item or continuation
      evidence. Remove B4's first-to-last range fill.
- [x] Process every later `References` heading independently. Require
      intervening prose and local downstream item evidence; continued numbering
      may relate regions but must not join them.
- [x] Keep ownership, prose, entries, and masks unchanged. In-text citation to
      bibliography-number validation is deferred and is not a B5 requirement.
- [x] Run the same four focused PDFs and stop before the corpus. The atlas must
      produce separate PDF-page-9-10 and PDF-page-14 regions without claiming
      PDF pages 11-13.

B5 candidate: `outputs/b5_per_heading_bibitem_focused_20260720` completed all
four PDFs. The atlas records references 1-42 on PDF pages 9-10 and 43-54 on PDF
page 14 as separate regions; no PDF-page-11-13 block is retained. GOLD BioAge
retains four unnumbered blocks. Lead exposure and Science Advances add their
final continuation-only blocks; Science stops before acknowledgements. The
Science heading line is also returned as current legacy unnumbered evidence.
All other substantive artifacts are unchanged. The corpus was not run.

## B5.1 Numbered-Start Indentation

- [x] Remove the exact-coordinate numbered-start exclusion from
      `bibliography_item_evidence_for_block()`.
- [x] Reuse positioned characters already present in `PaperPositionedDocument`
      to expose the leading digit width on the existing internal line record;
      add no PDF pass, schema, or helper.
- [x] Within one canonical block, let its first valid numbered candidate
      establish the number indentation. Return a later numeric-looking line as
      an item start only when it remains within one leading-digit width of that
      indentation; otherwise retain it as current-item text. Reset at every
      block, without page, column, or gutter assumptions.
- [x] Leave the existing expected-number walk, heading handling, whole-block
      ownership, and numbered-entry assembly unchanged.
- [x] Add no heading-free discovery, clustering, backward search, confidence
      scoring, missing-number recovery, or alternate entry builder. Run the
      anthropometric-index PDF, the thirteen exact-coordinate regressions, and
      then all 28 PDFs. Accept only if the remaining failures are
      `NutritionEx.pdf`, `fld.pdf`, and the environment-wide-association paper,
      with downstream table artifacts unchanged.

B5.1 changes item-start decisions using a character-width-derived layout
boundary and was implemented under the exact authorization
`APPROVE_LAYOUT_TOLERANCE`.

B5.1 candidate: `outputs/b5_1_numbered_start_corpus_20260720` completed 28/28
PDFs with 1,346 entries. The anthropometric-index paper reaches reference 43;
its indented `29. https...` line remains inside reference 28, and the following
label-only line begins reference 29. The thirteen exact-coordinate regressions
recover their prior entry counts and terminal numbers. After normalizing the
package example's invocation path and generated report timestamps, all
downstream table artifacts match the pre-B5.1 B6 run. The remaining accepted
follow-ups are `NutritionEx.pdf` stopping at 27, `fld.pdf` stopping at 26, and
the environment-wide-association paper assigning seven PDF-page-9 non-reference
blocks to bibliography content and its mask.

## B6 Atomic Cutover

- [x] Assign accepted heading/content blocks to the bibliography entity and
      remove any confirmed bibliography blocks from provisional prose.
- [x] Derive page masks from accepted owned blocks and source lines.
- [ ] Verify masks exclude bibliography text and no other block.
- [x] Delete the old numbered-entry and section-fallback paths in the same
      change. Retain hanging-indent item assembly only for the explicitly
      unnumbered route and only within the approved indentation restriction.
- [x] Run focused checks and all 28 PDFs with up to six workers.
- [x] Compare sections, Markdown, bibliography, masks, extracted tables,
      boundaries, regions, footnotes, normalized tables, definitions, and parsed
      tables.
- [x] Explain differences against B1 expectations; use 1,350 entries only as a
      regression comparison.

B6 rerun: `outputs/b6_atomic_cutover_corpus_furniture_fix_20260720` completed
28/28 PDFs after the page-counter furniture fix. No final-page counter remains
in `PaperDocument`. The MDPI frailty bibliography now reaches reference 40.
Three B1 lists still stop early: the anthropometric-index paper at 29,
`NutritionEx.pdf` at 27, and `fld.pdf` at 26. The environment-wide association
paper still assigns seven PDF-page-9 supplementary, acknowledgements, and
author-contribution blocks to bibliography content and therefore to its mask.
The candidate is not accepted and was not refined after this run.

The B5.1 corpus run supersedes that result. The B6 cutover endpoint is accepted
with the three B5.1 follow-ups recorded above for separate repair.

## Acceptance and Commit

Accept only when blocks no longer depend on bibliography output, every accepted
bibliography block is owned once, entry block/line provenance is complete,
masks derive from ownership, old competing paths are absent, the retained
unnumbered route remains exclusive, B1 expectations pass, and all 28 PDFs
complete with every substantive difference explained.

For this endpoint, the three recorded B5.1 follow-ups are explicit acceptance
exceptions to the otherwise unchanged B1 and mask requirements.

Use actual `table1-parser parse` runs; do not use pytest. Keep only the current
ignored output and never stage `outputs/`. Commit implementation only after B6;
never commit competing operative routes for the same bibliography form.

Deferred: prose flow and assignment of other residual entity types.
