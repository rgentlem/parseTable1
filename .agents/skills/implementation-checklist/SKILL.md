---
name: implementation-checklist
description: Create, maintain, and execute concise checkbox-based living checklists for small software changes, staged implementation, and work that may pause between steps. Keep atomic cutovers together when splitting them would create an unsafe intermediate state.
---

# Implementation checklist

Maintain a living guide to the remaining work, not a project history.

## Contents

Keep only:

- the goal and scope;
- essential results from completed steps;
- remaining steps in execution order;
- decisions, success conditions, and stop conditions needed to resume safely.

For each remaining step state its outcome, necessary actions, observable success,
and material reasons to stop. Omit code excerpts, file inventories, validation
commands, audit transcripts, old outputs, withdrawn ideas, and superseded
rationale. Collapse completed steps to the facts later steps still need.

Use Markdown checkboxes for every progress-bearing action and success condition:
`- [ ]` means pending and `- [x]` means complete. Update them as work proceeds.
Do not use checkboxes for scope statements or stop conditions.

## Execution

- Inspect the implementation before planning, but keep working notes out of the
  checklist.
- Implement only the approved step and validate its observable result.
- Stop before beginning another unapproved step.
- Treat roughly 100 changed lines as an estimate, never a reason to split an
  atomic ownership, schema, or authority cutover.
- Make the smallest coherent change. Add no unrelated cleanup, fallback,
  compatibility path, dependency, abstraction, or future infrastructure.
- Do not commit or push unless explicitly requested.
- After completion, reduce the step to its essential checkpoint and remove
  superseded material.

Stop immediately if validation fails, relevant behavior regresses, an
assumption is false, or the work needs an unapproved design decision or material
scope expansion. Do not repair or try another design. Report observed facts and
the decision required, then wait for approval.
