"""Regression checks for source-grid parsed cell value components."""

from __future__ import annotations

from table1_parser.parse import (
    build_parsed_cell_values,
    parse_cell_value_components,
    parsed_cell_values_to_payload,
)
from table1_parser.schemas import NormalizedTable, RowView, ValueComponent


def _build_row(row_idx: int, cells: list[str]) -> RowView:
    """Create a compact RowView for component parser tests."""
    first_cell = cells[0] if cells else ""
    alpha_only = " ".join("".join(ch if ch.isalpha() or ch.isspace() else " " for ch in first_cell).split())
    return RowView(
        row_idx=row_idx,
        raw_cells=cells,
        first_cell_raw=first_cell,
        first_cell_normalized=first_cell,
        first_cell_alpha_only=alpha_only,
        nonempty_cell_count=sum(bool(cell) for cell in cells),
        numeric_cell_count=sum(any(char.isdigit() for char in cell) for cell in cells),
        has_trailing_values=any(bool(cell) for cell in cells[1:]),
        indent_level=0,
        likely_role=None,
    )


def _component_by_kind(components: list[ValueComponent], kind: str) -> ValueComponent:
    """Return the first component with a given kind."""
    return next(component for component in components if component.kind == kind)


def test_count_percent_regression_preserves_count_percent_components() -> None:
    """`n (%)` cells should keep count and percent as separate components."""
    parsed = parse_cell_value_components("412 (48.2)")

    count = _component_by_kind(parsed.components, "count")
    percent = _component_by_kind(parsed.components, "percent")

    assert parsed.parse_pattern == "count_parenthesized_percent"
    assert count.value == 412.0
    assert count.raw_fragment == "412"
    assert percent.value == 48.2
    assert percent.raw_fragment == "48.2"
    assert parsed.notes == []

def test_parenthesized_uncertainty_regression_waits_for_context() -> None:
    """`x (y)` cells should not force SD or SE without row/table context."""
    parsed = parse_cell_value_components("52.3 (14.1)")

    primary = _component_by_kind(parsed.components, "estimate")
    uncertainty = _component_by_kind(parsed.components, "unknown")

    assert parsed.parse_pattern == "numeric_parenthesized_uncertainty"
    assert primary.value == 52.3
    assert uncertainty.value == 14.1
    assert "ambiguous_uncertainty_component" in parsed.notes

def test_spaced_six_uncertainty_regression_handles_pdf_plusminus_artifact() -> None:
    """PDFs sometimes extract plus/minus as a spaced `6`; keep it as uncertainty."""
    spaced_six = parse_cell_value_components("25.9 6 3.6†", summary_style_hint="estimate_se")

    assert spaced_six.parse_pattern == "numeric_spaced_six_uncertainty"
    assert _component_by_kind(spaced_six.components, "estimate").value == 25.9
    assert _component_by_kind(spaced_six.components, "se").value == 3.6


def test_build_parsed_cell_values_preserves_source_indices_and_optional_value_columns() -> None:
    """The component sidecar should stay index-keyed and avoid semantic labels."""
    table = NormalizedTable(
        table_id="tbl-components",
        title="Table 1",
        caption="Baseline characteristics",
        header_rows=[0],
        body_rows=[1, 2, 3],
        row_views=[
            _build_row(0, ["Characteristic", "Overall", "P-value"]),
            _build_row(1, ["Age", "52.3 (14.1)", "0.03"]),
            _build_row(2, ["Sex", "", ""]),
            _build_row(3, ["Male", "34 (45%)", ""]),
        ],
        n_rows=4,
        n_cols=3,
        metadata={},
    )

    values = build_parsed_cell_values(
        [table],
        value_column_indices_by_table_id={"tbl-components": {1, 2}},
    )
    payload = parsed_cell_values_to_payload(values)

    assert [(value.row_idx, value.col_idx, value.raw_value) for value in values] == [
        (1, 1, "52.3 (14.1)"),
        (1, 2, "0.03"),
        (3, 1, "34 (45%)"),
    ]
    assert values[0].source_table_index == 0
    assert values[0].source_table_id == "tbl-components"
    assert payload[2]["components"][0]["kind"] == "count"
    assert "variable_name" not in payload[0]
