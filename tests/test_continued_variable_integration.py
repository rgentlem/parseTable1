"""Tests for continued-table variable integration artifacts."""

from __future__ import annotations

from table1_parser.continued_variable_integration import build_continued_variable_integrations
from table1_parser.schemas import (
    ColumnDefinition,
    DefinedColumn,
    DefinedLevel,
    DefinedVariable,
    NormalizedTable,
    RowView,
    Table1ContinuationGroup,
    TableDefinition,
)


def _row_view(row_idx: int, cells: list[str], *, indent_level: int = 0, likely_role: str = "unknown") -> RowView:
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
        indent_level=indent_level,
        likely_role=likely_role,
    )


def _table(table_id: str, rows: list[list[str]], *, page_num: int) -> NormalizedTable:
    return NormalizedTable(
        table_id=table_id,
        title="Table 1",
        caption="Baseline characteristics",
        header_rows=[0],
        body_rows=list(range(1, len(rows))),
        row_views=[
            _row_view(row_idx, rows[row_idx], indent_level=2 if row_idx in {2, 3} else 0)
            for row_idx in range(1, len(rows))
        ],
        n_rows=len(rows),
        n_cols=max(len(row) for row in rows),
        metadata={"cleaned_rows": rows, "source_page_num": page_num},
    )


def _definition(
    table_id: str,
    variables: list[DefinedVariable],
) -> TableDefinition:
    return TableDefinition(
        table_id=table_id,
        title="Table 1",
        caption="Baseline characteristics",
        variables=variables,
        column_definition=ColumnDefinition(
            columns=[
                DefinedColumn(col_idx=1, column_name="Overall", column_label="Overall", inferred_role="overall"),
                DefinedColumn(col_idx=2, column_name="Group", column_label="Group", inferred_role="group"),
            ]
        ),
    )


def _group() -> Table1ContinuationGroup:
    return Table1ContinuationGroup(
        group_id="table1_continuation_0",
        source_table_indices=[0, 1],
        source_table_ids=["tbl-base", "tbl-cont"],
        merge_decision="merge",
        decision_reason="explicit_table1_continuation_and_matching_columns",
        confidence=0.98,
        column_headers_match=True,
        column_headers=["characteristic", "overall", "group"],
    )


def test_continued_variable_integration_attaches_leading_continuation_levels() -> None:
    base = _table("tbl-base", [["Characteristic", "Overall", "Group"], ["Race, n (%)", "", ""]], page_num=2)
    continuation = _table(
        "tbl-cont",
        [
            ["Characteristic", "Overall", "Group"],
            ["White", "34 (45%)", "10 (40%)"],
            ["Black", "41 (55%)", "15 (60%)"],
            ["Age, years", "52.1", "49.9"],
        ],
        page_num=3,
    )
    base_definition = _definition(
        "tbl-base",
        [
            DefinedVariable(
                variable_name="Race",
                variable_label="Race, n (%)",
                variable_type="categorical",
                row_start=1,
                row_end=1,
            )
        ],
    )
    continuation_definition = _definition(
        "tbl-cont",
        [
            DefinedVariable(
                variable_name="White",
                variable_label="White",
                variable_type="unknown",
                row_start=1,
                row_end=1,
                summary_style_hint="count_pct",
            ),
            DefinedVariable(
                variable_name="Black",
                variable_label="Black",
                variable_type="unknown",
                row_start=2,
                row_end=2,
                summary_style_hint="count_pct",
            ),
            DefinedVariable(
                variable_name="Age years",
                variable_label="Age, years",
                variable_type="continuous",
                row_start=3,
                row_end=3,
                summary_style_hint="numeric",
            ),
        ],
    )

    integrations = build_continued_variable_integrations(
        [base, continuation],
        [base_definition, continuation_definition],
        [_group()],
    )

    assert len(integrations) == 1
    variables = integrations[0].variables
    assert [variable.variable_label for variable in variables] == ["Race, n (%)", "Age, years"]
    assert [level.level_label for level in variables[0].levels] == ["White", "Black"]
    assert variables[0].row_end == 3
    metadata = integrations[0].metadata
    assert metadata["tableone"]["vars"] == ["Race", "Age years"]
    assert metadata["tableone"]["logiFactors"] == [True, False]
    decision = metadata["continued_variable_integration"]["boundary_decisions"][0]
    assert decision["decision"] == "attached_levels"
    provenance = metadata["continued_variable_integration"]["row_provenance"]
    assert any(item["source_label"] == "Black" and item["indent_level"] == 2 for item in provenance)


def test_continued_variable_integration_preserves_fragments_when_boundary_is_new_variable() -> None:
    base = _table("tbl-base", [["Characteristic", "Overall", "Group"], ["Age, years", "52.1", "49.9"]], page_num=2)
    continuation = _table(
        "tbl-cont",
        [["Characteristic", "Overall", "Group"], ["BMI", "27.2", "29.1"]],
        page_num=3,
    )
    base_definition = _definition(
        "tbl-base",
        [
            DefinedVariable(
                variable_name="Age years",
                variable_label="Age, years",
                variable_type="continuous",
                row_start=1,
                row_end=1,
            )
        ],
    )
    continuation_definition = _definition(
        "tbl-cont",
        [
            DefinedVariable(
                variable_name="BMI",
                variable_label="BMI",
                variable_type="continuous",
                row_start=1,
                row_end=1,
            )
        ],
    )

    integrations = build_continued_variable_integrations(
        [base, continuation],
        [base_definition, continuation_definition],
        [_group()],
    )

    assert [variable.variable_label for variable in integrations[0].variables] == ["Age, years", "BMI"]
    decision = integrations[0].metadata["continued_variable_integration"]["boundary_decisions"][0]
    assert decision["decision"] == "unchanged"


def test_continued_variable_integration_supports_levels_split_across_fragments() -> None:
    base = _table(
        "tbl-base",
        [["Characteristic", "Overall", "Group"], ["Race, n (%)", "", ""], ["White", "34 (45%)", "10 (40%)"]],
        page_num=2,
    )
    continuation = _table(
        "tbl-cont",
        [["Characteristic", "Overall", "Group"], ["Black", "41 (55%)", "15 (60%)"]],
        page_num=3,
    )
    base_definition = _definition(
        "tbl-base",
        [
            DefinedVariable(
                variable_name="Race",
                variable_label="Race, n (%)",
                variable_type="categorical",
                row_start=1,
                row_end=2,
                levels=[DefinedLevel(level_name="White", level_label="White", row_idx=2)],
            )
        ],
    )
    continuation_definition = _definition(
        "tbl-cont",
        [
            DefinedVariable(
                variable_name="Black",
                variable_label="Black",
                variable_type="unknown",
                row_start=1,
                row_end=1,
                summary_style_hint="count_pct",
            )
        ],
    )

    integrations = build_continued_variable_integrations(
        [base, continuation],
        [base_definition, continuation_definition],
        [_group()],
    )

    assert [level.level_label for level in integrations[0].variables[0].levels] == ["White", "Black"]
    assert len(integrations[0].metadata["continued_variable_integration"]["row_provenance"]) == 3


def test_continued_variable_integration_skips_nonmerge_groups() -> None:
    group = _group().model_copy(update={"merge_decision": "skip", "column_headers_match": False})

    assert build_continued_variable_integrations([], [], [group]) == []
