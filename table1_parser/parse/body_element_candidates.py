"""Build logical body value element candidates over normalized source grids."""

from __future__ import annotations

import re
from collections.abc import Sequence

from table1_parser.schemas import (
    BodyElementCandidate,
    BodyElementSourceCell,
    ColumnHeaderSchema,
    ExtractedTable,
    NormalizedTable,
    TableCell,
)
from table1_parser.text_cleaning import clean_text


NUMERIC_TOKEN = r"(?:\d{1,3}(?:,\d{3})*|\d+)(?:\.\d+)?"
PARENTHESIZED_NUMERIC_ELEMENT = rf"{NUMERIC_TOKEN}\s*\(\s*{NUMERIC_TOKEN}\s*,\s*{NUMERIC_TOKEN}\s*\)"
COUNT_PERCENT_ELEMENT = rf"(?:\d{{1,3}}(?:,\d{{3}})*|\d+)\s*\(\s*\d+(?:\.\d+)?\s*%?\s*\)"
P_VALUE_ELEMENT = r"(?:[<>]=?\s*)?(?:0?\.\d+|\.\d+|1\.0+)"
ROW_ELEMENT_PATTERN = re.compile(
    rf"{PARENTHESIZED_NUMERIC_ELEMENT}|{COUNT_PERCENT_ELEMENT}|{P_VALUE_ELEMENT}",
    re.IGNORECASE,
)
FRAGMENTATION_EVIDENCE_PATTERN = re.compile(r"\)\s+\d[\d,]*(?:\.\d+)?\s*\(")


def build_body_element_candidates(
    tables: Sequence[NormalizedTable],
    column_header_schemas: Sequence[ColumnHeaderSchema],
    extracted_tables: Sequence[ExtractedTable] | None = None,
) -> list[BodyElementCandidate]:
    """Build candidate body value elements without rewriting the source grid."""
    schemas_by_table_id = {schema.table_id: schema for schema in column_header_schemas}
    extracted_by_table_id = {table.table_id: table for table in extracted_tables or []}
    candidates: list[BodyElementCandidate] = []
    for table_index, table in enumerate(tables):
        raw_grid = _raw_grid(table)
        if not raw_grid:
            continue
        cleaned_grid = [[clean_text(cell) for cell in row] for row in raw_grid]
        schema = schemas_by_table_id.get(table.table_id)
        value_col_indices = _value_col_indices(table, schema)
        if not value_col_indices:
            continue
        label_col_idx = schema.label_col_idx if schema is not None and schema.label_col_idx is not None else 0
        body_rows = _candidate_body_rows(table, len(raw_grid))
        source_col_indices = _source_col_indices(table)
        extracted_cell_by_position = _extracted_cell_by_position(extracted_by_table_id.get(table.table_id))
        row_sequence_by_anchor: dict[tuple[int, int], dict[str, object]] = {}
        compound_by_anchor: dict[tuple[int, int], dict[str, object]] = {}
        consumed_cells: set[tuple[int, int]] = set()

        for row_idx in body_rows:
            row_candidates = _row_sequence_candidates(
                table_index=table_index,
                table=table,
                row_idx=row_idx,
                value_col_indices=value_col_indices,
                label_col_idx=label_col_idx,
                raw_grid=raw_grid,
                cleaned_grid=cleaned_grid,
                source_col_indices=source_col_indices,
                extracted_cell_by_position=extracted_cell_by_position,
            )
            if row_candidates is None:
                continue
            for col_idx, row_candidate in row_candidates.items():
                row_sequence_by_anchor[(row_idx, col_idx)] = row_candidate
                for source_cell in row_candidate["source_cells"]:
                    if isinstance(source_cell, BodyElementSourceCell):
                        consumed_cells.add((source_cell.row_idx, source_cell.col_idx))

        for row_idx in body_rows:
            if any((row_idx, col_idx) in row_sequence_by_anchor for col_idx in value_col_indices):
                continue
            next_row_idx = row_idx + 1
            if next_row_idx >= len(cleaned_grid) or next_row_idx >= len(raw_grid):
                continue
            next_label = _grid_cell(cleaned_grid, next_row_idx, label_col_idx)
            if next_label:
                continue
            for col_idx in value_col_indices:
                target_text = _grid_cell(cleaned_grid, row_idx, col_idx)
                continuation_text = _grid_cell(cleaned_grid, next_row_idx, col_idx)
                if not target_text or not continuation_text:
                    continue
                target_balance = target_text.count("(") - target_text.count(")")
                continuation_balance = continuation_text.count("(") - continuation_text.count(")")
                if not (
                    target_balance > 0
                    and continuation_balance < 0
                    and continuation_text.count("(") == 0
                ):
                    continue
                raw_fragments = [
                    _grid_cell(raw_grid, row_idx, col_idx),
                    _grid_cell(raw_grid, next_row_idx, col_idx),
                ]
                compound_by_anchor[(row_idx, col_idx)] = {
                    "kind": "same_column_vertical_continuation",
                    "candidate_text": clean_text(" ".join(raw_fragments)),
                    "raw_fragments": raw_fragments,
                    "source_cells": [
                        _source_cell(
                            table_index=table_index,
                            table=table,
                            row_idx=row_idx,
                            col_idx=col_idx,
                            raw_grid=raw_grid,
                            cleaned_grid=cleaned_grid,
                            source_col_indices=source_col_indices,
                            extracted_cell_by_position=extracted_cell_by_position,
                        ),
                        _source_cell(
                            table_index=table_index,
                            table=table,
                            row_idx=next_row_idx,
                            col_idx=col_idx,
                            raw_grid=raw_grid,
                            cleaned_grid=cleaned_grid,
                            source_col_indices=source_col_indices,
                            extracted_cell_by_position=extracted_cell_by_position,
                        ),
                    ],
                    "reason": "open_parenthesis_continues_same_column_next_blank_label_row",
                    "confidence": 0.9,
                    "notes": [],
                }
                consumed_cells.add((row_idx, col_idx))
                consumed_cells.add((next_row_idx, col_idx))

        candidate_number = 0
        for row_idx in body_rows:
            if row_idx >= len(raw_grid):
                continue
            for col_idx in value_col_indices:
                if col_idx >= len(raw_grid[row_idx]):
                    continue
                row_sequence = row_sequence_by_anchor.get((row_idx, col_idx))
                if row_sequence is not None:
                    candidates.append(
                        BodyElementCandidate(
                            candidate_id=f"{table.table_id}:body_element:{candidate_number}",
                            source_table_index=table_index,
                            source_table_id=table.table_id,
                            anchor_row_idx=row_idx,
                            anchor_col_idx=col_idx,
                            kind="row_sequence_reconstruction",
                            candidate_text=str(row_sequence["candidate_text"]),
                            raw_fragments=list(row_sequence["raw_fragments"]),
                            source_cells=list(row_sequence["source_cells"]),
                            reason=str(row_sequence["reason"]),
                            confidence=float(row_sequence["confidence"]),
                            notes=list(row_sequence["notes"]),
                        )
                    )
                    candidate_number += 1
                    continue
                compound = compound_by_anchor.get((row_idx, col_idx))
                if compound is not None:
                    candidates.append(
                        BodyElementCandidate(
                            candidate_id=f"{table.table_id}:body_element:{candidate_number}",
                            source_table_index=table_index,
                            source_table_id=table.table_id,
                            anchor_row_idx=row_idx,
                            anchor_col_idx=col_idx,
                            kind="same_column_vertical_continuation",
                            candidate_text=str(compound["candidate_text"]),
                            raw_fragments=list(compound["raw_fragments"]),
                            source_cells=list(compound["source_cells"]),
                            reason=str(compound["reason"]),
                            confidence=float(compound["confidence"]),
                            notes=list(compound["notes"]),
                        )
                    )
                    candidate_number += 1
                    continue
                if (row_idx, col_idx) in consumed_cells:
                    continue
                raw_value = _grid_cell(raw_grid, row_idx, col_idx)
                if not clean_text(raw_value):
                    continue
                candidates.append(
                    BodyElementCandidate(
                        candidate_id=f"{table.table_id}:body_element:{candidate_number}",
                        source_table_index=table_index,
                        source_table_id=table.table_id,
                        anchor_row_idx=row_idx,
                        anchor_col_idx=col_idx,
                        kind="single_cell",
                        candidate_text=clean_text(raw_value),
                        raw_fragments=[raw_value],
                        source_cells=[
                            _source_cell(
                                table_index=table_index,
                                table=table,
                                row_idx=row_idx,
                                col_idx=col_idx,
                                raw_grid=raw_grid,
                                cleaned_grid=cleaned_grid,
                                source_col_indices=source_col_indices,
                                extracted_cell_by_position=extracted_cell_by_position,
                            )
                        ],
                        reason="single_populated_body_value_cell",
                        confidence=1.0,
                    )
                )
                candidate_number += 1
    return candidates


def body_element_candidates_to_payload(candidates: Sequence[BodyElementCandidate]) -> list[dict[str, object]]:
    """Serialize body element candidates as JSON-friendly dictionaries."""
    return [candidate.model_dump(mode="json") for candidate in candidates]


def _row_sequence_candidates(
    *,
    table_index: int,
    table: NormalizedTable,
    row_idx: int,
    value_col_indices: list[int],
    label_col_idx: int,
    raw_grid: list[list[str]],
    cleaned_grid: list[list[str]],
    source_col_indices: Sequence[int | None],
    extracted_cell_by_position: dict[tuple[int, int], TableCell],
) -> dict[int, dict[str, object]] | None:
    if len(value_col_indices) < 2 or row_idx >= len(raw_grid):
        return None
    row_texts = [_grid_cell(cleaned_grid, row_idx, col_idx) for col_idx in value_col_indices]
    next_row_idx = row_idx + 1
    has_blank_label_continuation = (
        next_row_idx < len(cleaned_grid)
        and not _grid_cell(cleaned_grid, next_row_idx, label_col_idx)
        and any(_grid_cell(cleaned_grid, next_row_idx, col_idx) for col_idx in value_col_indices)
    )
    has_unbalanced_parentheses = any(text.count("(") != text.count(")") for text in row_texts if text)
    has_close_then_open_cell = any(FRAGMENTATION_EVIDENCE_PATTERN.search(text) for text in row_texts)
    if not (has_blank_label_continuation or has_unbalanced_parentheses or has_close_then_open_cell):
        return None

    segments: list[tuple[str, list[BodyElementSourceCell]]] = []
    for col_idx in value_col_indices:
        raw_fragment = _grid_cell(raw_grid, row_idx, col_idx)
        source_cells = [
            _source_cell(
                table_index=table_index,
                table=table,
                row_idx=row_idx,
                col_idx=col_idx,
                raw_grid=raw_grid,
                cleaned_grid=cleaned_grid,
                source_col_indices=source_col_indices,
                extracted_cell_by_position=extracted_cell_by_position,
            )
        ]
        if has_blank_label_continuation and next_row_idx < len(raw_grid):
            target_text = _grid_cell(cleaned_grid, row_idx, col_idx)
            continuation_text = _grid_cell(cleaned_grid, next_row_idx, col_idx)
            target_balance = target_text.count("(") - target_text.count(")")
            continuation_balance = continuation_text.count("(") - continuation_text.count(")")
            if (
                target_text
                and continuation_text
                and target_balance > 0
                and continuation_balance < 0
                and continuation_text.count("(") == 0
            ):
                raw_fragment = clean_text(f"{raw_fragment} {_grid_cell(raw_grid, next_row_idx, col_idx)}")
                source_cells.append(
                    _source_cell(
                        table_index=table_index,
                        table=table,
                        row_idx=next_row_idx,
                        col_idx=col_idx,
                        raw_grid=raw_grid,
                        cleaned_grid=cleaned_grid,
                        source_col_indices=source_col_indices,
                        extracted_cell_by_position=extracted_cell_by_position,
                    )
                )
        if clean_text(raw_fragment):
            segments.append((raw_fragment, source_cells))
    if not segments:
        return None

    stream_parts: list[str] = []
    segment_spans: list[tuple[int, int, list[BodyElementSourceCell]]] = []
    position = 0
    for raw_fragment, source_cells in segments:
        if stream_parts:
            stream_parts.append(" ")
            position += 1
        cleaned_fragment = clean_text(raw_fragment)
        start = position
        stream_parts.append(cleaned_fragment)
        position += len(cleaned_fragment)
        segment_spans.append((start, position, source_cells))
    stream = "".join(stream_parts)
    matches = list(ROW_ELEMENT_PATTERN.finditer(stream))
    if len(matches) != len(value_col_indices):
        return None
    unmatched_text = stream
    for match in reversed(matches):
        unmatched_text = f"{unmatched_text[:match.start()]} {unmatched_text[match.end():]}"
    if clean_text(unmatched_text):
        return None

    row_candidates: dict[int, dict[str, object]] = {}
    for col_idx, match in zip(value_col_indices, matches, strict=True):
        source_cells: list[BodyElementSourceCell] = []
        seen_source_cells: set[tuple[int, int]] = set()
        for start, end, segment_source_cells in segment_spans:
            if end <= match.start() or start >= match.end():
                continue
            for source_cell in segment_source_cells:
                key = (source_cell.row_idx, source_cell.col_idx)
                if key in seen_source_cells:
                    continue
                seen_source_cells.add(key)
                source_cells.append(source_cell)
        candidate_text = clean_text(match.group(0))
        row_candidates[col_idx] = {
            "kind": "row_sequence_reconstruction",
            "candidate_text": candidate_text,
            "raw_fragments": [candidate_text],
            "source_cells": source_cells,
            "reason": "row_value_stream_splits_into_one_candidate_per_value_column",
            "confidence": 0.86,
            "notes": [],
        }
    return row_candidates


def _raw_grid(table: NormalizedTable) -> list[list[str]]:
    raw_grid = table.metadata.get("raw_rows")
    if isinstance(raw_grid, list):
        return [[str(cell) for cell in row] if isinstance(row, list) else [] for row in raw_grid]
    cleaned_grid = table.metadata.get("cleaned_rows")
    if isinstance(cleaned_grid, list):
        return [[str(cell) for cell in row] if isinstance(row, list) else [] for row in cleaned_grid]
    return [list(row_view.raw_cells) for row_view in table.row_views]


def _value_col_indices(table: NormalizedTable, schema: ColumnHeaderSchema | None) -> list[int]:
    if schema is None:
        return list(range(1, table.n_cols))
    return sorted(
        {
            leaf.col_idx
            for leaf in schema.leaves
            if leaf.is_value_column and not leaf.is_row_label_column and 0 <= leaf.col_idx < table.n_cols
        }
    )


def _candidate_body_rows(table: NormalizedTable, row_count: int) -> list[int]:
    if table.body_rows:
        return [row_idx for row_idx in table.body_rows if 0 <= row_idx < row_count]
    header_rows = set(table.header_rows)
    return [row_idx for row_idx in range(row_count) if row_idx not in header_rows]


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
) -> BodyElementSourceCell:
    original_col_idx = source_col_indices[col_idx] if col_idx < len(source_col_indices) else col_idx
    extracted_cell = (
        extracted_cell_by_position.get((row_idx, original_col_idx))
        if original_col_idx is not None
        else None
    )
    return BodyElementSourceCell(
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
