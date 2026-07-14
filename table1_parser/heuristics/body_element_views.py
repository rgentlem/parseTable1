"""Candidate-aware row views for semantic heuristics."""

from __future__ import annotations

import re
from collections.abc import Sequence

from table1_parser.schemas import BodyElementCandidate, BodyRowLabelCandidate, NormalizedTable, RowView
from table1_parser.text_cleaning import clean_text


NON_ALNUM_PATTERN = re.compile(r"[^A-Za-z0-9]+")
NON_ALPHA_PATTERN = re.compile(r"[^A-Za-z]+")
ALPHA_BOUNDARY_SEPARATOR_PATTERN = re.compile(r"(?<=[A-Za-z])[^A-Za-z0-9\s]+(?=[A-Za-z])")


def _replace_pattern_with_space(value: str, pattern: re.Pattern[str]) -> str:
    return clean_text(pattern.sub(" ", value))


def _preserve_alpha_boundaries(value: str) -> str:
    return ALPHA_BOUNDARY_SEPARATOR_PATTERN.sub(" ", value)


def _normalize_label_text(value: str) -> str:
    cleaned = _preserve_alpha_boundaries(clean_text(value))
    return _replace_pattern_with_space(cleaned, NON_ALNUM_PATTERN)


def _alpha_only_text(value: str) -> str:
    cleaned = _preserve_alpha_boundaries(clean_text(value))
    return _replace_pattern_with_space(cleaned, NON_ALPHA_PATTERN)


def table_with_body_element_candidates(
    table: NormalizedTable,
    body_element_candidates: Sequence[BodyElementCandidate] | None,
    body_row_label_candidates: Sequence[BodyRowLabelCandidate] | None = None,
) -> NormalizedTable:
    """Return a temporary semantic view with candidate values and labels in anchor cells."""
    table_candidates = [
        candidate
        for candidate in body_element_candidates or []
        if candidate.source_table_id == table.table_id
    ]
    label_candidates = [
        candidate
        for candidate in body_row_label_candidates or []
        if candidate.source_table_id == table.table_id
    ]
    if not table_candidates and not label_candidates:
        return table

    rows_by_idx = {row_view.row_idx: list(row_view.raw_cells) for row_view in table.row_views}
    consumed_nonanchor_cells: set[tuple[int, int]] = set()
    for candidate in table_candidates:
        if candidate.kind == "single_cell":
            continue
        for source_cell in candidate.source_cells:
            source_key = (source_cell.row_idx, source_cell.col_idx)
            anchor_key = (candidate.anchor_row_idx, candidate.anchor_col_idx)
            if source_key != anchor_key:
                consumed_nonanchor_cells.add(source_key)
    for candidate in label_candidates:
        for source_cell in candidate.source_cells:
            source_key = (source_cell.row_idx, source_cell.col_idx)
            anchor_key = (candidate.anchor_row_idx, candidate.anchor_col_idx)
            if source_key != anchor_key:
                consumed_nonanchor_cells.add(source_key)
    for row_idx, col_idx in consumed_nonanchor_cells:
        row = rows_by_idx.get(row_idx)
        if row is not None and 0 <= col_idx < len(row):
            row[col_idx] = ""
    for candidate in table_candidates:
        row = rows_by_idx.get(candidate.anchor_row_idx)
        if row is None or not 0 <= candidate.anchor_col_idx < len(row):
            continue
        row[candidate.anchor_col_idx] = candidate.candidate_text
    for candidate in label_candidates:
        row = rows_by_idx.get(candidate.anchor_row_idx)
        if row is None or not 0 <= candidate.anchor_col_idx < len(row):
            continue
        row[candidate.anchor_col_idx] = candidate.candidate_label

    row_views: list[RowView] = []
    for row_view in table.row_views:
        raw_cells = rows_by_idx.get(row_view.row_idx, row_view.raw_cells)
        cleaned_cells = [clean_text(cell) for cell in raw_cells]
        first_cell_raw = raw_cells[0] if raw_cells else ""
        trailing_cells = [cell for cell in cleaned_cells[1:] if cell]
        row_views.append(
            row_view.model_copy(
                update={
                    "raw_cells": raw_cells,
                    "first_cell_raw": first_cell_raw,
                    "first_cell_normalized": _normalize_label_text(first_cell_raw),
                    "first_cell_alpha_only": _alpha_only_text(first_cell_raw),
                    "nonempty_cell_count": sum(bool(cell) for cell in cleaned_cells),
                    "numeric_cell_count": sum(any(char.isdigit() for char in cell) for cell in cleaned_cells),
                    "has_trailing_values": bool(trailing_cells),
                }
            )
        )
    return table.model_copy(
        update={
            "row_views": row_views,
            "metadata": {
                **table.metadata,
                "body_element_candidate_view": {
                    "candidate_count": len(table_candidates),
                    "row_label_candidate_count": len(label_candidates),
                    "consumed_nonanchor_cell_count": len(consumed_nonanchor_cells),
                },
            },
        }
    )
