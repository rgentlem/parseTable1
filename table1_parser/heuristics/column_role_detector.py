"""Detect likely semantic roles for table columns from normalized headers."""

from __future__ import annotations

import re

from table1_parser.column_header_schema import column_header_descriptors
from table1_parser.heuristics.header_role_patterns import detect_p_value_header
from table1_parser.heuristics.models import ColumnRoleGuess
from table1_parser.schemas import ColumnHeaderSchema, NormalizedTable
from table1_parser.text_cleaning import clean_text


def detect_column_roles(
    table: NormalizedTable,
    column_schema: ColumnHeaderSchema | None = None,
) -> list[ColumnRoleGuess]:
    """Detect likely roles for each normalized table column."""
    labels_by_col_idx: dict[int, str] = {}
    if column_schema is not None and column_schema.table_id == table.table_id:
        for descriptor in column_header_descriptors(column_schema):
            parts = [*descriptor.header_group_labels, descriptor.leaf_label]
            labels_by_col_idx[descriptor.col_idx] = clean_text(" ".join(part for part in parts if part))
    else:
        cleaned_rows = table.metadata.get("cleaned_rows", [])
        grid = cleaned_rows if isinstance(cleaned_rows, list) else []
        header_rows = [grid[row_idx] for row_idx in table.header_rows if row_idx < len(grid)]
        if not header_rows:
            return [
                ColumnRoleGuess(col_idx=col_idx, header_label="", role="unknown", confidence=0.0)
                for col_idx in range(table.n_cols)
            ]
        for col_idx in range(table.n_cols):
            parts = [row[col_idx] for row in header_rows if col_idx < len(row) and row[col_idx]]
            labels_by_col_idx[col_idx] = clean_text(" ".join(parts))

    guesses: list[ColumnRoleGuess] = []
    for col_idx in range(table.n_cols):
        label = labels_by_col_idx.get(col_idx, "")
        lowered = label.lower()
        if not label:
            role, confidence = "unknown", 0.4
        elif p_value_match := detect_p_value_header(label, col_idx, table.n_cols):
            role, confidence = "p_value", p_value_match.confidence
        elif "smd" in lowered:
            role, confidence = "smd", 0.98
        elif "overall" in lowered or lowered in {"all", "total"}:
            role, confidence = "overall", 0.95
        elif lowered in {"control", "controls"}:
            role, confidence = "comparison_group", 0.92
        elif lowered in {"case", "cases"}:
            role, confidence = "group", 0.92
        elif lowered.startswith("q") and len(lowered) <= 3:
            role, confidence = "group", 0.8
        elif "(" in lowered and re.search(r"\bn\s*=", lowered):
            role, confidence = "group", 0.78
        else:
            role, confidence = "unknown", 0.45
        guesses.append(
            ColumnRoleGuess(
                col_idx=col_idx,
                header_label=label,
                role=role,
                confidence=confidence,
            )
        )
    return guesses
