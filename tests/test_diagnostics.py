"""Focused parse-quality diagnostic tests."""

from __future__ import annotations

from table1_parser.diagnostics import build_parse_quality_report
from table1_parser.schemas import NormalizedTable, RowView


def _row(row_idx: int, first_cell: str, values: list[str]) -> RowView:
    raw_cells = [first_cell, *values]
    return RowView(
        row_idx=row_idx,
        raw_cells=raw_cells,
        first_cell_raw=first_cell,
        first_cell_normalized=first_cell,
        first_cell_alpha_only=" ".join("".join(ch if ch.isalpha() else " " for ch in first_cell).split()),
        nonempty_cell_count=sum(bool(cell) for cell in raw_cells),
        numeric_cell_count=sum(any(ch.isdigit() for ch in cell) for cell in raw_cells),
        has_trailing_values=any(bool(cell) for cell in values),
    )


def test_parse_quality_reports_header_body_split_disagreement() -> None:
    table = NormalizedTable(
        table_id="tbl-split-disagreement",
        header_rows=[0],
        body_rows=[1, 2],
        row_views=[
            _row(1, "Age, years", ["52.1", "0.03"]),
            _row(2, "Sex", ["34 (48.2)", "0.10"]),
        ],
        n_rows=3,
        n_cols=3,
        metadata={
            "header_body_split_rule_comparison": {
                "selected": {"body_start": 1, "header_rows": [0]},
                "candidates": [
                    {"rule": "selective_hline_prefix", "body_start": 1, "header_rows": [0]},
                    {"rule": "first_value_region_data_row", "body_start": 2, "header_rows": [0, 1]},
                ],
                "rules_agree": False,
            }
        },
    )

    report = build_parse_quality_report(table, row_classifications=[])

    assert any(
        item.code == "header_body_split_rule_disagreement"
        for item in report.table_diagnostics
    )
