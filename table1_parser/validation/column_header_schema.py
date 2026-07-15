"""Validation helpers for column header schemas."""

from __future__ import annotations

from table1_parser.schemas import ColumnHeaderSchema


def validate_column_header_schema(schema: ColumnHeaderSchema) -> ColumnHeaderSchema:
    """Validate internal references and bounds for a column header schema."""
    evidence_ids = [item.evidence_id for item in schema.evidence]
    leaf_ids = [leaf.leaf_id for leaf in schema.leaves]
    group_ids = [group.group_id for group in schema.groups]
    relationship_ids = [
        relationship.relationship_id for relationship in schema.relationships
    ]
    for label, values in {
        "evidence_id": evidence_ids,
        "leaf_id": leaf_ids,
        "group_id": group_ids,
        "relationship_id": relationship_ids,
    }.items():
        duplicates = {value for value in values if values.count(value) > 1}
        if duplicates:
            raise ValueError(f"duplicate_{label}: {sorted(duplicates)}")

    evidence_id_set = set(evidence_ids)
    leaf_by_id = {leaf.leaf_id: leaf for leaf in schema.leaves}
    group_by_id = {group.group_id: group for group in schema.groups}
    leaf_cols = sorted(leaf.col_idx for leaf in schema.leaves)
    if leaf_cols != list(range(schema.n_cols)):
        raise ValueError(
            f"leaf_axis_incomplete: expected={list(range(schema.n_cols))}: "
            f"observed={leaf_cols}"
        )
    for item in schema.evidence:
        if item.col_idx >= schema.n_cols:
            raise ValueError(
                f"evidence_col_idx_out_of_bounds: {item.evidence_id}: {item.col_idx}"
            )
    for leaf in schema.leaves:
        if leaf.col_idx >= schema.n_cols:
            raise ValueError(
                f"leaf_col_idx_out_of_bounds: {leaf.leaf_id}: {leaf.col_idx}"
            )
        if (
            leaf.coordinate_left is not None
            and leaf.coordinate_right is not None
            and leaf.coordinate_right < leaf.coordinate_left
        ):
            raise ValueError(f"leaf_coordinate_bounds_reversed: {leaf.leaf_id}")
        missing_evidence = sorted(set(leaf.evidence_ids) - evidence_id_set)
        if missing_evidence:
            raise ValueError(
                f"leaf_references_unknown_evidence: {leaf.leaf_id}: {missing_evidence}"
            )

    for group in schema.groups:
        if group.col_end < group.col_start:
            raise ValueError(f"group_empty_span: {group.group_id}")
        leaf_cols = sorted(group.leaf_col_indices)
        if not leaf_cols:
            raise ValueError(f"group_has_no_leaf_columns: {group.group_id}")
        if len(leaf_cols) < 2:
            raise ValueError(f"group_requires_multiple_leaves: {group.group_id}")
        if leaf_cols != list(range(group.col_start, group.col_end + 1)):
            raise ValueError(
                f"group_leaf_columns_not_contiguous: {group.group_id}: {leaf_cols}"
            )
        if any(col_idx >= schema.n_cols for col_idx in leaf_cols):
            raise ValueError(
                f"group_col_idx_out_of_bounds: {group.group_id}: {leaf_cols}"
            )
        missing_evidence = sorted(set(group.evidence_ids) - evidence_id_set)
        if missing_evidence:
            raise ValueError(
                f"group_references_unknown_evidence: {group.group_id}: {missing_evidence}"
            )

    ordered_groups = sorted(
        schema.groups,
        key=lambda item: (item.col_start, item.col_end),
    )
    for index, left_group in enumerate(ordered_groups):
        for right_group in ordered_groups[index + 1 :]:
            if (
                left_group.col_start
                < right_group.col_start
                <= left_group.col_end
                < right_group.col_end
            ):
                raise ValueError(
                    "crossing_group_spans: "
                    f"{left_group.group_id}: {right_group.group_id}"
                )

    for relationship in schema.relationships:
        if relationship.parent_group_id not in group_by_id:
            raise ValueError(
                f"relationship_unknown_parent_group: {relationship.relationship_id}"
            )
        if relationship.child_leaf_id not in leaf_by_id:
            raise ValueError(
                f"relationship_unknown_child_leaf: {relationship.relationship_id}"
            )
        leaf = leaf_by_id[relationship.child_leaf_id]
        group = group_by_id[relationship.parent_group_id]
        if relationship.leaf_col_idx != leaf.col_idx:
            raise ValueError(
                f"relationship_leaf_col_mismatch: {relationship.relationship_id}"
            )
        if relationship.leaf_col_idx not in group.leaf_col_indices:
            raise ValueError(
                f"relationship_leaf_not_in_parent_group: {relationship.relationship_id}"
            )
        missing_evidence = sorted(set(relationship.evidence_ids) - evidence_id_set)
        if missing_evidence:
            raise ValueError(
                f"relationship_references_unknown_evidence: {relationship.relationship_id}: {missing_evidence}"
            )

    expected_relationships = {
        (group.group_id, leaf.col_idx)
        for group in schema.groups
        for leaf in schema.leaves
        if leaf.col_idx in group.leaf_col_indices
    }
    observed_relationships = {
        (relationship.parent_group_id, relationship.leaf_col_idx)
        for relationship in schema.relationships
    }
    if observed_relationships != expected_relationships:
        raise ValueError(
            "group_relationship_coverage_mismatch: "
            f"expected={sorted(expected_relationships)}: "
            f"observed={sorted(observed_relationships)}"
        )

    return schema
