"""Tests for artifact-only Table 1 continuation grouping."""

from __future__ import annotations

from table1_parser.schemas import ColumnHeaderSchema, NormalizedTable, RowView
from table1_parser.table1_continuations import build_table1_continuation_artifacts


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
    rows: list[list[str]],
    table_number: int,
    is_continuation: bool,
    header_rows: list[int] | None = None,
    source_page_num: int = 1,
) -> NormalizedTable:
    headers = header_rows if header_rows is not None else [0]
    body_rows = [idx for idx in range(len(rows)) if idx not in headers]
    title = f"Table {table_number} (continued)" if is_continuation else f"Table {table_number}"
    return NormalizedTable(
        table_id=table_id,
        title=title,
        caption=title if is_continuation else f"Table {table_number}. Baseline",
        header_rows=headers,
        body_rows=body_rows,
        row_views=[_row_view(idx, rows[idx]) for idx in body_rows],
        n_rows=len(rows),
        n_cols=max(len(row) for row in rows),
        metadata={
            "cleaned_rows": rows,
            "table_number": table_number,
            "is_continuation": is_continuation,
            "continuation_of_table_number": table_number if is_continuation else None,
            "source_page_num": source_page_num,
        },
    )


def _schema(table: NormalizedTable, signature: list[str]) -> ColumnHeaderSchema:
    return ColumnHeaderSchema(
        schema_id=f"{table.table_id}-column-schema",
        table_id=table.table_id,
        n_cols=table.n_cols,
        flattened_signature=signature,
    )


def test_table1_continuation_artifacts_merge_matching_table1_fragments() -> None:
    """Explicit Table 1 continuations with matching columns should write a merged artifact."""
    base = _normalized_table(
        "paper-p5-t0",
        rows=[
            ["Variable", "Overall (n = 100)", "Cases (n = 40)", "P-value"],
            ["Age", "52.1", "58.2", "0.01"],
            ["Sex", "", "", "<0.001"],
            ["Male", "50 (50%)", "30 (75%)", ""],
        ],
        table_number=1,
        is_continuation=False,
        source_page_num=5,
    )
    continuation = _normalized_table(
        "paper-p6-t0",
        rows=[
            ["Table 1 (continued)", "", "", ""],
            ["Variable", "Overall (n = 100)", "Cases (n = 40)", "P-value"],
            ["Female", "50 (50%)", "10 (25%)", ""],
            ["BMI", "29.1", "31.2", "0.02"],
        ],
        table_number=1,
        is_continuation=True,
        header_rows=[0, 1],
        source_page_num=6,
    )

    schemas = [
        _schema(base, ["Variable", "Overall", "Cases", "P-value"]),
        _schema(continuation, ["Variable", "Overall", "Cases", "P-value"]),
    ]

    groups, merged_tables = build_table1_continuation_artifacts([base, continuation], schemas)

    assert len(groups) == 1
    assert groups[0].merge_decision == "merge"
    assert groups[0].source_table_ids == ["paper-p5-t0", "paper-p6-t0"]
    assert groups[0].column_signature == ["variable", "overall", "cases", "p-value"]
    assert len(merged_tables) == 1
    merged = merged_tables[0]
    assert merged.table_id == "paper-p5-t0-merged-table1"
    assert merged.n_rows == 6
    assert merged.header_rows == [0]
    assert merged.body_rows == [1, 2, 3, 4, 5]
    assert merged.metadata["cleaned_rows"][4] == ["Female", "50 (50%)", "10 (25%)", ""]
    provenance = merged.metadata["table1_continuation_merge"]["row_provenance"]
    assert provenance[4]["source_table_id"] == "paper-p6-t0"
    assert provenance[4]["source_row_idx"] == 2


def test_table1_continuation_artifacts_skip_incompatible_columns() -> None:
    """Explicit continuations should not merge when column signatures differ."""
    base = _normalized_table(
        "paper-p5-t0",
        rows=[["Variable", "Overall", "Cases"], ["Age", "52.1", "58.2"]],
        table_number=1,
        is_continuation=False,
    )
    continuation = _normalized_table(
        "paper-p6-t0",
        rows=[["Variable", "Overall", "Controls"], ["BMI", "29.1", "27.5"]],
        table_number=1,
        is_continuation=True,
    )

    schemas = [
        _schema(base, ["Variable", "Overall", "Cases"]),
        _schema(continuation, ["Variable", "Overall", "Controls"]),
    ]

    groups, merged_tables = build_table1_continuation_artifacts([base, continuation], schemas)

    assert len(groups) == 1
    assert groups[0].merge_decision == "skip"
    assert groups[0].decision_reason == "explicit_table1_continuation_but_incompatible_columns"
    assert groups[0].diagnostics
    assert merged_tables == []


def test_table1_continuation_artifacts_ignore_non_table1_continuations() -> None:
    """Only Table 1 continuations should be grouped by this artifact stage."""
    base = _normalized_table(
        "paper-p10-t0",
        rows=[["Model", "OR", "P-value"], ["A", "1.2", "0.01"]],
        table_number=3,
        is_continuation=False,
    )
    continuation = _normalized_table(
        "paper-p11-t0",
        rows=[["Model", "OR", "P-value"], ["B", "1.4", "0.02"]],
        table_number=3,
        is_continuation=True,
    )

    groups, merged_tables = build_table1_continuation_artifacts([base, continuation])

    assert groups == []
    assert merged_tables == []


def test_table1_continuation_artifacts_detect_uncaptioned_next_page_fragment() -> None:
    """An uncaptioned demographic table after Table 1 should be pulled out as a continuation candidate."""
    base = _normalized_table(
        "paper-p2-t0",
        rows=[["Variable", "Q1", "Q2"], ["Age", "52", "58"]],
        table_number=1,
        is_continuation=False,
        source_page_num=2,
    )
    continuation = NormalizedTable(
        table_id="paper-p3-t0",
        title=None,
        caption=None,
        header_rows=[0],
        body_rows=[1],
        row_views=[_row_view(1, ["BMI", "29", "31"])],
        n_rows=2,
        n_cols=3,
        metadata={
            "cleaned_rows": [["Variable", "Q1", "Q2"], ["BMI", "29", "31"]],
            "table_number": None,
            "is_continuation": False,
            "continuation_of_table_number": None,
            "source_page_num": 3,
        },
    )

    schemas = [
        _schema(base, ["Variable", "Q1", "Q2"]),
        _schema(continuation, ["Variable", "Q1", "Q2"]),
    ]

    groups, merged_tables = build_table1_continuation_artifacts([base, continuation], schemas)

    assert len(groups) == 1
    assert groups[0].merge_decision == "merge"
    assert groups[0].decision_reason == "uncaptioned_table1_continuation_candidate_and_matching_columns"
    assert groups[0].source_table_ids == ["paper-p2-t0", "paper-p3-t0"]
    assert len(merged_tables) == 1


def test_table1_continuation_artifacts_fail_without_column_schema() -> None:
    """Continuation grouping should not reconstruct signatures when schemas are missing."""
    base = _normalized_table(
        "paper-p2-t0",
        rows=[["Variable", "Q1", "Q2"], ["Age", "52", "58"]],
        table_number=1,
        is_continuation=False,
        source_page_num=2,
    )
    continuation = _normalized_table(
        "paper-p3-t0",
        rows=[["Variable", "Q1", "Q2"], ["BMI", "29", "31"]],
        table_number=1,
        is_continuation=True,
        source_page_num=3,
    )

    groups, merged_tables = build_table1_continuation_artifacts([base, continuation])

    assert len(groups) == 1
    assert groups[0].merge_decision == "skip"
    assert groups[0].column_signature == []
    assert any("column_header_schema_missing_or_empty" in item for item in groups[0].diagnostics)
    assert merged_tables == []
