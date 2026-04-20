---
format: pdf
---

# parseTable1 Benchmark Error Log

This document summarizes recurring parsing errors identified during manual review of benchmark papers processed by `parseTable1` using the deterministic pipeline (`--no-llm-semantic`).

Current review focus follows the following:

-   prioritize **Table 1**

-   prioritize **variable names** and **variable types**

-   compare parser output against the real Table 1 in the PDF

-   identify recurring failure modes before attempting fixes

------------------------------------------------------------------------

# Overall Summary

Across the reviewed papers, the most important failure modes are:

1.  **Catastrophic Table 1 structure collapse**
    -   all row variables merged into one giant variable, or
    -   `variables: []`, with no usable parsed rows
2.  **Column collapse**
    -   all columns merged into a single long `column_name`
    -   grouped headers not reconstructed correctly
3.  **Missing subgroup / level rows**
    -   e.g., `<60 years`, `≥60 years` missing entirely
4.  **False positive table extraction**
    -   pages without real tables are sometimes incorrectly extracted as tables
5.  **Minor normalization / OCR-style formatting issues**
    -   symbols such as `±`, `≥`, en dash, etc. appear as unicode escapes
    -   variable names are sometimes normalized too aggressively

These findings suggest that the most serious current problems occur **before semantic interpretation**, likely in one or more of:

-   extraction

-   normalization

-   row segmentation

-   column segmentation

-   grid reconstruction

-   table-definition building

LLM-related components are **not** the priority at this stage.

------------------------------------------------------------------------

# fld.pdf

## Ground-truth status

Table 1 is mostly parsed, but several row/level details are missing or slightly distorted. This is **not a catastrophic failure**, but it still contains important errors.

------------------------------------------------------------------------

## 1. parsed_tables.json

Structure:

-   `table_id`

-   `title`

-   `caption`

-   `variables`

-   `columns`

-   `values`

-   `notes`

-   `overall_confidence`

### 1.1 variables

#### Errors

-   `<60 years` and `≥60 years` were not recognized / are missing.
    -   As a result, the entire subgroup information for these two rows is absent from the parsed output.
    -   This is important because these are valid categorical levels / stratification rows.
-   Some `variable_name` / `variable_label` outputs are not ideal.
    -   Example:
        -   `variable_name`: `BMI kg m2`
        -   `variable_label`: `BMI, kg/m2, mean(SD)`
    -   This normalization is not catastrophic, but it reduces readability and consistency.

#### Minor formatting issues

-   `-` may appear as `\u2013`
-   `≥` may appear as `\u2265`

#### Analysis

This paper suggests that the parser can recover the general structure of Table 1, but may fail on:

-   subgroup rows

-   special symbols

-   variable-label normalization

This is a **medium-severity** issue, not a full structural failure.

------------------------------------------------------------------------

### 1.2 columns

#### Errors

The following column names do not appear to be cleanly reconstructed:

-   `Overall n 3 961`

-   `Non FLD group n 1 584`

-   `FLD group n 2 377`

These seem to preserve the overall meaning, but the formatting is degraded and likely not normalized correctly.

#### Analysis

This suggests imperfect column-header normalization rather than total column collapse.

------------------------------------------------------------------------

### 1.3 values

#### Minor formatting issues

-   `±` appears as `\u00b1`

#### Possible issue

-   For some categorical and binary variables, P-values may not be attached correctly.
-   Example:
    -   `Race, n (%)` may have no values in the first few columns for a certain row object, while the p-value exists in the last column.

#### Analysis

This may or may not be a serious issue depending on intended downstream use. If P-values are expected to be preserved as part of the parsed table, this should be treated as a real bug.

------------------------------------------------------------------------

### 1.4 notes

#### Question

What is `notes` intended to represent?

#### Working interpretation

Based on observed outputs, `notes` appears to be reserved for parser warnings, sanity checks, or post-processing consistency messages. In this paper it does not seem to contain critical information.

------------------------------------------------------------------------

## 2. table_definitions.json

Structure:

-   `table_id`

-   `title`

-   `caption`

-   `variables`

-   `column_definition`

-   `notes`

-   `overall_confidence`

### Errors

-   Same issue as above:
    -   `<60 years`
    -   `≥60 years` were not recognized / are missing.

#### Analysis

This indicates the loss happens **before final parsed output**, likely already at the table-definition stage.

------------------------------------------------------------------------

## 3. normalized_tables.json

### Errors

-   Same issue:
    -   `<60 years`
    -   `≥60 years` are missing here as well.

#### Analysis

This suggests the problem likely occurs **during extraction or normalization**, not only in semantic interpretation.

------------------------------------------------------------------------

## 4. table_profiles.json

### Observation

-   For all tables other than Table 1, `should_run_llm_semantics` is set to `false`.

#### Interpretation

This is probably intentional, since the project is currently specialized for Table 1-style parsing. Not necessarily a bug.

------------------------------------------------------------------------

# periodontitis.pdf

## Ground-truth status

This is a **catastrophic Table 1 failure**.

In addition, page 11 does not contain a real table, but the system extracted one anyway. Although current evaluation is focused on Table 1, this false positive extraction is still a serious upstream issue.

------------------------------------------------------------------------

## 1. parsed_tables.json

### 1.1 variables

#### Error

All variables were collapsed into one giant variable, making the output unusable.

Observed example:

-   `variable_name` contains the concatenation of essentially the entire left column of Table 1

#### Severity

**Critical**

#### Analysis

Likely causes:

-   **multi-level header handling failure**

-   **section + level mixed row structure**

-   **few visual ruling lines / whitespace-based layout**

-   possible failure in row segmentation or normalization joining

This is not a minor labeling error; it is a full structural collapse.

------------------------------------------------------------------------

### 1.2 columns

#### Error

Columns were also collapsed into a single merged column.

Observed example:

-   `column_name`: `Healthy lifestyle score All n 5611 0 1 n 1815 2 3 n 3233 4 6 n 563 p value`

#### Severity

**Critical**

#### Analysis

This indicates failure in column-boundary recovery, probably related to multi-level grouped headers.

------------------------------------------------------------------------

### 1.3 values

#### Error

Because both rows and columns failed structurally, values are unusable.

-   all values are effectively merged into one block
-   no meaningful row/column mapping remains

#### Severity

**Critical**

------------------------------------------------------------------------

### 1.4 notes

#### Observation

No useful notes are present for this catastrophic failure.

#### Analysis

This suggests the parser currently lacks a strong sanity-check or fallback warning for this failure mode.

------------------------------------------------------------------------

## 2. table_definitions.json

### Error

Same as `parsed_tables.json`:

-   rows not reconstructed correctly

-   columns not reconstructed correctly

-   output effectively unusable

#### Severity

**Critical**

#### Analysis

The failure occurs before final value parsing and is likely structural rather than semantic.

------------------------------------------------------------------------

# stroke.pdf

## Ground-truth status

The parser extracted a false table on page 12, although no real table exists there.

This is an upstream extraction problem.

------------------------------------------------------------------------

## 1. parsed_tables.json

### 1.1 variables

#### Error

-   The first variable, `Age, years`, is missing.

#### Severity

**Medium**

#### Analysis

This suggests partial row loss rather than total structural collapse.

------------------------------------------------------------------------

## Additional issue

-   Page 12 was incorrectly identified as containing a table.

#### Severity

**Medium to High**

#### Analysis

False positives in table extraction can pollute downstream benchmarking and may need better filtering.

------------------------------------------------------------------------

# metabolic.pdf

## Ground-truth status

This is a **catastrophic Table 1 failure**.

------------------------------------------------------------------------

## 1. parsed_tables.json

### Error

-   Table 1 parsing completely failed.
-   `variables: []`
-   no usable row variables were recovered
-   columns appear collapsed into a single merged header-like column

#### Severity

**Critical**

#### Analysis

This appears to be the same bug family as `periodontitis.pdf`, but with an even harsher failure mode: instead of collapsing all rows into one giant variable, the parser returns **zero variables**.

This strongly suggests failure in:

-   row segmentation

-   column segmentation

-   structure reconstruction

------------------------------------------------------------------------

# pad.pdf

## Ground-truth status

This is a **catastrophic Table 1 failure**.

------------------------------------------------------------------------

## 1. parsed_tables.json

### Error

-   Same failure pattern as `metabolic.pdf`
-   `variables: []`
-   no usable row variables
-   table content appears collapsed into a single merged column

#### Severity

**Critical**

#### Analysis

This is another instance of the same recurring failure mode seen in:

-   `periodontitis.pdf`

-   `metabolic.pdf`

Together these papers indicate that the parser is currently unstable on a common class of NHANES Table 1 layouts.

------------------------------------------------------------------------

# Cross-paper Failure Pattern

## Recurring catastrophic failure family

Observed in:

-   `periodontitis.pdf`

-   `metabolic.pdf`

-   `pad.pdf`

### Pattern

-   Table 1 structure is not reconstructed
-   rows are merged into one variable or lost entirely
-   columns collapse into one merged string
-   values become unusable or disappear

### Likely root-cause region

These failures most likely originate in the deterministic pipeline, especially one or more of:

-   extracted table block segmentation

-   normalized row boundary detection

-   multi-level header reconstruction

-   column inference without strong vertical ruling lines

-   section-row versus indented-level handling

------------------------------------------------------------------------

# Priority for Fixing

## Highest priority

1.  **Catastrophic Table 1 structure failures**
    -   `periodontitis.pdf`
    -   `metabolic.pdf`
    -   `pad.pdf`

## Medium priority

2.  Missing row/level recovery
    -   `fld.pdf`
    -   `stroke.pdf`

## Lower priority / cosmetic

3.  Symbol normalization issues
    -   `±`
    -   `≥`
    -   en dash / unicode escapes
4.  Variable-name prettification
    -   e.g. `BMI kg m2`

------------------------------------------------------------------------

# Suggested next debugging target

The next debugging target should be the deterministic pipeline stage responsible for:

-   row segmentation

-   column segmentation

-   multi-level header handling

-   prevention of full table collapse

A useful sanity check to add would be:

-   detect when a large Table 1 yields either:

    -   `variables: []`, or

    -   exactly one giant variable containing many newline-separated row labels

Such cases should trigger:

-   a warning

-   a fallback path

-   or at minimum a lower-confidence structural failure signal

------------------------------------------------------------------------

# Current conclusion

The most serious current issue is **not semantic interpretation**, but **structural reconstruction failure** in deterministic Table 1 parsing.

Before improving LLM behavior, the parser needs to reliably recover:

-   row variables

-   grouped headers

-   levels

-   columns

for standard NHANES-style Table 1 layouts.