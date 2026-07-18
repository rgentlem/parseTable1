# Codex Task: Phase 1 Implementation

Read the full architecture spec:

docs/design/codex_build_spec.md

Also read project constraints in:

AGENTS.md

---

# Task

Implement **Phase 1 only** of the project.

Do not implement later phases yet.

Phase 1 focuses on **project scaffolding and schemas**.

---

# Phase 1 Scope

Create the basic Python package structure and core data models.

Implement:

1. Package scaffold
2. Configuration module
3. Typed schemas
4. CLI scaffold
5. Basic tests

Do NOT implement:

- PDF extraction
- normalization
- heuristic parsing
- LLM integration
- validation pipeline

Those belong to later phases.

---

# Required Directory Structure

Create this package layout:

table1_parser/
  __init__.py
  cli.py
  config.py
  logging.py

  schemas/
    extracted_table.py
    normalized_table.py
    parsed_table.py

tests/

---

# Schemas to Implement

Implement typed records for:

### TableCell
Fields:

row_idx  
col_idx  
text  
page_num (optional)  
bbox (optional)  
extractor_name (optional)  
confidence (optional)

---

### ExtractedTable

Fields:

table_id  
source_pdf  
page_num  
title  
caption  
n_rows  
n_cols  
cells (list of TableCell)  
extraction_backend  
metadata

---

### RowView

Fields:

row_idx  
raw_cells  
first_cell_raw  
first_cell_normalized  
first_cell_alpha_only  
nonempty_cell_count  
numeric_cell_count  
has_trailing_values  
indent_level  
likely_role

---

### NormalizedTable

Fields:

table_id  
title  
caption  
header_rows  
body_rows  
row_views  
n_rows  
n_cols  
metadata

---

### ParsedLevel

Fields:

label  
row_idx

---

### ParsedVariable

Fields:

variable_name  
variable_label  
variable_type  
row_start  
row_end  
levels  
confidence

---

### ParsedColumn

Fields:

col_idx  
column_name  
column_label  
inferred_role  
confidence

---

### ValueRecord

Fields:

row_idx  
col_idx  
variable_name  
level_label  
column_name  
raw_value  
value_type  
parsed_numeric  
parsed_secondary_numeric  
confidence

---

### ParsedTable

Fields:

table_id  
title  
caption  
variables  
columns  
values  
notes  
overall_confidence

---

# CLI Stub

Create a CLI command using typer or argparse.

Command:

table1-parser

Subcommands:

extract
parse

For Phase 1 these commands should only print:

"Feature not implemented yet"

---

# Config Module

Create `config.py` with configuration settings such as:

default_extraction_backend  
llm_model  
max_table_candidates  
heuristic_confidence_threshold

Use a typed settings structure chosen for demonstrated value.

---

# Logging

Create a simple logging configuration in `logging.py`.

Provide a function:

get_logger(name)

---

# Tests

Create pytest tests for:

1. schema validation
2. object creation
3. serialization
4. CLI import

Tests should confirm models can be instantiated and serialized.

---

# Deliverables

After Phase 1:

The repository should contain:

- working Python package
- typed schemas
- CLI stub
- config module
- tests passing with pytest

The code should import correctly and install locally.

---

# Coding Style

Follow rules in AGENTS.md:

- type hints everywhere
- typed records
- modular structure
- docstrings on public classes

---

# Final Instruction

Implement Phase 1 only.

Do not add extraction or parsing logic yet.
