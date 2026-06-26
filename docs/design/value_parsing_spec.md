# Value Parsing and Symbol Canonicalization Spec

This document specifies two related future changes for the value-parsing path:

1. symbol canonicalization for parser-facing text
2. Table 1 `n (%)` parsing and consistency heuristics

These changes are intended to improve parsing stability without changing the core pipeline shape:

```text
PDF -> ExtractedTable -> NormalizedTable -> TableDefinition -> ParsedTable
```

They do not change the rule that raw extracted text must be preserved.

## Goals

- preserve paper-facing raw text exactly as extracted
- make parser behavior stable when visually equivalent symbols appear in different Unicode forms
- parse common Table 1 `n (%)` cells into structured numeric fields
- parse common continuous summary cells, including PDFs that extract a visual plus/minus as a spaced numeric `6`
- add soft consistency checks that are useful for classic baseline-characteristics tables
- avoid overfitting the parser to one paper or one journal style
- allow row-label-derived expected value styles to support conservative structural repair of malformed normalized grids

## Non-Goals

- do not detect a per-paper character encoding scheme
- do not rewrite canonical raw JSON fields to a lossy normalized form
- do not assume all categorical rows in all tables use `n (%)`
- do not reject a table solely because a count-percent heuristic fails
- do not mix value parsing into the value-free `TableDefinition` stage

## 1. Symbol Canonicalization

### Problem

Extracted text already arrives in Python as Unicode strings, but equivalent comparison and dash symbols may appear in multiple forms.

Examples:

- `<`, `＜`
- `>`, `＞`
- `≤`, `≦`
- `≥`, `≧`
- `-`, `−`, `–`, `—`

If the parser only recognizes one spelling, heuristics become brittle even though the visible content is effectively the same.

### Design Rule

The system must preserve two distinct views of text:

- raw text:
  the exact extracted cell text that is written to canonical JSON payloads
- canonical parsing text:
  a normalized form used only by deterministic heuristics, regex matching, and later value parsing

Raw text remains the source-of-record. Canonical parsing text is an internal helper representation.

### Canonicalization Scope

Canonicalization should run in deterministic text-cleaning helpers used by:

- header cleaning
- label normalization
- value-pattern detection
- p-value parsing
- any later numeric value parser

It should not mutate the stored raw text in:

- `TableCell.text`
- `RowView.raw_cells`
- `ValueRecord.raw_value`

### Initial Mapping Rules

The first implementation should normalize at least the following:

- comparison operators:
  - `<`, `＜`, `&lt;` -> `<`
  - `>`, `＞`, `&gt;` -> `>`
  - `≤`, `≦`, `&le;` -> `<=`
  - `≥`, `≧`, `&ge;` -> `>=`
- dash and minus variants:
  - `‐`, `‑`, `‒`, `–`, `—`, `―`, `−` -> `-`
- whitespace:
  collapse repeated whitespace to a single space

The mapping should stay conservative. Only normalize symbols that are semantically equivalent for parser purposes.

Some PDFs extract the visual plus/minus glyph in summary values as a spaced `6`,
for example `25.9 6 3.6`. The current parser treats that shape as `mean_sd`
only when it appears as two numeric tokens separated by a spaced `6`; unspaced
integers such as `2603` remain plain counts. This is a parser-facing value
pattern rule and does not rewrite `raw_value`.

### Where It Should Live

The canonicalization logic should live in the normalization/text-cleaning layer and be reused by heuristics rather than reimplemented inside multiple regex modules.

Expected touch points:

- `table1_parser/normalize/cleaner.py`
- `table1_parser/normalize/text_normalizer.py`
- `table1_parser/heuristics/value_pattern_detector.py`

### JSON Encoding Note

This change does not require adding an "encoding scheme" field to JSON artifacts.

The repository should continue to write JSON files as UTF-8 text. If a later cleanup is desired for readability, JSON writers may switch to `ensure_ascii=False`, but that is a serialization choice, not a schema change.

### Debugging Guidance

If debugging visibility becomes useful later, the project may optionally add parser-trace fields or wrapper artifacts that show both:

- raw text
- canonical parsing text

That should be treated as debug output, not as a replacement for canonical raw fields.

## 2. Table 1 `n (%)` Parsing

### Problem

Many classic epidemiology Table 1 tables print categorical cells as:

```text
count (percent)
```

Examples:

- `120 (43.7)`
- `120 (43.7%)`

The current repository already recognizes this shape as `count_pct`, but the next value-parsing phase should make the interpretation explicit and add cross-cell consistency checks.

### Parsing Rule

For a cell recognized as `count_pct`:

- `parsed_numeric` stores the count
- `parsed_secondary_numeric` stores the percent
- `ValueRecord.value_type` should remain the existing closest type until the schema is expanded deliberately

The parser should accept both percent spellings:

- `34 (45)`
- `34 (45%)`

Counts should be parsed as integer-like values. Percents may be integer or decimal.

### Scope Restriction

This heuristic is intended only for variables that look like categorical partitions.

Candidate variables should satisfy most of the following:

- the row variable has explicit levels
- `summary_style_hint == "count_pct"` or cell-level pattern detection strongly supports `count_pct`
- the column is not inferred as `p_value`
- the column is not inferred as `smd`

This heuristic should not run on:

- continuous summaries such as `mean (SD)`
- median/IQR rows
- free-text note rows
- p-value columns

### Row-Style Inheritance Rule

Expected value style is sometimes defined by a parent variable row rather than by each printed level row.

Examples:

- `Education level, n (%)`
- level rows such as `<High school`, `High school`, `>High school`

Design rule:

- when a categorical variable row indicates a summary style such as `n (%)`, that expected style should be inherited by its level rows for downstream parsing and soft structural checks
- the parent variable row itself may legitimately have no values
- this inherited expectation may be used earlier in normalization to repair obviously split adjacent cells such as `594` plus `(34.4%)`

This remains a soft heuristic. It should support structural repair and confidence adjustment, not hard rejection.

### Column Semantics Rule

The denominator interpretation is not uniform across all columns.

For this project, the intended heuristic is:

- the first substantive data column may act as an overall column
- that column should only be treated as "sum to 100%" when its header clearly means overall population, such as:
  - `Overall`
  - `Total`
  - `All`
  - a blank or missing header when column-role inference and table layout strongly suggest it is the overall column
- the final `p_value` column is excluded from all count-percent checks
- non-`p_value` subgroup columns should not automatically be forced to sum to 100%

Instead, subgroup columns may use overall-population percentages rather than within-column percentages. In that common layout, the percentages down one subgroup column sum to that subgroup's share of the total population, not to 100.

### Denominator Modes

The parser should support two soft denominator modes for categorical `n (%)` rows:

1. overall-column mode

- applies only to the first substantive data column when it is confidently interpreted as `overall`
- sibling level percents for one categorical variable should sum to approximately 100

2. overall-population-denominator subgroup mode

- applies to non-`p_value` subgroup columns when an overall denominator is available
- sibling level percents for one categorical variable should sum to the subgroup's share of the full study population
- this expected subgroup share should be estimated from a stronger source, in priority order:
  - explicit header `N`
  - an inferred overall denominator from the overall column
  - a high-confidence table-wide `n` row if present

The parser should not assume that subgroup columns use within-column denominators unless the table provides strong evidence for that convention.

### Proposed Heuristic Flow

For each parsed categorical variable with sibling levels:

1. identify candidate value columns

- exclude `p_value`
- exclude `smd`
- keep the first substantive data column as a possible `overall` column
- keep remaining substantive columns as subgroup columns

2. parse all sibling `count_pct` cells for one variable across those columns

- parse count
- parse percent
- record failures without crashing

3. evaluate the first substantive column as a possible overall column

- if the header is `Overall`, `Total`, `All`, or confidently blank-overall:
  - check whether sibling percentages sum to about 100
  - use a rounding tolerance rather than exact equality
- otherwise:
  - do not apply the 100% rule

4. evaluate each non-`p_value` subgroup column

- if an overall denominator can be estimated reliably:
  - compute the expected subgroup share of the full population
  - compare the sibling percent sum for that subgroup column to the expected share
- if no reliable denominator is available:
  - skip the subgroup-share check

5. convert heuristic results into notes and confidence adjustments

- strong agreement increases confidence
- weak disagreement lowers confidence
- major disagreement produces a validation note or warning

### Tolerances

All checks must be soft and rounding-aware.

Recommended starting tolerances:

- overall-column sum-to-100 check:
  allow a small absolute error such as 1 to 2 percentage points
- subgroup-share checks:
  allow a slightly wider tolerance because denominator inference may itself be approximate

Exact tolerances can be tuned using the synthetic fixtures and sample papers.

### Important Failure Modes

The parser must tolerate these common exceptions:

- omitted or collapsed rare categories
- explicit `Unknown` or `Missing` categories that may or may not be printed
- weighted survey tables
- percentages computed with a denominator that excludes missing values
- one-row binary summaries without explicit sibling rows
- category rows that are not exhaustive partitions
- journals that print row percentages rather than overall-population percentages

Because of these cases, the heuristic should affect confidence and diagnostics, not act as a hard accept/reject rule.

## 3. Intended Schema Consequences

This spec does not require an immediate schema change.

The existing future-facing `ParsedTable` fields are already sufficient for first implementation:

- `ValueRecord.raw_value`
- `ValueRecord.parsed_numeric`
- `ValueRecord.parsed_secondary_numeric`

Interpretation:

- `raw_value` preserves the printed source text
- `parsed_numeric` stores the parsed count
- `parsed_secondary_numeric` stores the parsed percent

If a later phase needs explicit denominator provenance or validation diagnostics per value, those should be added deliberately and documented across all affected schemas.

## 4. Tests

When implemented, tests should cover at least:

- comparison symbol normalization for `<`, `>`, `<=`, `>=`
- dash/minus normalization
- preservation of raw source text after canonicalization
- `mean_sd` parsing for both real plus/minus glyphs and spaced-`6` extraction artifacts
- `count_pct` parsing with and without `%`
- overall-column sibling percentages summing to about 100
- subgroup-column sibling percentages summing to subgroup share of the total population
- graceful handling of omitted levels, missing categories, and p-value columns

## 5. Implementation Boundaries

These changes should stay separated by stage:

- normalization:
  canonical parsing text helpers
- heuristics:
  value-pattern recognition and denominator inference
- parsed-value assembly:
  creation of `ValueRecord` entries
- validation/diagnostics:
  soft count-percent consistency checks and warnings

Do not collapse symbol normalization, value parsing, and validation into one monolithic step.
