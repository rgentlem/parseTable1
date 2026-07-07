"""Build per-table rescue and failure status records from existing parse artifacts."""

from __future__ import annotations

from collections.abc import Sequence
import re

from table1_parser.heuristics.value_pattern_detector import detect_value_pattern
from table1_parser.schemas import (
    ExtractedTable,
    NormalizedTable,
    ParsedTable,
    ResolvedTableSet,
    SourceFragmentDiagnostic,
    TableDefinition,
    TableProcessingAttempt,
    TableProcessingStatus,
    TableProfile,
)
from table1_parser.text_cleaning import clean_text


ALPHA_PATTERN = re.compile(r"[A-Za-z]")
ALNUM_PATTERN = re.compile(r"[A-Za-z0-9]")


def build_table_processing_statuses(
    extracted_tables: Sequence[ExtractedTable],
    normalized_tables: Sequence[NormalizedTable],
    table_profiles: Sequence[TableProfile],
    table_definitions: Sequence[TableDefinition],
    parsed_tables: Sequence[ParsedTable],
    parse_quality_reports: Sequence[object] | None = None,
    *,
    resolved_table_set: ResolvedTableSet | None = None,
    source_parse_quality_reports: Sequence[object] | None = None,
) -> list[TableProcessingStatus]:
    """Build per-table rescue and failure status records using current pipeline outputs."""
    statuses: list[TableProcessingStatus] = []
    resolved_by_table_id = (
        {resolved_table.table_id: resolved_table for resolved_table in resolved_table_set.resolved_tables}
        if resolved_table_set is not None
        else {}
    )
    source_resolution_by_table_id = (
        {source_table.source_table_id: source_table for source_table in resolved_table_set.source_tables}
        if resolved_table_set is not None
        else {}
    )
    source_quality_by_table_id = {
        str(report.table_id): report
        for report in source_parse_quality_reports or []
        if getattr(report, "table_id", None) is not None
    }
    for table_index, (extracted_table, normalized_table, table_profile, table_definition, parsed_table) in enumerate(zip(
        extracted_tables,
        normalized_tables,
        table_profiles,
        table_definitions,
        parsed_tables,
        strict=True,
    )):
        extracted_rows = [["" for _ in range(extracted_table.n_cols)] for _ in range(extracted_table.n_rows)]
        for cell in extracted_table.cells:
            if cell.row_idx < extracted_table.n_rows and cell.col_idx < extracted_table.n_cols:
                extracted_rows[cell.row_idx][cell.col_idx] = cell.text
        extracted_metadata = extracted_table.metadata if isinstance(extracted_table.metadata, dict) else {}
        extracted_signals = extracted_metadata.get("signals", {})
        quality_report = (
            parse_quality_reports[table_index]
            if parse_quality_reports is not None and table_index < len(parse_quality_reports)
            else None
        )
        resolved_table = resolved_by_table_id.get(table_definition.table_id)
        source_table_ids = (
            list(resolved_table.source_table_ids)
            if resolved_table is not None and resolved_table.source_table_ids
            else [normalized_table.table_id]
        )
        quality_reports_for_status = (
            [
                source_quality_by_table_id[source_table_id]
                for source_table_id in source_table_ids
                if source_table_id in source_quality_by_table_id
            ]
            if source_quality_by_table_id
            else [quality_report] if quality_report is not None else []
        )
        quality_error_codes = {
            str(item.code)
            for report in quality_reports_for_status
            for item in getattr(report, "table_diagnostics", [])
            if getattr(item, "severity", None) == "error"
        }
        source_fragment_diagnostics: list[SourceFragmentDiagnostic] = []
        for source_table_id in source_table_ids:
            source_resolution = source_resolution_by_table_id.get(source_table_id)
            source_report = source_quality_by_table_id.get(source_table_id)
            if source_report is not None:
                for diagnostic_group in (
                    getattr(source_report, "table_diagnostics", []),
                    getattr(source_report, "row_diagnostics", []),
                    getattr(source_report, "column_diagnostics", []),
                ):
                    for diagnostic in diagnostic_group:
                        source_fragment_diagnostics.append(
                            SourceFragmentDiagnostic(
                                source_table_id=source_table_id,
                                source_table_index=(
                                    source_resolution.source_table_index
                                    if source_resolution is not None
                                    else None
                                ),
                                source_role=source_resolution.role if source_resolution is not None else None,
                                stage="parse_quality",
                                code=str(getattr(diagnostic, "code", "")),
                                severity=getattr(diagnostic, "severity", None),
                                row_idx=getattr(diagnostic, "row_idx", None),
                                col_idx=getattr(diagnostic, "col_idx", None),
                            )
                        )
        if resolved_table is not None:
            for decision in resolved_table.column_schema_decisions:
                for diagnostic in decision.diagnostics:
                    source_table_id = (
                        decision.continuation_table_id
                        if decision.continuation_table_id in source_table_ids
                        else decision.base_table_id
                    )
                    source_resolution = source_resolution_by_table_id.get(source_table_id)
                    source_fragment_diagnostics.append(
                        SourceFragmentDiagnostic(
                            source_table_id=source_table_id,
                            source_table_index=(
                                source_resolution.source_table_index
                                if source_resolution is not None
                                else None
                            ),
                            source_role=source_resolution.role if source_resolution is not None else None,
                            stage="resolution",
                            code=diagnostic,
                        )
                    )
        has_table_signal = bool(
            extracted_table.title
            or extracted_table.caption
            or extracted_metadata.get("table_number")
            or (
                isinstance(extracted_signals, dict)
                and (
                    extracted_signals.get("caption_match")
                    or extracted_signals.get("table_1_match")
                    or extracted_signals.get("caption_table_number")
                )
            )
        )
        populated_trailing_cell_count = sum(
            1
            for row_view in normalized_table.row_views
            for raw_value in row_view.raw_cells[1:]
            if str(raw_value).strip()
        )
        matrix_like_layout_candidate = (
            normalized_table.n_cols >= 5
            and len(normalized_table.header_rows) >= 1
            and len(normalized_table.body_rows) >= 3
            and populated_trailing_cell_count >= max(8, len(normalized_table.body_rows))
        )
        text_only_layout_candidate = _is_text_only_layout_candidate(
            normalized_table,
            table_profile=table_profile,
            has_table_signal=has_table_signal,
            variable_count=len(table_definition.variables),
        )
        non_semantic_layout_candidate = (
            not has_table_signal
            and table_profile.table_family == "unknown"
            and not matrix_like_layout_candidate
            and not text_only_layout_candidate
            and bool(
                quality_error_codes.intersection(
                    {
                        "unknown_row_fraction_likely_failure",
                        "low_value_pattern_recognition",
                        "weak_variable_structure",
                        "multiple_quality_warnings",
                    }
                )
            )
        )
        is_descriptive_candidate = (
            table_profile.table_family == "descriptive_characteristics"
            or bool(isinstance(extracted_signals, dict) and extracted_signals.get("table_1_match"))
            or "title_or_caption_mentions_characteristics" in table_profile.evidence
        )
        column_repairs = normalized_table.metadata.get("column_repairs", {})
        extra_wide_value_column_repair = (
            column_repairs.get("extra_wide_value_column") if isinstance(column_repairs, dict) else None
        )
        extra_wide_value_column_repaired = isinstance(extra_wide_value_column_repair, dict)
        stacked_value_cells_unrepaired = any(
            isinstance(cell, str) and cell.count("\n") >= 4
            for row in extracted_rows
            for cell in row[1:]
        ) and not extra_wide_value_column_repaired
        extraction_inadequate = (
            extracted_table.n_rows <= 1
            or (is_descriptive_candidate and extracted_table.n_rows <= 3 and extracted_table.n_cols <= 2)
            or any(isinstance(row[0], str) and row[0].count("\n") >= 4 for row in extracted_rows if row)
            or stacked_value_cells_unrepaired
        )
        text_cleaning_provenance = normalized_table.metadata.get("text_cleaning_provenance", {})
        dropped_leading_cols = int(normalized_table.metadata.get("dropped_leading_cols", 0))
        dropped_trailing_cols = int(normalized_table.metadata.get("dropped_trailing_cols", 0))
        merged_columns = column_repairs.get("merged_columns", []) if isinstance(column_repairs, dict) else []
        dropped_repaired_cols = (
            column_repairs.get("dropped_empty_columns_after_repair", []) if isinstance(column_repairs, dict) else []
        )
        normalization_inadequate = (
            not normalized_table.body_rows
            or (is_descriptive_candidate and len(normalized_table.body_rows) <= 1)
            or normalized_table.n_cols <= 1
        )
        usable_columns = [
            column
            for column in table_definition.column_definition.columns
            if column.inferred_role != "unknown"
        ]
        definition_inadequate = len(table_definition.variables) == 0 or len(usable_columns) == 0
        parsed_inadequate = bool(table_definition.variables) and bool(usable_columns) and len(parsed_table.values) == 0
        attempts = [
            TableProcessingAttempt(
                stage="extraction",
                name="explicit_grid_refinement",
                considered=extracted_metadata.get("layout_source") == "pymupdf4llm_json",
                ran=bool(extracted_metadata.get("explicit_grid_refined_from_words")),
                succeeded=bool(extracted_metadata.get("explicit_grid_refined_from_words")) and not extraction_inadequate,
                note=str(extracted_metadata.get("grid_refinement_source")) if extracted_metadata.get("grid_refinement_source") else None,
            ),
            TableProcessingAttempt(
                stage="extraction",
                name="low_quality_candidate_text_layout_rescue",
                considered=bool(
                    extracted_metadata.get("layout_source") in {"pymupdf4llm_json", "pymupdf_text_positions_rescue"}
                    and isinstance(extracted_signals, dict)
                    and extracted_signals.get("caption_match")
                ),
                ran=extracted_metadata.get("layout_source") == "pymupdf_text_positions_rescue",
                succeeded=extracted_metadata.get("layout_source") == "pymupdf_text_positions_rescue" and not extraction_inadequate,
                note="replacement_candidate_selected" if extracted_metadata.get("layout_source") == "pymupdf_text_positions_rescue" else None,
            ),
            TableProcessingAttempt(
                stage="extraction",
                name="page_text_layout_fallback",
                considered=extracted_metadata.get("layout_source") == "pymupdf_text_positions",
                ran=extracted_metadata.get("layout_source") == "pymupdf_text_positions",
                succeeded=extracted_metadata.get("layout_source") == "pymupdf_text_positions" and not extraction_inadequate,
                note=str(extracted_metadata.get("layout_source")) if extracted_metadata.get("layout_source") == "pymupdf_text_positions" else None,
            ),
            TableProcessingAttempt(
                stage="normalization",
                name="edge_column_trim",
                considered=True,
                ran=bool(dropped_leading_cols or dropped_trailing_cols),
                succeeded=bool(dropped_leading_cols or dropped_trailing_cols),
                note=f"leading={dropped_leading_cols}, trailing={dropped_trailing_cols}" if dropped_leading_cols or dropped_trailing_cols else None,
            ),
            TableProcessingAttempt(
                stage="normalization",
                name="split_value_column_repair",
                considered=True,
                ran=any(int(item.get("merged_row_count", 0)) > 0 for item in merged_columns if isinstance(item, dict)),
                succeeded=any(int(item.get("merged_row_count", 0)) > 0 for item in merged_columns if isinstance(item, dict)),
                note=(
                    f"merged_columns={sum(1 for item in merged_columns if isinstance(item, dict) and int(item.get('merged_row_count', 0)) > 0)}"
                    if any(int(item.get("merged_row_count", 0)) > 0 for item in merged_columns if isinstance(item, dict))
                    else None
                ),
            ),
            TableProcessingAttempt(
                stage="normalization",
                name="extra_wide_value_column_repair",
                considered=True,
                ran=extra_wide_value_column_repaired,
                succeeded=extra_wide_value_column_repaired,
                note=(
                    f"value_columns={int(extra_wide_value_column_repair.get('created_value_columns', 0))}"
                    if extra_wide_value_column_repaired
                    else None
                ),
            ),
            TableProcessingAttempt(
                stage="normalization",
                name="drop_empty_columns_after_repair",
                considered=True,
                ran=bool(dropped_repaired_cols),
                succeeded=bool(dropped_repaired_cols),
                note=f"dropped={len(dropped_repaired_cols)}" if dropped_repaired_cols else None,
            ),
            TableProcessingAttempt(
                stage="normalization",
                name="glyph_repair",
                considered=True,
                ran=bool(isinstance(text_cleaning_provenance, dict) and text_cleaning_provenance.get("cells_with_extractor_glyph_repairs")),
                succeeded=bool(isinstance(text_cleaning_provenance, dict) and text_cleaning_provenance.get("cells_with_extractor_glyph_repairs")),
                note=(
                    f"cells={int(text_cleaning_provenance.get('cells_with_extractor_glyph_repairs', 0))}"
                    if isinstance(text_cleaning_provenance, dict) and text_cleaning_provenance.get("cells_with_extractor_glyph_repairs")
                    else None
                ),
            ),
            TableProcessingAttempt(
                stage="table_definition",
                name="deterministic_definition",
                considered=True,
                ran=True,
                succeeded=not definition_inadequate,
                note=f"variables={len(table_definition.variables)}, usable_columns={len(usable_columns)}",
            ),
            TableProcessingAttempt(
                stage="parsed_table",
                name="deterministic_value_parse",
                considered=True,
                ran=True,
                succeeded=not parsed_inadequate,
                note=f"values={len(parsed_table.values)}",
            ),
        ]
        status = "ok"
        failure_stage = None
        failure_reason = None
        notes: list[str] = []
        if is_descriptive_candidate:
            notes.append("descriptive_table_candidate")
        if isinstance(extracted_signals, dict) and extracted_signals.get("table_1_match"):
            notes.append("table_1_candidate")
        if non_semantic_layout_candidate:
            status = "failed"
            failure_stage = "extraction"
            failure_reason = "non_table_layout_candidate"
            notes.append("non_semantic_table_candidate")
        elif matrix_like_layout_candidate and table_profile.table_family == "unknown":
            notes.append("matrix_like_table_without_supported_semantic_route")
        elif text_only_layout_candidate:
            notes.append("text_only_table_without_supported_semantic_route")
        elif is_descriptive_candidate and extraction_inadequate:
            status = "failed"
            failure_stage = "extraction"
            failure_reason = (
                "collapsed_grid_unrecovered"
                if extracted_table.n_rows <= 1 or (extracted_table.n_rows <= 3 and extracted_table.n_cols <= 2)
                else "insufficient_table_structure_after_extraction"
            )
        elif is_descriptive_candidate and normalization_inadequate:
            status = "failed"
            failure_stage = "normalization"
            failure_reason = (
                "no_body_rows_after_normalization"
                if not normalized_table.body_rows
                else "collapsed_body_after_normalization"
                if len(normalized_table.body_rows) <= 1
                else "no_usable_columns_after_normalization"
            )
        elif is_descriptive_candidate and definition_inadequate:
            status = "failed"
            failure_stage = "table_definition"
            failure_reason = (
                "no_variables_for_descriptive_table"
                if len(table_definition.variables) == 0
                else "no_columns_for_descriptive_table"
                if len(usable_columns) == 0
                else "unresolved_descriptive_structure"
            )
        elif is_descriptive_candidate and parsed_inadequate:
            status = "failed"
            failure_stage = "parsed_table"
            failure_reason = "no_values_after_parse"
        elif any(
            attempt.ran and attempt.succeeded and attempt.name not in {"deterministic_definition", "deterministic_value_parse"}
            for attempt in attempts
        ):
            status = "rescued"
        if failure_reason is not None:
            notes.append(f"parse_failed:{failure_reason}")
        statuses.append(
            TableProcessingStatus(
                table_id=table_definition.table_id,
                source_table_ids=source_table_ids,
                status=status,
                failure_stage=failure_stage,
                failure_reason=failure_reason,
                attempts=attempts,
                source_fragment_diagnostics=source_fragment_diagnostics,
                notes=notes,
            )
        )
    return statuses


def _is_text_only_layout_candidate(
    normalized_table: NormalizedTable,
    *,
    table_profile: TableProfile,
    has_table_signal: bool,
    variable_count: int,
) -> bool:
    """Return whether a real table is text-only and outside current Table 1 semantics."""
    if (
        not has_table_signal
        or table_profile.table_family != "unknown"
        or variable_count > 0
        or normalized_table.n_cols < 2
        or len(normalized_table.body_rows) < 2
    ):
        return False

    populated_cells: list[str] = []
    trailing_populated = 0
    for row_view in normalized_table.row_views:
        for col_idx, raw_value in enumerate(row_view.raw_cells):
            cleaned = clean_text(str(raw_value))
            if not cleaned or not ALNUM_PATTERN.search(cleaned):
                continue
            populated_cells.append(cleaned)
            if col_idx > 0:
                trailing_populated += 1
    if len(populated_cells) < 6 or trailing_populated < max(3, len(normalized_table.body_rows)):
        return False

    text_like_count = sum(
        1
        for cell in populated_cells
        if ALPHA_PATTERN.search(cell) and len(cell) >= 3
    )
    value_like_count = sum(
        1
        for cell in populated_cells
        if detect_value_pattern(cell).pattern != "unknown"
    )
    return (
        text_like_count / len(populated_cells) >= 0.80
        and value_like_count <= max(1, int(len(populated_cells) * 0.15))
    )
