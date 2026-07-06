# Paper Page Furniture Artifact

Design contract for repeated non-table page text and regions.

## Purpose

`paper_page_furniture.json` records text that appears in essentially the same
page-relative location across multiple pages. It is structural evidence for
ignoring repeated page furniture before it contaminates footnote harvesting,
cell-text annotations, or later extraction cleanup.

The artifact does not need to classify the repeated text before footnote use.
For suppression, repeated headers, footers, watermarks, marginal text, and
download/license notices are all treated as repeated page regions.

## File

```text
outputs/papers/<paper_stem>/paper_page_furniture.json
```

The parser should write a valid empty artifact when no repeated page furniture
is found.

Current status: `table1-parser parse` builds this artifact before table
extraction and writes it for every paper. R inspection helpers can load and
display clusters and ignored regions. Extraction uses ignored regions to mask
repeated page-furniture words, chars, and explicit-grid rows. Paper text,
markdown, cell text annotation, and footnote PDF-block collection must consume
the same ignored regions before they build downstream artifacts.

## Top-Level Shape

```json
{
  "paper_id": "paper-stem",
  "source_pdf": "paper.pdf",
  "observations": [],
  "clusters": [],
  "ignored_regions": [],
  "metadata": {
    "source_artifacts": [],
    "thresholds": {},
    "diagnostics": []
  }
}
```

## Text Observation Record

An observation is one positioned page text line or span before recurrence
clustering.

Required fields:

- `observation_id`
- `page_num`
- `raw_text`
- `normalized_text`
- `bbox`
- `relative_bbox`
- `page_width`
- `page_height`

Optional fields:

- `orientation`
- `block_index`
- `line_index`
- `source_artifact`
- `confidence`
- `notes`

`bbox` uses page coordinates from the extractor. `relative_bbox` stores the same
region as page-width/page-height fractions, so repeated positions can be compared
across pages with slightly different sizes.

`normalized_text` is only a matching key. It collapses whitespace and may mask
the current PDF page-number token as `<page_num>`. `raw_text` preserves the
observed text.

The top-level metadata `page_count` should come from the PDF document page
count, not from the highest page number with extractable text observations.

## Cluster Record

A cluster is repeated text with similar normalized content and stable
page-relative location.

Required fields:

- `cluster_id`
- `normalized_text_key`
- `representative_text`
- `observation_ids`
- `page_nums`
- `occurrence_count`
- `page_fraction`
- `recurrence_scope`
- `representative_bbox`
- `representative_relative_bbox`
- `confidence`

Optional fields:

- `scope_page_count`
- `scope_page_fraction`
- `recurrence_basis`
- `notes`

If later review needs human labels such as running header, watermark, or footer,
that should be layered onto the artifact rather than required for suppression.

## Ignored Region Record

An ignored region is a page-specific bbox derived from a repeated cluster.

Required fields:

- `region_id`
- `cluster_id`
- `page_num`
- `bbox`
- `relative_bbox`
- `confidence`

Optional fields:

- `source_observation_ids`
- `notes`

Downstream code should use `ignored_regions` for geometric overlap checks
instead of recomputing cluster positions.

## Recurrence Rule

Initial clustering should require both:

- repeated normalized text or repeated text pattern
- stable page-relative position

The initial implementation clusters exact `normalized_text` values by nearby
page-relative centers, then only accepts clusters in a page edge band. This
keeps repeated body-table values or repeated table notes from becoming page
furniture just because they recur at similar coordinates. It records
`all_pages`, `odd_pages`, `even_pages`, or `page_subset` recurrence according to
the pages covered by the matched group.

A practical starting threshold is at least three pages or at least 50-70% of
paper pages. Store the exact threshold and skipped-candidate diagnostics in
`metadata`.

Also evaluate odd-page and even-page recurrence separately. Printed page
furniture often alternates by page parity, such as different left/right running
headers. In that case `page_fraction` may be low across the full paper, but
`scope_page_fraction` can be high within `recurrence_scope = "odd_pages"` or
`"even_pages"`.

## Consumption Status

Extraction uses this artifact before candidate refinement. It records
`page_furniture_overlap` metadata when a candidate bbox touches ignored regions
and `page_furniture_mask` metadata when positioned words, chars, or explicit-grid
rows are removed. Cell-text annotation and footnote PDF-block code consume the
same regions before grouping characters into annotations or definition blocks,
so repeated page furniture is not reintroduced as small markers or definition
lines.
