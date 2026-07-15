"""Tests for parser-native column header schemas."""

from __future__ import annotations

import pytest

from table1_parser.schemas import (
    ColumnHeaderCellEvidence,
    ColumnHeaderGroup,
    ColumnHeaderLeaf,
    ColumnHeaderRelationship,
    ColumnHeaderSchema,
)
from table1_parser.validation.column_header_schema import validate_column_header_schema


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
