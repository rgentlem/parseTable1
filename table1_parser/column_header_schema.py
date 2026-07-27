"""Deterministic assembly of parser-native column header schemas."""

from __future__ import annotations

import re

from table1_parser.schemas import (
    ColumnHeaderCellEvidence,
    ColumnHeaderDescriptor,
    ColumnHeaderGroup,
    ColumnHeaderLeaf,
    ColumnHeaderRelationship,
    ColumnHeaderSchema,
    HeaderStructureCandidate,
    NormalizedTable,
)
from table1_parser.text_cleaning import clean_text
from table1_parser.validation.column_header_schema import validate_column_header_schema


NON_ALNUM_PATTERN = re.compile(r"[^A-Za-z0-9]+")
ALPHA_BOUNDARY_SEPARATOR_PATTERN = re.compile(
    r"(?<=[A-Za-z])[^A-Za-z0-9\s]+(?=[A-Za-z])"
)
HEADER_MARKUP_PATTERN = re.compile(r"[*_`]+")
HEADER_SPACE_PATTERN = re.compile(r"\s+")
HEADER_TRAILING_SPLIT_HYPHEN_PATTERN = re.compile(r"\s+[-–—]\s*$")
HEADER_LEADING_SPLIT_HYPHEN_PATTERN = re.compile(
    r"(^|[\s(,;:])[-–—]\s+(?=[A-Za-z]+[)\]])"
)


def build_column_header_schema(
    table: NormalizedTable,
    header_structure_candidate: HeaderStructureCandidate | None = None,
) -> ColumnHeaderSchema:
    """Build one parser-native column header schema from a normalized table."""
    schema_id = f"{table.table_id}:column_header_schema"
    if (
        header_structure_candidate is None
        or header_structure_candidate.table_id != table.table_id
    ):
        return ColumnHeaderSchema(
            schema_id=schema_id,
            table_id=table.table_id,
            n_cols=table.n_cols,
            label_col_idx=0 if table.n_cols else None,
            header_rows_considered=list(table.header_rows),
            body_rows_considered=list(table.body_rows),
            diagnostics=[
                "header_structure_candidate_missing"
                if header_structure_candidate is None
                else "header_structure_candidate_table_id_mismatch"
            ],
            confidence=0.0,
        )

    candidate = header_structure_candidate
    diagnostics = [
        "projected_header_structure_candidate",
        *candidate.concerns,
        *candidate.diagnostics,
    ]
    projection_errors: list[str] = []
    if candidate.header_row_indices != table.header_rows:
        projection_errors.append("candidate_normalized_header_rows_mismatch")
    if candidate.body_row_indices != table.body_rows:
        projection_errors.append("candidate_normalized_body_rows_mismatch")

    candidate_leaves = sorted(
        candidate.leaf_candidates,
        key=lambda item: item.physical_col_idx,
    )
    candidate_leaf_by_id = {leaf.leaf_id: leaf for leaf in candidate_leaves}
    leaf_indices = [leaf.physical_col_idx for leaf in candidate_leaves]
    if leaf_indices != list(range(table.n_cols)):
        projection_errors.append(
            "candidate_leaf_axis_incomplete:"
            f"expected={list(range(table.n_cols))}:observed={leaf_indices}"
        )
    if len(candidate_leaf_by_id) != len(candidate_leaves):
        projection_errors.append("candidate_leaf_ids_duplicate")

    candidate_evidence_by_id = {item.evidence_id: item for item in candidate.evidence}
    if len(candidate_evidence_by_id) != len(candidate.evidence):
        projection_errors.append("candidate_evidence_ids_duplicate")
    candidate_group_by_id = {
        group.group_id: group for group in candidate.group_candidates
    }
    if len(candidate_group_by_id) != len(candidate.group_candidates):
        projection_errors.append("candidate_group_ids_duplicate")

    source_col_indices = table.metadata.get("source_col_indices")
    if (
        not isinstance(source_col_indices, list)
        or len(source_col_indices) != table.n_cols
    ):
        original_col_indices: list[int | None] = [None] * table.n_cols
        projection_errors.append("normalized_source_column_identity_missing")
    else:
        original_col_indices = [
            value if isinstance(value, int) and value >= 0 else None
            for value in source_col_indices
        ]
        if original_col_indices != list(range(table.n_cols)):
            projection_errors.append("normalized_source_column_identity_not_physical")

    raw_grid = table.metadata.get("cleaned_rows")
    if isinstance(raw_grid, list):
        grid = [
            [clean_text(str(cell)) for cell in row] if isinstance(row, list) else []
            for row in raw_grid
        ]
    else:
        grid = []
        projection_errors.append("normalized_cleaned_rows_missing")

    evidence_columns: dict[str, set[int]] = {
        evidence_id: set() for evidence_id in candidate_evidence_by_id
    }
    for leaf in candidate_leaves:
        for evidence_id in leaf.evidence_ids:
            if evidence_id not in evidence_columns:
                projection_errors.append(
                    f"candidate_leaf_unknown_evidence:{leaf.leaf_id}:{evidence_id}"
                )
                continue
            evidence_columns[evidence_id].add(leaf.physical_col_idx)
    for group in candidate.group_candidates:
        group_columns = sorted(
            candidate_leaf_by_id[leaf_id].physical_col_idx
            for leaf_id in group.leaf_ids
            if leaf_id in candidate_leaf_by_id
        )
        if len(group_columns) != len(group.leaf_ids):
            projection_errors.append(f"candidate_group_unknown_leaf:{group.group_id}")
        if group_columns and group_columns != list(
            range(group_columns[0], group_columns[-1] + 1)
        ):
            projection_errors.append(f"candidate_group_noncontiguous:{group.group_id}")
        for evidence_id in group.evidence_ids:
            if evidence_id not in evidence_columns:
                projection_errors.append(
                    f"candidate_group_unknown_evidence:{group.group_id}:{evidence_id}"
                )
                continue
            evidence_columns[evidence_id].update(group_columns)

    evidence: list[ColumnHeaderCellEvidence] = []
    for item in candidate.evidence:
        linked_columns = sorted(evidence_columns.get(item.evidence_id, set()))
        col_idx = linked_columns[0] if linked_columns else 0
        if not linked_columns:
            diagnostics.append(f"unreferenced_candidate_evidence:{item.evidence_id}")
        row_idx = min(
            item.header_row_indices,
            default=min(candidate.header_row_indices, default=0),
        )
        evidence.append(
            ColumnHeaderCellEvidence(
                evidence_id=item.evidence_id,
                table_id=table.table_id,
                row_idx=row_idx,
                col_idx=col_idx,
                original_row_idx=row_idx,
                original_col_idx=(
                    original_col_indices[col_idx]
                    if col_idx < len(original_col_indices)
                    else None
                ),
                raw_text=item.text,
                cleaned_text=clean_text(item.text),
                bbox=item.canonical_bbox,
                page_num=candidate.page_num,
                source="header_structure_candidate",
            )
        )

    leaf_header_row_idx = max(candidate.header_row_indices, default=None)
    leaves: list[ColumnHeaderLeaf] = []
    for leaf in candidate_leaves:
        col_idx = leaf.physical_col_idx
        left, right = leaf.canonical_x_bounds
        body_nonempty_rows = [
            row_idx
            for row_idx in candidate.body_row_indices
            if row_idx < len(grid)
            and col_idx < len(grid[row_idx])
            and bool(grid[row_idx][col_idx])
        ]
        leaf_label = clean_text(leaf.base_text)
        leaves.append(
            ColumnHeaderLeaf(
                leaf_id=leaf.leaf_id,
                table_id=table.table_id,
                col_idx=col_idx,
                original_col_idx=(
                    original_col_indices[col_idx]
                    if col_idx < len(original_col_indices)
                    else None
                ),
                is_row_label_column=col_idx == 0,
                is_value_column=col_idx != 0,
                leaf_header_row_idx=leaf_header_row_idx,
                leaf_label=leaf_label,
                leaf_name=_normalize_header_name(leaf_label) or f"column_{col_idx}",
                body_nonempty_row_indices=body_nonempty_rows,
                evidence_ids=list(leaf.evidence_ids),
                coordinate_left=left,
                coordinate_center=(left + right) / 2.0,
                coordinate_right=right,
            )
        )

    groups: list[ColumnHeaderGroup] = []
    for group in candidate.group_candidates:
        group_columns = sorted(
            candidate_leaf_by_id[leaf_id].physical_col_idx
            for leaf_id in group.leaf_ids
            if leaf_id in candidate_leaf_by_id
        )
        if not group_columns:
            projection_errors.append(f"candidate_group_empty:{group.group_id}")
            continue
        group_rows = [
            row_idx
            for evidence_id in group.evidence_ids
            if evidence_id in candidate_evidence_by_id
            for row_idx in candidate_evidence_by_id[evidence_id].header_row_indices
        ]
        group_label = clean_text(group.base_text)
        groups.append(
            ColumnHeaderGroup(
                group_id=group.group_id,
                table_id=table.table_id,
                row_idx=min(
                    group_rows,
                    default=min(candidate.header_row_indices, default=0),
                ),
                label=group_label,
                name=_normalize_header_name(group_label) or f"group_{len(groups)}",
                col_start=group_columns[0],
                col_end=group_columns[-1],
                leaf_col_indices=group_columns,
                evidence_ids=list(group.evidence_ids),
                inference_rule="explicit_cell_span",
                confidence=1.0,
            )
        )

    relationships: list[ColumnHeaderRelationship] = []
    for relationship in candidate.relationships:
        group = candidate_group_by_id.get(relationship.parent_group_id)
        leaf = candidate_leaf_by_id.get(relationship.child_leaf_id)
        if group is None or leaf is None:
            projection_errors.append(
                f"candidate_relationship_reference_missing:{relationship.relationship_id}"
            )
            continue
        relationships.append(
            ColumnHeaderRelationship(
                relationship_id=relationship.relationship_id,
                table_id=table.table_id,
                parent_group_id=relationship.parent_group_id,
                child_leaf_id=relationship.child_leaf_id,
                leaf_col_idx=leaf.physical_col_idx,
                evidence_ids=list(
                    dict.fromkeys([*group.evidence_ids, *leaf.evidence_ids])
                ),
                confidence=1.0,
            )
        )

    expected_relationships = {
        (group.group_id, leaf_id)
        for group in candidate.group_candidates
        for leaf_id in group.leaf_ids
    }
    observed_relationships = {
        (item.parent_group_id, item.child_leaf_id) for item in candidate.relationships
    }
    if observed_relationships != expected_relationships:
        projection_errors.append("candidate_group_relationships_incomplete")

    diagnostics.extend(projection_errors)
    schema = ColumnHeaderSchema(
        schema_id=schema_id,
        table_id=table.table_id,
        n_cols=table.n_cols,
        label_col_idx=0 if table.n_cols else None,
        header_rows_considered=list(candidate.header_row_indices),
        body_rows_considered=list(candidate.body_row_indices),
        leaf_header_row_idx=leaf_header_row_idx,
        leaves=leaves,
        groups=groups,
        relationships=relationships,
        evidence=evidence,
        diagnostics=list(dict.fromkeys(diagnostics)),
        confidence=0.0 if projection_errors else 1.0,
    )
    if projection_errors:
        return schema
    return validate_column_header_schema(schema)


def build_column_header_schemas(
    tables: list[NormalizedTable],
    header_structure_candidates: list[HeaderStructureCandidate],
) -> list[ColumnHeaderSchema]:
    """Project header candidates for normalized tables while preserving order."""
    candidates_by_table_id = {
        candidate.table_id: candidate for candidate in header_structure_candidates
    }
    return [
        build_column_header_schema(table, candidates_by_table_id.get(table.table_id))
        for table in tables
    ]


def column_header_schemas_to_payload(
    schemas: list[ColumnHeaderSchema],
) -> list[dict[str, object]]:
    """Serialize column header schemas as JSON-friendly records."""
    return [schema.model_dump(mode="json") for schema in schemas]


def column_header_descriptors(
    schema: ColumnHeaderSchema,
) -> list[ColumnHeaderDescriptor]:
    """Return canonical parser-facing column descriptors from a header schema."""
    groups_by_id = {group.group_id: group for group in schema.groups}
    context_by_leaf_id: dict[str, list[tuple[int, str, str]]] = {
        leaf.leaf_id: [] for leaf in schema.leaves
    }
    for relationship in schema.relationships:
        group = groups_by_id.get(relationship.parent_group_id)
        if group is not None:
            context_by_leaf_id.setdefault(relationship.child_leaf_id, []).append(
                (group.row_idx, group.group_id, group.label)
            )
    descriptors: list[ColumnHeaderDescriptor] = []
    for leaf in sorted(schema.leaves, key=lambda item: item.col_idx):
        context_items = sorted(context_by_leaf_id.get(leaf.leaf_id, []))
        context_labels = [label for _, _, label in context_items]
        context_ids = [group_id for _, group_id, _ in context_items]
        shared_context_label = (
            clean_text(" ".join(context_labels)) if context_labels else None
        )
        column_parts = [*context_labels]
        if leaf.leaf_label:
            column_parts.append(leaf.leaf_label)
        column_label = clean_text(" ".join(part for part in column_parts if part))
        header_path = [part for part in [*context_labels, leaf.leaf_label] if part]
        descriptors.append(
            ColumnHeaderDescriptor(
                leaf_id=leaf.leaf_id,
                col_idx=leaf.col_idx,
                original_col_idx=leaf.original_col_idx,
                column_label=column_label,
                column_name=_normalize_header_name(column_label)
                or leaf.leaf_name
                or f"column_{leaf.col_idx}",
                leaf_label=leaf.leaf_label,
                leaf_name=leaf.leaf_name,
                header_group_ids=context_ids,
                header_group_labels=context_labels,
                header_path=header_path,
                shared_context_label=shared_context_label,
                is_row_label_column=leaf.is_row_label_column,
                is_value_column=leaf.is_value_column,
            )
        )
    return descriptors


def column_header_labels(schema: ColumnHeaderSchema) -> list[str]:
    """Return parser-facing column header labels from a column header schema."""
    return [descriptor.column_label for descriptor in column_header_descriptors(schema)]


def column_header_comparison_labels(schema: ColumnHeaderSchema) -> list[str]:
    """Return normalized column labels for schema-based column comparison."""
    labels: list[str] = []
    for descriptor in column_header_descriptors(schema):
        normalized = HEADER_MARKUP_PATTERN.sub("", descriptor.column_label)
        normalized = (
            normalized.replace("\u00a0", " ")
            .replace("\u2009", " ")
            .replace("\u202f", " ")
        )
        normalized = HEADER_SPACE_PATTERN.sub(" ", normalized).strip().lower()
        normalized = HEADER_TRAILING_SPLIT_HYPHEN_PATTERN.sub("", normalized)
        normalized = HEADER_LEADING_SPLIT_HYPHEN_PATTERN.sub(r"\1", normalized)
        normalized = normalized.strip(" .,:;")
        labels.append(HEADER_SPACE_PATTERN.sub(" ", normalized).strip())
    return labels


def _normalize_header_name(value: str) -> str:
    cleaned = ALPHA_BOUNDARY_SEPARATOR_PATTERN.sub(" ", clean_text(value))
    return clean_text(NON_ALNUM_PATTERN.sub(" ", cleaned))
