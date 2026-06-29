"""Normalization layer tests for Phase 3."""

from __future__ import annotations

from pathlib import Path

from table1_parser.normalize.header_detector import detect_header_rows
from table1_parser.normalize.io import load_normalized_tables, normalized_tables_to_payload, write_normalized_tables
from table1_parser.normalize.pipeline import normalize_extracted_table
from table1_parser.normalize.row_signature import build_row_signature
from table1_parser.schemas import ExtractedTable, TableCell


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


def test_normalization_uses_first_column_text_x0_metadata_for_indentation() -> None:
    """Normalization should use visible first-word positions when cell bboxes are full-column bounds."""
    extracted = ExtractedTable(
        table_id="tbl-text-indent",
        source_pdf="paper.pdf",
        page_num=1,
        n_rows=5,
        n_cols=2,
        cells=[
            TableCell(row_idx=0, col_idx=0, text="Variable", bbox=(34.0, 10.0, 120.0, 18.0)),
            TableCell(row_idx=0, col_idx=1, text="Overall"),
            TableCell(row_idx=1, col_idx=0, text="Marital status, n (%)", bbox=(34.0, 20.0, 120.0, 28.0)),
            TableCell(row_idx=1, col_idx=1, text=""),
            TableCell(row_idx=2, col_idx=0, text="Married", bbox=(34.0, 30.0, 120.0, 38.0)),
            TableCell(row_idx=2, col_idx=1, text="10 (50.0)"),
            TableCell(row_idx=3, col_idx=0, text="Never married", bbox=(34.0, 40.0, 120.0, 48.0)),
            TableCell(row_idx=3, col_idx=1, text="5 (25.0)"),
            TableCell(row_idx=4, col_idx=0, text="Education level, n (%)", bbox=(34.0, 50.0, 120.0, 58.0)),
            TableCell(row_idx=4, col_idx=1, text=""),
        ],
        extraction_backend="pymupdf4llm",
        metadata={
            "row_bounds": [(10.0, 18.0), (20.0, 28.0), (30.0, 38.0), (40.0, 48.0), (50.0, 58.0)],
            "horizontal_rules": [19.0],
            "first_column_text_x0_by_row": {
                "0": 34.0,
                "1": 36.0,
                "2": 44.0,
                "3": 44.0,
                "4": 36.0,
            }
        },
    )

    normalized = normalize_extracted_table(extracted)
    indents = {row_view.row_idx: row_view.indent_level for row_view in normalized.row_views}

    assert indents[2] == 8
    assert indents[3] == 8
    assert indents[4] == 0
    assert normalized.metadata["indentation_informative"] is True


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


def test_normalization_repairs_split_left_label_columns() -> None:
    """Split left-side label fragments should be merged before RowView construction."""
    extracted = ExtractedTable(
        table_id="tbl-split-labels",
        source_pdf="paper.pdf",
        page_num=1,
        n_rows=7,
        n_cols=5,
        cells=[
            TableCell(row_idx=0, col_idx=0, text="Characteristic"),
            TableCell(row_idx=0, col_idx=2, text="Overall"),
            TableCell(row_idx=0, col_idx=3, text="PAD"),
            TableCell(row_idx=0, col_idx=4, text="P-value"),
            TableCell(row_idx=1, col_idx=2, text="(n = 8636)"),
            TableCell(row_idx=1, col_idx=3, text="(n = 618)"),
            TableCell(row_idx=2, col_idx=0, text="Race, n"),
            TableCell(row_idx=2, col_idx=1, text="(%)"),
            TableCell(row_idx=2, col_idx=4, text="<0.001"),
            TableCell(row_idx=3, col_idx=0, text="Mexican"),
            TableCell(row_idx=3, col_idx=1, text="American"),
            TableCell(row_idx=3, col_idx=2, text="1852 (21.22%)"),
            TableCell(row_idx=3, col_idx=3, text="98 (15.86%)"),
            TableCell(row_idx=4, col_idx=0, text="Other"),
            TableCell(row_idx=4, col_idx=1, text="Hispanic"),
            TableCell(row_idx=4, col_idx=2, text="339 (3.88%)"),
            TableCell(row_idx=4, col_idx=3, text="15 (2.43%)"),
            TableCell(row_idx=5, col_idx=0, text="Non-Hispanic"),
            TableCell(row_idx=5, col_idx=1, text="White"),
            TableCell(row_idx=5, col_idx=2, text="4689 (53.74%)"),
            TableCell(row_idx=5, col_idx=3, text="353 (57.12%)"),
            TableCell(row_idx=6, col_idx=0, text="Non-Hispanic"),
            TableCell(row_idx=6, col_idx=1, text="Black"),
            TableCell(row_idx=6, col_idx=2, text="1578 (18.08%)"),
            TableCell(row_idx=6, col_idx=3, text="138 (22.33%)"),
        ],
        extraction_backend="pymupdf4llm",
    )

    normalized = normalize_extracted_table(extracted)

    assert normalized.metadata["cleaned_rows"][2][0] == "Race, n (%)"
    assert normalized.metadata["cleaned_rows"][3][0] == "Mexican American"
    assert normalized.metadata["cleaned_rows"][4][0] == "Other Hispanic"
    assert normalized.metadata["cleaned_rows"][5][0] == "Non-Hispanic White"
    assert normalized.metadata["cleaned_rows"][6][0] == "Non-Hispanic Black"
    assert [row_view.first_cell_raw for row_view in normalized.row_views] == [
        "Race, n (%)",
        "Mexican American",
        "Other Hispanic",
        "Non-Hispanic White",
        "Non-Hispanic Black",
    ]
    assert normalized.metadata["column_repairs"]["merged_split_label_columns"] == [
        {"from_col_idx": 1, "to_col_idx": 0, "merged_row_count": 5}
    ]


def test_normalization_expands_extra_wide_stacked_value_column() -> None:
    """A visually wide upright table collapsed into one value stack should regain its value columns."""
    rows = [
        ["", "Severity of AL, %"],
        ["Characteristics", "‡3 mm\nSE\n‡4 mm\nSE\n‡5 mm\nSE\n‡6 mm\nSE\n‡7 mm\nSE\nMean AL, mm\nSE"],
        ["Total", "88.1\n0.8\n60.8\n1.6\n40.9\n1.4\n24.2\n1.0\n14.7\n0.6\n1.72\n0.03"],
        ["Age (mean: 24 teeth)", ""],
        ["30 to 34 years", "72.3\n1.8\n32.6\n2.3\n16.4\n1.8\n8.3\n1.0\n3.2\n0.7\n1.23\n0.04"],
        ["35 to 49 years", "85.7\n1.1\n51.8\n2.2\n32.4\n1.9\n17.0\n1.2\n10.4\n0.8\n1.52\n0.04"],
    ]
    extracted = ExtractedTable(
        table_id="tbl-extra-wide",
        source_pdf="paper.pdf",
        page_num=1,
        n_rows=len(rows),
        n_cols=2,
        cells=[
            TableCell(row_idx=row_idx, col_idx=col_idx, text=value)
            for row_idx, row in enumerate(rows)
            for col_idx, value in enumerate(row)
        ],
        extraction_backend="pymupdf4llm",
        metadata={
            "row_bounds": [(float(idx * 10), float(idx * 10 + 8)) for idx in range(len(rows))],
            "horizontal_rules": [float(idx * 10) for idx in range(len(rows) + 1)],
        },
    )

    normalized = normalize_extracted_table(extracted)

    repair = normalized.metadata["column_repairs"]["extra_wide_value_column"]
    assert normalized.n_cols == 13
    assert normalized.header_rows == [0, 1]
    assert normalized.metadata["header_detection"]["source"] == "extra_wide_value_column_boundary"
    assert normalized.metadata["cleaned_rows"][0][1:] == ["Severity of AL, %"] * 12
    assert normalized.metadata["cleaned_rows"][1][1:5] == ["‡3 mm", "SE", "‡4 mm", "SE"]
    assert normalized.metadata["cleaned_rows"][2][1:] == [
        "88.1",
        "0.8",
        "60.8",
        "1.6",
        "40.9",
        "1.4",
        "24.2",
        "1.0",
        "14.7",
        "0.6",
        "1.72",
        "0.03",
    ]
    assert repair["created_value_columns"] == 12
    assert repair["first_value_row_idx"] == 2
    assert repair["header_stack_row_indices"] == [0, 1]


def test_normalization_expands_grouped_extra_wide_header_stack() -> None:
    """Coarser header stacks should repeat over paired value/statistic leaf columns."""
    rows = [
        ["", "Severity"],
        ["", "‡3 mm\n‡4 mm\n‡5 mm\n‡6 mm\n‡7 mm"],
        ["Extent", "%\nSE\n%\nSE\n%\nSE\n%\nSE\n%\nSE"],
        ["Site specific", ""],
        ["PD", ""],
        ["‡5% sites", "44.9\n2.2\n17.0\n0.9\n6.3\n0.6\n2.4\n0.3\n0.6\n0.09"],
        ["‡10% sites", "31.2\n1.8\n10.6\n0.6\n3.1\n0.4\n1.2\n0.2\n0.2\n0.05"],
        ["Mean", "11.9\n0.7\n3.8\n0.2\n1.2\n0.1\n0.5\n0.05\n0.1\n0.01"],
    ]
    extracted = ExtractedTable(
        table_id="tbl-extra-wide-grouped",
        source_pdf="paper.pdf",
        page_num=1,
        n_rows=len(rows),
        n_cols=2,
        cells=[
            TableCell(row_idx=row_idx, col_idx=col_idx, text=value)
            for row_idx, row in enumerate(rows)
            for col_idx, value in enumerate(row)
        ],
        extraction_backend="pymupdf4llm",
    )

    normalized = normalize_extracted_table(extracted)

    repair = normalized.metadata["column_repairs"]["extra_wide_value_column"]
    assert normalized.n_cols == 11
    assert normalized.header_rows == [0, 1, 2]
    assert normalized.metadata["cleaned_rows"][0][1:] == ["Severity"] * 10
    assert normalized.metadata["cleaned_rows"][1][1:7] == ["‡3 mm", "‡3 mm", "‡4 mm", "‡4 mm", "‡5 mm", "‡5 mm"]
    assert normalized.metadata["cleaned_rows"][2][1:7] == ["%", "SE", "%", "SE", "%", "SE"]
    assert repair["created_value_columns"] == 10
    assert repair["header_stack_row_indices"] == [0, 1, 2]
    assert repair["repeated_header_row_indices"] == [0, 1]


def test_normalization_chunks_multi_line_extra_wide_leaf_headers() -> None:
    """Dense stacked header rows can carry several lines per visual value column."""
    rows = [
        ["Characteristic", "US NHANES\nUS NHANES\nUKB\nUKB"],
        [
            "",
            "Quintile 1\n(10-35)\nN = 10\nQuintile 2\n(35-43)\nN = 11\n"
            "Quintile 1\n(17-52)\nN = 20\nQuintile 2\n(52-60)\nN = 21",
        ],
        ["Age", "1\n2\n3\n4"],
        ["Male", "5\n6\n7\n8"],
        ["Female", "9\n10\n11\n12"],
    ]
    extracted = ExtractedTable(
        table_id="tbl-extra-wide-chunked-headers",
        source_pdf="paper.pdf",
        page_num=1,
        n_rows=len(rows),
        n_cols=2,
        cells=[
            TableCell(row_idx=row_idx, col_idx=col_idx, text=value)
            for row_idx, row in enumerate(rows)
            for col_idx, value in enumerate(row)
        ],
        extraction_backend="pymupdf4llm",
    )

    normalized = normalize_extracted_table(extracted)

    repair = normalized.metadata["column_repairs"]["extra_wide_value_column"]
    assert normalized.n_cols == 5
    assert normalized.header_rows == [0, 1]
    assert normalized.metadata["cleaned_rows"][0][1:] == ["US NHANES", "US NHANES", "UKB", "UKB"]
    assert normalized.metadata["cleaned_rows"][1][1:] == [
        "Quintile 1 (10-35) N = 10",
        "Quintile 2 (35-43) N = 11",
        "Quintile 1 (17-52) N = 20",
        "Quintile 2 (52-60) N = 21",
    ]
    assert repair["created_value_columns"] == 4
    assert repair["header_stack_row_indices"] == [0, 1]
    assert repair["padded_or_truncated_row_indices"] == []


def test_normalization_trims_sparse_caption_tail_before_value_matrix_header() -> None:
    """A sparse leading note should not become the header when a denser header band follows."""
    rows = [
        ["poverty; GHGe,", "greenhouse gas emissions.", "", "", ""],
        ["Characteristic", "Group A", "Group A", "Group B", "Group B"],
        ["", "Q1", "Q2", "Q1", "Q2"],
        ["", "N = 10", "N = 11", "N = 20", "N = 21"],
        ["Age", "1", "2", "3", "4"],
        ["Male", "5", "6", "7", "8"],
    ]
    extracted = ExtractedTable(
        table_id="tbl-leading-note-before-header",
        source_pdf="paper.pdf",
        page_num=1,
        n_rows=len(rows),
        n_cols=len(rows[0]),
        cells=[
            TableCell(row_idx=row_idx, col_idx=col_idx, text=value)
            for row_idx, row in enumerate(rows)
            for col_idx, value in enumerate(row)
        ],
        extraction_backend="pymupdf4llm",
    )

    normalized = normalize_extracted_table(extracted)

    assert normalized.header_rows == [1, 2, 3]
    assert 0 not in normalized.body_rows
    assert normalized.metadata["header_detection"]["source"] == "value_matrix_boundary"
    assert normalized.metadata["header_detection"]["value_matrix_first_value_row_idx"] == 4


def test_normalization_repairs_embedded_label_count_in_first_value_column() -> None:
    """Label tails that share the first value cell with a count should move back to the label column."""
    rows = [
        ["Characteristics", "n", "%", "SE"],
        ["Income", "", "", ""],
        ["<100%", "FPL 625", "13.5", "0.8"],
        ["Never", "married 390", "10.4", "0.7"],
    ]
    extracted = ExtractedTable(
        table_id="tbl-embedded-label-count",
        source_pdf="paper.pdf",
        page_num=1,
        n_rows=len(rows),
        n_cols=len(rows[0]),
        cells=[
            TableCell(row_idx=row_idx, col_idx=col_idx, text=value)
            for row_idx, row in enumerate(rows)
            for col_idx, value in enumerate(row)
        ],
        extraction_backend="pymupdf4llm",
    )

    normalized = normalize_extracted_table(extracted)

    repair = normalized.metadata["column_repairs"]["embedded_label_count_cells"]
    assert normalized.metadata["cleaned_rows"][2] == ["<100% FPL", "625", "13.5", "0.8"]
    assert normalized.metadata["cleaned_rows"][3] == ["Never married", "390", "10.4", "0.7"]
    assert repair["repaired_row_indices"] == [2, 3]


def test_normalization_repairs_two_column_row_label_field_without_shifted_blanks() -> None:
    """A dense two-column row-label field should merge even when labels are not shifted right."""
    rows = [
        ["Characteristics", "", "n", "Weighted n", "Severe, %", "SE"],
        ["NHANES", "2009 to 2012", "7,066", "141.0", "8.9", "0.6"],
        ["Age (mean:", "24 teeth)", "", "", "", ""],
        ["30 to", "34 years", "846", "16.6", "4.0", "0.9"],
        ["Race/ethnic", "group", "", "", "", ""],
        ["Non-Hispanic", "Asian American§", "478", "7.6", "12.3", "1.1"],
        ["Less", "than high school", "1,784", "23.1", "11.8", "1.0"],
        ["Marital", "status", "", "", "", ""],
        ["Living", "with partner", "495", "9.2", "8.1", "0.8"],
    ]
    extracted = ExtractedTable(
        table_id="tbl-two-col-labels",
        source_pdf="paper.pdf",
        page_num=1,
        n_rows=len(rows),
        n_cols=len(rows[0]),
        cells=[
            TableCell(row_idx=row_idx, col_idx=col_idx, text=value)
            for row_idx, row in enumerate(rows)
            for col_idx, value in enumerate(row)
        ],
        extraction_backend="pymupdf4llm",
    )

    normalized = normalize_extracted_table(extracted)

    repair = normalized.metadata["column_repairs"]["split_row_label_field_columns"]
    assert normalized.n_cols == 5
    assert normalized.metadata["cleaned_rows"][2][0] == "Age (mean: 24 teeth)"
    assert normalized.metadata["cleaned_rows"][3] == ["30 to 34 years", "846", "16.6", "4.0", "0.9"]
    assert normalized.metadata["cleaned_rows"][5] == ["Non-Hispanic Asian American§", "478", "7.6", "12.3", "1.1"]
    assert normalized.metadata["cleaned_rows"][8] == ["Living with partner", "495", "9.2", "8.1", "0.8"]
    assert repair["merged_label_row_indices"] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert repair["evidence"]["merged_label_row_count"] == 5


def test_normalization_merges_vertical_label_continuation_rows() -> None:
    """Label-only continuation rows should merge into the preceding valued row and leave the body."""
    rows = [
        ["Characteristics", "n", "Weighted n", "Periodontitis"],
        ["All (NHANES", "3,743", "137.1", "46.1"],
        ["2009 to 2012)", "", "", ""],
        ["NHANES 2001 to", "3,733", "136.8", "46.3"],
        ["2004 protocol†", "", "", ""],
        ["Non-Hispanic Asian", "N/A", "N/A", "N/A"],
        ["American¶", "", "", ""],
    ]
    extracted = ExtractedTable(
        table_id="tbl-vertical-continuations",
        source_pdf="paper.pdf",
        page_num=1,
        n_rows=len(rows),
        n_cols=len(rows[0]),
        cells=[
            TableCell(row_idx=row_idx, col_idx=col_idx, text=value)
            for row_idx, row in enumerate(rows)
            for col_idx, value in enumerate(row)
        ],
        extraction_backend="pymupdf4llm",
    )

    normalized = normalize_extracted_table(extracted)

    repair = normalized.metadata["column_repairs"]["vertical_label_continuations"]
    assert normalized.metadata["cleaned_rows"][1][0] == "All (NHANES 2009 to 2012)"
    assert normalized.metadata["cleaned_rows"][3][0] == "NHANES 2001 to 2004 protocol†"
    assert normalized.metadata["cleaned_rows"][5][0] == "Non-Hispanic Asian American¶"
    assert {2, 4, 6}.isdisjoint(normalized.body_rows)
    assert repair["removed_continuation_row_indices"] == [2, 4, 6]


def test_normalization_merges_leading_label_fragment_into_following_valued_row() -> None:
    """A wrapped label line can appear immediately above the row containing its values."""
    rows = [
        ["Characteristics", "Overall", "Group 1", "Group 2"],
        ["SI (31025 min21", "", "", ""],
        ["per pmol/L)", "4.4 6 0.14", "7.1 6 0.11", "11.9 6 0.52"],
        ["AIRg (pmol/L)", "997 6 36.2", "396 6 7.5", "265 6 13.7"],
    ]
    extracted = ExtractedTable(
        table_id="tbl-leading-continuation",
        source_pdf="paper.pdf",
        page_num=1,
        n_rows=len(rows),
        n_cols=len(rows[0]),
        cells=[
            TableCell(row_idx=row_idx, col_idx=col_idx, text=value)
            for row_idx, row in enumerate(rows)
            for col_idx, value in enumerate(row)
        ],
        extraction_backend="pymupdf4llm",
    )

    normalized = normalize_extracted_table(extracted)

    repair = normalized.metadata["column_repairs"]["vertical_label_continuations"]
    assert normalized.metadata["cleaned_rows"][2][0] == "SI (31025 min21 per pmol/L)"
    assert 1 not in normalized.body_rows
    assert repair["merged_rows"] == [{"from_row_idx": 1, "to_row_idx": 2}]
    assert repair["removed_continuation_row_indices"] == [1]


def test_normalization_does_not_merge_header_leaf_into_n_row() -> None:
    """Header labels above an n row are not row-label continuations."""
    rows = [
        ["", "African", "Caucasian", "East Asian"],
        ["n", "688", "2,177", "205"],
        ["Age (years)", "25.9 6 3.6", "31.2 6 2.7", "32.6 6 2.9"],
    ]
    extracted = ExtractedTable(
        table_id="tbl-header-leaf-n-row",
        source_pdf="paper.pdf",
        page_num=1,
        n_rows=len(rows),
        n_cols=len(rows[0]),
        cells=[
            TableCell(row_idx=row_idx, col_idx=col_idx, text=value)
            for row_idx, row in enumerate(rows)
            for col_idx, value in enumerate(row)
        ],
        extraction_backend="pymupdf4llm",
    )

    normalized = normalize_extracted_table(extracted)

    assert normalized.metadata["cleaned_rows"][1][0] == "n"
    assert normalized.metadata["column_repairs"]["vertical_label_continuations"] is None


def test_normalization_does_not_merge_na_value_cells_into_label_continuations() -> None:
    """N/A-like value cells should not be mistaken for second-column label fragments."""
    rows = [
        ["Characteristics", "n", "Weighted n", "Periodontitis"],
        ["Non-Hispanic Asian", "N/A", "N/A", "N/A"],
        ["American¶", "", "", ""],
    ]
    extracted = ExtractedTable(
        table_id="tbl-na-continuation",
        source_pdf="paper.pdf",
        page_num=1,
        n_rows=len(rows),
        n_cols=len(rows[0]),
        cells=[
            TableCell(row_idx=row_idx, col_idx=col_idx, text=value)
            for row_idx, row in enumerate(rows)
            for col_idx, value in enumerate(row)
        ],
        extraction_backend="pymupdf4llm",
    )

    normalized = normalize_extracted_table(extracted)

    assert normalized.metadata["cleaned_rows"][1][0] == "Non-Hispanic Asian American¶"
    assert normalized.metadata["cleaned_rows"][1][1:] == ["N/A", "N/A", "N/A"]


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


def test_normalization_keeps_sparse_footnoted_p_value_column() -> None:
    """A sparse rightmost p-value column is data, not trailing page noise."""
    rows = [
        ["", "Lifestyle score", "", "", ""],
        ["", "Low (n = 2561)", "Middle (n = 2076)", "High (n = 2297)", "p"],
        ["Age, years", "36.0", "44.0", "45.0", "< 0.001b"],
        ["< 65y", "2396 (93.6%)", "1772 (85.4%)", "1908 (83.1%)", ""],
        [">= 65y", "165 (6.4%)", "304 (14.6%)", "389 (16.9%)", ""],
        ["Gender", "", "", "", "< 0.001a"],
        ["Men", "1450 (56.6%)", "987 (47.5%)", "1131 (49.2%)", ""],
        ["Women", "1111 (43.4%)", "1089 (52.5%)", "1166 (50.8%)", ""],
        ["Healthy diet", "172 (6.7%)", "1597 (76.9%)", "1540 (67.0%)", "< 0.001a"],
    ]
    extracted = ExtractedTable(
        table_id="tbl-p-values",
        source_pdf="paper.pdf",
        page_num=1,
        title="Table 1",
        caption="Baseline characteristics",
        n_rows=len(rows),
        n_cols=len(rows[0]),
        cells=[
            TableCell(row_idx=row_idx, col_idx=col_idx, text=value)
            for row_idx, row in enumerate(rows)
            for col_idx, value in enumerate(row)
        ],
        extraction_backend="pymupdf4llm",
    )

    normalized = normalize_extracted_table(extracted)

    assert normalized.n_cols == 5
    assert normalized.metadata["cleaned_rows"][1] == ["", "Low (n = 2561)", "Middle (n = 2076)", "High (n = 2297)", "p"]
    assert normalized.metadata["cleaned_rows"][2][4] == "< 0.001b"
    assert normalized.metadata["cleaned_rows"][5][4] == "< 0.001a"
    assert normalized.metadata["source_col_indices"] == [0, 1, 2, 3, 4]


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


def test_sparse_stub_label_column_is_removed_before_row_signatures() -> None:
    """Sparse section stubs should not hide a dense second-column row-label field."""
    extracted = ExtractedTable(
        table_id="tbl-sparse-stub-label",
        source_pdf="paper.pdf",
        page_num=1,
        n_rows=9,
        n_cols=4,
        cells=[
            TableCell(row_idx=0, col_idx=0, text="Characteristics"),
            TableCell(row_idx=0, col_idx=1, text=""),
            TableCell(row_idx=0, col_idx=2, text="White"),
            TableCell(row_idx=0, col_idx=3, text="Black"),
            TableCell(row_idx=1, col_idx=0, text=""),
            TableCell(row_idx=1, col_idx=1, text=""),
            TableCell(row_idx=1, col_idx=2, text="(n = 10)"),
            TableCell(row_idx=1, col_idx=3, text="(n = 20)"),
            TableCell(row_idx=2, col_idx=0, text="Outcomes"),
            TableCell(row_idx=2, col_idx=1, text=""),
            TableCell(row_idx=2, col_idx=2, text=""),
            TableCell(row_idx=2, col_idx=3, text=""),
            TableCell(row_idx=3, col_idx=0, text=""),
            TableCell(row_idx=3, col_idx=1, text="Systolic blood pressure (mmHg)"),
            TableCell(row_idx=3, col_idx=2, text="126.5 ± 21.6"),
            TableCell(row_idx=3, col_idx=3, text="125.4 ± 21.6"),
            TableCell(row_idx=4, col_idx=0, text=""),
            TableCell(row_idx=4, col_idx=1, text="Hypertension diagnosis [n (%)]"),
            TableCell(row_idx=4, col_idx=2, text="1917 (29.8)"),
            TableCell(row_idx=4, col_idx=3, text="1297 (31.3)"),
            TableCell(row_idx=5, col_idx=0, text="Covariates"),
            TableCell(row_idx=5, col_idx=1, text=""),
            TableCell(row_idx=5, col_idx=2, text=""),
            TableCell(row_idx=5, col_idx=3, text=""),
            TableCell(row_idx=6, col_idx=0, text=""),
            TableCell(row_idx=6, col_idx=1, text="Age (years)"),
            TableCell(row_idx=6, col_idx=2, text="54.7 ± 19.9"),
            TableCell(row_idx=6, col_idx=3, text="43.6 ± 17.2"),
            TableCell(row_idx=7, col_idx=0, text="Poverty"),
            TableCell(row_idx=7, col_idx=1, text="income ratio"),
            TableCell(row_idx=7, col_idx=2, text="3.2 ± 1.9"),
            TableCell(row_idx=7, col_idx=3, text="2.0 ± 1.5"),
            TableCell(row_idx=8, col_idx=0, text=""),
            TableCell(row_idx=8, col_idx=1, text="Blood lead (μg/dL)"),
            TableCell(row_idx=8, col_idx=2, text="3.7 ± 2.9"),
            TableCell(row_idx=8, col_idx=3, text="4.4 ± 4.0"),
        ],
        extraction_backend="pymupdf4llm",
    )

    normalized = normalize_extracted_table(extracted)

    repair = normalized.metadata["column_repairs"]["sparse_stub_label_column"]
    assert normalized.n_cols == 3
    assert normalized.metadata["dropped_leading_cols"] == 1
    assert repair["removed_stub_row_indices"] == [2, 5]
    assert repair["merged_label_row_indices"] == [7]
    assert 2 not in normalized.body_rows
    assert 5 not in normalized.body_rows
    assert normalized.metadata["cleaned_rows"][3][0] == "Systolic blood pressure (mmHg)"
    assert normalized.metadata["cleaned_rows"][7][0] == "Poverty income ratio"
    assert [row_view.first_cell_raw for row_view in normalized.row_views] == [
        "Systolic blood pressure (mmHg)",
        "Hypertension diagnosis [n (%)]",
        "Age (years)",
        "Poverty income ratio",
        "Blood lead (μg/dL)",
    ]


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
