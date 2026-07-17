# Paper Visual References Implementation Plan

## Goal

Implement paper-level visual-object and visual-reference artifacts that help a reader find table and figure mentions, verify whether those mentions refer to visuals in the same paper, and use stable anchors to retrieve nearby text.

Design reference:

- `docs/design/paper_visual_references.md`

This capability is document-context infrastructure. It must not change table extraction, normalization, deterministic table definitions, parsed values, LLM behavior, or table-processing status except by adding new inspectable artifacts.

## Planned Outputs

Add these parse artifacts:

```text
outputs/papers/<paper_stem>/paper_visual_inventory.json
outputs/papers/<paper_stem>/paper_references.json
```

Later, when figure image extraction is implemented, add:

```text
outputs/papers/<paper_stem>/figures/figure_<n>.png
```

The image artifacts are not part of the first implementation pass.

## Files To Add

Core Python:

- `table1_parser/schemas/paper_visual_references.py`
- `table1_parser/context/visual_inventory.py`
- `table1_parser/context/visual_references.py`

Tests:

- `tests/test_paper_visual_references.py`

Docs:

- update `docs/design/parsing_output_design.md`
- update `docs/design/paper_markdown_spec.md`
- update `docs/design/paper_parse_walkthrough.md`
- update `docs/r_visualization.md`

## Files To Update

Core Python:

- `table1_parser/schemas/__init__.py`
- `table1_parser/context/__init__.py`
- `table1_parser/cli.py`

R inspection:

- `R/inspect_paper_outputs.R`

Tests:

- `tests/test_cli.py`
- `tests/test_schemas.py`
- `tests/test_r_inspection.py`

## Implementation Phases

### Phase 1: Schemas Only

Add explicit Pydantic schemas without wiring them into the CLI yet.

Models:

- `PaperVisual`
- `PaperVisualReference`

Suggested literals:

```python
VisualKind = Literal["table", "figure"]
VisualCaptionSource = Literal[
    "extracted_table",
    "markdown_caption",
    "pdf_caption",
    "figure_image",
    "unknown",
]
VisualReferenceResolutionStatus = Literal[
    "resolved",
    "unresolved",
    "external_or_bibliographic",
    "ambiguous",
]
```

`PaperVisual` fields:

- `visual_id: str`
- `visual_kind: VisualKind`
- `label: str`
- `number: str`
- `caption: str | None = None`
- `caption_source: VisualCaptionSource = "unknown"`
- `page_num: int | None = None`
- `artifact_path: str | None = None`
- `source_table_id: str | None = None`
- `source: str | None = None`
- `confidence: float | None = Field(default=None, ge=0.0, le=1.0)`
- `text_reference_ids: list[str] = Field(default_factory=list)`
- `reference_check_status: VisualReferenceCheckStatus = "not_checked"`
- `reference_check_notes: list[str] = Field(default_factory=list)`
- `notes: list[str] = Field(default_factory=list)`

`PaperVisualReference` fields:

- `reference_id: str`
- `reference_kind: VisualKind`
- `reference_label: str`
- `reference_number: str`
- `matched_text: str`
- `section_id: str | None = None`
- `heading: str | None = None`
- `role_hint: SectionRoleHint = "other"`
- `paragraph_index: int = Field(ge=0)`
- `start_char: int = Field(ge=0)`
- `end_char: int = Field(ge=0)`
- `anchor_text: str`
- `resolved_visual_id: str | None = None`
- `resolution_status: VisualReferenceResolutionStatus = "unresolved"`
- `resolution_notes: list[str] = Field(default_factory=list)`

Tests:

- schemas instantiate and serialize cleanly
- invalid `confidence`, negative indexes, and invalid literals fail validation
- optional fields serialize as JSON-compatible nulls

### Phase 2: Canonical Label Normalization

Implement deterministic label normalization in `table1_parser/context/visual_references.py`.

Required behavior:

- `Table 1`, `TABLE 1`, and `Table1` normalize to `table:1`
- `Fig. 2`, `Figure 2`, and `FIGURE 2` normalize to `figure:2`
- simple suffixes such as `Figure 2A` normalize to `figure:2A`
- canonical display labels should be `Table <number>` or `Figure <number>`

Keep this logic local to the visual-reference context module unless it is reused by another module.

Tests:

- table variants
- figure variants
- case-insensitivity
- suffix labels
- invalid strings return `None` or an explicit no-match object rather than raising

### Phase 3: Table Visual Inventory

Implement table visual inventory construction from existing extracted and deterministic table artifacts.

Function:

```python
build_table_visuals(
    extracted_tables: list[ExtractedTable],
    table_definitions: list[TableDefinition],
) -> list[PaperVisual]
```

Rules:

- Prefer explicit table labels found in extracted table title or caption.
- Fall back to table definition title or caption.
- Use `source_table_id` to link back to the parser table ID.
- Use `page_num` from the extracted table when available.
- Preserve captions from extracted tables or table definitions.
- Do not invent a visual number if no table label can be found.
- Deduplicate by canonical `visual_kind:number`.
- If multiple extracted fragments refer to the same table number, keep one `PaperVisual` and add notes that indicate multiple source table IDs or continuation-like evidence.

Tests:

- table visual from `ExtractedTable.caption = "Table 1. Baseline characteristics"`
- fallback from `TableDefinition.title`
- no visual when no label exists
- dedupe repeated `Table 1` records
- continuation-like duplicate preserves note/source provenance

### Phase 4: Figure Caption Inventory

Implement figure caption detection from block-derived sections.

Function:

```python
build_figure_visuals(sections: list[PaperSection]) -> list[PaperVisual]
```

Initial detection should be conservative:

- recognize lines or paragraphs that begin with `Figure <n>`, `Fig. <n>`, `FIGURE <n>`, or common suffix variants such as `Figure 2A`
- capture the caption text as the detected paragraph or line-level caption text
- avoid treating prose mentions such as `as shown in Figure 2` as captions
- mark page numbers as null unless a reliable source is available

Do not extract PNG files in this phase.

Tests:

- `Figure 2. Flow diagram...` becomes a figure visual
- `Fig. 1 Study design` becomes a figure visual
- prose reference `as shown in Figure 2` does not become a figure visual
- repeated caption candidates dedupe by canonical figure label

### Phase 5: Paper Visual Inventory Assembly

Implement:

```python
build_paper_visual_inventory(
    extracted_tables: list[ExtractedTable],
    table_definitions: list[TableDefinition],
    sections: list[PaperSection],
) -> list[PaperVisual]
```

Rules:

- combine table visuals and figure visuals
- dedupe by `visual_id`
- preserve deterministic ordering: tables and figures in paper order when possible, then by kind and number
- do not fail parse if no visuals are found

CLI integration:

- extend `PaperParseArtifacts` with `paper_visual_inventory`
- build it after `paper_sections` and `table_definitions` exist
- write `paper_visual_inventory.json`

Tests:

- parse writes `paper_visual_inventory.json`
- output is empty list when no visuals are found
- table and figure visuals both serialize in the same artifact

### Phase 6: Reference Scanning

Implement deterministic reference scanning over `PaperSection.content`.

Function:

```python
collect_paper_visual_references(
    sections: list[PaperSection],
    visuals: list[PaperVisual],
) -> list[PaperVisualReference]
```

Required scanning behavior:

- scan all sections, including references-like sections
- detect table and figure references in ordinary prose
- split compound mentions into one record per target when feasible
- assign stable IDs as `paper_ref:<section_id>:p<paragraph_index>:r<reference_index>`
- store anchor fields: paragraph index, character span, and anchor paragraph text

Initial supported patterns:

- `Table 1`
- `Table1`
- `Tables 1 and 2`
- `Figure 2`
- `Fig. 2`
- `Figures 2A and 2B`
- `Figs. 1, 2`

Reference scanning should not infer captions. Caption detection belongs to the visual inventory phase.

Tests:

- single table reference
- single figure reference
- compact `Table1`
- compound table reference creates one record per target
- references-like section still produces records, with later resolution status marking
- stable IDs do not depend on previous sections that have no references

### Phase 7: Reference Resolution

Resolve scanned references against the visual inventory.

Rules:

- if exactly one visual matches canonical `kind:number`, set `resolved_visual_id` and `resolution_status = "resolved"`
- if no visual matches and section role is `references_like`, set `resolution_status = "external_or_bibliographic"`
- if no visual matches outside references-like sections, set `resolution_status = "unresolved"`
- if multiple visuals match, set `resolution_status = "ambiguous"` and preserve candidate IDs in `resolution_notes`

Do not drop unresolved or bibliographic references.

Tests:

- resolved in-paper table reference
- resolved in-paper figure reference
- unresolved figure reference outside references
- external or bibliographic figure reference inside references-like section
- ambiguous duplicate visual candidates are preserved as ambiguous if dedupe has not collapsed them

### Phase 8: CLI Output

Write the new artifacts from `table1-parser parse`.

In `table1_parser/cli.py`:

- import the new builders
- add `paper_visual_inventory` and `paper_references` to `PaperParseArtifacts`
- build visual inventory before references
- build references from sections plus visual inventory
- write both JSON artifacts in `_write_parse_outputs(...)`
- annotate visual records with reference-check status after references are resolved

Output must be additive. Existing outputs must remain unchanged:

- `extracted_tables.json`
- `normalized_tables.json`
- `table1_continuation_groups.json`
- `merged_table1_tables.json`
- `table_profiles.json`
- `table_definitions.json`
- `parsed_tables.json`
- `table_processing_status.json`
- `parse_quality_reports.json`
- `paper_markdown.md`
- `paper_sections.json`
- `paper_variable_inventory.json`
- `table_contexts/*.json`

Tests:

- CLI parse writes both new artifacts
- JSON content has stable IDs
- parse still succeeds when no references are found

### Phase 9: Table Context Links

Add lightweight links from per-table context bundles to the paper-level reference system.

Preferred schema additions to `TableContext`:

- `reference_ids: list[str] = Field(default_factory=list)`
- `resolved_visual_ids: list[str] = Field(default_factory=list)`

Rules:

- do not embed full reference records by default
- for a table with `table_label = "Table 1"`, link resolved references whose `resolved_visual_id` matches `paper_visual:table:1`
- also allow links by `source_table_id` when the visual inventory maps a table visual to the table definition's `table_id`
- unresolved references should remain paper-level unless there is a clear table-label match

Function signature options:

```python
build_table_contexts(
    sections: list[PaperSection],
    table_definitions: list[TableDefinition],
    paper_visual_inventory: list[PaperVisual] | None = None,
    paper_references: list[PaperVisualReference] | None = None,
) -> list[TableContext]
```

Keep backward compatibility by making the new arguments optional.

Tests:

- table context links to resolved `Table 1` reference ID
- no duplicate IDs
- existing callers that pass only sections and definitions still work

### Phase 10: R Inspection

Update `R/inspect_paper_outputs.R`.

Load artifacts:

- add `paper_visual_inventory`
- add `paper_references`

Add helpers:

```r
show_paper_visuals <- function(paper_dir, visual_kind = NULL)
show_paper_references <- function(
  paper_dir,
  reference_kind = NULL,
  reference_label = NULL,
  resolution_status = NULL
)
```

`show_paper_visuals(...)` should print:

- visual ID
- kind
- label
- page
- source table ID
- artifact path
- caption

`show_paper_references(...)` should print:

- reference ID
- label
- heading
- resolution status
- resolved visual ID
- anchor text

Update `show_table_context(...)` to print linked `reference_ids` when present.

Tests:

- R helper loads both artifacts
- visual helper filters by `figure`
- reference helper filters by `resolved`
- table context output includes linked reference IDs

### Phase 11: Documentation Updates

Update docs in the same implementation change:

- `docs/design/parsing_output_design.md`
  - add `PaperVisual` and `PaperVisualReference`
  - add output paths
  - document field intent and resolution statuses
- `docs/design/paper_markdown_spec.md`
  - mention visual inventory and reference extraction as markdown-derived artifacts
  - preserve the rule that markdown itself is not rewritten
- `docs/design/paper_parse_walkthrough.md`
  - update paper-context flow to include visual inventory and references
  - explain that references resolve against actual in-paper visuals
- `docs/r_visualization.md`
  - add R helper usage examples

If CLI outputs or table context schema shape change, ensure `README.md` is updated where it lists parse outputs and context inspection behavior.

## Figure Image Extraction Later

Do not include figure PNG extraction in the first implementation.

When implemented, add a separate plan because it will touch PDF layout/image handling.

Expected future touch points:

- figure region detection from PDF layout
- PNG writing under `outputs/papers/<paper_stem>/figures/`
- `artifact_path` population in `paper_visual_inventory.json`
- visual verification tests that avoid storing large fixture images in the repository

## Acceptance Criteria

The first complete implementation is done when:

- `table1-parser parse` writes `paper_visual_inventory.json`
- `table1-parser parse` writes `paper_references.json`
- all table and figure references found in markdown sections are preserved
- references resolve only when the referenced visual exists in `paper_visual_inventory.json`
- standard in-paper visuals record `referenced_in_text` only when they have at least one resolved non-self text reference
- caption/table-body self mentions do not satisfy the text-reference check
- supplementary visuals are marked `supplementary_exempt`
- unresolved and bibliographic references are explicit, not dropped
- figure captions are represented as figure visuals
- no figure image extraction is required
- table contexts can link to relevant paper-level reference IDs
- Python tests cover schemas, visual inventory, reference scanning, resolution, and CLI output
- R helpers can inspect visuals and references
- design/output/walkthrough/R docs are updated

## Non-Goals

- Do not use an LLM for reference detection or resolution.
- Do not parse figure image content.
- Do not classify scientific meaning of figures.
- Do not turn figure captions into table rows.
- Do not use `paper_markdown.md` as a replacement for table extraction.
- Do not remove unresolved references just because they cannot be matched to an in-paper visual.
