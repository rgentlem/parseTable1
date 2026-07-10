"""Group normalized rows into deterministic candidate variable blocks."""

from __future__ import annotations

import re
from collections.abc import Sequence

from table1_parser.heuristics.body_element_views import table_with_body_element_candidates
from table1_parser.heuristics.level_detector import detect_level_row_indices
from table1_parser.heuristics.models import RowClassification, VariableBlock
from table1_parser.heuristics.row_classifier import classify_rows, indentation_is_informative
from table1_parser.heuristics.value_pattern_detector import detect_value_pattern
from table1_parser.schemas import BodyElementCandidate, NormalizedTable, RowView
from table1_parser.text_cleaning import clean_text


THRESHOLD_LEVEL_PATTERN = re.compile(r"^\s*(?P<operator><=|>=|<|>|≤|≥)\s*(?P<threshold>.+?)\s*$")
COUNT_PCT_PARENT_PATTERN = re.compile(r"\bn\s*\(\s*%\s*\)", re.IGNORECASE)


def _nonempty_trailing_cell_count(row_view: RowView) -> int:
    """Count meaningful trailing cells while preserving raw row text elsewhere."""
    return sum(bool(clean_text(cell)) for cell in row_view.raw_cells[1:])


def _has_count_like_values(row_view: RowView) -> bool:
    """Return whether a row has enough count/count-percent cells to behave as a categorical level."""
    patterns = [
        detect_value_pattern(clean_text(cell)).pattern
        for cell in row_view.raw_cells[1:]
        if clean_text(cell) and detect_value_pattern(clean_text(cell)).pattern != "p_value"
    ]
    if not patterns:
        return False
    count_like = sum(pattern in {"count_pct", "n_only"} for pattern in patterns)
    return count_like >= 2 and count_like >= len(patterns) - 1


def _has_continuation_level_values(row_view: RowView) -> bool:
    """Return whether a boundary-leading row has data values compatible with a categorical level."""
    populated_cells = [clean_text(cell) for cell in row_view.raw_cells[1:] if clean_text(cell)]
    if not populated_cells:
        return False
    patterns = [detect_value_pattern(cell).pattern for cell in populated_cells]
    non_p_value_patterns = [pattern for pattern in patterns if pattern != "p_value"]
    if not non_p_value_patterns:
        return False
    if any(pattern in {"mean_sd", "median_iqr"} for pattern in non_p_value_patterns):
        return False
    if any(pattern in {"count_pct", "n_only"} for pattern in non_p_value_patterns):
        return True
    numeric_like_count = sum(any(char.isdigit() for char in cell) and not any(char.isalpha() for char in cell) for cell in populated_cells)
    return numeric_like_count >= 1 and numeric_like_count == len(non_p_value_patterns)


def _resolved_row_source_roles(table: NormalizedTable) -> dict[int, str]:
    """Return resolved-row source roles carried by the continuation resolver."""
    records = table.metadata.get("resolved_row_provenance")
    if not isinstance(records, list):
        return {}
    roles: dict[int, str] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        row_idx = record.get("resolved_row_idx")
        role = record.get("source_role")
        if isinstance(row_idx, int) and not isinstance(row_idx, bool) and isinstance(role, str):
            roles[row_idx] = role
    return roles


def _resolved_continuation_boundaries(table: NormalizedTable) -> list[tuple[int | None, int]]:
    """Return resolved row boundaries where accepted continuation fragments begin."""
    records = table.metadata.get("resolved_integration_boundaries")
    if not isinstance(records, list):
        return []
    boundaries: list[tuple[int | None, int]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        after_row_idx = record.get("after_resolved_row_idx")
        before_row_idx = record.get("before_resolved_row_idx")
        if not isinstance(after_row_idx, int) or isinstance(after_row_idx, bool) or after_row_idx < 0:
            continue
        before = (
            before_row_idx
            if isinstance(before_row_idx, int) and not isinstance(before_row_idx, bool) and before_row_idx >= 0
            else None
        )
        boundaries.append((before, after_row_idx))
    return sorted(set(boundaries), key=lambda boundary: boundary[1])


def _attach_leading_continuation_levels(
    *,
    table: NormalizedTable,
    blocks: list[VariableBlock],
    row_order: list[int],
    row_views_by_idx: dict[int, RowView],
) -> list[VariableBlock]:
    """Attach boundary-leading continuation rows to the previous open parent variable."""
    continuation_boundaries = _resolved_continuation_boundaries(table)
    source_roles = _resolved_row_source_roles(table)
    if not continuation_boundaries or not source_roles:
        return blocks

    block_by_start = {block.variable_row_idx: block for block in blocks}
    extension_rows_by_block_start: dict[int, list[int]] = {}
    rows_to_suppress_as_blocks: set[int] = set()
    row_position_by_idx = {row_idx: position for position, row_idx in enumerate(row_order)}

    for boundary_before, continuation_start in continuation_boundaries:
        start_position = row_position_by_idx.get(continuation_start)
        if start_position is None:
            continue
        if any(block.variable_row_idx < continuation_start <= block.row_end for block in blocks):
            continue
        prior_blocks = [
            block
            for block in blocks
            if block.row_end == boundary_before
            and block.variable_kind in {"binary", "categorical"}
            and bool(block.level_row_indices)
        ]
        if not prior_blocks:
            continue
        prior_block = prior_blocks[-1]
        leading_rows: list[int] = []
        for row_idx in row_order[start_position:]:
            if source_roles.get(row_idx) != "continuation_fragment":
                break
            row_view = row_views_by_idx.get(row_idx)
            if row_view is None:
                break
            candidate_block = block_by_start.get(row_idx)
            if candidate_block is not None and candidate_block.level_row_indices:
                break
            if not _has_continuation_level_values(row_view):
                break
            leading_rows.append(row_idx)
            if candidate_block is not None:
                rows_to_suppress_as_blocks.add(row_idx)
        if leading_rows:
            extension_rows_by_block_start.setdefault(prior_block.variable_row_idx, []).extend(leading_rows)

    if not extension_rows_by_block_start:
        return blocks

    adjusted_blocks: list[VariableBlock] = []
    for block in blocks:
        if block.variable_row_idx in rows_to_suppress_as_blocks:
            continue
        extension_rows = extension_rows_by_block_start.get(block.variable_row_idx, [])
        if not extension_rows:
            adjusted_blocks.append(block)
            continue
        level_rows = [*block.level_row_indices, *extension_rows]
        adjusted_blocks.append(
            block.model_copy(
                update={
                    "row_end": max(block.row_end, *extension_rows),
                    "level_row_indices": level_rows,
                }
            )
        )
    return adjusted_blocks


def _count_pct_continuation_level_rows(
    parent_row_idx: int,
    row_order: list[int],
    row_views_by_idx: dict[int, RowView],
) -> list[int]:
    """Collect count-percent level rows below an n (%) parent without relying on indentation."""
    parent = row_views_by_idx[parent_row_idx]
    if COUNT_PCT_PARENT_PATTERN.search(parent.first_cell_raw) is None:
        return []
    level_rows: list[int] = []
    for candidate_row_idx in row_order[row_order.index(parent_row_idx) + 1 :]:
        candidate = row_views_by_idx[candidate_row_idx]
        candidate_label = clean_text(candidate.first_cell_raw)
        if COUNT_PCT_PARENT_PATTERN.search(candidate_label) is not None:
            break
        if _has_count_like_values(candidate):
            level_rows.append(candidate_row_idx)
            continue
        break
    return level_rows


def group_variable_blocks(
    table: NormalizedTable,
    classifications: list[RowClassification] | None = None,
    body_element_candidates: Sequence[BodyElementCandidate] | None = None,
) -> list[VariableBlock]:
    """Group normalized body rows into candidate variables."""
    table = table_with_body_element_candidates(table, body_element_candidates)
    classifications = classifications or classify_rows(table)
    classifications_by_row = {
        classification.row_idx: classification.classification for classification in classifications
    }
    row_views_by_idx = {row_view.row_idx: row_view for row_view in table.row_views}
    row_order = [row_view.row_idx for row_view in table.row_views]
    use_indentation = indentation_is_informative(table)
    adjusted = dict(classifications_by_row)
    for row_idx in row_order:
        if adjusted.get(row_idx) != "continuous_variable_row":
            continue
        row_view = row_views_by_idx[row_idx]
        if _nonempty_trailing_cell_count(row_view) > 1:
            continue
        level_rows = detect_level_row_indices(
            parent_row_idx=row_idx,
            row_order=row_order,
            classifications_by_row=adjusted,
        )
        more_indented_levels = (
            sum(
                1
                for level_row_idx in level_rows
                if row_views_by_idx[level_row_idx].indent_level is not None
                and row_view.indent_level is not None
                and row_views_by_idx[level_row_idx].indent_level > row_view.indent_level
            )
            if use_indentation
            else 0
        )
        if len(level_rows) >= 2 and (
            (use_indentation and more_indented_levels >= 1)
            or _nonempty_trailing_cell_count(row_view) <= 1
        ):
            adjusted[row_idx] = "variable_header"
    classifications_by_row = adjusted
    blocks: list[VariableBlock] = []
    consumed_rows: set[int] = set()

    for row_idx in row_order:
        if row_idx in consumed_rows:
            continue

        row_view = row_views_by_idx[row_idx]
        classification = classifications_by_row.get(row_idx, "unknown")
        if classification in {"binary_variable_row", "level_row", "unknown"}:
            threshold_match = THRESHOLD_LEVEL_PATTERN.match(row_view.first_cell_raw)
            if threshold_match is not None:
                threshold_key = clean_text(threshold_match.group("threshold")).lower().replace(" ", "")
                threshold_level_rows: list[int] = []
                threshold_directions: set[str] = set()
                for candidate_row_idx in row_order[row_order.index(row_idx) :]:
                    if candidate_row_idx in consumed_rows:
                        break
                    if classifications_by_row.get(candidate_row_idx) not in {"binary_variable_row", "level_row", "unknown"}:
                        break
                    candidate_row = row_views_by_idx[candidate_row_idx]
                    candidate_match = THRESHOLD_LEVEL_PATTERN.match(candidate_row.first_cell_raw)
                    if candidate_match is None:
                        break
                    candidate_key = clean_text(candidate_match.group("threshold")).lower().replace(" ", "")
                    if candidate_key != threshold_key:
                        break
                    operator = candidate_match.group("operator")
                    threshold_directions.add("lower" if operator in {"<", "<=", "≤"} else "upper")
                    threshold_level_rows.append(candidate_row_idx)
                if len(threshold_level_rows) >= 2 and threshold_directions == {"lower", "upper"}:
                    variable_label = "Threshold category"
                    if blocks and blocks[-1].row_end < row_idx and blocks[-1].variable_kind == "continuous":
                        base_label = clean_text(blocks[-1].variable_label.split(",", maxsplit=1)[0])
                        if base_label:
                            variable_label = f"{base_label} category"
                    blocks.append(
                        VariableBlock(
                            variable_row_idx=row_idx,
                            row_start=row_idx,
                            row_end=threshold_level_rows[-1],
                            variable_label=variable_label,
                            variable_kind="binary",
                            level_row_indices=threshold_level_rows,
                        )
                    )
                    consumed_rows.update(threshold_level_rows)
                    continue

        if classification in {"continuous_variable_row", "binary_variable_row"}:
            blocks.append(
                VariableBlock(
                    variable_row_idx=row_idx,
                    row_start=row_idx,
                    row_end=row_idx,
                    variable_label=row_view.first_cell_raw,
                    variable_kind="binary" if classification == "binary_variable_row" else "continuous",
                    level_row_indices=[],
                )
            )
            consumed_rows.add(row_idx)
            continue

        if classification == "variable_header":
            level_rows = _count_pct_continuation_level_rows(
                parent_row_idx=row_idx,
                row_order=row_order,
                row_views_by_idx=row_views_by_idx,
            ) or detect_level_row_indices(
                parent_row_idx=row_idx,
                row_order=row_order,
                classifications_by_row=classifications_by_row,
            )
            consumed_rows.add(row_idx)
            consumed_rows.update(level_rows)
            blocks.append(
                VariableBlock(
                    variable_row_idx=row_idx,
                    row_start=row_idx,
                    row_end=level_rows[-1] if level_rows else row_idx,
                    variable_label=row_view.first_cell_raw,
                    variable_kind="categorical" if level_rows else "unknown",
                    level_row_indices=level_rows,
                )
            )
    return _attach_leading_continuation_levels(
        table=table,
        blocks=blocks,
        row_order=row_order,
        row_views_by_idx=row_views_by_idx,
    )
