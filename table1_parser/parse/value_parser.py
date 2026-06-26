"""Value parsing for final ParsedTable assembly."""

from __future__ import annotations

import re
from dataclasses import dataclass

from table1_parser.heuristics.value_pattern_detector import detect_value_pattern
from table1_parser.schemas import DefinedVariable, NormalizedTable, ParsedColumn, ValueRecord
from table1_parser.text_cleaning import clean_text


INTEGER_TOKEN = r"(?:\d{1,3}(?:,\d{3})*|\d+)"
DECIMAL_TOKEN = r"-?\d+(?:\.\d+)?"
FOOTNOTE_SUFFIX_TOKEN = r"(?:\s*(?:[*†‡§¶#{}|]+|[a-z]))*"
COUNT_PCT_EXTRACT_PATTERN = re.compile(
    rf"^(?P<count>{INTEGER_TOKEN})\s*\(\s*(?P<percent>\d+(?:\.\d+)?)%?\s*\)$"
)
MEAN_SD_EXTRACT_PATTERN = re.compile(
    rf"^(?P<mean>{DECIMAL_TOKEN})(?:\s*\(\s*(?P<sd_paren>{DECIMAL_TOKEN})\s*\)|\s*±\s*(?P<sd_pm>{DECIMAL_TOKEN})|\s+6\s+(?P<sd_six>{DECIMAL_TOKEN})){FOOTNOTE_SUFFIX_TOKEN}$"
)
N_ONLY_EXTRACT_PATTERN = re.compile(rf"^(?P<count>{INTEGER_TOKEN})$")
P_VALUE_NUMERIC_PATTERN = re.compile(rf"^(?:[<>]=?\s*)?(?P<value>0?\.\d+|\.\d+|1\.0+){FOOTNOTE_SUFFIX_TOKEN}$", re.IGNORECASE)
HEADER_N_PATTERN = re.compile(r"\bn\s*=\s*(?P<count>\d[\d,]*)\b", re.IGNORECASE)
COUNT_ROW_LABELS = {"n", "number", "no"}


@dataclass(slots=True)
class ParsedCell:
    """Parsed interpretation of one raw table cell."""

    value_type: str
    parsed_numeric: float | None
    parsed_secondary_numeric: float | None
    confidence: float


def build_value_records(
    table: NormalizedTable,
    variables: list[DefinedVariable],
    columns: list[ParsedColumn],
) -> tuple[list[ValueRecord], list[str]]:
    """Build long-format value records and attach soft count-percent notes."""
    row_views_by_idx = {row_view.row_idx: row_view for row_view in table.row_views}
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
            for column in columns:
                if column.col_idx >= len(row_view.raw_cells):
                    continue
                raw_value = row_view.raw_cells[column.col_idx]
                if not clean_text(raw_value):
                    continue
                parsed_cell = parse_cell_value(raw_value, column.inferred_role)
                values.append(
                    ValueRecord(
                        row_idx=row_idx,
                        col_idx=column.col_idx,
                        variable_name=variable.variable_name,
                        level_label=level_label,
                        column_name=column.column_name,
                        raw_value=raw_value,
                        value_type=parsed_cell.value_type,
                        parsed_numeric=parsed_cell.parsed_numeric,
                        parsed_secondary_numeric=parsed_cell.parsed_secondary_numeric,
                        confidence=parsed_cell.confidence,
                    )
                )

    notes = apply_count_percent_heuristics(table, variables, columns, values)
    return values, notes


def parse_cell_value(raw_value: str, column_role: str) -> ParsedCell:
    """Parse one raw cell conservatively into the ParsedTable numeric slots."""
    cleaned = clean_text(raw_value)
    pattern = detect_value_pattern(raw_value)

    if pattern.pattern == "count_pct":
        match = COUNT_PCT_EXTRACT_PATTERN.fullmatch(cleaned)
        if match is not None:
            return ParsedCell(
                value_type="count",
                parsed_numeric=float(int(match.group("count").replace(",", ""))),
                parsed_secondary_numeric=float(match.group("percent")),
                confidence=pattern.confidence,
            )
    if pattern.pattern == "mean_sd":
        match = MEAN_SD_EXTRACT_PATTERN.fullmatch(cleaned)
        if match is not None:
            secondary = match.group("sd_paren") or match.group("sd_pm") or match.group("sd_six")
            return ParsedCell(
                value_type="mean_sd",
                parsed_numeric=float(match.group("mean")),
                parsed_secondary_numeric=float(secondary) if secondary is not None else None,
                confidence=pattern.confidence,
            )
    if pattern.pattern == "n_only":
        match = N_ONLY_EXTRACT_PATTERN.fullmatch(cleaned)
        if match is not None:
            return ParsedCell(
                value_type="count",
                parsed_numeric=float(int(match.group("count").replace(",", ""))),
                parsed_secondary_numeric=None,
                confidence=pattern.confidence,
            )
    if pattern.pattern == "p_value":
        match = P_VALUE_NUMERIC_PATTERN.fullmatch(cleaned.lower().removeprefix("p=").strip())
        return ParsedCell(
            value_type="text",
            parsed_numeric=float(match.group("value")) if match is not None else None,
            parsed_secondary_numeric=None,
            confidence=pattern.confidence if column_role == "p_value" else min(pattern.confidence, 0.75),
        )
    return ParsedCell(
        value_type="text" if column_role in {"p_value", "statistic"} else "unknown",
        parsed_numeric=None,
        parsed_secondary_numeric=None,
        confidence=0.6 if column_role in {"p_value", "statistic"} else 0.4,
    )


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
            parsed = parse_cell_value(count_row.raw_cells[column.col_idx], column.inferred_role)
            if parsed.value_type == "count" and parsed.parsed_numeric is not None:
                denominators[column.col_idx] = int(round(parsed.parsed_numeric))
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
                value for value in column_values if value is not None and value.value_type == "count" and value.parsed_secondary_numeric is not None
            ]
            if len(parsed_values) != len(level_rows):
                continue
            observed_percent = sum(value.parsed_secondary_numeric or 0.0 for value in parsed_values)
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
