"""Tests for deterministic paper-level table taxonomy predictions."""

from __future__ import annotations

from table1_parser.diagnostics import ParseQualityReport, ParseQualitySummary
from table1_parser.heuristics.paper_table_inventory import build_paper_table_inventory
from table1_parser.schemas import (
    ColumnDefinition,
    DefinedColumn,
    NormalizedTable,
    RowView,
    TableDefinition,
    TableProcessingStatus,
    TableProfile,
)


def _row(row_idx: int, cells: list[str]) -> RowView:
    return RowView(
        row_idx=row_idx,
        raw_cells=cells,
        first_cell_raw=cells[0],
        first_cell_normalized=cells[0],
        first_cell_alpha_only=cells[0],
        nonempty_cell_count=sum(bool(cell) for cell in cells),
        numeric_cell_count=sum(any(char.isdigit() for char in cell) for cell in cells[1:]),
        has_trailing_values=any(bool(cell) for cell in cells[1:]),
        indent_level=0,
    )


def _quality(table_id: str, recognized: float = 0.9, unknown: float = 0.0) -> ParseQualityReport:
    return ParseQualityReport(
        report_timestamp="2026-05-04T00:00:00Z",
        table_id=table_id,
        summary=ParseQualitySummary(
            total_body_rows=4,
            unknown_row_count=0,
            unknown_row_fraction=unknown,
            variable_block_count=2,
            recognized_value_pattern_fraction=recognized,
            row_warning_count=0,
            column_warning_count=0,
        ),
    )


def test_table_inventory_prefers_demographic_description_when_table_has_p_values_but_no_effect_columns() -> None:
    """P-values alone should not make a descriptive Table 1 into analysis outputs."""
    table = NormalizedTable(
        table_id="tbl-1",
        title="Table 1",
        caption="Baseline characteristics",
        header_rows=[0],
        body_rows=[1, 2, 3],
        row_views=[
            _row(1, ["Age", "52.1 (10.2)", "49.9 (9.1)", "0.03"]),
            _row(2, ["Sex", "", "", ""]),
            _row(3, ["Male", "34 (45%)", "20 (40%)", "0.10"]),
        ],
        n_rows=4,
        n_cols=4,
        metadata={"table_number": 1, "cleaned_rows": [["Variable", "Overall", "Disease", "P-value"]]},
    )
    definition = TableDefinition(
        table_id="tbl-1",
        title="Table 1",
        caption="Baseline characteristics",
        variables=[],
        column_definition=ColumnDefinition(
            columns=[
                DefinedColumn(col_idx=1, column_name="overall", column_label="Overall", inferred_role="overall"),
                DefinedColumn(col_idx=2, column_name="disease", column_label="Disease", inferred_role="group"),
                DefinedColumn(col_idx=3, column_name="p_value", column_label="P-value", inferred_role="p_value"),
            ]
        ),
    )
    inventory = build_paper_table_inventory(
        "paper",
        [],
        [table],
        [TableProfile(table_id="tbl-1", table_family="descriptive_characteristics")],
        [definition],
        [],
        [_quality("tbl-1")],
        [TableProcessingStatus(table_id="tbl-1", status="ok")],
    )

    assert inventory.tables[0].table_category == "demographic_description"
    assert "descriptive_characteristics_table_family" in inventory.tables[0].category_evidence


def test_table_inventory_requires_effect_columns_for_analysis_outputs() -> None:
    """Effect or estimate headers should drive analysis-output classification."""
    table = NormalizedTable(
        table_id="tbl-2",
        title="Table 2",
        caption="Multivariable regression results",
        header_rows=[0],
        body_rows=[1, 2],
        row_views=[
            _row(1, ["Proteinuria", "1.42 (1.10, 1.83)", "<0.001"]),
            _row(2, ["eGFR", "0.78 (0.65, 0.94)", "0.01"]),
        ],
        n_rows=3,
        n_cols=3,
        metadata={"table_number": 2, "cleaned_rows": [["Variable", "Adjusted HR (95% CI)", "P-value"]]},
    )
    definition = TableDefinition(
        table_id="tbl-2",
        title="Table 2",
        caption="Multivariable regression results",
        variables=[],
        column_definition=ColumnDefinition(
            columns=[
                DefinedColumn(col_idx=1, column_name="adjusted_hr", column_label="Adjusted HR (95% CI)", inferred_role="group"),
                DefinedColumn(col_idx=2, column_name="p_value", column_label="P-value", inferred_role="p_value"),
            ]
        ),
    )
    inventory = build_paper_table_inventory(
        "paper",
        [],
        [table],
        [TableProfile(table_id="tbl-2", table_family="estimate_results")],
        [definition],
        [],
        [_quality("tbl-2")],
        [TableProcessingStatus(table_id="tbl-2", status="ok")],
    )

    assert inventory.tables[0].table_category == "analysis_outputs"
    assert "effect_or_estimate_column_header" in inventory.tables[0].category_evidence


def test_table_inventory_does_not_call_regression_title_analysis_without_effect_columns() -> None:
    """Regression-like titles without effect/estimate columns should stay uncertain."""
    table = NormalizedTable(
        table_id="tbl-5",
        title="Table 5. Logistic regression of frailty by diet adherence",
        caption=None,
        header_rows=[0],
        body_rows=[1, 2],
        row_views=[
            _row(1, ["Low adherence", "220 (10.6%)", "276 (7.0%)"]),
            _row(2, ["High adherence", "114 (4.3%)", "90 (3.1%)"]),
        ],
        n_rows=3,
        n_cols=3,
        metadata={"table_number": 5, "cleaned_rows": [["", "Low", "High"]]},
    )
    definition = TableDefinition(
        table_id="tbl-5",
        title="Table 5. Logistic regression of frailty by diet adherence",
        caption=None,
        variables=[],
        column_definition=ColumnDefinition(
            columns=[
                DefinedColumn(col_idx=1, column_name="low", column_label="Low", inferred_role="group"),
                DefinedColumn(col_idx=2, column_name="high", column_label="High", inferred_role="group"),
            ]
        ),
    )
    inventory = build_paper_table_inventory(
        "paper",
        [],
        [table],
        [TableProfile(table_id="tbl-5", table_family="unknown")],
        [definition],
        [],
        [_quality("tbl-5")],
        [TableProcessingStatus(table_id="tbl-5", status="ok")],
    )

    assert inventory.tables[0].table_category == "unknown"
    assert "analysis_like_title_without_effect_or_estimate_columns" in inventory.tables[0].category_evidence
