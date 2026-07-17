# Parser ToDo

This is the persistent implementation ToDo list for parser work. Agents should check it before changing extraction, normalization, row/column semantics, table routing, value parsing, diagnostics, or R inspection helpers. Update it when a task is completed, reprioritized, split, or superseded.

Keep detailed implementation notes and epidemiology-table reasoning here or in linked implementation documents. Keep high-level design docs focused on stable pipeline shape, schemas, persisted artifact contracts, and durable architecture decisions.

## Current Priorities

- [ ] Complete the canonical positioned-evidence unification in
  `docs/implementation/canonical_orientation_unification_checklist.md` before
  making another footer-specific correction. The required path is
  `PaperPositionedDocument -> TablePositionedEvidence -> ExtractedTable ->
  TableBoundaryProposal -> TableRegion/footer ownership`, with one canonical
  implementation after the source orientation transform. The PDF-page-18
  failure in `periodontis2.pdf`, printed Table 5, is the first guidepost: its
  descriptive title currently doubles the candidate width, its real closing
  rule is missing from `ExtractedTable.metadata.horizontal_rules` despite
  remaining in canonical positioned evidence, and downstream consumers use
  different rule representations. Keep the current parser code frozen until
  the checklist's complete producer/consumer inventory and exact Step 1 patch
  have been reviewed and explicitly approved.
- [ ] Complete and validate the unified bottom-of-table footer detector tracked
  in `docs/implementation/footer_detection_unification_checklist.md`. Ownership
  is now implemented once in `build_table_region()` with mandatory typography,
  positioned prose continuity, and preceding data support. The DOI-barrier
  28-PDF comparison is complete; the remaining broader footer review must also
  compare accepted internal footer rows with the settled body occupancy vector
  and header-aligned bands, initially as a non-operative audit for body rows
  accidentally assigned to the footer.
  Visual-object DOI lines are now owned once from the shared positioned text
  stream and act as a hard terminal barrier before footer text or rule events
  are offered to that owner. The 28-PDF comparison in
  `outputs/testpapers_batch_doi_barrier_20260716` changed physical table shapes
  and region ownership only in
  `Association between anthropometric indices and chronic kidney disease- Insights from NHANES 2009–2018.pdf`:
  its five previously empty candidates on PDF pages 8, 10, 12, and 13 retained
  their data grids and three-row footer bands. All table and figure DOI values
  and source-line IDs remained unchanged in `paper_visual_inventory.json`.
  Subsequent approved cleanup removed the external first-line distance gate and
  table-left alignment gates, stops external collection at font/type changes,
  rejects positioned headings and same-block consecutive body continuations,
  and makes boundary proposals use `canonical_candidate_bbox` before broader
  evidence scope. The 28-PDF run
  `outputs/testpapers_batch_footer_current2_20260716` is the comparison baseline;
  remaining footer failures are recorded in
  `tmp/current_footer_detection4.md`. No new numeric layout tolerance may be
  implemented without the `APPROVE_LAYOUT_TOLERANCE` gate in `AGENTS.md`.
  The same-block typography correction is validated in
  `outputs/testpapers_batch_footer_same_block_20260716`: PDF pages 6–9,
  printed Tables 2 continued and 3–5 of
  `mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older
  Adults- NHANES 2007–2017.pdf` now retain their complete footer blocks across
  the source PDF's 8.0/7.9-point variation. All 28 PDFs completed; table shapes
  are unchanged, and no other table changed footer ownership. This uses source
  block and font continuity and adds no numeric layout tolerance.
  The existing candidate image bbox is now also a hard terminal barrier when
  its top edge is exactly below the canonical table bbox. The 28-PDF checkpoint
  is `outputs/testpapers_batch_visual_object_footer_barrier_final_20260716`.
  All commands completed with 91 unchanged physical grids and 77 resolved
  tables. Of the six candidates carrying
  `candidate_visual_object_barrier_bbox`, five retain byte-identical structural
  artifacts apart from parse-quality timestamps. In
  `Systemic inflammation markers and the prevalence of hypertension- A NHANES cross-sectional study.pdf`,
  PDF page 6, printed Table 1 continued, the y=337.890 image barrier limits the
  external footer to source lines 72-75 at y=266.881-311.592. The 14 x 5 grid,
  body rows, and y=263.197 closing boundary remain unchanged; one footer and
  the explicit `a`/`b` definitions are restored, resolving all 12 letter-marker
  links.
- [ ] Review or explicitly accept the deferred corpus gaps and uncertainties in
  `docs/implementation/corpus_artifact_uncertainties_20260715.md`. This records
  unsupported rotated marker geometry, unresolved header/visual identities,
  incomplete visual-reference coverage, unresolved bibliography-like markers,
  and downstream semantic uncertainty without treating every diagnostic as a
  parser defect.
- [ ] Choose any future work from the separate prioritized improvement list in
  `docs/implementation/post_geometry_improvement_backlog_20260715.md`. Each
  item requires a fresh read-only audit and specific parser-logic approval
  before implementation.

Current corpus-driven hardening guide:
`docs/implementation/real_paper_testing_guide.md`. Use it for the ordered
real-paper review loop across extraction, normalization, continuation handling,
table semantics, footnote/reference artifacts, and mixed-family routing. The
current retained reference run is
`outputs/testpapers_batch_phase_k_step5_guarded_final_20260715`;
its comparison baseline is
`outputs/testpapers_batch_phase_k_step4_final_20260715`.

Fallback/removal inventory:
`docs/implementation/fallback_inventory.md`. Do not add new fallback tools or
downstream repair layers to compensate for weak extraction. Prefer fixing
positioned extraction, caption/table-region ownership, page-furniture filtering,
and explicit schema artifacts; fail closed with diagnostics when geometry is
insufficient.

Immediate prerequisite before Phase J:
`docs/implementation/pre_phase_j_extraction_integrity_checklist.md`. The
duplicate-extraction correction and full Step 2 re-baseline are complete at
`outputs/testpapers_batch_pre_phase_j_step2_final_20260715`. The 28 PDFs now
produce 91 extraction objects representing 91 unique physical grids and 82
resolved tables after nine accepted two-fragment continuation merges. All 91
retained grids match the Phase I baseline exactly; only the misbound duplicate
on PDF page 5 of `Asthma prevalence among United States population insights
from NHANES data analysis.pdf` is removed. Its real Table 1 pages 4–5 now
resolve together, and printed Tables 2–3 remain separate. The Step 3 planning
reset is complete: the refreshed 91-grid audit and focused implementation
contract are in
`docs/implementation/header_geometry_to_column_schema_checklist.md`. Phase J
Step 1 is complete at
`outputs/testpapers_batch_phase_j_step1_final_20260715`. The one general
text-table rule uses a complete first row, adjacent full-width rules,
character-weighted bold contrast, and full-column coverage. It changes only
PDF page 3, printed Table 1 of `mdpi-The Relationship Between a Mediterranean
Diet and Frailty in Older Adults- NHANES 2007–2017.pdf`: row 0 becomes the
header, candidate completeness rises from 90/91 to 91/91, and all physical
grids, occupancy separators, canonical leaf bounds, marker occurrences,
continuations, resolved counts, and status categories remain unchanged. Phase
J Step 2 is complete at
`outputs/testpapers_batch_phase_j_step2_final_closed_20260715`. One compact
rule-banded path now builds all 663 candidate leaves and 115 contiguous groups
from the final region, canonical leaf bands, positioned text, and rules. It
removes the former flat-grid override, body-row promotion, body-anchor repair,
cross-band helper layer, and separate grouping branches. All 91 candidates are
complete; all 56 header marker links and eight inherited continuation labels
retain their logical targets and provenance; no evidence comes from a body
row. The 91 physical grids, regions, occupancy, leaf geometry, marker
occurrences, 82 resolved tables, nine continuation integrations, and 17 `ok` /
65 `rescued` statuses remain exact. Phase J Step 3 is next: confirm
`NormalizedTable` preserves the settled grid and region without rerunning
header inference or changing source identity. Phase J Step 3 is complete:
normalization now requires the matching final `TableRegion`, copies its row
ownership directly, preserves the complete physical column axis, and no longer
contains either the legacy header/body detector fallback or sparse edge-column
removal. Phase J Step 4 is complete at
`outputs/testpapers_batch_phase_j_step4_final_20260715`: all 91 schemas are
exact projections of 663 candidate leaves, 115 groups, and 376 relationships,
with stable marker-node and evidence IDs. Direct projection corrects three
explicit continuations that the former independent schema builder alone had
rejected, yielding the approved current baseline of 79 resolved tables and 12
integrations from the unchanged 91 grids. Phase J Step 5 is next: delete the
now-unreachable independent schema reconstruction code and remove the resolved
schema rebuild call. Phase J Step 5 is complete at
`outputs/testpapers_batch_phase_j_step5_final_20260715`. The schema module is
reduced from 2,248 to 401 lines, with the independent builder, repair/grouping
helpers, continuation override, and resolved rebuild fallback deleted. The 28
PDFs reproduce Step 4 except for report timestamps: 79 resolved tables from 91
grids, with 13 recognized continuation candidates, 12 accepted integrations,
and one correctly rejected candidate (`periodontis2.pdf`, PDF pages 10–11,
printed Table 1) whose projected column paths disagree. Phase J Step 6 is next:
confirm body candidates consume the projected schemas without changing source
cells, physical rows, marker provenance, or semantics. Phase J Step 6 is
complete at `outputs/testpapers_batch_phase_j_step6_final_20260715`. All 9,523
body-value candidates and 56 logical row-label candidates join the expected
projected leaf, and all 7,873 final values carry the matching projected header
path. Exact physical source text now comes directly from `ExtractedTable` in
both existing builders; the former marker-only CLI raw-text rewrite is gone.
This corrects 1,306 source-cell provenance strings without changing candidate
identity, parser-facing text, parsed components, semantic values, marker
attachments, geometry, schemas, resolved tables, or statuses. Phase J Step 7
is complete using the existing fresh Step 6 corpus. All six focused examples
pass, all 91 physical grids remain exact, the one approved MDPI row-ownership
change is isolated, and all 663 leaves, 115 groups, and 376 relationships are
exact candidate projections. The 87 changed candidates are exactly the
general Step 2 rebuild set; all 91 schema changes are the intended direct
projections. Continuation decisions differ from Step 3 only for the three
approved integrations. No test was added and pytest was not run. Phase J Step
8 implementation audit is complete: parser code is net 1,382 lines smaller,
no new class, artifact, helper, or fallback exists, documentation is aligned,
and static checks pass. With explicit approval, the 13 schema-builder tests for
the deleted independent reconstruction path and the 22 direct-normalization
tests that omitted the now-required `TableRegion` were removed. Active schema
validation, header detection, and row-signature coverage remains. No new test
was added and pytest was not run. Phase J is ready to stage.
The post-Phase J `periodontis2.pdf` continuation review is complete. On PDF
page 11, printed Table 1, the PDF content stream places the right edge of the
repeated header and value column outside the declared page box. The shared
positioned-document pass now retains that direct source text instead of
clipping it. Ordinary extraction therefore recovers the missing header row,
the complete final leaf, and complete values; page 10 and page 11 project to
the same 13 column paths and the unchanged continuation gate integrates them
as one 43 x 13 table. The full 28-PDF checkpoint is
`outputs/testpapers_batch_offpage_text_recovery_20260715`: 91 extraction
objects, 78 resolved tables after 13 accepted continuation integrations, 16
`ok`, 62 `rescued`, and no failures. Structural outputs outside
`periodontis2.pdf` are unchanged. A focused positioned-document regression
protects this source recovery; no candidate leaf inheritance, schema repair,
or resolver workaround was added.

Phase K Step 1 and its approved continuation-cue ownership follow-up are
complete at
`outputs/testpapers_batch_phase_k_continuation_cue_final_20260715`. The footnote stage now
consumes extracted footer rows only from final
`TableRegion.footer_note_rows` and external footer lines only from the final
rule's `TableBoundaryProposal.following_text_line_ids`. The late last-value/rule
fallback, `_last_value_matrix_row_idx()`, and arbitrary styled-text scan below
the table bbox are removed. Across all 28 PDFs, the parser preserves 91
physical tables, 78 resolved tables, 13 accepted continuation integrations,
16 `ok` / 62 `rescued` statuses, and all 400 link outcomes. Footer records fall
from 134 to 65 owned records. The MDPI footer paragraphs on PDF pages 6–9 remain
continuous across same-font 8.0/7.9-point jitter, replacing 13 truncated link
meanings with their complete explicit definitions. On PDF page 4, printed Table
1 of `Asthma prevalence among United States population insights from NHANES
data analysis.pdf`, the standalone final `Continued` cue is removed before
physical table ownership because it has no data-column value; its text and
former row position remain in `metadata.trailing_non_table_rows`. The page-5
`Missing values` row keeps `9303 (14.5)` and remains the third level of `Ever
told you had chronic bronchitis`. That Step 1 checkpoint did not change anchor
identity or continuation-scoping logic.

Phase K Step 2 is complete at
`outputs/testpapers_batch_phase_k_step2_final_20260715`. Each promoted
table-cell footnote anchor now reuses its existing
`CellTextAnnotation.annotation_id`; the anchor notes retain the annotation type
while full superscript/subscript/inline geometry remains in
`cell_text_annotations.json`. A missing annotation ID fails closed with a
diagnostic instead of creating a second positional identity. The existing
smaller-raised definition-marker evidence now accepts a marker at the beginning
of its own physical line without requiring punctuation on the preceding line.
This resolves only the explicit `a` definition in `hypertension.pdf`, PDF page
6, printed Table 2: the corpus moves from 346 resolved / 54 unresolved links to
347 / 53. All 91 physical extraction objects, 78 resolved tables, 13 accepted
continuation integrations, and 16 `ok` / 62 `rescued` statuses are unchanged;
the extraction-through-parsed-table artifacts are byte-identical.

Phase K Step 3 is complete at
`outputs/testpapers_batch_phase_k_step3_final_20260715`. The existing footnote
anchor, footer, definition, and link functions now consume final
`ResolvedTableSet` membership; `paper_footnotes.py` no longer depends on the
older Table 1 continuation review artifact. Cross-fragment candidates qualify
at the existing `same_visual` rank only when both source table IDs belong to
the same accepted integrated resolved table. Rejected continuations fail
closed. All 94 current cross-fragment links remain unchanged, including 3 links
across PDF pages 2–3, printed Table 1 of `Science-Advanaced-Planetary Health
Diet and risk of mortality and chronic diseases- Results from US NHANES, UK
Biobank, and a meta-analysis.pdf` and 77 across PDF pages 7–8, printed Table 1
and PDF pages 11–12, printed Table 3 of `Association between anthropometric
indices and chronic kidney disease- Insights from NHANES 2009–2018.pdf`. The
28 PDFs retain 91 physical tables, 78 resolved tables, 13 accepted continuation
integrations, 16 `ok` / 62 `rescued` statuses, and 347 resolved / 53 unresolved
links. The only non-timestamp artifact difference assigns accepted printed
Table 2–4 visual IDs to terminal footers and definitions on PDF pages 13, 15,
and 17 of `periodontis2.pdf`; no link outcome changes.

Phase K Step 4 is complete at
`outputs/testpapers_batch_phase_k_step4_final_20260715`. The existing caption
definition branch now accepts only a trailing explicit symbol block after
completed caption prose and reuses the local symbol-block parser. It recognizes
attached markers such as `*p < 0.05` while removing the former broad
letter/number caption regex. In `Asthma prevalence among United States
population insights from NHANES data analysis.pdf`, PDF page 6, printed Table
3, the caption supplies three explicit p-value definitions and all 40 star
occurrences resolve to them. Five unlinked false caption definitions are
removed from `gallstones.pdf`, PDF page 7, printed Table 2; the asthma paper,
PDF page 5, printed Table 1; and `Journal of Periodontology - 2015 - Eke -
Update on Prevalence of Periodontitis in Adults in the United States  NHANES
2009.pdf`, PDF pages 4–5, printed Table 1. The 433 Phase I annotations still
partition into 400 anchors, 30 mathematical or unit suppressions, and 3
subscript suppressions. The corpus now has 105 definitions, 387 resolved links,
0 ambiguous links, and 13 unresolved numeric bibliography candidates. All 91
physical tables, 78 resolved tables, 13 accepted integrations, and 16 `ok` / 62
`rescued` statuses remain unchanged; only the three affected footnote artifacts
and their derived style profiles change.

Phase K Step 5 is complete at
`outputs/testpapers_batch_phase_k_step5_guarded_final_20260715`. The existing
`PaperVisual` record now stores optional `doi` and `doi_source_line_id` values,
and the existing R paper-output loader carries `paper_visual_inventory.json`.
One shared standalone-object pattern requires an exact `.tNNN` or
`.gNNN` suffix. It attaches seven table DOIs to extracted table visuals and
retains eight positioned figure-caption sequences that directly precede their
matching figure DOIs at the same text origin. Other DOI lines remain
unassigned. The same pattern stops external footer text before a visual DOI;
on PDF page 6, printed Table 1 of `An environment-wide association study
(EWAS) on type 2 diabetes mellitus.pdf`, the `{` definition is now exactly
`denotes unweighted number.` All 28 PDFs retain 91 physical tables, 78 resolved
tables, 13 accepted continuation integrations, 16 `ok` / 62 `rescued`
statuses, 105 definitions, and 387 resolved / 13 unresolved links. All table
and bibliography artifacts are byte-identical to Step 4. No new class,
artifact, fallback, or DOI lookup was added. Phase K is closed; the retained
reference run is the guarded Step 5 corpus above.

Current table-geometry implementation checklist:
`docs/implementation/table_geometry_reconstruction_checklist.md`. Use it to
track marker occurrences, body occupancy, provisional leaf-column candidates,
the completed removal of token-start evidence, preliminary header structure,
canonical extraction, marker attachment, and footer resolution.
The first minimal canonical-extraction boundary cleanup is complete:
pre-selection grids now use the internal typed `ProvisionalExtractedTable`,
while only the selected grid is returned for persistence as `ExtractedTable`.
Canonical physical-grid materialization now also lives in the extraction
package. Preliminary header structure no longer gates canonical extraction;
header/leaf disagreement remains an inspectable header-candidate diagnostic.
Canonical selection now validates rather than routinely rewrites the positioned
grid. When the retained positioned and occupancy leaf counts agree, positioned
cells are preserved unless at least two header cells in one physical row are
wholly contained by different occupancy leaves. A count disagreement defaults
to occupancy materialization. Token starts and continuation parent-band
replacement are no longer part of canonical extraction.

The 28-PDF checkpoint
`outputs/testpapers_batch_gated_sparse_body_occupancy_first_edge_20260715`
completed all 92 physical tables with no empty or rejected grid: 64 use
count-and-cell-geometry-confirmed positioned cells and 28 use occupancy
materialization. No table now selects the narrow header-line-plus-token path.
When ordinary exact-gap occupancy is exactly one separator short, a sparse
stub row may abstain from defining the stub/value boundary only if its label
reaches within two observed spaces of the earliest structurally separated
first-data occupancy. Characters at or beyond that data edge remain evidence,
so p-value occupancy is not removed. This supplies the missing stub separator
for the seven previously token-confirmed tables without changing their cells.
It also corrects printed Table 3 (continued) on PDF page 12 of `Association
between anthropometric indices and chronic kidney disease- Insights from
NHANES 2009–2018.pdf` from 8 x 6 to 8 x 7, matching the stub plus three
OR/p-value pairs on PDF page 11. The rejected
stub split in printed Table 2 on PDF page 5 of `mdpi-The Relationship Between a
Mediterranean Diet and Frailty in Older Adults- NHANES 2007–2017.pdf` remains
six columns. Repeated header-cell/leaf conflicts reject only printed Table 2 on
PDF page 4 and printed Table 4 on PDF page 6 of `GOLD BioAge and depression-
Associations with mortality among depressed NHANES participants
(2005–2018).pdf`; both return exactly to the clean committed cells.

All five `cobaltpaper.pdf` tables now match commit `6db4bb1` exactly in row and
column count, text, and bbox geometry: 23 x 8 and 36 x 8 on PDF page 3, 27 x 6
and 28 x 4 on PDF page 4, and 28 x 4 on PDF page 5. Across the 83 table IDs
shared with that clean commit, exact physical matches rise from 14 in the prior
checkpoint to 46, with no table moving away from a prior exact match. Printed
Table 1 on PDF pages 5-6 of `Systemic inflammation markers and the prevalence
of hypertension- A NHANES cross-sectional study.pdf` remains 48 x 5 plus 14 x
5, has identical five-leaf headers, and merges as one 61-row, 5-column logical
table. The finalized corpus has no
cross-band header-run concern and no Cobalt header concern. Its only non-stub
missing-header case was the eight intentionally blank local child labels in
printed Table 2 (continued) on PDF page 13 of `periodontis2.pdf`. The recovered
header-candidate step now inherits only those labels after adjacent identity,
complete occupancy-leaf alignment, compatible nonblank leaves, and matching
group spans. The existing resolver then integrates PDF pages 12–13 as one 38 x
11 table. All 92 physical extracts and earlier geometry artifacts are unchanged;
no other table inherits a label.

Phase A is complete: each selected `ExtractedTable` now carries compact
`table_positioned_evidence` references into the shared PyMuPDF positioned
document after text furniture and bibliography masks are applied. The full
2026-07-12 corpus run produced 27 paper outputs and 82 tables with no invalid
references or non-Phase-A extraction changes.
Phase B is complete: the existing `CellTextAnnotation` list is now the canonical
early marker-occurrence inventory. Occurrences retain stable IDs, canonical
glyph keys, physical source-cell IDs, source character and line/span
references, bboxes, and font evidence without changing raw text or deciding
footnote meaning. The full 2026-07-12 corpus run recorded 506 valid occurrences
with no annotation diagnostics or changes to existing footnote outputs.
Essential Phase C/D orientation invariant: normalize the complete table-local
positioned evidence for a rotated table into a canonical upright frame before
proposing header/body bands or calculating body occupancy. Preserve original
coordinates and each rule segment's identity and endpoints, then run the same
boundary, occupancy, and extraction route used for ordinarily oriented tables.
Do not retain a separate rotated occupancy or header/body inference path.
The paper text-stream prerequisite is implemented independently of table bands:
source lines retain original IDs and bboxes, rotated orientation groups receive
canonical bboxes and group-local reading order, and context adjacency cannot
cross page or orientation-group boundaries. Raw positioned and extracted
artifacts remain available alongside this projection through downstream JSON
and eventual R consumption.
The 28-PDF checkpoint
`outputs/testpapers_batch_orientation_stream_stage1_20260712` emitted 90 tables
with no failed status. All 87 tables from the prior 27-paper run are
byte-identical; `inst/extdata/NutritionEx.pdf` adds three tables. Bibliography
content is unchanged, and only genuine caption classifications changed.
Stage 2 caption assembly and binding is also complete. The extractor no longer
uses PyMuPDF4LLM caption boxes or page-text caption fallback. It consumes
line-initial candidates from `paper_table_mentions.json`, uses span order and
font separation as structural label evidence while preserving raw line text,
preserves all post-label y-bands in the provisional grid, binds in canonical
orientation-group geometry, and only then groups following text into physical
y-bands and stops complete captions before the first band with multiple
separated horizontal runs. Table rules remain outer geometric limits.
The 28-PDF checkpoint
`outputs/testpapers_batch_caption_stage2_final_20260712` emitted the same 90
tables with zero failed statuses; all table IDs, dimensions, cell text, and
cell coordinates are identical to Stage 1. Eight continuation fragments have
no local caption and 82 tables have bound caption regions. Header/body/footer
band selection remains the next separate Phase C task.
The later geometry-only caption refinement is checkpointed at
`outputs/testpapers_batch_caption_ybands_final_20260713`: all 28 PDFs emitted 92
physical tables. Compared with the preceding extraction checkpoint, only five
grids changed, all by restoring header bands previously consumed by provisional
caption extension. Complete caption line ownership changed only for the two
affected Planetary Health Diet tables, and the restored page-2 header allows its
page-3 continuation to integrate. The existing suite remains at 138 passing
tests; the known page-6 Systemic inflammation table still fails later semantic
definition with `no_variables_for_descriptive_table`.
Stage 3 canonical table-local evidence is complete. The typed
`table_positioned_evidence` projection now carries one affine transform and
positionally aligned canonical geometry for every retained line, span, word,
character, individual rule segment, and stroked rule segment. Candidate,
evidence, caption, and structural-scope bounds use the same frame. The 28-PDF
checkpoint `outputs/testpapers_batch_canonical_evidence_stage3_final_20260712`
contains the same 90 tables with zero failed statuses or geometry diagnostics;
15 tables use rotated transforms and 75 use identity transforms. Extracted
grids and downstream semantic outputs are unchanged. Return now to Phase C
provisional caption/header/body/footer boundary selection; do not add another
orientation-specific route.
Phase C is complete: proposal recording, selected-region review, font-first
body/footer proposals, and explicit fail-closed ownership are implemented.
`table_boundary_proposals.json`. It uses the Stage 3 canonical frame for
ordinary and rotated tables, retains references to individual rule segments,
records stub/value coverage and font changes, suppresses repeated body-rule
patterns from the compact proposal while preserving them in extraction
evidence. `TableRegion` reuses the structural header detector and consumes the
proposal's body/footer models: one supported model is accepted directly, while
raw occupancy chooses only among multiple plausible intervals. The selected
rows are consumed by normalization. Incorrect selected-edge
"unsupported" judgments have been removed. The final 28-PDF/90-table run is
`outputs/testpapers_batch_phase_c_complete_20260712`; it has no failed or
blocked tables, 20 unchanged ending-rule footer candidates, and no
non-proposal artifact changes apart from parse-quality timestamps. All 90
physical extracts have credible rule geometry and a coherent positioned grid,
so none triggers the new guard. A future table lacking both receives empty
region and normalized header/body bands with a structured fail-closed
diagnostic. Phase D writes raw `body_occupancy.json` records for all 90 physical
tables. Phase E writes `leaf_column_candidates.json`. Phase F review exposed a
Phase E bin-origin defect: a real gap can straddle adjacent diagnostic bins and
disappear. The refined occupancy artifact now records exact ordinary-character
gaps and qualifies a separator only when it is at least two observed
space-glyph widths in the dominant table font and size. The Phase C
body/footer-model selection described above is historical: the unified footer
work now leaves proposals as evidence-only records and makes one ownership
decision in `build_table_region()`.
`outputs/testpapers_batch_phase_f_font_space_gap_20260713` covers all 28 PDFs
and 90 tables with no command failure or occupancy/leaf diagnostic. Six tables
gain one supported band, 68 candidate counts now agree with the current
extract, and 22 remain diagnostic disagreements. The Phase F occupancy result
remains geometry evidence; it no longer selects among competing footer models.

Phase G is complete as a non-operative artifact.
`header_structure_candidates.json` aligns positioned header words with the
Phase E bands. Each occupancy band normally defines one preliminary leaf before
intact positioned header runs attach by greatest horizontal overlap. A complete
flat finalized header instead preserves one non-empty canonical cell per
selected column; the generic word-gap run threshold remains only for incomplete
or multilevel headers. Individual
partial rules define groups over those leaves, and source-line plus canonical
marker geometry attaches header markers. The current 28-PDF/90-table run is
`outputs/testpapers_batch_phase_f_font_space_gap_20260713`. Eighty-nine tables
have usable headers and 627 leaves matching 627 occupancy bands; the non-target
text table retains `header_rows_missing`. The artifact contains 109 groups and
74 uniquely linked header markers: 66 leaf links and eight group links. Twenty
header runs cross candidate band boundaries, 13 non-stub bands lack header
text, and 31 blank stubs remain explicit. No existing parser output changes
apart from the candidate artifacts, diagnostic separator counts, and
parse-quality timestamps, and the accepted `ColumnHeaderSchema` remains
independent.

The incomplete/multilevel Phase G refinement is also complete as a
non-operative artifact. The 28-PDF/92-table checkpoint is
`outputs/testpapers_batch_header_structure_geometry_20260714`. It reduces the
23 cross-band concerns in the flat-header checkpoint to two upstream
caption/table-ownership concerns in `cobaltpaper.pdf`, PDF page 3. Structural
examples now include all three repeated Model groups in `NutritionEx.pdf`, PDF
page 6; `Sarcopenia.pdf`, PDF pages 7-8; and `fld.pdf`, PDF page 9, plus the
nested Severity and threshold groups in `periodontis2.pdf`, PDF page 18.
Flat/wrapped one-leaf headers remain leaves, including printed Table 5 in
`mdpi-The Relationship Between a Mediterranean Diet and Frailty in Older
Adults- NHANES 2007–2017.pdf`, PDF page 9. Canonical extracts and accepted
semantic artifacts do not change. Missing continuation child labels remain
explicitly blank for later inheritance rather than being invented locally.

Phase F is complete. Corpus review showed that repeated token starts are
ambiguous inside compound values, while exact occupancy now establishes every
needed separator. `token_start_evidence.json`, its schema/builder, and both
token-dependent canonical-grid overrides are removed.

Phase H is closed at
`outputs/testpapers_batch_geometry_phase_h_closed_20260715`. All 28 PDFs and
92 physical tables match the preceding occupancy checkpoint exactly in ID,
page, shape, cells, and bboxes. Canonical selection has only two paths: 64
count-confirmed positioned grids and 28 occupancy-materialized grids.

Phase I marker attachment is complete at
`outputs/testpapers_batch_geometry_phase_i_marker_attachment_final_20260715`.
The 28 PDFs yield 92 physical extracted/normalized tables and 84 resolved
working tables after eight accepted two-fragment continuation merges. All 433
marker occurrences retain complete physical-cell/character/span
provenance; 56 header occurrences link to one header node, 317 link to body
value candidates, and one links to an existing vertical row-label candidate.
The remaining 59 occurrences stay physical-cell-only because no eligible
logical body/header candidate exists. Exact alignment removes 372 linked
occurrences from candidate `base_text`; two uncertain header glyphs remain with
diagnostics, and 114 repeated symbol residues remain with explicit
unassociated-glyph diagnostics. All Phase H physical, occupancy, canonical,
normalized, column-schema, resolved-table, and continuation artifacts are
unchanged. Phase J is the next table-geometry checklist boundary.

Phase H canonical extraction is complete. Candidate regions now use only the
shared PyMuPDF positioned evidence: horizontally compatible caption/rule
geometry, enclosed connected rule components, prior-page numeric value-column
alignment, and canonicalized rotated orientation groups. Abstract-owned
candidates are rejected, open equation/callout frames do not qualify as grids,
and no alternate extraction backend or broad first-to-last-rule candidate path
remains. The final 28-PDF run is
`outputs/testpapers_batch_extraction_geometry_complete_20260713`: all commands
passed, 91 physical tables were emitted, no candidate occurs on PDF page 1, no
grid has zero rows or columns, and the recovered PDF page 3 continuation in
`Science-Advanaced-Planetary Health Diet and risk of mortality and chronic
diseases- Results from US NHANES, UK Biobank, and a meta-analysis.pdf` integrates
with PDF page 2 into one 68-row, 9-column resolved Table 1. Existing pytest is
138/138 passing; whole-package Ruff still reports three unrelated pre-existing
findings outside the extraction modules.

Numeric page-furniture follow-up is complete. Standalone printed page numbers
are matched independently of the PDF page index only when top/bottom geometry
recurs over all pages or an odd/even scope; arbitrary page subsets are rejected
because continued table values can otherwise look recurrent. The 28-PDF run
`outputs/testpapers_batch_numeric_edge_furniture_refined_20260713` adds 44
verified page-number regions across five PDFs and removes none. All 91 existing
physical tables retain identical dimensions, cell text, and cell coordinates.
`Systemic inflammation markers and the prevalence of hypertension- A NHANES
cross-sectional study.pdf`, PDF page 5, now supplies a caption candidate and a
new 1-row, 5-column failed table candidate, isolating the still-unfixed
caption/rule-region truncation from page-furniture ownership.

Caption/rule-region follow-up: when caption and matching horizontal-rule spans
establish a candidate region, that region must remain operative in positioned
grid construction. Do not replace its bottom rule with the last text baseline
or admit nearby rules outside the selected region. Text-derived candidate
bounds remain appropriate only for paths without direct rule-supported bounds.
Recurrent stroked horizontal rules at a stable top edge or repeated-bottom band
position on at least 80% of document pages are now recorded as rule furniture
and excluded before caption/rule spans are formed; the raw segments remain in
the positioned document artifact.

1. [x] Centralize positioned PDF text/geometry into one shared document pass.
   Replace overlapping PyMuPDF document parses with a single positioned-text
   artifact or in-memory object that preserves page, column, block, line, span,
   character, bbox, font name, font size, flags, writing direction when
   available, and raw/normalized text. Page furniture, captions, table
   extraction, section text, bibliography, footnotes, and table metadata should
   consume that shared evidence rather than independently rebuilding partial
   line/block/font views. Stage this carefully: first define or reuse the shared
   artifact without changing parser decisions, then use it narrowly for
   footer/table-metadata detection with font-change and below-table geometry,
   then migrate broader cleanup only after the artifact is stable.
   Implemented stage: `paper_positioned_document.json` is now built once at the
   front of `parse`, `extract`, and `normalize`; it preserves lines, spans,
   words, chars, page text, and horizontal rule segments. Page-furniture
   detection, `paper_text_stream.json`, extraction geometry, and
   `cell_text_annotations.json` consume that shared evidence; `paper_markdown.md`
   is rendered from the text stream; and the old `pymupdf4llm.to_markdown()`
   paper-context fallback has been removed. Remaining follow-up is to keep
   opportunistic PDF tag support aligned with this artifact rather than adding
   another page parse.
   Processing-order invariant: build the positioned document first, detect and
   apply page-furniture exclusions second, and only then build the filtered
   text stream, identify document sections, and parse the bibliography. Table
   extraction must receive those earlier ownership results; bibliography
   parsing is not a cleanup pass over already extracted table candidates.

   - [ ] Separate source-glyph preservation from parser-facing symbol
     normalization. Positioned and extracted evidence should retain the decoded
     Unicode text observed in the PDF, including symbols such as `≥` and `≤`.
     A distinct semantic normalization step may accept Unicode, ASCII, HTML,
     and documented repaired variants and map them to typed relations such as
     `>=` or `<=`. Preserve the original text and repair provenance whenever a
     broken extractor glyph is reconstructed. Audit `clean_text()` consumers so
     source-line identity, caption ownership, and geometry joins never depend on
     equality between raw Unicode text and semantically normalized text; those
     joins must use stable source references or bounding-box alignment.

2. [ ] Take advantage of PDF tags when present.
   Inspect PDF structure tags as extraction evidence when a paper exposes a
   usable `/StructTreeRoot`, especially `<Table>`, `<TR>`, `<TH>`, `<TD>`,
   `<Caption>`, and nearby `<P>` structure. Tags should be treated as
   hard evidence when they align with geometry, not as a replacement for
   coordinate-faithful extraction. Initial corpus check: 13/27 PDFs have a
   structure tree, 11/27 expose table-structure tags, and only 3/27 expose
   explicit caption tags, so tag support should opportunistically improve
   extraction/caption ownership while the geometry path remains primary.

3. [x] Add a parser-native column header schema artifact.
   Build `ColumnHeaderSchema` between `NormalizedTable` and `TableDefinition` so leaf columns, higher spanning header groups, group-to-leaf relationships, raw cell evidence, and coordinates are explicit before any tableone-style projection.
   Design note: `docs/design/column_header_schema.md`.
   Implementation plan: `docs/implementation/column_header_schema_implementation_plan.md`.
   This should become the primary column model consumed by `TableDefinition` and any later stored summary/tableone projection; continuation compatibility is an important later consumer, but not the main design driver.
   Initial implementation is in place: `table1-parser parse` writes `column_header_schemas.json`, `TableDefinition` consumes it, continuation checks use schema-derived column headers, and tests cover Eke-like Table 1/Table 2 structures plus non-problem tables.
   Follow-up: Eke Tables 1-2 show that multi-line header stacks can produce wrong parent paths when rule-banded header rows are extracted as many short text fragments. The current parser now repairs obvious split estimate/uncertainty value columns, drops sparse non-matrix page-text columns and empty separator columns, removes tall/narrow numeric margin text before grid construction, groups leaf-header words into visual runs by small between-word spacing before assigning those runs to body-derived column extents, only merges wrapped leaf rows after geometry-based header inference, preserves normalized-to-original column identity in `source_col_indices`, moves short leading leaf fragments across adjacent column boundaries when structural or coordinate evidence supports it, trims sparse group rows out of the leaf-header stack, and persists `TableDefinition.column_definition.header_spans` plus per-column `header_path` so JSON no longer relies on flattened multirow labels. Remaining work should expose ambiguous leaf-band fragment assignments as structured candidates that deterministic code or later LLM inference can adjudicate; do not hard-code paper-specific vocabulary.
   Required earlier-stage follow-up: add an explicit
   `HeaderStructureCandidate` after cell-text annotation and before
   `TableRegion`. It should use positioned header lines/spans, individual
   horizontal-rule segments, candidate body-column geometry, and cell marker
   annotations to propose a LaTeX-like structure: one candidate leaf per
   physical column, candidate multicolumn groups over contiguous leaves, and
   wrapped text fragments attached to the same candidate node. It must retain
   ambiguity and source coordinates and must not rewrite `ExtractedTable`.
   `TableRegion` should consume this candidate when deciding the header/body
   boundary. The existing post-normalization `ColumnHeaderSchema` remains the
   accepted column model and should validate or reject the preliminary
   candidate rather than independently reconstructing a competing header.
   Detailed cutover checklist:
   `docs/implementation/header_geometry_to_column_schema_checklist.md`.

4. [ ] Make continuations semantically real.
   One logical Table 1 spanning pages should feed `TableDefinition` and `ParsedTable`, rather than leaving page-level and continuation-page parses as separate semantic outputs.
   Design note: `docs/design/table_continuation_resolution.md`.
   Variable integration design: `docs/design/separated_variable_description_integration.md`.
   Implementation spec: `docs/implementation/continued_variable_integration_implementation_spec.md`.
   First diagnostic step implemented: `table_continuation_column_checks.json` checks explicit and narrow inferred uncaptained adjacent-page `demographic_description` continuations for column count and schema-derived column-header compatibility without changing parser inputs. `table1_continuation_groups.json` can also report an uncaptained next-page Table 1 fragment, but merged artifacts are still inspection-only and are skipped when normalized columns or schema-derived column headers are incompatible.
   Continued-variable integration now writes `continued_variable_integrations.json` as a source-fragment inspection artifact made of existing `TableDefinition` objects with integrated `DefinedVariable` records plus integration provenance and tableone-style metadata. Canonical semantic continuation handling now goes through `resolved_tables.json`.
   Boundary handling now preserves and reinterprets leading continuation body rows before the first standalone continuation variable, so body rows that are ambiguous without the prior fragment can still attach as levels when compatible column and parent-variable context supports it.
   Follow-up: Planetary Health Table 1 now integrates p2-t0 and p3-t0 as one resolved Table 1. The shared PyMuPDF word/rule header-span repair keeps sparse upper group headers as spanning cells while preserving dense repeated leaf headers, so both fragments expose the same visible 9-column header structure before `ColumnHeaderSchema` comparison. The current upstream header-grid rule derives spanning-group evidence from word start columns, not glyph right edges, and requires ordered non-overlapping spans; this preserves tight wrapped leaf headers such as periodontitis p6-t0. Merged continuation artifacts remain source-fragment review views; canonical semantic parsing consumes `resolved_tables.json`.
   Current implementation checklist: `docs/implementation/project_completion_priorities_draft.md`.
   Resolved-table design contract G1.1-G1.5 is in place: `ResolvedTableSet` and child Pydantic models define `resolved_tables.json`, `normalized_tables.json` remains the full source record, and current continuation artifacts are documented as review/provenance inputs or derived views.
   Initial resolver G1.6 is in place: `build_resolved_table_set()` consumes all normalized tables in source order and returns singleton or integrated `ResolvedTable` records with source-table index entries, table-resolution decisions, and row provenance.
   Continuation identity gate G1.7 is in place: explicit continuation metadata, explicit `Table N (continued)` title/caption or leading-row text, and uncaptained adjacent-page fragments after numbered tables are recorded as continuation candidates. They still fail closed as singleton resolved tables with `rejected_continuation` decisions until parent matching and column gates are implemented.
   Parent selection G1.8 is in place: continuation candidates record the closest earlier non-continuation same-number parent when page order and available orientation metadata are compatible. Missing or ambiguous parent choices remain rejected singleton resolved tables until later resolver gates accept integration.
   Column-gated in-memory integration G1.9-G1.12 is in place: the resolver accepts optional `ColumnHeaderSchema` records, uses schema-derived comparison labels as the only column compatibility model, rejects missing or incompatible schemas with `ColumnSchemaCompatibilityDecision`, carries forward parent headers only after a schema match, and appends continuation body rows while recording dropped continuation non-body rows in `IntegrationBoundary`.
   Resolver provenance and source indexing G1.13-G1.15 are in place: retained rows record source table ID, source table index, source row index, source role, and page evidence when available; the source-table index records singleton fragments, consumed base fragments, consumed continuation fragments, and rejected continuation candidates; rejected continuations remain singleton resolved tables with diagnostics.
   Parser wiring G1.16-G1.20 is in place: `table1-parser parse` writes `resolved_tables.json`, builds `TableProfile` and `TableDefinition` over resolved working tables, keeps `parsed_cell_values.json` source-fragment keyed, and joins source value components into `ParsedTable.values` through resolved-row provenance. Remaining work includes continuation-level semantic hardening, status/source-fragment diagnostics, and corpus review.
   Continuation hardening G1.21-G1.23 is in place: accepted continuation body rows feed ordinary resolved-table row/level grouping, so leading continuation count/percent rows can attach to an open categorical parent from the base fragment; `table_processing_status.json` is keyed to resolved semantic tables and carries source table IDs plus structured source-fragment diagnostics; `continued_variable_integrations.json` is retained only as a source-fragment review artifact built from source-fragment definitions and is not consumed by canonical semantic parsing.
   Documentation/artifact contract G1.24-G1.27 is in place: `parsing_output_design.md` records the `resolved_tables.json` contract and source-fragment versus resolved-table artifact relationships; `paper_parse_walkthrough.md` shows resolved tables as the semantic input to profiles, definitions, parsed tables, paper table inventory, and status; no R inspection docs were changed because no real R inspection surface was added.
   Verification G1.28-G1.33 is in place: focused resolved-table regressions cover accepted explicit continuations, schema-rejected continuation candidates, continuation level attachment to a base-fragment parent, and unrelated same-column tables remaining separate. The latest retained full 27-PDF run is `outputs/testpapers_batch_20260709_bib_region_mask`; use that output for current footnote and corpus inspection.
   Recent caption-continuation update: explicit extraction now binds table
   captions one-to-one by page geometry above or below the table before using
   caption text as table identity. A strong uncaptained fragment immediately
   before a below-captioned fragment can now integrate as the prefix of that
   logical table when `ColumnHeaderSchema` comparison matches. In the Asthma
   NHANES paper, page 4 and page 5 now resolve as one Table 1, while page 5
   Table 2 and page 6 Table 3 keep their own below-table captions.

5. [x] Keep paper-page-furniture filtering near the front of document processing.
   `paper_page_furniture.json` is now built before paper markdown,
   layout-aware text streaming, section parsing, bibliography extraction, and
   table extraction. It is also supplied before cell text annotation and
   footnote text-stream footer detection. Repeated page-furniture lines are removed
   from `paper_markdown.md` and `paper_text_stream.json`; `paper_sections.json`
   are derived from the PyMuPDF layout-aware stream when available, and the
   artifact is supplied to the extractor as explicit ignore regions.
   Repeated page-furniture words and chars are removed before text-position,
   rescue, rotated, or sideways reconstruction consumes them, and explicit-grid
   rows are removed only when most populated cell bboxes are mostly inside
   ignored regions. Extraction records `metadata.page_furniture_overlap` when a
   candidate touches ignored regions and `metadata.page_furniture_mask` when
   evidence was removed.
   Implementation plan: `docs/implementation/paper_page_furniture_implementation_plan.md`.
   Design contract, Pydantic schemas, positioned page-text collection,
   matching-text normalization, edge-band recurrence clustering,
   `paper_page_furniture.json` parse output, R inspection helpers, real-paper
   review, early-filtered cell text annotation and text-stream footer
   detection, and early extraction masking are in place.
   Current edge policy: use the ordinary 6% edge band, with a bottom-only 10%
   discovery band restricted to `all_pages` text covering at least half of all
   pages. Positioned words/chars are excluded by exact block/line provenance;
   bbox masking remains only for evidence without line identity. A possible
   later recovery pass may search more widely for the same text only after a
   strict furniture cluster has already been established. The decision and
   deferred option are recorded in
   `docs/implementation/paper_page_furniture_implementation_plan.md`.
   Recent table-mention update: `paper_table_mentions.json` is now built from
   the page-furniture-filtered layout-aware text stream before table extraction.
   It classifies `Table N` lines as caption candidates, continuation labels, or
   prose references and is passed into text-position fallback extraction so a
   prose reference split across lines cannot seed a table candidate. Mention
   records preserve the source-line bbox, and caption rejection uses bbox
   overlap rather than equality between normalized mention text and raw
   positioned glyph text. The 27-paper verification run
   `outputs/testpapers_batch_prose_bbox_fix_20260712` emitted 87 tables; all
   extracted-table artifacts were unchanged from the preceding rotation run
   except removal of the false 8 x 6 prose candidate on PDF page 5 of the
   18-page `periodontis2.pdf`. The
   mention pass also treats line-initial `Table S...` listings under an active
   `Supplementary Information` heading as prose references rather than viable
   caption candidates. The fallback also rejects numeric-anchor grids when the
   supposed value region is
   mostly multi-word prose fragments.
   Clarified order: page-furniture detection and masking happen immediately
   after the shared positioned-document pass. The filtered document is then
   used to identify sections, with careful bibliography parsing as a distinct
   section-owned stage. Only after section and bibliography ownership is known
   should table candidate extraction begin.

6. [x] Retire broad trailing-row cleanup where page-furniture masking owns the issue.
   `metadata.trailing_non_table_rows` is now limited to explicit trailing
   continuation-page cues, including a standalone final `Continued` row with no
   data-column value. Broad large-gap/text-spread trimming after the final
   value row was removed so footer/page-furniture cleanup is owned by the early
   page-furniture mask rather than by a second heuristic path.

7. [ ] Make table-region ownership the single source of caption/header/body/footer truth.
   Initial implementation is in place: `table_regions.json` is built after
   extraction and cell-text annotation, before normalization. `TableRegion`
   records row roles anchored by body geometry: caption rows, preamble rows, column-header rows,
   body rows, footer-note rows, row-role assignments, rule evidence,
   confidence, and diagnostics. Normalization consumes
   `TableRegion.column_header_rows` and `TableRegion.body_rows` when available,
   and extracted-table footnote footer harvesting now prefers
   `TableRegion.footer_note_rows`.
   Caption ownership is now established earlier for explicit table boxes:
   caption candidates are linked by nearest compatible table geometry above or
   below the box, and `metadata.caption_binding` records placement, distance,
   and bbox evidence. `TableRegion` still owns row regions inside each
   extracted table, while extracted-table title/caption fields carry the visual
   table identity.
   Current canonical extraction update: explicit PyMuPDF4LLM table boxes are
   treated only as rough table-region hints. The extracted grid is rebuilt from
   positioned PyMuPDF words, characters, and full-width rules through the
   hline, value-matrix, or bbox-word geometry paths before normalization sees
   the table. `layout_source = "pymupdf4llm_json"` may still identify the
   source of the rough box, but `canonical_extraction_layer =
   "pymupdf_positioned_geometry"` marks tables whose rows/cells/header geometry
   are owned by PyMuPDF positioned extraction. If positioned reconstruction
   cannot build a credible grid from the rough box, the explicit backend table
   is not emitted as an extracted table.
   Current verification run:
   `outputs/testpapers_batch_20260709_bib_region_mask` parsed 27/27 PDFs,
   emitted 82 extracted tables, used `pymupdf_positioned_geometry` for all 82,
   and had 0 backend JSON grid survivors. The test suite no longer keeps
   backend-grid survival fixtures as acceptable parser behavior.
   Positioned row-grid construction derives the first row-label/value boundary
   from the observed gap before the repeated first value-column anchor, rather
   than from a fake midpoint between the leftmost row-label text and the first
   value column. It must keep the extracted grid coordinate-faithful: if a
   printed value is split across physical cells or rows, extraction preserves
   those cells and bboxes rather than joining them.
   The existing collapsed explicit-grid reconstruction is now isolated in
   `_refine_collapsed_explicit_body_layout()`. A narrow ruled-body layout
   branch now handles non-rotated three-rule tables when header visual runs and
   body value starts agree, producing
   `grid_refinement_source = "ruled_body_layout_word_positions"` before the
   older numeric-anchor collapsed-grid path is tried. The first verification
   run changed only the intended Lead exposure p5-t0 table from 27 x 6 to
   27 x 3; all other extracted tables, including the other collapsed-path table
   and all non-collapsed tables, were unchanged.
   Follow-up verification split the Lead p5-t0 header with the partial
   value-region rule above the White/Black leaves: row 0 is now a
   `group_header`, rows 1-2 are `leaf_header`, and `Mean ± SDa` is a group
   spanning both value leaves. The 27-paper run changed only Lead artifacts
   plus ordinary parse-quality timestamps.
   Recent rule-classification update: `horizontal_rules` now preserves
   discontinuous same-y rule positions as ordinary drawn-rule evidence, while
   `full_width_horizontal_rules` is restricted to continuous near-edge-to-near-edge
   rules. Discontinuous value-region rules should inform header structure; they
   must not be promoted into header/body or body/footer separators by summing
   separated spans. The 27-paper run
   `outputs/testpapers_batch_rule_continuity2_20260710` parsed 27/27 PDFs and
   exposed a remaining ruled-body layout bug in `stroke-p7-t1`: the table
   should preserve a row-label column plus six value columns, but the
   ruled-body branch merged the row label with the first OR column.
   Follow-up fixed in `outputs/testpapers_batch_rule_endpoint_fix_20260710`:
   when a clean ruled body exposes column-band endpoints on the full-width
   separator/bottom rules, the collapsed ruled-body branch now uses those
   endpoints as column starts instead of dropping the leftmost header cluster as
   a presumed row-label header. The full 27-paper run still parsed 27/27 PDFs
   and 82 tables; the only extracted-table shape change versus the previous run
   was `stroke-p7-t1` moving from 7 x 6 to 7 x 7.
   Leaf-header reconstruction groups positioned words into small-gap visual
   runs before assigning each run to body-derived column extents. Anchors may
   define value-column extents upstream, but they do not glue visually separated
   header text into one leaf. If geometry roles cover only upper header rows,
   `ColumnHeaderSchema` can use lower declared header rows as the leaf band,
   while rejecting trailing rows that already contain body-value evidence.
   This preserves the Planetary Health p2 -> p3 continuation and the MDPI p5
   -> p6 continuation without schema-level continuation enrichment.
   Grid construction now removes all-empty rows and terminal all-empty columns
   before emitting extracted tables; the current full run found 0 empty-row or
   trailing-empty-column problems in both extracted and normalized tables.
   Recent fallback cleanup: the broad low-quality page rescue
   (`pymupdf_text_positions_rescue`), page-wide sideways transformed
   replacement (`sideways_text_positions`), and model/estimate-specific
   `word_positions_with_horizontal_rules` refinement have been removed. The
   verification run
   `outputs/testpapers_batch_20260709_bib_region_mask` still
   parses 27/27 PDFs, emits 82 extracted tables, records 1308 bibliography
   entries, and has 442 resolved / 0 inferred / 0 unresolved / 0 ambiguous
   footnote links. Bibliography-owned words/chars are now removed before table
   candidate construction instead of suppressing the whole first bibliography
   page and all later pages. This exposes real post-reference tables in
   `periodontis2.pdf` while keeping bibliography entries themselves out of
   candidate evidence.
   Remaining follow-up: Planetary p2 and p3 still use mixed candidate paths
   even though both emit PyMuPDF-positioned geometry, so the next extraction
   hardening step should make the continuation fragment follow the same
   canonical positioned path instead of relying on the PyMuPDF4LLM rough-box
   path.
   Follow-up: migrate column-header schema rescue logic and remaining
   continuation/header compatibility review paths to trust `TableRegion`
   rather than repairing title/caption contamination locally. Harden column
   geometry for Eke Table 2 p6 -> p7, where row-region ownership is now clean
   but normalized column counts still differ. Add R inspection helpers only
   after the Python artifact stabilizes.

8. [ ] Align parser route with table taxonomy.
   `table_category` should drive routing once it is available. Current `table_family` is better understood as an early provisional parser-route signal; decide whether to rename, replace, or derive it from the paper table inventory.
   Recent update: obvious OR/CI estimate-result tables without title/caption
   signals now route through `TableProfile.table_family = "estimate_results"`
   when repeated effect+CI headers and estimate-CI range cells provide
   structural support. In the latest corpus run, Asthma p6-t0 moved from
   `non_table_layout_candidate` to `analysis_outputs`.

9. [ ] Add first-class support for data matrices.
   Tables categorized as `data_presentation` need a sibling semantic model/parser instead of being forced through Table 1 descriptive semantics or left as only normalized grids.
   Recent update: wide matrix-like real tables without title/caption signals are
   no longer marked as `non_table_layout_candidate` solely because Table 1
   variable semantics fail. They remain `ok` with
   `matrix_like_table_without_supported_semantic_route` status notes and can be
   categorized as `data_presentation`. Helicobacter p5-t0, p6-t0, and p7-t0 now
   follow this path.

10. [ ] Model value semantics beyond count/percent.
   Add explicit handling for weighted population sizes, prevalence/percent estimates, age-standardized estimates, standard errors, and `N/A`/not-estimable values where appropriate.
   Design note: `docs/design/parsed_value_components.md`.
   Implementation plan: `docs/implementation/parsed_value_components_implementation_plan.md`.
   Direction: parse source-table cells into index-keyed value-component records before continuation fragments are joined. Do not duplicate row/column labels or variable names in the cell-value artifact; attach semantics later by joining on source/integrated row and column provenance.
   Add the component artifact early in the parse flow, after `ColumnHeaderSchema` and before semantic row/column value joins, so later paper-review diagnostics can assess value patterns without depending on a completed semantic parse.
   Current incremental support: count-percent recognition accepts decimal
   count components when the percent component has an explicit `%`, preserving
   ordinary `mean (SD)` cells such as `52.3 (14.1)`. Parser-facing p-value
   header role matching strips trailing footnote-marker suffixes such as
   `p-value2` or `p-Value 2` while leaving raw header text and
   `cell_text_annotations.json` / `paper_footnotes.json` marker association
   intact. Row classification and table profiling now consume
   `ColumnHeaderSchema`-derived column roles when available, so p-value and
   statistic columns are excluded consistently during categorical block
   detection.
   Do not preserve the old two-slot `ValueRecord` shape as canonical if it blocks the right design. The semantic value layer should become a component-aware joined view over source cell components, row/level semantics, and column semantics.
   Later paper typo/error review should consume the component layer, `ColumnHeaderSchema`, and `ParsedTable.values` once real review workflows identify concrete repeated checks. Do not add generic per-column profile artifacts or helper surfaces before those failure modes are known.
   Recent update: `ParsedTable.values` now preserves source-table provenance, row/column semantics, header paths, parse patterns, and typed value components without scalar compatibility aliases. Count-percent checks now operate on components, and `parsed_cell_values.json` records source-grid components without duplicating semantic row or column labels. The earlier validation-report and parsed-value-column-profile sidecars were removed as over-scoped for the current data-structure goal.
   Recent body-element update: `body_element_candidates.json` now sits after
   `ColumnHeaderSchema` and before `parsed_cell_values.json`. It records
   single-cell candidates plus logical value candidates reconstructed from
   same-column vertical continuations or row text streams that split into one
   candidate per settled value column. `body_row_label_candidates.json` now
   sits beside it for wrapped body row labels, replacing the older
   normalization-time `vertical_label_continuations` row merge. The extracted
   and normalized physical grids are not mutated; candidates carry source
   cells, fragments, bboxes when available, and candidate text or labels used by
   later parsing.
   Recent normalization cleanup: value-fragment grid mutation paths were
   retired from normalization, including count-percent column merging, split
   uncertainty-column merging, embedded label/count movement, extra-wide
   newline-stacked value-column expansion, and empty-column cleanup created by
   those repairs. Eke Table 1 page 4/page 5 now preserves the 19 physical
   columns. `ColumnHeaderSchema` comparison labels now canonicalize standalone
   split-header hyphen punctuation, so the Eke fragments resolve as one
   continuation without re-merging the grid. Remaining value-component work is
   to represent the related estimate/SE leaves explicitly for downstream value
   interpretation.
   Recent column-shape cleanup: normalization no longer drops trailing
   nondata columns, sparse nonmatrix columns, sparse stub label columns, or
   split row-label field columns, and it no longer performs inline
   `merged_split_label_columns` mutation. The physical grid is preserved; bad
   ownership belongs in extraction/table-region work, while logically related
   row-label fragments should be represented by row-label candidates or
   semantic row logic.
11. [ ] Strengthen parent/level reasoning.
   Use table-local evidence such as repeated level blocks, blank or sparse parent rows, indentation, header value roles, continuation boundaries, and value-region shape. Indentation should be one strong signal, not the only signal.

12. [ ] Clean up benign PDF text artifacts cautiously.
   Some text-based PDFs include spreadsheet-like artifacts that should be normalized without hiding extraction evidence. Known examples:
   - U+FEFF zero-width no-break/BOM characters embedded in extracted table cells, likely from spreadsheet copy/paste into the source document. These currently survive into row labels such as Planetary Health rows with invisible trailing characters.
   - Single-row split label tails such as `Coronary heart disease, n` plus adjacent `(\%)`/`(%)` in the next cell when the fragment is physically adjacent to the row label and clearly before the first value column.
   Recent update: footnote-suffixed p-values such as `<0.001a` now count as p-value tokens for word-position column anchoring and value parsing, so a far-right p-value cluster is not collapsed into the last data column.
   Sidecar: `docs/design/cell_text_annotations.md` defines `cell_text_annotations.json` for superscript, subscript, and small-marker geometry; parse now populates page-coordinate cell-bbox annotations when PyMuPDF char geometry is available, and R inspection loads and displays the sidecar. Implementation checklist is in `docs/implementation/cell_text_annotations_implementation_plan.md`. Keep this separate from symbol canonicalization and value parsing.
   Marker-preservation update: header nodes and existing logical body value or
   vertical row-label candidates now expose unchanged `raw_text`, marker-free
   `base_text`, and occurrence-level `marker_ids`. Attachment uses the stable
   physical source-cell ID only after the logical candidate exists. Removal is
   backed by bbox plus exact character/span provenance and exact text alignment;
   uncertain glyphs and repeated symbols without distinct occurrence evidence
   remain in `base_text` with diagnostics. `ExtractedTable`, normalized rows,
   occupancy, canonical selection, continuation identity, and inherited header
   labels are unchanged. Value parsing consumes `base_text` while
   `ParsedCellValue.raw_value` preserves `raw_text`; footnote linking continues
   to consume the associated marker records without assuming that every raised
   glyph is a footnote.
   Footnote follow-up: `docs/design/paper_footnotes.md` defines the `paper_footnotes.json` artifact contract, and `docs/implementation/paper_footnotes_implementation_plan.md` tracks the staged work. Core Python schemas, anchor inventories, table-local footer metadata, definition inventories, glyph canonicalization, deterministic links, parse output, R data-frame helpers, `ObservedFootnotes` attachment, and real-PDF smoke passes are in place. Review found resolved, unresolved, and ambiguous real examples; links remain review-only and should not be consumed downstream.
   Recent footnote update: table-local note lines can now define markers after leading explanatory prose, including embedded and bracketed markers such as `significance. a Represents ... b Represents ...` and `[a] ... [b] ...`. This resolves the `metabolic` Table 1 p-value superscripts against the local Chi-square and Kruskal-Wallis definitions while keeping links as review evidence only.
   Recent footer update: statistical-significance footer lines can now define repeated asterisk runs such as `* P value < 0.05, ** P value < 0.01, *** P value < 0.001`, and anchors attached to p-values preserve the visible asterisk count. This resolves the `stroke` Table 1-3 asterisk superscripts.
   Recent symbol-footer update: known symbol markers such as `†`, `‡`, and `*` can now define any non-empty local footer text without semantic checks on the definition body. This resolves `cardiovascular` Table 1 double-dagger links and the anthropometric CKD dagger/star footer links; p-value semantics belong in a later interpretation layer.
   Recent extracted-footer update: `paper_footnotes.json` now builds table-note
   definition source lines only from final `TableRegion.footer_note_rows`,
   appending adjacent continuation rows in extracted row order. Same-table
   extracted footer definitions remain preferred over duplicate same-table
   positioned-text definitions, which protects multiline rotated-table footers
   such as Eke Table 2.
   Recent text-stream footer update: `paper_footnotes.json` now consumes
   `paper_text_stream.json` line groups for footer metadata instead of running a
   second PyMuPDF block parse. Candidate footer groups now come only from the
   final retained rule's `TableBoundaryProposal.following_text_line_ids` and
   are accepted once by `TableRegion` using mandatory typography, positioned
   prose continuity, and preceding-data evidence. The footnote stage does not
   requalify them from marker or line-count evidence. Final accepted
   `ResolvedTableSet` membership supplies footnote
   continuation scope, so a footer on a terminal uncaptioned fragment can
   resolve anchors from the earlier fragment only after canonical integration.
   Recent footer-finder update: table-local footers are persisted in
   `paper_footnotes.json` under `footers` and surfaced in R through
   `footnote_footers_df()` and `show_paper_footnotes()`.
   `find_table_footer_rows()` consumes final `TableRegion.footer_note_rows` and
   does not rerun row-bound, last-value, rule, or marker-based ownership.
   Generic page-bottom and body-text blocks no longer produce table-footnote
   definitions.
   Recent footer artifact update: text-stream footer line groups classified as
   table-local footers are persisted as unsplit `footers` records before
   definition splitting. R footnote review filters match the selected table's
   visual ID as well as its fragment table ID, so continued-fragment footers can
   be reviewed without treating `Table 1. (continued)` as definition text.
   Recent math/unit update: numeric superscripts and subscripts in expressions like `10^9`, `10^6`, `m^2`, `kg/m^2`, `CO₂`, `I²`, and `×10^9/L` are rejected before `FootnoteAnchor` creation. Subscript annotations are now generally suppressed as non-footnote anchors, including single-letter notation such as `S_I`/`AIR_g` and multi-letter subscript words such as `P_Begg`/`P_Egger`. They remain visible in `cell_text_annotations.json` with original glyph case; `paper_footnotes.json` records suppression counts in `math_unit_anchor_suppression_count`, `subscript_anchor_suppression_count`, and `word_like_subscript_anchor_suppression_count`.
   Recent symbol-font update: PyMuPDF char extraction now applies font-qualified Unicode normalization before word/grid reconstruction for known embedded symbol-font codes such as `±`, `×`, `−`, and `<`. Inline marker detection accepts same-height trailing glyphs attached to numeric/comparator text including `±` values and preserves marker font metadata. In the focused Ethnic Differences run, `S_I` and `AIR_g` remain suppressed subscript annotations, while the marker-font `x` resolves against the local `xP < ...` footer definition.
   Recent footnote-scope update: conventional p-value-star inference has been removed from `paper_footnotes.json`. Observed `*`, `**`, and `***` markers are preserved as anchors and remain unresolved unless an explicit candidate definition is found; conventional statistical interpretation belongs in a later interpretation layer.
   Bibliographic reference follow-up: `paper_bibliography.json` now preserves the paper's own bibliography entries, numbered or unnumbered, from the PyMuPDF layout-aware text stream. Numeric table-cell study/source/header markers are no longer removed from `paper_footnotes.json` just because their glyphs overlap bibliography labels. The footnote linker now keeps those anchors and marks them unresolved without a same-table or same-visual definition, adding review notes such as `possible_bibliographic_reference`; bibliography matching belongs in `paper_bibliography.json`. Reference-list extraction uses one layout stream: read page, then column, then vertical position; start entries at the column left edge, with either a numeric label or the first author/organization line; and keep indented rows open across column and page breaks. The bibliography pass is now the only source of reference-region evidence used by table extraction: if entries are found, bibliography-owned source lines and entry bboxes are passed into extraction so positioned words/chars can be removed before table candidate construction; if no bibliography is found, extraction does not run a separate raw-text `References` scan. The current full 27-PDF run, `outputs/testpapers_batch_20260709_bib_region_mask`, has 1308 bibliography entries, 0 empty bibliographies, and 0 bibliography diagnostics.
   Future work: harvest numeric bibliography reference markers from body text and captions into the same per-paper artifact, then validate one-to-one coverage for numbered lists: every observed numeric reference marker should resolve to a numbered bibliography entry, and every numbered bibliography entry should have at least one observed marker. Add author-year body citation harvesting separately against preserved unnumbered entries. Record coverage gaps as diagnostics without introducing any cross-paper citation-management layer.
   Footnote-style update: `paper_footnotes.json` now splits local caption/footer definitions from structured marker evidence before falling back to text parsing. Extracted footer rows can use `cell_text_annotations.json` when a raised superscript marker begins the first populated footer cell. Raw damaged strings where the marker runs into the following word are preserved as source text but do not define the marker. Extracted footer rows can still contribute weaker text evidence from confirmed statistical marker prefixes such as `xP < ...`. Structured marker evidence is merged with ordinary symbol markers in the same footer group, so an upright `* p < 0.05` definition is not dropped just because the same group also contains a raised `†` definition, as in the anthropometric CKD Table 1 footer. Textual marker definitions such as `The asterisk indicates ...` remain valid local definition evidence. The parser also preserves symbol-block splitting across variable whitespace before `†`, `‡`, `§`, and similar markers, while avoiding all-caps acronym false splits such as `eGFR`; vertical-bar glyph artifacts attached to rotated numeric cells are suppressed as non-footnote symbols.
   Treat these as normalization follow-ups, not emergency parser changes. Preserve raw extraction, add focused repairs with provenance, and avoid broad rules that could merge real value columns into labels.

13. [ ] Add known-failure regression fixtures.
   Create stable real-paper or minimal extracted-table fixtures for specific failures and structural variants that have actually mattered in parser review. Focus on cases that protect parser behavior from silent regressions, not broad unit testing for its own sake. For value components, cover only the patterns and artifact contracts that are tied to real failures or review workflows.
   Recent cleanup: removed broad scaffold/schema/provider/synthetic/display smoke tests and kept the suite focused on parser structural regressions, artifact contracts, and LLM identity-safety checks. Future tests should continue to justify themselves as known-failure protections or important artifact contracts.

14. [ ] Improve R inspection workflow.
   Provide R-native review objects and display methods that make variables, levels, columns, parse notes, category/route decisions, and diagnostics easy to inspect during corpus review.
   Current direction: defer new R helper work until real usage of the component-native artifacts shows which views are needed. Decide whether `ObservedTableOne` remains the right R inspection object before extending it. Any R surface should consume canonical components directly and should not require parser scalar compatibility aliases. Avoid many tiny specialized helpers unless repeated review workflows justify them.
   Design note: `docs/design/table_one_epidemiological_description.md` now defines the narrower Table One target as an epidemiological description table with explicit population/denominator, column, row, cell, and footnote components. Future R inspection work should use that scope before adding body classes or validation methods.
   Recent update: `show_table_structure()` now treats structured header spans, per-column header paths, and deterministic variable row spans as the default structure view, including the row-label leaf column from `ColumnHeaderSchema`, while raw normalized header rows remain opt-in provenance/debug evidence through `include_raw_header_rows = TRUE`.

## Notes

- Do not mark a task complete just because one narrow case has been patched. Mark it complete only when the repo has a general implementation and tests for the intended scope.
- If a task expands into multiple concrete implementation steps, add subitems or link to a dedicated implementation note.
- Recent rotated extraction update: explicit rotated-grid refinement now prefers
  PyMuPDF directional text-block geometry as the source table region before
  coordinate transformation. This keeps a rotated table plus footer together when
  they occupy one column of a two-column page and excludes upright article text in
  the other column.
- Recent rotated candidate restoration: an unintended working-tree expansion
  applied caption-and-rule candidate construction to every canonical orientation
  group and removed the complete uncaptioned orientation-group candidate. Narrow
  local rule sequences then replaced full rotated table regions. Non-upright
  groups again materialize their complete canonical positioned-text candidate
  before entering the shared boundary, occupancy, and canonical-grid stages;
  upright caption-and-rule candidates retain the positive-width connector and
  image-object barrier changes. The 28-PDF checkpoint
  `outputs/testpapers_batch_orientation_restoration_20260716` completed all
  parses, restored PDF pages 5 and 6 of
  `Helicobacter pylori infection in the United States beyond NHANES- a scoping review of seroprevalence estimates by racial and ethnic groups.pdf`
  to 56 x 15 and 58 x 15, preserved its page-7 15-column grid, restored the
  earlier rotated fragments in `periodontis2.pdf`, and left both focused Role
  tables and all CKD canonical-grid failures unchanged.
- Recent document-processing update: repeated page furniture is built near the
  front of parse processing and passed to paper text streaming, markdown
  filtering, table extraction, cell text annotation, and text-stream footer
  detection before those stages build downstream artifacts. Broad trailing
  large-gap/text-spread cleanup after the final value row has been retired;
  `metadata.trailing_non_table_rows` now records only explicit trailing
  continuation-page cues with no data-column value.
- Recent extraction guardrail: the purpose-built bibliography pass now owns
  reference-region detection before table extraction. When it finds entries, it
  passes bibliography-owned line IDs and entry bboxes into extraction so
  positioned bibliography words/chars are removed before table candidates are
  built. It no longer suppresses an entire page or all later pages just because
  a bibliography begins there. When it finds no entries, extraction does not run
  a separate raw-text `References` scan.
- Recent paper-context update: `paper_text_stream.json` now records
  layout-aware, page-furniture-filtered PyMuPDF text lines, page-level
  `column_boundaries` and `column_bands`, and orders pages as page, column, then
  y-position for any detected column count. `paper_sections.json` and
  bibliography entry extraction consume this stream. `paper_markdown.md` is now
  a rendered view of the stream rather than a backend-markdown fallback.
- Recent document-structure follow-up: page furniture should remove repeated
  running headers, footers, watermarks, and other recurring non-content. It
  should not classify one-off section headings. Add a coarse document-outline
  layer that preserves original headings while mapping them into broad roles
  such as abstract, introduction/background, methods, results, discussion,
  conclusion, references, and other.
- Recent extraction guardrail: sparse trailing table-continuation notes such as
  `(Table 1 continues on next page)`, and standalone final `Continued` cues with
  no data-column value, are removed and recorded in
  `metadata.trailing_non_table_rows`; post-header notes such as `(Continued from
  previous page)` remain provenance rows but are excluded from normalized
  `body_rows`.
- Recent extraction update: rotated word-position refinement fails closed when a small backend grid would expand into an implausibly wide table. More than 30 columns is rejected for rotated collapsed-grid recovery, and 13-30 columns requires separator-rule support. Newer PyMuPDF4LLM can emit a mixed-orientation table box containing both upright article text and a rotated table; extraction now derives a separate rotated-block candidate from the contiguous vertical PyMuPDF text block inside that box and lets candidate deduplication choose the recovered table region. The retained full-corpus run now includes the Ethnic Differences recovery and its resolved subscript/marker-font false footnote issues.
- Recent value-matrix geometry update: explicit-grid refinement can derive
  column boundaries from repeated numeric value anchors before using header text
  starts. The row-label/value split is taken from the observed per-row gap before
  the value run, so the left mostly-text column stays intact without keying on a
  header word such as `Characteristics`.
- Recent front-matter extraction update: table candidate detection now builds a
  coarse Abstract-to-Introduction interval from positioned PyMuPDF text. An
  uncaptained backend table-like box inside that interval is suppressed unless
  it has explicit table identity or strong value-matrix evidence. This keeps
  article-info/abstract layout grids out of `extracted_tables.json`; in the
  GOLD paper, the false page-1 `ARTICLE INFO`/`ABSTRACT` pseudo-table is no
  longer extracted, while real tables begin on page 4.
- Recent candidate-order update: final table-candidate selection now applies a
  source-order plausibility check to weak unnumbered candidates. A weak
  unnumbered candidate before a confirmed Table 1, or between consecutive
  confirmed numbered tables such as Table 3 and Table 4, is suppressed because
  it has no plausible table-number slot. Strong unnumbered candidates remain so
  continuation and semantic stages can decide them from geometry and schema;
  adjacent row-label/numeric fragments after a numbered table are also retained
  as possible continuations.
- Recent table-region normalization update: empty-column pruning after
  normalization repairs now uses region-owned header/body rows when available.
  Footer/note rows remain available in extraction and table-region artifacts,
  but they cannot keep a footer-only column alive in the normalized data grid.
- Superseded normalization note: the former rule/value-anchor/content fallback
  now runs only while constructing `TableRegion`. Phase J Step 3 removed it
  from normalization, which copies final region rows without making another
  selection. Full-width separator evidence remains derived from drawn rule
  geometry so filled row highlighting/background shading does not create false
  hlines.
- Recent column-schema update: full-width hlines inside an already selected header band now split upper spanning-group rows from lower wrapped leaf-header rows. Cardiovascular Table 2 keeps body start row 7 while using rows 4-6 as leaf labels and rows 0-3 as training/testing cohort groups.
- Recent column-schema update: comma-containing leaf headers are split across
  adjacent value columns only when body rows repeatedly show the same adjacent
  comma-pair structure: the left value cell ends with a comma and the right
  value cell is populated. This exposes `OR (95% CI)` and `P-value` leaves in
  the METS-IR hypertension Tables 2-4 while keeping unit labels such as
  `Mean AL, mm` and body intervals with internal commas intact.
- Recent normalization update: dense row-by-row full-width rules no longer disable hline separator detection. Fully ruled tables should still use hlines as boundary proposals, then choose the boundary that preserves a multicolumn group row plus its single-column leaf-label row above any row-label-only body parent. This fixes the Table 3 continuation in `Association between anthropometric indices and chronic kidney disease: Insights from NHANES 2009–2018`, where page 11 and page 12 now share the same `Model 1`/`Model 2`/`Model 3` column schema and integrate as one resolved table.
- Recent hline-led extraction update: for credible ruled table candidates with
  full-width drawn horizontal rules, extraction now treats the
  PyMuPDF4LLM grid as only a rough region and rebuilds row/column structure
  from positioned PyMuPDF words inside the ruled band. The first internal
  full-width rule supplies the header/body separator when both sides contain
  text; value-column anchors come from repeated body value positions; upper
  header cells can span adjacent blank value columns. The same sparse-versus-
  dense header-cluster repair is shared with text-position fallback, so base
  pages and continuation pages do not diverge solely because one came from
  fallback and the other came from a backend explicit table box. In the latest retained
  run this fixes GOLD Table 3 (`p5-t0`) as a 5-row, 3-column table with
  `Adjusted Model` spanning `OR (95%CI)` and `p-value`. Downstream
  TableDefinition semantics for small estimate-result tables remain separate
  follow-up work.
- Earlier review update: `outputs/testpapers_footer_blocks_20260701_final`
  recorded 27 PDF command successes, 447 footnote links, 375 resolved links, 54
  inferred links, 7 ambiguous links, 11 unresolved links, 39 math/unit anchor
  suppressions, 2 word-like subscript suppressions, 56 PDF text blocks
  classified as table footers, and 48 page-furniture definition-block
  suppressions from the retired late-filter path. Current footer detection uses
  page-furniture-filtered `paper_text_stream.json` line groups rather than PDF
  block harvesting.
  `parse_quality_reports.json` reports
  `header_body_split_rule_disagreement` when the hline and value-anchor
  candidates both exist and disagree, except when the hline body start only
  precedes the first value row by expected variable/section-header rows with no
  recognized value pattern.
- Recent bibliography baseline update:
  `docs/implementation/real_paper_testing_guide.md` now uses
  `outputs/testpapers_batch_20260709_bib_region_mask` as the current
  retained run: 27 PDF command successes, 0 empty bibliographies, 0
  bibliography diagnostics, 1308 bibliography entries, 25 numbered
  bibliography papers, 2 unnumbered bibliography papers, and 0 mixed
  numbering-style papers. The same run has 442 resolved / 0 inferred / 0
  unresolved / 0 ambiguous footnote links.
- Recent front-matter guard check:
  `outputs/testpapers_batch_20260706_frontmatter_guard` recorded 27/27 parse
  command successes. GOLD no longer has the page-1 pseudo-table; the remaining
  failed table statuses in that run are periodontis2 p6-t0, periodontitis
  p11-t0, PRISm/COPD p4-t0, and Mediterranean Diet/Frailty p3-t0.
