---
name: epiconnector-parser-change
description: Use for any parseTable1 parser change involving extraction, normalization, column headers, table definitions, parsed values, schemas, CLI outputs, documentation contracts, R inspection surfaces, or commits. Enforces local Epiconnector context, critical-path discipline, doc updates, and failure-driven testing.
---

# Epiconnector Parser Change

## Start Here

Read these first:

- `AGENTS.md`
- `docs/design/codex_build_spec.md`
- `docs/design/design_index.md`
- `docs/implementation/parser_todo.md`

Also look in the broader local project when relevant:

- `/Users/robert/Projects/Epiconnector`
- `/Users/robert/Projects/Epiconnector/tableone`
- `/Users/robert/Projects/Epiconnector/testpapers`

## Change Discipline

Keep changes on the critical parser path. Prefer stable data structures and
pipeline artifacts over speculative helpers, display surfaces, compatibility
aliases, or broad test expansion.

For value parsing and table summaries:

- preserve raw source values
- store components as structured data, not formatted strings
- do not add scalar compatibility aliases unless explicitly requested
- defer R helpers until real usage shows repeated needs
- defer diagnostics until known review failures motivate them

## Documentation

Update docs in the same change when behavior changes.

Always update `docs/design/paper_parse_walkthrough.md` when changing:

- pipeline stage order
- CLI parse outputs
- persisted artifact contracts
- the purpose of intermediate artifacts
- paper-level or table-level outputs from `table1-parser parse`

Update `docs/implementation/parser_todo.md` when priorities are completed,
deferred, split, or corrected.

## Verification

Use targeted regression checks for known failures and core artifact contracts.
Do not add tests simply to cover helpers or branches.

Before commit-worthy parser changes:

- run relevant focused tests
- run `pytest` when feasible
- consider `$testpapers-batch-review` for broad output/schema changes
- report which tests and real-paper corpus runs were performed

## Generated Outputs

Treat `/Users/robert/Projects/Epiconnector/parseTable1/outputs` as generated
program output. It is gitignored and should not be staged or committed.
