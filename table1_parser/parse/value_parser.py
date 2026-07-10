"""Value parsing for final ParsedTable assembly."""

from __future__ import annotations

import re
from collections.abc import Sequence

from table1_parser.parse.cell_value_components import build_parsed_cell_values, parse_cell_value_components
from table1_parser.schemas import (
    DefinedVariable,
    NormalizedTable,
    ParsedCellValue,
    ParsedColumn,
    ResolvedRowProvenance,
    ValueComponent,
    ValueRecord,
)
from table1_parser.text_cleaning import clean_text


HEADER_N_PATTERN = re.compile(r"\bn\s*=\s*(?P<count>\d[\d,]*)\b", re.IGNORECASE)
COUNT_ROW_LABELS = {"n", "number", "no"}


def build_value_records(
    table: NormalizedTable,
    variables: list[DefinedVariable],
    columns: list[ParsedColumn],
    parsed_cell_values: list[ParsedCellValue] | None = None,
    source_table_index: int | None = None,
    row_provenance: Sequence[ResolvedRowProvenance] | None = None,
) -> tuple[list[ValueRecord], list[str]]:
    """Build semantic value records and attach soft count-percent notes."""
    row_views_by_idx = {row_view.row_idx: row_view for row_view in table.row_views}
    provenance_by_row_idx = (
        {provenance.resolved_row_idx: provenance for provenance in row_provenance}
        if row_provenance is not None
        else {}
    )
    if parsed_cell_values is None:
        parsed_cell_values = build_parsed_cell_values(
            [table],
            value_column_indices_by_table_id={table.table_id: {column.col_idx for column in columns}},
        )
    component_values_by_key = {
        (value.source_table_id, value.row_idx, value.col_idx): value
        for value in parsed_cell_values
    }
    values: list[ValueRecord] = []

    for variable in variables:
        row_targets = (
            [(level.row_idx, level.level_label) for level in variable.levels]
            if variable.levels
            else [(variable.row_start, None)]
        )
        for row_idx, level_label in row_targets:
            row_view = row_views_by_idx.get(row_idx)
            if row_view is None:
                continue
            source_row = provenance_by_row_idx.get(row_idx)
            source_table_id = source_row.source_table_id if source_row is not None else table.table_id
            source_row_idx = source_row.source_row_idx if source_row is not None else row_idx
            source_index = (
                source_row.source_table_index
                if source_row is not None
                else source_table_index
                if source_table_index is not None
                else 0
            )
            for column in columns:
                if column.col_idx >= len(row_view.raw_cells):
                    continue
                raw_value = row_view.raw_cells[column.col_idx]
                if not clean_text(raw_value):
                    continue
                component_value = component_values_by_key.get((source_table_id, source_row_idx, column.col_idx))
                if component_value is None:
                    parsed_component = parse_cell_value_components(raw_value, summary_style_hint=variable.summary_style_hint)
                    component_value = ParsedCellValue(
                        source_table_index=source_index,
                        source_table_id=source_table_id,
                        row_idx=source_row_idx,
                        col_idx=column.col_idx,
                        raw_value=raw_value,
                        raw_fragments=[raw_value],
                        parse_pattern=parsed_component.parse_pattern,
                        components=parsed_component.components,
                        confidence=parsed_component.confidence,
                        notes=parsed_component.notes,
                    )
                value_raw_text = component_value.raw_value
                semantic_components, semantic_notes = _semantic_components_for_variable(component_value.components, variable.summary_style_hint)
                confidence_values = [component.confidence for component in semantic_components if component.confidence is not None]
                if component_value.confidence is not None:
                    confidence_values.append(component_value.confidence)
                confidence = round(sum(confidence_values) / len(confidence_values), 4) if confidence_values else None
                values.append(
                    ValueRecord(
                        source_table_index=component_value.source_table_index,
                        source_table_id=component_value.source_table_id,
                        row_idx=row_idx,
                        col_idx=column.col_idx,
                        variable_name=variable.variable_name,
                        variable_label=variable.variable_label,
                        level_label=level_label,
                        column_name=column.column_name,
                        column_label=column.column_label,
                        header_leaf_id=column.header_leaf_id,
                        header_leaf_label=column.header_leaf_label,
                        header_group_ids=column.header_group_ids,
                        header_group_labels=column.header_group_labels,
                        header_path=column.header_path,
                        raw_value=value_raw_text,
                        parse_pattern=component_value.parse_pattern,
                        components=semantic_components,
                        confidence=confidence,
                        notes=[*component_value.notes, *semantic_notes],
                    )
                )

    notes = apply_count_percent_heuristics(table, variables, columns, values)
    return values, notes


def _semantic_components_for_variable(
    components: list[ValueComponent],
    summary_style_hint: str | None,
) -> tuple[list[ValueComponent], list[str]]:
    """Resolve context-dependent component kinds for the semantic value layer."""
    notes: list[str] = []
    normalized_hint = clean_text(summary_style_hint or "").lower().replace("-", "_")
    if normalized_hint not in {"mean_sd", "mean_s_d", "mean_standard_deviation", "estimate_se", "mean_se", "estimate_standard_error", "mean_standard_error"}:
        return [component.model_copy(deep=True) for component in components], notes

    has_ambiguous_uncertainty = any(component.kind == "unknown" and "ambiguous_uncertainty_component" in component.notes for component in components)
    if not has_ambiguous_uncertainty:
        return [component.model_copy(deep=True) for component in components], notes

    resolved_components: list[ValueComponent] = []
    if normalized_hint in {"mean_sd", "mean_s_d", "mean_standard_deviation"}:
        for component in components:
            if component.kind == "estimate":
                resolved_components.append(component.model_copy(update={"kind": "mean"}, deep=True))
            elif component.kind == "unknown" and "ambiguous_uncertainty_component" in component.notes:
                resolved_components.append(component.model_copy(update={"kind": "sd", "notes": []}, deep=True))
            else:
                resolved_components.append(component.model_copy(deep=True))
        notes.append("semantic_uncertainty_resolved:mean_sd")
    else:
        for component in components:
            if component.kind == "unknown" and "ambiguous_uncertainty_component" in component.notes:
                resolved_components.append(component.model_copy(update={"kind": "se", "notes": []}, deep=True))
            else:
                resolved_components.append(component.model_copy(deep=True))
        notes.append("semantic_uncertainty_resolved:estimate_se")
    return resolved_components, notes


def _numeric_component(components: list[ValueComponent], kind: str) -> float | None:
    """Return one numeric component value by kind."""
    for component in components:
        if component.kind == kind and isinstance(component.value, (int, float)):
            return float(component.value)
    return None


def apply_count_percent_heuristics(
    table: NormalizedTable,
    variables: list[DefinedVariable],
    columns: list[ParsedColumn],
    values: list[ValueRecord],
) -> list[str]:
    """Adjust count-percent confidence softly and return table-level notes."""
    notes: list[str] = []
    if not values:
        return notes

    values_by_key = {(value.variable_name, value.row_idx, value.col_idx): value for value in values}
    candidate_columns = [column for column in sorted(columns, key=lambda item: item.col_idx) if column.inferred_role not in {"p_value", "statistic"}]
    if not candidate_columns:
        return notes

    first_substantive_column = candidate_columns[0]
    lowered = clean_text(first_substantive_column.column_label).lower()
    overall_column = first_substantive_column if (
        first_substantive_column == candidate_columns[0]
        and (
            first_substantive_column.inferred_role == "overall"
            or lowered in {"overall", "total", "all"}
            or (not lowered and any(other.inferred_role == "group" for other in candidate_columns[1:]))
        )
    ) else None
    denominators: dict[int, int] = {}
    for column in columns:
        match = HEADER_N_PATTERN.search(clean_text(column.column_label))
        if match is not None:
            denominators[column.col_idx] = int(match.group("count").replace(",", ""))

    count_row = None
    for row_view in table.row_views:
        label = clean_text(row_view.first_cell_raw).lower().rstrip(".")
        if label in COUNT_ROW_LABELS:
            count_row = row_view
            break
    if count_row is not None:
        for column in columns:
            if column.col_idx >= len(count_row.raw_cells) or column.col_idx in denominators:
                continue
            parsed_count_components = parse_cell_value_components(count_row.raw_cells[column.col_idx])
            count = _numeric_component(parsed_count_components.components, "count")
            if count is not None:
                denominators[column.col_idx] = int(round(count))
    overall_n = denominators.get(overall_column.col_idx) if overall_column is not None else None

    for variable in variables:
        if not variable.levels:
            continue
        if variable.summary_style_hint != "count_pct":
            continue
        level_rows = [level.row_idx for level in variable.levels]
        for column in candidate_columns:
            column_values = [
                values_by_key.get((variable.variable_name, row_idx, column.col_idx))
                for row_idx in level_rows
            ]
            parsed_values = [
                value
                for value in column_values
                if value is not None
                and _numeric_component(value.components, "count") is not None
                and _numeric_component(value.components, "percent") is not None
            ]
            if len(parsed_values) != len(level_rows):
                continue
            observed_percent = sum(_numeric_component(value.components, "percent") or 0.0 for value in parsed_values)
            note: str | None = None
            delta = 0.0
            if overall_column is not None and column.col_idx == overall_column.col_idx:
                if abs(observed_percent - 100.0) <= 2.0:
                    delta = 0.03
                else:
                    delta = -0.15
                    note = (
                        f"count_pct_overall_sum_mismatch:"
                        f" variable={variable.variable_name}"
                        f" column={column.column_name}"
                        f" observed={observed_percent:.1f}"
                        " expected=100.0"
                    )
            elif overall_n is not None:
                subgroup_n = denominators.get(column.col_idx)
                if subgroup_n is not None and overall_n > 0:
                    expected_percent = subgroup_n / overall_n * 100.0
                    if abs(observed_percent - expected_percent) <= 3.0:
                        delta = 0.02
                    else:
                        delta = -0.10
                        note = (
                            f"count_pct_group_share_mismatch:"
                            f" variable={variable.variable_name}"
                            f" column={column.column_name}"
                            f" observed={observed_percent:.1f}"
                            f" expected={expected_percent:.1f}"
                        )
            for value in parsed_values:
                base = value.confidence if value.confidence is not None else 0.9
                value.confidence = max(0.0, min(1.0, round(base + delta, 4)))
            if note is not None:
                notes.append(note)
    return notes
