"""Focused tests for final ParsedTable assembly."""

from __future__ import annotations

from table1_parser.parse import build_parsed_table
from table1_parser.parse.value_parser import parse_cell_value
from table1_parser.schemas import (
    ColumnDefinition,
    DefinedColumn,
    DefinedLevel,
    DefinedVariable,
    NormalizedTable,
    RowView,
    TableDefinition,
)


def _build_row(
    row_idx: int,
    first_cell_raw: str,
    trailing: list[str],
    indent_level: int | None = None,
) -> RowView:
    """Create a compact RowView for parsed-table tests."""
    raw_cells = [first_cell_raw, *trailing]
    alpha_only = " ".join("".join(ch if ch.isalpha() or ch.isspace() else " " for ch in first_cell_raw).split())
    return RowView(
        row_idx=row_idx,
        raw_cells=raw_cells,
        first_cell_raw=first_cell_raw,
        first_cell_normalized=first_cell_raw,
        first_cell_alpha_only=alpha_only,
        nonempty_cell_count=sum(bool(cell) for cell in raw_cells),
        numeric_cell_count=sum(any(char.isdigit() for char in cell) for cell in raw_cells),
        has_trailing_values=any(bool(cell) for cell in trailing),
        indent_level=indent_level,
        likely_role=None,
    )


def _build_table() -> NormalizedTable:
    """Build a normalized table with an overall column, subgroup Ns, and p-values."""
    return NormalizedTable(
        table_id="tbl-parsed",
        title="Table 1",
        caption="Baseline characteristics by case status",
        header_rows=[0],
        body_rows=[1, 2, 3, 4],
        row_views=[
            _build_row(1, "n", ["100", "40", "60", ""]),
            _build_row(2, "Sex", ["", "", "", ""]),
            _build_row(3, "Male", ["40 (40)", "10 (10)", "30 (30)", "0.02"]),
            _build_row(4, "Female", ["60 (60)", "30 (30)", "30 (30)", ""]),
        ],
        n_rows=5,
        n_cols=5,
        metadata={
            "cleaned_rows": [
                ["Characteristic", "Overall (n=100)", "Cases (n=40)", "Controls (n=60)", "P-value"],
                ["n", "100", "40", "60", ""],
                ["Sex", "", "", "", ""],
                ["Male", "40 (40)", "10 (10)", "30 (30)", "0.02"],
                ["Female", "60 (60)", "30 (30)", "30 (30)", ""],
            ]
        },
    )


def _build_definition() -> TableDefinition:
    """Build a matching TableDefinition with a binary categorical variable."""
    return TableDefinition(
        table_id="tbl-parsed",
        title="Table 1",
        caption="Baseline characteristics by case status",
        variables=[
            DefinedVariable(
                variable_name="Sex",
                variable_label="Sex",
                variable_type="binary",
                row_start=2,
                row_end=4,
                levels=[
                    DefinedLevel(level_name="Male", level_label="Male", row_idx=3, confidence=0.92),
                    DefinedLevel(level_name="Female", level_label="Female", row_idx=4, confidence=0.92),
                ],
                summary_style_hint="count_pct",
                confidence=0.95,
            )
        ],
        column_definition=ColumnDefinition(
            columns=[
                DefinedColumn(
                    col_idx=1,
                    column_name="overall",
                    column_label="Overall (n=100)",
                    inferred_role="overall",
                    confidence=0.95,
                ),
                DefinedColumn(
                    col_idx=2,
                    column_name="cases",
                    column_label="Cases (n=40)",
                    header_leaf_id="leaf-2",
                    header_leaf_label="Cases (n=40)",
                    header_group_ids=["group-1"],
                    header_group_labels=["Case status"],
                    header_path=["Case status", "Cases (n=40)"],
                    inferred_role="group",
                    confidence=0.92,
                ),
                DefinedColumn(
                    col_idx=3,
                    column_name="controls",
                    column_label="Controls (n=60)",
                    inferred_role="comparison_group",
                    confidence=0.92,
                ),
                DefinedColumn(
                    col_idx=4,
                    column_name="p_value",
                    column_label="P-value",
                    inferred_role="p_value",
                    confidence=0.98,
                ),
            ]
        ),
    )


def test_build_parsed_table_parses_count_percent_values_and_column_roles() -> None:
    """Final parsed output should keep semantic columns while parsing count-percent cells."""
    parsed = build_parsed_table(_build_table(), _build_definition())

    assert parsed.table_id == "tbl-parsed"
    assert [column.inferred_role for column in parsed.columns] == ["overall", "group", "group", "p_value"]
    assert parsed.columns[1].header_path == ["Case status", "Cases (n=40)"]
    male_overall = next(
        value for value in parsed.values if value.variable_name == "Sex" and value.level_label == "Male" and value.col_idx == 1
    )
    assert male_overall.raw_value == "40 (40)"
    assert male_overall.value_type == "count"
    assert male_overall.parsed_numeric == 40.0
    assert male_overall.parsed_secondary_numeric == 40.0
    assert male_overall.confidence == 0.98


def test_build_parsed_table_uses_subgroup_share_heuristic_for_non_overall_columns() -> None:
    """Subgroup count-percent cells should validate against their share of the overall population."""
    parsed = build_parsed_table(_build_table(), _build_definition())

    cases_male = next(
        value for value in parsed.values if value.variable_name == "Sex" and value.level_label == "Male" and value.col_idx == 2
    )
    controls_female = next(
        value for value in parsed.values if value.variable_name == "Sex" and value.level_label == "Female" and value.col_idx == 3
    )

    assert cases_male.confidence == 0.97
    assert controls_female.confidence == 0.97
    assert parsed.notes == []


def test_build_parsed_table_adds_soft_note_when_group_share_does_not_match() -> None:
    """Soft heuristic mismatches should lower confidence and add a note instead of rejecting the table."""
    table = _build_table()
    table.row_views[2].raw_cells[2] = "10 (12)"
    table.row_views[3].raw_cells[2] = "30 (33)"

    parsed = build_parsed_table(table, _build_definition())

    mismatched = next(
        value for value in parsed.values if value.variable_name == "Sex" and value.level_label == "Male" and value.col_idx == 2
    )
    assert mismatched.confidence == 0.85
    assert any(note.startswith("count_pct_group_share_mismatch: variable=Sex column=cases") for note in parsed.notes)


def test_build_parsed_table_parses_n_only_categorical_values_without_count_percent_notes() -> None:
    """Categorical variables with n_only summaries should parse as counts without count-percent notes."""
    table = _build_table()
    table.row_views[2].raw_cells[1:] = ["40", "10", "30", "0.02"]
    table.row_views[3].raw_cells[1:] = ["60", "30", "30", ""]
    definition = _build_definition()
    definition.variables[0].summary_style_hint = "n_only"

    parsed = build_parsed_table(table, definition)

    male_overall = next(
        value for value in parsed.values if value.variable_name == "Sex" and value.level_label == "Male" and value.col_idx == 1
    )
    female_cases = next(
        value for value in parsed.values if value.variable_name == "Sex" and value.level_label == "Female" and value.col_idx == 2
    )

    assert male_overall.value_type == "count"
    assert male_overall.parsed_numeric == 40.0
    assert male_overall.parsed_secondary_numeric is None
    assert female_cases.value_type == "count"
    assert female_cases.parsed_numeric == 30.0
    assert parsed.notes == []


def test_parse_cell_value_parses_pdf_plusminus_six_mean_sd() -> None:
    """A numeric 6 between two values can be the extracted plus/minus glyph."""
    parsed = parse_cell_value("25.9 6 3.6†", "group")

    assert parsed.value_type == "mean_sd"
    assert parsed.parsed_numeric == 25.9
    assert parsed.parsed_secondary_numeric == 3.6


def test_parse_cell_value_parses_footnoted_p_value() -> None:
    """P-value footnote markers should not block numeric p-value parsing."""
    parsed = parse_cell_value("< 0.001b", "p_value")

    assert parsed.value_type == "text"
    assert parsed.parsed_numeric == 0.001
