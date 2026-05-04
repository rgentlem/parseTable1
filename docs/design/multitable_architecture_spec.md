# Multitable Routing and Estimate-Table Spec

This document specifies how the parser should evolve from a mostly Table 1-oriented pipeline into a multi-family table parser that can handle:

- descriptive characteristic tables
- estimate / model-result tables
- unknown or unsupported tables

The main motivating examples are papers where:

- Table 1 and Table 2 are both descriptive characteristic tables with different subject matter
- Table 3 and Table 4 report model estimates, confidence intervals, and p-values

The current repository is strongest on the first family and should not force all later tables into the same heuristic path.

## Goals

- keep the pipeline staged, inspectable, and deterministic-first
- avoid applying Table 1 row/level heuristics to estimate-result tables
- skip semantic LLM calls for tables that do not need them
- make model-result tables first-class outputs rather than edge cases
- preserve the ability to use paper context later for model interpretation

## Non-Goals

- do not collapse all tables into one universal schema
- do not use the LLM for raw value extraction
- do not require model interpretation before deterministic estimate parsing can succeed
- do not route tables by biomedical topic such as demographic vs clinical

## 1. Core Design Change

Add a routing stage after normalization:

```text
PDF
-> ExtractedTable
-> NormalizedTable
-> TableProfile
-> family-specific definition
-> family-specific parsed output
```

This keeps the current separation principles intact while preventing one heuristic stack from trying to explain every table.

## 2. Table Families

The parser should classify tables by structural and semantic family, not by the paper author's numbering.

### `descriptive_characteristics`

Use for tables whose rows are characteristics or variables and whose values are descriptive summaries.

Typical cues:

- rows represent variables and categorical levels
- cells look like `n (%)`, `mean (SD)`, `median (IQR)`, or scalar counts
- columns represent groups such as overall, exposure groups, treatment groups, or strata
- table titles often contain phrases like `baseline characteristics`, `characteristics`, `clinical characteristics`, `demographic characteristics`

This family includes both:

- classic demographic Table 1 tables
- clinical-characteristics tables that are structurally the same but appear as Table 2 or later

### `estimate_results`

Use for tables whose rows report model terms, outcomes, contrasts, or strata and whose values are estimates.

Typical cues:

- cells contain estimates with confidence intervals
- p-value columns are explicit and frequent
- headers contain model labels such as `unadjusted`, `adjusted`, `model 1`, `model 2`
- titles and captions mention `hazard ratio`, `odds ratio`, `risk ratio`, `regression`, `association`, `multivariable`, `cox`, `logistic`, `linear`

Typical printed values:

- `1.42 (1.10, 1.83)`
- `0.78 [0.65, 0.94]`
- `1.22`
- `<0.001`

### `unknown`

Use when a table does not clearly fit either supported family.

The parser should preserve the normalized table and routing evidence even when no family-specific parse is attempted.

## 3. `TableProfile`

Add a new canonical schema:

- `table1_parser/schemas/table_profile.py`

and a new persisted file:

- `outputs/papers/<paper_stem>/table_profiles.json`

Each profile should contain at least:

- `table_id`
- `title`
- `caption`
- `table_family: Literal["descriptive_characteristics", "estimate_results", "unknown"]`
- `should_run_llm_semantics: bool`
- `family_confidence: float | None`
- `evidence: list[str]`
- `notes: list[str]`

### Design Intent

`TableProfile` should explain:

- what currently implemented parser route can handle the table
- whether semantic LLM work is worth doing
- why that decision was made

It should be a direct deterministic artifact, not an implicit branch hidden in CLI code. It is provisional route metadata, not a second table taxonomy. As the paper-level table inventory matures, route selection should be derived from or checked against the broader `table_category` decision.

## 4. Routing Rules

### For `descriptive_characteristics`

Run:

- existing row/level grouping heuristics
- existing `TableDefinition`
- current `ParsedTable` value parsing
- optional semantic LLM refinement when useful

Set:

- `should_run_llm_semantics = True` for ambiguous or context-sensitive tables
- `should_run_llm_semantics = False` for highly regular descriptive tables if later performance tuning requires it

### For `estimate_results`

Run:

- deterministic estimate-table definition
- deterministic estimate value parsing
- no semantic LLM row/level interpretation by default

Set:

- `should_run_llm_semantics = False`

Rationale:

- estimate tables are often explicit in the printed cells
- row/level semantics are less ambiguous than in descriptive tables
- the useful future LLM work is about model context, not cell parsing

### For `unknown`

Run:

- no family-specific final parser by default
- preserve normalized and routing artifacts

Set:

- `should_run_llm_semantics = False`

until a specific supported family is added.

## 5. Descriptive-Characteristics Family

This family should absorb what is currently thought of as "Table 1 parsing."

### Naming Change

In code and docs, the current Table 1-specific heuristic path should gradually be renamed from a Table-1-only mental model to:

- `descriptive_characteristics`

The goal is to support:

- demographic baseline tables
- clinical characteristic tables
- other row-variable summary tables with the same structural conventions

### Existing Outputs

This family may continue using:

- `TableDefinition`
- `ParsedTable`

with the current row-variable, level, and long-format value design.

## 6. Estimate-Results Family

This family needs its own value-free and value-bearing schemas.

### 6.1 `EstimateTableDefinition`

Add a new canonical schema:

- `table1_parser/schemas/estimate_table_definition.py`

and a new persisted file:

- `outputs/papers/<paper_stem>/estimate_table_definitions.json`

This schema should describe table semantics without storing parsed numeric values.

Suggested top-level fields:

- `table_id`
- `title`
- `caption`
- `metric_definition`
- `row_definition`
- `column_definition`
- `notes`
- `overall_confidence`

Suggested components:

#### `EstimateMetricDefinition`

- `estimate_metric: Literal["hr", "or", "rr", "beta", "difference", "unknown"]`
- `metric_label: str | None`
- `ci_style: Literal["paren_comma", "bracket_comma", "separate_columns", "unknown"]`
- `confidence: float | None`

#### `EstimateRowTerm`

Represents one row-level reported term.

Suggested fields:

- `row_idx`
- `term_label`
- `term_name`
- `term_role: Literal["predictor", "outcome_level", "contrast", "subgroup", "reference", "unknown"]`
- `parent_term_label: str | None`
- `reference_hint: str | None`
- `confidence: float | None`

#### `EstimateColumn`

Represents one estimate-table column.

Suggested fields:

- `col_idx`
- `column_label`
- `column_name`
- `inferred_role: Literal["estimate", "ci", "ci_lower", "ci_upper", "p_value", "model", "statistic", "unknown"]`
- `model_label: str | None`
- `adjustment_hint: str | None`
- `confidence: float | None`

#### `EstimateColumnDefinition`

Suggested fields:

- `columns`
- `modeling_layout: Literal["single_model", "multi_model", "separate_p_value", "unknown"]`
- `confidence: float | None`

### 6.2 `ParsedEstimateTable`

Add a new canonical schema:

- `table1_parser/schemas/parsed_estimate_table.py`

and a new persisted file:

- `outputs/papers/<paper_stem>/parsed_estimate_tables.json`

Suggested top-level fields:

- `table_id`
- `title`
- `caption`
- `terms`
- `models`
- `results`
- `notes`
- `overall_confidence`

Suggested `EstimateResultRecord` fields:

- `row_idx`
- `term_label`
- `term_name`
- `model_name`
- `estimate_metric`
- `estimate`
- `ci_lower`
- `ci_upper`
- `p_value`
- `raw_estimate_text`
- `raw_ci_text`
- `raw_p_value_text`
- `confidence`

### Why Not Reuse `ParsedTable`

Estimate-result tables encode different semantics:

- rows are often terms or contrasts, not categorical levels
- values are inferential statistics, not descriptive summaries
- model identity is often central

Trying to force these into `ParsedVariable` and `ValueRecord` would blur the distinction between descriptive and inferential outputs.

## 7. Model Understanding

For estimate-result tables, "understanding the model" should be treated as a distinct semantic task.

### Deterministic Table-Only Understanding

The parser should infer from table text alone when possible:

- estimate metric from title, caption, header, or footnotes
- model labels such as `Model 1`, `Model 2`, `Unadjusted`, `Adjusted`
- whether CIs are inline or separated into their own columns
- whether p-values are in a dedicated column

### Context-Aware Model Interpretation

Later, a separate context stage may interpret:

- what model family was used
  - logistic regression
  - Cox proportional hazards model
  - linear regression
  - mixed-effects model
- what covariates define `Adjusted` or `Model 2`
- what outcome the estimates refer to when the table alone is abbreviated

This should be a separate optional artifact, not mixed into deterministic value parsing.

Suggested future schema:

- `EstimateModelContext`

Suggested fields:

- `table_id`
- `model_name`
- `model_family`
- `outcome_label`
- `adjustment_description`
- `supporting_section_ids`
- `supporting_passages`
- `confidence`

## 8. LLM Use Policy

### `descriptive_characteristics`

LLM may be useful for:

- ambiguous parent vs level structure
- messy multi-row headers
- grouping-variable semantics

### `estimate_results`

LLM should not be used for:

- parsing estimate numbers
- parsing confidence intervals
- parsing p-values

LLM may later be useful for:

- understanding model family
- understanding the meaning of named models
- tying abbreviated headers to paper context

This means the estimate-table path should default to:

- deterministic parsing first
- optional later context interpretation second

## 9. CLI and Output Behavior

`table1-parser parse` should continue to run once per paper and write all available stage artifacts.

Target future output set:

- `extracted_tables.json`
- `normalized_tables.json`
- `table_profiles.json`
- `table_definitions.json` for `descriptive_characteristics` tables
- `parsed_tables.json` for `descriptive_characteristics` tables
- `estimate_table_definitions.json` for `estimate_results` tables
- `parsed_estimate_tables.json` for `estimate_results` tables
- `paper_markdown.md`
- `paper_sections.json`
- `table_contexts/*.json`

The parser should not require every family-specific output file to be populated for every paper.

## 10. Validation

Add family-specific validation modules:

- `table1_parser/validation/table_profile.py`
- `table1_parser/validation/estimate_table_definition.py`
- `table1_parser/validation/parsed_estimate_table.py`

Validation should ensure:

- routed families are from the allowed vocabulary
- row and column references exist in the normalized table
- estimate records do not invent rows or columns
- CI and p-value fields match visible printed cells

## 11. Implementation Order

Recommended order:

1. add `TableProfile` and deterministic routing
2. gate current semantic LLM calls using `TableProfile.should_run_llm_semantics`
3. rename the current Table 1 family concept to `descriptive_characteristics`
4. add `EstimateTableDefinition`
5. add `ParsedEstimateTable`
6. later add optional `EstimateModelContext`

This gets immediate value by preventing unnecessary LLM calls on obvious estimate-result tables even before the full estimate parser is finished.

## 12. Success Criteria

This change is successful when:

- a mixed paper can contain both descriptive and estimate-result tables
- Tables 1 and 2 in a paper can both route to `descriptive_characteristics`
- later estimate tables can route to `estimate_results`
- the parser skips current semantic LLM heuristics for estimate-result tables
- model-result tables are represented with their own explicit semantic outputs instead of being forced into Table 1-centric structures
