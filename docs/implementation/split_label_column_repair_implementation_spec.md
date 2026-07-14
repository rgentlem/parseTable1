# Split Label Column Repair Implementation Spec

Retired: this implementation path has been removed from normalization. Do not
reintroduce split-label column merging as a `NormalizedTable` mutation.

## Goal

Implement a normalization-stage repair for tables where one logical row label is split across columns 0 and 1.

## Files

- `table1_parser/normalize/pipeline.py`
- `tests/test_normalization.py`
- `tests/test_table_definition.py`

## Constraints

- do not change schemas
- do not change extraction logic
- do not add a new parser stage
- preserve raw label text while merging split left-side label columns
- avoid small single-use helpers unless clearly justified

## Step 1: Detect split left label columns

In `pipeline.py`, inspect columns 0 and 1 after leading/trailing empty-column trimming.

Treat the table as eligible when:

- column 0 is frequently label-like
- column 1 is also frequently label-like
- later columns contain the numeric/value cells
- column 1 does not behave like a value/stat column

## Step 2: Merge eligible rows

For rows where:

- column 0 is label-like
- column 1 is label-like
- later columns contain values or statistic content

merge:

- `raw_rows[row_idx][0] = raw_rows[row_idx][0] + " " + raw_rows[row_idx][1]`
- same for `cleaned_rows`

Then blank column 1 for those rows.

## Step 3: Drop the emptied helper column

If column 1 becomes empty after the row merges, drop it from:

- `raw_rows`
- `cleaned_rows`

Then continue with the existing normalization flow.

## Step 4: Record repair metadata

Add the repair to `metadata["column_repairs"]` as:

- `merged_split_label_columns`

Each record should include:

- `from_col_idx`
- `to_col_idx`
- `merged_row_count`

## Step 5: Preserve downstream behavior

After the merge:

- `RowView.first_cell_raw` should contain the merged label
- header detection and later heuristics should use the repaired rows

No downstream schema or parser changes should be needed.

## Tests

Add focused tests for a `pad`-like layout where:

- `Mexican | American`
- `Other | Hispanic`
- `Non-Hispanic | White`
- `Less than | 9th grade`
- `Married/Living | with a partner`

are split across columns 0 and 1.

Required assertions:

- normalized `cleaned_rows` merge the label fragments
- `RowView.first_cell_raw` uses the full merged label
- later `TableDefinition` labels also use the merged form

## Validation

Run:

```bash
pytest tests/test_normalization.py tests/test_table_definition.py -q
```

Then re-parse:

```bash
python3 -m table1_parser.cli parse ~/Downloads/pad.pdf
```

Check:

- `outputs/papers/pad/normalized_tables.json`
- `outputs/papers/pad/table_definitions.json`
- `outputs/papers/pad/parsed_tables.json`

## Minimum Success Criteria

- `Mexican American` is restored
- `Other Hispanic` is restored
- `Non-Hispanic White` is restored
- `Non-Hispanic Black` is restored
- `Less than 9th grade` is restored
- `High school graduate` is restored
- `Married/Living with a partner` is restored
