"""Deterministic column-definition assembly for TableDefinition."""

from __future__ import annotations

import re
from dataclasses import dataclass

from table1_parser.column_header_schema import build_column_header_schema, column_header_descriptors
from table1_parser.heuristics.header_role_patterns import detect_p_value_header
from table1_parser.normalize.text_normalizer import normalize_label_text
from table1_parser.schemas import (
    ColumnDefinition,
    ColumnHeaderDescriptor,
    ColumnHeaderSchema,
    DefinedColumn,
    NormalizedTable,
)
from table1_parser.text_cleaning import clean_text


BY_PATTERN = re.compile(r"\b(?:stratified\s+)?by\s+(.+?)(?:[.;]|$)", re.IGNORECASE)
LABEL_COLUMN_TOKENS = {"characteristic", "characteristics", "variable", "variables", "factor", "covariate"}
OVERALL_HEADER_TOKENS = {"overall", "all", "total", "total population", "full cohort"}
GROUP_COMPARISON_TOKENS = {"control", "controls", "reference"}
STAT_SMD_PATTERN = re.compile(r"\b(?:smd|standardized mean difference)\b", re.IGNORECASE)
RANGE_LEVEL_PATTERN = re.compile(r"^(?:[<>]=?\s*)?-?\d+(?:\.\d+)?(?:\s*-\s*-?\d+(?:\.\d+)?)?$")


@dataclass(slots=True)
class GroupLevelGuess:
    """One grouped-column level inferred from the header layout."""

    col_idx: int
    level_label: str
    level_name: str
    order: int
    confidence: float


@dataclass(slots=True)
class StatColumnGuess:
    """One statistical/test column inferred from the header layout."""

    col_idx: int
    subtype: str
    confidence: float


@dataclass(slots=True)
class ColumnGroupingAnalysis:
    """Internal deterministic interpretation of column grouping structure."""

    label_col_idx: int
    grouping_label: str | None
    grouping_name: str | None
    overall_col_indices: list[int]
    grouped_col_indices: list[int]
    stat_col_indices: list[int]
    group_levels: dict[int, GroupLevelGuess]
    stat_columns: dict[int, StatColumnGuess]
    confidence: float | None


def _build_grouping_analysis(
    table: NormalizedTable,
    descriptors: list[ColumnHeaderDescriptor],
    label_col_idx: int | None = None,
) -> ColumnGroupingAnalysis:
    """Partition columns into label, overall, grouped, and statistical blocks."""
    if label_col_idx is None:
        label_col_idx = 0
    descriptor_col_indices = {descriptor.col_idx for descriptor in descriptors}
    if label_col_idx not in descriptor_col_indices:
        label_col_idx = 0
    if descriptors and label_col_idx == 0:
        first_label = descriptors[0].leaf_label.lower()
        if first_label and first_label not in LABEL_COLUMN_TOKENS and descriptors[0].column_label:
            label_col_idx = 0
    stat_columns: dict[int, StatColumnGuess] = {}
    for descriptor in descriptors:
        if descriptor.col_idx == label_col_idx:
            continue
        label = clean_text(" ".join([descriptor.column_label, descriptor.leaf_label])).lower()
        subtype = None
        if label:
            if STAT_SMD_PATTERN.search(label):
                subtype = "smd"
            else:
                p_value_match = detect_p_value_header(descriptor.column_label, descriptor.col_idx, len(descriptors))
                if p_value_match is None and descriptor.leaf_label != descriptor.column_label:
                    p_value_match = detect_p_value_header(descriptor.leaf_label, descriptor.col_idx, len(descriptors))
                if p_value_match is not None:
                    subtype = p_value_match.subtype
        if subtype is None:
            continue
        p_value_match = detect_p_value_header(descriptor.column_label, descriptor.col_idx, len(descriptors))
        stat_columns[descriptor.col_idx] = StatColumnGuess(
            col_idx=descriptor.col_idx,
            subtype=subtype,
            confidence=0.99 if subtype == "smd" else (p_value_match.confidence if p_value_match else 0.97),
        )
    data_descriptors = [
        descriptor
        for descriptor in descriptors
        if descriptor.col_idx != label_col_idx and descriptor.col_idx not in stat_columns
    ]
    overall_col_indices: list[int] = []
    if data_descriptors:
        explicit_overall = [
            descriptor.col_idx
            for descriptor in data_descriptors
            if descriptor.leaf_label.lower() in OVERALL_HEADER_TOKENS or descriptor.column_label.lower() in OVERALL_HEADER_TOKENS
        ]
        if explicit_overall:
            overall_col_indices = [explicit_overall[0]]
        elif len(data_descriptors) >= 2:
            overall_col_indices = [data_descriptors[0].col_idx]
        elif len(data_descriptors) == 1 and any(descriptor.col_idx in stat_columns for descriptor in descriptors[1:]):
            overall_col_indices = [data_descriptors[0].col_idx]
    grouped_descriptors = [descriptor for descriptor in data_descriptors if descriptor.col_idx not in overall_col_indices]
    grouping_label = None
    for text in (table.title, table.caption):
        cleaned = clean_text(text or "")
        match = BY_PATTERN.search(cleaned)
        if match is not None:
            grouping_label = clean_text(match.group(1).strip(" :"))
            break
    if grouping_label is None:
        shared_contexts = {descriptor.shared_context_label for descriptor in grouped_descriptors if descriptor.shared_context_label}
        if len(shared_contexts) == 1:
            grouping_label = shared_contexts.pop()
    if grouping_label is None and descriptors:
        label_header = descriptors[label_col_idx].column_label
        if label_header and clean_text(label_header).lower() not in LABEL_COLUMN_TOKENS:
            grouping_label = label_header
    grouping_name = normalize_label_text(grouping_label) if grouping_label else None
    group_levels = {
        descriptor.col_idx: GroupLevelGuess(
            col_idx=descriptor.col_idx,
            level_label=(
                descriptor.shared_context_label
                if descriptor.shared_context_label
                and (
                    RANGE_LEVEL_PATTERN.fullmatch(descriptor.leaf_label.strip())
                    or (
                        any(char.isdigit() for char in descriptor.leaf_label)
                        and not any(char.isalpha() for char in descriptor.leaf_label)
                    )
                )
                else descriptor.leaf_label or descriptor.column_label
            ),
            level_name=normalize_label_text(
                (
                    descriptor.shared_context_label
                    if descriptor.shared_context_label
                    and (
                        RANGE_LEVEL_PATTERN.fullmatch(descriptor.leaf_label.strip())
                        or (
                            any(char.isdigit() for char in descriptor.leaf_label)
                            and not any(char.isalpha() for char in descriptor.leaf_label)
                        )
                    )
                    else descriptor.leaf_label or descriptor.column_label
                )
            )
            or descriptor.column_name,
            order=order,
            confidence=0.9 if descriptor.shared_context_label else 0.82,
        )
        for order, descriptor in enumerate(grouped_descriptors, start=1)
    }
    confidence_components = [
        0.95 if overall_col_indices else 0.6,
        0.9 if grouped_descriptors else 0.65,
        0.95 if stat_columns else 0.7,
        0.92 if grouping_label else 0.68,
    ]
    return ColumnGroupingAnalysis(
        label_col_idx=label_col_idx,
        grouping_label=grouping_label,
        grouping_name=grouping_name,
        overall_col_indices=overall_col_indices,
        grouped_col_indices=[descriptor.col_idx for descriptor in grouped_descriptors],
        stat_col_indices=sorted(stat_columns),
        group_levels=group_levels,
        stat_columns=stat_columns,
        confidence=round(sum(confidence_components) / len(confidence_components), 4) if descriptors else None,
    )


def build_column_definition(
    table: NormalizedTable,
    column_schema: ColumnHeaderSchema | None = None,
) -> ColumnDefinition:
    """Build value-free column definitions from a normalized table."""
    if column_schema is None or column_schema.table_id != table.table_id:
        column_schema = build_column_header_schema(table)
    descriptors = column_header_descriptors(column_schema)
    analysis = _build_grouping_analysis(table, descriptors, column_schema.label_col_idx)
    columns: list[DefinedColumn] = []
    for descriptor in descriptors:
        if descriptor.col_idx == analysis.label_col_idx:
            continue
        lowered = clean_text(descriptor.column_label).lower()
        role = "unknown"
        confidence = 0.45
        grouping_variable_hint = None
        group_level_label = None
        group_level_name = None
        group_order = None
        statistic_subtype = None
        if descriptor.col_idx in analysis.overall_col_indices:
            role = "overall"
            confidence = 0.96 if lowered in OVERALL_HEADER_TOKENS else 0.84
            grouping_variable_hint = analysis.grouping_name
        elif descriptor.col_idx in analysis.grouped_col_indices:
            level_guess = analysis.group_levels[descriptor.col_idx]
            role = "comparison_group" if level_guess.level_label.lower() in GROUP_COMPARISON_TOKENS else "group"
            confidence = level_guess.confidence if analysis.grouping_name else max(0.78, level_guess.confidence - 0.08)
            grouping_variable_hint = analysis.grouping_name
            group_level_label = level_guess.level_label
            group_level_name = level_guess.level_name
            group_order = level_guess.order
        elif descriptor.col_idx in analysis.stat_col_indices:
            stat_guess = analysis.stat_columns[descriptor.col_idx]
            role = "smd" if stat_guess.subtype == "smd" else "p_value"
            confidence = stat_guess.confidence
            statistic_subtype = stat_guess.subtype
        elif analysis.grouping_name and descriptor.col_idx != analysis.label_col_idx and descriptor.column_label:
            role = "group"
            confidence = 0.72
            grouping_variable_hint = analysis.grouping_name
        columns.append(
            DefinedColumn(
                col_idx=descriptor.col_idx,
                column_name=descriptor.column_name,
                column_label=descriptor.column_label,
                inferred_role=role,
                grouping_variable_hint=grouping_variable_hint,
                group_level_label=group_level_label,
                group_level_name=group_level_name,
                group_order=group_order,
                statistic_subtype=statistic_subtype,
                confidence=confidence,
            )
        )
    if not columns:
        definition_confidence = None
    else:
        base = sum(column.confidence or 0.0 for column in columns) / len(columns)
        definition_confidence = max(round(base, 4), analysis.confidence or 0.0)
    return ColumnDefinition(
        grouping_label=analysis.grouping_label,
        grouping_name=analysis.grouping_name,
        group_count=len(analysis.grouped_col_indices) if analysis.grouped_col_indices else None,
        columns=columns,
        confidence=definition_confidence,
    )
