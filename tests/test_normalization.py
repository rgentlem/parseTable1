"""Normalization layer tests for Phase 3."""

from __future__ import annotations

from pathlib import Path

from table1_parser.heuristics.table_definition_builder import build_table_definition
from table1_parser.normalize.header_detector import detect_header_rows
from table1_parser.normalize.io import load_normalized_tables, normalized_tables_to_payload, write_normalized_tables
from table1_parser.normalize.pipeline import normalize_extracted_table
from table1_parser.normalize.row_signature import build_row_signature
from table1_parser.normalize.text_normalizer import alpha_only_text, normalize_label_text
from table1_parser.schemas import ExtractedTable, TableCell
from table1_parser.text_cleaning import clean_text


def test_clean_text_collapses_whitespace_and_normalizes_dashes() -> None:
    """Cleaning should normalize repeated whitespace, comparisons, and dash variants."""
    assert clean_text("  Age   -  years  ") == "Age - years"
    assert clean_text("BMI\u2013kg/m2") == "BMI-kg/m2"
    assert clean_text("p \uff1c 0.05") == "p < 0.05"
    assert clean_text("BMI \u2265 30") == "BMI >= 30"
    assert clean_text("�0.12") == "<=0.12"
    assert clean_text("Q1 �0.12") == "Q1 <=0.12"


def test_label_normalization_preserves_alphanumerics() -> None:
    """Normalized label text should retain letters and digits while dropping punctuation."""
    assert normalize_label_text("High school") == "High school"
    assert normalize_label_text("Family poverty-income ratio") == "Family poverty income ratio"
    assert normalize_label_text("Non-hispanic white") == "Non hispanic white"
    assert normalize_label_text("Hispanic/Mexican") == "Hispanic Mexican"
    assert normalize_label_text("More than high school") == "More than high school"
    assert normalize_label_text("Age, years") == "Age years"
    assert normalize_label_text("BMI, kg/m2") == "BMI kg m2"
    assert normalize_label_text("<HS") == "HS"


def test_alpha_only_conversion_drops_symbols_and_digits() -> None:
    """Alpha-only text should preserve only alphabetic tokens."""
    assert alpha_only_text("High school") == "High school"
    assert alpha_only_text("Family poverty-income ratio") == "Family poverty income ratio"
    assert alpha_only_text("Non-hispanic white") == "Non hispanic white"
    assert alpha_only_text("Hispanic/Mexican") == "Hispanic Mexican"
    assert alpha_only_text("More than high school") == "More than high school"
    assert alpha_only_text("Age, years") == "Age years"
    assert alpha_only_text("<HS") == "HS"
    assert alpha_only_text("BMI, kg/m2") == "BMI kg m"


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


def test_header_detector_uses_horizontal_rules_as_strong_boundary_signal() -> None:
    """Wide horizontal rules should strengthen top header-boundary detection when row bounds exist."""
    rows = [
        ["Characteristic", "Overall", "P-value"],
        ["Age, years", "52.1", "0.03"],
        ["Male", "34", "0.10"],
    ]

    header_rows, body_rows = detect_header_rows(
        rows,
        row_bounds=[(12.0, 20.0), (26.0, 34.0), (40.0, 48.0)],
        horizontal_rules=[6.0, 24.0],
    )

    assert header_rows == [0]
    assert body_rows == [1, 2]


def test_header_detector_lets_strong_rules_override_weaker_text_heuristics() -> None:
    """Strong bracketing rules should win even when text-only cues would miss a second header row."""
    rows = [
        ["Characteristic", "Overall", "Cases"],
        ["", "n", "%"],
        ["Age, years", "52.1", "51.4"],
        ["Male", "34", "32"],
    ]

    header_rows, body_rows = detect_header_rows(
        rows,
        row_bounds=[(12.0, 20.0), (24.0, 32.0), (38.0, 46.0), (50.0, 58.0)],
        horizontal_rules=[7.0, 35.0],
    )

    assert header_rows == [0, 1]
    assert body_rows == [2, 3]


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


def test_header_detector_promotes_strong_header_like_first_body_row() -> None:
    """A top row of ranges and trailing statistic labels should be promoted into the header."""
    rows = [
        ["", "Q1", "Q2", "Q3", "Q4"],
        ["Cobalt quartiles (mg/l)", "<=0.12", "0.13-0.14", "0.15-0.18", "P value"],
        ["Age (yrs), mean±SD", "58.1±11.2", "60.0±11.4", "61.4±11.6", "<.001"],
    ]

    header_rows, body_rows = detect_header_rows(rows)

    assert header_rows == [0, 1]
    assert body_rows == [2]


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


def test_normalization_marks_flush_left_indentation_as_uninformative() -> None:
    """Nearly uniform body-row label positions should not count as informative indentation."""
    extracted = ExtractedTable(
        table_id="tbl-indent-flat",
        source_pdf="paper.pdf",
        page_num=1,
        n_rows=4,
        n_cols=2,
        cells=[
            TableCell(row_idx=0, col_idx=0, text="Variable", bbox=(10.0, 10.0, 40.0, 18.0)),
            TableCell(row_idx=0, col_idx=1, text="Overall"),
            TableCell(row_idx=1, col_idx=0, text="Race", bbox=(10.0, 20.0, 40.0, 28.0)),
            TableCell(row_idx=1, col_idx=1, text=""),
            TableCell(row_idx=2, col_idx=0, text="White", bbox=(10.5, 30.0, 45.0, 38.0)),
            TableCell(row_idx=2, col_idx=1, text="10"),
            TableCell(row_idx=3, col_idx=0, text="Other", bbox=(10.0, 40.0, 45.0, 48.0)),
            TableCell(row_idx=3, col_idx=1, text="12"),
        ],
        extraction_backend="pymupdf4llm",
    )

    normalized = normalize_extracted_table(extracted)

    assert normalized.metadata["indentation_informative"] is False


def test_row_signature_preserves_raw_text_word_boundaries() -> None:
    """Row signatures should keep the raw string untouched while normalizing separately."""
    row_view = build_row_signature(1, ["High school", "34"])

    assert row_view.raw_cells == ["High school", "34"]
    assert row_view.first_cell_raw == "High school"
    assert row_view.first_cell_normalized == "High school"
    assert row_view.first_cell_alpha_only == "High school"


def test_extracted_table_to_normalized_table_conversion() -> None:
    """Normalization should convert extracted rows into a NormalizedTable view."""
    extracted = ExtractedTable(
        table_id="tbl-1",
        source_pdf="paper.pdf",
        page_num=1,
        title="Table 1",
        caption="Baseline characteristics",
        n_rows=3,
        n_cols=3,
        cells=[
            TableCell(row_idx=0, col_idx=0, text="Variable"),
            TableCell(row_idx=0, col_idx=1, text="Overall (n=100)"),
            TableCell(row_idx=0, col_idx=2, text="P-value"),
            TableCell(row_idx=1, col_idx=0, text="Age, years"),
            TableCell(row_idx=1, col_idx=1, text="52.1"),
            TableCell(row_idx=1, col_idx=2, text="0.03"),
            TableCell(row_idx=2, col_idx=0, text="Male"),
            TableCell(row_idx=2, col_idx=1, text="34"),
            TableCell(row_idx=2, col_idx=2, text="0.10"),
        ],
        extraction_backend="pymupdf4llm",
    )

    normalized = normalize_extracted_table(extracted)

    assert normalized.header_rows == [0]
    assert normalized.body_rows == [1, 2]
    assert normalized.row_views[0].first_cell_normalized == "Age years"
    assert normalized.row_views[1].first_cell_alpha_only == "Male"
    assert normalized.metadata["extraction_backend"] == "pymupdf4llm"


def test_normalization_preserves_table_orientation_metadata() -> None:
    """Normalization should preserve extraction metadata about table orientation."""
    extracted = ExtractedTable(
        table_id="tbl-rotated",
        source_pdf="paper.pdf",
        page_num=9,
        title="Table 2",
        caption="Distribution table",
        n_rows=2,
        n_cols=2,
        cells=[
            TableCell(row_idx=0, col_idx=0, text="Variable"),
            TableCell(row_idx=0, col_idx=1, text="Value"),
            TableCell(row_idx=1, col_idx=0, text="DPHP"),
            TableCell(row_idx=1, col_idx=1, text="0.74"),
        ],
        extraction_backend="pymupdf4llm",
        metadata={
            "table_orientation": "rotated",
            "rotation_source": "pymupdf_line_direction",
            "rotation_direction": "vertical_text_up",
            "rotation_confidence": 0.98,
        },
    )

    normalized = normalize_extracted_table(extracted)

    assert normalized.metadata["table_orientation"] == "rotated"


def test_normalization_uses_rotated_local_rule_metadata_after_extraction_refinement() -> None:
    """Normalized output should recognize headers from rotated local-coordinate refinement metadata."""
    rows = [
        ["Urinary PAH", "metabolites", "Quintile_1", "Quintile_2", "P for trend"],
        ["(ng/g creatinine)", "* 0.01", "", "", ""],
        ["", "", "OR (95% CI)", "P", ""],
        ["1-Hydroxynaphthalene", "", "", "", ""],
        ["Model_1", "Reference", "1.10 (0.90-1.40)", "0.200", ""],
    ]
    cells: list[TableCell] = []
    for row_idx, row in enumerate(rows):
        for col_idx, value in enumerate(row):
            cells.append(TableCell(row_idx=row_idx, col_idx=col_idx, text=value))

    extracted = ExtractedTable(
        table_id="tbl-rotated-refined",
        source_pdf="paper.pdf",
        page_num=8,
        n_rows=len(rows),
        n_cols=len(rows[0]),
        cells=cells,
        extraction_backend="pymupdf4llm",
        metadata={
            "table_orientation": "rotated",
            "rotation_source": "pymupdf_line_direction",
            "rotation_direction": "vertical_text_up",
            "rotation_confidence": 1.0,
            "geometry_coordinate_frame": "table_local_rotated_normalized",
            "grid_refinement_source": "rotated_word_positions_with_rules",
            "row_bounds": [
                (1.6, 11.37),
                (10.6, 20.37),
                (17.49, 27.27),
                (35.34, 45.12),
                (48.15, 57.21),
            ],
            "horizontal_rules": [-0.22, 31.77, 327.17],
        },
    )

    normalized = normalize_extracted_table(extracted)

    assert normalized.header_rows == [0, 1, 2]
    assert normalized.body_rows == [3, 4]


def test_normalization_repairs_split_count_percent_columns_and_promotes_following_header_row() -> None:
    """Count-plus-percent fragments should merge left and enable stronger header interpretation."""
    extracted = ExtractedTable(
        table_id="tbl-repair",
        source_pdf="paper.pdf",
        page_num=1,
        n_rows=6,
        n_cols=8,
        cells=[
            TableCell(row_idx=0, col_idx=2, text="Q1"),
            TableCell(row_idx=0, col_idx=3, text="Q2"),
            TableCell(row_idx=0, col_idx=4, text="Q3"),
            TableCell(row_idx=0, col_idx=6, text="Q4"),
            TableCell(row_idx=1, col_idx=0, text="Cobalt quartiles (mg/l)"),
            TableCell(row_idx=1, col_idx=1, text="All"),
            TableCell(row_idx=1, col_idx=2, text="<=0.12"),
            TableCell(row_idx=1, col_idx=3, text="0.13-0.14"),
            TableCell(row_idx=1, col_idx=4, text="0.15-0.18"),
            TableCell(row_idx=1, col_idx=5, text=">=0.19"),
            TableCell(row_idx=1, col_idx=7, text="P value"),
            TableCell(row_idx=2, col_idx=0, text="Education level, n (%)"),
            TableCell(row_idx=2, col_idx=7, text=".046"),
            TableCell(row_idx=3, col_idx=0, text="<High school"),
            TableCell(row_idx=3, col_idx=1, text="849 (12.4%)"),
            TableCell(row_idx=3, col_idx=2, text="220 (11.4%)"),
            TableCell(row_idx=3, col_idx=3, text="182 (12.9%)"),
            TableCell(row_idx=3, col_idx=4, text="248 (13.9%)"),
            TableCell(row_idx=3, col_idx=5, text="199"),
            TableCell(row_idx=3, col_idx=6, text="(11.5%)"),
            TableCell(row_idx=4, col_idx=0, text="High school"),
            TableCell(row_idx=4, col_idx=1, text="2364 (34.5%)"),
            TableCell(row_idx=4, col_idx=2, text="706 (36.6%)"),
            TableCell(row_idx=4, col_idx=3, text="467 (33.3%)"),
            TableCell(row_idx=4, col_idx=4, text="618 (34.6%)"),
            TableCell(row_idx=4, col_idx=5, text="573"),
            TableCell(row_idx=4, col_idx=6, text="(33.2%)"),
            TableCell(row_idx=5, col_idx=0, text=">High school"),
            TableCell(row_idx=5, col_idx=1, text="3640 (53.1%)"),
            TableCell(row_idx=5, col_idx=2, text="1002 (52.0%)"),
            TableCell(row_idx=5, col_idx=3, text="765 (54.1%)"),
            TableCell(row_idx=5, col_idx=4, text="921 (51.5%)"),
            TableCell(row_idx=5, col_idx=5, text="952"),
            TableCell(row_idx=5, col_idx=6, text="(55.2%)"),
        ],
        extraction_backend="pymupdf4llm",
    )

    normalized = normalize_extracted_table(extracted)

    assert normalized.header_rows == [0, 1]
    assert normalized.n_cols == 7


def test_normalization_repairs_split_leading_label_fragments_for_table1_rows() -> None:
    """Split NHANES-style row labels should be merged before variable grouping and column inference."""
    rows = [
        ["", "", "All (n=5611)", "0-1 (n=1815)", "2-3 (n=3233)", "4-6 (n=563)", "p value"],
        ["Age (years),", "Mean (SD)", "52.09 (14.16)", "52.12 (13.51)", "52.33 (14.38)", "50.63 (14.82)", "0.03"],
        ["Gender,", "n (%)", "", "", "", "", "<0.01"],
        ["Male", "", "2935 (52.31)", "871 (47.99)", "1731 (53.54)", "333 (59.51)", ""],
        ["Female", "", "2676 (47.69)", "944 (52.01)", "1502 (46.46)", "230 (20.85)", ""],
        ["Family", "income-to-poverty ratio,", "n (%)", "", "", "", ""],
        ["Low income", "(<=1.85)", "1998 (35.61)", "821 (45.23)", "1054 (32.60)", "123 (21.85)", "<0.01"],
        ["High income", "(>1.85)", "3613 (64.39)", "994 (54.77)", "2179 (67.40)", "440 (78.15)", ""],
    ]
    cells: list[TableCell] = []
    for row_idx, row in enumerate(rows):
        for col_idx, value in enumerate(row):
            cells.append(TableCell(row_idx=row_idx, col_idx=col_idx, text=value))

    extracted = ExtractedTable(
        table_id="tbl-leading-labels",
        source_pdf="paper.pdf",
        page_num=1,
        n_rows=len(rows),
        n_cols=len(rows[0]),
        cells=cells,
        extraction_backend="pymupdf4llm",
    )

    normalized = normalize_extracted_table(extracted)
    definition = build_table_definition(normalized)

    assert normalized.n_cols == 6
    assert normalized.metadata["cleaned_rows"][1][0] == "Age (years), Mean (SD)"
    assert normalized.metadata["cleaned_rows"][2][0] == "Gender, n (%)"
    assert normalized.metadata["cleaned_rows"][5][0] == "Family income-to-poverty ratio, n (%)"
    assert [variable.variable_name for variable in definition.variables] == [
        "Age",
        "Gender",
        "Family income to poverty ratio",
    ]
    assert [column.column_label for column in definition.column_definition.columns] == [
        "All (n=5611)",
        "0-1 (n=1815)",
        "2-3 (n=3233)",
        "4-6 (n=563)",
        "p value",
    ]


def test_normalization_repairs_broken_replacement_char_threshold_in_headers() -> None:
    """A broken replacement character before a numeric threshold should normalize to <=."""
    extracted = ExtractedTable(
        table_id="tbl-threshold-repair",
        source_pdf="paper.pdf",
        page_num=1,
        n_rows=3,
        n_cols=5,
        cells=[
            TableCell(row_idx=0, col_idx=1, text="Q1"),
            TableCell(row_idx=0, col_idx=2, text="Q2"),
            TableCell(row_idx=1, col_idx=0, text="Cobalt quartiles (mg/l)"),
            TableCell(row_idx=1, col_idx=1, text="�0.12"),
            TableCell(row_idx=1, col_idx=2, text="0.13-0.14"),
            TableCell(row_idx=1, col_idx=3, text=">=0.19"),
            TableCell(row_idx=1, col_idx=4, text="P value"),
            TableCell(row_idx=2, col_idx=0, text="SBP (mm Hg), mean±SD"),
            TableCell(row_idx=2, col_idx=1, text="131.0±19.7"),
            TableCell(row_idx=2, col_idx=2, text="129.4±18.1"),
            TableCell(row_idx=2, col_idx=3, text="131.3±21.3"),
            TableCell(row_idx=2, col_idx=4, text="<.001"),
        ],
        extraction_backend="pymupdf4llm",
    )

    normalized = normalize_extracted_table(extracted)

    assert normalized.metadata["cleaned_rows"][1][1] == "<=0.12"
    assert normalized.header_rows == [0, 1]
    assert normalized.metadata["text_cleaning_provenance"] == {
        "observed_symbol_counts": {"<": 1, "<=": 0, ">": 0, ">=": 1},
        "reconstructed_symbol_counts": {"<": 0, "<=": 1, ">": 0, ">=": 0},
        "total_observed_symbol_count": 2,
        "total_reconstructed_symbol_count": 1,
        "extractor_glyph_repair_rule_counts": {"replacement_char_le_threshold": 1},
        "cells_with_extractor_glyph_repairs": 1,
    }


def test_count_percent_column_merge_preserves_raw_text_for_provenance() -> None:
    """Column repair should keep raw text raw enough for later provenance accounting."""
    extracted = ExtractedTable(
        table_id="tbl-merge-provenance",
        source_pdf="paper.pdf",
        page_num=1,
        n_rows=6,
        n_cols=8,
        cells=[
            TableCell(row_idx=0, col_idx=2, text="Q1"),
            TableCell(row_idx=0, col_idx=3, text="Q2"),
            TableCell(row_idx=0, col_idx=4, text="Q3"),
            TableCell(row_idx=0, col_idx=6, text="Q4"),
            TableCell(row_idx=1, col_idx=0, text="Cobalt quartiles (mg/l)"),
            TableCell(row_idx=1, col_idx=1, text="All"),
            TableCell(row_idx=1, col_idx=2, text="<=0.12"),
            TableCell(row_idx=1, col_idx=3, text="0.13-0.14"),
            TableCell(row_idx=1, col_idx=4, text="0.15-0.18"),
            TableCell(row_idx=1, col_idx=5, text=">=0.19"),
            TableCell(row_idx=1, col_idx=7, text="P value"),
            TableCell(row_idx=2, col_idx=0, text="Education level, n (%)"),
            TableCell(row_idx=2, col_idx=7, text=".046"),
            TableCell(row_idx=3, col_idx=0, text="<High school"),
            TableCell(row_idx=3, col_idx=1, text="849 (12.4%)"),
            TableCell(row_idx=3, col_idx=2, text="220 (11.4%)"),
            TableCell(row_idx=3, col_idx=3, text="182 (12.9%)"),
            TableCell(row_idx=3, col_idx=4, text="248 (13.9%)"),
            TableCell(row_idx=3, col_idx=5, text="199"),
            TableCell(row_idx=3, col_idx=6, text="(11.5%)"),
            TableCell(row_idx=4, col_idx=0, text="High school"),
            TableCell(row_idx=4, col_idx=1, text="2364 (34.5%)"),
            TableCell(row_idx=4, col_idx=2, text="706 (36.6%)"),
            TableCell(row_idx=4, col_idx=3, text="467 (33.3%)"),
            TableCell(row_idx=4, col_idx=4, text="618 (34.6%)"),
            TableCell(row_idx=4, col_idx=5, text="573"),
            TableCell(row_idx=4, col_idx=6, text="(33.2%)"),
            TableCell(row_idx=5, col_idx=0, text=">High school"),
            TableCell(row_idx=5, col_idx=1, text="3640 (53.1%)"),
            TableCell(row_idx=5, col_idx=2, text="1002 (52.0%)"),
            TableCell(row_idx=5, col_idx=3, text="765 (54.1%)"),
            TableCell(row_idx=5, col_idx=4, text="921 (51.5%)"),
            TableCell(row_idx=5, col_idx=5, text="952"),
            TableCell(row_idx=5, col_idx=6, text="(55.2%)"),
        ],
        extraction_backend="pymupdf4llm",
    )

    normalized = normalize_extracted_table(extracted)

    assert normalized.metadata["cleaned_rows"][3] == [
        "<High school",
        "849 (12.4%)",
        "220 (11.4%)",
        "182 (12.9%)",
        "248 (13.9%)",
        "199 (11.5%)",
        "",
    ]
    assert normalized.row_views[1].raw_cells == [
        "<High school",
        "849 (12.4%)",
        "220 (11.4%)",
        "182 (12.9%)",
        "248 (13.9%)",
        "199 (11.5%)",
        "",
    ]


def test_normalized_table_round_trip_serialization(tmp_path: Path) -> None:
    """Normalized tables should round-trip cleanly through the persisted JSON artifact."""
    extracted = ExtractedTable(
        table_id="tbl-roundtrip",
        source_pdf="paper.pdf",
        page_num=1,
        n_rows=3,
        n_cols=3,
        cells=[
            TableCell(row_idx=0, col_idx=0, text="Variable"),
            TableCell(row_idx=0, col_idx=1, text="Overall"),
            TableCell(row_idx=0, col_idx=2, text="P-value"),
            TableCell(row_idx=1, col_idx=0, text="Age, years"),
            TableCell(row_idx=1, col_idx=1, text="52.1"),
            TableCell(row_idx=1, col_idx=2, text="0.03"),
            TableCell(row_idx=2, col_idx=0, text="Male"),
            TableCell(row_idx=2, col_idx=1, text="34"),
            TableCell(row_idx=2, col_idx=2, text="0.10"),
        ],
        extraction_backend="pymupdf4llm",
    )

    normalized = normalize_extracted_table(extracted)
    output_path = tmp_path / "normalized_tables.json"
    write_normalized_tables(output_path, [normalized])
    loaded = load_normalized_tables(output_path)

    assert loaded[0] == normalized


def test_normalized_table_payload_helper_serializes_models() -> None:
    """The payload helper should produce a list of JSON-friendly normalized-table objects."""
    extracted = ExtractedTable(
        table_id="tbl-payload",
        source_pdf="paper.pdf",
        page_num=1,
        n_rows=2,
        n_cols=2,
        cells=[
            TableCell(row_idx=0, col_idx=0, text="Variable"),
            TableCell(row_idx=0, col_idx=1, text="Overall"),
            TableCell(row_idx=1, col_idx=0, text="Age, years"),
            TableCell(row_idx=1, col_idx=1, text="52.1"),
        ],
        extraction_backend="pymupdf4llm",
    )

    payload = normalized_tables_to_payload([normalize_extracted_table(extracted)])

    assert payload[0]["table_id"] == "tbl-payload"
    assert payload[0]["header_rows"] == [0]


def test_normalization_uses_rule_metadata_for_header_boundary_when_available() -> None:
    """Normalization should pass optional row-bound and rule metadata into header detection."""
    extracted = ExtractedTable(
        table_id="tbl-rule-header",
        source_pdf="paper.pdf",
        page_num=1,
        title="Table 1",
        caption="Baseline characteristics",
        n_rows=3,
        n_cols=3,
        cells=[
            TableCell(row_idx=0, col_idx=0, text="Characteristic"),
            TableCell(row_idx=0, col_idx=1, text="Overall"),
            TableCell(row_idx=0, col_idx=2, text="P-value"),
            TableCell(row_idx=1, col_idx=0, text="Age, years"),
            TableCell(row_idx=1, col_idx=1, text="52.1"),
            TableCell(row_idx=1, col_idx=2, text="0.03"),
            TableCell(row_idx=2, col_idx=0, text="Male"),
            TableCell(row_idx=2, col_idx=1, text="34"),
            TableCell(row_idx=2, col_idx=2, text="0.10"),
        ],
        extraction_backend="pymupdf4llm",
        metadata={
            "row_bounds": [(12.0, 20.0), (26.0, 34.0), (40.0, 48.0)],
            "horizontal_rules": [6.0, 24.0],
        },
    )

    normalized = normalize_extracted_table(extracted)

    assert normalized.header_rows == [0]
    assert normalized.body_rows == [1, 2]
    assert normalized.metadata["header_detection"]["source"] == "horizontal_rules"
    assert normalized.metadata["header_detection"]["rule_strength"] == "strong"


def test_normalization_accepts_pymupdf_text_layout_rule_metadata() -> None:
    """Normalization should treat PyMuPDF fallback geometry metadata like other extracted tables."""
    extracted = ExtractedTable(
        table_id="tbl-pymupdf-fallback",
        source_pdf="paper.pdf",
        page_num=1,
        title="Table 1",
        caption="Baseline characteristics",
        n_rows=3,
        n_cols=3,
        cells=[
            TableCell(row_idx=0, col_idx=0, text="Characteristic"),
            TableCell(row_idx=0, col_idx=1, text="Overall"),
            TableCell(row_idx=0, col_idx=2, text="P-value"),
            TableCell(row_idx=1, col_idx=0, text="Age, years"),
            TableCell(row_idx=1, col_idx=1, text="52.1"),
            TableCell(row_idx=1, col_idx=2, text="0.03"),
            TableCell(row_idx=2, col_idx=0, text="Male"),
            TableCell(row_idx=2, col_idx=1, text="34"),
            TableCell(row_idx=2, col_idx=2, text="0.10"),
        ],
        extraction_backend="pymupdf4llm",
        metadata={
            "layout_source": "pymupdf_text_positions",
            "row_bounds": [(12.0, 20.0), (26.0, 34.0), (40.0, 48.0)],
            "horizontal_rules": [6.0, 24.0],
        },
    )

    normalized = normalize_extracted_table(extracted)

    assert normalized.metadata["extraction_backend"] == "pymupdf4llm"
    assert normalized.metadata["header_detection"]["source"] == "horizontal_rules"


def test_mostly_empty_leading_column_gets_removed() -> None:
    """A mostly empty leading edge column should be dropped at the table level."""
    extracted = ExtractedTable(
        table_id="tbl-leading-empty",
        source_pdf="paper.pdf",
        page_num=1,
        n_rows=3,
        n_cols=4,
        cells=[
            TableCell(row_idx=0, col_idx=0, text=""),
            TableCell(row_idx=0, col_idx=1, text="Variable"),
            TableCell(row_idx=0, col_idx=2, text="Overall"),
            TableCell(row_idx=0, col_idx=3, text="P-value"),
            TableCell(row_idx=1, col_idx=0, text=""),
            TableCell(row_idx=1, col_idx=1, text="Age, years"),
            TableCell(row_idx=1, col_idx=2, text="52.1"),
            TableCell(row_idx=1, col_idx=3, text="0.03"),
            TableCell(row_idx=2, col_idx=0, text=""),
            TableCell(row_idx=2, col_idx=1, text="Male"),
            TableCell(row_idx=2, col_idx=2, text="34"),
            TableCell(row_idx=2, col_idx=3, text="0.10"),
        ],
        extraction_backend="pymupdf4llm",
    )

    normalized = normalize_extracted_table(extracted)

    assert normalized.n_cols == 3
    assert normalized.metadata["dropped_leading_cols"] == 1
    assert normalized.metadata["cleaned_rows"][0] == ["Variable", "Overall", "P-value"]


def test_noisy_mostly_empty_leading_column_still_gets_removed() -> None:
    """A few stray noninformative first-column values should not block leading-column cleanup."""
    extracted = ExtractedTable(
        table_id="tbl-leading-noisy",
        source_pdf="paper.pdf",
        page_num=1,
        n_rows=4,
        n_cols=4,
        cells=[
            TableCell(row_idx=0, col_idx=0, text=""),
            TableCell(row_idx=0, col_idx=1, text="Characteristic"),
            TableCell(row_idx=0, col_idx=2, text="Overall"),
            TableCell(row_idx=0, col_idx=3, text=""),
            TableCell(row_idx=1, col_idx=0, text="."),
            TableCell(row_idx=1, col_idx=1, text="n"),
            TableCell(row_idx=1, col_idx=2, text="5490"),
            TableCell(row_idx=1, col_idx=3, text=""),
            TableCell(row_idx=2, col_idx=0, text="1"),
            TableCell(row_idx=2, col_idx=1, text="Age, years"),
            TableCell(row_idx=2, col_idx=2, text="52.1"),
            TableCell(row_idx=2, col_idx=3, text=""),
            TableCell(row_idx=3, col_idx=0, text=""),
            TableCell(row_idx=3, col_idx=1, text="Male"),
            TableCell(row_idx=3, col_idx=2, text="34"),
            TableCell(row_idx=3, col_idx=3, text=""),
        ],
        extraction_backend="pymupdf4llm",
    )

    normalized = normalize_extracted_table(extracted)

    assert normalized.n_cols == 2
    assert normalized.metadata["dropped_leading_cols"] == 1
    assert normalized.metadata["dropped_trailing_cols"] == 1
    assert normalized.metadata["cleaned_rows"][1] == ["n", "5490"]


def test_meaningful_first_column_is_preserved() -> None:
    """A table with real first-column labels should keep the first column."""
    extracted = ExtractedTable(
        table_id="tbl-keep-leading",
        source_pdf="paper.pdf",
        page_num=1,
        n_rows=3,
        n_cols=3,
        cells=[
            TableCell(row_idx=0, col_idx=0, text="Variable"),
            TableCell(row_idx=0, col_idx=1, text="Overall"),
            TableCell(row_idx=0, col_idx=2, text="P-value"),
            TableCell(row_idx=1, col_idx=0, text="Age, years"),
            TableCell(row_idx=1, col_idx=1, text="52.1"),
            TableCell(row_idx=1, col_idx=2, text="0.03"),
            TableCell(row_idx=2, col_idx=0, text="Male"),
            TableCell(row_idx=2, col_idx=1, text="34"),
            TableCell(row_idx=2, col_idx=2, text="0.10"),
        ],
        extraction_backend="pymupdf4llm",
    )

    normalized = normalize_extracted_table(extracted)

    assert normalized.n_cols == 3
    assert normalized.metadata["dropped_leading_cols"] == 0
    assert normalized.metadata["cleaned_rows"][1][0] == "Age, years"


def test_trailing_mostly_empty_column_is_removed_conservatively() -> None:
    """A mostly empty trailing edge column should be removed without touching inner empties."""
    extracted = ExtractedTable(
        table_id="tbl-trailing-empty",
        source_pdf="paper.pdf",
        page_num=1,
        n_rows=3,
        n_cols=4,
        cells=[
            TableCell(row_idx=0, col_idx=0, text="Variable"),
            TableCell(row_idx=0, col_idx=1, text="Overall"),
            TableCell(row_idx=0, col_idx=2, text="P-value"),
            TableCell(row_idx=0, col_idx=3, text=""),
            TableCell(row_idx=1, col_idx=0, text="Age, years"),
            TableCell(row_idx=1, col_idx=1, text="52.1"),
            TableCell(row_idx=1, col_idx=2, text="0.03"),
            TableCell(row_idx=1, col_idx=3, text="."),
            TableCell(row_idx=2, col_idx=0, text="Male"),
            TableCell(row_idx=2, col_idx=1, text="34"),
            TableCell(row_idx=2, col_idx=2, text="0.10"),
            TableCell(row_idx=2, col_idx=3, text=""),
        ],
        extraction_backend="pymupdf4llm",
    )

    normalized = normalize_extracted_table(extracted)

    assert normalized.n_cols == 3
    assert normalized.metadata["dropped_trailing_cols"] == 1
    assert normalized.metadata["cleaned_rows"][1] == ["Age, years", "52.1", "0.03"]


def test_inner_empty_cells_are_preserved_when_edge_columns_are_trimmed() -> None:
    """Empty cells inside the remaining grid should not be removed."""
    extracted = ExtractedTable(
        table_id="tbl-inner-empty",
        source_pdf="paper.pdf",
        page_num=1,
        n_rows=3,
        n_cols=5,
        cells=[
            TableCell(row_idx=0, col_idx=0, text=""),
            TableCell(row_idx=0, col_idx=1, text="Variable"),
            TableCell(row_idx=0, col_idx=2, text="Overall"),
            TableCell(row_idx=0, col_idx=3, text="P-value"),
            TableCell(row_idx=0, col_idx=4, text=""),
            TableCell(row_idx=1, col_idx=0, text=""),
            TableCell(row_idx=1, col_idx=1, text="Sex"),
            TableCell(row_idx=1, col_idx=2, text=""),
            TableCell(row_idx=1, col_idx=3, text=""),
            TableCell(row_idx=1, col_idx=4, text=""),
            TableCell(row_idx=2, col_idx=0, text="."),
            TableCell(row_idx=2, col_idx=1, text="Male"),
            TableCell(row_idx=2, col_idx=2, text="34"),
            TableCell(row_idx=2, col_idx=3, text="0.10"),
            TableCell(row_idx=2, col_idx=4, text=""),
        ],
        extraction_backend="pymupdf4llm",
    )

    normalized = normalize_extracted_table(extracted)

    assert normalized.metadata["cleaned_rows"][1] == ["Sex", "", ""]
    assert normalized.metadata["cleaned_rows"][2] == ["Male", "34", "0.10"]


def test_row_and_column_order_are_preserved_after_edge_trimming() -> None:
    """Leading/trailing cleanup should preserve the order of remaining rows and columns."""
    extracted = ExtractedTable(
        table_id="tbl-order",
        source_pdf="paper.pdf",
        page_num=1,
        n_rows=4,
        n_cols=5,
        cells=[
            TableCell(row_idx=0, col_idx=0, text=""),
            TableCell(row_idx=0, col_idx=1, text="A"),
            TableCell(row_idx=0, col_idx=2, text="B"),
            TableCell(row_idx=0, col_idx=3, text="C"),
            TableCell(row_idx=0, col_idx=4, text=""),
            TableCell(row_idx=1, col_idx=0, text=""),
            TableCell(row_idx=1, col_idx=1, text="r1"),
            TableCell(row_idx=1, col_idx=2, text="x"),
            TableCell(row_idx=1, col_idx=3, text="y"),
            TableCell(row_idx=1, col_idx=4, text=""),
            TableCell(row_idx=2, col_idx=0, text="1"),
            TableCell(row_idx=2, col_idx=1, text="r2"),
            TableCell(row_idx=2, col_idx=2, text="m"),
            TableCell(row_idx=2, col_idx=3, text="n"),
            TableCell(row_idx=2, col_idx=4, text="."),
            TableCell(row_idx=3, col_idx=0, text=""),
            TableCell(row_idx=3, col_idx=1, text="r3"),
            TableCell(row_idx=3, col_idx=2, text="p"),
            TableCell(row_idx=3, col_idx=3, text="q"),
            TableCell(row_idx=3, col_idx=4, text=""),
        ],
        extraction_backend="pymupdf4llm",
    )

    normalized = normalize_extracted_table(extracted)

    assert normalized.metadata["cleaned_rows"] == [
        ["A", "B", "C"],
        ["r1", "x", "y"],
        ["r2", "m", "n"],
        ["r3", "p", "q"],
    ]
