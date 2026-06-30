"""Focused regressions for canonical resolved continuation tables."""

from __future__ import annotations

from table1_parser.diagnostics import DiagnosticItem, ParseQualityReport, ParseQualitySummary
from table1_parser.heuristics.table_definition_builder import build_table_definitions
from table1_parser.processing_status import build_table_processing_statuses
from table1_parser.resolved_tables import build_resolved_table_set
from table1_parser.schemas import (
    ColumnHeaderLeaf,
    ColumnHeaderSchema,
    ExtractedTable,
    NormalizedTable,
    ParsedTable,
    RowView,
    TableCell,
    TableProfile,
)


def _row_view(row_idx: int, cells: list[str]) -> RowView:
    first_cell = cells[0] if cells else ""
    return RowView(
        row_idx=row_idx,
        raw_cells=cells,
        first_cell_raw=first_cell,
        first_cell_normalized=first_cell,
        first_cell_alpha_only="".join(char for char in first_cell if char.isalpha() or char.isspace()),
        nonempty_cell_count=sum(bool(cell) for cell in cells),
        numeric_cell_count=sum(any(char.isdigit() for char in cell) for cell in cells),
        has_trailing_values=any(bool(cell) for cell in cells[1:]),
        indent_level=0,
        likely_role="unknown",
    )


def _table(
    table_id: str,
    rows: list[list[str]],
    *,
    is_continuation: bool,
    page_num: int,
    table_number: int = 1,
) -> NormalizedTable:
    body_rows = list(range(1, len(rows)))
    return NormalizedTable(
        table_id=table_id,
        title=f"Table {table_number} (continued)" if is_continuation else f"Table {table_number}",
        caption=(
            f"Table {table_number} (continued)"
            if is_continuation
            else f"Table {table_number}. Baseline characteristics"
        ),
        header_rows=[0],
        body_rows=body_rows,
        row_views=[_row_view(row_idx, rows[row_idx]) for row_idx in body_rows],
        n_rows=len(rows),
        n_cols=max(len(row) for row in rows),
        metadata={
            "cleaned_rows": rows,
            "table_number": table_number,
            "is_continuation": is_continuation,
            "continuation_of_table_number": table_number if is_continuation else None,
            "source_page_num": page_num,
        },
    )


def _schema(
    table: NormalizedTable,
    headers: list[str] | None = None,
) -> ColumnHeaderSchema:
    headers = headers or ["Characteristic", "Overall", "Cases"]
    return ColumnHeaderSchema(
        schema_id=f"{table.table_id}:column_header_schema",
        table_id=table.table_id,
        n_cols=table.n_cols,
        leaves=[
            ColumnHeaderLeaf(
                leaf_id=f"{table.table_id}:leaf:{col_idx}",
                table_id=table.table_id,
                col_idx=col_idx,
                is_row_label_column=col_idx == 0,
                is_value_column=col_idx != 0,
                leaf_label=header,
                leaf_name=header,
            )
            for col_idx, header in enumerate(headers)
        ],
    )


def test_explicit_matching_continuation_becomes_one_resolved_semantic_table() -> None:
    """Explicit continuations with matching schema columns should become one working table."""
    base = _table(
        "tbl-base",
        [["Characteristic", "Overall", "Cases"], ["Age, years", "52.1", "58.2"]],
        is_continuation=False,
        page_num=1,
    )
    continuation = _table(
        "tbl-cont",
        [["Characteristic", "Overall", "Cases"], ["BMI", "27.1", "29.4"]],
        is_continuation=True,
        page_num=2,
    )

    resolved_set = build_resolved_table_set([base, continuation], [_schema(base), _schema(continuation)])

    assert len(resolved_set.resolved_tables) == 1
    resolved = resolved_set.resolved_tables[0]
    assert resolved.resolution_type == "integrated_continuation"
    assert resolved.source_table_ids == ["tbl-base", "tbl-cont"]
    assert resolved.table.body_rows == [1, 2]
    assert resolved.table.metadata["cleaned_rows"][2] == ["BMI", "27.1", "29.4"]
    assert resolved_set.source_tables[0].role == "base_fragment"
    assert resolved_set.source_tables[1].role == "continuation_fragment"
    assert resolved_set.decisions[-1].decision_type == "integrated_continuation"
    assert resolved_set.decisions[-1].status == "accepted"


def test_explicit_continuation_with_incompatible_columns_remains_rejected_singleton() -> None:
    """Continuation identity is not enough when schema-derived columns differ."""
    base = _table(
        "tbl-base",
        [["Characteristic", "Overall", "Cases"], ["Age, years", "52.1", "58.2"]],
        is_continuation=False,
        page_num=1,
    )
    continuation = _table(
        "tbl-cont",
        [["Characteristic", "Overall", "Controls"], ["BMI", "27.1", "25.4"]],
        is_continuation=True,
        page_num=2,
    )

    resolved_set = build_resolved_table_set(
        [base, continuation],
        [
            _schema(base, ["Characteristic", "Overall", "Cases"]),
            _schema(continuation, ["Characteristic", "Overall", "Controls"]),
        ],
    )

    assert len(resolved_set.resolved_tables) == 2
    assert [table.resolution_type for table in resolved_set.resolved_tables] == ["singleton", "singleton"]
    assert resolved_set.source_tables[1].role == "rejected_continuation"
    rejected = resolved_set.resolved_tables[1]
    assert rejected.table_id == "tbl-cont"
    assert rejected.row_provenance[0].source_role == "rejected_continuation"
    assert rejected.column_schema_decisions[0].status == "rejected"
    assert any("column_header_mismatch" in item for item in rejected.column_schema_decisions[0].diagnostics)
    assert resolved_set.decisions[-1].decision_type == "rejected_continuation"
    assert resolved_set.decisions[-1].status == "rejected"


def test_unrelated_tables_with_similar_columns_are_not_integrated() -> None:
    """Matching columns alone should not create a continuation relationship."""
    first = _table(
        "tbl-1",
        [["Characteristic", "Overall", "Cases"], ["Age, years", "52.1", "58.2"]],
        is_continuation=False,
        page_num=1,
        table_number=1,
    )
    second = _table(
        "tbl-2",
        [["Characteristic", "Overall", "Cases"], ["BMI", "27.1", "29.4"]],
        is_continuation=False,
        page_num=2,
        table_number=2,
    )

    resolved_set = build_resolved_table_set([first, second], [_schema(first), _schema(second)])

    assert len(resolved_set.resolved_tables) == 2
    assert [table.table_id for table in resolved_set.resolved_tables] == ["tbl-1", "tbl-2"]
    assert [table.resolution_type for table in resolved_set.resolved_tables] == ["singleton", "singleton"]
    assert [decision.decision_type for decision in resolved_set.decisions] == ["singleton", "singleton"]
    assert [source.role for source in resolved_set.source_tables] == ["singleton", "singleton"]


def test_boundary_continuation_notes_integrate_uncaptioned_fragments() -> None:
    """Adjacent uncaptioned fragments with numbered boundary notes and matching columns form one table."""
    base_rows = [
        ["Study", "N", "H pylori"],
        ["Study A", "10", "20%"],
        ["Study B", "20", "30%"],
    ]
    continuation_rows = [
        ["Study", "N", "H pylori"],
        ["(Continued from", "previous", "page)"],
        ["Study C", "30", "40%"],
    ]
    final_rows = [
        ["Study", "N", "H pylori"],
        ["(Continued from", "previous", "page)"],
        ["Study D", "40", "50%"],
    ]
    base = NormalizedTable(
        table_id="paper-p5-t0",
        title=None,
        caption=None,
        header_rows=[0],
        body_rows=[1, 2],
        row_views=[_row_view(row_idx, base_rows[row_idx]) for row_idx in [1, 2]],
        n_rows=3,
        n_cols=3,
        metadata={
            "cleaned_rows": base_rows,
            "source_page_num": 5,
            "trailing_non_table_rows": {
                "reasons": ["trailing_continuation_note"],
                "continuation_table_number": 1,
            },
        },
    )
    continuation = NormalizedTable(
        table_id="paper-p6-t0",
        title=None,
        caption=None,
        header_rows=[0],
        body_rows=[2],
        row_views=[_row_view(2, continuation_rows[2])],
        n_rows=3,
        n_cols=3,
        metadata={
            "cleaned_rows": continuation_rows,
            "source_page_num": 6,
            "header_detection": {"continuation_note_rows": [1]},
            "trailing_non_table_rows": {
                "reasons": ["trailing_continuation_note"],
                "continuation_table_number": 1,
            },
        },
    )
    final = NormalizedTable(
        table_id="paper-p7-t0",
        title=None,
        caption=None,
        header_rows=[0],
        body_rows=[2],
        row_views=[_row_view(2, final_rows[2])],
        n_rows=3,
        n_cols=3,
        metadata={
            "cleaned_rows": final_rows,
            "source_page_num": 7,
            "header_detection": {"continuation_note_rows": [1]},
        },
    )

    resolved_set = build_resolved_table_set(
        [base, continuation, final],
        [
            _schema(base, ["", "N", "H pylori"]),
            _schema(continuation, ["Characteristics", "N", "H pylori"]),
            _schema(final, ["", "N", "H pylori"]),
        ],
    )

    assert len(resolved_set.resolved_tables) == 1
    resolved = resolved_set.resolved_tables[0]
    assert resolved.resolution_type == "integrated_continuation"
    assert resolved.logical_table_number == 1
    assert resolved.source_table_ids == ["paper-p5-t0", "paper-p6-t0", "paper-p7-t0"]
    assert resolved.table.body_rows == [1, 2, 3, 4]
    assert resolved.table.metadata["cleaned_rows"][3] == ["Study C", "30", "40%"]
    assert resolved.table.metadata["cleaned_rows"][4] == ["Study D", "40", "50%"]
    assert [source.role for source in resolved_set.source_tables] == [
        "base_fragment",
        "continuation_fragment",
        "continuation_fragment",
    ]
    assert all(decision.status == "accepted" for decision in resolved_set.decisions)
    assert any(
        "prior_trailing_continuation_table_number:1" in decision.identity_evidence
        for decision in resolved_set.decisions
        if decision.decision_type == "integrated_continuation"
    )


def test_empty_continued_row_integrates_adjacent_fragment_after_column_match() -> None:
    """A final empty Continued row is dropped only after the next fragment matches columns."""
    base_rows = [
        ["Variables", "Total", "With asthma", "Without asthma", "P value"],
        ["Ever told you had chronic bronchitis", "", "", "", "0.000"],
        ["No", "53,355 (83.1)", "3889 (83.9)", "49,466 (98.4)", ""],
        ["Yes", "1564 (2.4)", "761 (16.4)", "803 (1.6)", ""],
        ["Continued", "", "", "", ""],
    ]
    continuation_rows = [
        ["Variables", "Total", "With asthma", "Without asthma", "P value"],
        ["Missing values", "9303 (14.5)", "", "", ""],
        ["Ever told you had COPD, emphysema, ChB", "", "", "", "0.000"],
    ]
    base = NormalizedTable(
        table_id="asthma-p4-t0",
        title=None,
        caption=None,
        header_rows=[0],
        body_rows=[1, 2, 3, 4],
        row_views=[_row_view(row_idx, base_rows[row_idx]) for row_idx in [1, 2, 3, 4]],
        n_rows=5,
        n_cols=5,
        metadata={"cleaned_rows": base_rows, "source_page_num": 4},
    )
    continuation = NormalizedTable(
        table_id="asthma-p5-t0",
        title=None,
        caption=None,
        header_rows=[0],
        body_rows=[1, 2],
        row_views=[_row_view(row_idx, continuation_rows[row_idx]) for row_idx in [1, 2]],
        n_rows=3,
        n_cols=5,
        metadata={"cleaned_rows": continuation_rows, "source_page_num": 5},
    )

    resolved_set = build_resolved_table_set(
        [base, continuation],
        [
            _schema(base, ["Variables", "Total", "With asthma", "Without asthma", "P value"]),
            _schema(continuation, ["Variables", "Total", "With asthma", "Without asthma", "P value"]),
        ],
    )

    assert len(resolved_set.resolved_tables) == 1
    resolved = resolved_set.resolved_tables[0]
    assert resolved.resolution_type == "integrated_continuation"
    assert ["Continued", "", "", "", ""] not in resolved.table.metadata["cleaned_rows"]
    assert resolved.table.metadata["cleaned_rows"][4] == ["Missing values", "9303 (14.5)", "", "", ""]
    assert resolved.integration_boundaries[0].dropped_rows[0].reason == (
        "base_trailing_empty_continued_row_dropped_after_schema_match"
    )
    assert "adjacent_page_after_empty_continued_row" in resolved_set.decisions[-1].identity_evidence


def _extracted_table(table_id: str) -> ExtractedTable:
    return ExtractedTable(
        table_id=table_id,
        source_pdf="paper.pdf",
        page_num=1,
        title="Table 1",
        caption="Table 1. Baseline characteristics",
        n_rows=2,
        n_cols=3,
        cells=[TableCell(row_idx=0, col_idx=0, text="Characteristic")],
        extraction_backend="test",
    )


def _quality_report(table_id: str, code: str | None = None) -> ParseQualityReport:
    return ParseQualityReport(
        report_timestamp="2026-06-29T00:00:00Z",
        table_id=table_id,
        summary=ParseQualitySummary(
            total_body_rows=1,
            unknown_row_count=0,
            unknown_row_fraction=0.0,
            variable_block_count=1,
            recognized_value_pattern_fraction=1.0,
            row_warning_count=0,
            column_warning_count=0,
        ),
        table_diagnostics=(
            [
                DiagnosticItem(
                    severity="warning",
                    code=code,
                    message="Source-fragment warning.",
                )
            ]
            if code is not None
            else []
        ),
    )


def test_resolved_continuation_attaches_leading_levels_and_preserves_source_status() -> None:
    """Continuation levels should attach in the canonical resolved semantic table."""
    base = _table(
        "tbl-base",
        [["Characteristic", "Overall", "Cases"], ["Race, n (%)", "", ""]],
        is_continuation=False,
        page_num=1,
    )
    continuation = _table(
        "tbl-cont",
        [
            ["Characteristic", "Overall", "Cases"],
            ["White", "34 (45%)", "10 (40%)"],
            ["Black", "41 (55%)", "15 (60%)"],
            ["Age, years", "52.1", "49.9"],
        ],
        is_continuation=True,
        page_num=2,
    )
    source_schemas = [_schema(base), _schema(continuation)]

    resolved_set = build_resolved_table_set([base, continuation], source_schemas)
    resolved = resolved_set.resolved_tables[0]
    resolved_schema = source_schemas[0].model_copy(update={"table_id": resolved.table_id})
    definition = build_table_definitions([resolved.table], [resolved_schema])[0]

    assert len(resolved_set.resolved_tables) == 1
    assert resolved.resolution_type == "integrated_continuation"
    assert [variable.variable_label for variable in definition.variables] == ["Race, n (%)", "Age, years"]
    assert [level.level_label for level in definition.variables[0].levels] == ["White", "Black"]
    assert definition.variables[0].row_end == 3

    statuses = build_table_processing_statuses(
        [_extracted_table(resolved.table_id)],
        [resolved.table],
        [TableProfile(table_id=resolved.table_id, table_family="unknown")],
        [definition],
        [
            ParsedTable(
                table_id=resolved.table_id,
                title=resolved.title,
                caption=resolved.caption,
                variables=[],
                columns=[],
                values=[],
            )
        ],
        resolved_table_set=resolved_set,
        source_parse_quality_reports=[
            _quality_report("tbl-base"),
            _quality_report("tbl-cont", "continuation_source_warning"),
        ],
    )

    assert statuses[0].table_id == resolved.table_id
    assert statuses[0].source_table_ids == ["tbl-base", "tbl-cont"]
    assert [
        (diagnostic.source_table_id, diagnostic.stage, diagnostic.code)
        for diagnostic in statuses[0].source_fragment_diagnostics
    ] == [("tbl-cont", "parse_quality", "continuation_source_warning")]
