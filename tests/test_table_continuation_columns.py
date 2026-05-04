"""Tests for explicit continuation column-compatibility diagnostics."""

from __future__ import annotations

from table1_parser.schemas import ExtractedTable, NormalizedTable, RowView, TableCell, TableProfile
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


def _extracted_table(
    table_id: str,
    *,
    rows: list[list[str]],
    page_num: int,
    col_boxes: list[tuple[float, float]],
) -> ExtractedTable:
    cells: list[TableCell] = []
    for row_idx, row in enumerate(rows):
        top = float(row_idx * 10)
        bottom = top + 8.0
        for col_idx, value in enumerate(row):
            left, right = col_boxes[col_idx]
            cells.append(
                TableCell(
                    row_idx=row_idx,
                    col_idx=col_idx,
                    text=value,
                    page_num=page_num,
                    bbox=(left, top, right, bottom),
                )
            )
    return ExtractedTable(
        table_id=table_id,
        source_pdf="paper.pdf",
        page_num=page_num,
        title=f"Table {page_num}",
        caption=f"Table {page_num}",
        n_rows=len(rows),
        n_cols=max(len(row) for row in rows),
        cells=cells,
        extraction_backend="test",
        metadata={"bbox": (0.0, 0.0, 100.0, 40.0)},
    )


def _profile(table_id: str, family: str = "descriptive_characteristics") -> TableProfile:
    return TableProfile(table_id=table_id, table_family=family, family_confidence=0.9)


def test_column_checks_include_descriptive_continuations_beyond_table1() -> None:
    """Demographic/descriptive continuations should be checked even when table number is not 1."""
    rows = [["Variable", "Overall", "Cases"], ["Age", "52", "58"]]
    base = _normalized_table("tbl-7a", table_number=7, rows=rows, page_num=3)
    continuation = _normalized_table("tbl-7b", table_number=7, rows=rows, is_continuation=True, page_num=4)
    extracted = [
        _extracted_table("tbl-7a", rows=rows, page_num=3, col_boxes=[(0.0, 20.0), (20.0, 60.0), (60.0, 100.0)]),
        _extracted_table("tbl-7b", rows=rows, page_num=4, col_boxes=[(1.0, 21.0), (21.0, 61.0), (61.0, 101.0)]),
    ]

    checks = build_table_continuation_column_checks(
        [base, continuation],
        extracted,
        [_profile("tbl-7a", "estimate_results"), _profile("tbl-7b", "unknown")],
        ["demographic_description", "unknown"],
    )

    assert len(checks) == 1
    assert checks[0].table_number == 7
    assert checks[0].base_table_id == "tbl-7a"
    assert checks[0].continuation_table_id == "tbl-7b"
    assert checks[0].base_table_category == "demographic_description"
    assert checks[0].normalized_column_count_match is True
    assert checks[0].header_signature_status == "match"
    assert checks[0].coordinate_status == "compatible"
    assert checks[0].overall_status == "compatible"


def test_column_checks_flag_shifted_continuation_coordinates() -> None:
    """Explicit continuations with shifted value columns should be reported as incompatible."""
    rows = [["Variable", "Overall", "Cases"], ["Age", "52", "58"]]
    base = _normalized_table("tbl-2a", table_number=2, rows=rows, page_num=3)
    continuation = _normalized_table("tbl-2b", table_number=2, rows=rows, is_continuation=True, page_num=4)
    extracted = [
        _extracted_table("tbl-2a", rows=rows, page_num=3, col_boxes=[(0.0, 20.0), (20.0, 60.0), (60.0, 100.0)]),
        _extracted_table("tbl-2b", rows=rows, page_num=4, col_boxes=[(0.0, 20.0), (40.0, 70.0), (80.0, 100.0)]),
    ]

    checks = build_table_continuation_column_checks(
        [base, continuation],
        extracted,
        [_profile("tbl-2a"), _profile("tbl-2b")],
        ["demographic_description", "demographic_description"],
    )

    assert len(checks) == 1
    assert checks[0].coordinate_status == "incompatible"
    assert checks[0].overall_status == "incompatible"
    assert any(entry.status == "mismatched" for entry in checks[0].column_map)


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
