# Phase K: Footer Definition Ownership And Marker Resolution

Status: complete.

This checklist aligns the existing footnote extraction and linking code with
the final table-region, marker, and continuation artifacts. It does not add a
new footnote subsystem.

Current corpus checkpoint:
`outputs/testpapers_batch_phase_k_step5_guarded_final_20260715`.

Step 4 was compared with the retained Step 3 baseline:
`outputs/testpapers_batch_phase_k_step3_final_20260715`.

Phase K must not change physical rows, columns, cells, occupancy, header
structure, normalized values, canonical table selection, or accepted
continuation identity. The approved follow-up exception removes one explicit
non-table continuation cue before `ExtractedTable` ownership; its raw text and
positioned evidence remain preserved.

## 0. Lock The Scope And Baseline

- [x] Identify the existing models and parser functions used for marker
      occurrences, footer rows, footer definitions, links, and continuation
      scope.
- [x] Record the current marker partition: 433 marker occurrences become 400
      footnote anchors, 30 mathematical or unit suppressions, and 3 subscript
      suppressions.
- [x] Record the current link results: 346 resolved and 54 unresolved, including
      13 possible bibliography references.
- [x] Confirm that Stage K should reuse `CellTextAnnotation`, `TableRegion`,
      `TableBoundaryProposal`, `ResolvedTableSet`, and the existing paper
      footnote models.
- [x] Confirm that no new schema class, artifact, helper layer, or fallback path
      is required.

## 1. Use One Footer-Ownership Path

- [x] For footer rows inside an extracted grid, consume only the matching final
      `TableRegion.footer_note_rows`.
- [x] Remove the late fallback in `find_table_footer_rows()` that re-infers
      footer rows from the last value row and horizontal rules.
- [x] Remove `_last_value_matrix_row_idx()` if it becomes unused.
- [x] For footer text outside the extracted grid, start only from positioned
      lines attached to the table's final rule through
      `TableBoundaryProposal.following_text_line_ids`.
- [x] Use table-local typography and exact marker geometry to decide whether
      those adjacent lines form a footer.
- [x] Replace the broad scan of arbitrary styled text below the table bounding
      box; do not retain both paths.
- [x] Preserve source line IDs, bounding boxes, font evidence, and raw text for
      every retained footer.

Step 1 is complete when every retained footer is owned either by a final
`TableRegion` footer band or by positioned lines immediately following the
table's final rule.

Step 1 checkpoint:

- `outputs/testpapers_batch_phase_k_continuation_cue_final_20260715` contains
  all 28 PDFs,
  91 physical extraction objects, 78 resolved tables, and 13 accepted
  continuation integrations. Statuses remain 16 `ok`, 62 `rescued`, and 0
  `failed`.
- The retained footer inventory falls from 134 broad-scan records to 65 owned
  records: 10 from final `TableRegion.footer_note_rows` and 55 from final-rule
  `following_text_line_ids`. Every extracted row index and every external
  source line ID exactly matches its owning artifact.
- All 400 anchor link outcomes remain unchanged at 346 resolved and 54
  unresolved. Thirteen resolved anchors in
  `mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older
  Adults- NHANES 2007–2017.pdf`, PDF pages 6–9, now retain their complete
  definition paragraphs instead of text truncated at 8.0/7.9-point font-size
  jitter.
- Continuation labels and DOI lines formerly found only by the broad external
  scan are gone, as is the numeric `All-cause mortality ... Random-effects
  model` body row on PDF page 5, printed Table 2 of
  `Science-Advanaced-Planetary Health Diet and risk of mortality and chronic
  diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf`.
  The literal `Continued` cue on PDF page 4, printed Table 1 of
  `Asthma prevalence among United States population insights from NHANES data
  analysis.pdf` is now removed before table ownership because its final row has
  no data-column value. The cue remains recorded in
  `metadata.trailing_non_table_rows`; the page-5 `Missing values` row retains
  `9303 (14.5)` and remains a level of `Ever told you had chronic bronchitis`
  in the resolved table definition.

## 2. Align Occurrence And Definition Markers

- [x] Reuse each `CellTextAnnotation.annotation_id` as the corresponding
      footnote-anchor identity instead of creating a second positional
      occurrence identity.
- [x] Continue storing definition markers separately as
      `FootnoteDefinitionMarkerEvidence` records.
- [x] Accept a smaller, raised definition marker at the beginning of its own
      physical line without requiring punctuation at the end of the preceding
      line.
- [x] Preserve the complete raw definition text and its positioned evidence.
- [x] Do not assign a conventional meaning to a marker unless the PDF contains
      an explicit definition.

Step 2 is complete when `hypertension.pdf`, PDF page 6, printed Table 2 links
the `a` in `Model 3a` to its explicit footer definition.

Step 2 checkpoint:

- All 433 `CellTextAnnotation` records retain unique annotation IDs. The 400
  promoted anchors now use those exact IDs, and each anchor records the source
  annotation type, including `superscript`; the full character, span, font,
  and bounding-box evidence remains in `cell_text_annotations.json`.
- `hypertension.pdf`, PDF page 6, printed Table 2 now links
  `hypertension-p6-t0:marker:0` to the explicit `a` definition. The marker is
  the first glyph of `page-6-line-22`, at 4.9 points against the line's
  7.0-point dominant text, and is smaller and raised. The complete unsplit
  footer text and exact marker bbox are preserved.
- The full 28-PDF checkpoint retains 91 physical extraction objects, 78
  resolved tables, 13 accepted continuation integrations, and statuses of 16
  `ok`, 62 `rescued`, and 0 `failed`. All extraction, geometry, normalization,
  header, continuation, table-definition, and parsed-table artifacts are
  byte-for-byte unchanged.
- Link counts move only from 346 resolved / 54 unresolved to 347 resolved / 53
  unresolved. The hypertension link is the only changed link outcome at this
  checkpoint; the 40 stars whose explicit asthma-caption definitions were not
  yet recognized remain unresolved, and all 13 numeric bibliography candidates
  remain available to the bibliography artifact.
- `paper_style_profile.json` and the 13 bibliography mention IDs inherit the
  stable occurrence identity. After normalizing that intended identity change,
  the bibliography artifacts are unchanged; the hypertension style profile is
  the only derived style result changed by the newly resolved explicit link.

## 3. Use Canonical Continuation Scope

- [x] Pass the final `ResolvedTableSet` to the existing footnote extraction and
      linking path.
- [x] Derive same-logical-table scope from accepted source-table membership.
- [x] Remove the footnote path's dependency on the older
      `Table1ContinuationGroup` review artifact.
- [x] Resolve a marker against a terminal-page definition only when the source
      fragments belong to the same accepted logical table.
- [x] Preserve the existing glyph, table, page, continuation, and footer-
      geometry ranking in `link_paper_footnotes()`.

Step 3 is complete when existing cross-page definition links are unchanged for:

- `Science-Advanaced-Planetary Health Diet and risk of mortality and chronic
  diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf`, PDF
  pages 2–3, printed Table 1.
- `Association between anthropometric indices and chronic kidney disease-
  Insights from NHANES 2009–2018.pdf`, PDF pages 7–8, printed Table 1, and PDF
  pages 11–12, printed Table 3.

Step 3 checkpoint:

- The existing footnote builders and linker now receive the final
  `ResolvedTableSet`. `paper_footnotes.py` no longer imports or accepts
  `Table1ContinuationGroup`; that artifact remains a non-canonical Table 1
  inspection view only.
- Cross-fragment eligibility is built inline from source-table IDs belonging to
  an accepted `integrated_continuation`. Exact same-table links retain their
  higher rank, accepted continuation links retain the existing `same_visual`
  rank, and same-page and paper-level ranks are unchanged. A rejected
  continuation cannot share table scope merely because it prints the same
  table number.
- Focused outputs preserve all existing cross-page targets exactly: 3 links in
  `Science-Advanaced-Planetary Health Diet and risk of mortality and chronic
  diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf`, PDF
  pages 2–3, printed Table 1; and 77 links in `Association between
  anthropometric indices and chronic kidney disease- Insights from NHANES
  2009–2018.pdf`, PDF pages 7–8, printed Table 1 and PDF pages 11–12, printed
  Table 3.
- The historical rejected case in `periodontis2.pdf`, PDF pages 10–11, printed
  Table 1 confirms the guard: page 10 keeps `paper_visual:table:1`, while the
  rejected page-11 fragment receives no shared visual ID.
- The full 28-PDF checkpoint retains 91 physical extraction objects, 78
  resolved tables, 13 accepted continuation integrations, statuses of 16
  `ok`, 62 `rescued`, and 0 `failed`, and 347 resolved / 53 unresolved links.
  All 94 cross-fragment links belong to accepted resolved memberships and are
  unchanged from Step 2.
- The only non-timestamp artifact difference is corrected provenance in
  `periodontis2.pdf`: terminal footers and definitions on PDF pages 13, 15, and
  17 now inherit the accepted visual IDs for printed Tables 2, 3, and 4. No
  footer text, definition text, marker, or link outcome changes.

## 4. Preserve Explicit Resolution Outcomes

- [x] Keep `resolved`, `ambiguous`, and `unresolved` link outcomes explicit.
- [x] Keep possible numeric bibliography references available to the
      bibliography stage rather than treating them as footnote definitions.
- [x] Keep mathematical, unit, subscript, and other non-footnote notation in
      the Phase I annotation evidence.
- [x] Verify that every one of the 433 marker occurrences belongs to exactly
      one anchor or suppression outcome.
- [x] Keep unresolved markers unresolved when no explicit definition exists.

Step 4 is complete when the 40 star occurrences in `Asthma prevalence among
United States population insights from NHANES data analysis.pdf`, PDF page 6,
printed Table 3 resolve to the caption's explicit `*p < 0.05`, `**p < 0.01`,
and `***p < 0.001` definitions without assigning a conventional meaning to any
undefined marker.

Step 4 checkpoint:

- The caption-definition branch now accepts only a trailing explicit symbol
  block after completed caption prose. It reuses the existing symbol-block
  parser, preserves the complete caption as `raw_text`, and recognizes a
  marker attached directly to its definition body. The former broad
  letter/number caption regex is removed rather than retained in parallel.
- In `Asthma prevalence among United States population insights from NHANES
  data analysis.pdf`, PDF page 6, printed Table 3, the caption supplies three
  explicit definition records and all 40 table-cell star occurrences resolve.
  No p-value meaning is inferred beyond the caption's own text.
- Five false caption definitions are removed: prose `a` in `gallstones.pdf`,
  PDF page 7, printed Table 2; `S` in the duplicated title/caption text for
  `Asthma prevalence among United States population insights from NHANES data
  analysis.pdf`, PDF page 5, printed Table 1; and `2009` in the captions for
  `Journal of Periodontology - 2015 - Eke - Update on Prevalence of
  Periodontitis in Adults in the United States  NHANES 2009.pdf`, PDF pages
  4–5, printed Table 1. None had a linked occurrence.
- All 433 Phase I annotations partition exactly into 400 anchors, 30
  mathematical or unit suppressions, and 3 subscript suppressions. The corpus
  now has 105 definitions, 387 resolved links, 0 ambiguous links, and 13
  unresolved numeric bibliography candidates.
- The 28 PDFs retain 91 physical extraction objects, 78 resolved tables, 13
  accepted continuation integrations, and statuses of 16 `ok`, 62 `rescued`,
  and 0 `failed`. Extraction, region, annotation, occupancy, normalization,
  header, continuation, resolved-table, value, table-definition, parsed-table,
  bibliography, and status artifacts are byte-for-byte unchanged. Only the
  three affected `paper_footnotes.json` and derived
  `paper_style_profile.json` artifacts change.

## 5. Run Focused Real-Paper Checks

- [x] Parse `hypertension.pdf` and confirm that the physical-line-start `a`
      definition is retained and linked.
- [x] Parse `Asthma prevalence among United States population insights from
      NHANES data analysis.pdf` and confirm that its explicitly defined stars
      resolve to the caption definitions.
- [x] Parse the two continuation examples in Step 3 and compare exact link
      targets with the baseline.
- [x] Parse `Journal of Periodontology - 2015 - Eke - Update on Prevalence of
      Periodontitis in Adults in the United States  NHANES 2009.pdf` and
      preserve its rotated footer definitions.
- [x] Parse `periodontis2.pdf` and preserve its terminal-fragment footer bands.
- [x] Confirm that continuation labels and ordinary numeric body rows are not
      retained as footers, and that visual-object DOI lines are retained as
      caption metadata rather than appended to footnote definitions.

Implemented DOI ownership rule:

- A standalone table or figure DOI is useful source metadata, not junk. Keep
  its original line in `paper_text_stream.json` and store its canonical DOI on
  the existing caption-bearing `PaperVisual` record. Do not create a separate
  DOI artifact or caption class.
- Add optional `doi` and `doi_source_line_id` fields to `PaperVisual`. Derive
  the clickable `https://doi.org/<doi>` URL in display code rather than storing
  a redundant URL field.
- Recognize only a complete standalone DOI whose terminal object suffix gives
  a table or figure number, such as `.t001` or `.g002`, and attach it only when
  that kind and number identify exactly one existing `PaperVisual`. Preserve
  unmatched DOI lines without guessing.
- Use the same DOI pattern in the existing external-footer stage to stop a
  definition block before the DOI line. This keeps the DOI available to the
  visual inventory while preventing it from becoming part of the preceding
  marker definition; no downstream cleanup path is added.
- Keep `paper_visual_inventory.json` available through the existing R paper
  output loader. The DOI then remains with the visual caption and can be
  rendered as a link without changing table values or footnote links.

The current corpus contains 15 directly usable visual-object DOI lines: seven
table DOIs and eight figure DOIs across the two PLOS papers. The remaining
standalone DOI lines are article, bibliography, data, or supplement identifiers
and must not be attached to a table or figure merely because they occur in the
same paper.

Step 5 checkpoint:

- `PaperVisual` now carries optional `doi` and `doi_source_line_id` fields. The
  shared standalone-object DOI pattern attaches all seven `.tNNN` values to
  existing table visuals. For a `.gNNN` value whose figure was absent from the
  markdown-derived inventory, the existing inventory stage accepts only the
  same-page caption sequence whose first line is the matching `Figure/Fig N`
  label and whose final line immediately precedes the DOI at the same text
  origin. This creates no new artifact or caption model.
- The two PLOS papers contain exactly 15 accepted values: seven table DOIs and
  eight figure DOIs. Their 15 positioned source lines remain byte-for-byte
  unchanged in `paper_text_stream.json`. Article, bibliography, data, and
  supplement DOIs remain unattached.
- In `An environment-wide association study (EWAS) on type 2 diabetes
  mellitus.pdf`, PDF page 6, printed Table 1, the DOI no longer extends the
  `{` definition: its text is exactly `denotes unweighted number.` The five
  existing star links and every corpus link outcome are unchanged.
- The eight caption-backed figure records resolve 22 previously unresolved
  prose figure references: 10 in `An environment-wide association study
  (EWAS) on type 2 diabetes mellitus.pdf` and 12 in `Association between
  anthropometric indices and chronic kidney disease- Insights from NHANES
  2009–2018.pdf`. These are direct consequences of adding the caption-bearing
  visual records, not new reference-resolution logic.
- The existing R paper-output loader carries `paper_visual_inventory.json`, and
  `show_paper_visuals()` derives `https://doi.org/<doi>` for display. The
  canonical stored value remains the DOI, not a redundant URL.

## 6. Run And Compare The Full Corpus

- [x] Run all 28 PDFs into a fresh ignored output directory with up to six
      parallel parser processes.
- [x] Confirm 91 physical extraction objects, 78 resolved tables, and 13
      accepted continuation integrations.
- [x] Confirm table statuses remain 16 `ok`, 62 `rescued`, and 0 `failed`.
- [x] Confirm extracted grids, table regions, marker occurrences, normalized
      tables, header artifacts, and resolved tables are unchanged.
- [x] Compare every changed footnote link, footer, definition, bibliography
      mention, and derived inspection artifact with the baseline.
- [x] Report every changed table using the exact PDF filename, PDF page number,
      and printed table number when available.

Step 6 checkpoint:

- `outputs/testpapers_batch_phase_k_step5_guarded_final_20260715` contains all
  28 PDFs.
  It retains 91 physical extraction objects, 78 resolved tables, 13 accepted
  continuation integrations, and statuses of 16 `ok`, 62 `rescued`, and 0
  `failed`.
- The 433 Phase I annotations still partition exactly into 400 anchors, 30
  mathematical or unit suppressions, and 3 subscript suppressions. The corpus
  remains at 105 definitions, 387 resolved links, 0 ambiguous links, and 13
  unresolved numeric bibliography candidates.
- Extraction, boundary, region, annotation, occupancy, leaf, header,
  normalization, continuation, body-candidate, value, table-definition,
  parsed-table, bibliography, and processing-status artifacts are all
  byte-for-byte unchanged from Step 4.
- `paper_footnotes.json` changes only for `An environment-wide association
  study (EWAS) on type 2 diabetes mellitus.pdf`, PDF page 6, printed Table 1,
  where the visual DOI is removed from the footer and its two definitions.
  `paper_references.json` and `paper_style_profile.json` change only in the two
  PLOS papers because their caption-backed figures now exist. The remaining
  `paper_visual_inventory.json` differences are the two new optional fields on
  existing records. `parse_quality_reports.json` differs only by run
  timestamps.

## 7. Regression And Closeout Gate

- [x] Confirm that no new focused regression test is proposed for this narrow
      ownership change; the retained real-paper evidence exercises all 15 DOI
      attachments and the affected external footer.
- [x] Record that pytest was not required or separately approved for this
      corpus-validated ownership change.
- [x] Run `ruff`, `py_compile`, and `git diff --check` on the changed source and
      documentation.
- [x] Update `parser_todo.md`, `paper_footnotes.md`,
      `paper_parse_walkthrough.md`, and the parent geometry checklist with the
      accepted implementation and corpus evidence.
- [x] Confirm that the parser diff adds no new model, artifact, helper layer,
      fallback, or parallel resolution path.

Closeout checkpoint: Python lint and compilation, R source parsing, and
`git diff --check` pass. No test was added and pytest was not run.

Phase K is complete: footer ownership is decided once, existing marker
occurrences link through canonical table and continuation identity, and
uncertain or undefined markers remain explicit rather than being guessed.
