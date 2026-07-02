"""Deterministic routing of normalized tables into semantic families."""

from __future__ import annotations

import re

from table1_parser.heuristics.column_role_detector import detect_column_roles
from table1_parser.heuristics.value_pattern_detector import detect_value_pattern
from table1_parser.heuristics.variable_grouper import group_variable_blocks
from table1_parser.schemas import NormalizedTable, TableProfile
from table1_parser.text_cleaning import clean_text
from table1_parser.validation.table_profile import validate_table_profile


DESCRIPTIVE_TEXT_PATTERN = re.compile(
    r"\b(?:baseline|characteristics?|clinical characteristics|demographic)\b",
    re.IGNORECASE,
)
ESTIMATE_TEXT_PATTERN = re.compile(
    r"\b(?:hazard ratio|odds ratio|relative risk|risk ratio|association|regression|multivariable|cox|logistic|linear)\b",
    re.IGNORECASE,
)
MODEL_HEADER_PATTERN = re.compile(r"\b(?:adjusted|unadjusted|model\s*\d+)\b", re.IGNORECASE)
ESTIMATE_HEADER_PATTERN = re.compile(
    r"\b(?:hazard ratio|odds ratio|relative risk|risk ratio|95%\s*ci|confidence interval|hr\b|or\b|rr\b)\b",
    re.IGNORECASE,
)
INLINE_INTERVAL_PATTERN = re.compile(
    r"^-?\d+(?:\.\d+)?\s*[\(\[]\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*[\)\]]$"
)
ESTIMATE_CI_RANGE_PATTERN = re.compile(
    r"^-?\d+(?:\.\d+)?\s*,?\s*[\(\[]\s*-?\d+(?:\.\d+)?\s*(?:,|-)\s*-?\d+(?:\.\d+)?\s*[\)\]]"
    r"\s*(?:[*†‡§¶#{}|]+|[a-z])*$",
    re.IGNORECASE,
)


def build_table_profile(table: NormalizedTable) -> TableProfile:
    """Classify one normalized table into a supported semantic family."""
    evidence: list[str] = []
    descriptive_score = 0
    estimate_score = 0

    cleaned_rows = table.metadata.get("cleaned_rows", [])
    header_rows = [cleaned_rows[row_idx] for row_idx in table.header_rows if isinstance(cleaned_rows, list) and row_idx < len(cleaned_rows)]
    header_labels: list[str] = []
    for col_idx in range(table.n_cols):
        parts = [row[col_idx] for row in header_rows if col_idx < len(row) and clean_text(str(row[col_idx]))]
        label = clean_text(" ".join(str(part) for part in parts))
        if label:
            header_labels.append(label)
    title_caption_text = clean_text(" ".join(part for part in [table.title or "", table.caption or ""] if part))
    header_text = clean_text(" ".join(header_labels))
    all_context_text = clean_text(" ".join(part for part in [title_caption_text, header_text] if part))

    if DESCRIPTIVE_TEXT_PATTERN.search(title_caption_text):
        descriptive_score += 2
        evidence.append("title_or_caption_mentions_characteristics")
    if ESTIMATE_TEXT_PATTERN.search(all_context_text):
        estimate_score += 2
        evidence.append("title_caption_or_header_mentions_estimate_metric")
    if ESTIMATE_HEADER_PATTERN.search(header_text):
        estimate_score += 1
        evidence.append("header_mentions_estimate_metric_or_ci")
    if MODEL_HEADER_PATTERN.search(header_text):
        estimate_score += 1
        evidence.append("header_mentions_model_or_adjustment")
    effect_ci_header_count = sum(
        1
        for label in header_labels
        if re.search(r"\b(?:OR|HR|RR|PR)\b", label)
        and re.search(r"\b(?:95\s*%\s*CI|CI)\b", label)
    )
    if effect_ci_header_count >= 2:
        estimate_score += 2
        evidence.append("multiple_effect_ci_headers")

    pattern_counts: dict[str, int] = {}
    for row_view in table.row_views:
        for raw_value in row_view.raw_cells[1:]:
            cleaned = clean_text(raw_value)
            if not cleaned:
                continue
            pattern = detect_value_pattern(raw_value).pattern
            pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
    descriptive_pattern_total = sum(
        pattern_counts.get(name, 0) for name in ("count_pct", "mean_sd", "median_iqr", "n_only")
    )
    if descriptive_pattern_total >= 2:
        descriptive_score += 1
        evidence.append("body_contains_descriptive_summary_patterns")
    if pattern_counts.get("count_pct", 0) >= 2:
        descriptive_score += 1
        evidence.append("body_contains_multiple_count_percent_cells")

    variable_blocks = group_variable_blocks(table)
    if any(block.level_row_indices for block in variable_blocks):
        descriptive_score += 2
        evidence.append("row_structure_contains_parent_level_blocks")

    column_roles = detect_column_roles(table)
    if any(role.role in {"overall", "group", "comparison_group"} for role in column_roles):
        descriptive_score += 1
        evidence.append("header_contains_group_or_overall_columns")
    p_value_column_count = sum(role.role == "p_value" for role in column_roles)

    inline_interval_count = 0
    for row_view in table.row_views:
        for raw_value in row_view.raw_cells[1:]:
            if INLINE_INTERVAL_PATTERN.fullmatch(clean_text(raw_value)):
                inline_interval_count += 1
            elif ESTIMATE_CI_RANGE_PATTERN.fullmatch(clean_text(raw_value)):
                inline_interval_count += 1
    if inline_interval_count >= 2:
        estimate_score += 2
        evidence.append("body_contains_multiple_inline_estimate_intervals")

    p_value_like_count = pattern_counts.get("p_value", 0)
    if p_value_column_count >= 1 and p_value_like_count >= 2:
        estimate_score += 1
        evidence.append("p_value_column_matches_p_value_like_cells")

    if estimate_score >= 4 and estimate_score > descriptive_score:
        family = "estimate_results"
    elif descriptive_score >= 3 and descriptive_score >= estimate_score:
        family = "descriptive_characteristics"
    else:
        family = "unknown"
        if not evidence:
            evidence.append("insufficient_family_evidence")

    profile = TableProfile(
        table_id=table.table_id,
        title=table.title,
        caption=table.caption,
        table_family=family,
        family_confidence=(
            min(0.98, round(0.55 + 0.08 * descriptive_score + 0.03 * max(0, descriptive_score - estimate_score), 4))
            if family == "descriptive_characteristics"
            else (
                min(0.98, round(0.55 + 0.08 * estimate_score + 0.03 * max(0, estimate_score - descriptive_score), 4))
                if family == "estimate_results"
                else min(0.75, round(0.35 + 0.05 * max(descriptive_score, estimate_score), 4))
            )
        ),
        evidence=evidence,
        notes=[],
    )
    return validate_table_profile(profile)


def build_table_profiles(tables: list[NormalizedTable]) -> list[TableProfile]:
    """Build deterministic route decisions for a list of normalized tables."""
    return [build_table_profile(table) for table in tables]


def table_profiles_to_payload(profiles: list[TableProfile]) -> list[dict[str, object]]:
    """Serialize table profiles as JSON-friendly dictionaries."""
    return [profile.model_dump(mode="json") for profile in profiles]
