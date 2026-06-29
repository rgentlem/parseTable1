---
name: implementation-goal-checklist
description: Use when turning a parseTable1 project goal, completion priority, design note, TODO item, or implementation phase into a structured checkbox implementation plan. Produces consistent step checklists grounded in existing docs, real-paper evidence, and known failure modes rather than speculative helpers or broad unit-test plans.
---

# Implementation Goal Checklist

## Source Context

Before writing a checklist, read:

- `AGENTS.md`
- `docs/design/codex_build_spec.md`
- `docs/design/design_index.md`
- `docs/implementation/parser_todo.md`

Then read the design or implementation documents that directly match the goal.
Use `/Users/robert/Projects/Epiconnector/testpapers` and recent batch outputs
only as observed evidence. Do not invent guides, helper surfaces, or test plans
from assumptions.

## Checklist Shape

Write a compact implementation plan with:

- the goal in one or two sentences
- the evidence or source documents used
- checkbox sections for design contract, implementation, artifacts/docs, and
  verification
- stable goal-scoped IDs on every checkbox item, such as `G1.1`, `G1.2`, or
  `P2.1`, so the user can refer to individual steps unambiguously
- acceptance criteria when the goal is large enough to need them
- a short "Do Not Do" section when scope control matters

Prefer broad parser-stage tasks over tiny helper-level tasks. Defer R helpers,
diagnostics, and convenience APIs unless real usage or observed failures justify
them. Verification should emphasize known-failure regressions and artifact
contracts, not broad unit-test expansion for its own sake.

Keep implementation guidance clear, concise, and minimal. Prefer direct changes
inside the existing pipeline modules. Do not propose single-use helper
functions, speculative class structures, or tests that are not tied to known
failures or stable artifact contracts.

## Output Template

```markdown
## Goal

<One or two sentences.>

## Evidence Used

- `<doc-or-output>`

## Implementation Checklist

### Design Contract

- [ ] **G1.1** ...

### Implementation

- [ ] **G1.2** ...

### Artifacts And Documentation

- [ ] **G1.3** ...

### Verification

- [ ] **G1.4** ...

## Acceptance Criteria

- [ ] **G1.5** ...

## Do Not Do

- [ ] **G1.6** ...
```
