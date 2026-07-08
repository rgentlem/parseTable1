# Corpus-Driven Real-Paper Testing Guide

Use this guide for the next hardening phase:

```text
Corpus-Driven Hardening Of Extraction, Normalization, Semantics, Footnotes, And References
```

The goal is to work through real papers in a reproducible order, identify the
first artifact where structure goes wrong, and fix the earliest parser stage
that owns the problem. The current priority is to keep the layout-aware
bibliography and caption/footer footnote baselines stable while continuing
failed-status and mixed-family review.

Before committing parser changes, update this guide with the current real-paper
run, output directory, observed failures, and any changed interpretation of the
review checklist. Treat the guide as part of commit hygiene, not as an optional
post-commit note.

All paper paths below are relative to:

```text
/Users/robert/Projects/Epiconnector/testpapers
```

## Current Reference Baseline

Latest reference run:

```text
outputs/testpapers_batch_20260708_header_group_upstream_fix
```

The current refreshed baseline is
`outputs/testpapers_batch_20260708_header_group_upstream_fix`. It was produced after
the PyMuPDF layout-aware text stream became the source of document order for
sections and reference lists, and after table-local caption/footer note blocks
began splitting footnote definitions from structured marker evidence, including
raised superscript markers in PDF character geometry and confirmed footer-cell
marker prefixes. Page text is ordered page, column, then
y-position, with page furniture removed before bibliography and table
extraction, and before cell text annotation or footnote PDF-block collection
consume page characters. The bibliography extractor reads numbered and
hanging-indent reference lists through one positioned stream, supports
references split across columns and pages, treats numbered offset labels as the
same entry-start structure as unnumbered hanging-indent entries, and does not
require bibliographies to be numbered. Credible ruled table candidates can also
be rebuilt from PyMuPDF word positions and stroked horizontal rules instead of
using the PyMuPDF4LLM grid as the sole row/column structure. The current run
also adds a pre-extraction `paper_table_mentions.json` pass that classifies
`Table N` lines as caption candidates, continuation labels, or prose references
from the page-furniture-filtered text stream. Text-position fallback now
consumes that artifact and rejects numeric-anchor grids whose value region is
mostly prose fragments. Explicit table extraction now also uses caption
geometry directly: caption boxes are bound one-to-one to the nearest compatible
table above or below, and strong uncaptained fragments can integrate with a
following below-captioned fragment when the column-header schema matches.
The backend JSON grid is no longer an emitted extraction fallback:
PyMuPDF4LLM may still provide a rough table box, but rows, columns, cell
boxes, row bounds, and header geometry must come from positioned PyMuPDF words,
characters, and rules. If positioned reconstruction cannot build a credible
grid from a rough box, that backend candidate is not emitted as an extracted
table. Ruled-table extraction and text-position fallback also share the same
header-span repair: sparse upper-header word clusters become spanning group
cells only when their start-column spans are ordered, non-overlapping, and
cover multiple lower columns; dense or tight wrapped header clusters remain
separate leaf columns.

Older generated `outputs/` runs should not be treated as current.

Current header/body and multicolumn-header inspection note:

```text
docs/implementation/header_body_cleanup_inspection.md
```

Current bibliography summary:

```text
PDFs: 27
parse command failures: 0
paper_bibliography:
  papers with bibliography entries: 27
  papers with empty bibliographies: 0
  papers with bibliography diagnostics: 0
  total bibliography entries: 1370
  numbered entries: 1092
  unnumbered entries: 278
  numbered bibliography papers: 22
  unnumbered bibliography papers: 5
  mixed numbering-style papers: 0
```

Current footnote summary:

```text
PDFs: 27
parse command failures: 0
paper_footnotes:
  anchors: 387
  definitions: 191
  links: 387
  resolved links: 387
  inferred links: 0
  ambiguous links: 0
  unresolved links: 0
  math/unit anchors suppressed before footnote linking: 34
  subscript anchors suppressed before footnote linking: 5
  word-like subscript anchors suppressed before footnote linking: 0
  citation-like anchors suppressed before footnote linking: 18
  non-footnote symbol anchors suppressed before footnote linking: 2
  PDF text blocks classified as table footers: 35
  extracted-table footer records: 10
  page-furniture filter stage: before_pdf_definition_block_construction (27 papers)
extraction page-furniture mask:
  extracted tables with mask metadata: 60
  page words removed before extraction/refinement: 949
  page chars removed before extraction/refinement: 7920
  explicit-grid rows removed by page-furniture mask: 0
```

Current papers with unresolved or ambiguous footnote links:

- None in `outputs/testpapers_batch_20260708_header_group_upstream_fix`.

Current extraction/status summary:

```text
PDFs: 27
parse command failures: 0
extracted tables: 66
extraction geometry:
  pymupdf_positioned_words_and_rules: 64
  pymupdf_positioned_words: 2
  pymupdf4llm_json_table_cells: 0
canonical extraction layer:
  pymupdf_positioned_geometry: 66
table_processing_status:
  ok: 16
  rescued: 42
  failed: 0
previous backend-grid survivor:
  periodontitis-p11-t0 is no longer emitted
```

Current table-mention summary:

```text
paper_table_mentions:
  total mentions: 318
  prose_reference: 240
  caption_candidate: 70
  continuation_label: 8
periodontis2 page 6:
  Table 4 shows... -> prose_reference, same_line_prose_verb_after
  ... is shown in / Table 5. At ... -> prose_reference, previous_line_prose_cue_before
  extracted page-6 table candidates: 0
known weak bucket:
  line_initial_table_label without bold/heading evidence can still include
  false positives such as Eke `Table 2 also shows...`; current policy is to
  monitor this bucket rather than add another rule until it causes extraction
  harm.
```

Current open structural issues:

- `papers_from_johnny/hypertension.pdf`, `hypertension-p5-t0`, is the only
  known current parse defect from the latest header-geometry review. The table
  extracts and parses, but `extracted_tables.json` interleaves tight multiword
  leaf headers across adjacent value columns. Current leaf labels are
  `Healthy diet physically active`, `and Healthy diet physically`, `but
  Unhealthy inactive physically`, `diet and Unhealthy inactive but physically
  active`, and `diet P value`; the expected labels are `Healthy diet and
  physically active`, `Healthy diet but physically inactive`, `Unhealthy diet
  and physically inactive`, `Unhealthy diet but physically active`, and `P
  value`.
- Two attempted leaf-header word-reassignment patches were intentionally
  rejected and reverted. `outputs/header_leaf_wordgap_focus_20260708` fixed
  `hypertension-p5-t0` but changed `cardiovascular-p5-t0`.
  `outputs/header_leaf_anchor_runs_focus_20260708` also fixed
  `hypertension-p5-t0`, but regressed MDPI frailty `p5-t0`, `p7-t0`, `p8-t0`,
  Eke `p8-t0`, Eke `p9-t0`, and `cardiovascular-p5-t0`. Do not revive
  word-level cross-column reassignment. The next acceptable direction is
  whole-cluster/header-cell assignment from PyMuPDF geometry, followed by
  column-band/span ownership.
- `papers_from_laha/Science-Advanaced-Planetary Health Diet and risk of
  mortality and chronic diseases- Results from US NHANES, UK Biobank, and a
  meta-analysis.pdf` still needs a path-consistency audit for Table 1. The
  p2 -> p3 continuation is accepted and the grouped column-header schemas now
  match, but the fragments reach that result through different candidate paths:
  p2 enters through whole-page PyMuPDF text-position extraction, while p3 still
  starts from a PyMuPDF4LLM rough table box and then uses hline word-position
  refinement. This is not currently a semantic failure, but it remains
  unresolved extraction-path debt because two fragments of one visual table
  should ideally follow the same canonical positioned-geometry path.

Resolved since the prior baseline:

- `cardiovascular` Table 1 page 4 now resolves 20 double-dagger body-cell
  anchors to the local `‡` table footer definition.
- `Association between anthropometric indices and chronic kidney disease` now
  resolves its 2 dagger links and converts 160 formerly conventional inferred
  p-value-star links into explicit same-table footer links.
  During the marker-evidence cleanup, this paper briefly regressed to 29
  ambiguous Table 1 `*` links because the footer parser found the raised `†`
  marker and dropped the ordinary upright `* p < 0.05` marker in the same block.
  The current parser merges structured marker evidence with ordinary symbol
  marker evidence before splitting one footer block.
- `Science-Advanaced-Planetary Health Diet and risk of mortality and chronic
  diseases` now resolves its Table 1 `*`, `†`, `‡`, and `§` links from the
  complete footer block on the continued page. `CO₂`, `I²`, `P_Begg`, and
  `P_Egger` are suppressed as notation or word-like subscripts rather than
  unresolved footnotes.
- `mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older
  Adults` no longer has unresolved or ambiguous footnote links in the current
  baseline.
- Early page-furniture masking, trailing-trim retirement, footer-block
  detection, and marker-evidence cleanup reduce the current full-corpus
  footnote issue count to 0 unresolved / 0 ambiguous links.
- Eke drops from 529 unresolved / 11 ambiguous links to 0 unresolved / 0
  ambiguous links in the current full-corpus baseline.
- Rotated Ethnic table annotation cleanup and bibliography/citation suppression
  resolved the prior Ethnic false-marker issue. Caption/footer footnote parsing
  now resolves the remaining metabolic, Systemic inflammation, Planetary Health,
  and Ethnic Differences caption/footer markers through general table-local
  marker-definition parsing rather than paper-specific link patches.
- OR/CI estimate routing, matrix-like table status guards, front-matter/prose
  suppression, and backend-grid survival removal keep current table-processing
  failures at 0 in the retained baseline.
- Asthma NHANES below-table captions are now attached to the correct visual
  tables: p5-t0 carries `Table 1`, p5-t1 carries `Table 2`, and p6-t0 carries
  `Table 3`. The strong uncaptained p4-t0 fragment integrates with p5-t0 as
  resolved Table 1 after column-schema matching, and the prior false Table 1
  continuation candidate involving p5-t1/p6-t0 is gone.
- The caption-contaminated backend-row-drop path has been retired. The same
  class of issue should now be solved by positioned PyMuPDF reconstruction and
  `TableRegion` ownership, not by mutating backend rows.
- Shared PyMuPDF word/rule header-span repair improves real multicolumn
  headers by splitting collapsed upper group labels in PRISm, PAD, gallstones,
  MDPI frailty, Lead, Cobalt, periodontitis, and Planetary Health. The current
  header-grid rule uses word start columns rather than glyph right edges when
  deciding whether an upper header cluster spans multiple lower columns, which
  preserves tight wrapped leaf headers such as periodontitis page 6 while
  allowing Planetary Health p2-t0 to expose the same grouped schema as p3-t0.

## Review Loop

For each checklist item:

1. Inspect the current artifacts under the reference baseline first.
2. Identify the first bad artifact in parser order:
   `extracted_tables.json`, `normalized_tables.json`,
   `column_header_schemas.json`, `resolved_tables.json`,
   `table_definitions.json`, `parsed_cell_values.json`,
   `parsed_tables.json`, `paper_footnotes.json`, `paper_bibliography.json`,
   `paper_table_mentions.json`, `paper_style_profile.json`,
   `paper_references.json`.
3. Record whether the issue belongs to extraction, normalization, continuation,
   table semantics, footnote detection/linking, or visual-reference resolution.
4. Fix only the earliest responsible stage.
5. Add focused regression coverage only for a known failure or stable artifact
   contract.
6. Re-run the reviewed chunk, then re-run the full corpus after parser behavior
   changes.

## Ordered Review Checklist

### C0. Footnotes And References First

- [x] **C0.0** Re-review embedded Table 1 p-value footnote definitions in
  `metabolic`.
  - PDF path: `papers_from_johnny/metabolic.pdf`
  - Previous artifact issue: Table 1 had detected `a`/`b` p-value superscript
    anchors but no definitions, because the definition line started with
    explanatory prose rather than a marker.
  - Earlier result: fixed in
    `outputs/testpapers_footer_blocks_20260701_final`; Table 1 `a`/`b` links
    were resolved, and Table 2 asterisk p-value markers became conventional
    `inferred` links rather than unresolved footnotes.
  - Current result:
    `outputs/testpapers_batch_20260708_header_group_upstream_fix` resolves all 15
    Table 1 `letter:a` / `letter:b` links against the below-table footer note.
    In the visual PDF the definitions begin with raised `a` and `b`
    superscripts. Raw extracted text may collapse those markers into following
    words, but the parser splits them from smaller raised glyph evidence rather
    than from the damaged string. Table 2 now resolves all 21 `*` links against
    the explicit same-table footer sentence `The asterisk indicates statistical
    significance`, rather than emitting conventional inferred links.

- [x] **C0.1** Review false-positive footnote marker detection in Eke.
  - PDF path: `papers_from_laha/Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009.pdf`
  - Baseline artifact issue: `paper_footnotes.json` had 529 unresolved links and
    11 ambiguous links, with many small-letter glyphs such as `letter:t`,
    `letter:r`, and `letter:l`.
  - Focused fix: page 7 now uses explicit PyMuPDF directional text-block geometry
    as the rotated source column before coordinate transformation, keeping the
    rotated table plus footer and excluding upright article text in the other
    page column.
  - Current full-corpus result:
    `outputs/testpapers_batch_20260708_header_group_upstream_fix` extracts page
    7 with no `letter:t`, `letter:r`, or `letter:l` anchors.
    `paper_footnotes.json` builds the page 7 `†` and `‡` definitions from
    extracted footer row blocks, including their continuation rows. No
    unresolved or ambiguous footnote links remain for this paper in the current
    baseline.

- [x] **C0.2** Review bibliographic superscripts versus table footnotes.
  - PDF path: `papers_from_laha/Helicobacter pylori infection in the United States beyond NHANES- a scoping review of seroprevalence estimates by racial and ethnic groups.pdf`
  - Focused output: `outputs/helicobacter_bibliography_fix_20260701_final`.
  - Result: `paper_footnotes.json` now has 3 resolved `letter:a` links and 0
    unresolved links. The true footer definition is `Value shows median age
    rather than mean.`
  - Result: `paper_bibliography.json` preserves 80 numbered bibliography
    entries and resolves all 35 numeric row-label study/source markers to
    bibliography entries. Those markers are suppressed from table-footnote link
    counts as citation-like row-label markers when no local table-note
    definition exists.
  - Remaining bibliography follow-up: body-text reference-marker harvesting is
    not implemented yet, so `entry_without_mention_count` is expected to remain
    nonzero until the future one-to-one bibliography coverage validation is
    added.

- [x] **C0.3** Review collapsed/rotated extraction causing bogus footnote
  anchors.
  - PDF path: `papers_from_laha/Ethnic Differences in the Relationship Between Insulin Sensitivity and Insulin Response.pdf`
  - Current result:
    `outputs/testpapers_batch_20260708_header_group_upstream_fix` has 9 resolved
    links and 0 unresolved or ambiguous links. `S_I` and `AIR_g` remain
    suppressed as subscript notation, vertical-bar artifacts attached to
    rotated numeric cells are suppressed as non-footnote symbols, and the
    marker-font `x` resolves against the local `xP < 0.05 vs. East Asian`
    footer definition through confirmed footer-cell marker evidence.

- [x] **C0.4** Resolve statistical-significance stars with footer definitions
  in `stroke`.
  - PDF path: `papers_from_johnny/stroke.pdf`
  - Previous artifact issue: 65 unresolved links.
  - Strong signal: 58 unresolved anchors were statistical-significance
    asterisks, often attached to p-values such as `<0.001***`.
  - Current result: fixed in
    `outputs/testpapers_batch_20260708_header_group_upstream_fix`; Table 1,
    Table 2, and Table 3 each have local `*`, `**`, and `***` definitions linked
    by same-table scope.
  - The previous 7 row-label unit exponents are now suppressed before
    `FootnoteAnchor` creation and counted in
    `math_unit_anchor_suppression_count`, so this paper is now a clean resolved
    footnote baseline for the local statistical-star-footer case.

- [x] **C0.4a** Re-review unresolved symbol footnote markers in Planetary
  Health Table 1 row labels.
  - PDF path: `papers_from_laha/Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf`
  - Current result:
    `outputs/testpapers_batch_20260708_header_group_upstream_fix` resolves all 4
    Table 1 links (`*`, `†`, `‡`, `§`) against the footer block on the
    continued page. The symbol splitter now handles variable whitespace before
    each marker in a contiguous footer block.

- [x] **C0.5** Resolve symbol-marker footer definitions that start with
  lowercase or arbitrary explanatory text.
  - PDF paths:
    1. `papers_from_johnny/cardiovascular.pdf`
    2. `papers_from_laha/Association between anthropometric indices and chronic kidney disease- Insights from NHANES 2009–2018.pdf`
  - Previous artifact issue: cardiovascular had 20 unresolved `‡` body-cell
    links because the local table footer line `†: ...; ‡: ...` was filtered out
    before definition parsing. Anthropometric CKD had 2 unresolved dagger links
    and 160 conventional inferred p-value-star links because local symbol
    footer definitions were not harvested.
  - Current result: fixed in
    `outputs/testpapers_batch_20260708_header_group_upstream_fix`. Known symbol
    markers such as `†`, `‡`, and `*` now define any non-empty local footer text;
    this is a structural footnote rule, not a p-value rule. Structured marker
    evidence from raised glyphs is merged with ordinary symbol marker evidence
    in the same footer block, so anthropometric CKD Table 1 keeps both the local
    `* p < 0.05` definition and the raised `†` definition.

- [x] **C0.6** Review ambiguous footnote linking where definitions exist but are
  not unique.
  - PDF paths:
    1. `papers_from_laha/mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017.pdf`
  - Previous artifact issue: MDPI Mediterranean had 3 ambiguous links and 3
    unresolved numeric links.
  - Current result: `outputs/testpapers_batch_20260708_header_group_upstream_fix` has 0
    unresolved and 0 ambiguous footnote links for this paper.

- [x] **C0.6a** Re-review repeated letter markers on continued tertile headers.
  - PDF path: `papers_from_laha/Systemic inflammation markers and the prevalence of hypertension- A NHANES cross-sectional study.pdf`
  - Current result:
    `outputs/testpapers_batch_20260708_header_group_upstream_fix` resolves all 12
    `letter:b` markers attached to `Tertile 1`, `Tertile 2`, and `Tertile 3`
    labels across the continued Table 1 against the same-visual footer
    definition on the continuation page.

- [ ] **C0.7** Review unresolved table-reference resolution before worrying
  about figures.
  - Highest unresolved table-reference counts:
    1. `papers_from_laha/An atlas of exposome–phenome associations in health and disease risk.pdf` - 21 unresolved table references.
    2. `papers_from_laha/Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf` - 10 unresolved table references, mostly supplement tables.
    3. `papers_from_laha/An environment-wide association study (EWAS) on type 2 diabetes mellitus.pdf` - 9 unresolved supplement table references.
    4. `papers_from_laha/Uses of NHANES Biomarker Data for Chemical Risk Assessment- Trends, Challenges, and Opportunities.pdf` - 9 unresolved table references.
  - Treat unresolved figure references separately; the table parser is not yet a
    figure extractor.

Acceptance for C0: footnote anchors are separated into true table-note markers,
bibliographic citations, statistical-significance markers, and false positives.
Reference resolution should clearly distinguish unresolved in-paper tables from
supplement-only or out-of-scope references.

### C1. Actual Failed Table Statuses

- [x] **C1.1** Review failed statuses that may be correct non-target tables.
  1. `papers_from_laha/An environment-wide association study (EWAS) on type 2 diabetes mellitus.pdf`
     - `An environment-wide association study (EWAS) on type 2 diabetes mellitus-p6-t0`
     - Current status in `outputs/testpapers_batch_20260708_header_group_upstream_fix`:
       `ok`, categorized as `analysis_outputs`.
     - Review result: structurally plausible ENWAS analysis-output table with
       sparse left descriptor columns; not a Table 1 descriptive failure.
  2. `papers_from_laha/mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017.pdf`
     - `mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017-p3-t0`
     - Current status in `outputs/testpapers_batch_20260708_header_group_upstream_fix`:
       `ok`.
     - Review result: text/reference table comparing frailty definitions; a
       correct non-target table for the current Table 1 descriptive parser.

- [x] **C1.2** Review `non_table_layout_candidate` failures.
  1. `papers_from_laha/Asthma prevalence among United States population insights from NHANES data analysis.pdf`
     - `Asthma prevalence among United States population insights from NHANES data analysis-p6-t0`
     - Current status: `ok`; `TableProfile.table_family` is
       `estimate_results`, and `paper_table_inventory.table_category` is
       `analysis_outputs`.
     - Fix: repeated OR/CI headers and estimate-CI range cells now provide
       enough deterministic evidence for estimate-result routing.
  2. `papers_from_laha/GOLD BioAge and depression- Associations with mortality among depressed NHANES participants (2005–2018).pdf`
     - `GOLD BioAge and depression- Associations with mortality among depressed NHANES participants (2005–2018)-p1-t0`
     - Current status: no longer extracted as a table candidate in
       `outputs/testpapers_batch_20260708_header_group_upstream_fix`.
     - Review result: abstract/title-page text laid out as article front
       matter, not a table artifact to route semantically. The front-matter
       guard now suppresses it before the table pipeline.
  3. `papers_from_laha/Helicobacter pylori infection in the United States beyond NHANES- a scoping review of seroprevalence estimates by racial and ethnic groups.pdf`
     - `Helicobacter pylori infection in the United States beyond NHANES- a scoping review of seroprevalence estimates by racial and ethnic groups-p5-t0`
     - `Helicobacter pylori infection in the United States beyond NHANES- a scoping review of seroprevalence estimates by racial and ethnic groups-p6-t0`
     - `Helicobacter pylori infection in the United States beyond NHANES- a scoping review of seroprevalence estimates by racial and ethnic groups-p7-t0`
     - Current status: `ok` with
       `matrix_like_table_without_supported_semantic_route`; categorized as
       `data_presentation`.
     - Review result: real continued data/reference matrix, not a non-table
       layout. It still needs future data-matrix semantics rather than Table 1
       descriptive parsing.
  4. `papers_from_laha/periodontis2.pdf`
     - Prior artifacts: `periodontis2-p6-t0` and `periodontis2-p6-t1`.
     - Current status in `outputs/testpapers_batch_20260708_header_group_upstream_fix`:
       no page-6 table candidates are extracted.
     - Review result: page 6 contains prose references to Tables 4 and 5, not a
       visual table. `paper_table_mentions.json` now classifies `Table 4
       shows...` and the split-line `... is shown in / Table 5. At ...` as
       prose references. The text-position fallback consumes that evidence and
       also rejects candidate grids where numeric anchors merely split prose
       into sentence fragments.
  5. `papers_from_johnny/periodontitis.pdf`
     - `periodontitis-p11-t0`
     - Current status in `outputs/testpapers_batch_20260708_header_group_upstream_fix`:
       no longer emitted as an extracted table.
     - Review result: abbreviation glossary/reference block, not a table
       artifact. The retired backend-grid survival path is no longer allowed to
       emit this rough box as a table.

- [x] **C1.3** Review the collapsed-grid failure.
  - PDF path: `papers_from_laha/Ethnic Differences in the Relationship Between Insulin Sensitivity and Insulin Response.pdf`
  - Table: `Ethnic Differences in the Relationship Between Insulin Sensitivity and Insulin Response-p5-t0`
  - Current status: `rescued`; the prior `collapsed_grid_unrecovered` failure is
    no longer present in `outputs/testpapers_batch_20260708_header_group_upstream_fix`.
  - Current footnote result: 9 resolved links and 0 unresolved links. The prior
    residual `letter:i`, `letter:x`, and `letter:g` false-marker issue is no
    longer present as unresolved footnote evidence; the remaining `letter:x`
    marker resolves through confirmed footer-cell marker evidence for the local
    `xP < ...` table note.

Acceptance for C1: every failed table is classified as correct non-target table,
extraction failure, normalization failure, unsupported table family, or ambiguous
pending review. The current baseline has no failed table-processing statuses.

### C2. Caption, Header/Body, And Extraction Geometry

C2 is table-structure review, and should run before continuation review. It
covers table captions, continuation labels, title/preamble rows, column-header
rows, body rows, footers, and the extraction geometry that separates those
regions. Figure extraction and figure-caption interpretation are future work,
not part of this pass. However, figure captions should still be kept as
distinct non-table document components when encountered, so they do not
contaminate table candidates now and can support later figure extraction.

- [ ] **C2.1** Review caption and region ownership before header/body or
  continuation decisions.
  - Confirm table captions and continuation captions are attached to the
    correct table candidate.
  - If a table has no caption above it, check for a caption below it before
    treating it as uncaptioned; a strong uncaptained adjacent fragment is
    continuation evidence, not a reason to reassign a later caption by page
    order.
  - Confirm caption text, title/preamble rows, body rows, and footer/note blocks
    are not being merged into the wrong table region.
  - Confirm figure captions are excluded from table candidates while preserving
    their identity as separate document components for future figure/caption
    extraction.
  - For each paper, check artifacts in this order:
    1. `paper_visual_inventory.json`: confirm each visual component has the
       correct `visual_kind`, label, page, caption, and `source_table_id`.
       Tables should be table visuals; figure captions may appear as figure
       visuals but should not point at table candidates.
    2. `extracted_tables.json`: confirm `title`, `caption`, `page_num`,
       `n_rows`, `n_cols`, `metadata.bbox`, `metadata.row_bounds`,
       `metadata.horizontal_rules`, `metadata.trailing_non_table_rows`,
       `metadata.table_orientation`, `metadata.is_continuation`, and
       `metadata.continuation_of_table_number`. The caption/continuation label
       should not also appear as a body row, footer definition, or unrelated
       table candidate.
    3. `paper_text_stream.json`: inspect positioned lines on the relevant page
       around the table bbox. The expected order is caption/title, header,
       body, footer/note block, then surrounding prose or other document
       components. Column and rotation evidence should explain that order.
    4. `normalized_tables.json`: confirm `header_rows`, `body_rows`,
       `row_views`, `metadata.header_detection`,
       `metadata.header_body_split_rule_comparison`, preamble rows,
       post-header note rows, and continuation-note rows match the visual
       table structure.
    5. `column_header_schemas.json`: confirm the selected header rows produce
       the expected leaf columns and that caption/title/footer text is not
       being promoted into column headers.
    6. `paper_footnotes.json` and `cell_text_annotations.json`: confirm
       footer/note text is represented as table-local definitions or suppressed
       non-footnote notation, not as caption text or body rows. Superscript
       marker evidence should come from positioned glyphs where possible.
    7. `table1_continuation_groups.json` and
       `table_continuation_column_checks.json`: only after the earlier checks
       pass, confirm continuation decisions use the correct caption,
       continuation label, row provenance, and column schema.
  1. `papers_from_laha/Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009.pdf`
     - Current footnote pollution issue appears addressed: continued-page
       caption text is no longer being written into footnote definitions, and
       all footnote links are resolved.
     - p4 -> p5 for `Table 1. (continued)` and p6 -> p7 for
       `Table 2. (continued)` now pass continuation column/header checks and
       are accepted as integrated continuations in `resolved_tables.json`.
       This remains a C2 review case because the normalized header/body split
       still selects row 9 where hline evidence proposes row 2; decide whether
       the value-anchor selection is correct for these multirow headers before
       changing continuation behavior.
  2. `papers_from_johnny/metabolic.pdf`
     - Current artifacts appear clean for this check: below-table footer
       parsing keeps the table caption separate, raised `a` and `b` markers link
       body cells to definitions, and Table 2 `*` links resolve through the
       local statistical-significance footer.
  3. `papers_from_laha/Ethnic Differences in the Relationship Between Insulin Sensitivity and Insulin Response.pdf`
     - Current artifacts appear clean for this check: rotated Table 1 is
       extracted as a table, the caption/footer are separated, and the nine
       detected footnote links resolve.
  4. `papers_from_laha/Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf`
     - Current footnote links resolve. The p2 -> p3 Table 1 continuation is
       accepted in `resolved_tables.json` after the base fragment's
       PyMuPDF-positioned header grid records the same two grouped upper
       headers as the continuation fragment. This remains a C2.4 path-review
       case because p2 currently enters through `pymupdf_text_positions` while
       p3 still enters through a PyMuPDF4LLM rough box plus hline word
       refinement. Figure-caption components in `paper_visual_inventory.json`
       remain noisy; confirm whether that is only future figure-extraction
       debt or whether it is contaminating table candidates, captions, or rows.

- [ ] **C2.2** Review current header/body split disagreements.
  1. `papers_from_laha/GOLD BioAge and depression- Associations with mortality among depressed NHANES participants (2005–2018).pdf`
     - p4-t1: hline body start 2, value-anchor body start 4, selected 2.
       This appears to be an acceptable disagreement caused by body parent and
       wrapped-value rows.
     - p5-t0 / Table 3 is no longer a C2 extraction/header failure:
       `grid_refinement_source = "hline_word_positions"`, extracted shape is
       5 rows by 3 columns, header rows are 0-1, body rows are 2-4, and
       `Adjusted Model` spans `OR (95%CI)` plus `p-value`. The remaining
       issue is downstream TableDefinition semantics for a small estimate
       result table, not extraction geometry.
  2. `papers_from_laha/Asthma prevalence among United States population insights from NHANES data analysis.pdf`
     - p5-t0 and p6-t0.
     - p5-t0: hline body start 3, value-anchor body start 1, selected 1.
     - p6-t0: hline body start 2, value-anchor body start 1, selected 1.
  3. `papers_from_laha/Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009.pdf`
     - p4-t0 and p5-t0: hline body start 2, value-anchor body start 9,
       selected 9.
  4. `papers_from_laha/Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf`
     - p2-t0 is no longer a continuation-blocking header schema failure:
       PyMuPDF text-position geometry now records
       `header_row_geometry_roles = group_header, leaf_header, leaf_header,
       leaf_header`, so p2-t0 and p3-t0 expose the same column header schema.
       The only schema change versus the prior no-backend-grid baseline is the
       intended p2-t0 split into two upper groups over cols 1-4 and 5-8; the
       periodontitis p6-t0 wrapped leaf headers remain flat leaf headers.
     - p5-t0: hline body start 1, value-anchor body start 0, selected 1.
  5. `papers_from_laha/Helicobacter pylori infection in the United States beyond NHANES- a scoping review of seroprevalence estimates by racial and ethnic groups.pdf`
     - p6-t0: hline body start 8, value-anchor body start 18, selected 7.
     - p7-t0: hline body start 8, value-anchor body start 7, selected 7.
  6. `papers_from_johnny/cardiovascular.pdf`
     - p5-t0.
     - hline body start 4, value-anchor body start 7, selected 7.
  7. `papers_from_johnny/hypertension.pdf`
     - `hypertension-p5-t0`.
     - First bad artifact: `extracted_tables.json`.
     - Current issue: the leaf header row is assigned word-by-word to
       body-derived column bands, so tight multiword wrapped headers are
       interleaved across adjacent columns. The table otherwise extracts,
       parses, and has `table_processing_status = rescued`.
     - Do not fix this by moving individual words across column boundaries.
       The next review should evaluate a cluster-first/header-cell-first
       extraction rule: build complete header clusters from positioned words,
       assign whole clusters to column bands or spans, and then let
       `ColumnHeaderSchema` stack vertical wrapped fragments.

- [ ] **C2.3** Review explicit hline and preamble behavior in papers with
  title/preamble rows above true column headers.
  1. `papers_from_johnny/fld.pdf`
  2. `papers_from_johnny/pad.pdf`
  3. `papers_from_laha/cobaltpaper.pdf`
  4. `papers_from_johnny/cardiovascular.pdf`
  5. `papers_from_laha/Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009.pdf`

- [ ] **C2.4** Decide whether raw PyMuPDF geometry should replace
  PyMuPDF4LLM-derived grids for specific failure classes.
  - Start only with ruled or rotated cases where words, rules, and table bbox
    provide strong structural evidence.
  - Do not add downstream continuation/schema hacks to compensate for bad
    extraction geometry.
  - Initial ruled-table path is implemented: when credible full-width stroked
    horizontal rules exist, extraction rebuilds the grid from positioned
    PyMuPDF words and hline geometry, using PyMuPDF4LLM only as a candidate
    region source. Keep this item open for broader replacement decisions,
    especially rotated and non-ruled layouts.
  - Current path-consistency audit target:
    `papers_from_laha/Science-Advanaced-Planetary Health Diet and risk of
    mortality and chronic diseases- Results from US NHANES, UK Biobank, and a
    meta-analysis.pdf`. Table 1 p2 and p3 now produce compatible grouped
    schemas and integrate, but p2 enters through whole-page PyMuPDF
    text-position extraction while p3 starts from a PyMuPDF4LLM rough table
    box plus hline word-position refinement. Determine why the same visual
    continued table does not use one canonical positioned-geometry path before
    adding any continuation or schema compensation.

Acceptance for C2: each disagreement is classified as correct caption
ownership, caption/body/footer ownership defect, figure-caption contamination of
a table artifact, correct hline split, correct value-anchor split, extraction
hline defect, normalization candidate defect, or unsupported/misrouted table
family.

### C3. Continuation Decisions

C3 should run after C2 because continuation decisions depend on correct
caption, header/body, footer, and column-schema evidence.

- [ ] **C3.1** Review accepted continuations and confirm one visual continued
  table becomes one semantic resolved table.
  1. `papers_from_laha/Association between anthropometric indices and chronic kidney disease- Insights from NHANES 2009–2018.pdf`
     - p7 -> p8 and p11 -> p12 accepted.
  2. `papers_from_laha/Helicobacter pylori infection in the United States beyond NHANES- a scoping review of seroprevalence estimates by racial and ethnic groups.pdf`
     - p5 -> p6 and p6 -> p7 accepted.
  3. `papers_from_laha/Systemic inflammation markers and the prevalence of hypertension- A NHANES cross-sectional study.pdf`
     - p5 -> p6 accepted.
  4. `papers_from_johnny/gallstones.pdf`
     - p5 -> p6 accepted.
  5. `papers_from_laha/mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017.pdf`
     - p5 -> p6 accepted.
  6. `papers_from_laha/Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009.pdf`
     - p4 -> p5 accepted for Table 1, and p6 -> p7 accepted for Table 2.
  7. `papers_from_laha/Asthma prevalence among United States population insights from NHANES data analysis.pdf`
     - p4 -> p5 accepted as a prefix fragment integrated with the
       below-captioned terminal Table 1 fragment after column-schema matching.
  8. `papers_from_laha/Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf`
     - p2 -> p3 accepted after grouped column-header schemas match.

- [ ] **C3.2** Review rejected continuation candidates that may expose header or
  column-schema defects.
  1. `papers_from_laha/Asthma prevalence among United States population insights from NHANES data analysis.pdf`
     - Prior p5 -> p6 false continuation is no longer present; p5-t1 and p6-t0
       pass through as singleton Table 2 and Table 3.
  2. `papers_from_laha/periodontis2.pdf`
     - Prior p5 -> p6 rejection is no longer present because page 6 no longer
       emits table candidates from prose references.

Acceptance for C3: continuation decisions are explainable from
`resolved_tables.json`, source table IDs, row provenance, captions or
continued-table labels, and `column_header_schemas.json`.

### C4. Mixed Table Families And Regression Baseline

- [ ] **C4.1** Review estimate-result and data-presentation tables without
  forcing them into descriptive Table 1 semantics.
  1. `papers_from_johnny/cardiovascular.pdf`
  2. `papers_from_johnny/stroke.pdf`
  3. `papers_from_laha/cobaltpaper.pdf`
  4. `papers_from_laha/An atlas of exposome–phenome associations in health and disease risk.pdf`
  5. `papers_from_laha/An environment-wide association study (EWAS) on type 2 diabetes mellitus.pdf`

- [ ] **C4.2** Re-run representative mostly-successful descriptive papers after
  fixes from C0-C4.1.
  1. `papers_from_laha/Systemic inflammation markers and the prevalence of hypertension- A NHANES cross-sectional study.pdf`
  2. `papers_from_laha/Lead exposure as a contributor to the Black–White racial disparity in blood pressure- evidence from NHANES 1988–1994 and 2017–2020.pdf`
  3. `papers_from_johnny/hypertension.pdf`
  4. `papers_from_johnny/pad.pdf`
  5. `papers_from_johnny/fld.pdf`

- [ ] **C4.3** Run the complete 27-PDF corpus after each substantial parser
  change set and compare against the latest accepted baseline. Report command
  failures, missing artifacts, table status counts, failure reasons, resolved
  continuation counts, footnote link statuses, reference resolution statuses,
  parsed cell-value counts, and header/body split disagreements.

Acceptance for C4: corpus comparison explains any movement in table-level
status, artifact counts, footnote/reference counts, or structural split
disagreements. Command success alone is not sufficient.

## Issue Note Template

Use this short note for each reviewed chunk or paper:

```text
Review ID:
PDF path:
output directory:
table_id/table_index:
current status:
first bad artifact:
earliest responsible stage:
observed evidence:
expected behavior:
fix decision:
regression decision:
```

## Scope Guardrails

- Do not add paper-specific vocabulary rules to make one paper pass.
- Do not judge success from CLI exit status alone.
- Do not debug downstream semantics before confirming extraction and
  normalization are structurally correct.
- Do not treat row highlighting or background fills as horizontal-rule
  separators.
- Do not force data/result tables into descriptive Table 1 semantics.
- Do not create broad unit-test expansion; add focused regressions for known
  failures or artifact contracts.
- Do not add R helpers before repeated review use shows what is needed.
- Do not add word-level header reassignment across column boundaries. Header
  reconstruction should operate on complete positioned clusters/cells and then
  assign those units to column bands or spans.
