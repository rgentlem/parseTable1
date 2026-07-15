"""Normalization layer tests for Phase 3."""

from __future__ import annotations

from table1_parser.normalize.header_detector import detect_header_rows, detect_header_rows_with_metadata
from table1_parser.normalize.row_signature import build_row_signature


def test_header_detector_prefers_top_text_heavy_rows() -> None:
    """Header detection should classify top metadata rows separately from the body."""
    rows = [
        ["Variable", "Overall (n=100)", "P-value"],
        ["Age, years", "52.1", "0.03"],
        ["Male", "34", "0.10"],
    ]

    header_rows, body_rows = detect_header_rows(rows)

    assert header_rows == [0]
    assert body_rows == [1, 2]


def test_header_detector_uses_full_width_rule_as_header_boundary() -> None:
    """A full-width drawn rule below top rows should define the header boundary."""
    rows = [
        ["Characteristic", "Overall", "P-value"],
        ["Age, years", "52.1", "0.03"],
        ["Male", "34", "0.10"],
    ]

    header_rows, body_rows = detect_header_rows(
        rows,
        row_bounds=[(12.0, 20.0), (26.0, 34.0), (40.0, 48.0)],
        separator_horizontal_rules=[6.0, 24.0],
    )

    assert header_rows == [0]
    assert body_rows == [1, 2]




def test_header_detector_lets_full_width_rule_define_multiline_header() -> None:
    """A full-width separator should keep a two-line header together."""
    rows = [
        ["Characteristic", "Overall", "Cases"],
        ["", "n", "%"],
        ["Age, years", "52.1", "51.4"],
        ["Male", "34", "32"],
    ]

    header_rows, body_rows = detect_header_rows(
        rows,
        row_bounds=[(12.0, 20.0), (24.0, 32.0), (38.0, 46.0), (50.0, 58.0)],
        separator_horizontal_rules=[7.0, 35.0],
    )

    assert header_rows == [0, 1]
    assert body_rows == [2, 3]


def test_header_detector_excludes_title_row_above_header_band() -> None:
    """A title row above the header band should be neither header nor body."""
    rows = [
        ["Table 1 Baseline characteristics", "", "", "", ""],
        ["Variables", "Overall", "Group A", "Group B", "P-value"],
        ["Sex, n (%)", "", "", "", "< 0.001"],
        ["Male", "20 (50%)", "8 (40%)", "12 (60%)", ""],
        ["Female", "20 (50%)", "12 (60%)", "8 (40%)", ""],
    ]

    header_rows, body_rows, metadata = detect_header_rows_with_metadata(
        rows,
        row_bounds=[(10.0, 18.0), (20.0, 28.0), (30.0, 38.0), (40.0, 48.0), (50.0, 58.0)],
        separator_horizontal_rules=[18.0, 29.0],
    )

    assert header_rows == [1]
    assert body_rows == [2, 3, 4]
    assert metadata["source"] == "horizontal_rule_separator"
    assert metadata["preamble_rows"] == [0]
    assert metadata["separator_body_support"] == "sparse_body_starter_with_value_rows"


def test_header_detector_skips_header_band_with_empty_row_label_below_rule() -> None:
    """Column header bands below early hlines should not become body rows."""
    rows = [
        ["Prevalence of", "Total Periodontitis", "", "Using", "NHANES", "Data", "by Selected"],
        ["Individuals Aged", ">=30", "Years in", "the United", "States,", "2009", "to 2012"],
        ["", "", "", "", "NHANES", "2009 to 2012", "(Combined NHANES"],
        ["", "NHANES", "2009 to 2010", "", "NHANES", "2011 to 2012", ""],
        ["", "", "", "Total", "", "", "Total"],
        ["", "", "", "Periodontitis,", "", "", "Periodontitis,"],
        ["", "", "Weighted", "n Periodontitis", "Standardized", "Weighted", ""],
        ["Characteristics", "n", "(millions)*", "(% - SE)", "(% - SE)", "n", "(millions)"],
        ["All (NHANES 2009 to 2012)", "3,743", "137.1", "47.2 - 2.1", "47.7 - 1.9", "3,323", "144.8"],
    ]

    header_rows, body_rows, metadata = detect_header_rows_with_metadata(
        rows,
        row_bounds=[
            (8.2, 19.6),
            (21.1, 33.5),
            (49.7, 57.8),
            (61.6, 69.8),
            (79.6, 87.8),
            (91.6, 99.8),
            (115.5, 123.7),
            (125.4, 135.7),
            (144.5, 153.7),
        ],
        separator_horizontal_rules=[43.5, 73.8, 139.7],
    )

    assert header_rows == list(range(8))
    assert body_rows == [8]
    assert metadata["separator_rule_y"] == 139.7


def test_header_detector_keeps_leaf_header_above_first_value_row() -> None:
    """Value-anchor backtracking should not absorb a leaf header row into the body."""
    rows = [
        ["Table", "1.", "", "", "", "", ""],
        ["Prevalence of", "Total Periodontitis", "", "Using", "NHANES", "Data", "by Selected"],
        ["Individuals Aged", ">=30", "Years in", "the United", "States,", "2009", "to 2012"],
        ["", "", "", "", "NHANES", "2009 to 2012", "(Combined NHANES"],
        ["", "NHANES", "2009 to 2010", "", "NHANES", "2011 to 2012", ""],
        ["", "", "", "Total", "", "", "Total"],
        ["", "", "", "Periodontitis,", "", "", "Periodontitis,"],
        ["", "", "Weighted", "n Periodontitis", "Standardized", "Weighted", ""],
        ["Characteristics", "n", "(millions)*", "(% - SE)", "(% - SE)", "n", "(millions)"],
        ["All (NHANES 2009 to 2012)", "3,743", "137.1", "47.2 - 2.1", "47.7 - 1.9", "3,323", "144.8"],
    ]

    header_rows, body_rows, metadata = detect_header_rows_with_metadata(rows)

    assert header_rows == list(range(1, 9))
    assert body_rows == [9]
    assert metadata["preamble_rows"] == [0]
    assert metadata["value_anchor_body_start"] == 9


def test_header_detector_accepts_sparse_categorical_parent_below_header_rule() -> None:
    """A categorical parent row can start the body even when it is not value-dense."""
    rows = [
        ["Variables", "Overall", "PAD", "", "P-value"],
        ["", "(n = 8636)", "NO (n = 8108)", "YES (n = 618)", ""],
        ["Sex, n (%)", "", "", "", "0.727"],
        ["Male", "4309 (49.38%)", "4008 (49.43%)", "301 (48.71%)", ""],
        ["Female", "4417 (50.62%)", "4100 (50.57%)", "317 (51.29%)", ""],
    ]

    header_rows, body_rows = detect_header_rows(
        rows,
        row_bounds=[(10.0, 18.0), (20.0, 28.0), (30.0, 38.0), (40.0, 48.0), (50.0, 58.0)],
        separator_horizontal_rules=[9.0, 29.0],
    )

    assert header_rows == [0, 1]
    assert body_rows == [2, 3, 4]


def test_header_detector_accepts_sparse_reference_rows_below_header_rule() -> None:
    """Estimate tables can start with sparse group and reference rows before dense rows."""
    rows = [
        ["", "Adjusted", "95% confidence", ""],
        ["Variable", "odds ratio", "intervals", "P value"],
        ["Cobalt", "", "", ""],
        ["Q1", "1(reference)", "", ""],
        ["Q2", "0.97", "0.82-1.14", ".679"],
    ]

    header_rows, body_rows = detect_header_rows(
        rows,
        row_bounds=[(10.0, 18.0), (20.0, 28.0), (30.0, 38.0), (40.0, 48.0), (50.0, 58.0)],
        separator_horizontal_rules=[9.0, 29.0],
    )

    assert header_rows == [0, 1]
    assert body_rows == [2, 3, 4]


def test_header_detector_accepts_label_only_parent_below_header_rule() -> None:
    """A label-only parent row below a full-width rule can start the body."""
    rows = [
        ["Quartiles", "Crude.", "", "Model", "1"],
        ["", "OR (95% CI)", "p-value", "OR (95%", "CI) p-value"],
        ["GOLD BioAge", "", "", "", ""],
        ["", "0.63", "", "", ""],
        ["Q1(<=32.7)", "", "<0.001", "0.63 (0.56-0.71)", "<0.001"],
    ]

    header_rows, body_rows, metadata = detect_header_rows_with_metadata(
        rows,
        row_bounds=[
            (595.1, 605.6),
            (608.2, 618.7),
            (621.4, 631.8),
            (629.9, 640.4),
            (634.3, 644.7),
        ],
        separator_horizontal_rules=[593.8, 620.1, 693.4],
    )

    assert header_rows == [0, 1]
    assert body_rows == [2, 3, 4]
    assert metadata["source"] == "horizontal_rule_separator"
    assert metadata["separator_body_support"] == "label_only_body_starter_with_value_rows"


def test_header_detector_keeps_multicolumn_leaf_header_above_label_only_parent() -> None:
    """A group header plus leaf header should stop before a row-label-only parent."""
    rows = [
        ["", "Model 1", "", "Model 2", "", "Model 3", ""],
        ["", "OR (95% CI)", "p-value", "OR (95% CI)", "p-value", "OR (95% CI)", "p-value"],
        ["Classified by WC quantiles", "", "", "", "", "", ""],
        ["Q1", "1.0", "-", "1.0", "-", "1.0", "-"],
        ["Q2", "1.18 (1.01, 1.38)", "0.049", "0.87 (0.73, 1.03)", "0.109", "0.86 (0.73, 1.03)", "0.101"],
    ]
    row_bounds = [
        (88.2, 100.8),
        (100.8, 113.3),
        (113.3, 125.8),
        (125.8, 138.3),
        (138.3, 150.8),
    ]

    header_rows, body_rows, metadata = detect_header_rows_with_metadata(
        rows,
        row_bounds=row_bounds,
        separator_horizontal_rules=[88.2, 100.8, 113.3, 125.8, 138.3, 150.8],
    )

    assert header_rows == [0, 1]
    assert body_rows == [2, 3, 4]
    assert metadata["source"] == "horizontal_rule_separator"
    assert metadata["separator_body_support"] == "label_only_body_starter_with_value_rows"


def test_header_detector_keeps_split_estimate_header_above_value_body() -> None:
    """Split estimate leaf headers with digits should not be treated as body values."""
    rows = [
        ["Exposure", "Model 1", "", "Model 2", "", "Model 3", ""],
        ["", "OR (95%", "CI), P-value", "OR (95%", "CI), P-value", "OR (95%", "CI), P-value"],
        ["Continuous", "1.50 (1.40-1.60),", "< 0.001", "1.52 (1.41-1.63),", "< 0.001", "1.46 (1.36-1.58),", "< 0.001"],
        ["METS-IR quartile", "", "", "", "", "", ""],
        ["Q1", "Reference", "", "Reference", "", "Reference", ""],
    ]

    header_rows, body_rows, metadata = detect_header_rows_with_metadata(
        rows,
        row_bounds=[
            (97.4, 107.2),
            (109.1, 118.9),
            (121.1, 130.6),
            (132.8, 142.3),
            (144.5, 154.0),
        ],
        separator_horizontal_rules=[96.4, 119.7, 201.5],
    )

    assert header_rows == [0, 1]
    assert body_rows == [2, 3, 4]
    assert metadata["source"] == "horizontal_rule_separator"


def test_header_detector_accepts_top_rule_that_sits_slightly_below_first_row_top() -> None:
    """Small geometry jitter should not stop rule-based header detection from firing."""
    rows = [
        ["PAHs quintiles", "Model_1", "", "Model_2", "", "Model_3", ""],
        ["", "OR (95% CI)", "P", "OR (95% CI)", "P", "OR (95% CI)", "P"],
        ["Quintile_1", "Reference", "", "Reference", "", "Reference", ""],
        ["Quintile_2", "1.19 (0.94-1.51)", "0.200", "1.15 (0.90-1.48)", "0.300", "1.13 (0.87-1.48)", "0.400"],
    ]

    header_rows, body_rows = detect_header_rows(
        rows,
        row_bounds=[
            (576.29, 589.96),
            (594.79, 604.57),
            (613.43, 622.49),
            (625.53, 634.60),
        ],
        horizontal_rules=[577.44, 609.07, 682.0],
    )

    assert header_rows == [0, 1]
    assert body_rows == [2, 3]


def test_header_detector_uses_first_boundary_rule_when_rotated_row_bands_overlap() -> None:
    """A close first boundary rule should still define the header when line boxes overlap slightly."""
    rows = [
        ["Urinary PAH", "metabolites", "Quintile_1", "Quintile_2", "P for trend"],
        ["(ng/g creatinine)", "* 0.01", "", "", ""],
        ["", "", "OR (95% CI)", "P", ""],
        ["1-Hydroxynaphthalene", "", "", "", ""],
        ["Model_1", "Reference", "1.10 (0.90-1.40)", "0.200", ""],
    ]

    header_rows, body_rows = detect_header_rows(
        rows,
        row_bounds=[
            (1.6, 11.37),
            (10.6, 20.37),
            (17.49, 27.27),
            (35.34, 45.12),
            (48.15, 57.21),
        ],
        horizontal_rules=[-0.22, 31.77, 327.17],
    )

    assert header_rows == [0, 1, 2]
    assert body_rows == [3, 4]


def test_header_detector_falls_back_when_horizontal_rules_are_missing() -> None:
    """Header detection should keep the existing heuristic behavior when no rules are available."""
    rows = [
        ["Characteristic", "Overall", "P-value"],
        ["Age, years", "52.1", "0.03"],
        ["Male", "34", "0.10"],
    ]

    header_rows, body_rows = detect_header_rows(
        rows,
        row_bounds=[(12.0, 20.0), (26.0, 34.0), (40.0, 48.0)],
        horizontal_rules=[],
    )

    assert header_rows == [0]
    assert body_rows == [1, 2]


def test_header_detector_does_not_treat_count_row_as_header() -> None:
    """A row starting with n and otherwise containing counts should stay out of the header."""
    rows = [
        ["Characteristics", "Overall", "Non-RA", "RA", "p test"],
        ["n", "5490", "5171", "319", ""],
        ["Gender=Female(%)", "2793(50.9)", "2603(50.3)", "190(59.6)", "0.002"],
    ]

    header_rows, body_rows = detect_header_rows(rows)

    assert header_rows == [0]
    assert body_rows == [1, 2]


def test_fragmented_horizontal_rules_do_not_override_content_fallback() -> None:
    """Weak line evidence should not displace the existing heuristic detector."""
    rows = [
        ["Characteristic", "Overall", "P-value"],
        ["Age, years", "52.1", "0.03"],
        ["Male", "34", "0.10"],
    ]

    header_rows, body_rows = detect_header_rows(
        rows,
        row_bounds=[(12.0, 20.0), (26.0, 34.0), (40.0, 48.0)],
        horizontal_rules=[24.0],
    )

    assert header_rows == [0]
    assert body_rows == [1, 2]


def test_header_detector_does_not_treat_row_boundaries_as_separator_rules() -> None:
    """Overloaded row-boundary rules should not trigger the visual hline separator path."""
    rows = [
        ["", "The AUC of the optimal", "", "The AUC of the", ""],
        ["", "parameter combination", "", "optimal parameter", ""],
        ["", "in the training cohort", "", "combination", ""],
        ["", "", "", "in the testing cohort", ""],
        ["", "All-cause", "Cardio-", "All-cause", "Cardio-"],
        ["", "mortality", "vascular", "mortality", "vascular"],
        ["", "", "mortality", "", "mortality"],
        ["Logistic", "0.860", "0.831", "0.852", "0.829"],
        ["Regression", "", "", "", ""],
    ]
    row_bounds = [(float(idx * 10), float(idx * 10 + 8)) for idx in range(len(rows))]
    row_boundary_rules = sorted({value for bounds in row_bounds for value in bounds})

    header_rows, body_rows, metadata = detect_header_rows_with_metadata(
        rows,
        row_bounds=row_bounds,
        horizontal_rules=row_boundary_rules,
    )

    assert metadata["source"] != "horizontal_rule_separator"
    assert metadata["source"] == "value_region_anchor"
    assert header_rows == list(range(7))
    assert body_rows[0] == 7




def test_row_signature_generation_keeps_raw_and_normalized_forms() -> None:
    """Row signatures should preserve raw text while deriving normalized first-column features."""
    row_view = build_row_signature(1, ["  <HS", "34", "45%"])

    assert row_view.raw_cells == ["  <HS", "34", "45%"]
    assert row_view.first_cell_raw == "  <HS"
    assert row_view.first_cell_normalized == "HS"
    assert row_view.first_cell_alpha_only == "HS"
    assert row_view.numeric_cell_count == 2
    assert row_view.has_trailing_values is True
    assert row_view.indent_level == 2
    assert row_view.likely_role is None


def test_row_signature_prefers_bbox_indent_when_available() -> None:
    """Bounding-box indentation should override literal leading spaces when present."""
    row_view = build_row_signature(
        1,
        ["  Hispanic/Mexican", "34"],
        first_cell_bbox=(18.0, 0.0, 30.0, 10.0),
        base_x0=10.0,
    )

    assert row_view.first_cell_raw == "  Hispanic/Mexican"
    assert row_view.first_cell_normalized == "Hispanic Mexican"
    assert row_view.indent_level == 8


def test_row_signature_prefers_text_x0_indent_over_cell_bbox() -> None:
    """Text-start indentation should override full-cell bbox boundaries."""
    row_view = build_row_signature(
        1,
        ["Married", "34"],
        first_cell_bbox=(34.0, 0.0, 120.0, 10.0),
        base_x0=34.0,
        first_cell_text_x0=44.0,
        base_text_x0=36.0,
    )

    assert row_view.indent_level == 8




def test_row_signature_preserves_raw_text_word_boundaries() -> None:
    """Row signatures should keep the raw string untouched while normalizing separately."""
    row_view = build_row_signature(1, ["High school", "34"])

    assert row_view.raw_cells == ["High school", "34"]
    assert row_view.first_cell_raw == "High school"
    assert row_view.first_cell_normalized == "High school"
    assert row_view.first_cell_alpha_only == "High school"
