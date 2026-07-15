# Paper Visual References

This document defines the planned design for collecting table and figure references from a paper in a way that helps a reader identify the referenced object and access nearby explanatory text.

This is a document-context capability. It must remain separate from table extraction, table normalization, deterministic table parsing, and LLM interpretation.

## Motivation

Readers often need to answer questions such as:

- where does the paper discuss Table 1?
- what nearby text explains a figure?
- does a prose mention such as `Figure 2` refer to a figure in this paper or to another cited paper?
- what caption belongs to a figure, even before figure-image extraction exists?

The current paper-context path persists `paper_positioned_document.json`,
`paper_text_stream.json`, `paper_markdown.md`, `paper_sections.json`, and
per-table context bundles. The visual-reference capability should extend that
path with explicit visual-object and visual-reference artifacts instead of
embedding this logic inside the table parser.

## Conceptual Flow

The planned document-context flow is:

```text
paper_positioned_document.json
  -> paper_text_stream.json
  -> paper_markdown.md
  -> paper_sections.json
  -> paper_visual_inventory.json
  -> paper_references.json
  -> table_contexts/*.json
```

`paper_visual_inventory.json` records visual objects that appear to exist in the paper.

`paper_references.json` records prose references to tables and figures.

`table_contexts/*.json` may link to relevant reference IDs, but the canonical reference inventory remains paper-level.

## Design Principles

- Collect all table and figure references found in the paper text, not only references to Table 1.
- Resolve references against an inventory of actual in-paper visual objects before treating them as in-paper references.
- Preserve unresolved references rather than silently dropping them.
- Extract figure captions at least, even before figure image extraction is implemented.
- Keep figure image extraction optional and additive.
- Store stable IDs so Python, R, and later UI workflows can join artifacts reliably.
- Store anchor coordinates first; variable-sized text windows can be requested or computed later.
- Keep JSON as the transport format, while treating the objects as explicit schema-level concepts.

## Visual Inventory

The visual inventory is a paper-level list of actual tables and figures detected in the paper.

Planned output path:

```text
outputs/papers/<paper_stem>/paper_visual_inventory.json
```

Canonical model concept:

```text
PaperVisual
```

Planned fields:

- `visual_id`
- `visual_kind`
- `label`
- `number`
- `caption`
- `caption_source`
- `page_num`
- `artifact_path`
- `source_table_id`
- `source`
- `confidence`
- `text_reference_ids`
- `reference_check_status`
- `reference_check_notes`
- `notes`

Optional visual-identity fields:

- `doi`
- `doi_source_line_id`

### Visual-object DOI

A standalone DOI printed with a table or figure is part of that visual's
caption metadata and persistent identity. It should be stored on the existing
`PaperVisual` record, beside `caption`, for both tables and figures. The source
line remains unchanged in `paper_text_stream.json`, and
`doi_source_line_id` preserves the direct join to that positioned evidence.

Store the canonical DOI value, for example
`10.1371/journal.pone.0010746.t001`, rather than a publisher URL. Python and R
display code can derive a clickable link as
`https://doi.org/10.1371/journal.pone.0010746.t001`.

Attachment fails closed. Accept only a complete standalone DOI whose terminal
object suffix identifies a table or figure, such as `.t001` or `.g002`, and
require that the decoded kind and number match exactly one `PaperVisual`. A
table DOI attaches only to an existing extracted-table visual. If a figure
caption was missed by the markdown-caption path, a figure DOI may materialize
that same `PaperVisual` schema only when the immediately preceding positioned
text is one same-page caption sequence beginning with the exact matching
`Figure/Fig N` label and sharing the DOI line's text origin. This is caption
inventory from direct PDF evidence, not inference from a prose figure mention.
Article-level, bibliography, dataset, and supplement DOIs remain in the
positioned text stream but are not assigned to a visual. The DOI line is visual
metadata, not part of a table footnote definition.

`visual_kind` should be:

- `table`
- `figure`

Example table visual:

```json
{
  "visual_id": "paper_visual:table:1",
  "visual_kind": "table",
  "label": "Table 1",
  "number": "1",
  "caption": "Baseline characteristics of the study population.",
  "caption_source": "extracted_table",
  "page_num": 4,
  "artifact_path": null,
  "source_table_id": "tbl-1",
  "doi": "10.1371/journal.pone.0010746.t001",
  "doi_source_line_id": "page-6-line-188",
  "source": "table_extraction",
  "confidence": 0.95,
  "text_reference_ids": ["paper_ref:section_4:p2:r0"],
  "reference_check_status": "referenced_in_text",
  "reference_check_notes": [],
  "notes": []
}
```

Example figure visual:

```json
{
  "visual_id": "paper_visual:figure:2",
  "visual_kind": "figure",
  "label": "Figure 2",
  "number": "2",
  "caption": "Flow diagram for study inclusion.",
  "caption_source": "markdown_caption",
  "page_num": 6,
  "artifact_path": null,
  "source_table_id": null,
  "source": "markdown_caption",
  "confidence": 0.8,
  "text_reference_ids": [],
  "reference_check_status": "no_text_reference",
  "reference_check_notes": ["no_non_self_text_reference_found"],
  "notes": []
}
```

For tables, the inventory should initially be built from extracted table titles and captions when available, with markdown captions as a fallback or supplement.

For figures, the first implementation should detect captions from markdown or PDF text. The caption inventory should exist before image extraction is implemented.

## Figure Images

Figure image extraction is a later additive capability.

When implemented, figure image artifacts should live under the same paper output directory:

```text
outputs/papers/<paper_stem>/figures/figure_2.png
```

The `artifact_path` field in `PaperVisual` should point to the image path relative to the paper output directory.

The visual inventory schema should not need to change when image extraction is added.

Figure images should be treated as figure artifacts, not as markdown replacements and not as table grids.

## Paper References

Paper references are prose mentions of visual objects, such as:

- `Table 1`
- `Table1`
- `Tables 1 and 2`
- `Figure 2`
- `Fig. 2`
- `Figs. 2A and 2B`

Planned output path:

```text
outputs/papers/<paper_stem>/paper_references.json
```

Canonical model concept:

```text
PaperVisualReference
```

Planned fields:

- `reference_id`
- `reference_kind`
- `reference_label`
- `reference_number`
- `matched_text`
- `section_id`
- `heading`
- `role_hint`
- `paragraph_index`
- `start_char`
- `end_char`
- `anchor_text`
- `resolved_visual_id`
- `resolution_status`
- `resolution_notes`

`reference_kind` should be:

- `table`
- `figure`

`resolution_status` should be:

- `resolved`
- `unresolved`
- `external_or_bibliographic`
- `ambiguous`

## Visual Reference Check

Every in-paper table and figure should normally be referenced from prose outside the visual object itself.

The parser should therefore annotate each `PaperVisual` with:

- `text_reference_ids`
- `reference_check_status`
- `reference_check_notes`

`reference_check_status` should be:

- `referenced_in_text`
- `no_text_reference`
- `supplementary_exempt`
- `not_checked`

Only resolved references should count toward `text_reference_ids`.

Caption-like and table-body self mentions should not count as supporting text references. Examples that should not satisfy the check include:

- `Table 1. Baseline characteristics...`
- `Figure 2. Study flow diagram...`
- table markdown or extracted table text that contains its own table label

Prose references should count, for example:

- `Baseline characteristics are shown in Table 1.`
- `The study flow is summarized in Figure 2.`

Supplementary tables and figures are exempt because they may be listed only in supplementary material. A visual should be treated as supplementary when its number starts with `S` or its label/caption clearly includes terms such as `supplementary` or `supplemental`.

This check is an observability signal. It should not make `table1-parser parse` fail.

Example resolved reference:

```json
{
  "reference_id": "paper_ref:section_4:p2:r0",
  "reference_kind": "figure",
  "reference_label": "Figure 2",
  "reference_number": "2",
  "matched_text": "Figure 2",
  "section_id": "section_4",
  "heading": "Results",
  "role_hint": "results_like",
  "paragraph_index": 2,
  "start_char": 42,
  "end_char": 50,
  "anchor_text": "The study selection process is shown in Figure 2.",
  "resolved_visual_id": "paper_visual:figure:2",
  "resolution_status": "resolved",
  "resolution_notes": []
}
```

Example unresolved or external reference:

```json
{
  "reference_id": "paper_ref:section_12:p8:r0",
  "reference_kind": "figure",
  "reference_label": "Figure 1",
  "reference_number": "1",
  "matched_text": "Figure 1",
  "section_id": "section_12",
  "heading": "References",
  "role_hint": "references_like",
  "paragraph_index": 8,
  "start_char": 83,
  "end_char": 91,
  "anchor_text": "Smith et al. reported a similar association in Figure 1.",
  "resolved_visual_id": null,
  "resolution_status": "external_or_bibliographic",
  "resolution_notes": ["reference_found_in_references_like_section"]
}
```

## Reference Resolution

References should be resolved deterministically against `paper_visual_inventory.json`.

Normalization should handle common variants:

- `Table 1`, `TABLE 1`, and `Table1` normalize to `table:1`
- `Fig. 2`, `Figure 2`, and `FIGURE 2` normalize to `figure:2`
- simple letter suffixes such as `Figure 2A` normalize to `figure:2A`

A reference should be marked `resolved` only when it matches an actual visual object in the paper visual inventory.

If the reference appears in a references-like section, bibliography entry, or citation context and does not resolve to an in-paper visual, it should be marked `external_or_bibliographic`.

If the label is detected but no matching in-paper visual exists, it should be marked `unresolved`.

If multiple possible in-paper visuals match, it should be marked `ambiguous` and preserve candidate IDs in `resolution_notes` until a more explicit schema field is needed.

Resolution should not use an LLM. Later LLM workflows may consume resolved references, but they should not be required to determine whether a reference exists.

## Anchor-First Text Model

The default anchor should be compact: the sentence containing the reference plus one preceding and one following sentence when available.

Required anchor fields:

- `section_id`
- `paragraph_index`
- `start_char`
- `end_char`
- `anchor_text`

This keeps `paper_references.json` and `table_contexts/*.json` readable by default while preserving enough location information for later tools to compute different regions on demand:

- matched sentence
- same paragraph
- previous/current/next paragraph
- full section
- N characters before and after
- page-level text if page anchors become available

Do not hardcode one context-window size into the canonical artifact.

## Stable IDs

Visual IDs should be deterministic from kind and canonical label when possible:

```text
paper_visual:table:1
paper_visual:figure:2
paper_visual:figure:2A
```

Reference IDs should be deterministic from document location:

```text
paper_ref:<section_id>:p<paragraph_index>:r<reference_index>
```

`reference_index` is the zero-based order of visual-reference matches within that paragraph after deterministic scanning.

IDs should not depend on output array position alone.

## Relationship To Table Contexts

Per-table context files should remain focused table-support bundles.

They may include links to paper-level references:

```json
{
  "table_id": "tbl-1",
  "table_index": 0,
  "table_label": "Table 1",
  "reference_ids": ["paper_ref:section_4:p2:r0"],
  "resolved_visual_ids": ["paper_visual:table:1"]
}
```

The full `PaperVisualReference` records should remain in `paper_references.json`.

Embedding a compact copy in `table_contexts/*.json` is optional convenience behavior, but the paper-level artifact should be the canonical source.

## Relationship To Existing Artifacts

`paper_positioned_document.json` and `paper_text_stream.json` remain the
structured document-context artifacts. `paper_markdown.md` is a rendered view of
the filtered text stream.

`paper_sections.json` remains the structured section view.

`paper_variable_inventory.json` remains the variable-search artifact.

`table_contexts/*.json` remain per-table retrieval bundles.

The visual-reference artifacts should not replace any of these.

They add:

- `paper_visual_inventory.json`
- `paper_references.json`
- optional `figures/*.png` files later

## Implementation Phases

### Phase 1: Design And Schemas

- Add explicit Pydantic models for `PaperVisual` and `PaperVisualReference`.
- Add tests for schema serialization.
- Document output paths and field intent.

### Phase 2: Deterministic Caption Inventory

- Build table visuals from extracted table titles and captions.
- Detect figure captions from markdown or PDF text.
- Write `paper_visual_inventory.json`.
- Preserve unresolved or low-confidence caption candidates with notes where useful.

### Phase 3: Deterministic Reference Collection

- Scan paper sections for table and figure reference mentions.
- Write `paper_references.json`.
- Resolve references against the visual inventory.
- Mark unresolved, bibliographic, and ambiguous references explicitly.

### Phase 4: Context Integration

- Add `reference_ids` and `resolved_visual_ids` to table context bundles.
- Update R inspection helpers to show references and anchor text.
- Keep canonical reference details paper-level.

### Phase 5: Figure Image Artifacts

- Extract figure image regions when feasible.
- Write image files under `figures/`.
- Populate `artifact_path` in `paper_visual_inventory.json`.
- Keep caption-only figure records valid when image extraction is unavailable.

## R Consumption

R helpers should expose paper references without requiring users to manually inspect JSON.

Planned helper behavior:

- list all detected in-paper visual objects
- list all references, optionally filtered by `table`, `figure`, label, or resolution status
- print anchor text for each reference
- show table context with linked reference IDs
- later, display figure image paths when `artifact_path` is available

The R-side representation should preserve IDs exactly as written in JSON.

## Open Questions

- Whether supplementary labels such as `Supplementary Figure 1` should be modeled as a separate visual namespace or as a `label_prefix` field.
- Whether compound references such as `Figures 1 and 2` should produce one reference record per resolved visual or one parent record with multiple targets. The initial recommendation is one record per target so joining remains simple.
- Whether table continuations should share the same visual ID as the base table or have child visual IDs. The initial recommendation is one canonical `paper_visual:table:<n>` with notes or source table IDs for continuations.
- Whether page numbers for figure captions can be reliably recovered from the markdown source alone. If not, page numbers should remain nullable until PDF-layout support is added.
