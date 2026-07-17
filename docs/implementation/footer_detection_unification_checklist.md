# Footer Detection Unification Checklist

Goal: run one bottom-of-table footer detector for every table. The detector may
consume horizontal-rule, data-column occupancy, typography, and positioned
text evidence, but footer detection, ownership, and footnote-definition
processing must not be split across different routes.

Focused failure:

`Helicobacter pylori infection in the United States beyond NHANES- a scoping
review of seroprevalence estimates by racial and ethnic groups.pdf`, PDF page
7, printed Table 1. Row 47 is `aValue shows median age rather than mean.`; only
the stub is populated, its leading span is 4.58 pt versus 6.48 pt for the
following text, and the bottom horizontal line follows it. Row 46 contains
`study` in data column 1 and must remain body content.

Reference runs:

```text
outputs/testpapers_batch_phase_k_step5_guarded_final_20260715
outputs/testpapers_batch_canonical_orientation_step3_full_20260716
```

## Constraints

- Keep physical rows, cells, raw text, source character/span references, and
  horizontal-rule evidence unchanged.
- Treat a superscript as supporting evidence, not sufficient footer evidence.
- Require a clear observed font or font-size change for every accepted footer.
  A horizontal rule supplies boundary geometry but never replaces typography.
- Do not trust provisional column indices to establish footer identity. Use
  direct positioned-text continuity and gaps first; provisional data-column
  occupancy may only support the decision.
- Reuse existing table-region, positioned-line, boundary-proposal, annotation,
  and footnote models. Add no class, artifact, framework, repair pass, or
  paper-specific wording rule.
- Run one footer detector exactly once per table. Text above a bottom rule,
  text below it, and text where no bottom rule exists are evidence
  configurations inside that detector, not separate routes or fallbacks.
- Validate the completed change against the complete 28-PDF corpus; the focused
  Helicobacter failure is a required inspection within that corpus run, not a
  substitute for it.

## Approved Bottom-Up Footer Algorithm

- [ ] **1. Honor an existing outgoing-continuation decision**
  - If `continues_on_next_page` is true, assign no footer and stop footer
    detection for that fragment.
  - This step consumes the flag only. Detecting and linking continuation
    fragments is a separate problem and is not part of this footer change.

- [ ] **2. Build one ordered bottom view**
  - Order raw physical line groups and horizontal rules within the canonical
    candidate bounds.
  - Use raw positioned lines, horizontal rules, line order, left position,
    font name, font size, and observed space widths only.
  - Do not use cells, columns, `col_idx`, body occupancy, or vocabulary rules.

- [ ] **3. Select exactly one starting element**
  - Start at the final ordered element.
  - If it is a closing horizontal rule, move to the immediately preceding raw
    physical line group.
  - Otherwise, start with the final raw physical line group.
  - Do not inspect text below the candidate bounds.

- [ ] **4. Validate the first candidate line**
  - Require it to be left-justified to the candidate's left edge.
  - Reject a continuation notice or DOI.
  - Require dominant font name or font size to differ from ordinary page prose.
  - Require it to be prose-like.
  - Reject it when adjacent positioned runs contain a horizontal gap larger
    than two observed space widths for that font and size.
  - If any condition fails, assign no footer and stop.

- [ ] **5. Walk upward one element at a time**
  - After accepting a line, inspect exactly the next element upward.
  - Stop before that element if it is a horizontal rule.
  - Stop before that line if its dominant font name differs from the current
    accepted line. Preserve font-size variation within one source PDF text
    block; a font-size change across source blocks remains a stop.
  - Stop before that line if it is not left-justified.
  - Stop before that line if it is not prose-like.
  - Stop before that line if adjacent positioned runs contain a horizontal gap
    larger than two observed space widths for that font and size.
  - Otherwise, prepend the line to the footer suffix and continue upward.

- [ ] **6. Accept only the collected bottom suffix**
  - Never restart above the stopping point.
  - Never test another horizontal rule.
  - Assign every collected line to the footer and leave every line above the
    stopping point outside the footer.
  - Remove accepted internal footer rows from `TableRegion.body_rows` and place
    them in `TableRegion.footer_note_rows`.
  - Preserve accepted external line IDs, bbox, styles, and table association in
    the existing boundary-candidate fields.

- [ ] **7. Verify the two Table 3 fragments**
  - In `Association between anthropometric indices and chronic kidney disease-
    Insights from NHANES 2009–2018.pdf`, page 11, printed Table 3, the first
    group above the closing rule is Q3 data with separated positioned runs.
    Assign no footer and do not reach `Classified by C-index quantiles`.
  - In `Association between anthropometric indices and chronic kidney disease-
    Insights from NHANES 2009–2018.pdf`, page 12, printed Table 3, collect the
    three left-justified prose lines above the closing rule, stop at the
    preceding horizontal rule, keep `p for trend` as data, and exclude the DOI
    below the candidate bounds.

- [ ] **8. Verify the focused failure and complete corpus**
  - In `Helicobacter pylori infection in the United States beyond NHANES- a
    scoping review of seroprevalence estimates by racial and ethnic groups.pdf`,
    page 7, printed Table 1, assign row 47 as the sole footer row and retain row
    46 as body content.
  - Run and compare the complete 28-file corpus with up to six workers.
  - Run the existing relevant pytest commands and full pytest without adding a
    new test unless separately approved.

## Steps

- [x] **0. Freeze the agreed single-detector rule**
  - Build one ordered view of the table's bottom boundary from existing
    extracted rows, final-rule evidence when present, and adjacent positioned
    text. Do not persist a new artifact for this view.
  - Starting at the table bottom, identify one consecutive prose-like block.
    Its physical lines must not contain the separated horizontal runs or
    table-sized gaps characteristic of data rows. Reuse the existing observed
    space-width evidence rather than inventing a fixed distance.
  - Use any content in an established data band as supporting stop evidence,
    not only a numeric or recognized value. Do not make this depend on the
    provisional physical column count.
  - When potential footer text is below a bottom horizontal line, require the
    row above the line to contain data and require the candidate typography to
    differ from ordinary page prose.
  - When potential footer text is above a bottom horizontal line, use the line
    as the table's outer bound and use the same backward positioned-text scan
    to delimit the candidate block.
  - When no bottom horizontal line exists, require a clear font or font-size
    change at the boundary from the last data-containing row to the potential
    footer block.
  - In every configuration, require a clear positioned font or font-size
    change. A smaller leading definition span may supply that evidence, but a
    superscript label by itself may not.
  - Apply one acceptance, ownership, raw-text preservation, and definition-
    parsing sequence after those evidence conditions are evaluated.

- [x] **1. Audit and select the single ownership point**
  - Trace every current rule-following-text, extracted-row, marker-led,
    `TableRegion.footer_note_rows`, and `FootnoteFooter` decision.
  - Select one existing function/stage that can examine both internal rows and
    adjacent external positioned text before body occupancy is finalized.
  - List the exact competing footer detectors to remove. Evidence collection
    may remain in its owning artifact, but it must not make an independent
    footer decision.

  Audit result:

  - The single ownership point will be `build_table_region()` in
    `table1_parser/table_regions.py`, called once per table by
    `build_table_regions()`. It runs before body occupancy and already receives
    the extracted grid, `TableBoundaryProposal`, canonical positioned page,
    and `CellTextAnnotationTable`; its wrapper already receives the shared
    `PaperTextStream`, including the ordinary page-text style.
  - Internal accepted rows remain represented by
    `TableRegion.footer_note_rows`. Accepted external positioned lines remain
    represented by the final `TableBoundaryCandidate.following_text_line_ids`,
    bbox, styles, and `body_footer` role. No schema or artifact is required.
  - `build_table_boundary_proposal()` currently goes beyond evidence
    collection: it filters following lines using page-body style, gap, resumed
    body, and smaller-font conditions, then assigns `body_footer`. It must be
    reduced to collecting final-rule, adjacent-line, bbox, and style evidence;
    it must not accept a footer.
  - `build_table_region()` currently contains two internal decisions: the
    proposal-backed boundary/occupancy selection and the separate `_footer_rows()`
    branch. `_footer_marker_rows_by_table_id()` and `_footer_rows()` are the
    competing marker/rule detector to remove when their evidence is folded
    into the one bottom-of-table decision.
  - `find_table_footer_definition_lines()` in
    `table1_parser/paper_footnotes.py` currently re-decides external ownership
    from a structured marker, smaller table-local type, or three physical
    lines. That acceptance gate must move to the single region-stage detector;
    marker geometry may remain there only as definition evidence after
    ownership is established.
  - `find_table_footer_rows()` is already a pure projection of final
    `TableRegion.footer_note_rows`. The extracted-row/text-stream footer
    builders, `build_paper_footnote_definition_candidates()`, and
    `link_paper_footnotes()` can remain downstream consumers provided none
    independently accepts or rejects footer ownership.
  - The retained 28-PDF reference has 91 region/proposal records, 67 final-rule
    adjacent-text bands provisionally labelled `body_footer`, 55 accepted
    external footers, and 10 internal footer regions containing 59 rows: 65
    `FootnoteFooter` records in total. The current pre-change 28-PDF run has 87
    region/proposal records, the same 67 provisionally labelled external
    bands, 56 accepted external footers, and six internal footer regions
    containing 29 rows: 62 footers in total. The 67-to-55/56 reduction confirms
    that external footer ownership is currently decided twice.
  - Because the canonical column grid is not yet final at this stage, the
    unified detector must qualify a potential footer as a continuous
    positioned prose band with no gap at least two observed space widths. Font
    or font-size change is mandatory in addition to that continuity. Existing
    cell/data-band alignment may stop the backward scan, but cannot be its sole
    basis.

- [x] **2. Implement the one bottom-of-table detector**
  - Call it once for every table with the existing extracted grid, final-rule
    evidence, positioned lines/styles, and cell annotations.
  - Perform one positioned-text continuity/gap scan and one mandatory local
    typography comparison while treating provisional data-column alignment and
    the final rule, when present, as supporting evidence rather than dispatch
    choices.
  - Preserve the complete multirow potential footer block and its internal-row
    or external-line provenance.
  - Record the evidence basis using existing detection-basis or notes fields;
    do not introduce a new candidate model.

  Implementation result:

  - `build_table_region()` now makes the sole footer-ownership decision. It
    uses canonical row/line geometry, existing annotation font evidence, the
    existing two-observed-space occupancy threshold, consecutive-row spacing,
    and positioned data-band support. The final rule remains supporting
    geometry and an outer rule after an internal footer is not mislabeled as
    the body/footer separator.
  - `build_table_boundary_proposal()` now only retains rule and adjacent-line
    evidence; it no longer assigns `body_footer`.
  - Visual-object DOI source lines are collected once from the shared
    `PaperTextStream` and passed into `build_table_region()` as owned lines. The
    first aligned DOI line is a hard terminal barrier for both adjacent footer
    text and later rule events, so it is never offered to the bottom-up footer
    owner while remaining available to `paper_visual_inventory.json`.
    `outputs/testpapers_batch_doi_barrier_20260716` completed all 28 PDFs and
    changed table shapes and footer ownership only for the five DOI-blocked
    candidates on PDF pages 8, 10, 12, and 13 of
    `Association between anthropometric indices and chronic kidney disease- Insights from NHANES 2009–2018.pdf`.
  - A candidate's existing `candidate_visual_object_barrier_bbox` now supplies
    the same terminal evidence when its top edge is exactly below the canonical
    table bbox. Images above a below-captioned table do not qualify. External
    text at or beyond the following image is never offered to the footer owner;
    no distance tolerance, alternate scan, or new artifact is introduced. In
    `Systemic inflammation markers and the prevalence of hypertension- A NHANES cross-sectional study.pdf`,
    PDF page 6, printed Table 1 continued, this stops at the image beginning at
    y=337.890 and accepts exactly source lines 72-75 at y=266.881-311.592. The
    28-PDF checkpoint is
    `outputs/testpapers_batch_visual_object_footer_barrier_final_20260716`.
    All 91 physical grids and 77 resolved tables remain unchanged; the other
    five image-bearing candidates retain their structural artifacts apart from
    parse-quality timestamps.

- [x] **3. Use one footer acceptance and processing path**
  - Apply raw-text preservation, positioned evidence, marker support,
    ownership, and footnote-definition parsing in the detector's single
    processing sequence.
  - Remove accepted internal rows from `TableRegion.body_rows` and place them
    in `footer_note_rows`.
  - Keep accepted below-rule text outside the physical table grid while
    retaining its table association and positioned provenance in the existing
    footer artifact.
  - Remove the older rule-only, marker-only, extracted-row, and text-stream
    footer decisions so none can accept or reject a footer independently.

  Implementation result:

  - The proposal-backed interval selector, `_footer_marker_rows_by_table_id()`,
    `_footer_rows()`, late external marker/font/line-count acceptance gate, and
    CLI role-removal pass are removed.
  - Accepted internal bands always enter definition processing; markers may
    split definitions but no longer determine whether accepted text is passed
    through. Existing footer, definition, and marker models remain unchanged.

- [ ] **4. Run and compare the complete 28-PDF corpus**
  - Run with up to six bounded workers into a fresh ignored output directory.
  - Compare first against the pre-footer full run to isolate footer effects,
    then against the retained reference to report the broader state accurately.
  - Report every changed footer candidate, `TableRegion`, body occupancy, leaf
    geometry, physical grid, footnote artifact, and processing status.
  - Accept only changes directly explained by the agreed evidence conditions
    inside the single detector.
  - Do not fix unrelated extraction differences in this step.
  - Within the corpus output, confirm that Helicobacter PDF-page-7 row 47 is
    the sole internal footer row, row 46 remains body content, the
    4.58-to-6.48-pt evidence and raw text are preserved, and PDF pages 5 and 6
    are unchanged.
  - Recheck the terminal fragment's physical column count; report whether
    excluding the footer from body occupancy restores 15 columns rather than
    assuming that it will.
  - Report a non-operative cross-check of every newly accepted internal footer
    row against the settled body occupancy vector and header-aligned column
    bands. A row that reproduces the body's whitespace pattern may be a body
    row assigned to the footer; record it for review, but do not add a second
    ownership or repair path during this run.
  - Run the existing relevant tests and full pytest; add no new test without
    separate approval.

- [ ] **5. Close the change**
  - Update this checklist and the parser ToDo with the full-corpus evidence and
    the required Helicobacter inspection.
  - Confirm obsolete competing footer logic and descriptions are removed or
    aligned.
  - Confirm unrelated dirty R, README, man-page, vignette, and `tmp/` files are
    untouched and unstaged.
