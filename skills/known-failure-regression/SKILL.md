---
name: known-failure-regression
description: Use when adding or changing parser tests for a known parse failure, real-paper structural variant, schema contract, output regression, or bug fix. Enforces failure-driven regression coverage instead of broad unit testing for coverage.
---

# Known Failure Regression

## Principle

Add tests only when they protect a known failure, a real-paper pattern, or a
core artifact contract that would be costly to break silently.

Do not add broad unit tests just to exercise helper functions or branches.

## Before Adding A Test

Identify the reason for the regression:

- real paper and PDF path, if applicable
- failing artifact or parser stage
- expected behavior
- prior wrong behavior
- why the case is general enough to keep

Prefer minimal fixtures that preserve the structural evidence needed by the
parser. Do not reduce examples so far that the test no longer represents the
failure mode.

## Test Shape

Prefer:

- compact `NormalizedTable`, `ColumnHeaderSchema`, or `TableDefinition`
  fixtures when the failure is semantic
- real-paper batch review when the failure depends on extraction geometry
- assertions on artifact contracts and important parsed records
- clear comments tying the test to the failure mode

Avoid:

- paper-specific vocabulary shortcuts
- compatibility aliases unless explicitly requested
- helper-only tests with no known failure
- large generated fixtures or logs in the repository

## Documentation

Update `docs/implementation/parser_todo.md` when the regression changes parser
priorities or records a newly understood failure mode.

If the fix changes schema shape, CLI outputs, or pipeline flow, also update the
relevant design docs and `docs/design/paper_parse_walkthrough.md`.
