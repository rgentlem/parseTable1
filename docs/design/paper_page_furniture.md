# Paper Page Furniture Artifact

Design contract for repeated non-table page text, page-edge rules, and regions.

## Purpose

`paper_page_furniture.json` records text that appears in essentially the same
page-relative location across multiple pages. It is structural evidence for
ignoring repeated page furniture before it contaminates footnote harvesting,
cell-text annotations, or later extraction cleanup.

The artifact does not need to classify the repeated text before footnote use.
For suppression, repeated headers, footers, watermarks, marginal text, and
download/license notices are all treated as repeated page regions.

The artifact also records stroked horizontal rules in a stable top edge or
repeated-bottom band position on at least 80% of document pages. These rules remain in
`paper_positioned_document.json` but are excluded from table-candidate rule
geometry so journal header/footer separators cannot become table boundaries.

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
document construction, cell text annotation, and document-linked footer detection must consume
the same ignored regions before they build downstream artifacts.

## Top-Level Shape

```json
{
  "paper_id": "paper-stem",
  "source_pdf": "paper.pdf",
  "page_scope": {},
  "observations": [],
  "clusters": [],
  "ignored_regions": [],
  "ignored_rule_regions": [],
  "metadata": {
    "source_artifacts": [],
    "thresholds": {},
    "diagnostics": []
  }
}
```

## Page Scope Record

`page_scope` is the sole paper-length authority. It records
`physical_page_count`, `detection_status`, `reported_paper_page_total`,
`terminal_pdf_page_num`, `included_page_nums`,
`excluded_trailing_page_nums`, `printed_page_offset`, accepted source
observation IDs, and diagnostics.

Detection uses the first accepted recurrent page-number candidate matching
`N of M` or `N / M` whose constant printed-page offset yields a terminal PDF
page and whose observations include `M of M`. If no candidate qualifies,
`detection_status` is `unknown`, every physical page is included, and none is
excluded.

Furniture clustering and recurrent-rule detection use only the included page
set and its count. Raw observations remain present for every physical PDF page.

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

`normalized_text` collapses whitespace only. It preserves every observed
integer, while `raw_text` preserves the exact source text.

Page-number substitution is an evidence-gated matching feature, not observation
normalization. The collector creates one private candidate for each standalone
integer and masks only that slot in its candidate template. Candidates group by
single-slot template and orientation only while their page-relative source bboxes
retain one positive common intersection. Spatially ambiguous membership is
rejected. A group is accepted only when it has one observation on each of at
least two distinct PDF pages, completely covers all PDF pages, all even PDF
pages, or all odd PDF pages after page 1, and every observation has the same
`slot value - PDF page number`.

Only an accepted template becomes an additional matching key in canonical
furniture clustering. Its regions contain exactly the accepted source-line IDs.
A rejected candidate leaves the ordinary full-text key available for exact-text
clustering; no observation is mutated before or after candidate evaluation.

The top-level metadata `page_count` should come from the PDF document page
count, not from the highest page number with extractable text observations.

## Cluster Record

A cluster is repeated ordinary text or an accepted page-number template with
stable page-relative location.

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

`ignored_rule_regions` contains page-specific source bboxes, relative bboxes,
the recurrence page set and fraction, and the shared rule-cluster identifier.
Only recurrent stroked horizontal rules in the ordinary top edge or wider
repeated-bottom band qualify; isolated table rules and rules recurring on an
arbitrary page subset remain available to table extraction.

## Recurrence Rule

Clustering requires both:

- repeated ordinary normalized text or an accepted page-number candidate template
- stable page-relative position

The implementation clusters matching keys and orientations when their
page-relative source bboxes retain one positive common intersection. This
admits observed coordinate drift and text-width changes without rounding
coordinates or adding a distance, overlap-fraction, or IoU threshold. It then
evaluates complete all-page, even-page, and odd-body-page recurrence
independently. Even recurrence must cover every even PDF page; odd-body
recurrence must cover every odd PDF page after page 1. Partial parity sequences
and arbitrary page subsets are rejected regardless of their total-page
fraction.

A numeric slot can produce `<page_num>` only through the candidate gate above.
The constant-offset invariant supports consecutive or odd/even page sequences
and nonzero printed-page offsets while rejecting constant issue, volume, year,
or counter-total slots. Duplicate observations on one PDF page, contradictory
offsets, insufficient coverage, and spatial ambiguity reject the candidate.

## Consumption Status

Immediately after page-furniture detection, the parser creates one in-memory
projection of `PaperPositionedDocument` containing only `included_page_nums`.
Every later document-interpretation and table-extraction stage consumes that
projection. The persisted `paper_positioned_document.json` remains the complete
raw record of all physical pages.

Extraction uses this artifact before candidate refinement. It records
`page_furniture_overlap` metadata when a candidate bbox touches ignored regions
and `page_furniture_mask` metadata when positioned words, chars, or explicit-grid
rows are removed. Cell-text annotation and document-linked footer detection consume
the same regions before grouping annotations or footer line groups, so repeated
page furniture is not reintroduced as small markers or definition lines.
Recurrent edge-rule regions are applied only to candidate rule segments; they do
not remove text, cells, or the raw positioned rule evidence.

Raw raster and vector components remain in `PaperPositionedDocument`. Before
figure-caption binding consumes those components, it excludes an exact
component-kind-and-bbox signature only when that signature occurs on every page
in the matched furniture cluster and positively overlaps that cluster's
page-specific ignored region. This preserves the raw visual evidence while
preventing recurrent page-number or header clips from expanding a figure; a
one-page figure that merely crosses the same page-edge region remains eligible.
