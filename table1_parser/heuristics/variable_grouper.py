"""Group normalized rows into deterministic candidate variable blocks."""

from __future__ import annotations

import re

from table1_parser.heuristics.level_detector import detect_level_row_indices
from table1_parser.heuristics.models import RowClassification, VariableBlock
from table1_parser.heuristics.row_classifier import classify_rows, indentation_is_informative
from table1_parser.heuristics.value_pattern_detector import detect_value_pattern
from table1_parser.schemas import NormalizedTable, RowView
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
) -> list[VariableBlock]:
    """Group normalized body rows into candidate variables."""
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
    return blocks
