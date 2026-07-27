# Paper Parse Walkthrough

This document explains, in human terms, what happens when this project parses one paper and why it keeps several intermediate versions of each table.

It is a companion to:

- `docs/design/parsing_process.md` for the short overview
- `docs/design/parsing_output_design.md` for the canonical artifact contract

The goal here is not to restate every schema field. The goal is to explain the flow of work from one PDF to the saved outputs, and to make clear why the parser does not jump straight from PDF text to a final structured table.

## One Paper, Many Artifacts

The main user-facing command is:

```bash
table1-parser parse path/to/paper.pdf
```

For one paper, this writes a paper output directory:

```text
outputs/papers/<paper_stem>/
```

Today that directory may contain:

- `extracted_tables.json`
- `table_boundary_proposals.json`
- `table_regions.json`
- `cell_text_annotations.json`
- `normalized_tables.json`
- `column_header_schemas.json`
- `body_element_candidates.json`
- `body_row_label_candidates.json`
- `body_occupancy.json`
- `leaf_column_candidates.json`
- `header_structure_candidates.json`
- `resolved_tables.json`
- `table1_continuation_groups.json`
- `table_continuation_column_checks.json`
- `merged_table1_tables.json`
- `table_profiles.json`
- `paper_table_inventory.json`
- `table_definitions.json`
- `continued_variable_integrations.json`
- `parsed_cell_values.json`
- `parsed_tables.json`
- `table_processing_status.json`
- `parse_quality_reports.json`
- `paper_footnotes.json`
- `paper_bibliography.json`
- `paper_style_profile.json`
- `paper_page_furniture.json`
- `paper_markdown.md`
- `paper_document.json`
- `paper_sections.json`
- `paper_table_mentions.json`
- `paper_visual_inventory.json`
- `paper_references.json`
- `paper_variable_inventory.json`
- `table_contexts/table_<n>_context.json`
- `table_variable_plausibility_llm.json` when `review-variable-plausibility` is run
- `llm_variable_plausibility_debug/...` when variable-plausibility debug tracing is enabled

Some of these are per-table artifacts. Others are paper-level context artifacts.

`cell_text_annotations.json` records superscript, subscript, and small marker
geometry by table cell when compatible PyMuPDF character geometry and extracted
cell bboxes are available. It does not change the raw extracted grid. After
header and body logical candidates exist, stable annotation IDs are attached to
those candidates. Each linked candidate preserves `raw_text` and exposes
marker-free `base_text` only when exact character/span geometry and text
alignment identify the occurrence; uncertain or unassociated repeated glyphs
remain visible with diagnostics.

Each detected annotation now also serves as a stable early marker occurrence:
it records a unique occurrence ID, normalized glyph key, physical source cell,
source PyMuPDF character and line/span references, bbox, and font evidence.
This inventory deliberately retains numeric citations, mathematical notation,
and other unresolved candidates; classification and footer resolution happen
later.

`table_regions.json` records row roles around the geometry-defined body for each extracted
table before normalization: caption/title rows, preamble rows, column-header
bands, body rows, footer/note bands, and row-level role assignments. It is
built from extracted table entries, row bounds, cell bboxes when needed, and
horizontal rules after page-furniture filtering. Table captions and titles are
represented here as table identity/component evidence, not as column headers.
Discontinuous same-y rule segments are preserved as ordinary horizontal-rule
evidence; only continuous near-edge-to-near-edge drawn rules are treated as
full-width boundary rules. The same stage owns the one bottom-of-table footer
decision. Every accepted footer requires a positioned font or font-size change,
a consecutive prose block without a horizontal gap of at least two observed
space widths, and preceding data-band support. A final horizontal rule is
supporting boundary evidence, not sufficient footer evidence. Internal accepted
rows move from `body_rows` to `footer_note_rows`; accepted text below the final
rule remains outside the physical grid. In both cases the exact accepted
positioned lines are persisted once in `TableRegion.footer_line_ids`.

`table_boundary_proposals.json` is built between canonical extracted geometry
and `TableRegion`. It keeps rule-supported table-start and header/body edges,
plus final-rule and adjacent positioned-text evidence, in one upright frame for
both ordinary and rotated tables. Individual rule segments remain referenced
rather than merged. Adjacent text collection stops at a known caption, later
table, or section heading; continuation lines retain source line IDs, canonical
bounds, and font styles across font-size jitter of at most 0.2 PDF points. The
proposal does not accept or reject footer ownership. It also records whether credible
rule geometry or a coherent repeated positioned grid exists. If neither exists,
`TableRegion` fails closed with no manufactured header/body bands, and
normalization preserves that decision. Selected region edges are attached
afterward for inspection.

`paper_positioned_document.json` records the shared PyMuPDF positioned text pass
for the whole paper: pages, visual lines, span text, bboxes, font names, font
sizes, flags, line directions, words, characters, and horizontal rule segments.
Each page also records one compact `visual_components` collection. Raster
components reuse displayed image-block bboxes and source block indices; vector
clip and group components come from the page's single extended-drawing pass and
retain their exact bbox, source index, nesting level, and available drawing
sequence range. Full-page default clips are omitted. These records are
non-operative component evidence, not figure classifications. Clip and group
records describe drawing scopes rather than painted rules, so the extended
drawing hierarchy supplies only `visual_components`. Both horizontal-rule
projections continue to use the ordinary `get_drawings()` records; extended
clip, group, and separately exposed nested records never enter table-rule
geometry.
Text extraction is not clipped to the declared page box: source text outside or
crossing that display boundary is retained with its original bbox. This lets the
ordinary geometry path recover malformed pages whose content stream places part
of a table beyond the visible page without adding a table-specific repair.
It is built before paper furniture, text streaming, section parsing,
bibliography extraction, table mention detection, table extraction context, and
cell text annotation.

Each selected extracted table records
`positioned_evidence`, a typed compact set of page-local references
back into this shared PyMuPDF artifact. The record identifies table-local lines,
spans, words, characters, and individual rule segments after text furniture and
bibliography masks have been applied. It also stores geometry-only canonical
projections aligned with every source-reference list, plus one affine transform
from page space into the table's orientation-group frame. Candidate, evidence,
caption, and structural-scope bounds are projected through that same transform.
Upright tables use the identity transform; rotated tables therefore no longer
require a separate downstream geometry route. It is the sole table-local
positioned-evidence authority; there is no metadata copy or compatibility
alias. The record does not copy text/font payloads, classify any boundary, or
alter the extracted table grid. It now reserves `canonical_grid_bbox`,
`canonical_row_bounds`, and `canonical_physical_column_bounds` for the final
caption-free physical grid. Those fields have no semantic column roles and
remain null or empty until the Step 4 grid-authority cutover populates them.

`paper_page_furniture.json` records repeated page text observations, recurrence
clusters, generic ignored regions, and the authoritative `page_scope`. It is built from
`paper_positioned_document.json` before layout-aware document construction, section
parsing, bibliography extraction, and table extraction. Repeated page-furniture
lines are removed before `paper_document.json` is built; `paper_markdown.md`
then renders only the document's accepted prose.
The first accepted recurrent `N of M` or `N / M` candidate with an observed
`M of M` counter defines the terminal PDF page. If none qualifies, scope is
`unknown` and includes every physical page. Immediately after detection, the
parser creates one in-memory positioned-document projection over the included
pages. Document interpretation, table extraction, and all later stages consume
that projection; persisted `paper_positioned_document.json` retains every
physical page as raw evidence.
Table extraction consumes the positioned
document's words, chars, page text, and rule segments; cell text annotation
consumes the same positioned characters. The page-furniture artifact is still
passed into table extraction, cell text annotation, and document-linked footer
detection as an early geometry mask. It is written even when no repeated page
furniture is found.
Page-furniture observations preserve their ordinary whitespace-normalized text,
including every integer. For each standalone integer, the collector evaluates a
single-slot template without mutating the observation. Only an unambiguous group
completely covering all pages, all even pages, or all odd pages after page 1,
with no duplicate page and one constant `slot value - PDF page number`, enters
furniture clustering under `<page_num>`. This permits nonzero printed-page
offsets and independent odd/even sequences. Rejected slots retain ordinary
exact-text matching.

`paper_footnotes.json` records detected table-local footer regions, footnote
anchors, candidate definitions, and glyph-key links as a paper-level review
artifact. It is written even when no anchors or definitions are found.
Each table-cell anchor reuses its source `CellTextAnnotation.annotation_id` and
records the source annotation type, normally `superscript` or `inline_marker`.
Subscripts remain unpromoted annotation evidence. The stable ID joins back to
the complete character, span, font, bbox, and attachment evidence in
`cell_text_annotations.json`; no second positional anchor identity is generated.
Definition candidates are fed by the exact positioned lines owned by the
matching final `TableRegion.footer_line_ids`.
`find_table_footer_definition_lines()` does not rerun row-bound, overlap,
last-value-row, or horizontal-rule inference. Every accepted footer band enters
definition processing; observed markers may split that band into several
definitions but do not decide whether the accepted text is processed. Confirmed
footer rows can carry marker-start evidence from cell-text annotation geometry
when a raised marker begins the first populated footer cell; raw extracted
strings that visually run the marker into the next word are preserved as
provenance but do not define the marker.

`paper_document.json` is the filtered, layout-ordered, and ownership-partitioned
view of `paper_positioned_document.json`. Its blocks preserve source line IDs
and original page-space bboxes. Lines are partitioned by writing direction;
rotated groups are ordered through an upright group-local projection recorded
as `canonical_bbox`, with orientation-group provenance.
It now owns accepted figure scopes as canonical `figure` entities. These
contain explicit block-leading figure labels, ordered caption block IDs, and
bound raster/vector component references. Same-page source-consecutive
caption continuations require exact positive vertical overlap with the anchor
caption band. A visual component binds only when it is entirely above the
caption assembly, has exact positive horizontal overlap with it, and is not
claimed by another caption. `content_bbox` is the exact component union and
`composite_bbox` is its exact union with the caption blocks. The component and
caption union also defines an exact envelope from the highest component top to
the caption top. Unchanged non-caption blocks with positive page-space
intersection with that envelope are listed in `internal_block_ids`, after
which both bboxes are recomputed as exact unions. Drawing sequence, text
extraction order, page-width thresholds, overlap percentages, edge alignment,
and distance thresholds do not participate. `PaperDocument.structure` contains
one page number and ordered structural-unit list for every page. It exposes the
figure entity exactly once and omits that figure's caption and internal blocks.
Those blocks remain in the source-backed registry and are owned by the entity's
separate caption and content components; positioned visual and rule evidence
remains unchanged. Rejected detections remain non-owning diagnostics. Gutter
and block-layout construction consumes each accepted figure once as its opaque
composite bbox and omits its caption and internal blocks from layout input.
The resulting region placements are flattened in page and existing
orientation-group order and persisted as that page's canonical
`structural_unit_ids`. First-pass prose identification now runs its established
rules over the ordinary blocks in this order and skips figure units without
opening their components.
Context adjacency stops at page and orientation-group boundaries. It is also the
positioned text source for footer candidates absent from the extracted grid.
The stream preserves visual lines, page/column order, line bbox, dominant font
name, dominant font size, and document-level font-style counts after
page-furniture filtering. The external table-footer consumer starts only from
the final `TableRegion.footer_line_ids` after `TableRegion` has accepted
ownership. It does not consume proposal evidence as ownership, requalify that
adjacent group, or scan arbitrary text below the table bbox. Retained groups
are persisted as unsplit `footers`
records, so review can inspect the same raw footer region that later produces
split definition records.
The same smaller-raised marker evidence may begin its own physical source line;
in that position it need not borrow a punctuation boundary from the preceding
line. Embedded markers still require a local definition boundary. Source line,
bbox, font-size, and line-start evidence remain on the definition record.
Other paper text lines are not consumed by `paper_footnotes.json`; this artifact
is table-local. Candidate table-local groups may start with a marker or contain
embedded marker definitions after nearby explanatory prose. If
extracted text visually collapses a superscript marker into the following
definition word, the definition split is based on the smaller raised marker
glyph recorded in PyMuPDF character geometry or `cell_text_annotations.json`,
not on the malformed word itself.
Textual marker definitions such as `The asterisk indicates ...` remain valid
local definition evidence. A single table-footer block can yield several
definition records, for example `*`, `†`, `‡`, `§`, `**`, and `***`
definitions. Repeated page furniture should not enter this stage: table rows,
cell-character annotations, and PDF definition blocks are all derived from
early-filtered geometry.
An extracted caption contributes definitions only when a symbol-marker block
starts after completed caption prose at a punctuation boundary. That narrow
suffix is split with the existing local definition parser, so attached forms
such as `*p < 0.05` are retained while prose letters, years, and
caption-decorating symbols are not promoted as definitions. The complete
caption remains raw provenance.
A standalone DOI ending in an exact visual-object suffix such as `.t001` or
`.g002` terminates an adjacent external footer block before the DOI line. The
line remains unchanged in `paper_positioned_document.json` and its canonical
block, and is consumed as visual caption metadata by
`paper_visual_inventory.json`, not as definition text.
An extracted candidate's existing `candidate_visual_object_barrier_bbox`
similarly terminates the external scan at the image's top edge when that edge
is structurally below the canonical table bbox. It limits footer ownership but
does not enlarge or otherwise rewrite the table bbox.
R footnote review helpers filter by table fragment ID and by paper visual ID,
so a table-number review includes footer records found on continued fragments
such as `Table 1. (continued)` without treating the continuation label itself as
a footnote definition.
The footnote stage receives the final `ResolvedTableSet`. Different source
fragment IDs share the existing `same_visual` link rank only when they are
members of the same accepted integrated table; printed table-number equality
and rejected continuation candidates do not create link scope. The older Table
1 continuation artifact remains an inspection view and is not consumed here.
Numeric table-cell bibliography markers are preserved as anchors and remain
unresolved when they have no local table-note definition. The linker can add
review notes when their glyph keys also appear in the paper bibliography, but
bibliographic resolution belongs in `paper_bibliography.json`.

`paper_bibliography.json` records the paper's own bibliography entries,
numbered or unnumbered, and observed numeric reference markers linked to
numbered entries. `PaperDocument` builds page-furniture-filtered canonical
blocks, the figure-aware block layout, and provisional prose first. Explicit
reference headings and the operative per-heading item walk then consume the
same flattened ordinary-block order; figure units are skipped. Numbered and
retained unnumbered entries preserve their source lines, accepted heading and
content blocks become bibliography entity components, and extraction masks
derive from that ownership. The reference walk uses only blocks with the same
writing orientation as its heading, so an upright bibliography cannot claim a
rotated table or other rotated visual object on a later page. When this
purpose-built walk finds a bibliography, table extraction receives
bibliography-owned source-line IDs and entry bboxes so positioned bibliography
words/chars can be removed before table candidates are built. If this pass does
not find a bibliography, table extraction receives no reference-section evidence
and does not independently scan table text for `References`. Table-cell
reference-marker links are added later after cell text annotations are
available.

`paper_table_mentions.json` is built from the page-furniture-filtered canonical
block registry joined to positioned lines before table extraction and before
final `PaperDocument` ownership is materialized. It records each observed
`Table N` mention as a caption candidate, continuation label, or prose
reference, preserving line IDs, the source-line bbox, local context, and cue
evidence such as a previous line ending in `shown in`. Continuation labels also
record whether they continue from the previous page, continue to the next page,
or leave the direction unspecified. Candidate construction uses this same typed
role for every writing orientation: incoming labels may own following table
evidence, outgoing labels may own preceding table evidence, and unspecified
labels may be considered on either side. Text-position table
fallback consumes this artifact and rejects proposed caption lines that overlap
a prose-reference bbox, so differences between raw and normalized glyph text
cannot turn a prose reference into the start of a table candidate.

Raw and derived artifacts remain side by side through the R handoff:
`paper_positioned_document.json` preserves shared source geometry,
while `paper_document.json` adds orientation-aware reading order and canonical
ownership without replacing it. After page-furniture filtering, document
construction first assembles complete provisional source-block records with
their block-local lines, text, source and canonical union bboxes, orientation,
source order, and source-block provenance. Each populated orientation group then
builds the operative block layout from exact canonical block top and bottom
events. Each non-empty
atomic interval contributes exact positive x-gutters. Tracks continue by
positive x-intersection, remain dormant under one-sided occupancy, and may
refine an existing lane without ending the region when another track persists.
A block crossing only part of the leaf structure spans those columns rather
than removing the gutter globally. Regions materialize left-to-right leaf
column track bboxes plus one ordered `block_placements` list; every block occurs
once with `start_column` and `end_column_exclusive`, ordered by start column,
canonical top, and source order. A region transition occurs only when all
established tracks close and never cuts a structural unit. Accepted figures
participate as one opaque composite-bbox unit and their member blocks remain
available only through entity inspection. Flattened placements define
`PaperDocument.structure` and the ordinary-block order consumed by first-pass
prose and bibliography processing. Block-local line order remains unchanged;
legacy page-wide column metadata remains classification evidence only.
`paper_document.json` also records non-operative bibliography-region candidates.
An explicit heading line must begin its canonical block. The candidate begins
at that block in the page's block-layout order, then records same-orientation
blocks on larger PDF page numbers. Existing prose overlaps are reported as
conflicts without assigning ownership. The operative item walk consumes the
same ordered ordinary blocks, records numbered-start, retained unnumbered, and
accepted continuation evidence, and stops at the first unsupported block.
Separate headings remain separate even when their item numbering continues.
Accepted heading/content blocks become bibliography entity components, and
extraction masks derive from that ownership. Retired B3/B4 comparison fields
are no longer persisted.
Its block registry preserves the block order, source block index,
orientation-group ID, exact page-space and canonical union bboxes, column index
and count, ordered source line IDs, role, and text. Font and span evidence
remains on those source lines rather than being copied into the block. The
prose ownership decision uses only upright source
continuity, exact observed column extent, one font name with a
largest-minus-smallest line font-size span below 0.5, sentence evidence,
confirmed headings, and unfinished prose crossing a page, column, or observed
spanning-layout boundary. An already-marked full-width block is treated as
spanning but cannot independently establish paragraph evidence; one spanning
residual block may sit between unfinished accepted prose and its continuation.
Arbitrary body blocks are not promoted into headings, and opaque font names are
not interpreted.
After the dominant body font profile is available, a line receives the heading
role only when all of its visible spans are bold and its font is strictly larger
than the dominant body font. Table-caption lines and entirely bold source blocks
containing completed sentence prose are excluded. No heading-name list is used.
The legacy bibliography parser does not supply heading roles or trigger block
splits. Source blocks are split only at heading/body transitions established
before bibliography parsing. Consecutive heading lines stay together, and each
logical block preserves its source block index and ordered line provenance.
`extracted_tables.json` preserves the selected physical table grid.
Later normalized and continuation-resolved artifacts reference these records;
they do not replace them.

`paper_style_profile.json` summarizes the document's observed conventions for
footnote markers, bibliography/reference-list style, table caption placement,
figure caption evidence, and table/figure prose references. It is built from
the existing document, table, footnote, bibliography, visual-inventory, and
visual-reference artifacts. It also records consistency checks, such as whether
a predicted numbered bibliography actually has numbered entries. It is review
evidence only; it does not rewrite footnote links or bibliography entries.
Numeric unit/exponent superscripts and subscripts such as `10^9`, `m^2`,
`CO₂`, and `I²` are suppressed before footnote-anchor creation and counted in
metadata. Multi-letter subscript words such as `P_Begg` and `P_Egger` are also
kept out of the footnote anchor inventory.
P-value asterisk markers without explicit definitions remain unresolved.
Explicit thresholds printed in a local caption or footer are linked as source
definitions; conventional meanings are not invented for undefined markers.

## Why There Are Multiple Versions Of A Table

The parser deliberately keeps several versions of the same table because each stage answers a different question.

- `ExtractedTable` answers: what did the PDF extractor recover?
- `TableRegion` answers: which extracted rows and columns belong to captions,
  column headers, body content, and footer notes by geometry?
- `NormalizedTable` answers: what cleaned table structure should downstream logic reason over?
- `ColumnHeaderSchema` answers: how do normalized columns, leaf headers, and higher spanning header groups relate?
- `BodyElementCandidate` answers: which physical body-cell fragments may form
  one logical value element under the settled column grid?
- `ResolvedTableSet` answers: which normalized fragments form the semantic working table list?
- `TableProfile` answers: what kind of table does this appear to be?
- `PaperTableInventory` answers: what broad paper-level category was assigned to each table number?
- `TableDefinition` answers: what do the rows and columns mean, before we parse values?
- `ParsedTable` answers: what final variables, levels, columns, and values did we infer?

If the system skipped these stages and wrote only one final output, it would be much harder to debug extraction errors, normalization repairs, header mistakes, row-type mistakes, and value-parsing mistakes.

## High-Level Flow

The current implemented flow for `parse` is:

```text
PDF
  -> paper positioned document
  -> page-furniture detection and masking
  -> canonical block registry and discovery evidence
  -> table mentions
  -> provisional extraction and canonical grid selection
  -> cell text annotations
  -> table boundary proposals
  -> table regions
  -> body occupancy diagnostic
  -> provisional physical-column bands (legacy leaf-candidate filename)
  -> preliminary semantic header structure
  -> normalized tables
  -> column header schemas
  -> resolved tables
  -> finalized paper document ownership
  -> sections and prose-only markdown
  -> body element candidates
  -> parsed source-cell values
  -> Table 1 continuation inspection artifacts over source fragments
  -> paper footnotes
  -> table profiles over resolved tables
  -> table definitions over resolved tables
  -> parsed tables
  -> table processing statuses over resolved tables
  -> parse quality reports
  -> paper variable inventory
  -> per-table context bundles

TableDefinition.variables
  -> optional standalone variable-plausibility LLM review
```

The implemented `HeaderStructureCandidate` is built after provisional body
occupancy and physical-column bands are available, then rebuilt for the
finalized canonical extract. The legacy-named leaf-candidate artifact assigns
no descriptor, value, group, or leaf roles. Header interpretation creates the
preliminary terminal header nodes and maps each one explicitly to a physical
column with `physical_col_idx`; it also expresses multicolumn groups, wrapped
header fragments, marker attachments, and cross-band diagnostics while
preserving source geometry. For a complete one-row header with one non-empty
canonical cell per selected column, the finalized candidate preserves those
cells one-for-one; a confirmed continuation may therefore expose its accepted
parent terminal-node axis while retaining a disagreeing local physical-band
count as a concern. For incomplete or multilevel headers, observed body-cell
anchors and unambiguous lowest-band header evidence supply the terminal-node
axis. Positioned runs that cover one anchor remain terminal labels; runs or
individual partial rules that cover multiple contiguous anchors can become
groups.
Same-row peers partition a repeated group row only when local rule evidence
already supports that structure. Header text cannot independently add columns.
The artifact remains non-operative for physical extraction: a missing or
disagreeing header candidate cannot reject or alter the canonical
`ExtractedTable`. After final geometry, an adjacent continuation with matching
group spans and a complete one-to-one physical-column alignment may inherit
only blank candidate labels. Those nodes retain their local blanks and source
provenance, and `ColumnHeaderSchema` consumes that effective candidate rather
than reconstructing the missing text. The current header interpreter still
assigns descriptor/value meaning from the first-column split; that assumption
is confined to semantic header interpretation and is scheduled for removal in
Step 7 of the unification checklist.

Two points matter here.

First, the table pipeline and the paper-context pipeline are related but separate.

Second, the optional LLM path is now separate from `parse`. `parse` stays deterministic, while `review-variable-plausibility` writes an additional QA-style artifact.

The parse command also writes a table-level processing-status artifact so rescue attempts and terminal failures are explicit.

## Step 1: CLI Entry And Paper Setup

The CLI first validates that the PDF exists and determines the output directory.

At this point, nothing semantic has happened yet. The system is just deciding whether it can run and where to write artifacts.

Why this is separate:

- it keeps command failures simple and predictable
- it avoids half-written outputs when the input path is wrong

## Step 2: Table Extraction

Before table extraction, the parser builds repeated page-furniture regions from
positioned page text, then builds the canonical block registry, figure-aware
physical layout, table mentions, and the existing prose and bibliography
discovery evidence in memory. No preliminary document, sections, or Markdown
are exposed. The
extraction layer receives page-furniture regions, caption/prose table-mention
evidence, and, when a bibliography was found, bibliography-owned source-line and
entry-bbox evidence. It is responsible for finding likely tables in the
remaining PDF geometry and recovering a raw grid for each one.

After provisional extraction, canonical-grid selection, and final table
geometry complete, the parser materializes the final `PaperDocument` once from
that same block registry. Sections and Markdown are then derived from its prose.

Conceptually, this stage does five things:

1. inspect the PDF page layout
2. remove repeated page-furniture words and chars by exact source-line
   provenance, using bbox masking only for explicit-grid evidence without line
   identity
3. find table candidates
4. build internal `ProvisionalExtractedTable` objects for the deduplicated
   candidates
5. select adequate positioned row and physical-column geometry and materialize the
   public `ExtractedTable` objects

`ProvisionalExtractedTable` is an internal typed grid candidate. It is not
persisted, normalized, or exposed as the canonical extraction artifact. The
first geometry pass may use it to choose the physical grid; only the resulting
`ExtractedTable` crosses the persistence and normalization boundary.

The extractor uses only the shared PyMuPDF positioned-document evidence and
has no alternate table-extraction backend. If positioned words, characters,
source rule segments, and structural text evidence cannot support a candidate,
the extractor fails closed.

Before candidate rule spans are formed, stroked horizontal rules at a stable
top edge or repeated-bottom band position on at least 80% of document pages are
excluded as page furniture. Their source geometry remains in the
positioned-document artifact; only their participation in table-boundary
selection is suppressed.

For upright pages, caption mentions are structural evidence. A caption can
seed a candidate only from horizontal-rule spans that overlap it on the x-axis;
other captions constrain the region only when they overlap the same span. This
allows side-by-side tables to keep independent vertical bounds. Words and
characters are clipped to the resulting caption/rule region before the normal
positioned grid builder runs. That observed rule-bounded region remains the
operative candidate bbox during grid construction and rule detection; the
builder derives bounds from text only when no rule-supported region was found.
Rules outside the selected region do not participate in its boundary model.

An uncaptioned region can also seed a candidate when its individual horizontal
and vertical source rules form one connected, enclosed grid. Directly touching
source segments may belong to the same graph component, but their identities
and endpoints remain separate. An open callout or equation frame is not a
closed table grid, and partial header rules are never promoted to full-width
rules by this component check.

A top-of-page continuation can be recovered from the preceding page's value
column anchors. The new page must show numeric occupancy in every inherited
value-column band, and the candidate ends at the first horizontal rule covering
those bands after the last supported value row. When the parent is numbered,
the fragment inherits the existing continuation identity fields so ordinary
column-schema validation can decide whether to integrate it.

Canonical grid selection uses the same local positioned and occupancy geometry
for base tables and continuation fragments. Continuation identity is retained
for later schema and header-inheritance decisions, but it does not replace the
continuation's local physical bands with a parent-derived axis.

Rotated orientation groups are transformed once into the same canonical
upright frame before candidate construction. The positioned grid builder then
uses the same words, characters, and individual source-rule evidence as it does
for upright tables. Original page coordinates and the canonical transform are
retained in extraction provenance.

If an Abstract-to-Introduction interval is identified from positioned document
structure, any candidate overlapping that interval is rejected. The abstract
does not participate in table-candidate recovery.

When positioned word rows do not already have explicit column boundaries, the
first label/value split is derived from the repeated first value-column anchor
and the observed physical gap immediately before that value across body rows.
It is not derived by averaging the left edge of the row-label text with the
first numeric value. Parenthesized numeric expressions are kept together while
choosing anchors and while assigning cells: an open parenthesis must remain
with following fragments through its matching close parenthesis unless stronger
column geometry proves that the fragments belong to separate cells.

Header visual runs and individual partial horizontal rules can define grouped
header spans over the body-derived leaf columns. Recognizable header words do
not create columns or hierarchy. Compound values such as `mean ± SD` and
`n (%)` remain in one physical value column when the positioned body and header
geometry support one leaf.

Candidate scores remain diagnostic. Selection deduplicates page/index
collisions, preserves stable source order, and can suppress a weak unnumbered
candidate whose position is incompatible with the confirmed table-number
sequence. Strong unnumbered grids and adjacent continuation geometry remain
available for later schema checks.

The extraction invariants are:

- remove page furniture and bibliography-owned words and characters first
- reject Abstract-owned candidates
- derive caption candidates from horizontally compatible caption/rule geometry
- require an enclosed connected rule component for an uncaptioned explicit grid
- require inherited numeric column occupancy plus a covering ending rule for a
  cross-page continuation
- transform rotated evidence before running the ordinary positioned grid builder
- retain source rule segments and raw text instead of repairing a weak extract
- fail closed when these paths do not establish a credible table

### What `ExtractedTable` Contains

`ExtractedTable` is the raw table-facing artifact. It keeps:

- `table_id`
- page number
- detected title and caption when available
- detected table-number and continuation metadata in `metadata` when caption or
  cross-page parent geometry supports it
- row and column counts
- raw cell text
- optional cell bounding boxes
- required typed `positioned_evidence` with source references and the canonical
  affine transform
- extractor metadata

This is the parser's source-faithful record of what the positioned PDF layer
supports. For rotated tables, `table_cells`, `row_bounds`, and horizontal rules
may use the canonical table-local frame. Extraction records the source bbox,
rotation direction, and applied transform so later stages can project source
characters into that same frame.

An explicit continuation cue at the end of a candidate is not a table row.
`trim_trailing_non_table_rows()` removes a standalone final `Continued` cue, or
an explicit next-page continuation note, only when that suffix row has no
table-value cells. `metadata.trailing_non_table_rows` preserves the raw cue,
its former row position, and the removal reason while the shared positioned
document retains the source line. When a typed `to_next_page` table mention
directly establishes a caption-and-rule candidate region, the same metadata
path preserves its mention ID, source line and bbox, continuation role, and
candidate-region provenance without reclassifying it as a caption or matching
its cleaned text again. A first row on the continuation fragment is kept as
table data when at least one non-stub cell contains a value; this is why
`Missing values | 9303 (14.5)` remains part of the continued Asthma Table 1.

The similarly shaped internal `ProvisionalExtractedTable` exists only before
canonical row and physical-column selection. It must not be written as
`extracted_tables.json` or consumed by normalization.

Extraction may record the visible first-word x-position for each first-column
row label. This supplements the physical cell boundary with the actual text
indentation while preserving the original positioned cell geometry.

Positioned candidates preserve recovered cell text bounding boxes in
`table_cells`. These boxes use the same coordinate frame as the recovered grid
and allow normalization to infer row-label indentation without changing the
extract. A cell bbox is evidence for extracted cell content; the cell's
`row_idx` and `col_idx` identify its grid slot, and neither fact assigns a
semantic header role.

### Why `ExtractedTable` Exists

This is the audit trail for extraction.

If a value is wrong here, the problem is in extraction, not in later semantic logic.

If a value is correct here but wrong later, the problem is in normalization or parsing.

That distinction is one of the main reasons the project keeps intermediate artifacts.

## Step 3: Table Region Ownership

The table-region stage converts extracted table geometry into explicit row
ownership before normalization changes the parser-facing grid.

Before `ExtractedTable` is materialized, an internal first pass consumes
`ProvisionalExtractedTable` objects plus their available geometry to select the
canonical physical grid. Caption-owned and empty rows and empty outer columns
are removed first. If the retained positioned-column count agrees with the
local physical-band count, occupancy validates the existing positioned axis
and the source cells are preserved. The positioned cell assignment is rejected
when at least two header cells in one physical row are each wholly contained by
a different physical band; this is direct bbox disagreement, not a semantic
header judgment. A column-count disagreement ordinarily uses occupancy bands
to materialize the grid.

A strongly ruled positioned axis may survive a count disagreement only when
repeated value anchors already establish that axis, distinct source header-line
starts cover every non-stub positioned column, the positioned label column is
supported on every token-evidence body line, and each value column is supported
on at least three body rows. This confirms an existing axis; it does not derive
one from token clusters. The separate explicit-continuation path may reuse an
already finalized parent axis only when page order, leaf headers, column count,
value-anchor alignment, and complete per-line value-band support all agree.

After materialization, the persisted table-region
artifacts are rebuilt from `ExtractedTable` objects and their available geometry:
cell boxes, row bounds, table bboxes, full-width and ordinary horizontal rules,
and already-filtered page context. After caption/preamble ownership is removed,
the same structural header detector used by normalization selects the
header/body split from retained separator rules and then value-region evidence.
Footer ownership is decided once in this stage from the table bottom. The same
scan evaluates extracted trailing rows and final-rule-adjacent positioned text,
requires a local typography change and prose continuity without a gap of two
observed spaces, and uses data-band content plus any final rule only as
supporting geometry. It does not infer boundaries from footer wording or let a
later footnote consumer revise ownership. Its ordered `footer_line_ids` are the
single downstream reference for either kind of accepted footer.

This stage deliberately separates three concepts that should not share one
generic "header" label:

- page headers are page-furniture candidates and should already be filtered
- table captions/titles identify a table but are not column headers
- column-header bands are the rows that define the table's column axis

`NormalizedTable` consumes these region decisions when available. Footnote
harvesting consumes only `footer_line_ids` from this artifact and does not
independently recover internal lines from row geometry or external lines from a
boundary proposal.

### Provisional Physical-Column Geometry and Header Interpretation

After row ownership is selected, `body_occupancy.json` preserves the raw
physical-line occupancy matrix. It also records exact internal character-box
gaps, retaining only gaps at least two observed spaces wide in the dominant
body font and size. `leaf_column_candidates.json` uses those font-qualified
gaps as provisional separators, so separator detection is not dependent on the
starting offset of the diagnostic x bins. Despite the legacy filename, the
artifact contains role-free `PhysicalColumnBandCandidate` records. It does not
identify a stub, descriptor column, value column, group, or semantic leaf.
`header_structure_candidates.json` then aligns positioned header evidence with
those bands. This later interpretation stage creates preliminary terminal
header nodes and maps them to physical columns through `physical_col_idx`. On
the finalized pass, a complete flat one-row header preserves one non-empty
extracted cell per selected canonical column without applying the general word-
gap run threshold. Intact runs remain the evidence for incomplete and
multilevel headers. Observed body-cell centers and unambiguous terminal-label
centers act as per-band anchors: one-anchor runs stack on a terminal node, while
multi-anchor runs and individual partial rules can define multicolumn groups
over contiguous terminal nodes. Same-row peer partitioning is
allowed only with local rule support, and repeated peer rows are aligned into
equal blocks only when the leaf count divides evenly and every peer has a
corresponding rule fragment. Mixed physical header/body rows are not yet
represented cell-by-cell: current `TableRegion` ownership remains row-wide.
Step 6 will introduce mixed-row ownership only from typed rule identities,
adjacent source rows, exact boundary relationships, and explicit cell
ownership.
Group-to-leaf relationships and source-supported marker attachments remain
explicit. Header words crossing occupancy boundaries and bands without header
text are retained as diagnostics after structural assignment rather than being
used to rewrite the grid. A header/leaf-count disagreement is likewise recorded
on this artifact after extraction and does not participate in canonical-grid
acceptance.

Persisted header structure does not gate physical extraction. Occupancy and
physical-band evidence are operative during canonical extraction in the
current transitional flow. `ColumnHeaderSchema` consumes the header candidate,
and its exact physical-column alignment also supports provenance-bearing blank-
label inheritance for a structurally aligned continuation; normalization
performs no repair.

## Step 4: Normalization

Normalization converts each `ExtractedTable` into a `NormalizedTable`.

This is the first stage that prepares the table for interpretation, but it still avoids making strong semantic claims such as "this row is definitely a categorical parent variable" or "this cell definitely means a count and percent."

### What Normalization Does

Normalization currently performs several practical cleanup steps.

#### 4.1 Build A Stable Row Grid

The extracted cells are reassembled into a row-major grid.

This gives the downstream logic a stable rectangular structure to reason over.

#### 4.2 Preserve The Selected Physical Grid

Normalization keeps the selected table's physical row and column counts and
the identity of every source column. It does not remove sparse edge columns,
move text, merge cells, or synthesize replacements. Incorrect physical cells
must be corrected in extraction; logical relationships between preserved
cells belong in later candidate and semantic stages.

#### 4.3 Produce Parser-Facing Cleaned Rows

Normalization builds `metadata.cleaned_rows`, which is the parser-facing text version of the table.

This cleaned form is used by downstream heuristics, prompting, and debugging.

The shared text cleaning layer currently does things like:

- collapse whitespace
- normalize symbol variants such as dash forms and comparator forms
- repair a narrow set of known extractor glyph failures

One example of that last category is a broken replacement character such as `�0.12` being repaired to `<=0.12` in parser-facing text.

Some symbol-font repairs happen earlier, during PyMuPDF character extraction,
because font context is needed to know that an extracted character such as `6`
is really `±` or that a symbol-font comma is really `<`. Those repairs feed
word/grid reconstruction and preserve raw glyph provenance on character
records. Parser-facing text cleaning remains the later table-text normalization
layer.

Important design rule:

- raw extracted cell text is still preserved earlier in `ExtractedTable`
- cleaned parser-facing text belongs in normalization and later stages

#### 4.4 Record Text Cleaning Provenance

Normalization now also records `metadata.text_cleaning_provenance`.

This is a table-level audit summary showing, for the surviving normalized grid:

- which comparator symbols were observed directly
- which comparator symbols were reconstructed from known extractor glyph-failure rules
- which repair rules fired
- how many cells needed glyph repair

This exists because parser-facing cleanup is useful, but it should not be invisible.

#### 4.5 Apply Table-Region Header And Body Rows

Normalization requires the matching final record from `table_regions.json`
and consumes its `column_header_rows` and `body_rows` directly. Caption/title
rows, preamble
rows, and footer/note rows remain preserved in `metadata.cleaned_rows`, but
they are excluded from `header_rows` and `body_rows`.

There is no normalization-time header/body fallback. A missing or invalid
region fails rather than creating a second ownership decision.

This is an important turning point in the parse, because many later steps assume the system already knows which rows are header material and which rows are body material.

Why the split is still visible here:

- it is still structural
- later semantic steps need this split
- it is easier to debug when region decisions are visible before full semantic interpretation

#### 4.6 Build Row Signatures

For each body row, normalization builds a `RowView`.

`RowView` is a compact row-level feature record. It keeps:

- raw row cells for the body row
- cleaned first-cell forms
- whether the row has trailing values
- simple numeric density signals
- indentation when it can be inferred

This gives later heuristics a small and inspectable summary of the row rather than forcing every heuristic to re-derive low-level row facts from scratch.

#### 4.7 Preserve Split Value Evidence

If extraction records an estimate, count, percentage, or uncertainty fragment
in a separate physical cell, normalization leaves it there. Later body-value
candidates may relate those fragments without changing the grid.

#### 4.8 Preserve Physical Row-Label Columns

Normalization no longer shifts, merges, or suppresses row-label columns after
extraction. Sparse stub columns, split left-side label fields, section stubs,
and adjacent label fragments remain in the physical normalized grid. If those
columns are wrong, the fix belongs in positioned extraction or table-region
ownership; if they are physically real but logically related, downstream
row-label candidate or semantic row logic should represent that relationship
without rewriting `NormalizedTable`.

This keeps `ExtractedTable` and `NormalizedTable` aligned on physical column
structure and avoids hiding extraction defects behind row-label repairs.

#### 4.9 Preserve Physical Value Fragments

Normalization no longer merges split value fragments, embedded label/count
fragments, or newline-stacked value-region cells into synthetic columns. If
the extracted grid contains those physical fragments, `NormalizedTable`
preserves them. Logical relationships between fragments belong later in
`body_element_candidates.json`, parsed value components, or extraction fixes
when the visual grid itself was wrong.

Wrapped body row labels are not merged during normalization. They remain as
physical rows in `normalized_tables.json` and are later represented in
`body_row_label_candidates.json`, after `ColumnHeaderSchema` has established
row-label and value columns.

#### 4.10 Preserve Region Boundary Provenance

Normalization copies the table-region source, confidence, caption rows,
preamble rows, footer/note rows, and diagnostics into
`metadata.header_detection`. This makes the
region decision visible beside the normalized grid while keeping the canonical
region artifact in `table_regions.json`.

#### 4.11 Decide Whether Indentation Is Informative

For some papers, first-column indentation clearly helps distinguish parent rows from level rows.

For other papers, small horizontal shifts are just extraction noise.

Normalization records whether indentation appears informative enough to matter later.

### What `NormalizedTable` Contains

At the end of normalization, each table has:

- `header_rows`
- `body_rows`
- `row_views`
- `metadata.cleaned_rows`
- `metadata.source_col_indices`
- identity-preserving source-column information
- header-detection diagnostics
- indentation diagnostics
- text-cleaning provenance

### Why `NormalizedTable` Exists

This artifact is where the table becomes parser-friendly without yet becoming fully semantic.

That separation matters because many downstream mistakes are really normalization mistakes, not semantic mistakes.

`source_col_indices` is the identity map from each normalized column to the
same extracted physical column. Later stages consume that identity; they do
not reconstruct it from repair summaries.

## Step 5: Build `ColumnHeaderSchema`

After normalization, the parser builds a parser-native column-header schema for
each normalized table and writes `column_header_schemas.json`.

This artifact keeps column structure explicit before `TableDefinition` builds
the value-free table definition. It records:

- one projected terminal node per candidate node, retaining its explicit
  physical-column mapping
- candidate `base_text` as the structural leaf and group label
- the candidate's contiguous spanning groups over those leaves
- group-to-leaf relationships as explicit records
- stable candidate node and evidence IDs, preserving marker linkage
- positioned raw text and canonical coordinates from candidate evidence
- structured diagnostics when a candidate axis or reference is incomplete

This stage does not infer header rows, repair fragments, create groups, or
respan nodes. Those decisions have already been made once from positioned
geometry in `HeaderStructureCandidate`. A missing or invalid matching
candidate fails closed instead of invoking a second header builder. Resolved
tables ordinarily receive a table-ID-adjusted projection of their source
schema; a missing source schema produces an explicit empty failure record and
never triggers reconstruction.

The current projection still labels physical column zero as the row-label
column and all later columns as values. Step 3 keeps that assumption out of
physical-band evidence; Step 7 will replace it with explicit descriptor, value,
or unknown terminal-node roles and allow multiple descriptor columns.

`TableDefinition.column_definition` now carries that structure forward. Each
defined column stores a leaf `column_label`, a top-to-bottom `header_path`, the
supporting header group IDs and labels, and table-level `header_spans` that can
render multirow column headers without reconstructing them from flattened text.
The semantic `columns` list remains value/statistic-column oriented, while
`header_spans` also includes the row-label leaf so displays keep the full
header axis, including labels such as `Characteristic` or `Variable`.

The schema is deliberately not a tableone object and does not store summary
values. It supplies the column axis that later semantic and stored-summary
objects can consume.

Why this exists:

- multi-row headers should be recoverable as structured leaf columns and spanning groups
- `TableDefinition` should classify column semantics from a shared column model
  rather than rebuilding header structure locally
- later tableone-style rendering needs a stored summary object before printing,
  and that object will need a stable column axis

## Step 6: Resolve Continuation Fragments

After normalization and column-schema construction, the parser builds
`resolved_tables.json`.

This artifact is the semantic working table set. It starts from every
normalized source table and promotes either:

- singleton resolved tables for ordinary source tables
- integrated resolved tables when a continuation candidate has clear identity
  evidence, an unambiguous parent fragment, and compatible
  `ColumnHeaderSchema` columns
- rejected continuation singletons when a candidate fails closed

The resolver preserves `normalized_tables.json` unchanged as the complete
source record. Every retained resolved row maps back to source table ID, source
table index, source row index, source role, and page evidence when available.

`TableProfile`, `TableDefinition`, and `ParsedTable` consume this resolved
working list. For an integrated continuation, the parent headers are carried
forward only after the schema compatibility decision is accepted, continuation
body rows are appended in source order, and dropped continuation header or
non-body rows are recorded in the integration boundary. Compatibility normally
requires the full header paths to match. A continuation that repeats the same
leaf headers and column count but omits the parent's spanning group row may
inherit that parent group tree; a contradictory continuation group is not
ignored.

Continuation integration is not limited to captions that appear above the first
fragment. If a strong uncaptioned table fragment, including the last source
fragment in an already integrated prefix, is immediately followed by a
captioned fragment whose column schema matches, the captioned terminal fragment
can supply the logical table identity for the earlier chain. An integrated
prefix keeps its resolved-table ID, prior source roles, row provenance, and
existing boundaries; the terminal fragment is appended as a continuation with
one new boundary. The earlier headers are carried forward and the repeated
terminal header row is dropped.

The parser still writes the older continuation inspection artifacts for review.
Those artifacts remain useful for checking source-fragment continuation
evidence, but they are no longer the canonical semantic table list.

From this point forward, the semantic table count is the length of
`resolved_tables[*]`, not the length of `normalized_tables.json`. That means
`table_profiles.json`, `table_definitions.json`, `parsed_tables.json`,
`paper_table_inventory.json`, and `table_processing_status.json` use resolved
table IDs. Source-fragment artifacts still use original normalized table IDs
and are joined back through `resolved_tables.json` provenance when needed.

When parse outputs are written, the parser also checks whether explicit or
narrow inferred source-fragment continuations have compatible columns.

This inspection path does not try random integrations. A
continuation fragment must already have clear continuation evidence for a
specific table number, or be an uncaptained, unnumbered adjacent-page fragment
after a likely descriptive table, before the parser compares it to the closest
prior fragment for that table number.

The parser writes:

- `table_continuation_column_checks.json`
  records normalized column-count agreement, schema-derived column-header agreement,
  and an overall compatible/incompatible/no-parent status

The same parse still checks whether the paper appears to have a Table 1 continuation.

This stage is intentionally narrow. It only considers Table 1, and it only accepts a merge when the continuation evidence is explicit or strongly inferred and the schema-derived column headers are compatible.

Current examples of continuation evidence include:

- extractor metadata indicating a continuation of table number 1
- title or caption text such as `Table 1 (continued)`
- a continuation marker in the first normalized rows
- an uncaptained, unnumbered table-like fragment on the next page after Table 1

When the evidence is compatible, the parser writes two inspection artifacts:

- `table1_continuation_groups.json`
  records the source table IDs, table indices, column-header comparison, merge decision, and diagnostics
- `merged_table1_tables.json`
  records an artifact-only `NormalizedTable` that appends continuation body rows to the base Table 1 rows

The merged artifact preserves source-row provenance in `metadata.table1_continuation_merge`.
That lets a human inspect a single logical Table 1 view while still tracing every merged row back to the original normalized table and row index.

For compatible continuation groups, the parser may also write
`continued_variable_integrations.json`. This older artifact is retained as a
review view over source fragments while `resolved_tables.json` is the semantic
input to table definitions and parsed values. It is built from source-fragment
table definitions, not from the resolved semantic definitions, so it remains an
auditable old-view artifact rather than a second semantic parse path.

Continuation header comparison is schema-only: the continuation artifacts use
`ColumnHeaderSchema` through the parser's column-header tooling and do not
reconstruct column meaning from normalized header rows. If a usable schema is
missing, compatibility fails with a structured diagnostic instead of falling
back to a cruder comparison. Coordinate profiles remain separate diagnostics
and do not override matching column headers with matching normalized column
counts.

## Step 7: Provisional Table Routing With `TableProfile`

Once the resolved working table list exists, the parser builds a `TableProfile`
for each resolved table.

This is an early routing stage. It asks questions like:

- does this table look like one of the parser families currently implemented?
- should the current Table 1-style semantic parser run?

The current repository is centered on Table 1 style descriptive tables, but mixed-table papers exist. `TableProfile` is the stage that prevents the system from pretending every table belongs to the same family.

`TableProfile` is narrower than the paper table inventory because it is built earlier and currently represents parser-route support, not the complete table taxonomy. A wide numeric data matrix can still have `table_family = "unknown"` if it is neither a descriptive-characteristics table nor an estimate-results table. The broader `paper_table_inventory.json` stage can still categorize that same object as `data_presentation` using shape, numeric density, threshold/statistic headers, and normalization repair evidence.

The intended long-term direction is that the broad table category drives route selection once that category is available. In other words, `table_family` should be treated as a provisional route signal and should remain consistent with `table_category`, not as an unrelated second concept.

Why this stage exists:

- it keeps mixed-table handling explicit
- it lets the deterministic parser decide whether an LLM step is even relevant

## Step 8: Build `TableDefinition`

`TableDefinition` is the value-free semantic interpretation of each resolved
table.

This means it tries to answer:

- which rows represent variables?
- which rows are levels under a variable?
- which columns are group columns, overall columns, or statistic columns?

But it does not yet parse all displayed values into final numeric records.

### What `TableDefinition` Tries To Recover

For rows:

- continuous variable rows
- categorical parent rows
- child level rows
- one-row binary indicator rows, where a single `n (%)` row reports the counted state and the complementary state is implicit
- count-percent categorical level continuations, where value-pattern continuity can preserve levels under an `n (%)` parent even when indentation is unavailable or unreliable
- variable labels
- normalized variable names
- row spans
- units hints
- summary-style hints

For columns:

- label column vs data columns
- overall vs group vs p-value vs trend vs SMD style columns
- grouped-column structure when it can be inferred

Column structure now comes from `ColumnHeaderSchema`. That means
`TableDefinition` can focus on semantic roles and grouping labels instead of
owning the mechanics of leaf-header and spanning-group recovery.

One implemented heuristic detail is worth calling out explicitly:

- a row with empty group columns but populated test or statistic columns can still be a variable header
- if that row is followed by plausible child levels such as `Yes` and `No`, it should be treated as a new variable, not as another level under the previous variable
- continuous-summary rows can be recognized when a PDF extracts the plus/minus glyph as a spaced `6`, such as `25.9 6 3.6`; the raw cell text remains unchanged

This matters for printed Table 1 layouts where the parent row carries only the p-value or trend-test result and the level rows carry the group counts.

### Why `TableDefinition` Exists

This is one of the most important design choices in the project.

The parser does not jump directly from a normalized grid to parsed numeric values because it is useful to have a stable semantic layer that describes what the table means before any value parsing happens.

This makes it easier to:

- inspect row and column meaning independently of value parsing
- support downstream matching and R-side table objects
- compare deterministic semantics with future LLM semantics

## Step 9: Build Body Element Candidates

After `ColumnHeaderSchema` exists, the parser builds
`body_element_candidates.json` and `body_row_label_candidates.json` over source
normalized tables.

`body_element_candidates.json` is the first body-value interpretation layer. It
does not alter the extracted or normalized grid. Instead, it records candidate
logical values from one or more physical source cells, including:

- a normal single populated body cell
- a value split vertically into a blank-label continuation row
- a row text stream that can be split into exactly one candidate value per
  settled value column

Each candidate keeps its source cells, original row and column indices when
known, bboxes when available, printed fragments, candidate text, `raw_text`,
`base_text`, and linked `marker_ids`. Marker attachment occurs only after the
candidate exists and only through a stable source-cell ID. It never changes a
physical row, column, cell, occupancy band, or bbox.

The builders take exact source-cell text from the matching `ExtractedTable`;
normalized cleaned rows are not treated as raw text. `anchor_col_idx` is the
stable join to the projected schema leaf. The later column definition supplies
that leaf's ID, groups, and full header path to final values without duplicating
header semantics in the candidate artifact.

This lets later value parsing use good element-candidate text while R and
Python inspection can still show what was physically printed in the PDF.

`body_row_label_candidates.json` is the sibling body-label interpretation
layer. It records candidate logical labels from adjacent physical body rows
where the anchor row has values and following label-continuation rows have
label text but empty value columns. It gives row classification and
`TableDefinition` the candidate label while preserving the physical rows in
`normalized_tables.json`. Marker-bearing ordinary single-row labels remain
physical-cell-only links unless a logical row-label candidate already exists.

## Step 10: Parse Source-Cell Value Components

After body element candidates exist, the parser builds
`parsed_cell_values.json` from those candidates in schema-derived value
columns.

Value-component parsing consumes marker-free parser-facing text derived from
candidate `base_text`, while each parsed record's `raw_value` preserves
candidate `raw_text`. Marker-linked candidates retain the exact
geometry-derived `base_text` as the parsing input. Candidate diagnostics make
any retained uncertain marker glyph explicit.

This is deliberately earlier than the final semantic value join. Each record is
keyed by:

- source table index
- source table ID
- row index
- column index

The record stores the parser-facing value string that was parsed plus typed
components such as
`count`, `percent`, `estimate`, `se`, `mean`, `sd`, `median`, `q1`, `q3`,
`p_value`, `missing`, `text`, or `unknown`.
When the value came from multiple physical cells, the record also stores the
element candidate ID, printed fragments, and source-cell provenance.

It does not store variable names, level labels, column names, or header paths.
Those semantics belong to `TableDefinition` and `ColumnHeaderSchema`.

This early component layer is useful for two reasons:

- continuation handling remaps already-parsed source values by row and column
  provenance instead of reparsing display strings after fragments are joined
- paper-review diagnostics can later assess per-column value-pattern anomalies,
  possible typos, and suspicious inconsistencies without depending on a fully
  successful semantic parse

Ambiguous shapes such as `52.3 (14.1)` remain conservative until semantic
context can distinguish `mean (SD)` from `estimate (SE)`.

## Step 11: Build `ParsedTable`

`ParsedTable` is the final deterministic structured table output.

This stage combines:

- the resolved normalized table grid
- the table definition
- source-cell value components

and produces normalized long-format value records.

### What Happens Here

The parser walks the semantic row and column structure and joins each relevant
displayed cell to its source `ParsedCellValue` record. For singleton resolved
tables this is usually the same row index. For integrated continuations, the
join uses `ResolvedRowProvenance` so a resolved row can still point back to
the original source table fragment and source row. It then attaches variable,
level, column, and header-path semantics to the already parsed component
payload.

Examples include:

- count and percent components
- mean and standard deviation components
- median, q1, and q3 components
- p-value components with inequality relations
- scalar count or estimate components

Some source component shapes are deliberately conservative. For example,
`52.3 (14.1)` is parsed in `parsed_cell_values.json` as an estimate plus an
ambiguous uncertainty component unless source context already resolves it. In
this semantic join stage, a variable-level summary hint such as `mean_sd` can
refine those components into `mean` plus `sd` while preserving the source
record provenance and raw printed value.

### Why `ParsedTable` Is Separate From `TableDefinition`

Because row and column semantics can be right even when value parsing is wrong, and vice versa.

Keeping these apart makes debugging much more honest.

`ParsedTable.values` is now the component-aware long-format semantic view.
`components` is the canonical value payload. Scalar compatibility aliases such
as `value_type`, `parsed_numeric`, and `parsed_secondary_numeric` are not part
of the canonical value record.
`parsed_tables.json` is not replaced by `parsed_cell_values.json`; it is the
joined semantic view over source components.

## Step 11: Build Parse Quality Reports

The parser also writes `parse_quality_reports.json`.

This is an inspection artifact built from deterministic row classifications, variable blocks, column-role guesses, and value-pattern recognition.
It is meant to answer questions like:

- are many rows still classified as unknown?
- did a p-value column mostly contain p-value-like values?
- are inferred group or overall columns mostly numeric/statistical?
- did header detection or normalization emit suspicious structural signals?
- do the full-width hline separator and first value-region anchor disagree on
  where the table body starts?

This step does not change `table_definitions.json` or `parsed_tables.json`.
It exists so column and row problems are visible even when the table technically parses.

## Step 12: Write Paper Page Furniture

The parser writes the `paper_page_furniture.json` artifact that was built before
paper context parsing and table extraction.

This paper-level artifact collects PyMuPDF page text lines with ordinary
whitespace-normalized matching keys, clusters repeated text in stable
page-relative positions, and emits generic ignored regions. A numeric slot gains
an additional `<page_num>` matching key only after recurrent positioned evidence
proves one constant offset from the PDF page sequence; rejected slots remain
ordinary text. Document construction, Markdown filtering, table extraction,
cell text annotation, and document-linked footer detection use those regions
before downstream artifacts are built.

## Step 13: Build Paper-Level Document Context

The parser also builds a paper-level context representation from the whole document.

This is separate from table extraction.

The current paper-context path is:

```text
PDF -> raw positioned evidence -> page furniture and page scope
    -> included-page positioned projection -> canonical discovery blocks
    -> table mentions -> canonical table extraction and geometry
    -> paper_document.json -> paper_sections.json + paper_markdown.md
    -> paper_bibliography.json -> paper_visual_inventory.json
    -> paper_references.json -> paper_style_profile.json
    -> paper_variable_inventory.json -> table_contexts/*.json
```

The canonical discovery blocks are built directly from filtered positioned
evidence. Table mentions, bibliography masks, and the approved prose-line
footer veto use that in-memory state before extraction. After final table
geometry, `paper_document.json` is materialized once from the same blocks and
the established prose-candidate decisions over the flattened layout traversal.
Figure units remain opaque and are skipped during prose identification and
bibliography detection. Bibliography heading discovery, numbered starts,
continuation evidence, and the retained unnumbered route consume the same
ordered ordinary blocks; their accepted item and ownership rules are unchanged.
`paper_sections.json` and `paper_markdown.md` consume its prose segments. The
non-prose paper consumers now use its canonical block text, role, and order and
join block line IDs to `paper_positioned_document.json` only for raw typography
and geometry. There is no separate full-paper text-stream artifact.

### `paper_markdown.md`

This is the prose-only Markdown view rendered from
`PaperDocument.prose.segments`.

It is not the canonical table grid.

It preserves:

- section and subsection headings owned by prose
- sentence-bearing paragraphs in reading order
- narrative references such as `Table 1 shows ...`

It excludes entity and residual blocks. The Markdown file is not a separate
extraction backend or an ownership model; `PaperDocument` is canonical.

### `paper_document.json`

This is the canonical prose/entity/residual ownership projection over the
filtered positioned blocks. Its single block registry preserves each block's
page, source order, line IDs, orientation, columns, and exact geometry. Current
prose-candidate headings open ordered prose segments, and accepted body blocks
become their paragraphs. The established prose rules consume ordinary blocks in
flattened layout-placement order and do not inspect accepted figure members.
Accepted figure and bibliography entities own their component blocks, and every
other retained block is listed in `unassigned_block_ids` without additional
inference. The persisted section and Markdown views consume prose ownership.
Non-prose consumers read canonical block text, role, and order and join source
IDs to positioned evidence without creating another stream.

### `paper_sections.json`

This is the exact ordered `PaperDocument.prose.segments` list. Each segment
stores its ordered `heading_block_ids` and paragraphs; each paragraph stores its
`paragraph_id`, ordered `block_ids`, and text. It performs no separate ownership
or section-role inference.

### `paper_table_mentions.json`

The parser scans the canonical discovery blocks joined to raw positioned lines
for `Table N` mentions before table extraction. Each record keeps the table number,
source line ID and bbox, local context line IDs, source-line text, cue, and
whether the mention is a
`caption_candidate`, `continuation_label`, or `prose_reference`. A continuation
record additionally carries `continuation_role` as `from_previous_page`,
`to_next_page`, or `unspecified`; this controls which side of the label may
contain its table without branching on writing orientation.

This artifact is used as extraction evidence, not as a table source. A line
beginning with `Table 5.` is rejected as a fallback table start when the previous
line makes the sentence read as `... is shown in Table 5.`. Before an unfinished
previous line can provide weaker continuation evidence, its last visible span
and the current line's first visible span must retain the same font and bold
state. A font or bold-state change ends that proposed continuation; this uses
the positioned boundary spans and does not compare point sizes or line gaps.
The positioned line evidence records when any source span is bold, but this
descriptive line-level fact does not assign a heading role or independently
support a caption candidate. A heading requires complete-line bold evidence and
a font strictly larger than the dominant body font; it is never assigned from a
heading-name match. Explicit heading evidence may support a caption
candidate, but it does not by itself create a table. Line-initial
`Table S...` listings under an active `Supplementary Information` heading are
classified as `prose_reference`, not `caption_candidate`, because they describe
external supplementary material rather than an extractable in-paper table.

Table extraction uses these caption candidates together with the same canonical
blocks and their joined positioned geometry. It does not consume preliminary
sections, Markdown, or document ownership.
The provisional grid keeps every physical y-band after the caption-label band;
it does not remove possible continuation text before header geometry is
available. Complete caption binding then matches the label to a table in the
canonical orientation-group frame, groups adjacent source text into physical
y-bands, and extends the caption only through single-run bands. The first band
containing multiple horizontally separated runs establishes the start of the
header; a table rule is an outer geometric limit, not the caption/header
delimiter. The persisted
`ExtractedTable.metadata.caption_region` and `caption_binding` records retain
both page-space and canonical geometry plus source line IDs. This step changes
caption ownership without moving or merging table text. Canonical grid selection
can omit source words owned by the bound caption region; the original positioned
lines and coordinates remain in `paper_positioned_document.json`. This step does
not yet establish body/footer row bands.

### `paper_bibliography.json`

The canonical document builder identifies bibliography entries after physical
layout and provisional prose and before table extraction begins. Independent
item walks start at explicit reference headings and consume whole blocks in
layout order. For numbered lists, an entry start may be a bracketed, dotted, or
bare numeric label; the retained author-year route uses first-author or
organization lines with hanging-indent continuations. Entries may remain open
across block, column, and page breaks until the next accepted start. Accepted
heading and content blocks supply the in-memory extraction mask and later belong
to bibliography entities in the finalized `PaperDocument`; each entry preserves
its contributing source line IDs. The artifact is
per-paper only: it keeps labels and raw/clean entry text as separate entities
without DOI lookup, author normalization, cross-paper deduplication, or any
corpus-level reference store.

The bibliography pass is also the only stage that discovers reference-list
evidence for table extraction. If it finds entries, the parse flow passes
bibliography-owned source-line IDs and entry bboxes into extraction so
references cannot become table-candidate evidence. If it finds no entries, no
bibliography-derived table suppression is applied. Extraction does not run a
separate raw-text `References` detector.

After table extraction and cell text annotation, numeric table-cell markers that
look like bibliography references can be linked to those bibliography entries.
For example, numeric superscripts attached to study/source row labels should be
represented here rather than counted as unresolved table footnotes when no local
table-note definition exists.

### `paper_style_profile.json`

The parser builds a compact style summary from existing paper-level artifacts.

It records:

- likely footnote marker family, with counts by numeric, letter, symbol,
  asterisk, and unknown markers
- likely bibliography/reference-list style, including numbered versus
  unnumbered/hanging-indent lists
- likely table caption placement, using extracted-table caption metadata and
  nearby positioned text lines
- figure caption text evidence, with an explicit note that figure geometry is
  not extracted yet
- prose table/figure reference wording and resolution-status counts

Each dimension keeps `likely_style`, `confidence`, count dictionaries, compact
evidence examples, and notes. The profile also has `checks` that compare the
style inference with parsed artifact reality, including bibliography numbering,
footnote link coverage, caption-placement coverage, figure-geometry
availability, and visual-reference resolution. This gives later
footnote/linking work an inspectable document-style signal without embedding
journal-specific rules in the link resolver.

### `paper_visual_inventory.json`

The parser builds a paper-level inventory of actual in-paper visual objects.

For tables, this starts from extracted table titles and captions and links back to `table_id` when possible.

For figures, the implemented scope is caption inventory from block-derived
text plus a narrow positioned-text case: when a standalone `.gNNN` DOI directly
follows a same-page caption sequence beginning with the matching `Figure/Fig
N` label at the same text origin, that caption is retained as a figure visual.
This does not infer a figure from a prose mention. Figure image extraction is
intentionally separate and can later populate artifact paths without changing
the reference schema.

`PaperVisual.doi` stores the canonical DOI and
`PaperVisual.doi_source_line_id` joins it to the preserved positioned line.
The R paper-output loader carries this inventory, and display code derives the
corresponding `https://doi.org/<doi>` link rather than persisting a redundant
URL.

This inventory is the check that prevents every prose mention of `Figure X` from being treated as an in-paper figure reference.

After references are resolved, each visual is annotated with a reference-check status. Standard in-paper tables and figures should have at least one resolved prose reference outside the visual object itself. Caption-like mentions such as `Table 1. Baseline characteristics` and extracted table-body text do not satisfy this check. Supplementary tables and figures are exempt.

### `paper_references.json`

The parser scans all paper sections for table and figure mentions such as `Table 1`, `Table1`, `Fig. 2`, and compound mentions like `Figures 2A and 2B`.

Each reference keeps a stable reference ID, section and paragraph anchor fields, character offsets, and compact anchor text. By default the anchor text is the sentence containing the mention plus one preceding and one following sentence when available.

References are resolved against `paper_visual_inventory.json` when possible. Mentions that do not match an actual in-paper visual remain explicit as `unresolved` or `external_or_bibliographic` rather than being dropped.

### `paper_variable_inventory.json`

The parser then builds a paper-level candidate reference list of variables.

This artifact records:

- raw mention-level evidence from prioritized prose sections
- variable-like labels harvested from deterministic table definitions
- mentions found in table titles and captions
- conservative merged candidate variables with provenance back to mentions

This is a Phase 1 search artifact, not a final interpretation layer. It is intended to stay easy to inspect in both Python and R.

### `table_contexts/*.json`

For each table, the parser builds a focused context bundle using:

- the section list
- the table title and caption
- variable labels
- grouping labels
- resolved paper-level table reference IDs when available

This produces per-table passages and term lists that can later support standalone review workflows or future semantic interpretation.

## Step 14: Optional Variable-Plausibility LLM Review

The separate `review-variable-plausibility` command can run a narrow LLM review using:

- the deterministic `TableDefinition.variables`
- merged table title/caption text
- attached level labels, units hints, and summary-style hints

This produces `table_variable_plausibility_llm.json`.

Current implemented scope:

- score whether a variable label and `variable_type` fit together
- score whether categorical levels look sensible for the named variable
- preserve the supplied variables exactly and add `plausibility_score`

This command does not rewrite the deterministic table definition.

When `LLM_DEBUG=true`, the review command also writes `llm_variable_plausibility_debug/...`.

Why this stage is optional:

- deterministic structure should do as much as possible first
- LLM use should be focused on ambiguity, not raw PDF recovery
- review calls should be inspectable and skippable

## Step 15: Write Table Processing Status

After deterministic parsing, the parser writes `table_processing_status.json`.

This artifact records:

- the resolved semantic table ID
- the normalized source table IDs that contributed to that status record
- which existing rescue or repair paths were considered
- which ones ran
- source-fragment diagnostics carried forward from parse-quality and resolution artifacts
- whether the table ended as `ok`, `rescued`, or `failed`
- the terminal failure stage and failure reason when rescue was exhausted

If a structurally wide matrix-like real table is outside the current
descriptive/estimate parser routes, status should preserve it as a real table
with an unsupported-route note instead of calling it a non-table layout
artifact. The broader `paper_table_inventory.json` category can then expose it
as `data_presentation` for later family-specific parsing work.

For integrated continuations, status is resolved-table keyed. Source-fragment
warnings remain inspectable through `source_table_ids` and
`source_fragment_diagnostics` rather than becoming separate semantic table
statuses.

## What A Human Should Inspect First

When a parse looks wrong, inspect the outputs in this order.

1. `extracted_tables.json`
   If the raw grid is already wrong, stop here. The problem is extraction.

2. `normalized_tables.json`
   If the raw grid was usable but header rows, edge trimming, split-value repair, or cleaned text are wrong, the problem is normalization.

3. `column_header_schemas.json`
   If the column leaves, p-value/statistic columns, or spanning header groups
   are wrong, inspect this before body value candidates.

4. `body_element_candidates.json`
   If values are split across physical cells or rows, inspect this to see
   whether the logical value candidates preserve the right source fragments and
   bboxes without changing the extracted grid.

5. `body_row_label_candidates.json`
   If row labels are split across physical rows, inspect this to see whether
   logical label candidates preserve the right source fragments and bboxes
   without changing the extracted or normalized grid.

6. `resolved_tables.json`
   If one logical table spans pages, inspect this to see whether fragments were integrated, rejected, or left as singletons, and how resolved rows map back to source table rows.

7. `table_continuation_column_checks.json`
   If a source fragment has explicit or narrow inferred continuation evidence, inspect this to see whether the normalized column count and schema-derived column headers are compatible.

7. `table1_continuation_groups.json`, `merged_table1_tables.json`, and `continued_variable_integrations.json`
   Inspect these older review artifacts when you need a source-fragment view of continuation candidates, merged rows, or boundary reinterpretation evidence.

8. `table_profiles.json`
   If the table was routed to the wrong family, the problem is in routing.

9. `paper_table_inventory.json`
   If a table is assigned to the wrong broad category, inspect this artifact's chosen category, confidence, and evidence.

10. `table_definitions.json`
   If row meanings or column meanings are wrong, the problem is in the semantic heuristics.

11. `parsed_cell_values.json`
   If the printed cell components are wrong before semantic labels are attached, the problem is in source-cell value parsing.

12. `parsed_tables.json`
   If source-cell components and row/column meanings are right but the final values are wrong, the problem is in the semantic value join.

13. `table_processing_status.json`
   If a table is empty or incomplete, inspect this next to see which rescue paths were attempted and where failure was recorded.

14. `parse_quality_reports.json`
   If the parse succeeded but the columns, p-values, headers, or row classifications look suspicious, inspect this artifact for deterministic quality warnings.

15. `paper_footnotes.json`
   If superscripts, subscripts, or note markers matter, inspect this artifact for detected table-local footer regions, anchors, candidate definitions, math/unit suppression metadata, and resolved, ambiguous, inferred, or unresolved glyph-key links.

16. `paper_bibliography.json`
   If numeric study/source markers look like bibliography references, inspect this artifact for the paper's fixed reference-list entries, observed marker links, and per-paper coverage diagnostics.

17. `paper_page_furniture.json`
   If repeated page headers, footers, watermarks, or download notices may be contaminating extraction or note parsing, inspect this artifact for recurring clusters and ignored regions.

18. `paper_positioned_document.json`, `paper_document.json`, `paper_markdown.md`, `paper_sections.json`, `paper_visual_inventory.json`, `paper_references.json`, `paper_variable_inventory.json`, and `table_contexts/*.json`
   If semantic context retrieval is weak, inspect these next.

19. `table_variable_plausibility_llm.json`
   If deterministic variables were reasonable but the plausibility review looks wrong, the issue is in prompting, provider behavior, or validation for the standalone review command.

## Why This Pipeline Shape Is Worth Keeping

The system is intentionally not "PDF in, one JSON out."

The multiple stages are not accidental complexity. They are what make the parser inspectable and research-friendly.

This separation gives the project:

- raw extraction provenance
- parser-facing structural cleanup
- resolved continuation provenance plus source-fragment continuation inspection
- explicit routing for mixed-table papers
- value-free semantics before value parsing
- optional standalone variable plausibility review
- deterministic parse-quality diagnostics
- easier debugging when a paper fails in only one part of the pipeline

That is the main reason the project can support both engineering work and research iteration without collapsing all errors into one opaque final output.
