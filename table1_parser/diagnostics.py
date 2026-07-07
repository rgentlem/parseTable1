"""Parse-quality diagnostics for normalized tables and heuristic outputs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from table1_parser.heuristics.models import ColumnRoleGuess, RowClassification, VariableBlock
from table1_parser.heuristics.value_pattern_detector import detect_value_pattern
from table1_parser.schemas import ExtractedTable, NormalizedTable
from table1_parser.text_cleaning import clean_text


Severity = Literal["info", "warning", "error"]
RECOGNIZED_PATTERNS = {"count_pct", "mean_sd", "median_iqr", "n_only", "p_value"}
UNKNOWN_WARNING_THRESHOLD = 0.25
UNKNOWN_SUSPICIOUS_THRESHOLD = 0.50
UNKNOWN_FAILURE_THRESHOLD = 0.70


class DiagnosticItem(BaseModel):
    """A single parse-quality signal with simple severity and location metadata."""

    severity: Severity
    code: str
    message: str
    row_idx: int | None = Field(default=None, ge=0)
    col_idx: int | None = Field(default=None, ge=0)


class ParseQualitySummary(BaseModel):
    """Compact counts that summarize broad parse quality for a table."""

    total_body_rows: int = Field(ge=0)
    unknown_row_count: int = Field(ge=0)
    unknown_row_fraction: float = Field(ge=0.0, le=1.0)
    variable_block_count: int = Field(ge=0)
    recognized_value_pattern_fraction: float = Field(ge=0.0, le=1.0)
    row_warning_count: int = Field(ge=0)
    column_warning_count: int = Field(ge=0)


class ParseQualityReport(BaseModel):
    """Structured parse-quality report for one normalized table."""

    report_timestamp: str
    source_identifier: str | None = None
    table_id: str
    summary: ParseQualitySummary
    table_diagnostics: list[DiagnosticItem] = Field(default_factory=list)
    row_diagnostics: list[DiagnosticItem] = Field(default_factory=list)
    column_diagnostics: list[DiagnosticItem] = Field(default_factory=list)


def _utc_timestamp() -> str:
    """Return the current UTC timestamp in ISO 8601 with a trailing Z."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_parse_quality_report(
    table: NormalizedTable,
    row_classifications: list[RowClassification],
    variable_blocks: list[VariableBlock] | None = None,
    column_roles: list[ColumnRoleGuess] | None = None,
    *,
    extracted_table: ExtractedTable | None = None,
    source_identifier: str | None = None,
) -> ParseQualityReport:
    """Build a conservative parse-quality report from existing pipeline outputs."""
    variable_blocks = variable_blocks or []
    column_roles = column_roles or []
    classification_by_row = {item.row_idx: item for item in row_classifications}
    row_order = [row_view.row_idx for row_view in table.row_views]

    row_diagnostics: list[DiagnosticItem] = []
    column_diagnostics: list[DiagnosticItem] = []
    table_diagnostics: list[DiagnosticItem] = []

    unknown_row_count = sum(item.classification == "unknown" for item in row_classifications)
    total_body_rows = len(table.row_views)
    unknown_fraction = unknown_row_count / total_body_rows if total_body_rows else 0.0

    all_value_patterns = []
    recognized_pattern_count = 0
    total_value_count = 0
    for row_view in table.row_views:
        classification = classification_by_row.get(row_view.row_idx)
        trailing_patterns = []
        for raw_value in row_view.raw_cells[1:]:
            cleaned = clean_text(raw_value)
            if not cleaned:
                continue
            total_value_count += 1
            pattern = detect_value_pattern(raw_value)
            all_value_patterns.append(pattern)
            trailing_patterns.append(pattern)
            if pattern.pattern in RECOGNIZED_PATTERNS:
                recognized_pattern_count += 1

        if classification is None:
            continue
        if classification.classification == "unknown":
            row_diagnostics.append(
                DiagnosticItem(
                    severity="warning",
                    code="unknown_row",
                    message="Row classification is unknown.",
                    row_idx=row_view.row_idx,
                )
            )
        if row_view.has_trailing_values and not clean_text(row_view.first_cell_raw):
            row_diagnostics.append(
                DiagnosticItem(
                    severity="warning",
                    code="missing_label_with_values",
                    message="Row has populated trailing cells but no informative label.",
                    row_idx=row_view.row_idx,
                )
            )
        if classification.classification == "continuous_variable_row" and trailing_patterns and all(
            pattern.pattern == "unknown" for pattern in trailing_patterns
        ):
            row_diagnostics.append(
                DiagnosticItem(
                    severity="warning",
                    code="continuous_without_pattern",
                    message="Continuous row has no recognizable value pattern.",
                    row_idx=row_view.row_idx,
                )
            )
        if classification.classification == "level_row":
            try:
                row_position = row_order.index(row_view.row_idx)
            except ValueError:
                parent_row_idx = None
            else:
                parent_row_idx = None
                for prior_row_idx in reversed(row_order[:row_position]):
                    prior = classification_by_row.get(prior_row_idx)
                    if prior is None:
                        continue
                    if prior.classification == "variable_header":
                        parent_row_idx = prior_row_idx
                        break
                    if prior.classification in {"continuous_variable_row", "section_header"}:
                        break
            if parent_row_idx is None:
                row_diagnostics.append(
                    DiagnosticItem(
                        severity="warning",
                        code="level_without_parent",
                        message="Level row has no plausible categorical parent above it.",
                        row_idx=row_view.row_idx,
                    )
                )
        if classification.classification == "variable_header":
            try:
                row_position = row_order.index(row_view.row_idx)
            except ValueError:
                has_following_levels = False
            else:
                has_following_levels = False
                for next_row_idx in row_order[row_position + 1 :]:
                    next_classification = classification_by_row.get(next_row_idx)
                    if next_classification is None:
                        continue
                    if next_classification.classification == "level_row":
                        has_following_levels = True
                        break
                    if next_classification.classification in {"variable_header", "continuous_variable_row", "section_header"}:
                        break
            if not has_following_levels:
                row_diagnostics.append(
                    DiagnosticItem(
                        severity="info",
                        code="parent_without_levels",
                        message="Categorical parent row has no plausible levels below it.",
                        row_idx=row_view.row_idx,
                    )
                )

    if unknown_fraction > UNKNOWN_FAILURE_THRESHOLD:
        table_diagnostics.append(
            DiagnosticItem(
                severity="error",
                code="unknown_row_fraction_likely_failure",
                message=f"Unknown row fraction is very high ({unknown_fraction:.2f}).",
            )
        )
    elif unknown_fraction > UNKNOWN_SUSPICIOUS_THRESHOLD:
        table_diagnostics.append(
            DiagnosticItem(
                severity="warning",
                code="unknown_row_fraction_suspicious",
                message=f"Unknown row fraction is suspiciously high ({unknown_fraction:.2f}).",
            )
        )
    elif unknown_fraction > UNKNOWN_WARNING_THRESHOLD:
        table_diagnostics.append(
            DiagnosticItem(
                severity="warning",
                code="unknown_row_fraction_warning",
                message=f"Unknown row fraction exceeds the warning threshold ({unknown_fraction:.2f}).",
            )
        )

    if total_body_rows >= 4 and len(variable_blocks) == 0:
        table_diagnostics.append(
            DiagnosticItem(
                severity="error" if unknown_fraction > UNKNOWN_SUSPICIOUS_THRESHOLD else "warning",
                code="weak_variable_structure",
                message="No variable blocks were detected in a non-trivial table body.",
            )
        )

    recognized_fraction = recognized_pattern_count / total_value_count if total_value_count else 0.0
    if total_value_count >= 6 and recognized_fraction < 0.25:
        table_diagnostics.append(
            DiagnosticItem(
                severity="error",
                code="low_value_pattern_recognition",
                message=f"Recognized value-pattern rate is very low ({recognized_fraction:.2f}).",
            )
        )
    elif total_value_count >= 6 and recognized_fraction < 0.50:
        table_diagnostics.append(
            DiagnosticItem(
                severity="warning",
                code="weak_value_pattern_recognition",
                message=f"Recognized value-pattern rate is low ({recognized_fraction:.2f}).",
            )
        )

    dropped_leading = int(table.metadata.get("dropped_leading_cols", 0))
    dropped_trailing = int(table.metadata.get("dropped_trailing_cols", 0))
    if dropped_leading or dropped_trailing:
        table_diagnostics.append(
            DiagnosticItem(
                severity="info",
                code="edge_column_cleanup",
                message=f"Normalization dropped leading={dropped_leading} trailing={dropped_trailing} edge columns.",
            )
        )

    header_detection = table.metadata.get("header_detection", {})
    if len(table.header_rows) >= 3:
        table_diagnostics.append(
            DiagnosticItem(
                severity="warning",
                code="suspicious_header_row_count",
                message=f"Header detection selected {len(table.header_rows)} rows; more than 2 header rows is unusual.",
            )
        )
    if (
        isinstance(header_detection, dict)
        and header_detection.get("source") == "horizontal_rule_separator"
        and header_detection.get("rule_content_disagreement")
    ):
        table_diagnostics.append(
            DiagnosticItem(
                severity="info",
                code="header_rule_content_disagreement",
                message="Strong horizontal-rule evidence overrode content-based header detection.",
            )
        )
    split_comparison = table.metadata.get("header_body_split_rule_comparison")
    if isinstance(split_comparison, dict):
        candidates = split_comparison.get("candidates")
        if isinstance(candidates, list):
            body_start_by_rule = {
                candidate.get("rule"): candidate.get("body_start")
                for candidate in candidates
                if isinstance(candidate, dict) and isinstance(candidate.get("body_start"), int)
            }
            hline_body_start = body_start_by_rule.get("selective_hline_prefix")
            value_anchor_body_start = body_start_by_rule.get("first_value_region_data_row")
            if (
                isinstance(hline_body_start, int)
                and isinstance(value_anchor_body_start, int)
                and hline_body_start != value_anchor_body_start
            ):
                selected = split_comparison.get("selected")
                selected_body_start = selected.get("body_start") if isinstance(selected, dict) else None
                expected_body_leader_gap = False
                if (
                    hline_body_start < value_anchor_body_start
                    and selected_body_start == hline_body_start
                    and value_anchor_body_start - hline_body_start <= 3
                ):
                    row_view_by_idx = {row_view.row_idx: row_view for row_view in table.row_views}
                    variable_start_rows = {block.row_start for block in variable_blocks}
                    expected_body_leader_gap = True
                    for row_idx in range(hline_body_start, value_anchor_body_start):
                        classification = classification_by_row.get(row_idx)
                        if row_idx not in variable_start_rows and (
                            classification is None
                            or classification.classification not in {"variable_header", "section_header"}
                        ):
                            expected_body_leader_gap = False
                            break
                        row_view = row_view_by_idx.get(row_idx)
                        if row_view is None:
                            expected_body_leader_gap = False
                            break
                        recognized_values = [
                            detect_value_pattern(raw_value).pattern
                            for raw_value in row_view.raw_cells[1:]
                            if clean_text(raw_value)
                        ]
                        if any(pattern in RECOGNIZED_PATTERNS for pattern in recognized_values):
                            expected_body_leader_gap = False
                            break
                if not expected_body_leader_gap:
                    table_diagnostics.append(
                        DiagnosticItem(
                            severity="warning",
                            code="header_body_split_rule_disagreement",
                            message=(
                                "Horizontal-rule and value-region header/body splits disagree "
                                f"(hline body_start={hline_body_start}, "
                                f"value-anchor body_start={value_anchor_body_start}, "
                                f"selected body_start={selected_body_start})."
                            ),
                        )
                    )

    role_by_col = {role.col_idx: role for role in column_roles}
    for col_idx in range(1, table.n_cols):
        values = []
        for row_view in table.row_views:
            if col_idx < len(row_view.raw_cells):
                values.append(clean_text(row_view.raw_cells[col_idx]))
            else:
                values.append("")
        nonempty_values = [value for value in values if value]
        if not nonempty_values:
            column_diagnostics.append(
                DiagnosticItem(
                    severity="warning",
                    code="mostly_empty_column",
                    message="Column is entirely empty across body rows.",
                    col_idx=col_idx,
                )
            )
            continue

        empty_fraction = 1.0 - (len(nonempty_values) / len(values)) if values else 0.0
        if empty_fraction > 0.85:
            column_diagnostics.append(
                DiagnosticItem(
                    severity="warning",
                    code="mostly_empty_column",
                    message=f"Column is mostly empty ({empty_fraction:.2f}).",
                    col_idx=col_idx,
                )
            )

        patterns = [detect_value_pattern(value) for value in nonempty_values]
        recognized_fraction_col = sum(pattern.pattern in RECOGNIZED_PATTERNS for pattern in patterns) / len(patterns)
        role = role_by_col.get(col_idx)
        if role is not None and role.role == "p_value":
            p_value_fraction = sum(pattern.pattern == "p_value" for pattern in patterns) / len(patterns)
            if p_value_fraction < 0.30:
                column_diagnostics.append(
                    DiagnosticItem(
                        severity="error",
                        code="invalid_p_value_column",
                        message="Column is labeled as p_value but rarely contains p-value-like entries.",
                        col_idx=col_idx,
                    )
                )
            elif p_value_fraction < 0.60:
                column_diagnostics.append(
                    DiagnosticItem(
                        severity="warning",
                        code="weak_p_value_column",
                        message="Column is labeled as p_value but many entries do not resemble p-values.",
                        col_idx=col_idx,
                    )
                )
        elif role is not None and role.role in {"overall", "group", "comparison_group"} and recognized_fraction_col < 0.40:
            column_diagnostics.append(
                DiagnosticItem(
                    severity="warning" if recognized_fraction_col >= 0.20 else "error",
                    code="non_numeric_statistical_column",
                    message="Column inferred as numeric/statistical contains too much unrecognized text.",
                    col_idx=col_idx,
                )
            )

    combined_warning_count = sum(item.severity in {"warning", "error"} for item in row_diagnostics + column_diagnostics)
    if combined_warning_count >= 6:
        table_diagnostics.append(
            DiagnosticItem(
                severity="error" if combined_warning_count >= 10 else "warning",
                code="multiple_quality_warnings",
                message="Multiple row and column diagnostics indicate broad parse-quality issues.",
            )
        )

    summary = ParseQualitySummary(
        total_body_rows=total_body_rows,
        unknown_row_count=unknown_row_count,
        unknown_row_fraction=unknown_fraction,
        variable_block_count=len(variable_blocks),
        recognized_value_pattern_fraction=recognized_fraction,
        row_warning_count=sum(item.severity in {"warning", "error"} for item in row_diagnostics),
        column_warning_count=sum(item.severity in {"warning", "error"} for item in column_diagnostics),
    )
    resolved_source = source_identifier or (
        extracted_table.source_pdf if extracted_table is not None else None
    )
    return ParseQualityReport(
        report_timestamp=_utc_timestamp(),
        source_identifier=resolved_source,
        table_id=table.table_id,
        summary=summary,
        table_diagnostics=table_diagnostics,
        row_diagnostics=row_diagnostics,
        column_diagnostics=column_diagnostics,
    )
