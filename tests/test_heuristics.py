"""Focused tests for deterministic heuristic parsing."""

from __future__ import annotations

from table1_parser.heuristics.column_role_detector import detect_column_roles
from table1_parser.heuristics.level_detector import is_common_level_label, is_likely_level_row
from table1_parser.heuristics.models import RowClassification
from table1_parser.heuristics.row_classifier import classify_rows, indentation_is_informative
from table1_parser.heuristics.value_pattern_detector import detect_value_pattern
from table1_parser.heuristics.variable_grouper import group_variable_blocks
from table1_parser.schemas import NormalizedTable, RowView


def _build_row(
    row_idx: int,
    first_cell_raw: str,
    trailing: list[str],
    indent_level: int | None = None,
) -> RowView:
    """Create a compact RowView for heuristic tests."""
    raw_cells = [first_cell_raw, *trailing]
    return RowView(
        row_idx=row_idx,
        raw_cells=raw_cells,
        first_cell_raw=first_cell_raw,
        first_cell_normalized=first_cell_raw,
        first_cell_alpha_only="".join(ch if ch.isalpha() or ch.isspace() else " " for ch in first_cell_raw).split() and " ".join("".join(ch if ch.isalpha() or ch.isspace() else " " for ch in first_cell_raw).split()) or "",
        nonempty_cell_count=sum(bool(cell) for cell in raw_cells),
        numeric_cell_count=sum(any(char.isdigit() for char in cell) for cell in raw_cells),
        has_trailing_values=any(bool(cell) for cell in trailing),
        indent_level=indent_level,
        likely_role=None,
    )


def test_row_classifier_handles_required_examples() -> None:
    """Row classification should cover continuous rows, parents, levels, and sections."""
    table = NormalizedTable(
        table_id="tbl-heuristics",
        header_rows=[0],
        body_rows=[1, 2, 3, 4, 5, 6, 7, 8, 9],
        row_views=[
            _build_row(1, "Age, years", ["52.3 (14.1)", "51.2 (13.0)"]),
            _build_row(2, "BMI, kg/m2", ["28.4 (6.1)", "27.0 (5.8)"]),
            _build_row(3, "Sex", []),
            _build_row(4, "Male", ["412 (48.2)", "201 (44.0)"]),
            _build_row(5, "Female", ["442 (51.8)", "255 (56.0)"]),
            _build_row(6, "Education", ["0.120"]),
            _build_row(7, "<HS", ["50 (10.2)", "33 (12.1)"]),
            _build_row(8, "High school", ["200 (40.8)", "101 (37.1)"]),
            _build_row(9, ">High school", ["240 (49.0)", "139 (50.8)"]),
        ],
        n_rows=10,
        n_cols=3,
    )

    classifications = {item.row_idx: item.classification for item in classify_rows(table)}

    assert classifications[1] == "continuous_variable_row"
    assert classifications[2] == "continuous_variable_row"
    assert classifications[3] == "variable_header"
    assert classifications[4] == "level_row"
    assert classifications[5] == "level_row"
    assert classifications[6] == "variable_header"
    assert classifications[7] == "level_row"
    assert classifications[8] == "level_row"
    assert classifications[9] == "level_row"


def test_row_classifier_keeps_negative_cases_unknown_or_section_header() -> None:
    """Negative examples should not be forced into variable or level classes."""
    table = NormalizedTable(
        table_id="tbl-negative",
        header_rows=[0],
        body_rows=[1, 2],
        row_views=[
            _build_row(1, "Baseline characteristics", []),
            _build_row(2, "Random note", ["see text"]),
        ],
        n_rows=3,
        n_cols=2,
    )

    classifications = {item.row_idx: item.classification for item in classify_rows(table)}

    assert classifications[1] == "section_header"
    assert classifications[2] == "unknown"


def test_row_with_n_percent_and_multiple_children_is_variable_header() -> None:
    """Categorical parent cues plus child levels should force a parent classification."""
    table = NormalizedTable(
        table_id="tbl-n-percent",
        header_rows=[0],
        body_rows=[1, 2, 3],
        row_views=[
            _build_row(1, "Education, n (%)", ["0.120"]),
            _build_row(2, "<HS", ["50 (10.2)", "33 (12.1)"]),
            _build_row(3, "High school", ["200 (40.8)", "101 (37.1)"]),
        ],
        n_rows=4,
        n_cols=3,
    )

    classifications = {item.row_idx: item.classification for item in classify_rows(table)}

    assert classifications[1] == "variable_header"
    assert classifications[2] == "level_row"
    assert classifications[3] == "level_row"


def test_stats_only_parent_rows_do_not_chain_as_levels() -> None:
    """Rows populated only in statistic columns should start new variables, not continue levels."""
    table = NormalizedTable(
        table_id="tbl-stats-only-parent",
        header_rows=[0],
        body_rows=[1, 2, 3, 4, 5, 6],
        row_views=[
            _build_row(1, "Elevated TGs, n (%)", ["", "", "", "", "<.001", ".018"]),
            _build_row(2, "Yes", ["371 (31.4%)", "363 (34.3%)", "522 (36.2%)", "335 (26.0%)", "", ""]),
            _build_row(3, "No", ["811 (68.6%)", "694 (65.7%)", "919 (63.8%)", "952 (74.0%)", "", ""]),
            _build_row(4, "Antihypertensive drugs", ["", "", "", "", ".021", ".034"]),
            _build_row(5, "Yes", ["732 (37.9%)", "571 (40.3%)", "769 (42.9%)", "699 (40.5%)", "", ""]),
            _build_row(6, "No", ["1199 (62.1%)", "847 (59.7%)", "1023 (57.1%)", "1026 (59.5%)", "", ""]),
        ],
        n_rows=7,
        n_cols=7,
        metadata={
            "cleaned_rows": [
                ["Variable", "Q1", "Q2", "Q3", "Q4", "P value", "P for trend"],
                ["Elevated TGs, n (%)", "", "", "", "", "<.001", ".018"],
                ["Yes", "371 (31.4%)", "363 (34.3%)", "522 (36.2%)", "335 (26.0%)", "", ""],
                ["No", "811 (68.6%)", "694 (65.7%)", "919 (63.8%)", "952 (74.0%)", "", ""],
                ["Antihypertensive drugs", "", "", "", "", ".021", ".034"],
                ["Yes", "732 (37.9%)", "571 (40.3%)", "769 (42.9%)", "699 (40.5%)", "", ""],
                ["No", "1199 (62.1%)", "847 (59.7%)", "1023 (57.1%)", "1026 (59.5%)", "", ""],
            ]
        },
    )

    classifications = {item.row_idx: item.classification for item in classify_rows(table)}
    blocks = group_variable_blocks(table)

    assert classifications[1] == "variable_header"
    assert classifications[2] == "level_row"
    assert classifications[3] == "level_row"
    assert classifications[4] == "variable_header"
    assert classifications[5] == "level_row"
    assert classifications[6] == "level_row"
    assert len(blocks) == 2
    assert blocks[0].level_row_indices == [2, 3]
    assert blocks[1].level_row_indices == [5, 6]


def test_symbol_only_parent_row_starts_new_categorical_block() -> None:
    """A parent row with only significance markers should own the following count-like levels."""
    table = NormalizedTable(
        table_id="tbl-symbol-parent",
        header_rows=[0],
        body_rows=[1, 2, 3, 4, 5, 6],
        row_views=[
            _build_row(1, "Education level", ["", "", "†", ""], indent_level=0),
            _build_row(2, "Less Than 9th Grade", ["1287(16.25%)", "929(15.46%)", "358(18.73%)", "106(18.12%)"], indent_level=8),
            _build_row(3, "College Graduate or above", ["1526(19.27%)", "1256(20.90%)", "270(14.13%)", "77(13.16%)"], indent_level=8),
            _build_row(4, "Ethnicity", ["", "", "‡", "‡"], indent_level=0),
            _build_row(5, "Mexican American", ["1256(15.86%)", "1095(18.22%)", "161(8.42%)", "34(5.81%)"], indent_level=8),
            _build_row(6, "Non-Hispanic White", ["3961(50.01%)", "2786(46.36%)", "1175(61.49%)", "372(63.59%)"], indent_level=8),
        ],
        n_rows=7,
        n_cols=5,
    )

    classifications = {item.row_idx: item.classification for item in classify_rows(table)}
    blocks = group_variable_blocks(table)

    assert classifications[4] == "variable_header"
    assert classifications[5] == "level_row"
    assert classifications[6] == "level_row"
    ethnicity = next(block for block in blocks if block.variable_label == "Ethnicity")
    assert ethnicity.level_row_indices == [5, 6]


def test_split_parent_and_level_descriptor_cells_still_group_levels() -> None:
    """A split parent label and one split level descriptor cell should not fragment a block."""
    table = NormalizedTable(
        table_id="tbl-split-parent-and-level",
        header_rows=[0],
        body_rows=[1, 2, 3, 4, 5, 6, 7],
        row_views=[
            _build_row(1, "Family income-to-poverty ratio,", ["", "n (%)", "", "", "", ""], indent_level=0),
            _build_row(2, "Low income", ["(<=1.85)", "1998 (35.61)", "821 (45.23)", "1054 (32.60)", "123 (21.85)", "<0.01"], indent_level=0),
            _build_row(3, "High income (>1.85)", ["", "3613 (64.39)", "994 (54.77)", "2179 (67.40)", "440 (78.15)", ""], indent_level=0),
            _build_row(4, "Smoking", ["status, n (%)", "", "", "", "", ""], indent_level=0),
            _build_row(5, "No smoking", ["", "2881 (51.35)", "396 (21.82)", "1991 (61.58)", "494 (87.74)", "<0.01"], indent_level=0),
            _build_row(6, "Former smoking", ["", "1583 (28.21)", "772 (42.53)", "770 (23.82)", "41 (7.28)", ""], indent_level=0),
            _build_row(7, "Current smoking", ["", "1147 (20.44)", "647 (35.65)", "472 (14.60)", "28 (4.97)", ""], indent_level=0),
        ],
        n_rows=8,
        n_cols=7,
        metadata={
            "cleaned_rows": [
                ["Characteristic", "", "Overall", "Low", "Medium", "High", "P-value"],
                ["Family income-to-poverty ratio,", "", "n (%)", "", "", "", ""],
                ["Low income", "(<=1.85)", "1998 (35.61)", "821 (45.23)", "1054 (32.60)", "123 (21.85)", "<0.01"],
                ["High income (>1.85)", "", "3613 (64.39)", "994 (54.77)", "2179 (67.40)", "440 (78.15)", ""],
                ["Smoking", "status, n (%)", "", "", "", "", ""],
                ["No smoking", "", "2881 (51.35)", "396 (21.82)", "1991 (61.58)", "494 (87.74)", "<0.01"],
                ["Former smoking", "", "1583 (28.21)", "772 (42.53)", "770 (23.82)", "41 (7.28)", ""],
                ["Current smoking", "", "1147 (20.44)", "647 (35.65)", "472 (14.60)", "28 (4.97)", ""],
            ]
        },
    )

    classifications = {item.row_idx: item.classification for item in classify_rows(table)}
    blocks = group_variable_blocks(table)

    assert classifications[1] == "variable_header"
    assert classifications[2] == "level_row"
    assert classifications[3] == "level_row"
    assert classifications[4] == "variable_header"
    assert classifications[5] == "level_row"
    assert classifications[6] == "level_row"
    assert classifications[7] == "level_row"
    income = next(block for block in blocks if block.variable_label == "Family income-to-poverty ratio,")
    smoking = next(block for block in blocks if block.variable_label == "Smoking")
    assert income.level_row_indices == [2, 3]
    assert smoking.level_row_indices == [5, 6, 7]


def test_mean_sd_row_without_children_stays_continuous() -> None:
    """Rows with continuous cues and no child levels should remain one-line continuous variables."""
    table = NormalizedTable(
        table_id="tbl-mean-sd",
        header_rows=[0],
        body_rows=[1],
        row_views=[_build_row(1, "Age, mean (SD)", ["52.3 (14.1)", "51.2 (13.0)"])],
        n_rows=2,
        n_cols=3,
    )

    classifications = classify_rows(table)

    assert classifications[0].classification == "continuous_variable_row"
    blocks = group_variable_blocks(table, classifications=classifications)
    assert len(blocks) == 1
    assert blocks[0].variable_kind == "continuous"
    assert blocks[0].level_row_indices == []


def test_adjacent_threshold_binary_rows_form_one_level_block() -> None:
    """Complementary threshold rows should group structurally without a special label list."""
    table = NormalizedTable(
        table_id="tbl-threshold-binary-pair",
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

    blocks = group_variable_blocks(table)

    assert [(block.variable_label, block.variable_kind, block.level_row_indices) for block in blocks] == [
        ("Age, years, mean(SD)", "continuous", []),
        ("Age category", "binary", [2, 3]),
        ("Weight, kg, mean(SD)", "continuous", []),
    ]


def test_parent_with_multiple_plausible_levels_is_upgraded_to_variable_header() -> None:
    """Forward lookahead should upgrade a would-be continuous parent into a categorical header."""
    table = NormalizedTable(
        table_id="tbl-lookahead",
        header_rows=[0],
        body_rows=[1, 2, 3],
        row_views=[
            _build_row(1, "Family poverty-income ratio", ["0.210"]),
            _build_row(2, "<1.30", ["100 (20.0)", "50 (18.0)"]),
            _build_row(3, ">=1.30", ["400 (80.0)", "230 (82.0)"]),
        ],
        n_rows=4,
        n_cols=3,
    )

    classifications = {item.row_idx: item.classification for item in classify_rows(table)}

    assert classifications[1] == "variable_header"
    assert classifications[2] == "level_row"
    assert classifications[3] == "level_row"


def test_orphan_count_rows_do_not_attach_to_continuous_variables() -> None:
    """Grouping must keep explicit continuous rows separate from later count rows."""
    table = NormalizedTable(
        table_id="tbl-group-upgrade",
        header_rows=[0],
        body_rows=[1, 2, 3],
        row_views=[
            _build_row(1, "BMI, mean ± SD", ["28.4 (6.1)", "27.0 (5.8)"]),
            _build_row(2, "Male", ["412 (48.2)", "201 (44.0)"]),
            _build_row(3, "Female", ["442 (51.8)", "255 (56.0)"]),
        ],
        n_rows=4,
        n_cols=3,
    )

    classifications = {item.row_idx: item.classification for item in classify_rows(table)}
    blocks = group_variable_blocks(table)

    assert classifications[1] == "continuous_variable_row"
    assert classifications[2] == "binary_variable_row"
    assert classifications[3] == "binary_variable_row"
    assert len(blocks) == 3
    assert blocks[0].variable_label == "BMI, mean ± SD"
    assert blocks[0].variable_kind == "continuous"
    assert blocks[0].level_row_indices == []
    assert blocks[1].variable_label == "Male"
    assert blocks[1].variable_kind == "binary"
    assert blocks[2].variable_label == "Female"
    assert blocks[2].variable_kind == "binary"


def test_unknown_rows_do_not_force_impossible_grouping() -> None:
    """Unknown rows may be skipped without attaching levels to a continuous variable."""
    table = NormalizedTable(
        table_id="tbl-unknown-layout",
        header_rows=[0],
        body_rows=[1, 2, 3, 4],
        row_views=[
            _build_row(1, "Age, years", ["52.3 (14.1)", "51.2 (13.0)"]),
            _build_row(2, "Random note", ["see text"]),
            _build_row(3, "Male", ["412 (48.2)", "201 (44.0)"]),
            _build_row(4, "Female", ["442 (51.8)", "255 (56.0)"]),
        ],
        n_rows=5,
        n_cols=3,
    )

    classifications = {item.row_idx: item.classification for item in classify_rows(table)}
    blocks = group_variable_blocks(table)

    assert classifications[1] == "continuous_variable_row"
    assert classifications[2] == "unknown"
    assert len(blocks) == 3
    assert blocks[0].variable_label == "Age, years"
    assert blocks[0].level_row_indices == []
    assert blocks[1].variable_label == "Male"
    assert blocks[1].variable_kind == "binary"
    assert blocks[2].variable_label == "Female"
    assert blocks[2].variable_kind == "binary"


def test_number_with_integer_values_forms_one_row_variable_block() -> None:
    """Short scalar-count rows should behave as one-row variables."""
    table = NormalizedTable(
        table_id="tbl-number",
        header_rows=[0],
        body_rows=[1],
        row_views=[_build_row(1, "Number", ["123", "456"])],
        n_rows=2,
        n_cols=3,
    )

    classifications = classify_rows(table)
    blocks = group_variable_blocks(table, classifications=classifications)

    assert classifications[0].classification == "continuous_variable_row"
    assert len(blocks) == 1
    assert blocks[0].variable_label == "Number"
    assert blocks[0].variable_kind == "continuous"
    assert blocks[0].level_row_indices == []


def test_lowercase_n_with_integer_values_forms_one_row_variable_block() -> None:
    """A compact n row with integer counts should be treated as a one-row variable."""
    table = NormalizedTable(
        table_id="tbl-lower-n",
        header_rows=[0],
        body_rows=[1],
        row_views=[_build_row(1, "n", ["5490", "5171", "319"])],
        n_rows=2,
        n_cols=4,
    )

    classifications = classify_rows(table)
    blocks = group_variable_blocks(table, classifications=classifications)

    assert classifications[0].classification == "continuous_variable_row"
    assert len(blocks) == 1
    assert blocks[0].variable_label == "n"
    assert blocks[0].level_row_indices == []


def test_uppercase_n_with_integer_values_forms_one_row_variable_block() -> None:
    """An uppercase N row with integer counts should be treated as a one-row variable."""
    table = NormalizedTable(
        table_id="tbl-upper-n",
        header_rows=[0],
        body_rows=[1],
        row_views=[_build_row(1, "N", ["5490", "5171", "319"])],
        n_rows=2,
        n_cols=4,
    )

    classifications = classify_rows(table)
    blocks = group_variable_blocks(table, classifications=classifications)

    assert classifications[0].classification == "continuous_variable_row"
    assert len(blocks) == 1
    assert blocks[0].variable_label == "N"
    assert blocks[0].level_row_indices == []


def test_gender_female_percent_row_becomes_one_row_summary_block() -> None:
    """Inline female summary rows should behave as complete one-row variables when they own no levels."""
    table = NormalizedTable(
        table_id="tbl-gender-female",
        header_rows=[0],
        body_rows=[1, 2],
        row_views=[
            _build_row(1, "Gender = Female (%)", ["2793 (50.9)", "2603 (50.3)", "190 (59.6)", "0.002"]),
            _build_row(2, "Age, years", ["48.35 (17.47)", "47.60 (17.42)", "60.51 (13.27)", "<0.001"]),
        ],
        n_rows=3,
        n_cols=5,
    )

    classifications = classify_rows(table)
    blocks = group_variable_blocks(table, classifications=classifications)

    assert classifications[0].classification == "binary_variable_row"
    assert blocks[0].variable_label == "Gender = Female (%)"
    assert blocks[0].variable_kind == "binary"
    assert blocks[0].row_start == blocks[0].row_end == 1


def test_female_percent_row_becomes_one_row_summary_block() -> None:
    """Standalone female-percent rows should behave as complete one-row variables when isolated."""
    table = NormalizedTable(
        table_id="tbl-female-only",
        header_rows=[0],
        body_rows=[1, 2],
        row_views=[
            _build_row(1, "Female (%)", ["2793 (50.9)", "2603 (50.3)", "190 (59.6)", "0.002"]),
            _build_row(2, "BMI, mean ± SD", ["28.4 (6.1)", "27.0 (5.8)", "29.9 (7.1)", "0.040"]),
        ],
        n_rows=3,
        n_cols=5,
    )

    classifications = classify_rows(table)
    blocks = group_variable_blocks(table, classifications=classifications)

    assert classifications[0].classification == "binary_variable_row"
    assert blocks[0].variable_label == "Female (%)"
    assert blocks[0].variable_kind == "binary"
    assert blocks[0].row_start == blocks[0].row_end == 1


def test_binary_row_with_integer_counts_only_becomes_one_row_summary_block() -> None:
    """Standalone indicator rows with integer counts only should still be binary variables."""
    table = NormalizedTable(
        table_id="tbl-female-counts-only",
        header_rows=[0],
        body_rows=[1, 2],
        row_views=[
            _build_row(1, "Female", ["2793", "2603", "190", "0.002"]),
            _build_row(2, "BMI, mean ± SD", ["28.4 (6.1)", "27.0 (5.8)", "29.9 (7.1)", "0.040"]),
        ],
        n_rows=3,
        n_cols=5,
    )

    classifications = classify_rows(table)
    blocks = group_variable_blocks(table, classifications=classifications)

    assert classifications[0].classification == "binary_variable_row"
    assert blocks[0].variable_label == "Female"
    assert blocks[0].variable_kind == "binary"
    assert blocks[0].row_start == blocks[0].row_end == 1


def test_true_categorical_parent_with_child_levels_is_not_collapsed_to_one_row_summary() -> None:
    """A real parent-plus-level block should stay categorical, even when one child mentions Female."""
    table = NormalizedTable(
        table_id="tbl-sex-parent",
        header_rows=[0],
        body_rows=[1, 2, 3],
        row_views=[
            _build_row(1, "Sex", []),
            _build_row(2, "Male (%)", ["412 (48.2)", "201 (44.0)"]),
            _build_row(3, "Female (%)", ["442 (51.8)", "255 (56.0)"]),
        ],
        n_rows=4,
        n_cols=3,
    )

    classifications = {item.row_idx: item.classification for item in classify_rows(table)}
    blocks = group_variable_blocks(table)

    assert classifications[1] == "variable_header"
    assert classifications[2] == "level_row"
    assert classifications[3] == "level_row"
    assert len(blocks) == 1
    assert blocks[0].variable_kind == "categorical"
    assert blocks[0].level_row_indices == [2, 3]


def test_hispanic_mexican_is_level_row_after_categorical_parent() -> None:
    """Slash-separated category labels should still be treated as level rows."""
    table = NormalizedTable(
        table_id="tbl-slash-level",
        header_rows=[0],
        body_rows=[1, 2, 3, 4],
        row_views=[
            _build_row(1, "Ethnicity", []),
            _build_row(2, "White", ["220 (55.0)", "110 (56.0)"]),
            _build_row(3, "Hispanic/Mexican", ["120 (30.0)", "55 (28.0)"]),
            _build_row(4, "Other", ["40 (10.0)", "18 (9.0)"]),
        ],
        n_rows=5,
        n_cols=3,
    )

    classifications = {item.row_idx: item.classification for item in classify_rows(table)}

    assert classifications[1] == "variable_header"
    assert classifications[2] == "level_row"
    assert classifications[3] == "level_row"
    assert classifications[4] == "level_row"


def test_indented_row_gets_stronger_level_signal_below_parent() -> None:
    """Indentation should strengthen, but not require, level-row interpretation."""
    table = NormalizedTable(
        table_id="tbl-indent-level",
        header_rows=[0],
        body_rows=[1, 2, 3],
        row_views=[
            _build_row(1, "Ethnicity", [], indent_level=0),
            _build_row(2, "Hispanic/Mexican", ["120 (30.0)", "55 (28.0)"], indent_level=4),
            _build_row(3, "Other", ["40 (10.0)", "18 (9.0)"], indent_level=4),
        ],
        n_rows=4,
        n_cols=3,
    )

    classifications = classify_rows(table)

    assert classifications[0].classification == "variable_header"
    assert classifications[1].classification == "level_row"
    assert classifications[1].confidence > 0.9


def test_flush_left_table_marks_indentation_uninformative_but_still_classifies_levels() -> None:
    """Flush-left tables should ignore indentation while preserving non-indentation level logic."""
    table = NormalizedTable(
        table_id="tbl-indent-flat",
        header_rows=[0],
        body_rows=[1, 2, 3],
        row_views=[
            _build_row(1, "Ethnicity", [], indent_level=0),
            _build_row(2, "White", ["220 (55.0)", "110 (56.0)"], indent_level=0),
            _build_row(3, "Hispanic/Mexican", ["120 (30.0)", "55 (28.0)"], indent_level=0),
        ],
        n_rows=4,
        n_cols=3,
    )

    classifications = {item.row_idx: item for item in classify_rows(table)}

    assert indentation_is_informative(table) is False
    assert classifications[1].classification == "variable_header"
    assert classifications[2].classification == "level_row"
    assert classifications[3].classification == "level_row"
    assert classifications[2].confidence == 0.78


def test_more_indented_following_rows_strengthen_parent_as_variable_header() -> None:
    """Multiple more-indented child rows should support a categorical parent interpretation."""
    table = NormalizedTable(
        table_id="tbl-indent-parent",
        header_rows=[0],
        body_rows=[1, 2, 3],
        row_views=[
            _build_row(1, "Group", [], indent_level=0),
            _build_row(2, "Unknown", ["10 (5.0)", "3 (2.0)"], indent_level=3),
            _build_row(3, "Other", ["20 (10.0)", "6 (4.0)"], indent_level=3),
        ],
        n_rows=4,
        n_cols=3,
    )

    classifications = {item.row_idx: item for item in classify_rows(table)}

    assert classifications[1].classification == "variable_header"
    assert classifications[1].confidence >= 0.88
    assert classifications[2].classification == "level_row"
    assert classifications[3].classification == "level_row"


def test_indented_numeric_matrix_rows_group_under_categorical_parent() -> None:
    """Indented numeric-matrix rows should behave as levels under a blank categorical parent."""
    table = NormalizedTable(
        table_id="tbl-indented-numeric-matrix",
        header_rows=[0, 1],
        body_rows=[2, 3, 4, 5, 6, 7, 8, 9, 10],
        row_views=[
            _build_row(2, "Age (mean: 24 teeth)", [], indent_level=0),
            _build_row(3, "30 to 34 years", ["72.3", "1.8", "32.6", "2.3"], indent_level=9),
            _build_row(4, "35 to 49 years", ["85.7", "1.1", "51.8", "2.2"], indent_level=9),
            _build_row(5, "Sex", [], indent_level=0),
            _build_row(6, "Males", ["92.0", "0.9", "68.4", "1.6"], indent_level=9),
            _build_row(7, "Females", ["84.4", "1.1", "53.6", "1.9"], indent_level=9),
            _build_row(8, "Education", [], indent_level=0),
            _build_row(9, "Less than high school", ["88.7", "1.7", "58.2", "2.0"], indent_level=9),
            _build_row(10, "High school/GED", ["86.4", "1.5", "55.0", "2.1"], indent_level=9),
        ],
        n_rows=11,
        n_cols=5,
        metadata={"indentation_informative": True},
    )

    classifications = {item.row_idx: item.classification for item in classify_rows(table)}
    blocks = group_variable_blocks(table)

    assert classifications[2] == "variable_header"
    assert classifications[3] == "level_row"
    assert classifications[4] == "level_row"
    assert classifications[5] == "variable_header"
    assert classifications[6] == "level_row"
    assert classifications[7] == "level_row"
    assert classifications[8] == "variable_header"
    assert classifications[9] == "level_row"
    assert classifications[10] == "level_row"
    assert [(block.variable_label, block.variable_kind, block.level_row_indices) for block in blocks] == [
        ("Age (mean: 24 teeth)", "categorical", [3, 4]),
        ("Sex", "categorical", [6, 7]),
        ("Education", "categorical", [9, 10]),
    ]


def test_indented_na_numeric_matrix_row_remains_level_under_parent() -> None:
    """N/A rows inside an indented numeric-matrix block should stay attached as levels."""
    table = NormalizedTable(
        table_id="tbl-indented-na-matrix",
        header_rows=[0],
        body_rows=[1, 2, 3],
        row_views=[
            _build_row(1, "Race/ethnic group", [], indent_level=0),
            _build_row(2, "Hispanic", ["95.0", "0.9", "71.6", "1.6"], indent_level=9),
            _build_row(3, "Non-Hispanic Asian American", ["N/A", "N/A", "N/A", "N/A"], indent_level=9),
        ],
        n_rows=4,
        n_cols=5,
        metadata={"indentation_informative": True},
    )

    classifications = {item.row_idx: item.classification for item in classify_rows(table)}
    blocks = group_variable_blocks(table)

    assert classifications[1] == "variable_header"
    assert classifications[2] == "level_row"
    assert classifications[3] == "level_row"
    assert blocks[0].variable_label == "Race/ethnic group"
    assert blocks[0].level_row_indices == [2, 3]


def test_flush_left_row_does_not_continue_indented_level_block() -> None:
    """Once a block starts with indented levels, a flush-left row should not continue it."""
    table = NormalizedTable(
        table_id="tbl-indent-boundary",
        header_rows=[0],
        body_rows=[1, 2, 3, 4],
        row_views=[
            _build_row(1, "Ethnicity", [], indent_level=0),
            _build_row(2, "White", ["220 (55.0)", "110 (56.0)"], indent_level=4),
            _build_row(3, "Other", ["20 (10.0)", "6 (4.0)"], indent_level=4),
            _build_row(4, "PIR", ["2.4 [1.2, 4.5]", "3.5 [1.7, 5.0]"], indent_level=0),
        ],
        n_rows=5,
        n_cols=3,
    )

    classifications = {item.row_idx: item.classification for item in classify_rows(table)}
    blocks = group_variable_blocks(table)

    assert classifications[1] == "variable_header"
    assert classifications[2] == "level_row"
    assert classifications[3] == "level_row"
    assert classifications[4] != "level_row"
    assert len(blocks) == 1
    assert blocks[0].level_row_indices == [2, 3]
    assert blocks[0].row_end == 3


def test_binary_rows_break_indented_categorical_block_and_form_standalone_blocks() -> None:
    """Indented categorical levels should stop before later top-level count-percent summary rows."""
    table = NormalizedTable(
        table_id="tbl-binary-break",
        header_rows=[0],
        body_rows=[1, 2, 3, 4, 5],
        row_views=[
            _build_row(1, "Alcohol consumption", ["", "", "", "<0.001"], indent_level=0),
            _build_row(2, "Binge drinking", ["1485 (58.0%)", "791 (38.1%)", "549 (23.9%)", ""], indent_level=4),
            _build_row(3, "Non-binge drinking", ["1076 (42.0%)", "1285 (61.9%)", "1748 (76.1%)", ""], indent_level=4),
            _build_row(4, "Healthy diet", ["172 (6.7%)", "1597 (76.9%)", "1540 (67.0%)", "<0.001"], indent_level=0),
            _build_row(5, "Regular physical activity", ["1589 (62.0%)", "1364 (65.7%)", "1864 (81.1%)", "<0.001"], indent_level=0),
        ],
        n_rows=6,
        n_cols=5,
        metadata={
            "cleaned_rows": [
                ["Characteristic", "Low", "Middle", "High", "P-value"],
                ["Alcohol consumption", "", "", "", "<0.001"],
                ["Binge drinking", "1485 (58.0%)", "791 (38.1%)", "549 (23.9%)", ""],
                ["Non-binge drinking", "1076 (42.0%)", "1285 (61.9%)", "1748 (76.1%)", ""],
                ["Healthy diet", "172 (6.7%)", "1597 (76.9%)", "1540 (67.0%)", "<0.001"],
                ["Regular physical activity", "1589 (62.0%)", "1364 (65.7%)", "1864 (81.1%)", "<0.001"],
            ]
        },
    )

    classifications = {item.row_idx: item.classification for item in classify_rows(table)}
    blocks = group_variable_blocks(table)

    assert classifications[1] == "variable_header"
    assert classifications[2] == "level_row"
    assert classifications[3] == "level_row"
    assert classifications[4] == "binary_variable_row"
    assert classifications[5] == "binary_variable_row"
    assert len(blocks) == 3
    assert blocks[0].variable_label == "Alcohol consumption"
    assert blocks[0].level_row_indices == [2, 3]
    assert blocks[1].variable_label == "Healthy diet"
    assert blocks[1].variable_kind == "binary"
    assert blocks[2].variable_label == "Regular physical activity"
    assert blocks[2].variable_kind == "binary"


def test_smoking_levels_remain_categorical_not_binary_rows() -> None:
    """Canonical flush-left smoking levels should stay attached to their parent block."""
    table = NormalizedTable(
        table_id="tbl-smoking",
        header_rows=[0],
        body_rows=[1, 2, 3, 4],
        row_views=[
            _build_row(1, "Smoking", ["", "", "", "<0.001"]),
            _build_row(2, "Never", ["1281 (50.0%)", "1489 (71.7%)", "1755 (76.4%)", ""]),
            _build_row(3, "Former", ["407 (15.9%)", "519 (25.0%)", "542 (23.6%)", ""]),
            _build_row(4, "Current", ["873 (34.1%)", "68 (3.3%)", "0 (0%)", ""]),
        ],
        n_rows=5,
        n_cols=5,
        metadata={
            "cleaned_rows": [
                ["Characteristic", "Low", "Middle", "High", "P-value"],
                ["Smoking", "", "", "", "<0.001"],
                ["Never", "1281 (50.0%)", "1489 (71.7%)", "1755 (76.4%)", ""],
                ["Former", "407 (15.9%)", "519 (25.0%)", "542 (23.6%)", ""],
                ["Current", "873 (34.1%)", "68 (3.3%)", "0 (0%)", ""],
            ]
        },
    )

    classifications = {item.row_idx: item.classification for item in classify_rows(table)}
    blocks = group_variable_blocks(table)

    assert classifications[1] == "variable_header"
    assert classifications[2] == "level_row"
    assert classifications[3] == "level_row"
    assert classifications[4] == "level_row"
    assert len(blocks) == 1
    assert blocks[0].variable_kind == "categorical"
    assert blocks[0].level_row_indices == [2, 3, 4]


def test_indicator_style_cat_row_breaks_flush_left_categorical_block() -> None:
    """Explicit `.cat = ...` labels should start a one-row binary variable after flush-left levels."""
    table = NormalizedTable(
        table_id="tbl-age-cat-indicator",
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

    classifications = {item.row_idx: item.classification for item in classify_rows(table)}
    blocks = group_variable_blocks(table)

    assert classifications[1] == "variable_header"
    assert classifications[2] == "level_row"
    assert classifications[3] == "level_row"
    assert classifications[4] == "level_row"
    assert classifications[5] == "binary_variable_row"
    assert classifications[6] == "variable_header"
    age_indicator_block = next(block for block in blocks if block.variable_row_idx == 5)
    assert age_indicator_block.variable_kind == "binary"
    assert age_indicator_block.row_start == age_indicator_block.row_end == 5


def test_interval_rows_with_p_values_do_not_form_false_categorical_block() -> None:
    """Top-level interval-summary rows with p-values should stay standalone, not parent-plus-level blocks."""
    table = NormalizedTable(
        table_id="tbl-interval-rows",
        header_rows=[0],
        body_rows=[1, 2, 3, 4, 5, 6],
        row_views=[
            _build_row(1, "Alcohol consumption", ["", "", "", "<0.001"], indent_level=0),
            _build_row(2, "Binge drinking", ["1485 (58.0%)", "791 (38.1%)", "549 (23.9%)", ""], indent_level=4),
            _build_row(3, "Non-binge drinking", ["1076 (42.0%)", "1285 (61.9%)", "1748 (76.1%)", ""], indent_level=4),
            _build_row(4, "LDL-cholesterol (mg/dL)", ["112.0 [90.0, 138.0]", "111.0 [91.0, 132.0]", "112.0 [90.0, 137.0]", "0.584"]),
            _build_row(5, "HDL-cholesterol (mg/dL)", ["49.0 [40.0, 60.0]", "54.0 [44.0, 65.0]", "53.0 [44.0, 65.0]", "<0.001"]),
            _build_row(6, "Triglycerides (mg/dL)", ["119.0[76.5, 186.0]", "110.0 [75.0, 171.0]", "108.0 [72.0, 168.0]", "<0.001"]),
        ],
        n_rows=7,
        n_cols=5,
        metadata={
            "cleaned_rows": [
                ["Characteristic", "Low", "Middle", "High", "P-value"],
                ["Alcohol consumption", "", "", "", "<0.001"],
                ["Binge drinking", "1485 (58.0%)", "791 (38.1%)", "549 (23.9%)", ""],
                ["Non-binge drinking", "1076 (42.0%)", "1285 (61.9%)", "1748 (76.1%)", ""],
                ["LDL-cholesterol (mg/dL)", "112.0 [90.0, 138.0]", "111.0 [91.0, 132.0]", "112.0 [90.0, 137.0]", "0.584"],
                ["HDL-cholesterol (mg/dL)", "49.0 [40.0, 60.0]", "54.0 [44.0, 65.0]", "53.0 [44.0, 65.0]", "<0.001"],
                ["Triglycerides (mg/dL)", "119.0[76.5, 186.0]", "110.0 [75.0, 171.0]", "108.0 [72.0, 168.0]", "<0.001"],
            ]
        },
    )

    classifications = {item.row_idx: item.classification for item in classify_rows(table)}
    blocks = group_variable_blocks(table)

    assert classifications[1] == "variable_header"
    assert classifications[2] == "level_row"
    assert classifications[3] == "level_row"
    assert classifications[4] == "continuous_variable_row"
    assert classifications[5] == "continuous_variable_row"
    assert classifications[6] == "continuous_variable_row"
    assert len(blocks) == 4
    assert blocks[0].variable_label == "Alcohol consumption"
    assert blocks[0].level_row_indices == [2, 3]
    assert blocks[1].variable_label == "LDL-cholesterol (mg/dL)"
    assert blocks[1].variable_kind == "continuous"
    assert blocks[2].variable_label == "HDL-cholesterol (mg/dL)"
    assert blocks[2].variable_kind == "continuous"
    assert blocks[3].variable_label == "Triglycerides (mg/dL)"
    assert blocks[3].variable_kind == "continuous"


def test_clear_indent_differences_mark_indentation_informative() -> None:
    """Repeated meaningful indent shifts should count as informative table-level structure."""
    table = NormalizedTable(
        table_id="tbl-indent-informative",
        header_rows=[0],
        body_rows=[1, 2, 3],
        row_views=[
            _build_row(1, "Group", [], indent_level=0),
            _build_row(2, "Unknown", ["10 (5.0)", "3 (2.0)"], indent_level=3),
            _build_row(3, "Other", ["20 (10.0)", "6 (4.0)"], indent_level=3),
        ],
        n_rows=4,
        n_cols=3,
    )

    assert indentation_is_informative(table) is True


def test_continuous_row_is_not_misclassified_from_whitespace_noise() -> None:
    """Indent-like whitespace alone should not override a one-row continuous summary."""
    table = NormalizedTable(
        table_id="tbl-indent-noise",
        header_rows=[0],
        body_rows=[1],
        row_views=[_build_row(1, "  Age, mean (SD)", ["52.3 (14.1)", "51.2 (13.0)"], indent_level=2)],
        n_rows=2,
        n_cols=3,
    )

    classifications = classify_rows(table)

    assert classifications[0].classification == "continuous_variable_row"


def test_tiny_indent_noise_is_not_treated_as_meaningful_structure() -> None:
    """One-space jitter should not make indentation informative."""
    table = NormalizedTable(
        table_id="tbl-indent-jitter",
        header_rows=[0],
        body_rows=[1, 2, 3],
        row_views=[
            _build_row(1, "Group", [], indent_level=0),
            _build_row(2, "White", ["220 (55.0)", "110 (56.0)"], indent_level=1),
            _build_row(3, "Other", ["20 (10.0)", "6 (4.0)"], indent_level=0),
        ],
        n_rows=4,
        n_cols=3,
    )

    assert indentation_is_informative(table) is False


def test_existing_logic_still_works_without_indentation() -> None:
    """Absent indentation metadata should fall back to the existing structural logic."""
    table = NormalizedTable(
        table_id="tbl-no-indent",
        header_rows=[0],
        body_rows=[1, 2, 3],
        row_views=[
            _build_row(1, "Ethnicity", []),
            _build_row(2, "White", ["220 (55.0)", "110 (56.0)"]),
            _build_row(3, "Hispanic/Mexican", ["120 (30.0)", "55 (28.0)"]),
        ],
        n_rows=4,
        n_cols=3,
    )

    classifications = {item.row_idx: item.classification for item in classify_rows(table)}

    assert classifications[1] == "variable_header"
    assert classifications[2] == "level_row"
    assert classifications[3] == "level_row"


def test_indented_slash_label_can_be_level_row() -> None:
    """Indentation should support slash-containing labels without making it mandatory."""
    table = NormalizedTable(
        table_id="tbl-indent-slash",
        header_rows=[0],
        body_rows=[1, 2, 3],
        row_views=[
            _build_row(1, "Race", [], indent_level=0),
            _build_row(2, "White", ["220 (55.0)", "110 (56.0)"], indent_level=2),
            _build_row(3, "Hispanic/Mexican", ["120 (30.0)", "55 (28.0)"], indent_level=2),
        ],
        n_rows=4,
        n_cols=3,
    )

    classifications = {item.row_idx: item.classification for item in classify_rows(table)}

    assert classifications[1] == "variable_header"
    assert classifications[2] == "level_row"
    assert classifications[3] == "level_row"


def test_indented_level_continuation_tolerates_one_malformed_count_percent_cell() -> None:
    """Indented categorical blocks should not break on one malformed count-percent value."""
    table = NormalizedTable(
        table_id="tbl-indent-malformed-level",
        header_rows=[0],
        body_rows=[1, 2, 3, 4],
        row_views=[
            _build_row(1, "Marital status, n (%)", [], indent_level=0),
            _build_row(2, "Married", ["12,405 (55.2)", "10,346 (55.6)", "2,059 (53.0)"], indent_level=8),
            _build_row(3, "Divorced", ["2,651 (10.3)", "2,109 (9.9)", "542 (12.7)"], indent_level=8),
            _build_row(4, "Never married", ["4,514 (18.4)", "4,040 (19,5)", "474 (11.1)"], indent_level=8),
        ],
        n_rows=5,
        n_cols=4,
        metadata={"indentation_informative": True},
    )

    classifications = {item.row_idx: item.classification for item in classify_rows(table)}

    assert classifications[1] == "variable_header"
    assert classifications[2] == "level_row"
    assert classifications[3] == "level_row"
    assert classifications[4] == "level_row"


def test_other_is_plausible_level_row_after_categorical_parent() -> None:
    """Generic residual category labels should be recognized under a categorical parent."""
    table = NormalizedTable(
        table_id="tbl-other-level",
        header_rows=[0],
        body_rows=[1, 2],
        row_views=[
            _build_row(1, "Group", []),
            _build_row(2, "Other", ["25 (12.5)", "10 (8.0)"]),
        ],
        n_rows=3,
        n_cols=3,
    )

    classifications = {item.row_idx: item.classification for item in classify_rows(table)}

    assert classifications[1] == "variable_header"
    assert classifications[2] == "level_row"


def test_level_detector_required_examples() -> None:
    """Structural comparator-style level cues should be detected conservatively."""
    assert is_common_level_label("Male") is False
    assert is_common_level_label("Female") is False
    assert is_common_level_label("Other") is False
    assert is_common_level_label("<HS") is True
    assert is_common_level_label("High school") is False
    assert is_common_level_label(">High school") is True
    assert is_common_level_label("<= 60 years") is True
    assert is_common_level_label("≥ 60 years") is True
    assert is_common_level_label("Never") is False
    assert is_common_level_label("Former") is False
    assert is_common_level_label("Current") is False
    assert is_common_level_label("Age, years") is False
    assert is_common_level_label("BMI, kg/m2") is False

    assert is_likely_level_row(_build_row(1, "Current", ["50 (20.1)"])) is True
    assert is_likely_level_row(_build_row(2, "Hispanic/Mexican", ["30 (15.0)"])) is True
    assert is_likely_level_row(_build_row(3, "Q1", ["50"])) is True
    assert is_likely_level_row(_build_row(4, "Age, years", ["52.3 (14.1)"])) is False
    assert is_likely_level_row(_build_row(5, "Current", ["52.3 (14.1)"])) is False
    assert is_likely_level_row(_build_row(6, "Q1", ["0.45"])) is False


def test_variable_grouper_builds_continuous_and_categorical_blocks() -> None:
    """Grouping should support one-line continuous rows and parent-plus-level blocks."""
    table = NormalizedTable(
        table_id="tbl-grouping",
        header_rows=[0],
        body_rows=[1, 2, 3, 4, 5, 6, 7],
        row_views=[
            _build_row(1, "Age, years", ["52.3 (14.1)", "51.2 (13.0)"]),
            _build_row(2, "Sex", []),
            _build_row(3, "Male", ["412 (48.2)", "201 (44.0)"]),
            _build_row(4, "Female", ["442 (51.8)", "255 (56.0)"]),
            _build_row(5, "Smoking status", []),
            _build_row(6, "Never", ["150 (30.0)", "80 (32.0)"]),
            _build_row(7, "Former", ["100 (20.0)", "40 (16.0)"]),
        ],
        n_rows=8,
        n_cols=3,
    )

    blocks = group_variable_blocks(table)

    assert len(blocks) == 3
    assert blocks[0].variable_label == "Age, years"
    assert blocks[0].variable_kind == "continuous"
    assert blocks[1].variable_label == "Sex"
    assert blocks[1].level_row_indices == [3, 4]
    assert blocks[2].variable_label == "Smoking status"
    assert blocks[2].level_row_indices == [6, 7]


def test_categorical_parent_with_empty_trailing_cells_groups_levels() -> None:
    """A sparse parent row should own contiguous level rows below it."""
    table = NormalizedTable(
        table_id="tbl-parent-empty",
        header_rows=[0],
        body_rows=[1, 2, 3, 4],
        row_views=[
            _build_row(1, "Education level", []),
            _build_row(2, "<HS", ["50 (10.2)", "33 (12.1)"]),
            _build_row(3, "High school", ["200 (40.8)", "101 (37.1)"]),
            _build_row(4, ">High school", ["240 (49.0)", "139 (50.8)"]),
        ],
        n_rows=5,
        n_cols=3,
    )

    classifications = {item.row_idx: item.classification for item in classify_rows(table)}
    blocks = group_variable_blocks(table)

    assert classifications[1] == "variable_header"
    assert classifications[2] == "level_row"
    assert classifications[3] == "level_row"
    assert classifications[4] == "level_row"
    assert len(blocks) == 1
    assert blocks[0].variable_kind == "categorical"
    assert blocks[0].level_row_indices == [2, 3, 4]


def test_column_role_detector_handles_required_headers() -> None:
    """Column-role detection should classify supported role labels conservatively."""
    table = NormalizedTable(
        table_id="tbl-columns",
        header_rows=[0],
        body_rows=[1],
        row_views=[_build_row(1, "Age, years", ["52.3 (14.1)", "51.2 (13.0)", "<0.001", "0.12"])],
        n_rows=2,
        n_cols=5,
        metadata={
            "cleaned_rows": [
                ["Variable", "Overall", "Cases", "Controls", "P-value"],
            ]
        },
    )

    roles = {item.header_label: item.role for item in detect_column_roles(table)}

    assert roles["Overall"] == "overall"
    assert roles["Cases"] == "group"
    assert roles["Controls"] == "comparison_group"
    assert roles["P-value"] == "p_value"

    smd_table = table.model_copy(
        update={"n_cols": 2, "metadata": {"cleaned_rows": [["Variable", "SMD"]]}}
    )
    smd_roles = detect_column_roles(smd_table)
    assert smd_roles[1].role == "smd"


def test_column_role_detector_handles_split_p_value_headers() -> None:
    """P-value headers split by whitespace or hyphenation should still be recognized."""
    variants = ["P-value", "P value", "p- value", "p-\nvalue", "pvalue", "P for trend", "p-trend"]
    for variant in variants:
        table = NormalizedTable(
            table_id=f"tbl-{variant}",
            header_rows=[0],
            body_rows=[1],
            row_views=[_build_row(1, "Age, years", ["52.3", "51.2", "<0.001"])],
            n_rows=2,
            n_cols=4,
            metadata={"cleaned_rows": [["Variable", "Overall", "Cases", variant]]},
        )

        roles = detect_column_roles(table)

        assert roles[3].role == "p_value"
        assert roles[3].confidence >= 0.94


def test_bare_p_header_requires_rightmost_or_almost_rightmost_position() -> None:
    """A bare p header should not classify as p_value when it is far from the right edge."""
    table = NormalizedTable(
        table_id="tbl-bare-p",
        header_rows=[0],
        body_rows=[1],
        row_views=[_build_row(1, "Age, years", ["52.3", "51.2", "<0.001", "0.12"])],
        n_rows=2,
        n_cols=5,
        metadata={"cleaned_rows": [["Variable", "p", "Overall", "Cases", "Controls"]]},
    )

    roles = detect_column_roles(table)

    assert roles[1].role == "unknown"


def test_split_p_value_header_does_not_break_categorical_levels() -> None:
    """A p-value column rendered as p- value should not split a categorical block."""
    table = NormalizedTable(
        table_id="tbl-split-p-value",
        header_rows=[0],
        body_rows=[1, 2, 3, 4, 5, 6],
        row_views=[
            _build_row(1, "Race, n (%)", ["", "", "", ""]),
            _build_row(2, "Mexican American", ["3,614 (8.7)", "3,075 (8.9)", "539 (7.5)", ""]),
            _build_row(3, "Other Hispanic", ["2,565 (6.1)", "2,197 (6.3)", "368 (5.0)", ""]),
            _build_row(4, "Non-Hispanic white", ["9,643 (66.2)", "7,817 (66.0)", "1,826 (67.0)", "<0.001"]),
            _build_row(5, "Non-Hispanic Black", ["4,987 (10.6)", "4,050 (10.3)", "937 (12.1)", ""]),
            _build_row(6, "Others", ["3,353 (8.4)", "2,889 (8.5)", "464 (7.7)", ""]),
        ],
        n_rows=7,
        n_cols=5,
        metadata={
            "cleaned_rows": [
                ["Characteristics", "Overall", "Non-CKD", "CKD", "p- value"],
                ["Race, n (%)", "", "", "", ""],
                ["Mexican American", "3,614 (8.7)", "3,075 (8.9)", "539 (7.5)", ""],
                ["Other Hispanic", "2,565 (6.1)", "2,197 (6.3)", "368 (5.0)", ""],
                ["Non-Hispanic white", "9,643 (66.2)", "7,817 (66.0)", "1,826 (67.0)", "<0.001"],
                ["Non-Hispanic Black", "4,987 (10.6)", "4,050 (10.3)", "937 (12.1)", ""],
                ["Others", "3,353 (8.4)", "2,889 (8.5)", "464 (7.7)", ""],
            ]
        },
    )

    classifications = {item.row_idx: item.classification for item in classify_rows(table)}
    blocks = group_variable_blocks(table)

    assert classifications[4] == "level_row"
    assert len(blocks) == 1
    assert blocks[0].variable_label == "Race, n (%)"
    assert blocks[0].level_row_indices == [2, 3, 4, 5, 6]


def test_value_pattern_detector_handles_required_examples_and_negatives() -> None:
    """Value-pattern detection should classify the required examples conservatively."""
    assert detect_value_pattern("412 (48.2)").pattern == "count_pct"
    assert detect_value_pattern("5,490").pattern == "n_only"
    assert detect_value_pattern("52.3 (14.1)").pattern == "mean_sd"
    assert detect_value_pattern("43.2 (35.0, 57.1)").pattern == "median_iqr"
    assert detect_value_pattern("<0.001").pattern == "p_value"
    assert detect_value_pattern("＜0.001").pattern == "p_value"
    assert detect_value_pattern("412").pattern == "n_only"

    assert detect_value_pattern("Cases").pattern == "unknown"
    assert detect_value_pattern("not reported").pattern == "unknown"
