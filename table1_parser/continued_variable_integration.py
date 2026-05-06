"""Integrate variable definitions across compatible continued table fragments."""

from __future__ import annotations

from table1_parser.heuristics.value_pattern_detector import detect_value_pattern
from table1_parser.schemas import (
    DefinedLevel,
    DefinedVariable,
    NormalizedTable,
    RowView,
    Table1ContinuationGroup,
    TableDefinition,
)
from table1_parser.text_cleaning import clean_text


COUNT_LIKE_VALUE_PATTERNS = {"count_pct", "n_only"}


def build_continued_variable_integrations(
    normalized_tables: list[NormalizedTable],
    table_definitions: list[TableDefinition],
    table1_continuation_groups: list[Table1ContinuationGroup],
) -> list[TableDefinition]:
    """Build integrated TableDefinition artifacts for compatible continuation groups."""
    integrations: list[TableDefinition] = []
    for group in table1_continuation_groups:
        if group.merge_decision != "merge" or not group.column_headers_match or len(group.source_table_indices) < 2:
            continue
        source_indices = group.source_table_indices
        if any(index >= len(normalized_tables) or index >= len(table_definitions) for index in source_indices):
            continue
        base_definition = table_definitions[source_indices[0]]
        row_idx_by_source, source_by_integrated = _integrated_row_maps(normalized_tables, source_indices)
        row_views_by_source = {
            (source_index, row_view.row_idx): row_view
            for source_index in source_indices
            for row_view in normalized_tables[source_index].row_views
        }
        variable_entries: list[dict[str, object]] = []
        for source_index in source_indices:
            for variable in table_definitions[source_index].variables:
                variable_entries.append(
                    {
                        "source_index": source_index,
                        "source_variable": variable,
                        "variable": _copy_variable_with_integrated_rows(variable, source_index, row_idx_by_source),
                    }
                )
        boundary_decisions: list[dict[str, object]] = []
        diagnostics: list[str] = []
        for prior_index, continuation_index in zip(source_indices, source_indices[1:], strict=False):
            decision = _reinterpret_boundary(
                variable_entries,
                normalized_tables,
                row_views_by_source,
                row_idx_by_source,
                prior_index,
                continuation_index,
            )
            boundary_decisions.append(decision)
            if decision["decision"] == "attached_levels":
                diagnostics.append(
                    "attached_continuation_levels:"
                    f"base={prior_index}:continuation={continuation_index}:"
                    f"parent={decision.get('parent_variable_name')}:levels={decision.get('attached_level_count')}"
                )
        integrated_variables = [
            entry["variable"]
            for entry in variable_entries
            if isinstance(entry.get("variable"), DefinedVariable)
        ]
        row_provenance = _row_provenance(integrated_variables, source_by_integrated, row_views_by_source)
        boundary_confidences = [
            float(decision["confidence"])
            for decision in boundary_decisions
            if isinstance(decision.get("confidence"), (int, float))
        ]
        item_confidences = [
            confidence
            for confidence in [
                *(variable.confidence for variable in integrated_variables),
                base_definition.column_definition.confidence,
                *boundary_confidences,
            ]
            if confidence is not None
        ]
        integrations.append(
            base_definition.model_copy(
                update={
                    "table_id": f"{base_definition.table_id}-continued-variable-integration",
                    "variables": integrated_variables,
                    "metadata": {
                        **base_definition.metadata,
                        "continued_variable_integration": {
                            "group_id": group.group_id,
                            "source_table_indices": source_indices,
                            "source_table_ids": [normalized_tables[index].table_id for index in source_indices],
                            "column_headers": group.column_headers,
                            "row_provenance": row_provenance,
                            "boundary_decisions": boundary_decisions,
                            "diagnostics": diagnostics,
                        },
                        "tableone": _tableone_metadata(integrated_variables),
                    },
                    "notes": [
                        *base_definition.notes,
                        f"continued_variable_integration:{group.group_id}",
                        *diagnostics,
                    ],
                    "overall_confidence": (
                        round(sum(item_confidences) / len(item_confidences), 4) if item_confidences else None
                    ),
                }
            )
        )
    return integrations


def continued_variable_integrations_to_payload(integrations: list[TableDefinition]) -> list[dict[str, object]]:
    """Serialize continued-variable integration TableDefinition artifacts."""
    return [integration.model_dump(mode="json") for integration in integrations]


def _tableone_metadata(variables: list[DefinedVariable]) -> dict[str, object]:
    vars_ = [variable.variable_name for variable in variables]
    logi_factors = [variable.variable_type in {"binary", "categorical"} for variable in variables]
    return {
        "vars": vars_,
        "logiFactors": logi_factors,
        "varFactors": [
            variable.variable_name
            for variable in variables
            if variable.variable_type in {"binary", "categorical"}
        ],
        "varNumerics": [variable.variable_name for variable in variables if variable.variable_type == "continuous"],
        "percentMissing": {variable.variable_name: None for variable in variables},
        "varLabels": {variable.variable_name: variable.variable_label for variable in variables},
    }


def _integrated_row_maps(
    normalized_tables: list[NormalizedTable],
    source_indices: list[int],
) -> tuple[dict[tuple[int, int], int], dict[int, dict[str, object]]]:
    row_idx_by_source: dict[tuple[int, int], int] = {}
    source_by_integrated: dict[int, dict[str, object]] = {}
    next_row_idx = 0
    for source_position, source_index in enumerate(source_indices):
        table = normalized_tables[source_index]
        rows = table.metadata.get("cleaned_rows")
        source_row_indices = (
            list(range(len(rows)))
            if source_position == 0 and isinstance(rows, list)
            else list(table.body_rows)
        )
        for source_row_idx in source_row_indices:
            row_idx_by_source[(source_index, source_row_idx)] = next_row_idx
            source_by_integrated[next_row_idx] = {
                "source_table_index": source_index,
                "source_table_id": table.table_id,
                "source_row_idx": source_row_idx,
                "source_page_num": table.metadata.get("source_page_num"),
            }
            next_row_idx += 1
    return row_idx_by_source, source_by_integrated


def _copy_variable_with_integrated_rows(
    variable: DefinedVariable,
    source_index: int,
    row_idx_by_source: dict[tuple[int, int], int],
) -> DefinedVariable:
    levels = [
        level.model_copy(update={"row_idx": row_idx_by_source.get((source_index, level.row_idx), level.row_idx)})
        for level in variable.levels
    ]
    return variable.model_copy(
        update={
            "row_start": row_idx_by_source.get((source_index, variable.row_start), variable.row_start),
            "row_end": row_idx_by_source.get((source_index, variable.row_end), variable.row_end),
            "levels": levels,
        }
    )


def _reinterpret_boundary(
    variable_entries: list[dict[str, object]],
    normalized_tables: list[NormalizedTable],
    row_views_by_source: dict[tuple[int, int], RowView],
    row_idx_by_source: dict[tuple[int, int], int],
    prior_index: int,
    continuation_index: int,
) -> dict[str, object]:
    continuation_positions = [
        position
        for position, entry in enumerate(variable_entries)
        if entry.get("source_index") == continuation_index and isinstance(entry.get("variable"), DefinedVariable)
    ]
    first_continuation_position = min(continuation_positions) if continuation_positions else len(variable_entries)
    prior_positions = [
        position
        for position, entry in enumerate(variable_entries[:first_continuation_position])
        if entry.get("source_index") == prior_index and isinstance(entry.get("variable"), DefinedVariable)
    ]
    if not prior_positions:
        return _boundary_decision(prior_index, continuation_index, "unchanged", ["no_open_parent"])
    parent_position = max(prior_positions)
    parent = variable_entries[parent_position]["variable"]
    source_parent = variable_entries[parent_position]["source_variable"]
    if not isinstance(parent, DefinedVariable) or not isinstance(source_parent, DefinedVariable):
        return _boundary_decision(prior_index, continuation_index, "unchanged", ["no_open_parent"])
    if not _is_open_parent(
        source_parent,
        normalized_tables[prior_index],
        row_views_by_source.get((prior_index, source_parent.row_start)),
    ):
        return _boundary_decision(
            prior_index,
            continuation_index,
            "unchanged",
            ["last_base_variable_is_not_open_parent"],
            parent.variable_name,
        )
    attached_levels: list[DefinedLevel] = []
    remove_positions: list[int] = []
    attachment_reasons: list[str] = []
    existing_labels = {clean_text(level.level_label).lower() for level in parent.levels}
    parent_row_view = row_views_by_source.get((prior_index, source_parent.row_start))
    first_continuation_source_row = None
    if continuation_positions:
        first_continuation_source_rows = [
            entry["source_variable"].row_start
            for position in continuation_positions
            if isinstance((entry := variable_entries[position]).get("source_variable"), DefinedVariable)
        ]
        first_continuation_source_row = min(first_continuation_source_rows) if first_continuation_source_rows else None
    for candidate_row_view in _leading_unclaimed_body_rows(
        normalized_tables[continuation_index],
        continuation_index,
        first_continuation_source_row,
        row_views_by_source,
    ):
        if not _is_leading_row_level_candidate(candidate_row_view):
            break
        normalized_label = clean_text(candidate_row_view.first_cell_raw).lower()
        if normalized_label in existing_labels:
            return _boundary_decision(
                prior_index,
                continuation_index,
                "rejected",
                ["duplicate_level_label"],
                parent.variable_name,
            )
        attached_levels.append(
            DefinedLevel(
                level_name=clean_text(candidate_row_view.first_cell_raw),
                level_label=candidate_row_view.first_cell_raw,
                row_idx=row_idx_by_source.get(
                    (continuation_index, candidate_row_view.row_idx),
                    candidate_row_view.row_idx,
                ),
                confidence=0.84,
            )
        )
        existing_labels.add(normalized_label)
        if "leading_body_rows_rewritten_as_levels" not in attachment_reasons:
            attachment_reasons.append("leading_body_rows_rewritten_as_levels")
    for position in continuation_positions:
        entry = variable_entries[position]
        candidate = entry["variable"]
        source_candidate = entry["source_variable"]
        if not isinstance(candidate, DefinedVariable) or not isinstance(source_candidate, DefinedVariable):
            break
        candidate_row_view = row_views_by_source.get((continuation_index, source_candidate.row_start))
        if not _is_level_candidate(source_candidate, candidate_row_view, parent_row_view):
            break
        normalized_label = clean_text(candidate.variable_label).lower()
        if normalized_label in existing_labels:
            return _boundary_decision(
                prior_index,
                continuation_index,
                "rejected",
                ["duplicate_level_label"],
                parent.variable_name,
            )
        attached_levels.append(
            DefinedLevel(
                level_name=candidate.variable_name,
                level_label=candidate.variable_label,
                row_idx=candidate.row_start,
                confidence=min(candidate.confidence or 0.86, 0.86),
            )
        )
        existing_labels.add(normalized_label)
        remove_positions.append(position)
        if "leading_continuation_variables_rewritten_as_levels" not in attachment_reasons:
            attachment_reasons.append("leading_continuation_variables_rewritten_as_levels")
    if not attached_levels:
        if not continuation_positions:
            return _boundary_decision(
                prior_index,
                continuation_index,
                "unchanged",
                ["no_continuation_variables"],
                parent.variable_name,
            )
        return _boundary_decision(
            prior_index,
            continuation_index,
            "unchanged",
            ["no_leading_continuation_levels"],
            parent.variable_name,
        )
    updated_parent = parent.model_copy(
        update={
            "variable_type": "categorical",
            "row_end": max([parent.row_end, *(level.row_idx for level in attached_levels)]),
            "levels": [*parent.levels, *attached_levels],
            "confidence": max(parent.confidence or 0.0, 0.86),
        }
    )
    variable_entries[parent_position]["variable"] = updated_parent
    for position in sorted(remove_positions, reverse=True):
        variable_entries.pop(position)
    return _boundary_decision(
        prior_index,
        continuation_index,
        "attached_levels",
        attachment_reasons,
        parent.variable_name,
        attached_level_count=len(attached_levels),
        confidence=0.86,
    )


def _leading_unclaimed_body_rows(
    table: NormalizedTable,
    source_index: int,
    first_defined_variable_row: int | None,
    row_views_by_source: dict[tuple[int, int], RowView],
) -> list[RowView]:
    rows: list[RowView] = []
    for row_idx in table.body_rows:
        if first_defined_variable_row is not None and row_idx >= first_defined_variable_row:
            break
        row_view = row_views_by_source.get((source_index, row_idx))
        if row_view is not None:
            rows.append(row_view)
    return rows


def _is_leading_row_level_candidate(row_view: RowView) -> bool:
    if not row_view.has_trailing_values:
        return False
    value_patterns: list[str] = []
    for cell in row_view.raw_cells[1:]:
        cleaned = clean_text(cell)
        if not cleaned:
            continue
        pattern = detect_value_pattern(cleaned).pattern
        if pattern != "p_value":
            value_patterns.append(pattern)
    if not value_patterns:
        return False
    count_like_count = sum(pattern in COUNT_LIKE_VALUE_PATTERNS for pattern in value_patterns)
    return count_like_count >= max(1, len(value_patterns) - 1)


def _is_open_parent(variable: DefinedVariable, table: NormalizedTable, row_view: RowView | None) -> bool:
    if variable.variable_type not in {"categorical", "unknown"}:
        return False
    if table.body_rows and variable.row_end < max(table.body_rows):
        return False
    parent_like = row_view is None or not row_view.has_trailing_values or row_view.nonempty_cell_count <= 1
    return parent_like or bool(variable.levels)


def _is_level_candidate(
    variable: DefinedVariable,
    row_view: RowView | None,
    parent_row_view: RowView | None,
) -> bool:
    if variable.levels or variable.variable_type == "continuous":
        return False
    if row_view is not None and not row_view.has_trailing_values:
        return False
    value_like = (
        variable.summary_style_hint in {"count_pct", "n_only"}
        or (row_view is not None and row_view.numeric_cell_count > 0)
    )
    if not value_like:
        return False
    if parent_row_view is not None and row_view is not None:
        parent_indent = parent_row_view.indent_level or 0
        candidate_indent = row_view.indent_level or 0
        if candidate_indent > parent_indent:
            return True
    return variable.variable_type in {"unknown", "binary", "categorical"}


def _boundary_decision(
    prior_index: int,
    continuation_index: int,
    decision: str,
    reasons: list[str],
    parent_variable_name: str | None = None,
    *,
    attached_level_count: int = 0,
    confidence: float | None = None,
) -> dict[str, object]:
    return {
        "boundary_id": f"continued_variable_boundary:{prior_index}:{continuation_index}",
        "base_table_index": prior_index,
        "continuation_table_index": continuation_index,
        "decision": decision,
        "parent_variable_name": parent_variable_name,
        "attached_level_count": attached_level_count,
        "confidence": confidence,
        "reasons": reasons,
    }


def _row_provenance(
    variables: list[DefinedVariable],
    source_by_integrated: dict[int, dict[str, object]],
    row_views_by_source: dict[tuple[int, int], RowView],
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for variable in variables:
        records.append(
            _row_provenance_record(
                variable.row_start,
                "variable",
                variable.variable_name,
                variable.variable_label,
                source_by_integrated,
                row_views_by_source,
            )
        )
        for level in variable.levels:
            records.append(
                _row_provenance_record(
                    level.row_idx,
                    "level",
                    level.level_name,
                    level.level_label,
                    source_by_integrated,
                    row_views_by_source,
                )
            )
    return records


def _row_provenance_record(
    integrated_row_idx: int,
    source_kind: str,
    source_name: str,
    source_label: str,
    source_by_integrated: dict[int, dict[str, object]],
    row_views_by_source: dict[tuple[int, int], RowView],
) -> dict[str, object]:
    source = source_by_integrated.get(integrated_row_idx, {})
    source_table_index = source.get("source_table_index")
    source_row_idx = source.get("source_row_idx")
    row_view = (
        row_views_by_source.get((int(source_table_index), int(source_row_idx)))
        if isinstance(source_table_index, int) and isinstance(source_row_idx, int)
        else None
    )
    return {
        **source,
        "integrated_row_idx": integrated_row_idx,
        "source_kind": source_kind,
        "source_name": source_name,
        "source_label": source_label,
        "indent_level": row_view.indent_level if row_view is not None else None,
        "likely_role": row_view.likely_role if row_view is not None else None,
        "first_cell_raw": row_view.first_cell_raw if row_view is not None else None,
        "first_cell_normalized": row_view.first_cell_normalized if row_view is not None else None,
        "nonempty_cell_count": row_view.nonempty_cell_count if row_view is not None else None,
        "numeric_cell_count": row_view.numeric_cell_count if row_view is not None else None,
        "has_trailing_values": row_view.has_trailing_values if row_view is not None else None,
    }
