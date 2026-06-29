---
name: testpapers-batch-review
description: Use when asked to run examples, real papers, all papers, the testpapers corpus, smoke tests on PDFs, or pre-commit/pre-push parser validation against local real-paper examples in `/Users/robert/Projects/Epiconnector/testpapers`.
---

# Testpapers Batch Review

## Paths

Use the real-paper corpus at:

```text
/Users/robert/Projects/Epiconnector/testpapers
```

Find PDFs recursively. Do not assume a single subdirectory.

Write generated outputs under a fresh ignored directory such as:

```text
outputs/testpapers_batch_<timestamp>
```

Do not stage or commit anything under `outputs/`.

## Batch Workflow

1. Confirm the current working tree state before running the batch.
2. Create a fresh batch output directory under `outputs/`.
3. Run `table1-parser parse <pdf> --outdir <batch-output-dir>` for each PDF.
4. Capture per-PDF success/failure status.
5. For successful runs, check that expected core artifacts exist:
   - `extracted_tables.json`
   - `normalized_tables.json`
   - `column_header_schemas.json`
   - `table_definitions.json`
   - `parsed_cell_values.json`
   - `parsed_tables.json`
   - `table_processing_status.json`
6. Summarize failures, crashes, missing artifacts, and any notable schema
   regressions.

## Reporting

Report:

- number of PDFs found
- output directory used
- passed/failed counts
- failed PDF paths and error summaries
- whether `parsed_cell_values.json` and component-bearing `parsed_tables.json`
  were produced
- whether `pytest` was also run

Do not treat existing files in `outputs/papers` as current unless regenerated in
the current run.
