"""Build logical body row-label candidates over normalized source grids."""

from __future__ import annotations

import re
from collections.abc import Sequence

from table1_parser.schemas import (
    BodyRowLabelCandidate,
    BodyRowLabelSourceCell,
    ColumnHeaderSchema,
    ExtractedTable,
    NormalizedTable,
    TableCell,
)
from table1_parser.text_cleaning import clean_text


UNFINISHED_LABEL_SUFFIX_PATTERN = re.compile(r"(?:\b(?:to|and|or|of|for|with|without|includes?)|[-/,])$", re.IGNORECASE)


def build_body_row_label_candidates(
    tables: Sequence[NormalizedTable],
    column_header_schemas: Sequence[ColumnHeaderSchema],
    extracted_tables: Sequence[ExtractedTable] | None = None,
) -> list[BodyRowLabelCandidate]:
    """Build candidate body row labels without rewriting the source grid."""
    schemas_by_table_id = {schema.table_id: schema for schema in column_header_schemas}
    extracted_by_table_id = {table.table_id: table for table in extracted_tables or []}
    candidates: list[BodyRowLabelCandidate] = []
    for table_index, table in enumerate(tables):
        raw_grid = _raw_grid(table)
        if not raw_grid:
            continue
        cleaned_grid = [[clean_text(cell) for cell in row] for row in raw_grid]
        schema = schemas_by_table_id.get(table.table_id)
        label_col_indices = _label_col_indices(table, schema)
        value_col_indices = _value_col_indices(table, schema, label_col_indices)
        if not label_col_indices or not value_col_indices:
            continue
        body_rows = _candidate_body_rows(table, len(raw_grid))
        body_row_set = set(body_rows)
        source_col_indices = _source_col_indices(table)
        extracted_cell_by_position = _extracted_cell_by_position(extracted_by_table_id.get(table.table_id))
        candidate_number = 0
        for row_idx in body_rows:
            anchor_label = _row_label_text(cleaned_grid, row_idx, label_col_indices)
            if not anchor_label or not _row_has_value_text(cleaned_grid, row_idx, value_col_indices):
                continue
            fragments = [_row_label_text(raw_grid, row_idx, label_col_indices)]
            continuation_rows: list[int] = []
            next_row_idx = row_idx + 1
            while next_row_idx in body_row_set:
                continuation_label = _row_label_text(cleaned_grid, next_row_idx, label_col_indices)
                if not continuation_label:
                    break
                if _row_has_value_text(cleaned_grid, next_row_idx, value_col_indices):
                    break
                current_label = clean_text(" ".join([anchor_label, *fragments[1:]]))
                if not _looks_like_label_continuation(current_label, continuation_label):
                    break
                fragments.append(_row_label_text(raw_grid, next_row_idx, label_col_indices))
                continuation_rows.append(next_row_idx)
                next_row_idx += 1
            if not continuation_rows:
                continue
            source_cells = [
                _source_cell(
                    table_index=table_index,
                    table=table,
                    row_idx=source_row_idx,
                    col_idx=col_idx,
                    raw_grid=raw_grid,
                    cleaned_grid=cleaned_grid,
                    source_col_indices=source_col_indices,
                    extracted_cell_by_position=extracted_cell_by_position,
                )
                for source_row_idx in [row_idx, *continuation_rows]
                for col_idx in label_col_indices
                if clean_text(_grid_cell(cleaned_grid, source_row_idx, col_idx))
            ]
            candidate_label = clean_text(" ".join(fragments))
            candidates.append(
                BodyRowLabelCandidate(
                    candidate_id=f"{table.table_id}:body_row_label:{candidate_number}",
                    source_table_index=table_index,
                    source_table_id=table.table_id,
                    anchor_row_idx=row_idx,
                    anchor_col_idx=label_col_indices[0],
                    kind="vertical_label_continuation",
                    candidate_label=candidate_label,
                    raw_fragments=fragments,
                    source_cells=source_cells,
                    continuation_row_indices=continuation_rows,
                    reason="adjacent_label_only_body_rows_continue_valued_anchor_label",
                    confidence=0.9,
                )
            )
            candidate_number += 1
    for candidate in candidates:
        candidate.raw_text = " ".join(source_cell.text for source_cell in candidate.source_cells)
        candidate.base_text = candidate.raw_text
        candidate.candidate_label = clean_text(candidate.base_text)
    return candidates


def body_row_label_candidates_to_payload(candidates: Sequence[BodyRowLabelCandidate]) -> list[dict[str, object]]:
    """Serialize body row-label candidates as JSON-friendly dictionaries."""
    return [candidate.model_dump(mode="json") for candidate in candidates]


def _looks_like_label_continuation(previous_label: str, candidate_label: str) -> bool:
    previous = clean_text(previous_label)
    candidate = clean_text(candidate_label)
    if not previous or not candidate or len(candidate.split()) > 6:
        return False
    if previous.count("(") > previous.count(")") and ")" in candidate:
        return True
    if UNFINISHED_LABEL_SUFFIX_PATTERN.search(previous):
        return True
    first_char = candidate[0]
    first_token = candidate.split()[0]
    starts_plain_lowercase_word = first_char.islower() and not any(char.isupper() for char in first_token[1:])
    return starts_plain_lowercase_word or first_char.isdigit() or first_char == ")"


def _raw_grid(table: NormalizedTable) -> list[list[str]]:
    raw_grid = table.metadata.get("raw_rows")
    if isinstance(raw_grid, list):
        return [[str(cell) for cell in row] if isinstance(row, list) else [] for row in raw_grid]
    cleaned_grid = table.metadata.get("cleaned_rows")
    if isinstance(cleaned_grid, list):
        return [[str(cell) for cell in row] if isinstance(row, list) else [] for row in cleaned_grid]
    return [list(row_view.raw_cells) for row_view in table.row_views]


def _label_col_indices(table: NormalizedTable, schema: ColumnHeaderSchema | None) -> list[int]:
    if schema is not None:
        schema_label_cols = sorted(
            {
                leaf.col_idx
                for leaf in schema.leaves
                if leaf.is_row_label_column and 0 <= leaf.col_idx < table.n_cols
            }
        )
        if schema_label_cols:
            return schema_label_cols
        if schema.label_col_idx is not None and 0 <= schema.label_col_idx < table.n_cols:
            return [schema.label_col_idx]
    return [0] if table.n_cols else []


def _value_col_indices(
    table: NormalizedTable,
    schema: ColumnHeaderSchema | None,
    label_col_indices: Sequence[int],
) -> list[int]:
    if schema is not None:
        schema_value_cols = sorted(
            {
                leaf.col_idx
                for leaf in schema.leaves
                if leaf.is_value_column and not leaf.is_row_label_column and 0 <= leaf.col_idx < table.n_cols
            }
        )
        if schema_value_cols:
            return schema_value_cols
    label_cols = set(label_col_indices)
    return [col_idx for col_idx in range(table.n_cols) if col_idx not in label_cols]


def _candidate_body_rows(table: NormalizedTable, row_count: int) -> list[int]:
    if table.body_rows:
        return [row_idx for row_idx in table.body_rows if 0 <= row_idx < row_count]
    header_rows = set(table.header_rows)
    return [row_idx for row_idx in range(row_count) if row_idx not in header_rows]


def _row_label_text(grid: list[list[str]], row_idx: int, label_col_indices: Sequence[int]) -> str:
    return clean_text(" ".join(_grid_cell(grid, row_idx, col_idx) for col_idx in label_col_indices))


def _row_has_value_text(grid: list[list[str]], row_idx: int, value_col_indices: Sequence[int]) -> bool:
    return any(clean_text(_grid_cell(grid, row_idx, col_idx)) for col_idx in value_col_indices)


def _source_col_indices(table: NormalizedTable) -> list[int | None]:
    source_col_indices = table.metadata.get("source_col_indices")
    if isinstance(source_col_indices, list) and len(source_col_indices) == table.n_cols:
        return [value if isinstance(value, int) and value >= 0 else None for value in source_col_indices]
    return list(range(table.n_cols))


def _extracted_cell_by_position(table: ExtractedTable | None) -> dict[tuple[int, int], TableCell]:
    if table is None:
        return {}
    return {(cell.row_idx, cell.col_idx): cell for cell in table.cells}


def _source_cell(
    *,
    table_index: int,
    table: NormalizedTable,
    row_idx: int,
    col_idx: int,
    raw_grid: list[list[str]],
    cleaned_grid: list[list[str]],
    source_col_indices: Sequence[int | None],
    extracted_cell_by_position: dict[tuple[int, int], TableCell],
) -> BodyRowLabelSourceCell:
    original_col_idx = source_col_indices[col_idx] if col_idx < len(source_col_indices) else col_idx
    extracted_cell = (
        extracted_cell_by_position.get((row_idx, original_col_idx))
        if original_col_idx is not None
        else None
    )
    return BodyRowLabelSourceCell(
        source_table_index=table_index,
        source_table_id=table.table_id,
        row_idx=row_idx,
        col_idx=col_idx,
        original_row_idx=row_idx,
        original_col_idx=original_col_idx,
        text=_grid_cell(raw_grid, row_idx, col_idx),
        cleaned_text=_grid_cell(cleaned_grid, row_idx, col_idx),
        bbox=extracted_cell.bbox if extracted_cell is not None else None,
        page_num=extracted_cell.page_num if extracted_cell is not None else None,
    )


def _grid_cell(grid: list[list[str]], row_idx: int, col_idx: int) -> str:
    if row_idx < 0 or row_idx >= len(grid):
        return ""
    row = grid[row_idx]
    if col_idx < 0 or col_idx >= len(row):
        return ""
    return str(row[col_idx])
