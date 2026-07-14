# Split Label Column Repair Design Spec

Retired: this normalization-stage repair is no longer implemented. Physical
left-side label columns are preserved in `NormalizedTable`; extraction should
own wrong column boundaries, and logical row-label assembly should be expressed
later through row-label candidates or semantic row logic.

## Purpose

Repair tables where the extractor splits one logical left-side row label into two adjacent label columns.

Example failure from `pad.pdf`:

- `Mexican | American`
- `Other | Hispanic`
- `Less than | 9th grade`
- `Married/Living | with a partner`

These should be one row label, not two columns.

## Problem

Current normalization assumes the first remaining column is the row-label column.

When extraction over-segments the left side of the table, the normalized rows keep both label fragments as separate columns, and later parsing only uses column 0 as `first_cell_raw`.

This truncates row labels without actually losing the text.

## Scope

This is a normalization-stage repair only.

In scope:

- detect adjacent split label columns on the left side
- merge them into one label column before `RowView` construction
- preserve all original text

Out of scope:

- extractor changes
- heuristic row classification changes
- schema changes
- value-column repair changes outside the left label region

## Detection Rule

A table is eligible for split-label repair when:

- columns 0 and 1 are both mostly label-like
- columns 2+ contain the real numeric/value cells
- column 1 is not behaving like a data column
- many body rows have:
  - label-like text in both column 0 and column 1
  - numeric/value content beginning in later columns

Typical examples:

- `Mexican | American | 1852 (21.22%) | ...`
- `High | school graduate | 2003 (22.95%) | ...`

## Repair Rule

For eligible rows:

- merge column 0 and column 1 into one label cell
- keep order and spacing
- blank column 1 after merge

After row-wise merge:

- drop column 1 if it becomes empty

## Row Eligibility

A row should be merged when:

- column 0 is label-like
- column 1 is label-like
- later columns contain values or statistic content

This should apply to:

- parent rows
- level rows

It should not merge rows where column 1 is actually a value/stat column.

## Placement In Pipeline

Run this in normalization after:

- leading/trailing empty-column trimming

Run it before:

- `RowView` construction
- header/body-sensitive downstream heuristics

This is the same stage where current column repairs already run.

## Output Behavior

After repair:

- `cleaned_rows` should contain the merged full label in column 0
- `RowView.first_cell_raw` should be the full label
- later parsing should see:
  - `Mexican American`
  - `Other Hispanic`
  - `High school graduate`
  - `Married/Living with a partner`

No raw text should be discarded.

## Metadata

Record the repair in normalization metadata under `column_repairs`.

Suggested entry:

- `merged_split_label_columns`

Each repair record should include:

- `from_col_idx`
- `to_col_idx`
- `merged_row_count`

## Constraints

- no schema changes
- no extractor changes
- no new parser stage
- preserve raw text content
- avoid aggressive merging beyond the left label region

## Minimum Success Criteria

For `pad.pdf` Table 1:

- `Mexican American` is restored as one label
- `Other Hispanic` is restored as one label
- `Non-Hispanic White` and `Non-Hispanic Black` are restored
- `Less than 9th grade` is restored
- `High school graduate` is restored
- `Married/Living with a partner` is restored

And these restorations should appear already in:

- `normalized_tables.json`
- `table_definitions.json`
- `parsed_tables.json`
