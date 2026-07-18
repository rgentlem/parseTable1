# Paper Document Plan and Contract

## Status and Goal

This document records the approved destination for partitioning a paper into
its narrative content and other document entities. It is a schema and artifact
contract, not blanket approval to change parser logic.

Step 3 now writes `paper_document.json`
directly from the existing filtered blocks and established prose-candidate
decisions, leave entities empty, and assign every other block to residual.
`paper_sections.json` is the prose segment list and `paper_markdown.md` renders
only those segments. Existing non-prose consumers now take canonical text,
block role and order from `PaperDocument`, joining referenced positioned lines
only for raw typography and geometry. The former `PaperTextStream` model,
builder, renderer, JSON artifact, and provenance labels have been retired.

`PaperDocument` replaces `PaperTextStream` as the canonical
interpreted paper artifact. It must represent the paper once, with explicit and
disjoint ownership of every retained positioned block.

The intended relationship is:

```text
PaperPositionedDocument       immutable PDF text and geometry evidence
          |
PaperPageFurniture            ignored recurring page furniture
          |
PaperDocument                 canonical interpreted block ownership
          |-- prose           narrative paper content in reading order
          |-- entities        tables, figures, boxes, bibliography, supplements
          `-- residual        unresolved blocks retained without guessing
```

Do not add `PaperReadingOrder`, a second full-paper stream, or another parallel
ownership artifact. Human-readable files and specialized inventories must be
views over `PaperDocument` or linked canonical artifacts.

## Raw Extraction Evidence and Canonical Document

`PaperPositionedDocument` remains the source of truth for raw PDF evidence:
page dimensions, lines, spans, characters, source text, font evidence, writing
direction, rules, and exact PDF coordinates. It preserves what the extractor
reported, including imperfect source grouping or text. Accepted document
corrections do not overwrite or remove that evidence.

`PaperDocument` is the corrected canonical representation of the paper. It is
not required to reproduce an incorrect source-block grouping or extracted text
unchanged. It is the source of truth for:

- the current canonical block text and role;
- which blocks are narrative prose;
- the paragraph and section/subsection reading order of that prose;
- which blocks belong to document entities;
- which entity component owns each block;
- which blocks remain unresolved.

Every divergence from raw extraction must remain traceable through source block,
line, span, or character evidence. Consumers use `PaperDocument` for canonical
text, structure, order, and ownership. They follow its source references into
`PaperPositionedDocument` only for raw text, typography, characters, rules, and
original PDF geometry; they must not silently reconstruct the canonical paper
from raw positioned lines and thereby bypass accepted corrections.

## Minimal Declarative Shape

The shapes below declare the required information and ownership relationships;
they do not prescribe Pydantic, a class hierarchy, or a separate implementation
object for every nested shape. Use the smallest representation that preserves
this contract in Python and has a clear equivalent in R. JSON is the transport
format.

```text
PaperDocument
  paper_id
  source_pdf
  pages
  blocks
  prose
  entities
  unassigned_block_ids
```

### Pages

Each page record preserves the page-local frame needed to interpret block
geometry:

```text
PaperDocumentPage
  page_num
  width
  height
  orientation_groups
```

Orientation groups retain their canonical dimensions, column bands, and column
boundaries. Canonical coordinates are comparable only within their declared
orientation group. Page-space coordinates remain authoritative for proximity
to visual objects, rules, captions, and other blocks.

### Blocks

`PaperDocument.blocks` is the single filtered block registry. Each retained
block is the current ownership unit derived from positioned source evidence and
must preserve at least:

```text
PaperDocumentBlock
  block_id
  page_num
  source_block_index
  role
  bbox
  canonical_bbox
  orientation
  orientation_group_id
  column_index
  column_count
  line_ids
  text
```

Every block keeps its exact page-space bbox. Its ordered line IDs link back to
the complete line, span, font, and character evidence in
`PaperPositionedDocument`. Do not duplicate detailed typography on the block.
`text` is the current canonical block text, not a promise that the extractor's
source text was correct. `role` preserves the accepted structural role needed
by later consumers.

More than one document block may retain the same `source_block_index` when a
positioned source block is split. `block_id` is unique; `source_block_index` is
provenance and is not required to be unique.

Page furniture removed through `PaperPageFurniture` does not enter this block
registry and receives no document owner.

## Block Refinement and Component Assembly

PDF source blocks are layout evidence, not guaranteed final ownership units.
The atomic migration preserves the existing line-refined block projection and
assigns each block initially to prose or residual. A residual block may still
contain fragments belonging to a caption, heading, or another entity component.
Before part of such a block receives more specific ownership, it must pass the
narrow refinement step below.

### Splitting mixed source blocks

Split a residual document block only when direct positioned evidence establishes
a role boundary within it. The initial operation is deliberately limited to
boundaries between complete source lines. Evidence may include:

- a confirmed heading-to-body role transition;
- an exact font family, weight, size, or writing-direction transition;
- a column, orientation-group, drawn-rule, or visual-object boundary; or
- another explicit transition already represented in positioned evidence.

Do not split from expected wording, subject vocabulary, caption labels, or
downstream semantic preference. A source block containing a heading line and
later body lines becomes two document blocks with unique block IDs, the same
source-block provenance, disjoint ordered line IDs, and separately computed
exact bboxes and text.

The initial schema does not split within one positioned line. If different
roles are mixed inside a line, keep that material residual until a demonstrated
case justifies an explicit span-level contract. Do not make two document blocks
claim the same line ID.

Before an approved split changes the block registry, expose it as non-operative
evidence:

```text
PaperBlockSplitProposal
  block_id
  proposed_parts
  structural_evidence

PaperBlockSplitPart
  line_ids
```

Each proposed part must contain a non-empty contiguous range of the target
block's lines. Taken together, the parts must reproduce all target lines once,
in source order, without changing their text. An accepted split atomically
replaces the target residual block with its proposed parts in the block registry
and `unassigned_block_ids`; assigning a refined part to an entity remains a
separate ownership decision.

### Consolidating fragmented components

Consolidation is logical assembly, not a physical merge of document blocks.
Paragraphs, multi-line headings, captions, and entity content or footers own an
ordered list of refined block IDs. Each block retains its own page, bbox, source
provenance, and line IDs.

```text
PaperComponentAssemblyProposal
  component_role
  block_ids
  structural_evidence
```

Assembly requires compatible page-local evidence: page and orientation,
consecutive source or established reading order, column or spanning-layout
membership, typography, intervening blocks, and visual or rule boundaries.
Cross-page assembly is limited to an explicit continuation onto an adjacent
page. Uncertain fragments remain residual rather than being joined by text
similarity or expected meaning.

The same assembly rule applies to prose and entities:

- a paragraph already owns one or more ordered block IDs;
- a section or subsection heading owns one or more ordered block IDs;
- an entity component already owns one or more ordered block IDs.

Split proposals and assembly proposals are review evidence, not parallel owners
and not a second document model. Once accepted, only the refined blocks and
their canonical `PaperDocument` ownership remain authoritative.

### Correcting extracted text

Canonical block text may differ from extracted text when direct source evidence
or an explicit reviewed correction establishes an extraction error. The raw
text remains unchanged in `PaperPositionedDocument`; the canonical block keeps
the source IDs needed to inspect it and explicit correction provenance for the
changed text. Do not create a corrected positioned-document copy.

Text correction is distinct from structural refinement:

- splitting changes which source lines form a block;
- assembly changes which blocks form a logical component;
- ownership changes where a block belongs;
- text correction changes canonical text while retaining the original source
  evidence.

Do not define a general correction schema before reviewing the first real
typographic cases. The demonstrated requirements are only that the source value
remain available, the canonical value be explicit, and the correction identify
its source evidence and basis.

Table-cell typography follows the same preservation rule inside the specialized
table artifacts: retain raw extracted cell text, allow an evidence-backed
canonical value, and record the correction there. `PaperDocument` owns the
table's document components and artifact link; it does not duplicate or repair
the table grid itself. Future figure extraction follows the same separation:
the figure entity owns caption and component blocks while linked extracted
figure evidence owns the image or vector geometry.

### Refinement invariants

- Every retained source line occurs in exactly one refined document block.
- Structural refinement does not invent, delete, duplicate, or reorder source
  text. An accepted text correction changes only canonical text and leaves its
  raw source evidence intact.
- Each refined bbox is the exact union of its referenced source lines.
- Physical consolidation never replaces page-local blocks with combined text
  or an ambiguous bbox.
- Every refined block is owned exactly once by prose, an entity component, or
  `unassigned_block_ids`.
- A split or assembly that cannot satisfy these invariants fails closed and
  leaves the affected material residual.

## Prose Contract

Prose means the narrative content of the paper: sentence-bearing abstract and
main-body paragraphs, including genuine narrative references such as
`Table 1 shows ...`.

Prose excludes captions, entity content, entity footers or notes,
bibliography entries, supplementary objects, running page furniture, author
and journal metadata, licences, and unresolved material.

```text
PaperProse
  segments

PaperProseSegment
  segment_id
  heading_block_ids
  paragraphs

PaperParagraph
  paragraph_id
  block_ids
  text
```

A segment corresponds to a section or subsection. Its ordered heading block IDs
allow a fragmented heading to be assembled without erasing block provenance.
The heading is structural ownership, not a prose paragraph. Paragraph block IDs
define reading order; stored paragraph text must be a deterministic assembly of
those blocks and must validate against them exactly.

Each accepted prose block belongs to exactly one heading or paragraph. Later
table, figure, footer, bibliography, or supplementary processing may not remove
or reclaim it.

## Entity Contract

Entities are first-class parts of the canonical paper, not text mixed into
prose and not merely display records.

`PaperDocument.entities` is the canonical source for the existence, kind,
scope, page-local location, component ownership, and structured-content links
of every established table, figure, box, bibliography, and supplementary
object.

```text
PaperEntity
  entity_id
  kind
  scope
  components

PaperEntityComponent
  role
  block_ids
  content_refs

PaperEntityContentRef
  artifact_kind
  artifact_id
```

Initial entity kinds are:

```text
table
figure
box
bibliography
supplementary_data
```

Entity scope is `main` or `supplementary`. A supplementary table is therefore
a `table` entity with supplementary scope, not a different table schema.

Initial component roles are:

```text
heading
caption
content
footer
```

Components own ordered block IDs. Their page and geometry come from the block
registry rather than being copied into a second source of truth.

Structured content remains canonical in its specialized artifact:

- table content references one or more `ExtractedTable` records and does not
  duplicate the grid;
- figure content references direct figure geometry or image artifacts;
- bibliography content references structured bibliography entries;
- supplementary content references its structured artifact when one exists.

Captions and footer/note text belong to their entity components and never enter
prose-derived sections or Markdown.

## Ownership and Coverage Invariants

Ownership is declared only by the ordered block references in prose segments,
entity components, and `unassigned_block_ids`. Do not duplicate an independent
owner field on each block.

For the retained block registry:

```text
prose block IDs
union entity block IDs
union unassigned block IDs
= all PaperDocument block IDs
```

Those three sets must be pairwise disjoint. Every accepted line must also occur
exactly once through its owning block. A conflict is a structured validation
failure; no owner silently overrides another.

The parser should make a strong general geometry-based effort to resolve
residual blocks. When direct evidence remains insufficient, the block stays in
`unassigned_block_ids` rather than being guessed into prose or an entity.

## Geometry and Proximity Contract

Every proposed paragraph or entity link must be validated against the
referenced blocks' page-local evidence. Relevant structural evidence includes:

- page and orientation-group identity;
- exact page-space and canonical bboxes;
- source block and line order;
- observed column or spanning-layout membership;
- intervening blocks;
- drawn-rule, image, and visual-object boundaries;
- exact typography transitions already present in positioned evidence.

Same-page, same-orientation ownership is the default. Cross-page ownership is
allowed only for an explicit continuation onto an adjacent page. A multi-page
entity preserves its separate page-local blocks; it must not replace them with
one ambiguous document-wide bbox.

This contract does not itself authorize a new numeric layout tolerance.

## Contracts With Current Pipeline Artifacts

### `PaperPageFurniture`

Page-furniture filtering occurs before `PaperDocument` blocks and ownership are
built. Repeated headers, footers, watermarks, and similar ignored regions must
not be removed later from prose or entities by string cleanup.

### Retired `PaperTextStream`

`PaperTextStream`, `paper_text_stream.json`, and their exclusive loaders and
renderers are retired. Consumers needing all filtered blocks use
`PaperDocument.blocks`; they do not retain a second stream. Consumers take
canonical text, block role, order, and ownership from `PaperDocument` and may
join its source IDs to
`PaperPositionedDocument` for detailed raw evidence. Reading positioned lines
directly as the document would ignore accepted splits, assemblies, ownership,
and text corrections.

### Sections and Markdown

`paper_sections.json` is a structured view of `PaperDocument.prose.segments`.
`paper_markdown.md` is a prose-only view of the same segments and paragraphs.
Neither view may independently infer ownership or include entity or residual
blocks.

### Table and Caption Processing

Pre-extraction layout consumers may inspect the canonical block registry and
unassigned blocks, but they may not offer frozen prose as a caption or table
component. Once a table entity is established, `PaperDocument` owns its
caption/content/footer relationship while `ExtractedTable` remains the
canonical physical grid.

Table regions, boundary proposals, continuation resolution, and semantic table
artifacts must reference the table entity or its linked table IDs. They must
not establish a competing caption or footer owner.

### Figures, Boxes, and Visual Inventory

Figure and box entities require direct positioned, rule, image, or visual-bound
evidence. Existing visual-inventory outputs become derived views or are
atomically aligned with `PaperDocument.entities`; they do not remain a second
ownership system.

### Bibliography

The bibliography is an entity, not prose. Its heading and entry blocks are
owned by bibliography components, and its content references the structured
bibliography artifact. Bibliography detection may continue early enough to
protect table extraction, but its final block ownership lives in
`PaperDocument`.

### Footnotes and Entity Footers

Table and figure notes, marker definitions, and other local footers consume the
entity footer component. A footnote or footer claim that overlaps frozen prose
must fail validation rather than remove the prose.

### References, Variable Inventory, and Table Context

Prose visual-reference collection, paper-variable search, and narrative table
context consume `PaperDocument.prose`. Explicit structured table evidence may
be added through linked table entities. Caption, footer, bibliography, and
unassigned text must not enter these prose-derived inputs accidentally.

### Future LLM Review

No LLM participates in the current geometry-first partition. A later LLM stage
may receive only unassigned block groups plus their page-local geometry and may
return structured ownership proposals. Deterministic validation must reject
non-proximal links, invented blocks, or any proposal that overlaps frozen prose
or established entity ownership.

## Atomic Migration and Implementation Order

The implementation should proceed through the existing partition checklist:

1. Atomically replace `PaperTextStream` with the minimal `PaperDocument`,
   reusing the current filtered positioned-block evidence and prose-candidate
   decisions without a second PDF pass or a new classification rule.
2. Populate `PaperDocument.prose` from the established prose candidates, place
   every other retained block in `unassigned_block_ids`, and make sections and
   Markdown exact prose-only views. Retire `PaperTextStream`, its persisted
   artifact, and its exclusive consumers in the same migration. Completed in
   Step 3.
3. Inspect every residual block with its page-local evidence. Expose proposed
   line-boundary splits, component assemblies, and ownership changes as
   non-operative evidence before they alter the canonical partition.
4. Resolve residual blocks into entity components using direct geometry,
   initially identifying captions and then tables, figures, boxes,
   bibliography, and supplementary material. Leave unsupported assignments
   residual.
5. Align specialized consumers and inventories to `PaperDocument` ownership.

Step 3 of the partition checklist performs the atomic artifact migration and
establishes initial prose and residual ownership without changing the current
classifier. Step 4 works through that residual registry and populates entity
ownership. Until the entity stage is complete, unassigned blocks remain
explicit and preserved; the parser must not claim that the paper is fully
partitioned.

## Acceptance Conditions

- Every retained block and line is accounted for exactly once.
- Every split is line-preserving, source-ordered, and traceable to one positioned
  source block.
- Every canonical text correction preserves and identifies its raw source
  evidence and correction basis.
- Every block preserves page identity and exact page-local geometry.
- Prose paragraphs are sentence-bearing and ordered by section/subsection.
- Captions, entity content, footers, bibliography, and supplements are absent
  from prose.
- Tables, figures, boxes, bibliography, and supplementary material are
  represented as entities with distinct components.
- Entity links are page- and geometry-compatible or explicit adjacent-page
  continuations.
- Sections and Markdown exactly match prose ownership.
- Structured table grids and other specialized artifacts are linked, not
  duplicated.
- Consolidated paragraphs, headings, and entity components retain their ordered
  constituent block IDs and page-local geometry.
- Later entity owners cannot reclaim frozen prose.
- Unresolved material remains inspectable without guessing.
