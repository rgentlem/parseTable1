"""Tests for parser-native column header schemas."""

from __future__ import annotations

import pytest

from table1_parser.column_header_schema import (
    build_column_header_schema,
    column_header_comparison_labels,
    column_header_descriptors,
    column_header_labels,
)
from table1_parser.heuristics.table_definition_builder import build_table_definition
from table1_parser.schemas import (
    ColumnHeaderCellEvidence,
    ColumnHeaderGroup,
    ColumnHeaderLeaf,
    ColumnHeaderRelationship,
    ColumnHeaderSchema,
    ExtractedTable,
    NormalizedTable,
    RowView,
    TableCell,
)
from table1_parser.validation.column_header_schema import validate_column_header_schema


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


def _normalized_table(
    table_id: str,
    rows: list[list[str]],
    *,
    header_rows: list[int],
    body_rows: list[int] | None = None,
) -> NormalizedTable:
    effective_body_rows = body_rows if body_rows is not None else [idx for idx in range(len(rows)) if idx not in header_rows]
    return NormalizedTable(
        table_id=table_id,
        title="Table 1",
        caption="Baseline characteristics",
        header_rows=header_rows,
        body_rows=effective_body_rows,
        row_views=[_row_view(row_idx, rows[row_idx]) for row_idx in effective_body_rows],
        n_rows=len(rows),
        n_cols=max(len(row) for row in rows) if rows else 0,
        metadata={"cleaned_rows": rows, "source_page_num": 3},
    )


def _extracted_table(table_id: str, rows: list[list[str]]) -> ExtractedTable:
    cells: list[TableCell] = []
    for row_idx, row in enumerate(rows):
        for col_idx, value in enumerate(row):
            cells.append(
                TableCell(
                    row_idx=row_idx,
                    col_idx=col_idx,
                    text=value,
                    page_num=3,
                    bbox=(float(col_idx * 10), float(row_idx * 5), float(col_idx * 10 + 8), float(row_idx * 5 + 4)),
                )
            )
    return ExtractedTable(
        table_id=table_id,
        source_pdf="paper.pdf",
        page_num=3,
        n_rows=len(rows),
        n_cols=max(len(row) for row in rows) if rows else 0,
        cells=cells,
        extraction_backend="test",
    )


def test_build_schema_for_simple_one_row_table() -> None:
    """A simple table should expose one leaf per normalized column."""
    rows = [
        ["Characteristic", "Overall", "RA", "P-value"],
        ["Age, years", "52.3", "51.2", "0.03"],
    ]
    table = _normalized_table("tbl-simple", rows, header_rows=[0])
    schema = build_column_header_schema(table, _extracted_table("tbl-simple", rows))

    assert [leaf.leaf_label for leaf in schema.leaves] == ["Characteristic", "Overall", "RA", "P-value"]
    assert schema.groups == []
    assert schema.relationships == []
    assert schema.leaves[0].is_row_label_column is True
    assert schema.leaves[1].coordinate_center == 14.0
    assert schema.evidence[0].raw_text == "Characteristic"


def test_build_schema_collapses_multirow_group_headers() -> None:
    """Repeated higher labels should become one spanning group over leaf columns."""
    rows = [
        ["Characteristic", "", "Cobalt quartile", "Cobalt quartile", "", ""],
        ["", "Overall", "Q1", "Q2", "P-value", "P for trend"],
        ["Age, years", "52.3", "50.4", "51.1", "0.03", "0.01"],
    ]
    table = _normalized_table("tbl-cobalt", rows, header_rows=[0, 1])
    schema = build_column_header_schema(table, _extracted_table("tbl-cobalt", rows))

    assert schema.leaf_header_row_idx == 1
    assert [(group.label, group.col_start, group.col_end, group.inference_rule) for group in schema.groups] == [
        ("Cobalt quartile", 2, 3, "repeated_label_span")
    ]
    labels = column_header_labels(schema)
    assert labels[2] == "Cobalt quartile Q1"
    assert labels[3] == "Cobalt quartile Q2"
    descriptors = column_header_descriptors(schema)
    assert descriptors[2].column_label == "Cobalt quartile Q1"
    assert descriptors[2].shared_context_label == "Cobalt quartile"
    assert descriptors[2].column_name == "Cobalt quartile Q1"
    assert descriptors[2].leaf_label == "Q1"
    assert column_header_comparison_labels(schema)[2] == "cobalt quartile q1"

    definition = build_table_definition(table, schema)

    assert definition.column_definition.grouping_label == "Cobalt quartile"
    assert [column.group_level_label for column in definition.column_definition.columns[:3]] == [None, "Q1", "Q2"]


def test_build_schema_preserves_extra_wide_header_stack() -> None:
    """Stacked repaired headers should keep both upper grouping layers."""
    rows = [
        ["", "Severity", "Severity", "Severity", "Severity"],
        ["", ">=3 mm", ">=3 mm", ">=4 mm", ">=4 mm"],
        ["Extent", "%", "SE", "%", "SE"],
        ["Total", "88.1", "0.8", "60.8", "1.6"],
    ]
    table = _normalized_table("tbl-extra-wide", rows, header_rows=[0, 1, 2])
    schema = build_column_header_schema(table, _extracted_table("tbl-extra-wide", rows))

    assert [(group.label, group.col_start, group.col_end) for group in schema.groups] == [
        ("Severity", 1, 4),
        (">=3 mm", 1, 2),
        (">=4 mm", 3, 4),
    ]
    labels = column_header_labels(schema)
    assert labels[1] == "Severity >=3 mm %"
    assert labels[2] == "Severity >=3 mm SE"


def test_build_schema_uses_internal_header_rule_for_wrapped_leaf_stack() -> None:
    """A rule inside the header separates spanning groups from wrapped leaf labels."""
    rows = [
        ["Characteristic", "Group A", "Group A", "Group B", "Group B"],
        ["", "Q1", "Q2", "Q1", "Q2"],
        ["", "(10-35)", "(35-43)", "(17-52)", "(52-60)"],
        ["", "N = 10", "N = 11", "N = 20", "N = 21"],
        ["Age", "43", "46", "57", "58"],
    ]
    table = _normalized_table("tbl-internal-header-rule", rows, header_rows=[0, 1, 2, 3], body_rows=[4])
    table.metadata["row_bounds"] = [(0.0, 5.0), (10.0, 15.0), (16.0, 21.0), (22.0, 27.0), (35.0, 40.0)]
    table.metadata["horizontal_rules"] = [7.0, 30.0]

    schema = build_column_header_schema(table, _extracted_table("tbl-internal-header-rule", rows))

    assert [leaf.leaf_label for leaf in schema.leaves] == [
        "Characteristic",
        "Q1 (10-35) N = 10",
        "Q2 (35-43) N = 11",
        "Q1 (17-52) N = 20",
        "Q2 (52-60) N = 21",
    ]
    assert [(group.label, group.col_start, group.col_end) for group in schema.groups] == [
        ("Group A", 1, 2),
        ("Group B", 3, 4),
    ]
    assert "split_wrapped_leaf_header_rows_by_rule:rows=1,2,3" in schema.diagnostics


def test_build_schema_splits_value_region_group_headers_by_geometry_gap() -> None:
    """A value-only group row can start after the row-label column and split at a large gap."""
    rows = [
        ["Characteristic", "Group", "A", "Label", "Group", "B"],
        ["", "Q1", "Q2", "Q3", "Q1", "Q2"],
        ["", "N = 10", "N = 11", "N = 12", "N = 20", "N = 21"],
        ["Age", "43", "46", "48", "57", "58"],
    ]
    table = _normalized_table("tbl-value-region-gap", rows, header_rows=[0, 1, 2], body_rows=[3])
    table.metadata["row_bounds"] = [(0.0, 5.0), (10.0, 15.0), (16.0, 21.0), (30.0, 35.0)]
    table.metadata["horizontal_rules"] = [7.0, 24.0]
    table.metadata["table_cells"] = [
        [
            [0.0, 0.0, 40.0, 5.0],
            [100.0, 0.0, 130.0, 5.0],
            [132.0, 0.0, 150.0, 5.0],
            [152.0, 0.0, 180.0, 5.0],
            [250.0, 0.0, 280.0, 5.0],
            [282.0, 0.0, 300.0, 5.0],
        ],
        [None, None, None, None, None, None],
        [None, None, None, None, None, None],
        [None, None, None, None, None, None],
    ]

    schema = build_column_header_schema(table, _extracted_table("tbl-value-region-gap", rows))

    assert [(group.label, group.col_start, group.col_end, group.inference_rule) for group in schema.groups] == [
        ("Group A Label", 1, 3, "explicit_cell_span"),
        ("Group B", 4, 5, "explicit_cell_span"),
    ]
    labels = column_header_labels(schema)
    assert labels[1] == "Group A Label Q1 N = 10"
    assert labels[4] == "Group B Q1 N = 20"


def test_build_schema_skips_eke_table1_title_like_header_rows() -> None:
    """Eke-like table title rows should not become spanning groups over leaves."""
    rows = [
        [
            "Prevalence of Total Periodontitis",
            "Using NHANES Data",
            "by Selected Characteristics",
            "and Individual NHANES Cycles",
            "for Individuals Aged >=30 Years",
            "in the United States, 2009 to 2012",
        ],
        ["Characteristics", "n", "Weighted n", "Periodontitis", "SE", "NHANES 2009 to 2010"],
        ["Total", "3743", "137.1", "46.1", "1.7", "47.2"],
    ]
    table = _normalized_table("tbl-eke-1", rows, header_rows=[0, 1])
    schema = build_column_header_schema(table, _extracted_table("tbl-eke-1", rows))

    assert schema.groups == []
    assert column_header_labels(schema)[3] == "Periodontitis"
    assert "skipped_title_like_leaf_header_row:row=0" in schema.diagnostics


def test_build_schema_recovers_eke_headers_when_caption_is_only_header_row() -> None:
    """If normalization marks only an Eke caption row as header, infer the real header stack."""
    rows = [
        [
            "Prevalence of Respective Periodontitis",
            "",
            "Categories",
            "by CDC/AAP",
            "and",
            "EFP Case",
            "Definitions",
        ],
        ["Years by Selected Characteristics:", "", "NHANES 2009", "to 2012", "", "", ""],
        ["", "", "", "Periodontitis", "(CDC/AAP Case Definitions)", "Periodontitis", "(EFP Case Definitions)"],
        ["Characteristics", "n", "Weighted n (millions)", "Severe, %", "SE", "Severe, %", "SE"],
        ["NHANES 2009 to 2012", "7066", "141.0", "8.9", "0.6", "12.0", "0.7"],
    ]
    table = _normalized_table("tbl-eke-recover", rows, header_rows=[0], body_rows=[1, 2, 3, 4])
    table.metadata["row_bounds"] = [(0.0, 5.0), (6.0, 11.0), (30.0, 35.0), (42.0, 47.0), (60.0, 65.0)]
    table.metadata["horizontal_rules"] = [20.0, 55.0]
    schema = build_column_header_schema(table, _extracted_table("tbl-eke-recover", rows))

    assert schema.leaf_header_row_idx == 3
    assert schema.body_rows_considered == [4]
    assert schema.groups[0].label == "Periodontitis (CDC/AAP Case Definitions)"
    assert column_header_labels(schema)[3] == "Periodontitis (CDC/AAP Case Definitions) Severe, %"
    assert "inferred_header_rows_from_body_values:rows=2,3" in schema.diagnostics
    assert "trimmed_body_rows_after_inferred_headers:start=4" in schema.diagnostics


def test_build_schema_for_eke_table2_case_definition_groups() -> None:
    """Eke Table 2-like case-definition headers should span their category leaves."""
    rows = [
        [
            "Characteristics",
            "Periodontitis (CDC/AAP Case Definitions)",
            "",
            "",
            "Periodontitis (EFP Case Definitions)",
            "",
            "",
        ],
        ["", "Mild", "Moderate", "Severe", "Stage I", "Stage II", "Stage III"],
        ["Total", "8.7", "30.0", "8.9", "12.0", "20.4", "14.2"],
    ]
    table = _normalized_table("tbl-eke-2", rows, header_rows=[0, 1])
    schema = build_column_header_schema(table, _extracted_table("tbl-eke-2", rows))

    assert [(group.label, group.col_start, group.col_end, group.inference_rule) for group in schema.groups] == [
        ("Periodontitis (CDC/AAP Case Definitions)", 1, 3, "single_cell_blank_span"),
        ("Periodontitis (EFP Case Definitions)", 4, 6, "single_cell_blank_span"),
    ]
    labels = column_header_labels(schema)
    assert labels[1] == "Periodontitis (CDC/AAP Case Definitions) Mild"
    assert labels[4] == "Periodontitis (EFP Case Definitions) Stage I"


def test_build_schema_moves_geometric_leading_leaf_fragment_to_previous_column() -> None:
    """A short leading fragment left of the column boundary belongs to the prior leaf."""
    rows = [
        ["Long table title", "", "", ""],
        ["Characteristic", "n", "Weighted", "n Periodontitis"],
        ["", "", "(millions)", "(% - SE)"],
        ["Total", "10", "1.5", "40 - 2"],
    ]
    table = _normalized_table("tbl-leaf-geometry", rows, header_rows=[0], body_rows=[1, 2, 3])
    table.metadata["row_bounds"] = [(0.0, 5.0), (10.0, 15.0), (16.0, 21.0), (30.0, 35.0)]
    table.metadata["horizontal_rules"] = [8.0, 25.0]
    table.metadata["source_col_indices"] = [0, 1, 2, 3]
    table.metadata["table_cells"] = [
        [None, None, None, None],
        [[10.0, 10.0, 70.0, 15.0], [80.0, 10.0, 90.0, 15.0], [100.0, 10.0, 110.0, 15.0], [112.0, 10.0, 162.0, 15.0]],
        [None, None, [100.0, 16.0, 125.0, 21.0], [130.0, 16.0, 170.0, 21.0]],
        [[10.0, 30.0, 35.0, 35.0], [80.0, 30.0, 90.0, 35.0], [100.0, 30.0, 125.0, 35.0], [130.0, 30.0, 170.0, 35.0]],
    ]

    schema = build_column_header_schema(table, _extracted_table("tbl-leaf-geometry", rows))

    assert [leaf.leaf_label for leaf in schema.leaves] == [
        "Characteristic",
        "n",
        "Weighted n (millions)",
        "Periodontitis (% - SE)",
    ]
    moved_evidence_ids = set(schema.leaves[2].evidence_ids)
    assert any(
        evidence.evidence_id in moved_evidence_ids and evidence.row_idx == 1 and evidence.col_idx == 3
        for evidence in schema.evidence
    )


def test_build_schema_preserves_dense_declared_leaf_header_row() -> None:
    """Long repeated leaf labels should not be discarded as title text."""
    rows = [
        ["Characteristic", "Shared group", "Shared group", "Shared group", "Shared group"],
        [
            "",
            "Quintile 1 (10-35), N = 10,737",
            "Quintile 2 (35-43), N = 10,737",
            "Quintile 3 (43-51), N = 10,736",
            "Quintile 4 (51-95), N = 10,737",
        ],
        ["Age", "10", "11", "12", "13"],
    ]
    table = _normalized_table("tbl-dense-leaf-header", rows, header_rows=[0, 1])
    schema = build_column_header_schema(table, _extracted_table("tbl-dense-leaf-header", rows))

    assert schema.leaf_header_row_idx == 1
    assert [leaf.leaf_label for leaf in schema.leaves[1:]] == rows[1][1:]
    assert [(group.label, group.col_start, group.col_end) for group in schema.groups] == [("Shared group", 1, 4)]


def test_build_schema_degrades_without_header_rows() -> None:
    """A table with no reliable headers should keep leaves and diagnostics."""
    rows = [["Age, years", "52.3", "0.03"], ["Male", "34", "0.10"]]
    table = _normalized_table("tbl-no-header", rows, header_rows=[], body_rows=[0, 1])
    schema = build_column_header_schema(table)

    assert [leaf.leaf_label for leaf in schema.leaves] == ["", "", ""]
    assert schema.groups == []
    assert "no_header_rows_available" in schema.diagnostics
    assert "generated_blank_leaf_without_header:col=1" in schema.diagnostics


def test_validate_column_header_schema_rejects_invalid_relationship() -> None:
    """Validation should reject relationships that point outside the group span."""
    schema = ColumnHeaderSchema(
        schema_id="schema",
        table_id="tbl",
        n_cols=3,
        leaves=[
            ColumnHeaderLeaf(leaf_id="leaf-2", table_id="tbl", col_idx=2, leaf_label="Q2", leaf_name="Q2"),
        ],
        groups=[
            ColumnHeaderGroup(
                group_id="group-1",
                table_id="tbl",
                row_idx=0,
                label="Q",
                name="Q",
                col_start=1,
                col_end=1,
                leaf_col_indices=[1],
                inference_rule="single_leaf_group",
            )
        ],
        relationships=[
            ColumnHeaderRelationship(
                relationship_id="rel-1",
                table_id="tbl",
                parent_group_id="group-1",
                child_leaf_id="leaf-2",
                leaf_col_idx=2,
            )
        ],
        evidence=[
            ColumnHeaderCellEvidence(
                evidence_id="evidence-1",
                table_id="tbl",
                row_idx=0,
                col_idx=1,
                cleaned_text="Q",
                source="normalized_cleaned_row",
            )
        ],
    )

    with pytest.raises(ValueError, match="relationship_leaf_not_in_parent_group"):
        validate_column_header_schema(schema)
