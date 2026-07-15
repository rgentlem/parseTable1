# Paper Bibliography Artifact

`paper_bibliography.json` preserves the fixed bibliography/reference list for
one parsed paper and links observed numeric reference markers back to numbered
entries in that list.

This is not a citation-management layer. It does not look up DOIs, normalize
authors, deduplicate across papers, or maintain a corpus-level reference store.
It is a per-paper extraction artifact.

## File

```text
outputs/papers/<paper_stem>/paper_bibliography.json
```

The parser writes a valid empty artifact when no bibliography entries or
reference markers are found.

## Pipeline Position

Bibliography entry extraction should run before table extraction because it
depends on the whole-paper document stream, not on table grids. The primary
source is `paper_text_stream.json`: positioned PyMuPDF lines filtered through
`paper_page_furniture.json` and ordered by page, column, then vertical position.
There is no backend-markdown fallback for bibliography entry extraction. Later
table-cell annotation and footnote processing can then link numeric table
markers to already-known numbered bibliography entries. The same bibliography
pass is the only source of the reference-region evidence used by table
extraction: when entries are found,
table extraction receives bibliography-owned source-line IDs and entry bboxes
and removes positioned bibliography words/chars before candidate construction;
when entries are not found, no bibliography-derived suppression is applied. The
extractor must not run a separate raw-text `References` scan.

The implemented flow is:

```text
PDF
-> paper_positioned_document.json
-> paper_page_furniture.json
-> paper_text_stream.json
-> paper_markdown.md
-> paper_sections.json
-> bibliography entries from positioned text
-> bibliography-owned line/entry evidence passed to table extraction when entries are found
-> table extraction and cell text annotations
-> bibliography reference-marker links
-> paper_bibliography.json
```

The reference-list reader is column-count agnostic. For each reference-list
page, it identifies local reference columns from aligned entry starts and
fallback x-start bands, reads column 1 top-to-bottom, then column 2
top-to-bottom, and continues for however many columns are present. Entries stay
open across column and page boundaries until the next left-edge entry start is
seen, so a reference split across pages remains one entry.

## Top-Level Shape

```json
{
  "paper_id": "paper-stem",
  "source_pdf": "paper.pdf",
  "entries": [],
  "reference_mentions": [],
  "metadata": {
    "entry_count": 0,
    "reference_mention_count": 0
  }
}
```

## Entry Record

An entry is one item from the paper's own bibliography. Bibliographies may be
numbered, unnumbered author-year lists, or a mix produced by the source layout.

Important fields:

- `entry_id`: stable per-paper ID such as `bib:33` or `bib:unnum:7`
- `label_raw`: visible bibliography label; empty for unnumbered entries
- `label_key`: canonical label key such as `number:33` or `unnumbered:7`
- `reference_number`: numeric label when present; `null` for unnumbered
- `raw_text`: extracted entry text
- `clean_text`: lightly cleaned text for inspection and matching
- `source_section_id`, `heading`, `role_hint`: section provenance
- `source_artifact`: usually `paper_text_stream.json`, with
  `paper_sections.json` used for fallback entries
- `source_line_ids`: positioned text lines that contributed to the entry
- `page_nums`: PDF pages spanned by the entry
- `bbox`: bounding box when all contributing lines are on one page
- `visual_line_count`: number of visual text rows assembled into the entry
- `confidence`
- `notes`

Extraction uses the same layout stream for numbered and unnumbered lists:
reference-list pages are read as page, column, then vertical position; a new
entry begins at the column's left edge, either with a visible numeric label or
with the first author/organization text in a hanging-indent list. Continuation
rows remain indented and entries can span column and page boundaries. Inline
starts such as `References 1. Author...` and bracketed/dotted/bare numeric
labels are supported. Extraction metadata records numbering style, low entry
counts, nonsequential numeric labels, unusually long entries, and observed
reference markers whose numbers exceed the extracted numbered bibliography.

## Reference Mention Record

A reference mention is an observed marker in a paper source that points to a
bibliography entry.

The initial implemented source is numeric table-cell markers that were detected
as cell text annotations, including numeric superscripts attached to row-label
study/source names and column-header citation phrases. These are bibliography
references, not table footnotes, when they have no local table-note definition
and match a numbered entry in the paper's own bibliography. Author-year body
citations are not linked yet, but their unnumbered bibliography entries are
preserved as first-class records.

Important fields:

- `mention_id`
- `label_raw`
- `label_key`
- `source_scope`
- `source_id`
- `source_artifact`
- `page_num`
- `table_id`, `row_idx`, `col_idx`, `source_role`
- `attached_to_text`, `text_context`, `bbox`
- `link_status`: `resolved`, `unresolved`, or `ambiguous`
- `entry_id`
- `candidate_entry_ids`
- `confidence`
- `notes`

For table-cell mentions, `mention_id` is
`bibref:<CellTextAnnotation.annotation_id>`, using the stable occurrence ID
reused by the corresponding footnote anchor. `source_id` remains the physical
cell source ID. This lets bibliography, footnote, and cell-annotation artifacts
refer to one physical occurrence without maintaining a second positional
identity. The source annotation retains whether the glyph was a superscript,
subscript, or inline marker.

Later body-text citation harvesting should reuse this same artifact rather than
creating a separate citation system.
