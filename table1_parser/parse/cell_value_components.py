"""Parse source-grid cell values into typed components."""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Literal

from table1_parser.heuristics.value_pattern_detector import detect_value_pattern
from table1_parser.schemas import NormalizedTable, ParsedCellValue, ValueComponent
from table1_parser.text_cleaning import clean_text


INTEGER_TOKEN = r"(?:\d{1,3}(?:,\d{3})*|\d+)"
DECIMAL_TOKEN = r"-?\d+(?:\.\d+)?"
UNSIGNED_DECIMAL_TOKEN = r"\d+(?:\.\d+)?"
FOOTNOTE_SUFFIX_TOKEN = r"(?:\s*(?:[*†‡§¶#{}|]+|[a-z]))*"
COUNT_PCT_COMPONENT_PATTERN = re.compile(
    rf"^(?P<count>{INTEGER_TOKEN})\s*\(\s*(?P<percent>{UNSIGNED_DECIMAL_TOKEN})(?P<percent_symbol>\s*%)?\s*\){FOOTNOTE_SUFFIX_TOKEN}$",
    re.IGNORECASE,
)
INTEGER_COMPONENT_PATTERN = re.compile(rf"^(?P<count>{INTEGER_TOKEN}){FOOTNOTE_SUFFIX_TOKEN}$", re.IGNORECASE)
DECIMAL_COMPONENT_PATTERN = re.compile(rf"^(?P<estimate>{DECIMAL_TOKEN}){FOOTNOTE_SUFFIX_TOKEN}$", re.IGNORECASE)
PARENTHESIZED_UNCERTAINTY_PATTERN = re.compile(
    rf"^(?P<primary>{DECIMAL_TOKEN})\s*\(\s*(?P<uncertainty>{DECIMAL_TOKEN})\s*\){FOOTNOTE_SUFFIX_TOKEN}$",
    re.IGNORECASE,
)
PLUSMINUS_UNCERTAINTY_PATTERN = re.compile(
    rf"^(?P<primary>{DECIMAL_TOKEN})\s*(?:±|\+/-)\s*(?P<uncertainty>{DECIMAL_TOKEN}){FOOTNOTE_SUFFIX_TOKEN}$",
    re.IGNORECASE,
)
SPACED_SIX_UNCERTAINTY_PATTERN = re.compile(
    rf"^(?P<primary>{DECIMAL_TOKEN})\s+6\s+(?P<uncertainty>{DECIMAL_TOKEN}){FOOTNOTE_SUFFIX_TOKEN}$",
    re.IGNORECASE,
)
DASH_UNCERTAINTY_PATTERN = re.compile(
    rf"^(?P<primary>{DECIMAL_TOKEN})\s+-\s+(?P<uncertainty>{DECIMAL_TOKEN}){FOOTNOTE_SUFFIX_TOKEN}$",
    re.IGNORECASE,
)
MEDIAN_IQR_COMPONENT_PATTERN = re.compile(
    rf"^(?P<median>{DECIMAL_TOKEN})\s*[\(\[]\s*(?P<q1>{DECIMAL_TOKEN})\s*,\s*(?P<q3>{DECIMAL_TOKEN})\s*[\)\]]{FOOTNOTE_SUFFIX_TOKEN}$",
    re.IGNORECASE,
)
P_VALUE_COMPONENT_PATTERN = re.compile(
    rf"^(?:p\s*[=:]?\s*)?(?P<relation><=|>=|<|>)?\s*(?P<value>0?\.\d+|\.\d+|1\.0+){FOOTNOTE_SUFFIX_TOKEN}$",
    re.IGNORECASE,
)
MISSING_VALUES = {
    "-",
    "--",
    "na",
    "n/a",
    "n.a.",
    "not available",
    "not estimable",
    "not estimated",
}
UncertaintyPrimaryKind = Literal["mean", "estimate"]
UncertaintyKind = Literal["sd", "se", "unknown"]


@dataclass(slots=True)
class CellValueComponentParse:
    """Component parse result for one raw source cell without grid coordinates."""

    raw_value: str
    parse_pattern: str
    components: list[ValueComponent]
    confidence: float
    notes: list[str]


def parse_cell_value_components(raw_value: str, summary_style_hint: str | None = None) -> CellValueComponentParse:
    """Parse one raw source cell into typed value components."""
    cleaned = clean_text(raw_value)
    lowered = cleaned.lower()
    detected = detect_value_pattern(raw_value)

    if lowered in MISSING_VALUES:
        return CellValueComponentParse(
            raw_value=raw_value,
            parse_pattern="missing",
            components=[ValueComponent(kind="missing", value=None, raw_fragment=cleaned, confidence=0.95)],
            confidence=0.95,
            notes=[],
        )

    match = COUNT_PCT_COMPONENT_PATTERN.fullmatch(cleaned)
    if match is not None:
        return CellValueComponentParse(
            raw_value=raw_value,
            parse_pattern="count_parenthesized_percent",
            components=[
                ValueComponent(
                    kind="count",
                    value=float(int(match.group("count").replace(",", ""))),
                    raw_fragment=match.group("count"),
                    relation="=",
                    confidence=0.96,
                ),
                ValueComponent(
                    kind="percent",
                    value=float(match.group("percent")),
                    raw_fragment=f"{match.group('percent')}{match.group('percent_symbol') or ''}",
                    relation="=",
                    confidence=0.96,
                ),
            ],
            confidence=max(detected.confidence, 0.95),
            notes=[],
        )

    match = MEDIAN_IQR_COMPONENT_PATTERN.fullmatch(cleaned)
    if match is not None:
        return CellValueComponentParse(
            raw_value=raw_value,
            parse_pattern="median_iqr",
            components=[
                ValueComponent(kind="median", value=float(match.group("median")), raw_fragment=match.group("median"), relation="=", confidence=0.94),
                ValueComponent(kind="q1", value=float(match.group("q1")), raw_fragment=match.group("q1"), relation="=", confidence=0.94),
                ValueComponent(kind="q3", value=float(match.group("q3")), raw_fragment=match.group("q3"), relation="=", confidence=0.94),
            ],
            confidence=max(detected.confidence, 0.94),
            notes=[],
        )

    uncertainty_parse = _parse_uncertainty_components(cleaned, raw_value, summary_style_hint, detected.confidence)
    if uncertainty_parse is not None:
        return uncertainty_parse

    match = P_VALUE_COMPONENT_PATTERN.fullmatch(lowered)
    if match is not None and (detected.pattern == "p_value" or lowered.startswith("p") or match.group("relation") is not None):
        raw_fragment = cleaned
        relation = match.group("relation") or "="
        confidence = detected.confidence if detected.pattern == "p_value" else 0.9
        return CellValueComponentParse(
            raw_value=raw_value,
            parse_pattern="p_value",
            components=[
                ValueComponent(
                    kind="p_value",
                    value=float(match.group("value")),
                    raw_fragment=raw_fragment,
                    relation=relation,
                    confidence=confidence,
                )
            ],
            confidence=confidence,
            notes=[] if lowered.startswith("p") or relation != "=" else ["p_value_shape_without_column_context"],
        )

    match = INTEGER_COMPONENT_PATTERN.fullmatch(cleaned)
    if match is not None:
        return CellValueComponentParse(
            raw_value=raw_value,
            parse_pattern="integer",
            components=[
                ValueComponent(
                    kind="count",
                    value=float(int(match.group("count").replace(",", ""))),
                    raw_fragment=match.group("count"),
                    relation="=",
                    confidence=0.9,
                )
            ],
            confidence=max(detected.confidence, 0.9),
            notes=[],
        )

    match = DECIMAL_COMPONENT_PATTERN.fullmatch(cleaned)
    if match is not None:
        return CellValueComponentParse(
            raw_value=raw_value,
            parse_pattern="numeric_scalar",
            components=[
                ValueComponent(
                    kind="estimate",
                    value=float(match.group("estimate")),
                    raw_fragment=match.group("estimate"),
                    relation="=",
                    confidence=0.75,
                    notes=["numeric_scalar_without_context"],
                )
            ],
            confidence=0.75,
            notes=["numeric_scalar_without_context"],
        )

    return CellValueComponentParse(
        raw_value=raw_value,
        parse_pattern="free_text",
        components=[ValueComponent(kind="text", value=raw_value, raw_fragment=raw_value, confidence=0.4)],
        confidence=0.4,
        notes=[],
    )


def build_parsed_cell_values(
    tables: list[NormalizedTable],
    value_column_indices_by_table_id: Mapping[str, Collection[int]] | None = None,
) -> list[ParsedCellValue]:
    """Build source-indexed parsed cell values for normalized table body cells."""
    parsed_values: list[ParsedCellValue] = []
    for table_index, table in enumerate(tables):
        body_rows = set(table.body_rows)
        allowed_columns = (
            set(value_column_indices_by_table_id[table.table_id])
            if value_column_indices_by_table_id is not None and table.table_id in value_column_indices_by_table_id
            else None
        )
        for row_view in table.row_views:
            if body_rows and row_view.row_idx not in body_rows:
                continue
            for col_idx, raw_value in enumerate(row_view.raw_cells):
                if allowed_columns is not None and col_idx not in allowed_columns:
                    continue
                if not clean_text(raw_value):
                    continue
                parsed = parse_cell_value_components(raw_value)
                parsed_values.append(
                    ParsedCellValue(
                        source_table_index=table_index,
                        source_table_id=table.table_id,
                        row_idx=row_view.row_idx,
                        col_idx=col_idx,
                        raw_value=raw_value,
                        parse_pattern=parsed.parse_pattern,
                        components=parsed.components,
                        confidence=parsed.confidence,
                        notes=parsed.notes,
                    )
                )
    return parsed_values


def parsed_cell_values_to_payload(values: list[ParsedCellValue]) -> list[dict[str, object]]:
    """Serialize parsed cell value component records as JSON-friendly dictionaries."""
    return [value.model_dump(mode="json") for value in values]


def _parse_uncertainty_components(
    cleaned_value: str,
    raw_value: str,
    summary_style_hint: str | None,
    detected_confidence: float,
) -> CellValueComponentParse | None:
    pattern_matches = (
        ("numeric_parenthesized_uncertainty", PARENTHESIZED_UNCERTAINTY_PATTERN.fullmatch(cleaned_value)),
        ("numeric_plusminus_uncertainty", PLUSMINUS_UNCERTAINTY_PATTERN.fullmatch(cleaned_value)),
        ("numeric_spaced_six_uncertainty", SPACED_SIX_UNCERTAINTY_PATTERN.fullmatch(cleaned_value)),
        ("numeric_dash_uncertainty", DASH_UNCERTAINTY_PATTERN.fullmatch(cleaned_value)),
    )
    for parse_pattern, match in pattern_matches:
        if match is None:
            continue
        normalized_hint = clean_text(summary_style_hint or "").lower().replace("-", "_")
        if normalized_hint in {"mean_sd", "mean_s_d", "mean_standard_deviation"}:
            primary_kind: UncertaintyPrimaryKind = "mean"
            uncertainty_kind: UncertaintyKind = "sd"
            notes: list[str] = []
        elif normalized_hint in {"estimate_se", "mean_se", "estimate_standard_error", "mean_standard_error"}:
            primary_kind = "estimate"
            uncertainty_kind = "se"
            notes = []
        else:
            primary_kind = "estimate"
            uncertainty_kind = "unknown"
            notes = ["ambiguous_uncertainty_component"]
        confidence = max(detected_confidence, 0.88)
        return CellValueComponentParse(
            raw_value=raw_value,
            parse_pattern=parse_pattern,
            components=[
                ValueComponent(
                    kind=primary_kind,
                    value=float(match.group("primary")),
                    raw_fragment=match.group("primary"),
                    relation="=",
                    confidence=confidence,
                ),
                ValueComponent(
                    kind=uncertainty_kind,
                    value=float(match.group("uncertainty")),
                    raw_fragment=match.group("uncertainty"),
                    relation="=",
                    confidence=confidence if uncertainty_kind != "unknown" else min(confidence, 0.75),
                    notes=notes,
                ),
            ],
            confidence=confidence,
            notes=notes,
        )
    return None
