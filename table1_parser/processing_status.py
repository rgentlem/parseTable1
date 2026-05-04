"""Build per-table rescue and failure status records from existing parse artifacts."""

from __future__ import annotations

from collections.abc import Sequence

from table1_parser.schemas import (
    ExtractedTable,
    NormalizedTable,
    ParsedTable,
    TableDefinition,
    TableProcessingAttempt,
    TableProcessingStatus,
    TableProfile,
)


def build_table_processing_statuses(
    extracted_tables: Sequence[ExtractedTable],
    normalized_tables: Sequence[NormalizedTable],
    table_profiles: Sequence[TableProfile],
    table_definitions: Sequence[TableDefinition],
    parsed_tables: Sequence[ParsedTable],
    parse_quality_reports: Sequence[object] | None = None,
) -> list[TableProcessingStatus]:
    """Build per-table rescue and failure status records using current pipeline outputs."""
    statuses: list[TableProcessingStatus] = []
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
        quality_error_codes = {
            str(item.code)
            for item in getattr(quality_report, "table_diagnostics", [])
            if getattr(item, "severity", None) == "error"
        }
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
        non_semantic_layout_candidate = (
            not has_table_signal
            and table_profile.table_family == "unknown"
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
        extraction_inadequate = (
            extracted_table.n_rows <= 1
            or (is_descriptive_candidate and extracted_table.n_rows <= 3 and extracted_table.n_cols <= 2)
            or any(isinstance(row[0], str) and row[0].count("\n") >= 4 for row in extracted_rows if row)
            or any(isinstance(cell, str) and cell.count("\n") >= 4 for row in extracted_rows for cell in row[1:])
        )
        column_repairs = normalized_table.metadata.get("column_repairs", {})
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
                status=status,
                failure_stage=failure_stage,
                failure_reason=failure_reason,
                attempts=attempts,
                notes=notes,
            )
        )
    return statuses
