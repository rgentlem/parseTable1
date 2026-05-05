"""Tests for explicit continuation column-compatibility diagnostics."""

from __future__ import annotations

from table1_parser.schemas import ColumnHeaderLeaf, ColumnHeaderSchema, NormalizedTable, RowView, TableProfile
from table1_parser.table_continuation_columns import build_table_continuation_column_checks


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
    *,
    table_number: int,
    rows: list[list[str]],
    is_continuation: bool = False,
    page_num: int = 1,
) -> NormalizedTable:
    header_rows = [0]
    body_rows = [idx for idx in range(len(rows)) if idx not in header_rows]
    title = f"Table {table_number} (continued)" if is_continuation else f"Table {table_number}"
    return NormalizedTable(
        table_id=table_id,
        title=title,
        caption=title,
        header_rows=header_rows,
        body_rows=body_rows,
        row_views=[_row_view(row_idx, rows[row_idx]) for row_idx in body_rows],
        n_rows=len(rows),
        n_cols=max(len(row) for row in rows),
        metadata={
            "bbox": (0.0, 0.0, 100.0, 40.0),
            "cleaned_rows": rows,
            "table_number": table_number,
            "is_continuation": is_continuation,
            "continuation_of_table_number": table_number if is_continuation else None,
            "source_page_num": page_num,
        },
    )


def _profile(table_id: str, family: str = "descriptive_characteristics") -> TableProfile:
    return TableProfile(table_id=table_id, table_family=family, family_confidence=0.9)


def _schema(table: NormalizedTable, headers: list[str]) -> ColumnHeaderSchema:
    return ColumnHeaderSchema(
        schema_id=f"{table.table_id}-column-schema",
        table_id=table.table_id,
        n_cols=table.n_cols,
        leaves=[
            ColumnHeaderLeaf(
                leaf_id=f"{table.table_id}-column-schema-leaf-{col_idx}",
                table_id=table.table_id,
                col_idx=col_idx,
                is_row_label_column=col_idx == 0,
                is_value_column=col_idx != 0,
                leaf_label=header,
                leaf_name=header,
            )
            for col_idx, header in enumerate(headers)
        ],
    )


def test_column_checks_include_descriptive_continuations_beyond_table1() -> None:
    """Demographic/descriptive continuations should be checked even when table number is not 1."""
    rows = [["Variable", "Overall", "Cases"], ["Age", "52", "58"]]
    base = _normalized_table("tbl-7a", table_number=7, rows=rows, page_num=3)
    continuation = _normalized_table("tbl-7b", table_number=7, rows=rows, is_continuation=True, page_num=4)

    checks = build_table_continuation_column_checks(
        [base, continuation],
        None,
        [_profile("tbl-7a", "estimate_results"), _profile("tbl-7b", "unknown")],
        ["demographic_description", "unknown"],
        [_schema(base, ["Variable", "Overall", "Cases"]), _schema(continuation, ["Variable", "Overall", "Cases"])],
    )

    assert len(checks) == 1
    assert checks[0].table_number == 7
    assert checks[0].base_table_id == "tbl-7a"
    assert checks[0].continuation_table_id == "tbl-7b"
    assert checks[0].base_table_category == "demographic_description"
    assert checks[0].normalized_column_count_match is True
    assert checks[0].column_header_status == "match"
    assert checks[0].overall_status == "compatible"


def test_column_checks_ignore_page_coordinates() -> None:
    """Page coordinate differences should not be part of continuation compatibility."""
    rows = [["Variable", "Overall", "Cases"], ["Age", "52", "58"]]
    base = _normalized_table("tbl-2a", table_number=2, rows=rows, page_num=3)
    continuation = _normalized_table("tbl-2b", table_number=2, rows=rows, is_continuation=True, page_num=4)

    checks = build_table_continuation_column_checks(
        [base, continuation],
        None,
        [_profile("tbl-2a"), _profile("tbl-2b")],
        ["demographic_description", "demographic_description"],
        [_schema(base, ["Variable", "Overall", "Cases"]), _schema(continuation, ["Variable", "Overall", "Cases"])],
    )

    assert len(checks) == 1
    assert checks[0].column_header_status == "match"
    assert checks[0].overall_status == "compatible"


def test_column_checks_skip_non_descriptive_continuations_when_profiles_are_available() -> None:
    """The diagnostic should target demographic/descriptive continuations, not every result-table split."""
    rows = [["Model", "OR", "P-value"], ["A", "1.2", "0.01"]]
    base = _normalized_table("tbl-3a", table_number=3, rows=rows, page_num=5)
    continuation = _normalized_table("tbl-3b", table_number=3, rows=rows, is_continuation=True, page_num=6)

    checks = build_table_continuation_column_checks(
        [base, continuation],
        table_profiles=[_profile("tbl-3a", "estimate_results"), _profile("tbl-3b", "estimate_results")],
    )

    assert checks == []


def test_column_checks_skip_non_demographic_continuations_when_categories_are_available() -> None:
    """Paper-table categories should be the preferred demographic-description gate."""
    rows = [["Variable", "Overall"], ["Age", "52"]]
    base = _normalized_table("tbl-6a", table_number=6, rows=rows, page_num=5)
    continuation = _normalized_table("tbl-6b", table_number=6, rows=rows, is_continuation=True, page_num=6)

    checks = build_table_continuation_column_checks(
        [base, continuation],
        table_profiles=[_profile("tbl-6a"), _profile("tbl-6b")],
        table_categories=["data_presentation", "data_presentation"],
    )

    assert checks == []


def test_column_checks_do_not_try_random_same_number_pairs() -> None:
    """Matching table numbers and columns are not enough without explicit continuation evidence."""
    rows = [["Variable", "Overall"], ["Age", "52"]]
    first = _normalized_table("tbl-4a", table_number=4, rows=rows, page_num=7)
    second = _normalized_table("tbl-4b", table_number=4, rows=rows, page_num=8)

    checks = build_table_continuation_column_checks(
        [first, second],
        table_profiles=[_profile("tbl-4a"), _profile("tbl-4b")],
    )

    assert checks == []


def test_column_checks_include_uncaptioned_next_page_demographic_fragment() -> None:
    """Uncaptioned adjacent demographic fragments should get continuation diagnostics."""
    rows = [["Variable", "Q1", "Q2"], ["Age", "52", "58"]]
    base = _normalized_table("tbl-1a", table_number=1, rows=rows, page_num=2)
    continuation = NormalizedTable(
        table_id="tbl-1b",
        title=None,
        caption=None,
        header_rows=[0],
        body_rows=[1],
        row_views=[_row_view(1, ["BMI", "29", "31"])],
        n_rows=2,
        n_cols=3,
        metadata={
            "bbox": (0.0, 0.0, 100.0, 40.0),
            "cleaned_rows": [["Variable", "Q1", "Q2"], ["BMI", "29", "31"]],
            "table_number": None,
            "is_continuation": False,
            "continuation_of_table_number": None,
            "source_page_num": 3,
        },
    )

    checks = build_table_continuation_column_checks(
        [base, continuation],
        table_profiles=[_profile("tbl-1a"), _profile("tbl-1b")],
        table_categories=["demographic_description", "demographic_description"],
        column_header_schemas=[
            _schema(base, ["Variable", "Q1", "Q2"]),
            _schema(continuation, ["Variable", "Q1", "Q2"]),
        ],
    )

    assert len(checks) == 1
    assert checks[0].table_number == 1
    assert checks[0].base_table_id == "tbl-1a"
    assert checks[0].continuation_table_id == "tbl-1b"
    assert checks[0].overall_status == "compatible"


def test_column_checks_fail_without_column_schema() -> None:
    """Continuation checks should not infer column headers without schema artifacts."""
    rows = [["Variable", "Q1", "Q2"], ["Age", "52", "58"]]
    base = _normalized_table("tbl-1a", table_number=1, rows=rows, page_num=2)
    continuation = _normalized_table("tbl-1b", table_number=1, rows=rows, is_continuation=True, page_num=3)

    checks = build_table_continuation_column_checks(
        [base, continuation],
        table_profiles=[_profile("tbl-1a"), _profile("tbl-1b")],
        table_categories=["demographic_description", "demographic_description"],
    )

    assert len(checks) == 1
    assert checks[0].column_header_status == "missing_both"
    assert checks[0].overall_status == "incompatible"
    assert any("column_header_schema_missing_or_empty" in item for item in checks[0].diagnostics)
