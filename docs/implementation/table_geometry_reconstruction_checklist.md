# Table Geometry Reconstruction Checklist

This checklist tracks the planned geometry-first path from a detected table
region to a canonical `ExtractedTable`, marker-linked logical elements, and
footer resolution.

Mark a step complete only after its artifact can be inspected on real papers
and the 28-paper corpus shows changes only in the intended direction.

## A. Preserve Table-Local Evidence

- [x] Start from one `DetectedTableCandidate` with a page-space bounding box.
- [x] Collect the positioned lines, spans, words, characters, fonts, and
      individual horizontal-rule segments inside or immediately adjacent to
      that box.
- [x] Apply page-furniture and bibliography ownership masks before using this
      evidence.
- [x] Preserve stable source IDs and original page coordinates for every
      retained item.

Completion evidence:

- The table-local evidence comes from `PaperPositionedDocument` without a
  second PDF parse.
- Discontinuous same-y rule segments remain separate records.

Implemented as `ExtractedTable.metadata.table_positioned_evidence`, validated
through the typed `TablePositionedEvidence` model. It stores the candidate bbox,
line IDs, line/span references, and page-local word, character, rule-segment,
and stroked-rule-segment indices into `paper_positioned_document.json`. Text and
font payloads remain in that shared PyMuPDF artifact and are not duplicated.
The 2026-07-12 verification run parsed all 27 corpus papers and 82 tables with
zero invalid references, zero Phase A diagnostics, and no extraction changes
after excluding the new metadata field from comparison.

## B. Inventory Candidate Marker Glyphs

- [x] Record every table-local superscript, subscript, and attached symbol
      candidate as a distinct marker occurrence.
- [x] Preserve its visible glyph, normalized glyph key, source character/span
      IDs, bbox, font evidence, and provisional table association.
- [x] Do not decide yet whether the occurrence is a footnote, citation,
      mathematical notation, unit exponent, or extraction artifact.
- [x] Do not remove the glyph from source text.

Completion evidence:

- Header, body, row-label, and extracted footer-cell occurrences are represented
  by the same occurrence model. Caption markers remain outside this table-cell
  inventory unless later corpus evidence justifies a paper-level extension.
- Repeated uses of the same glyph have separate occurrence IDs.

Implemented by extending each `CellTextAnnotation` in
`cell_text_annotations.json`; no parallel marker artifact was added. Every
detected occurrence now has an `annotation_id`, canonical `glyph_key`, physical
`source_cell_id`, source character indices, source line/span references, bbox,
and typed font evidence. Phase A character references validate occurrence
ownership but do not filter or reinterpret detections. The 2026-07-12 corpus
run recorded 506 occurrences across 82 tables: 334 inline markers, 165
superscripts, and 7 subscripts. All source references resolved, no annotation
table had diagnostics, and existing extraction, annotation detection, and
footnote outputs were unchanged.

## C. Establish Provisional Header And Body Bands

Document-order prerequisite completed: `paper_text_stream.json` partitions page
lines by writing direction, orders rotated groups in an upright local frame,
preserves original source IDs/bboxes beside canonical bboxes, and stops context
adjacency at page/orientation-group boundaries. This corrects caption and prose-
mention search order without changing extracted grids. It does not yet complete
the table-local Phase C transform of characters, rules, caption bounds, and
candidate bounds required below.

Stage 1 checkpoint: `outputs/testpapers_batch_orientation_stream_stage1_20260712`
contains all 28 current corpus PDFs and 90 tables with no failed status. All 87
tables from the preceding 27-paper run are byte-identical; the package example
`inst/extdata/NutritionEx.pdf` adds three tables. Bibliography content is
unchanged. Mention classification changes are limited to correcting genuine
caption lines in `An environment-wide association study (EWAS) on type 2
diabetes mellitus.pdf`, `cobaltpaper.pdf`, and the rotated tables in `Journal of
Periodontology - 2015 - Eke - Update on Prevalence of Periodontitis in Adults in
the United States  NHANES 2009.pdf`.

Stage 2 caption prerequisite is complete. Caption labels and complete caption
regions now come only from the shared PyMuPDF text stream. They are bound in an
orientation-group canonical frame and retain source line IDs, raw line text,
page-space bboxes, canonical bboxes, and above/below geometry. Line-initial
table-label evidence is required; parenthetical continuation notices are not
promoted to captions. Adjacent caption lines stop at the first table rule,
including a partial rule, without changing that segment's identity or width.
The checkpoint
`outputs/testpapers_batch_caption_stage2_final_20260712` contains 28 PDFs and
90 tables with zero failed statuses. Eight continuation fragments have no local
caption, and 82 tables have geometry-bound caption regions. All table IDs,
dimensions, cell text, and cell coordinates are identical to Stage 1.

Stage 3 canonical-evidence prerequisite is complete. Every retained table-local
line, span, word, character, individual rule segment, and stroked rule segment
now has a positionally aligned canonical bbox or segment in
`table_positioned_evidence`. Candidate, evidence, caption, and structural-scope
bounds use the same orientation-group frame and retain page-space originals.
One affine transform records the mapping; upright tables use its identity form.
No rule is merged, promoted, or classified. The checkpoint
`outputs/testpapers_batch_canonical_evidence_stage3_final_20260712` contains all
28 PDFs and 90 tables with zero failed statuses, zero geometry diagnostics, 15
rotated transforms, and 75 identity transforms. Every source/canonical list
length agrees, all bound caption bboxes agree with Stage 2, extracted grids are
identical, and downstream semantic artifacts are unchanged.

- [x] Before proposing bands, normalize every rotated table's complete
      table-local positioned evidence into one upright coordinate frame.
      Transform lines, spans, words, characters, individual rule segments,
      candidate bounds, caption bounds, and nearby structural boundaries
      together, while preserving original page coordinates and transform
      provenance.
- [x] After orientation normalization, use exactly the same boundary and
      extraction route for rotated and ordinarily oriented tables; do not keep
      a separate rotated header/body decision path.
- [x] Use table bounds, positioned text lines, and horizontal-rule geometry to
      propose a header band and a body band.
- [x] Preserve alternative boundaries when the evidence is ambiguous.
- [x] Evaluate all plausible horizontal-rule boundaries; do not accept the
      first rule merely because value-like rows occur below it.
- [x] Preserve each horizontal-rule segment and its endpoints through every
      coordinate transform. Partial segments must never be merged, combined,
      or promoted to full-width rules; aggregate same-y coverage may be kept
      only as separate supporting evidence.
- [x] Allow a provisional boundary to differ between the row-label/stub band
      and value bands when one physical row contains both body-label content
      and leaf-header content.
- [x] Treat these as extraction evidence, not the final `TableRegion`.
- [x] Propose body/footer boundaries from ending-rule geometry, font change,
      continued body occupancy, and the next known caption or section
      boundary; preserve competing proposals instead of cutting at the first
      rule followed by non-value-like text.
- [x] Fail closed when a candidate has neither credible table rules nor a
      coherent positioned table grid; do not manufacture header/body bands
      from narrative text.
- [x] At the end of Phase C, produce a boundary-review list for every table
      with conflicting header/body proposals, weak or missing rule geometry,
      low-confidence region ownership, unassigned rows, or uncertain
      body/footer separation.
- [x] Review those tables by full paper title and page/table ID before starting
      body occupancy work; record whether each concern needs a geometry change
      or is an acceptable evidence limitation.

Completion evidence:

- The proposed body band is sufficient to select physical lines for occupancy
  analysis.
- No row is semantically classified at this stage.
- No unresolved header/body or body/footer concern is carried into Phase D
  without explicit review.

Phase C selection checkpoint:

- `table_boundary_proposals.json` is written for all tables and does not alter
  `TableRegion`, normalization, or semantic output.
- `outputs/testpapers_batch_phase_c_complete_20260712` contains all 28 PDFs and
  90 tables. No table has failed or blocked status.
- Raw extraction is unchanged from the prior checkpoint. The only byte-level
  difference in `extracted_tables.json` is the relative source path recorded
  for `inst/extdata/NutritionEx.pdf`.
- `TableRegion` now uses the same structural header detector as normalization:
  retained horizontal-rule separators first, then value-region evidence. It
  determines footer ownership independently and does not cut a sparse body row
  after an interior rule merely because that row is not a dense value matrix.
- The compact proposal no longer labels a selected edge unsupported merely
  because that edge is absent from its deliberately reduced alternatives.
  Fifty-four tables retain diagnostic alternatives: 53 have multiple
  header/body candidates and the text-only Mediterranean-diet Table 1 has no
  credible header/body proposal. These are retained evidence, not competing
  selected-region decisions.
- The reviewed boundaries now match the paper layouts for Asthma Table 1,
  GOLD Table 4, Sarcopenia Tables 2 and 3, cardiovascular Table 2, metabolic
  Table 2, and the relevant tables and continuations in `periodontis2.pdf`.
  The Mediterranean-diet Table 1 remains a non-target text-only table.
- Multicolumn header construction now preserves direct row-spanning leaves.
  In `periodontis2.pdf`, Table 4 has the group `Severity of periodontal probing
  depth (PPD)` over columns 1-10 and direct leaves `Mean PPD mm` and `SD` in
  columns 11-12. Table 3 uses the analogous CAL structure.
- A continuation with the same physical leaf headers and column count, but no
  repeated group row, may inherit the parent group tree after continuation
  identity is established. The uncaptioned Table 3 continuation in
  `periodontis2.pdf` is accepted by this gate.
- Footer proposals now require the final retained rule candidate, immediate
  following text in a font style different from the document body, canonical
  table overlap, and no intervening caption, next table, or section heading.
  When value-like rows appear to resume, the following text must form a
  multi-line smaller-font band after a real style transition. Twenty candidates
  survive across the corpus. They retain source line IDs, canonical bounds,
  and font styles but do not change `TableRegion` or interpret the text.
- `TableBoundaryProposal` now records `credible_rule_geometry` and
  `coherent_positioned_grid`. Proposals are built before `TableRegion`; when
  both fields are false, region ownership returns empty header/body/footer
  bands with `table_region_fail_closed_insufficient_geometry`. Normalization
  preserves that empty decision instead of rerunning its fallback detector.
- All 90 current physical extracts have both evidence fields true, so no corpus
  table triggered fail-closed. The guard changes no existing region,
  normalized, resolved, or semantic artifact. Phase C is complete.

## D. Build The Body Occupancy Artifact

- [x] Calculate occupancy only in the canonical upright table-local coordinate
      frame. Rotated tables must not use page-space x/y coordinates or a
      rotation-specific occupancy implementation.
- [x] Choose an x-bin width derived from local character dimensions rather
      than a paper-specific fixed coordinate.
- [x] Build a binary physical-line-by-x-bin matrix: a bin is occupied when an
      ordinary body character intersects it.
- [x] Exclude candidate marker glyphs from occupancy calculations while
      retaining them in the marker inventory.
- [x] Persist the raw matrix, per-bin line counts, and proportions. Do not
      smooth, fill gaps, merge bins, or infer column bands in this artifact.
- [x] Keep wrapped continuation lines as physical lines; do not join them
      before occupancy is calculated.

`body_occupancy.json` is diagnostic only. Interpreting occupied bands and
zero-occupancy valleys belongs to Phase E, after the raw evidence has been
inspected across the corpus.

Completion evidence:

- Long labels and values do not dominate merely because they contain more
  characters; support is counted by physical line.
- Equivalent upright and rotated table geometry produces equivalent occupancy
  profiles after orientation normalization.
- The artifact can be plotted or inspected without changing extraction.

Phase D checkpoint:

- `outputs/testpapers_batch_phase_d_complete_20260712` contains all 28 PDFs
  and 90 physical tables.
- All 90 records have valid line-by-bin matrices, count and proportion vectors,
  zero diagnostics, and zero unlinked marker occurrences. Forty-eight tables
  exclude at least one exactly linked marker occurrence.
- The body occupancy artifact is not consumed by extraction, normalization,
  header parsing, or semantic parsing.
- A repeated manuscript footer on `periodontis2.pdf` is now removed before
  occupancy. On page 10, four footer-created rows disappear. The resulting
  positioned grid exposes a separate 13-versus-14 column-boundary ambiguity
  caused by whitespace inside the row-label field; that issue is retained for
  occupancy-driven leaf-column work rather than repaired here.

## E. Produce Provisional Leaf-Column Candidates

- [x] Build exact horizontal unions from ordinary positioned body-character
      boxes so separator evidence is independent of x-bin starting offset.
- [x] Retain an exact zero-occupancy gap as a provisional separator only when
      it is at least two median observed space-glyph widths in the dominant
      table font and size.
- [x] Use separator midpoints to define contiguous provisional physical bands.
- [x] Keep the leftmost row-label/stub candidate explicit.
- [x] Attach individual unmerged horizontal-rule endpoints when they fall
      inside a zero-occupancy valley. Rule endpoints support a separator but do
      not create one by themselves.
- [x] Do not use token starts, header words, expected column counts, value
      syntax, or epidemiological vocabulary.
- [x] Fail closed when the body has no font-qualified zero-occupancy separator.

Completion evidence:

- Every candidate leaf has an x-extent, source evidence IDs, and support
  measurements.
- Candidate columns are based on table geometry rather than recognized header
  words or expected epidemiological statistics.

Phase E font-gap refinement checkpoint:

- `leaf_column_candidates.json` is diagnostic only and is not consumed by
  extraction, normalization, header parsing, or semantic parsing.
- `outputs/testpapers_batch_phase_f_font_space_gap_20260713` contains all 28
  PDFs and 90 tables with no command failure, occupancy diagnostic, or
  leaf-candidate concern. Eighty-nine tables obtain their observed space width
  directly from table evidence; one uses the same font and size elsewhere in
  the paper-level positioned document.
- Existing boundary evidence first defines the provisional body. A single
  supported body/footer model is accepted directly. Occupancy is consulted
  only when multiple canonical body intervals remain plausible, and the
  largest interval wins when competing models preserve the same number of
  qualified exact gaps.
- Eight tables use one supported boundary model and 18 tables compare multiple
  models. Only five region assignments differ from the Phase E diagnostic
  baseline: the four reviewed rotated tables now use body/footer row splits
  24/25, 10/11, 9/10, and 10/11, while the Mediterranean-diet text-only table
  no longer mistakes an internal rule for a footer boundary.
- All candidate bands are ordered and contiguous, every separator is an exact
  zero-occupancy interval at least two observed table-font spaces wide, and all
  attached rule endpoints lie inside their separator.
- Sixty-eight candidate counts agree with the current extracted grid. The other
  22 are retained disagreements, not parser changes. In particular,
  `periodontis2.pdf` page 10 has 13 geometry candidates rather than the
  current extractor's 14 columns because the occupancy valley keeps the full
  multiword row label in one stub band.
- The existing test suite passes: 138 tests, with no new tests added.

Six tables gain one geometrically supported band. This separates Q1 from Q2 in
`NutritionEx.pdf`, PDF page 5, Table 1; All from Q1 in
`Role of Estimated Glucose Disposal Rate in Staging and Death Risk of Cardiovascular-Kidney-Metabolic Syndrome- Insights from NHANES 1999-2018.pdf`,
PDF page 4, Table 1; Hispanic from White in
`Helicobacter pylori infection in the United States beyond NHANES- a scoping review of seroprevalence estimates by racial and ethnic groups.pdf`,
PDF page 7, Table 1; the stub from Total in `Sarcopenia.pdf`, PDF page 5,
Table 1; the stub from the model result in
`Association between metabolic score for insulin resistance (METS-IR) and hypertension- a cross-sectional study based on NHANES 2007–2018.pdf`,
PDF page 7, Table 4; and the missing fifth band in
`Systemic inflammation markers and the prevalence of hypertension- A NHANES cross-sectional study.pdf`,
PDF page 6, Table 1.

Phase F review note:

- The Q1/Q2 failure was caused by the diagnostic bin origin hiding a real
  character-box gap, not by missing token-start evidence. Exact font-qualified
  gaps correct that earlier geometry defect first. Token-start evaluation
  remains pending only for unresolved bands that have no qualifying gap.

## F. Decide Whether Token-Start Evidence Adds Value

- [x] Inspect the ambiguous or conflicting candidates produced by Phases E
      and G, including cross-band header words, header bands without text, and
      bands carrying multiple positioned header fragments.
- [x] Identify tables where font-qualified exact gaps cannot distinguish
      tightly packed adjacent columns or split components that may belong to
      one leaf.
- [x] For only those cases, calculate ordinary token-left-edge distributions
      by physical body line.
- [x] Compare occupancy-only and occupancy-plus-token-start candidates across
      the corpus.
- [x] Retain token-start evidence only if it adds stable column information
      without splitting components such as `n (%)`, `mean (SD)`, or estimates
      and confidence intervals.
- [x] Otherwise remove it from the planned extraction path.

Decision rule:

- Token starts may support an existing candidate, reject an occupancy-only
  split, or reveal a column hidden by weak whitespace evidence. They must not
  independently define the final grid.
- Implemented narrow use: an explicit next-page continuation may reuse its
  already-finalized parent's leaf bands only when provisional leaf headers and
  column counts match, value anchors align within the observed character scale,
  and every inherited value band has token support on every body line.

Phase F checkpoint:

- `outputs/testpapers_batch_phase_f_token_start_20260713` covers all 28 PDFs
  and 90 tables with no command failure. Thirty-two tables have actionable
  refinement evidence and are evaluated; the other 58 retain explicit
  unevaluated records. All evaluated tables have complete physical-line token
  observations and no diagnostic.
- The 32-table review set is the union of 22 candidate-versus-current-grid
  count disagreements, 11 tables containing 20 cross-band header runs, four
  tables containing 13 non-stub bands without header text, and one header
  diagnostic. Categories overlap. Thirty-one blank stub labels are recorded
  separately; 21 occur without another concern and do not trigger token-start
  measurement.
- At a descriptive 50% physical-line support threshold, raw token-start bins
  show multiple repeated starts in the broad stub band of seven tables.
  Visual review confirms that each contains row labels plus the first value
  column in one occupancy band. The same review finds repeated starts inside
  legitimate value bands in 14 tables, commonly from estimates and confidence
  intervals. The threshold is review analysis, not parser logic.
- Token starts therefore add useful supporting evidence for a missing
  stub/value boundary, but are not specific enough to define separators.
  `token_start_evidence.json` retains exact source-referenced starts and raw
  counts without clustering, smoothing, splitting bands, or changing any
  accepted parser artifact.
- Relative to the preceding full run, all existing artifacts are byte-identical
  except timestamped quality reports. `token_start_evidence.json` is the only
  new parser output.

## G. Build `HeaderStructureCandidate`

- [x] Assign positioned header spans to candidate leaf bands.
- [x] Use individual partial horizontal rules to propose multicolumn groups
      over contiguous leaves.
- [x] Attach vertically adjacent wrapped header fragments to the same candidate
      node when geometry supports it.
- [x] Associate marker occurrence IDs with candidate header leaves and groups.
- [x] Preserve alternative attachments and unresolved fragments.

Completion evidence:

- The candidate is representable as LaTeX-like leaves and `multicolumn`
  groups.
- Same-y partial rule segments have not been merged into one full-width rule.

Phase G checkpoint:

- `header_structure_candidates.json` is diagnostic only. It does not alter
  `ExtractedTable`, `TableRegion`, `NormalizedTable`, `ColumnHeaderSchema`, or
  any semantic output.
- Missing or disagreeing header candidates do not gate canonical extraction.
  Header/leaf-count disagreement remains a candidate diagnostic for review.
- `outputs/testpapers_batch_phase_f_font_space_gap_20260713` contains all 28 PDFs
  and 90 tables with no command failure. Eighty-nine tables have usable header
  rows; their 627 preliminary leaves correspond one-to-one with their 627
  occupancy bands. The non-target text table with no header rows retains
  `header_rows_missing` and does not manufacture leaves for its three bands.
- The artifact contains 109 multicolumn groups. Every leaf is now created from
  an occupancy band before header text is attached. Intact positioned runs
  attach by greatest horizontal overlap, and multiple runs assigned to one
  band are assembled in visual order. `Sarcopenia.pdf`, PDF page 7, Table 2
  and PDF page 8, Table 3 now each have seven leaves: one stub plus
  `OR 95% CI` and `p-value` under each of three two-leaf Model groups.
- Seventy-four header marker occurrences are linked by source-line and
  canonical marker geometry: 66 to leaves and eight to groups. No current
  attachment is ambiguous or unresolved; the schema preserves those states
  for future papers instead of falling back to nearest-leaf assignment.
- Twenty intact header runs have words crossing occupancy-band boundaries;
  these retain source evidence and explicit diagnostics rather than being
  split. Thirteen non-stub bands lack attached header text, and 31 blank stub
  labels remain explicit. These are Phase F review signals, not grid changes.
- The refined exact gaps change only `body_occupancy.json`,
  `leaf_column_candidates.json`, `header_structure_candidates.json`, and
  timestamped quality reports. Two unchanged competing body-model selections
  also record the new separator count in region diagnostics propagated through
  normalized and resolved provenance; selected rows and semantic data do not
  change.
- Phase F subsequently adds exact token-start evidence for flagged tables.
  Neither Phase G nor Phase F selects a canonical physical grid.
- Complete flat-header preservation is checkpointed in
  `outputs/testpapers_batch_flat_header_cells_20260714`. All 28 PDFs completed
  and all 92 physical extracts retain accepted, byte-identical canonical grids.
  For `Systemic inflammation markers and the prevalence of hypertension- A
  NHANES cross-sectional study.pdf`, printed Table 1 on PDF page 5 and `Table 1
  (continued)` on PDF page 6 now each expose the five canonical cells as five
  exact header leaves. The page-6 candidate retains
  `local_leaf_axis_disagrees_with_canonical_grid:local=3:canonical=5`; the
  resolved table remains 61 x 5. Relative to the preceding checkpoint, only
  these two header-candidate records and their token-start diagnostics change;
  all other JSON is byte-identical after quality-report timestamps are removed.
  Corpus cross-band header-run concerns fall from 25 to 23.
- Incomplete and multilevel header reconstruction is checkpointed in
  `outputs/testpapers_batch_header_structure_geometry_20260714`. The finalized
  candidate uses observed body-cell anchor centers and unambiguous lowest-band
  header anchors to decide whether a positioned run belongs to one leaf or
  covers multiple leaves. Individual partial rules can establish exact
  contiguous group children; same-row peers partition those children only when
  the row has local rule support. Repeated peer rows can be aligned as equal
  contiguous blocks only when at least three peers exist, at least two are
  already groups, every peer has a local rule fragment, and the leaf count
  divides evenly. This restores clipped right-edge groups without a generic
  text-gap rule.
- A mixed physical header/body row contributes only value-side header evidence,
  and only when the rule immediately above it covers at least two observed
  value anchors while excluding an observed stub anchor and a lower
  header/body proposal supports the same bands. The selected `TableRegion` and
  its header/body row indices are not changed.
- Cross-band concerns are now emitted after leaf/group assignment. The 28-PDF,
  92-table corpus falls from 23 concerns to two, both attached to the two
  caption-owned false tables on `cobaltpaper.pdf`, PDF page 3. These require
  later table-region ownership work, not another header run rule.
- All canonical `ExtractedTable` content is identical after removing the two
  token-evaluation metadata fields. `TableRegion`, body occupancy, leaf-column
  candidates, accepted `ColumnHeaderSchema`, table definitions, parsed tables,
  parsed cell values, and continuation groups are identical. Eleven tables
  lose only the resolved `cross_band_header_run` token trigger; token-start
  logic is retained unchanged, and only `periodontis2.pdf`, PDF page 11,
  changes from evaluated to unevaluated.
- `periodontis2.pdf`, PDF page 13, printed Table 2 (continued), still preserves
  blank local child labels beneath its reconstructed parent groups. Supplying
  those labels is a later continuation-inheritance task, not local geometry or
  extraction rewriting.

## H. Finalize Canonical Extraction

- [x] Keep the pre-selection positioned grid in the internal typed
      `ProvisionalExtractedTable`; only the selected grid is an
      `ExtractedTable`.
- [x] Keep canonical physical-grid materialization in the extraction package,
      not in a downstream normalization or repair module.
- [x] Keep preliminary header structure out of canonical-grid acceptance;
      preserve disagreement only in the post-extraction header artifact.
- [x] Preserve an equal-count positioned grid only when repeated header cells
      are not wholly contained by different occupancy leaves in the same
      physical row.
- [x] Default a local positioned/occupancy count disagreement to occupancy
      materialization.
- [x] Preserve a disagreeing strongly ruled positioned axis only when repeated
      value anchors, distinct physical header-line starts, complete label-column
      support, and repeated token support in every value column corroborate the
      already-established axis.
- [x] Confirm parent leaf bands for an explicit continuation only from matching
      provisional leaf headers, aligned value anchors, and complete per-line
      token support; do not add a general token-derived separator path.
- [x] Select a physical grid only when leaf and row geometry are adequate.
- [x] Emit the canonical `ExtractedTable` with raw text and source-faithful
      coordinates.
- [x] Keep wrapped physical lines and split values exactly as printed.
- [x] Persist the geometry evidence and diagnostics that selected the grid.
- [x] Do not emit a candidate when positioned evidence cannot build
      a credible canonical table.

Completion evidence:

- Body occupancy has influenced extraction before `ExtractedTable` is
  finalized, not through a later repair pass.
- Visual comparison confirms that extracted row and column coordinates match
  the PDF.

Phase H checkpoint:

- Canonical extraction uses only the shared PyMuPDF positioned evidence.
  Upright candidates come from horizontally compatible caption/rule regions,
  enclosed connected rule grids, or prior-page value-column geometry.
  Rotated orientation groups are transformed before the same positioned grid
  builder runs.
- Connected-grid recovery requires an enclosed source-rule component without
  merging or reclassifying individual partial rules. Cross-page recovery
  requires numeric occupancy in every inherited value band and a covering
  ending rule.
- `outputs/testpapers_batch_extraction_geometry_complete_20260713` contains all
  28 PDFs and 91 physical tables with no command failure, page-1 candidate, or
  zero-shape grid. The only extraction differences from the preceding
  87-table run are Table 3 on PDF page 7 of `Association between metabolic
  score for insulin resistance (METS-IR) and hypertension- a cross-sectional
  study based on NHANES 2007–2018.pdf`; the fully ruled unnumbered table on PDF
  pages 4 and 5 of `Asthma prevalence among United States population insights
  from NHANES data analysis.pdf`; and the Table 1 continuation on PDF page 3 of
  `Science-Advanaced-Planetary Health Diet and risk of mortality and chronic
  diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf`.
- The recovered PDF page 3 fragment of Table 1 in `Science-Advanaced-Planetary
  Health Diet and risk of mortality and chronic diseases- Results from US
  NHANES, UK Biobank, and a meta-analysis.pdf` resolves with PDF page 2 as one
  68-row, 9-column logical table.
- Strict explicit-continuation parent-band confirmation is checkpointed in
  `outputs/testpapers_batch_continuation_parent_bands_final_20260713`. All 28
  PDFs completed and all 92 physical tables were accepted. The confirmation
  fired exactly once: Table 1 on PDF page 5 of `Systemic inflammation markers
  and the prevalence of hypertension- A NHANES cross-sectional study.pdf`
  supplied five parent leaf bands to the matching `Table 1 (continued)` on PDF
  page 6. The page-6 physical extract changed from 14 x 3 to 14 x 5 and now
  resolves with page 5 as one 61-row, 5-column logical table. No other
  `ExtractedTable` changed; outside this source PDF, persisted JSON is unchanged
  after removing parse timestamps. The still-disagreeing local three-band body
  occupancy and header candidate remain visible diagnostics for the next
  header-geometry task.
- Final canonical-axis validation is checkpointed in
  `outputs/testpapers_batch_canonical_axis_validation_final_20260714`. All 28
  PDFs completed; all 92 tables have non-empty accepted grids. Fifty-six tables
  preserve positioned cells after count and cell-bbox validation, 29 use local
  occupancy materialization, and seven preserve a disagreeing positioned axis
  through the strict header-line-plus-token confirmation. Visual review covers
  all seven. The repeated header-cell conflict rejects only printed Table 2 on
  PDF page 4 and printed Table 4 on PDF page 6 of `GOLD BioAge and depression-
  Associations with mortality among depressed NHANES participants
  (2005–2018).pdf`; both return to their clean committed cells. All five tables
  in `cobaltpaper.pdf`, PDF pages 3-5, exactly match commit `6db4bb1` in shape,
  text, and bboxes. Among 83 shared table IDs, exact physical matches to that
  commit rise from 14 to 46, and no prior exact match regresses. Printed Table 1
  on PDF pages 5-6 of `Systemic inflammation markers and the prevalence of
  hypertension- A NHANES cross-sectional study.pdf` remains a compatible 48 x
  5 plus 14 x 5 continuation and resolves to 61 x 5.
- Continuation-child inheritance is recovered in
  `outputs/testpapers_batch_header_inheritance_recovered_20260714`. Printed
  Table 2 on PDF page 13 of `periodontis2.pdf` inherits only columns 3–10 from
  PDF page 12 after complete occupancy-leaf alignment, compatible local labels,
  and matching group spans. Local blanks and source provenance remain in the
  candidate. Its 22 x 11 grid is unchanged and the pair resolves as one 38 x 11
  table. No other table inherits a label, and all earlier physical artifacts
  match the canonical-axis baseline.
- The final sparse-stub occupancy refinement is checkpointed in
  `outputs/testpapers_batch_gated_sparse_body_occupancy_first_edge_20260715`.
  It runs only when ordinary exact-gap occupancy is exactly one separator short.
  A sparse row abstains only when its continuous label reaches within two local
  space widths of the earliest structurally separated first-data occupancy;
  characters at or to the right of that edge, including p-values, remain
  evidence. All 28 PDFs and 92 tables complete. The seven formerly
  token-confirmed tables retain identical cells and now use occupancy-confirmed
  positioned geometry. Printed Table 3 (continued) on PDF page 12 of
  `Association between anthropometric indices and chronic kidney disease-
  Insights from NHANES 2009–2018.pdf` changes from 8 x 6 to the correct 8 x 7,
  matching its stub plus three OR/p-value pairs. All other physical grids are
  unchanged, including the 11 x 5 uncaptioned table on PDF page 5 of `Asthma
  prevalence among United States population insights from NHANES data
  analysis.pdf`, printed Table 3 on PDF page 8 of `periodontitis.pdf`, and the
  inherited 28 x 11 plus 22 x 11 `periodontis2.pdf` Table 2 pair.

## I. Attach Markers To Stable Elements

- [ ] Link marker occurrences to physical cells and header candidate nodes.
- [ ] After logical body candidates exist, link occurrences to body values and
      row-label elements as well.
- [ ] Expose unchanged `raw_text`, marker-free `base_text`, and associated
      `marker_ids` on logical candidates.
- [ ] Remove a glyph from `base_text` only when exact character/span geometry
      supports the association.
- [ ] Keep uncertain glyphs in `base_text` with diagnostics.

Completion evidence:

- Marker handling does not mutate `ExtractedTable.text`.
- Header and body interpretation can use marker-free text without losing the
  visible marker or its provenance.

## J. Build Final Table Regions And Logical Candidates

Detailed cutover checklist:
`docs/implementation/header_geometry_to_column_schema_checklist.md`.

- [ ] Build `TableRegion` using the selected grid and
      `HeaderStructureCandidate` evidence.
- [ ] Build `NormalizedTable` without changing physical geometry.
- [ ] Build `ColumnHeaderSchema` by validating, refining, or rejecting the
      preliminary header candidate.
- [ ] Build `BodyElementCandidate` and `BodyRowLabelCandidate` after the leaf
      grid is settled.
- [ ] Estimate left, right, center, or decimal alignment only after occupancy
      and leaf candidates exist; treat alignment as supporting evidence.

Completion evidence:

- `ColumnHeaderSchema` does not independently reconstruct a competing header.
- Wrapped logical elements retain all source cells and physical-line IDs.

## K. Extract And Resolve Footer Definitions

- [ ] Identify footer regions only after table/footer ownership is established.
- [ ] Create definition-marker records separately from table-element marker
      occurrences.
- [ ] Resolve occurrences to definitions by glyph key, table/visual identity,
      continuation scope, and footer geometry.
- [ ] Preserve explicit states for resolved, ambiguous, unresolved, possible
      citation, and non-footnote notation.
- [ ] Perform continuation-aware resolution only after continuation grouping.

Completion evidence:

- Resolution never invents conventional p-value meanings without an explicit
  definition.
- Numeric citation candidates remain available for bibliography resolution.

## L. Corpus Verification

- [x] Inspect focused examples for clean ruled tables, tightly packed columns,
      sparse p-value columns, wrapped values, wrapped headers, rotated tables,
      and continuation fragments.
- [x] Run all 28 PDFs with bounded parallel workers.
- [x] Compare extracted shapes, header structures, marker inventories, and
      resolved tables against the retained baseline.
- [x] Report every changed table by full paper name and table/page identifier.
- [x] Run the existing pytest suite; do not add tests without explicit
      approval.
- [x] Remove superseded generated output directories after the accepted run.
