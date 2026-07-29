"""Deterministic paper-level table taxonomy predictions."""

from __future__ import annotations

import re
from collections.abc import Sequence

from table1_parser.diagnostics import ParseQualityReport
from table1_parser.extract.table_detector import TABLE_IDENTIFIER_PATTERN
from table1_parser.heuristics.value_pattern_detector import detect_value_pattern
from table1_parser.schemas import (
    ExtractedTable,
    NormalizedTable,
    PaperTableInventory,
    PaperTableRecord,
    ParsedTable,
    TableDefinition,
    TableProcessingStatus,
    TableProfile,
)
from table1_parser.text_cleaning import clean_text


TABLE_NUMBER_PATTERN = re.compile(
    rf"\btable\s+(?P<table_number>{TABLE_IDENTIFIER_PATTERN.pattern})\b",
    re.IGNORECASE,
)
DESCRIPTIVE_TITLE_PATTERN = re.compile(
    r"\b(?:baseline|characteristics?|demographics?|study population|participants?|sample|cohort)\b",
    re.IGNORECASE,
)
EFFECT_PHRASE_PATTERN = re.compile(
    r"\b(?:odds ratio|hazard ratio|risk ratio|relative risk|prevalence ratio|rate ratio|"
    r"beta|coefficient|coef\.?|estimate|effect size|mean difference)\b",
    re.IGNORECASE,
)
EFFECT_ABBREVIATION_PATTERN = re.compile(r"\b(?:OR|HR|RR|PR)\b")
CI_HEADER_PATTERN = re.compile(r"\b(?:95\s*%\s*CI|CI|confidence interval|lower|upper)\b", re.IGNORECASE)
MODEL_PATTERN = re.compile(r"\b(?:adjusted|unadjusted|model\s*[0-9]+|regression|multivariable)\b", re.IGNORECASE)
ANALYSIS_LIKE_TITLE_PATTERN = re.compile(r"\b(?:regression|mediation|ROC|AUC)\b", re.IGNORECASE)
GENERAL_TITLE_PATTERN = re.compile(
    r"(?:\bcomparison of indicators\b|\b(?:definition|coding|questionnaire|scoring|inclusion|exclusion|assay|parameter|"
    r"criteria|algorithm|classification|cut[- ]?off|variable description|recommendations?)\b)",
    re.IGNORECASE,
)
INLINE_INTERVAL_PATTERN = re.compile(
    r"^-?\d+(?:\.\d+)?\s*[\(\[]\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*[\)\]]$"
)
PLAIN_NUMERIC_VALUE_PATTERN = re.compile(r"^(?:[<>]=?\s*)?-?\d+(?:,\d{3})*(?:\.\d+)?%?$")
THRESHOLD_OR_STAT_HEADER_PATTERN = re.compile(
    r"(?:[‡<>]=?\s*\d|\b(?:severity|extent|prevalence|weighted|mean|median|SE|standard error|%)\b)",
    re.IGNORECASE,
)


def build_paper_table_inventory(
    paper_id: str,
    extracted_tables: Sequence[ExtractedTable],
    normalized_tables: Sequence[NormalizedTable],
    table_profiles: Sequence[TableProfile],
    table_definitions: Sequence[TableDefinition],
    parsed_tables: Sequence[ParsedTable],
    parse_quality_reports: Sequence[ParseQualityReport],
    table_processing_statuses: Sequence[TableProcessingStatus],
) -> PaperTableInventory:
    """Build a compact deterministic taxonomy prediction for each table-like object."""
    records: list[PaperTableRecord] = []
    table_count = max(
        len(extracted_tables),
        len(normalized_tables),
        len(table_profiles),
        len(table_definitions),
        len(parsed_tables),
        len(parse_quality_reports),
        len(table_processing_statuses),
    )

    for table_position in range(table_count):
        extracted = extracted_tables[table_position] if table_position < len(extracted_tables) else None
        normalized = normalized_tables[table_position] if table_position < len(normalized_tables) else None
        profile = table_profiles[table_position] if table_position < len(table_profiles) else None
        definition = table_definitions[table_position] if table_position < len(table_definitions) else None
        parsed = parsed_tables[table_position] if table_position < len(parsed_tables) else None
        quality = parse_quality_reports[table_position] if table_position < len(parse_quality_reports) else None
        status = table_processing_statuses[table_position] if table_position < len(table_processing_statuses) else None
        table_id = (
            getattr(definition, "table_id", None)
            or getattr(normalized, "table_id", None)
            or getattr(parsed, "table_id", None)
            or getattr(extracted, "table_id", None)
            or f"table_{table_position}"
        )
        title = (
            getattr(definition, "title", None)
            or getattr(normalized, "title", None)
            or getattr(parsed, "title", None)
            or getattr(extracted, "title", None)
        )
        caption = (
            getattr(definition, "caption", None)
            or getattr(normalized, "caption", None)
            or getattr(parsed, "caption", None)
            or getattr(extracted, "caption", None)
        )
        normalized_metadata = normalized.metadata if normalized is not None and isinstance(normalized.metadata, dict) else {}
        extracted_metadata = extracted.metadata if extracted is not None and isinstance(extracted.metadata, dict) else {}
        normalized_signals = normalized_metadata.get("signals", {}) if isinstance(normalized_metadata.get("signals", {}), dict) else {}
        extracted_signals = extracted_metadata.get("signals", {}) if isinstance(extracted_metadata.get("signals", {}), dict) else {}
        table_number = next(
            (
                value
                for value in (
                    normalized_metadata.get("table_number"),
                    extracted_metadata.get("table_number"),
                    normalized_signals.get("caption_table_number"),
                    extracted_signals.get("caption_table_number"),
                )
                if isinstance(value, str)
                and TABLE_IDENTIFIER_PATTERN.fullmatch(value) is not None
            ),
            None,
        )
        if table_number is None:
            text_match = TABLE_NUMBER_PATTERN.search(" ".join(part for part in [title or "", caption or ""] if part))
            table_number = (
                text_match.group("table_number")
                if text_match is not None
                else None
            )
        continuation_of_table_number = next(
            (
                value
                for value in (
                    normalized_metadata.get("continuation_of_table_number"),
                    extracted_metadata.get("continuation_of_table_number"),
                )
                if isinstance(value, str)
                and TABLE_IDENTIFIER_PATTERN.fullmatch(value) is not None
            ),
            None,
        )

        cleaned_rows = normalized_metadata.get("cleaned_rows") if normalized_metadata else []
        if not isinstance(cleaned_rows, list):
            cleaned_rows = []
        header_rows = (
            [
                cleaned_rows[row_idx]
                for row_idx in normalized.header_rows
                if row_idx < len(cleaned_rows) and isinstance(cleaned_rows[row_idx], list)
            ]
            if normalized is not None
            else []
        )
        header_text = clean_text(
            " ".join(str(cell) for row in header_rows for cell in row if clean_text(str(cell)))
        )
        title_caption_text = clean_text(" ".join(part for part in [title or "", caption or ""] if part))
        body_text = clean_text(
            " ".join(
                str(cell)
                for row in cleaned_rows
                for cell in (row if isinstance(row, list) else [])
                if clean_text(str(cell))
            )
        )
        pattern_counts: dict[str, int] = {}
        inline_interval_count = 0
        populated_value_count = 0
        plain_numeric_value_count = 0
        dense_numeric_body_row_count = 0
        if normalized is not None:
            for row_view in normalized.row_views:
                populated_trailing_values = 0
                plain_numeric_trailing_values = 0
                for value in row_view.raw_cells[1:]:
                    cleaned_value = clean_text(value)
                    if not cleaned_value:
                        continue
                    populated_value_count += 1
                    populated_trailing_values += 1
                    if PLAIN_NUMERIC_VALUE_PATTERN.fullmatch(cleaned_value):
                        plain_numeric_value_count += 1
                        plain_numeric_trailing_values += 1
                    detected = detect_value_pattern(cleaned_value).pattern
                    pattern_counts[detected] = pattern_counts.get(detected, 0) + 1
                    if INLINE_INTERVAL_PATTERN.fullmatch(cleaned_value):
                        inline_interval_count += 1
                if populated_trailing_values >= 4 and plain_numeric_trailing_values >= max(
                    4,
                    int(populated_trailing_values * 0.75),
                ):
                    dense_numeric_body_row_count += 1
        descriptive_value_count = sum(pattern_counts.get(name, 0) for name in ("count_pct", "mean_sd", "median_iqr", "n_only"))
        count_value_count = pattern_counts.get("count_pct", 0) + pattern_counts.get("n_only", 0)
        descriptive_fraction = descriptive_value_count / populated_value_count if populated_value_count else 0.0
        count_fraction = count_value_count / populated_value_count if populated_value_count else 0.0
        plain_numeric_fraction = plain_numeric_value_count / populated_value_count if populated_value_count else 0.0
        data_matrix_layout_signal = (
            normalized is not None
            and normalized.n_cols >= 5
            and len(normalized.header_rows) >= 1
            and len(normalized.body_rows) >= 3
            and populated_value_count >= max(8, len(normalized.body_rows))
        )

        variable_count = len(definition.variables) if definition is not None else 0
        columns = definition.column_definition.columns if definition is not None else []
        usable_column_count = sum(column.inferred_role != "unknown" for column in columns)
        effect_header_signal = bool(EFFECT_PHRASE_PATTERN.search(header_text) or EFFECT_ABBREVIATION_PATTERN.search(header_text))
        ci_header_signal = bool(CI_HEADER_PATTERN.search(header_text))
        threshold_or_stat_header_signal = bool(THRESHOLD_OR_STAT_HEADER_PATTERN.search(header_text))
        model_signal = bool(MODEL_PATTERN.search(" ".join([title_caption_text, header_text])))
        p_value_column_signal = any(column.inferred_role == "p_value" for column in columns)
        quality_error_codes = {
            diagnostic.code
            for diagnostic in (quality.table_diagnostics if quality is not None else [])
            if diagnostic.severity == "error"
        }
        quality_failure_signal = bool(
            {
                "weak_variable_structure",
                "unknown_row_fraction_likely_failure",
            }
            & quality_error_codes
        )
        quality_warning_count = (
            quality.summary.row_warning_count + quality.summary.column_warning_count
            if quality is not None
            else 0
        )
        unknown_row_fraction = quality.summary.unknown_row_fraction if quality is not None else 0.0
        recognized_value_fraction = quality.summary.recognized_value_pattern_fraction if quality is not None else 0.0
        has_table_signal = bool(table_number or title or caption)

        category_scores: dict[str, tuple[float, list[str]]] = {
            "non_table_artifact": (0.0, []),
            "analysis_outputs": (0.0, []),
            "demographic_description": (0.0, []),
            "data_presentation": (0.0, []),
            "general": (0.0, []),
            "unknown": (0.35, ["real_table_with_insufficient_category_evidence"] if has_table_signal else []),
        }

        non_table_score, non_table_evidence = category_scores["non_table_artifact"]
        explicit_non_table_status = (
            status is not None
            and status.failure_reason == "non_table_layout_candidate"
            and not data_matrix_layout_signal
        )
        if explicit_non_table_status:
            non_table_score += 0.85
            non_table_evidence.append("processing_status_non_table_layout_candidate")
        if not has_table_signal:
            non_table_score += 0.15
            non_table_evidence.append("no_detected_table_number_title_or_caption")
        if (
            (explicit_non_table_status or not has_table_signal)
            and profile is not None
            and profile.table_family == "unknown"
            and not data_matrix_layout_signal
        ):
            non_table_score += 0.10
            non_table_evidence.append("table_family_unknown")
        if (
            (explicit_non_table_status or not has_table_signal)
            and unknown_row_fraction >= 0.70
            and not data_matrix_layout_signal
        ):
            non_table_score += 0.20
            non_table_evidence.append("very_high_unknown_row_fraction")
        if (
            (explicit_non_table_status or not has_table_signal)
            and recognized_value_fraction < 0.25
            and populated_value_count >= 6
            and not data_matrix_layout_signal
        ):
            non_table_score += 0.15
            non_table_evidence.append("low_value_pattern_recognition")
        if (
            (explicit_non_table_status or not has_table_signal)
            and quality_failure_signal
            and not data_matrix_layout_signal
        ):
            non_table_score += 0.15
            non_table_evidence.append("parse_quality_table_error")
        category_scores["non_table_artifact"] = (min(non_table_score, 0.98), non_table_evidence)

        analysis_score, analysis_evidence = category_scores["analysis_outputs"]
        if effect_header_signal:
            analysis_score += 0.55
            analysis_evidence.append("effect_or_estimate_column_header")
        if ci_header_signal and effect_header_signal:
            analysis_score += 0.20
            analysis_evidence.append("confidence_interval_column_header")
        if inline_interval_count >= 2 and effect_header_signal:
            analysis_score += 0.15
            analysis_evidence.append("estimate_interval_values_under_effect_columns")
        if p_value_column_signal and effect_header_signal:
            analysis_score += 0.05
            analysis_evidence.append("p_value_column_supports_effect_columns")
        if model_signal and effect_header_signal:
            analysis_score += 0.05
            analysis_evidence.append("model_or_adjustment_label_supports_effect_columns")
        if profile is not None and profile.table_family == "estimate_results" and effect_header_signal:
            analysis_score += 0.15
            analysis_evidence.append("estimate_results_table_family_with_effect_columns")
        category_scores["analysis_outputs"] = (min(analysis_score, 0.98), analysis_evidence)

        demographic_score, demographic_evidence = category_scores["demographic_description"]
        if profile is not None and profile.table_family == "descriptive_characteristics":
            demographic_score += 0.25
            demographic_evidence.append("descriptive_characteristics_table_family")
        if DESCRIPTIVE_TITLE_PATTERN.search(title_caption_text):
            demographic_score += 0.25
            demographic_evidence.append("caption_or_title_mentions_population_description")
        if descriptive_fraction >= 0.45 and descriptive_value_count >= 4:
            demographic_score += 0.20
            demographic_evidence.append("mostly_descriptive_summary_values")
        if variable_count >= 3:
            demographic_score += 0.15
            demographic_evidence.append("multiple_row_variables")
        if usable_column_count >= 2 and any(column.inferred_role in {"overall", "group", "comparison_group"} for column in columns):
            demographic_score += 0.10
            demographic_evidence.append("coherent_overall_or_group_columns")
        if table_number == "1" and status is not None and status.status != "failed":
            demographic_score += 0.05
            demographic_evidence.append("published_table_1_with_successful_parse")
        category_scores["demographic_description"] = (min(demographic_score, 0.98), demographic_evidence)

        data_score, data_evidence = category_scores["data_presentation"]
        if count_fraction >= 0.65 and count_value_count >= 6:
            data_score += 0.35
            data_evidence.append("mostly_count_or_frequency_values")
        if (
            normalized is not None
            and normalized.n_cols >= 5
            and plain_numeric_fraction >= 0.70
            and plain_numeric_value_count >= 12
            and dense_numeric_body_row_count >= 3
        ):
            data_score += 0.40
            data_evidence.append("mostly_numeric_matrix_values")
        if normalized is not None and normalized.n_cols >= 5 and threshold_or_stat_header_signal:
            data_score += 0.15
            data_evidence.append("threshold_or_statistic_column_headers")
        if normalized is not None and normalized.n_cols >= 3 and len(normalized.body_rows) >= 3 and variable_count <= 2:
            data_score += 0.25
            data_evidence.append("matrix_like_rows_and_columns")
        if data_matrix_layout_signal:
            data_score += 0.20
            data_evidence.append("wide_matrix_like_layout")
        if pattern_counts.get("mean_sd", 0) + pattern_counts.get("median_iqr", 0) == 0 and count_value_count >= 4:
            data_score += 0.10
            data_evidence.append("few_or_no_continuous_summary_rows")
        if not effect_header_signal and not ci_header_signal:
            data_score += 0.10
            data_evidence.append("no_effect_or_confidence_interval_columns")
        category_scores["data_presentation"] = (min(data_score, 0.98), data_evidence)

        general_score, general_evidence = category_scores["general"]
        if GENERAL_TITLE_PATTERN.search(" ".join([title_caption_text, body_text[:2000]])):
            general_score += 0.50
            general_evidence.append("definition_coding_scoring_or_reference_table_text")
        if has_table_signal and normalized is not None and normalized.n_rows >= 2 and normalized.n_cols >= 2:
            general_score += 0.20
            general_evidence.append("coherent_real_table_shape")
        if unknown_row_fraction < 0.50 and quality_warning_count <= 4:
            general_score += 0.10
            general_evidence.append("not_a_parse_quality_failure")
        category_scores["general"] = (min(general_score, 0.98), general_evidence)

        unknown_score, unknown_evidence = category_scores["unknown"]
        if ANALYSIS_LIKE_TITLE_PATTERN.search(title_caption_text) and not effect_header_signal:
            unknown_score += 0.50
            unknown_evidence.append("analysis_like_title_without_effect_or_estimate_columns")
        category_scores["unknown"] = (min(unknown_score, 0.85), unknown_evidence)

        winning_category, (winning_score, winning_evidence) = max(
            category_scores.items(),
            key=lambda item: (item[1][0], item[0] != "unknown"),
        )
        records.append(
            PaperTableRecord(
                table_id=str(table_id),
                table_number=table_number,
                title=title,
                caption=caption,
                table_category=winning_category,  # type: ignore[arg-type]
                category_confidence=round(winning_score, 4),
                category_evidence=winning_evidence or ["no_strong_category_evidence"],
                continuation_of_table_number=continuation_of_table_number,
                table_family=profile.table_family if profile is not None else None,
                processing_status=status.status if status is not None else None,
                failure_reason=status.failure_reason if status is not None else None,
            )
        )

    return PaperTableInventory(paper_id=paper_id, tables=records)


def paper_table_inventory_to_payload(inventory: PaperTableInventory) -> dict[str, object]:
    """Serialize a paper table inventory as a JSON-friendly dictionary."""
    return inventory.model_dump(mode="json")
