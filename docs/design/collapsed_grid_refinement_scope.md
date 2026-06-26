# Collapsed Grid Refinement Scope

## Purpose

Consolidate the duplicated collapsed-grid refinement logic in the PyMuPDF extractor without changing parser behavior or adding new rescue methods.

## Target

Refactor the duplicated rotated/upright collapsed-grid branches in [pymupdf4llm_extractor.py](/Users/robert/Projects/Epiconnector/parseTable1/table1_parser/extract/pymupdf4llm_extractor.py).

Current duplicate areas:

- rotated collapsed-grid refinement
- upright collapsed-grid refinement

Both branches currently:

- build word lines
- trim footer lines using horizontal rules
- rebuild a row grid from lines
- drop empty columns
- compare refined structure to the original grid
- return refined rows plus metadata

## In Scope

- unify the rotated and upright collapsed-grid refinement flow
- keep the logic inside the existing extractor function
- prepare geometry differently by mode, then run one shared inline rebuild block
- preserve current metadata fields and downstream behavior
- preserve current acceptance thresholds unless later testing justifies changing them

## Out Of Scope

- no new extraction algorithms
- no new rescue paths
- no new parser-stage failure logic
- no schema changes
- no CLI changes
- no broader extractor refactor outside this duplicated block

## Design Rules

- do not introduce small single-use helper functions
- keep the shared rebuild flow inline inside the parent function
- treat rotated and upright refinement as one method with two geometry-preparation modes
- keep estimate/model-specific refinement separate for now

## Mixed-Orientation Pages

Some two-column journal pages contain a rotated table in one column and upright
article prose in the other. In that case a whole-page direction summary can
lower the table's rotation confidence even when the candidate table region is
visibly rotated. The extractor should therefore allow candidate-local rotated
collapsed-grid refinement when all of these structural signals are present:

- the candidate reports a vertical text direction with at least moderate
  confidence
- the explicit grid has few columns and several stacked or text-blob cells
- positioned words inside the candidate provide enough evidence to rebuild a
  wider grid

For wide, short rotated candidates, PyMuPDF4LLM may report the table bbox in a
visual/upright frame rather than the page-space region needed for word clipping.
The extractor may try a transposed candidate clip before rotating into
table-local coordinates, but it should accept that result only when the rebuilt
grid gains clear columns and preserves enough rows. This is still a structural
geometry repair, not a paper-specific continuation rule.

Uncaptioned one-row, many-column prose shards from nearby article text should
not be preserved as explicit table outputs when they have dense prose fragments
and little value-cell evidence.

## Expected Result

- less duplicated extractor code
- unchanged extractor outputs except where a collapsed rotated candidate is
  structurally rebuilt or an uncaptioned prose shard is rejected
- clearer rescue logic for collapsed explicit grids

## Estimated Impact

- likely net reduction: 35 to 50 lines

If a later cleanup also folds the nearby estimate/model rebuild pattern into the same structure, total reduction could reach roughly 55 to 80 lines, but that is not part of this scoped change.
