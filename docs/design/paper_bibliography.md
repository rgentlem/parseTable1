# Paper Bibliography Artifact

`paper_bibliography.json` preserves the fixed bibliography/reference list for
one parsed paper and links observed numeric reference markers back to that list.

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
depends on the whole-paper markdown/section representation, not on table grids.
Later table-cell annotation and footnote processing can then link numeric table
markers to the already-known bibliography entries.

The implemented flow is:

```text
PDF
-> paper_page_furniture.json
-> paper_markdown.md
-> paper_text_stream.json
-> paper_sections.json
-> bibliography entries
-> table extraction and cell text annotations
-> bibliography reference-marker links
-> paper_bibliography.json
```

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

An entry is one numbered item from the paper's own bibliography.

Important fields:

- `entry_id`: stable per-paper ID such as `bib:33`
- `label_raw`: visible bibliography label
- `label_key`: canonical label key such as `number:33`
- `reference_number`: numeric label
- `raw_text`: extracted entry text
- `clean_text`: lightly cleaned text for inspection and matching
- `source_section_id`, `heading`, `role_hint`: section provenance
- `source_artifact`: usually `paper_sections.json`
- `confidence`
- `notes`

Initial extraction supports ordinary numbered lists and simple two-column
markdown tables that contain numbered bibliography entries.

## Reference Mention Record

A reference mention is an observed marker in a paper source that points to a
bibliography entry.

The initial implemented source is numeric table-cell markers that were detected
as cell text annotations, including numeric superscripts attached to row-label
study/source names and column-header citation phrases. These are bibliography
references, not table footnotes, when they have no local table-note definition
and match an entry in the paper's own bibliography.

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

Later body-text citation harvesting should reuse this same artifact rather than
creating a separate citation system.
