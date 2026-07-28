---
name: run-corpus-comparison
description: Run and compare the parseTable1 28-PDF corpus, including table inventories, bibliography items and reference mentions, footnote anchors and definitions, and missing table-to-footnote links. Use for corpus runs, re-baselines, parser regression audits, and requests to find missing or unmatched table superscripts or footnotes.
---

# Run Corpus Comparison

Follow `AGENTS.md`. Generate outputs and reports only. Do not change parser logic, tests, tolerances, or project documentation.

## Resolve Inputs

Resolve the candidate label, optional baseline, and requested artifact subset. Use a user-named baseline or one explicitly named by the active implementation document. Never infer an accepted baseline from modification time.

## Build The Corpus

Use every recursive PDF under `/Users/robert/Projects/Epiconnector/testpapers` plus `/Users/robert/Projects/Epiconnector/parseTable1/inst/extdata/NutritionEx.pdf`.

Require 27 external PDFs, 28 total PDFs, 28 unique absolute paths, and 28 unique filename stems. Stop and report any discrepancy.

## Run

Create one fresh absolute output directory:

```text
/Users/robert/Projects/Epiconnector/parseTable1/outputs/testpapers_batch_<label>_<YYYYMMDD>
```

Run one process per PDF, with at most six concurrent processes:

```text
table1-parser parse <absolute-pdf-path> --outdir <absolute-candidate-directory>
```

Capture each exit status. Let started processes finish after another fails. Do not run optional LLM commands. Require 28 attempts and one candidate paper directory per successful PDF.

## Audit Each Candidate

Read these artifacts when present:

- `extracted_tables.json`
- `resolved_tables.json`
- `paper_table_inventory.json`
- `table_processing_status.json`
- `paper_bibliography.json`
- `paper_footnotes.json`

Report missing artifacts explicitly.

### Tables

Report source-table count, resolved-table count, continuation integrations, and `ok`/`rescued`/`failed` counts. For every table report exact PDF filename, verified PDF page, printed table number when available, table ID, dimensions, title, resolution type, processing status, and failure reason.

### Bibliography

Report bibliography-entry counts: total, numbered, and unnumbered. Report table reference mentions by `resolved`, `ambiguous`, and `unresolved`, plus unique linked entry count. List every ambiguous or unresolved table reference mention with filename, page, printed table number, table ID, cell coordinates, raw label, attached text, candidates, and status.

Do not call bibliography entries missing merely because no table cites them; they may be cited only in prose.

### Table Footnote Alignment

Use explicit IDs and `paper_footnotes.json.links`; do not infer a link from equal glyph text alone.

For each table-cell anchor, classify in this order:

1. resolved footnote link
2. ambiguous footnote link
3. bibliography reference mention for the same anchor occurrence
4. unmatched table marker

Match a bibliography occurrence by removing the `bibref:` prefix from `reference_mentions[].mention_id` and comparing the remainder with `anchors[].anchor_id`.

Report these four missingness groups separately:

- table markers with unresolved footnote links and no bibliography mention
- table markers with ambiguous footnote links
- bibliography mentions with ambiguous or unresolved bibliography links
- table-associated definitions unused by any resolved table-cell anchor link

Treat a definition as table-associated when `table_id` is present or `source_scope` is `table_note` or `table_caption`. Do not classify page/body definitions as missing table markers.

For every unmatched occurrence report exact PDF filename, page, printed table number, table ID, glyph raw/key, anchor or definition ID, row/column when present, attached/context text, link candidates, and source scope. Preserve repeated occurrences; also summarize unique glyph keys.

## Compare Baseline And Candidate

Compare relative file inventories first, then common files byte-for-byte. Parse changed JSON and compare values without reordering arrays, coercing types, or ignoring fields. Use unified diffs for changed text.

Always compare the semantic inventories above, even when byte differences are numerous. Report candidate-versus-baseline changes in:

- tables, pages, dimensions, continuation decisions, and statuses
- bibliography entry identities, counts, and table-reference links
- footnote anchors, definitions, link statuses, and all four missingness groups

Separate expected, unexpected, and unexplained differences. Never silently accept a difference.

## Report

Return candidate and baseline directories; corpus, success, and failure counts; artifact file counts; table summary; bibliography summary; footnote-link summary; every missingness record; substantive baseline differences; limitations; and cleanup performed.

Never identify a paper only by stem, surname, internal ID, or abbreviation. Never claim the corpus passed while a parse failed, an expected artifact is missing, or an unexplained difference remains.

Keep the baseline through comparison. After successful reporting, if the user did not request preservation, retain only the current candidate under `outputs/`. Never delete source PDFs or non-generated files.
