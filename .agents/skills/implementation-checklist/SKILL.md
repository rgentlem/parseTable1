---
name: implementation-checklist
description: Design and implement small, explicit, reviewable software changes. Use for implementation checklists, staged code changes, or narrowly scoped fixes. Treat about 100 changed lines as a planning estimate, while keeping atomic cutovers together when splitting them would create an unsafe intermediate state. Stop immediately on any material implementation problem and return for redesign and approval.
---

# Implementation checklist

Design and implement software changes as a sequence of small, explicit steps.

## General rules

* Keep each step independently reviewable. Independently reviewable does not require independently deployable.
* Treat about 100 changed lines as a planning estimate, not a hard limit.
* Do not split an atomic migration, cutover, schema transition, or ownership change solely to meet the size estimate when doing so would create an inconsistent intermediate state, parallel authoritative paths, or temporarily invalid artifacts.
* When a coherent atomic step must exceed the estimate, explain why it must remain atomic and keep it limited to that one outcome.
* Each step must have one clear outcome.
* Use four to ten detailed task bullets per step.
* Name the likely files, functions, interfaces, and validation commands.
* Do not combine unrelated work.
* Do not make unrelated cleanup changes.
* Do not commit or push unless explicitly requested.

## Minimal implementation rule

Write only the code needed for the direct requested behavior.

Do not add:

* Extra infrastructure.
* General-purpose frameworks or abstractions.
* Test harnesses beyond focused tests needed for the change.
* Compatibility layers that were not requested.
* Hooks for hypothetical future requirements.
* Configuration for planned expansions.
* Premature extensibility.
* Unrelated refactoring.
* Defensive machinery for situations outside the stated task.

Prefer:

* Existing repository patterns.
* Existing dependencies.
* Existing abstractions when they fit directly.
* The smallest coherent diff.
* Simple local code over a new abstraction used only once.

## Checklist format

Use this structure:

# Implementation checklist

## Goal

Briefly state the requested result.

## Scope

* In scope: ...
* Out of scope: ...
* Confirmed assumptions: ...

## Step 1 — Outcome-oriented title

**Objective:** One completed result.

**Expected size:** Approximate changed-line count, normally 100 lines or fewer. If the estimate is larger, state why splitting the step would violate atomicity or create an unsafe intermediate state.

**Likely files:**

* `path/to/file`
* `path/to/test`

**Tasks:**

* Four to ten explicit implementation actions.
* State exactly what behavior will change.
* Identify relevant functions, types, or interfaces.
* Include focused tests or validation.
* Exclude unrelated cleanup and future-oriented work.

**Validation:**

* Exact commands to run.
* Exact observable success criteria.

**Review checkpoint:**

* What the resulting diff should contain.
* What it should explicitly not contain.
* For an atomic cutover, confirm that the step leaves no parallel authoritative path or inconsistent intermediate artifact.

Repeat for each step.

End with:

`Ready to implement after approval.`

## Execution

When asked only for a checklist:

* Inspect the relevant repository files.
* Present the checklist.
* Do not edit code.
* Wait for approval.

When explicitly asked to design and implement:

* Inspect the relevant files.
* Present a concise checklist.
* Implement the steps in order.
* Validate each step before beginning the next.
* Do not materially depart from the approved checklist.

When only selected steps are approved:

* Implement only those steps.
* Do not start later steps.

## Material-error stop rule

Stop immediately when any material problem is observed.

A material problem includes:

* A changed test fails.
* Existing relevant behavior regresses.
* The code does not build, type-check, lint, or run as expected.
* A confirmed checklist assumption is false.
* The selected API behaves differently from the inspected code or documentation.
* The requested behavior cannot be achieved with the approved design.
* The step requires an unapproved dependency, abstraction, configuration change, or architectural decision.
* The implementation is becoming materially larger than planned.
* The observed repository state differs materially from the facts used to design the step.
* Validation produces unexpected output relevant to the change.

After a material problem is observed:

1. Stop all task-related implementation.
2. Do not attempt a repair.
3. Do not try an alternative approach.
4. Do not modify tests to accommodate the implementation.
5. Do not broaden the scope.
6. Do not revert, rewrite, or continue task-related code unless needed to prevent repository corruption.
7. Return to the user with a factual failure report.
8. Prepare a redesigned checklist for discussion.
9. Wait for explicit approval before implementing the redesign.

## Factual reporting rule

Failure reports must contain only observed facts.

Do not include:

* Guesses.
* Suppositions.
* Probable causes stated as facts.
* Unverified explanations.
* Claims about what a dependency or API “must be doing.”
* Claims about repository intent not established by code, tests, documentation, or user statements.

Clearly separate:

* Observed facts.
* Unknowns.
* Questions requiring investigation.
* Proposed redesign choices.

A possible explanation may be listed only as an unverified question to investigate, not as a conclusion.

## Failure report format

# Implementation stopped

## Failed step

* Step number and objective.

## Observed facts

* Commands run.
* Exact pass or failure status.
* Relevant error output.
* Relevant unexpected behavior.
* Files changed.
* Approximate diff size.
* Current test, build, lint, and type-check status.

## Confirmed conflict with the approved design

* State exactly which approved assumption, expected behavior, or validation criterion was contradicted.
* Cite the code, test, command output, or documentation that establishes the conflict.

## Unknowns

* List facts that have not yet been established.
* Do not offer explanations for them.

## Current repository state

* State whether task-related changes remain.
* State whether the repository currently builds or passes relevant tests.
* State whether the partial change is usable.
* State whether any files may need to be reverted, without performing the revert.

## Redesigned checklist

Provide a complete revised checklist based only on confirmed facts.

Do not implement it.

## Decision required

State the specific approval or design decision needed.

End with:

`No further task-related changes were made after the material problem was identified.`

## Mechanical errors

The agent may correct a non-material operational mistake without returning to the user, including:

* A command typo.
* A wrong test filename or path.
* A missing quote.
* A malformed shell invocation.
* Accidentally invoking the wrong executable when the intended command is unambiguous.
* Re-running a command interrupted for reasons unrelated to the code.

This exception does not permit:

* Editing source code.
* Editing test expectations.
* Changing configuration.
* Adding a dependency.
* Changing the implementation design.
* Fixing code after a relevant test or validation failure.

When uncertain whether an issue is mechanical or material, treat it as material and stop.

## Completion report

After all approved steps pass:

# Implementation complete

## Completed steps

* List the completed steps and resulting behavior.

## Files changed

* List files by step.
* Give approximate changed-line counts.

## Validation

* List commands and outcomes.
* State any validation not performed.

## Scope confirmation

* Confirm the implementation contains only code needed for the direct task.
* Confirm no unapproved infrastructure, future-oriented code, or unrelated refactoring was added.
