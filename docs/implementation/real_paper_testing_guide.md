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

All paper paths below are relative to:

```text
/Users/robert/Projects/Epiconnector/testpapers
```

## Current Reference Baseline

Latest reference run:

```text
outputs/testpapers_batch_20260706_page_furniture_front
```

The current refreshed baseline is
`outputs/testpapers_batch_20260706_page_furniture_front`. It was produced after
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
require bibliographies to be numbered.

Older generated `outputs/` runs should not be treated as current.

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
  anchors: 380
  definitions: 193
  links: 380
  resolved links: 380
  inferred links: 0
  ambiguous links: 0
  unresolved links: 0
  math/unit anchors suppressed before footnote linking: 35
  subscript anchors suppressed before footnote linking: 6
  word-like subscript anchors suppressed before footnote linking: 0
  citation-like anchors suppressed before footnote linking: 47
  PDF text blocks classified as table footers: 49
  page-furniture filter stage: before_pdf_definition_block_construction (27 papers)
extraction page-furniture mask:
  extracted tables with mask metadata: 71
  page words removed before extraction/refinement: 987
  page chars removed before extraction/refinement: 8150
  explicit-grid rows removed by page-furniture mask: 0
```

Current papers with unresolved or ambiguous footnote links:

- None in `outputs/testpapers_batch_20260706_page_furniture_front`.

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
- Early page-furniture masking plus trailing-trim retirement reduces the
  full-corpus footnote issue count from 669 unresolved / 16 ambiguous links to
  56 unresolved / 6 ambiguous links.
- The footer-block finder reduces the current full-corpus footnote issue count
  from 56 unresolved / 6 ambiguous links to 11 unresolved / 7 ambiguous links.
- Eke drops from 529 unresolved / 11 ambiguous links to 6 unresolved / 2
  ambiguous links in the full-corpus baseline.
- Rotated Ethnic table annotation cleanup and bibliography/citation suppression
  resolved the prior Ethnic false-marker issue. Caption/footer footnote parsing
  now resolves the remaining metabolic, Systemic inflammation, Planetary Health,
  and Ethnic Differences caption/footer markers through general table-local
  marker-definition parsing rather than paper-specific link patches.
- OR/CI estimate routing and matrix-like table status guards reduce table-level
  failures from 9 to 4: 3 true `non_table_layout_candidate` narrative/reference
  artifacts and 1 `insufficient_table_structure_after_extraction` general
  reference table.

## Review Loop

For each checklist item:

1. Inspect the current artifacts under the reference baseline first.
2. Identify the first bad artifact in parser order:
   `extracted_tables.json`, `normalized_tables.json`,
   `column_header_schemas.json`, `resolved_tables.json`,
   `table_definitions.json`, `parsed_cell_values.json`,
   `parsed_tables.json`, `paper_footnotes.json`, `paper_bibliography.json`,
   `paper_style_profile.json`, `paper_references.json`.
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
    `outputs/testpapers_batch_20260706_page_furniture_front` resolves all 15
    Table 1 `letter:a` / `letter:b` links against the below-table footer note.
    In the PDF text the definitions appear collapsed as `aRepresents ...` and
    `bRepresents ...`, but the parser now splits them from smaller raised
    glyph evidence. Table 2 now resolves all 21 `*` links against the explicit
    same-table footer sentence
    `The asterisk indicates statistical significance`, rather than emitting
    conventional inferred links.

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
    `outputs/testpapers_batch_20260706_page_furniture_front` extracts page
    7 with no `letter:t`, `letter:r`, or `letter:l` anchors.
    `paper_footnotes.json` builds the page 7 `†` and `‡` definitions from
    extracted footer row blocks, including their continuation rows. Remaining
    links are 5 unresolved and 7 ambiguous: mostly numeric citation-like markers
    and repeated table/page footer definitions that currently only link at
    paper-level scope.

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
    `outputs/testpapers_batch_20260706_page_furniture_front` has 2 resolved
    links and 0 unresolved or ambiguous links. `S_I` and `AIR_g` remain
    suppressed as subscript notation, and the marker-font `x` resolves against
    the local `xP < 0.05 vs. East Asian` footer definition through confirmed
    footer-cell marker evidence.

- [x] **C0.4** Resolve statistical-significance stars with footer definitions
  in `stroke`.
  - PDF path: `papers_from_johnny/stroke.pdf`
  - Previous artifact issue: 65 unresolved links.
  - Strong signal: 58 unresolved anchors were statistical-significance
    asterisks, often attached to p-values such as `<0.001***`.
  - Current result: fixed in
    `outputs/testpapers_batch_20260706_page_furniture_front`; Table 1,
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
    `outputs/testpapers_batch_20260706_page_furniture_front` resolves all 4
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
    `outputs/testpapers_batch_20260706_page_furniture_front`. Known symbol
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
  - Current result: `outputs/testpapers_batch_20260706_page_furniture_front` has 0
    unresolved and 0 ambiguous footnote links for this paper.

- [x] **C0.6a** Re-review repeated letter markers on continued tertile headers.
  - PDF path: `papers_from_laha/Systemic inflammation markers and the prevalence of hypertension- A NHANES cross-sectional study.pdf`
  - Current result:
    `outputs/testpapers_batch_20260706_page_furniture_front` resolves all 12
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
     - Current status in `outputs/testpapers_batch_20260706_page_furniture_front`:
       `ok`, categorized as `analysis_outputs`.
     - Review result: structurally plausible ENWAS analysis-output table with
       sparse left descriptor columns; not a Table 1 descriptive failure.
  2. `papers_from_laha/mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017.pdf`
     - `mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017-p3-t0`
     - Current status in `outputs/testpapers_batch_20260706_page_furniture_front`:
       `failed`, reason: `insufficient_table_structure_after_extraction`,
       categorized as `general`.
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
     - Current status: still `failed`, reason `non_table_layout_candidate`.
     - Review result: abstract/title-page text laid out as columns, not a table
       artifact to route semantically.
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
     - `periodontis2-p6-t0`
     - Current status: still `failed`, reason `non_table_layout_candidate`.
     - Review result: prose paragraph text reconstructed as a four-column
       layout candidate, not a table artifact.
  5. `papers_from_johnny/periodontitis.pdf`
     - `periodontitis-p11-t0`
     - Current status: still `failed`, reason `non_table_layout_candidate`.
     - Review result: abbreviation glossary/reference block, not a table
       artifact.

- [x] **C1.3** Review the collapsed-grid failure.
  - PDF path: `papers_from_laha/Ethnic Differences in the Relationship Between Insulin Sensitivity and Insulin Response.pdf`
  - Table: `Ethnic Differences in the Relationship Between Insulin Sensitivity and Insulin Response-p5-t0`
  - Current status: `rescued`; the prior `collapsed_grid_unrecovered` failure is
    no longer present in `outputs/testpapers_batch_20260706_page_furniture_front`.
  - Current footnote result: 2 resolved links and 0 unresolved links. The prior
    residual `letter:i`, `letter:x`, and `letter:g` false-marker issue is no
    longer present as unresolved footnote evidence; the remaining `letter:x`
    marker resolves through confirmed footer-cell marker evidence for the local
    `xP < ...` table note.

Acceptance for C1: every failed table is classified as correct non-target table,
extraction failure, normalization failure, unsupported table family, or ambiguous
pending review.

### C2. Continuation Decisions

- [ ] **C2.1** Review accepted continuations and confirm one visual continued
  table becomes one semantic resolved table.
  1. `papers_from_laha/Association between anthropometric indices and chronic kidney disease- Insights from NHANES 2009–2018.pdf`
     - p7 -> p8 and p11 -> p12 accepted.
  2. `papers_from_laha/Helicobacter pylori infection in the United States beyond NHANES- a scoping review of seroprevalence estimates by racial and ethnic groups.pdf`
     - p5 -> p6 and p6 -> p7 accepted.
  3. `papers_from_laha/Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009.pdf`
     - p6 -> p7 accepted.
  4. `papers_from_laha/Systemic inflammation markers and the prevalence of hypertension- A NHANES cross-sectional study.pdf`
     - p5 -> p6 accepted.
  5. `papers_from_johnny/gallstones.pdf`
     - p5 -> p6 accepted.
  6. `papers_from_laha/mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017.pdf`
     - p5 -> p6 accepted.

- [ ] **C2.2** Review rejected continuation candidates that may expose header or
  column-schema defects.
  1. `papers_from_laha/Asthma prevalence among United States population insights from NHANES data analysis.pdf`
     - p4 -> p5 rejected; p5 -> p6 rejected.
  2. `papers_from_laha/Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009.pdf`
     - p4 -> p5 rejected.
  3. `papers_from_laha/Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf`
     - p2 -> p3 rejected.
  4. `papers_from_laha/periodontis2.pdf`
     - p5 -> p6 rejected.

Acceptance for C2: continuation decisions are explainable from
`resolved_tables.json`, source table IDs, row provenance, and
`column_header_schemas.json`.

### C3. Header/Body And Extraction Geometry

- [ ] **C3.1** Review current header/body split disagreements.
  1. `papers_from_laha/Association between metabolic score for insulin resistance (METS-IR) and hypertension- a cross-sectional study based on NHANES 2007–2018.pdf`
     - p6-t0: hline body start 2, value-anchor body start 3, selected 2.
  2. `papers_from_laha/Asthma prevalence among United States population insights from NHANES data analysis.pdf`
     - p5-t0 and p6-t0.
  3. `papers_from_laha/GOLD BioAge and depression- Associations with mortality among depressed NHANES participants (2005–2018).pdf`
     - p4-t1: hline body start 2, value-anchor body start 4, selected 2.
  4. `papers_from_laha/Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009.pdf`
     - p4-t0 and p5-t0: hline body start 3, value-anchor body start 10,
       selected 10.
  5. `papers_from_johnny/Sarcopenia.pdf`
     - p7-t0 and p8-t0.
  6. `papers_from_laha/Science-Advanaced-Planetary Health Diet and risk of mortality and chronic diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf`
     - p2-t0.
  7. `papers_from_johnny/cardiovascular.pdf`
     - p5-t0.
  8. `papers_from_laha/mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017.pdf`
     - p7-t0.

- [ ] **C3.2** Review explicit hline and preamble behavior in papers with
  title/preamble rows above true column headers.
  1. `papers_from_johnny/fld.pdf`
  2. `papers_from_johnny/pad.pdf`
  3. `papers_from_laha/cobaltpaper.pdf`
  4. `papers_from_johnny/cardiovascular.pdf`
  5. `papers_from_laha/Journal of Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in the United States  NHANES 2009.pdf`

- [ ] **C3.3** Decide whether raw PyMuPDF geometry should replace
  PyMuPDF4LLM-derived grids for specific failure classes.
  - Start only with ruled or rotated cases where words, rules, and table bbox
    provide strong structural evidence.
  - Do not add downstream continuation/schema hacks to compensate for bad
    extraction geometry.

Acceptance for C3: each disagreement is classified as correct hline split,
correct value-anchor split, extraction hline defect, normalization candidate
defect, or unsupported/misrouted table family.

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
