"""Focused tests for deterministic TableDefinition assembly."""

from __future__ import annotations

import pytest

from table1_parser.heuristics.table_definition_builder import build_table_definition
from table1_parser.heuristics.table_definition_rows import build_defined_variables
from table1_parser.schemas import NormalizedTable, RowView, TableDefinition
from table1_parser.validation.table_definition import validate_table_definition


def _build_row(
    row_idx: int,
    first_cell_raw: str,
    trailing: list[str],
    indent_level: int | None = None,
) -> RowView:
    """Create a compact RowView for TableDefinition tests."""
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


def test_build_table_definition_derives_variables_levels_and_columns() -> None:
    """The deterministic builder should assemble SQL-query-ready row and column semantics."""
    table = NormalizedTable(
        table_id="tbl-def",
        title="Table 1. Baseline characteristics by RA status",
        caption="Baseline characteristics by RA status",
        header_rows=[0],
        body_rows=[1, 2, 3, 4],
        row_views=[
            _build_row(1, "Age, years", ["52.3 (14.1)", "51.2 (13.0)", "0.03"]),
            _build_row(2, "Sex", []),
            _build_row(3, "Male", ["412 (48.2)", "201 (44.0)", ""]),
            _build_row(4, "Female", ["442 (51.8)", "255 (56.0)", ""]),
        ],
        n_rows=5,
        n_cols=4,
        metadata={
            "cleaned_rows": [
                ["Characteristic", "Overall", "RA", "P-value"],
                ["Age, years", "52.3 (14.1)", "51.2 (13.0)", "0.03"],
                ["Sex", "", "", ""],
                ["Male", "412 (48.2)", "201 (44.0)", ""],
                ["Female", "442 (51.8)", "255 (56.0)", ""],
            ]
        },
    )

    definition = build_table_definition(table)

    assert definition.table_id == "tbl-def"
    assert definition.variables[0].variable_name == "Age years"
    assert definition.variables[0].variable_type == "continuous"
    assert definition.variables[0].units_hint == "years"
    assert definition.variables[1].variable_label == "Sex"
    assert definition.variables[1].variable_type == "binary"
    assert [level.level_label for level in definition.variables[1].levels] == ["Male", "Female"]
    assert definition.column_definition.grouping_label == "RA status"
    assert definition.column_definition.group_count == 1
    assert [column.column_label for column in definition.column_definition.columns] == ["Overall", "RA", "P-value"]
    assert [column.inferred_role for column in definition.column_definition.columns] == ["overall", "group", "p_value"]
    assert definition.column_definition.columns[1].group_level_label == "RA"
    assert definition.column_definition.columns[1].group_order == 1
    assert definition.column_definition.columns[2].statistic_subtype == "p_value"


def test_build_table_definition_carries_rotated_layout_note() -> None:
    """Rotated tables should carry a simple note for downstream tooling."""
    table = NormalizedTable(
        table_id="tbl-rotated",
        header_rows=[0],
        body_rows=[1],
        row_views=[_build_row(1, "Age, years", ["52.3 (14.1)", "51.2 (13.0)"])],
        n_rows=2,
        n_cols=3,
        metadata={
            "cleaned_rows": [["Characteristic", "Overall", "Case"], ["Age, years", "52.3 (14.1)", "51.2 (13.0)"]],
            "table_orientation": "rotated",
        },
    )

    definition = build_table_definition(table)

    assert "rotated_table_layout" in definition.notes


def test_build_table_definition_preserves_numeric_threshold_and_range_level_names() -> None:
    """Level names should preserve comparator and range syntax, unlike variable names."""
    table = NormalizedTable(
        table_id="tbl-thresholds",
        header_rows=[0],
        body_rows=[1, 2, 3, 4],
        row_views=[
            _build_row(1, "Protein/creatinine ratio, n (%)", []),
            _build_row(2, "< 1.3", ["12 (10.0)"], indent_level=2),
            _build_row(3, "1.3-1.8", ["25 (20.8)"], indent_level=2),
            _build_row(4, ">1.8", ["83 (69.2)"], indent_level=2),
        ],
        n_rows=5,
        n_cols=2,
        metadata={
            "cleaned_rows": [
                ["Characteristic", "Overall"],
                ["Protein/creatinine ratio, n (%)", ""],
                ["< 1.3", "12 (10.0)"],
                ["1.3-1.8", "25 (20.8)"],
                [">1.8", "83 (69.2)"],
            ]
        },
    )

    definition = build_table_definition(table)

    assert definition.variables[0].variable_name == "Protein creatinine ratio"
    assert [level.level_name for level in definition.variables[0].levels] == ["< 1.3", "1.3-1.8", ">1.8"]
    assert [level.level_label for level in definition.variables[0].levels] == ["< 1.3", "1.3-1.8", ">1.8"]


def test_build_table_definition_preserves_textual_comparator_level_names() -> None:
    """Level names should keep comparator-prefixed textual categories distinct."""
    table = NormalizedTable(
        table_id="tbl-education",
        header_rows=[0],
        body_rows=[1, 2, 3],
        row_views=[
            _build_row(1, "Education, n (%)", []),
            _build_row(2, "<High school", ["15 (12.0)"], indent_level=2),
            _build_row(3, ">High school", ["110 (88.0)"], indent_level=2),
        ],
        n_rows=4,
        n_cols=2,
        metadata={
            "cleaned_rows": [
                ["Characteristic", "Overall"],
                ["Education, n (%)", ""],
                ["<High school", "15 (12.0)"],
                [">High school", "110 (88.0)"],
            ]
        },
    )

    definition = build_table_definition(table)

    assert definition.variables[0].variable_name == "Education"
    assert [level.level_name for level in definition.variables[0].levels] == ["<High school", ">High school"]
    assert [level.level_label for level in definition.variables[0].levels] == ["<High school", ">High school"]


def test_variable_and_level_names_use_different_normalization_rules() -> None:
    """Variable rows and level rows should still normalize differently after inlining."""
    table = NormalizedTable(
        table_id="tbl-name-rules",
        header_rows=[0],
        body_rows=[1, 2, 3],
        row_views=[
            _build_row(1, "Age, years, mean (SD)", ["52.3 (14.1)"]),
            _build_row(2, "Education, n (%)", []),
            _build_row(3, ">High school", ["110 (88.0)"], indent_level=2),
        ],
        n_rows=4,
        n_cols=2,
        metadata={
            "cleaned_rows": [
                ["Characteristic", "Overall"],
                ["Age, years, mean (SD)", "52.3 (14.1)"],
                ["Education, n (%)", ""],
                [">High school", "110 (88.0)"],
            ]
        },
    )

    variables = build_defined_variables(table)

    assert variables[0].variable_name == "Age years"
    assert variables[1].variable_name == "Education"
    assert variables[1].levels[0].level_name == ">High school"


def test_one_row_binary_summary_builds_binary_defined_variable() -> None:
    """Standalone count-percent summary rows should map to binary variables."""
    table = NormalizedTable(
        table_id="tbl-binary-row",
        header_rows=[0],
        body_rows=[1, 2],
        row_views=[
            _build_row(1, "Healthy diet", ["172 (6.7%)", "1597 (76.9%)", "1540 (67.0%)", "<0.001"]),
            _build_row(2, "Age, years", ["36.0 (12.0)", "44.0 (13.0)", "45.0 (14.0)", "<0.001"]),
        ],
        n_rows=3,
        n_cols=5,
        metadata={
            "cleaned_rows": [
                ["Characteristic", "Low", "Middle", "High", "P-value"],
                ["Healthy diet", "172 (6.7%)", "1597 (76.9%)", "1540 (67.0%)", "<0.001"],
                ["Age, years", "36.0 (12.0)", "44.0 (13.0)", "45.0 (14.0)", "<0.001"],
            ]
        },
    )

    variables = build_defined_variables(table)

    assert variables[0].variable_label == "Healthy diet"
    assert variables[0].variable_type == "binary"
    assert variables[0].summary_style_hint == "count_pct"
    assert variables[0].levels == []


def test_threshold_pair_rows_build_one_binary_defined_variable() -> None:
    """Adjacent complementary threshold rows should become one binary variable with levels."""
    table = NormalizedTable(
        table_id="tbl-threshold-pair",
        header_rows=[0],
        body_rows=[1, 2, 3, 4],
        row_views=[
            _build_row(1, "Age, years, mean(SD)", ["50.77 ± 17.30", "47.11 ± 18.46", "53.21 ± 16.03", "< 0.001"]),
            _build_row(2, "< 60years", ["2,512 (63.42%)", "1,105 (69.76%)", "1,407 (59.19%)", "< 0.001"]),
            _build_row(3, ">= 60years", ["1,449 (36.58%)", "479 (30.24%)", "970 (40.81%)", ""]),
            _build_row(4, "Weight, kg, mean(SD)", ["84.05 ± 22.53", "72.03 ± 16.04", "92.07 ± 22.68", "< 0.001"]),
        ],
        n_rows=5,
        n_cols=5,
        metadata={
            "cleaned_rows": [
                ["Characteristic", "Overall", "Without FLD", "With FLD", "P-value"],
                ["Age, years, mean(SD)", "50.77 ± 17.30", "47.11 ± 18.46", "53.21 ± 16.03", "< 0.001"],
                ["< 60years", "2,512 (63.42%)", "1,105 (69.76%)", "1,407 (59.19%)", "< 0.001"],
                [">= 60years", "1,449 (36.58%)", "479 (30.24%)", "970 (40.81%)", ""],
                ["Weight, kg, mean(SD)", "84.05 ± 22.53", "72.03 ± 16.04", "92.07 ± 22.68", "< 0.001"],
            ]
        },
    )

    variables = build_defined_variables(table)

    assert [variable.variable_label for variable in variables] == [
        "Age, years, mean(SD)",
        "Age category",
        "Weight, kg, mean(SD)",
    ]
    assert variables[1].variable_type == "binary"
    assert variables[1].row_start == 2
    assert variables[1].row_end == 3
    assert [level.level_label for level in variables[1].levels] == ["< 60years", ">= 60years"]
    assert variables[1].summary_style_hint == "count_pct"


def test_categorical_levels_with_integer_counts_only_build_n_only_summary_hint() -> None:
    """Categorical variables with integer-only child rows should carry an n_only summary hint."""
    table = NormalizedTable(
        table_id="tbl-education-counts-only",
        header_rows=[0],
        body_rows=[1, 2, 3],
        row_views=[
            _build_row(1, "Education", []),
            _build_row(2, "High school", ["25", "13", "12"]),
            _build_row(3, "College", ["75", "27", "48"]),
        ],
        n_rows=4,
        n_cols=4,
        metadata={
            "cleaned_rows": [
                ["Characteristic", "Overall", "Cases", "Controls"],
                ["Education", "", "", ""],
                ["High school", "25", "13", "12"],
                ["College", "75", "27", "48"],
            ]
        },
    )

    variables = build_defined_variables(table)

    assert variables[0].variable_type == "categorical"
    assert variables[0].summary_style_hint == "n_only"


def test_categorical_levels_with_non_count_values_do_not_silently_get_count_pct_hint() -> None:
    """Malformed categorical child values should not force a count_pct summary hint."""
    table = NormalizedTable(
        table_id="tbl-education-malformed",
        header_rows=[0],
        body_rows=[1, 2, 3],
        row_views=[
            _build_row(1, "Education, n (%)", []),
            _build_row(2, "High school", ["0.45", "0.32"]),
            _build_row(3, "College", ["0.55", "0.68"]),
        ],
        n_rows=4,
        n_cols=3,
        metadata={
            "cleaned_rows": [
                ["Characteristic", "Cases", "Controls"],
                ["Education, n (%)", "", ""],
                ["High school", "0.45", "0.32"],
                ["College", "0.55", "0.68"],
            ]
        },
    )

    variables = build_defined_variables(table)

    assert variables[0].variable_type == "unknown"
    assert variables[0].summary_style_hint is None


def test_indented_weighted_and_age_standardized_levels_build_categorical_variables() -> None:
    """Survey-weighted and age-standardized real-valued columns should still support levels."""
    table = NormalizedTable(
        table_id="tbl-weighted-levels",
        header_rows=[0, 1],
        body_rows=[2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
        row_views=[
            _build_row(2, "Age (mean: 24 teeth)", [], indent_level=0),
            _build_row(3, "30 to 34 years", ["435", "16.7", "24.4", "2.7"], indent_level=9),
            _build_row(4, "35 to 49 years", ["1,352", "54.0", "36.6", "1.6"], indent_level=9),
            _build_row(5, "Sex", [], indent_level=0),
            _build_row(6, "Males", ["1,872", "67.5", "56.4", "2.1"], indent_level=9),
            _build_row(7, "Females", ["1,871", "69.6", "38.4", "2.4"], indent_level=9),
            _build_row(8, "Education", [], indent_level=0),
            _build_row(9, "Less than high school", ["1,030", "23.8", "66.9", "2.4"], indent_level=9),
            _build_row(10, "High school/GED", ["815", "29.6", "53.5", "3.2"], indent_level=9),
            _build_row(11, "More than high school", ["1,889", "83.3", "39.3", "2.3"], indent_level=9),
        ],
        n_rows=12,
        n_cols=5,
        metadata={
            "indentation_informative": True,
            "cleaned_rows": [
                ["Characteristics", "n", "Weighted n (millions)", "Age standardized %", "SE"],
                ["", "", "", "", ""],
            ],
        },
    )

    variables = build_defined_variables(table)

    assert [(variable.variable_label, variable.variable_type) for variable in variables] == [
        ("Age (mean: 24 teeth)", "categorical"),
        ("Sex", "categorical"),
        ("Education", "categorical"),
    ]
    assert [level.level_label for level in variables[0].levels] == ["30 to 34 years", "35 to 49 years"]
    assert [level.level_label for level in variables[1].levels] == ["Males", "Females"]
    assert [level.level_label for level in variables[2].levels] == [
        "Less than high school",
        "High school/GED",
        "More than high school",
    ]
    assert all(variable.summary_style_hint is None for variable in variables)


def test_indicator_style_cat_row_builds_binary_defined_variable() -> None:
    """Explicit `.cat = ...` indicator rows should map to binary variables."""
    table = NormalizedTable(
        table_id="tbl-age-cat-defined",
        header_rows=[0],
        body_rows=[1, 2, 3, 4, 5, 6, 7, 8],
        row_views=[
            _build_row(1, "Smoking (%)", ["", "", "", "0.001"]),
            _build_row(2, "Every day", ["858 (15.6)", "801 (15.5)", "57 (17.9)", ""]),
            _build_row(3, "Not at all", ["1207 (22.0)", "1111 (21.5)", "96 (30.1)", ""]),
            _build_row(4, "Some days", ["229 (4.2)", "216 (4.2)", "13 (4.1)", ""]),
            _build_row(5, "Age.cat = greaterthan 60 years (%)", ["1670 (30.4)", "1489 (28.8)", "181 (56.7)", "<0.001"]),
            _build_row(6, "Activity_level (%)", ["", "", "", "0.011"]),
            _build_row(7, "Moderate Activity", ["565 (10.3)", "540 (10.4)", "25 (7.8)", ""]),
            _build_row(8, "None", ["4641 (84.5)", "4354 (84.2)", "287 (90.0)", ""]),
        ],
        n_rows=9,
        n_cols=5,
        metadata={
            "cleaned_rows": [
                ["Characteristic", "Overall", "Non-RA", "RA", "P-value"],
                ["Smoking (%)", "", "", "", "0.001"],
                ["Every day", "858 (15.6)", "801 (15.5)", "57 (17.9)", ""],
                ["Not at all", "1207 (22.0)", "1111 (21.5)", "96 (30.1)", ""],
                ["Some days", "229 (4.2)", "216 (4.2)", "13 (4.1)", ""],
                ["Age.cat = greaterthan 60 years (%)", "1670 (30.4)", "1489 (28.8)", "181 (56.7)", "<0.001"],
                ["Activity_level (%)", "", "", "", "0.011"],
                ["Moderate Activity", "565 (10.3)", "540 (10.4)", "25 (7.8)", ""],
                ["None", "4641 (84.5)", "4354 (84.2)", "287 (90.0)", ""],
            ]
        },
    )

    variables = build_defined_variables(table)
    age_indicator = next(variable for variable in variables if variable.row_start == 5)

    assert age_indicator.variable_label == "Age.cat = greaterthan 60 years (%)"
    assert age_indicator.variable_type == "binary"
    assert age_indicator.summary_style_hint == "count_pct"
    assert age_indicator.levels == []


def test_validate_table_definition_rejects_invalid_level_row() -> None:
    """Validation should reject row references that do not exist in the normalized table."""
    table = NormalizedTable(
        table_id="tbl-bad",
        header_rows=[0],
        body_rows=[1],
        row_views=[_build_row(1, "Age, years", ["52.3 (14.1)"])],
        n_rows=2,
        n_cols=2,
        metadata={"cleaned_rows": [["Characteristic", "Overall"], ["Age, years", "52.3 (14.1)"]]},
    )
    definition = TableDefinition.model_validate(
        {
            "table_id": "tbl-bad",
            "column_definition": {"columns": [{"col_idx": 1, "column_name": "Overall", "column_label": "Overall"}]},
            "variables": [
                {
                    "variable_name": "Sex",
                    "variable_label": "Sex",
                    "row_start": 1,
                    "row_end": 1,
                    "levels": [{"level_name": "Male", "level_label": "Male", "row_idx": 3}],
                }
            ],
        }
    )

    with pytest.raises(ValueError):
        validate_table_definition(definition, table)


def test_build_table_definition_infers_general_grouping_structure_from_multirow_headers() -> None:
    """Grouped columns should carry group levels, ordering, and statistic subtypes."""
    table = NormalizedTable(
        table_id="tbl-cobalt",
        title="Baseline characteristics",
        caption="Participant characteristics",
        header_rows=[0, 1],
        body_rows=[2],
        row_views=[_build_row(2, "Age, years", ["52.3 (14.1)", "50.4 (13.5)", "51.1 (12.8)", "0.03", "0.01"])],
        n_rows=3,
        n_cols=6,
        metadata={
            "cleaned_rows": [
                ["Characteristic", "", "Cobalt quartile", "Cobalt quartile", "", ""],
                ["", "Overall", "Q1", "Q2", "P-value", "P for trend"],
                ["Age, years", "52.3 (14.1)", "50.4 (13.5)", "51.1 (12.8)", "0.03", "0.01"],
            ]
        },
    )

    definition = build_table_definition(table)

    assert definition.column_definition.grouping_label == "Cobalt quartile"
    assert definition.column_definition.grouping_name == "Cobalt quartile"
    assert definition.column_definition.group_count == 2
    assert [column.inferred_role for column in definition.column_definition.columns] == [
        "overall",
        "group",
        "group",
        "p_value",
        "p_value",
    ]
    assert [column.group_level_label for column in definition.column_definition.columns[:3]] == [None, "Q1", "Q2"]
    assert [column.group_order for column in definition.column_definition.columns[:3]] == [None, 1, 2]
    assert [column.column_label for column in definition.column_definition.columns[:3]] == ["Overall", "Q1", "Q2"]
    assert definition.column_definition.columns[1].header_path == ["Cobalt quartile", "Q1"]
    assert [
        (span.header_level, span.col_start, span.col_end, span.label, span.source)
        for span in definition.column_definition.header_spans[:5]
    ] == [
        (0, 2, 3, "Cobalt quartile", "group"),
        (1, 0, 0, "Characteristic", "leaf"),
        (1, 1, 1, "Overall", "leaf"),
        (1, 2, 2, "Q1", "leaf"),
        (1, 3, 3, "Q2", "leaf"),
    ]
    assert definition.column_definition.columns[3].statistic_subtype == "p_value"
    assert definition.column_definition.columns[4].statistic_subtype == "p_trend"


def test_build_table_definition_supports_grouped_levels_without_known_grouping_variable() -> None:
    """Grouped columns should still be represented when the grouping variable is unclear."""
    table = NormalizedTable(
        table_id="tbl-smoking",
        header_rows=[0],
        body_rows=[1],
        row_views=[_build_row(1, "Body mass index, kg/m2", ["26.1 (5.3)", "24.3 (4.9)", "27.8 (5.8)"])],
        n_rows=2,
        n_cols=4,
        metadata={
            "cleaned_rows": [
                ["Characteristic", "Overall", "Never", "Current"],
                ["Body mass index, kg/m2", "26.1 (5.3)", "24.3 (4.9)", "27.8 (5.8)"],
            ]
        },
    )

    definition = build_table_definition(table)

    assert definition.column_definition.grouping_label is None
    assert definition.column_definition.group_count == 2
    assert [column.inferred_role for column in definition.column_definition.columns] == ["overall", "group", "group"]
    assert [column.group_level_label for column in definition.column_definition.columns] == [None, "Never", "Current"]


def test_build_table_definition_uses_label_column_header_as_grouping_fallback() -> None:
    """When grouped columns have distinct upper labels, the label-column header can define the grouping variable."""
    table = NormalizedTable(
        table_id="tbl-cobalt-repaired",
        header_rows=[0, 1],
        body_rows=[2],
        row_views=[_build_row(2, "Age (yrs), mean±SD", ["60.3±12.0", "58.1±11.2", "60.0±11.4", "61.4±11.6", "<.001"])],
        n_rows=3,
        n_cols=7,
        metadata={
            "cleaned_rows": [
                ["", "", "Q1", "Q2", "Q3", "Q4", "P value"],
                ["Cobalt quartiles (mg/l)", "All", "<=0.12", "0.13-0.14", "0.15-0.18", ">=0.19", "P for trend"],
                ["Age (yrs), mean±SD", "60.3±12.0", "58.1±11.2", "60.0±11.4", "61.4±11.6", "61.7±13.2", "<.001"],
            ]
        },
    )

    definition = build_table_definition(table)

    assert definition.column_definition.grouping_label == "Cobalt quartiles (mg/l)"
    assert definition.column_definition.group_count == 4
    assert [column.group_level_label for column in definition.column_definition.columns] == [
        None,
        "Q1",
        "Q2",
        "Q3",
        "Q4",
        None,
    ]
    assert definition.column_definition.columns[-1].statistic_subtype == "p_trend"
