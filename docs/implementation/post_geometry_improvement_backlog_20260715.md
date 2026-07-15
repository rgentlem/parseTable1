# Post-Geometry Areas Worth Improving

Status: deferred and unapproved.

This is a prioritized improvement list derived from the retained corpus
`outputs/testpapers_batch_phase_k_step5_guarded_final_20260715`. It is separate
from the factual uncertainty inventory in
`docs/implementation/corpus_artifact_uncertainties_20260715.md`.

No item below authorizes parser changes. Each item begins with a read-only audit
of the earliest artifact where the problem appears.

## 1. Resolve the remaining visual-identity gaps

Audit the three Helicobacter pylori fragments on PDF pages 6–8 and the malformed
`Table 1d` label on PDF page 6 of the insulin-sensitivity paper. Determine from
caption, continuation-cue, repeated-header, rule, and column-path geometry
whether the three Helicobacter fragments are one printed Table 1. Correct the
earliest caption/continuation identity stage only if that evidence is direct.

Success would mean every resolved table has the appropriate
`paper_visual_inventory.json` record without changing its physical grid.

## 2. Support annotations in rotated coordinate frames

Implement the existing
`docs/implementation/rotated_cell_text_annotations_implementation_plan.md`
only after confirming a single reversible transformation between positioned
character geometry and rotated table-cell geometry. The target is the same
annotation contract already used by upright tables, not a separate marker
inference path.

Success would remove the 17 unsupported-coordinate diagnostics while retaining
exact raw text and source character/span references.

## 3. Complete paper-wide visual inventory and reference resolution

Figure coverage is the dominant paper-context gap: 301 figure references and
128 table references remain unresolved. Extend the shared positioned-text and
caption evidence so actual in-paper figures and tables receive stable visual
records before attempting broader reference matching.

Do not resolve references from label text alone when no corresponding visual
object exists. Preserve external, bibliographic, and supplementary references
as separate statuses.

## 4. Improve semantic and value interpretation after geometry is verified

Start with the 20 rescued logical tables carrying error-level quality
diagnostics. For each one, confirm extraction, row ownership, header paths, and
continuation membership before changing value or variable rules. Prioritize
repeated structural patterns behind unknown rows, labels with values but no
variable, non-numeric statistical columns, and weak value-pattern recognition.

Success should reduce unknown semantic rows and error-level quality diagnostics
without changing physical cells or inventing rows, columns, or levels.

## 5. Review non-stub blank leaves and the one unresolved upper group

Inspect the 13 non-stub blank leaf labels individually and the unresolved upper
header run in `periodontis2.pdf`, PDF page 19, printed Table 5. Accept intentional
blank/spanning leaves explicitly; change grouping only where positioned text,
rules, and column coverage prove a different relationship.

The 34 ordinary blank stub leaves are not improvement targets.

## 6. Make quality status easier to interpret

The current `rescued` category combines usable tables with varying warning and
error severity. Improve structured R/Python summaries so users can distinguish
successful parses with minor warnings from those with error-level semantic
uncertainty. This should be an inspection/reporting improvement, not a change
to extraction or pass/fail meaning without separate approval.

## 7. Confirm the two papers with no target table objects

Visually audit the two no-table PDFs once. If they contain no in-scope
Table 1-style grid, record that as accepted corpus coverage. If an in-scope
table exists, find the earliest missing caption, region, rule, or positioned
grid evidence before proposing extraction work.

## Items that should remain fail-closed unless new evidence appears

- The two MDPI marker glyphs retained in `base_text` without exact alignment.
- The 13 `NutritionEx.pdf` numeric bibliography candidates that have no local
  footnote definition.
- The seven continuation/caption rows left outside header and body ownership.
- DOI lines that do not satisfy exact visual-object and caption-adjacency
  evidence.
- The smaller legacy continuation review counts, because canonical continuation
  resolution already represents all 13 accepted integrations.
