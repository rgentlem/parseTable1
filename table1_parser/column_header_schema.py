"""Deterministic assembly of parser-native column header schemas."""

from __future__ import annotations

import re
from statistics import median
from typing import Any, NamedTuple

from table1_parser.schemas import (
    ColumnHeaderCellEvidence,
    ColumnHeaderDescriptor,
    ColumnHeaderGroup,
    ColumnHeaderLeaf,
    ColumnHeaderRelationship,
    ColumnHeaderSchema,
    ExtractedTable,
    NormalizedTable,
    TableCell,
)
from table1_parser.text_cleaning import clean_text
from table1_parser.validation.column_header_schema import validate_column_header_schema


CONTINUATION_PATTERN = re.compile(r"\bcont(?:inued)?\.?\b|\(\s*continued\s*\)", re.IGNORECASE)
TABLE_TITLE_PATTERN = re.compile(r"\btable\s*\d+\b", re.IGNORECASE)
NON_ALNUM_PATTERN = re.compile(r"[^A-Za-z0-9]+")
ALPHA_BOUNDARY_SEPARATOR_PATTERN = re.compile(r"(?<=[A-Za-z])[^A-Za-z0-9\s]+(?=[A-Za-z])")
HEADER_MARKUP_PATTERN = re.compile(r"[*_`]+")
HEADER_SPACE_PATTERN = re.compile(r"\s+")
LABEL_COLUMN_TOKENS = {"characteristic", "characteristics", "variable", "variables", "factor", "covariate"}


class _HeaderRun(NamedTuple):
    row_idx: int
    row_end_idx: int
    col_start: int
    col_end: int
    label: str
    evidence_positions: tuple[tuple[int, int], ...]
    inference_rule: str
    confidence: float


def build_column_header_schema(
    table: NormalizedTable,
    extracted_table: ExtractedTable | None = None,
) -> ColumnHeaderSchema:
    """Build one parser-native column header schema from a normalized table."""
    diagnostics: list[str] = []
    raw_grid = table.metadata.get("cleaned_rows")
    if not isinstance(raw_grid, list):
        diagnostics.append("missing_cleaned_rows")
        raw_grid = []
    grid = [[clean_text(str(cell)) for cell in row] if isinstance(row, list) else [] for row in raw_grid]
    first_numeric_body_row = _first_numeric_body_row(grid, table.n_cols)
    grid = _repair_wrapped_header_fragments(grid, table.n_cols, first_numeric_body_row)
    header_rows = [row_idx for row_idx in table.header_rows if 0 <= row_idx < len(grid)]
    body_rows = [row_idx for row_idx in table.body_rows if 0 <= row_idx < len(grid)]
    if len(header_rows) != len(table.header_rows):
        diagnostics.append("some_header_rows_out_of_grid_bounds")
    if len(body_rows) != len(table.body_rows):
        diagnostics.append("some_body_rows_out_of_grid_bounds")
    header_detection = table.metadata.get("header_detection")
    trusted_separator_header_rows = (
        isinstance(header_detection, dict)
        and header_detection.get("source") == "horizontal_rule_separator"
    )

    first_declared_body_row = min(body_rows) if body_rows else None
    declared_leaf_header_candidates = [
        row_idx for row_idx in header_rows if first_declared_body_row is None or row_idx < first_declared_body_row
    ]
    declared_leaf_header_row_idx = (
        max(declared_leaf_header_candidates) if declared_leaf_header_candidates else max(header_rows, default=None)
    )
    usable_header_rows = [
        row_idx
        for row_idx in header_rows
        if (len(header_rows) > 1 and row_idx == declared_leaf_header_row_idx)
        or not _looks_like_title_or_continuation_header([_grid_cell(grid, row_idx, col_idx) for col_idx in range(table.n_cols)])
    ]
    skipped_leaf_header_rows = [row_idx for row_idx in header_rows if row_idx not in usable_header_rows]
    for row_idx in skipped_leaf_header_rows:
        diagnostics.append(f"skipped_title_like_leaf_header_row:row={row_idx}")

    inferred_header_rows_used = False
    geometry_header_rows, geometry_body_start = _infer_header_rows_from_geometry(grid, table.n_cols, table.metadata)
    if (
        usable_header_rows
        and geometry_header_rows
        and _header_rows_before_first_rule(usable_header_rows, table.metadata)
        and not trusted_separator_header_rows
    ):
        usable_header_rows = geometry_header_rows
        header_rows = geometry_header_rows
        inferred_header_rows_used = True
        diagnostics.append(f"replaced_title_rows_with_geometry_header_rows:rows={','.join(map(str, geometry_header_rows))}")
        if geometry_body_start is not None:
            body_rows = [row_idx for row_idx in body_rows if row_idx >= geometry_body_start] or [
                row_idx
                for row_idx in range(geometry_body_start, len(grid))
                if any(_grid_cell(grid, row_idx, col_idx) for col_idx in range(table.n_cols))
            ]
    if not usable_header_rows:
        inferred_header_rows, inferred_body_start = geometry_header_rows, geometry_body_start
        if not inferred_header_rows:
            inferred_header_rows, inferred_body_start = _infer_header_rows_from_grid(grid, table.n_cols)
        if inferred_header_rows:
            inferred_header_rows_used = True
            usable_header_rows = inferred_header_rows
            header_rows = inferred_header_rows
            diagnostics.append(f"inferred_header_rows_from_body_values:rows={','.join(map(str, inferred_header_rows))}")
            if inferred_body_start is not None:
                trimmed_body_rows = [row_idx for row_idx in body_rows if row_idx >= inferred_body_start]
                if not trimmed_body_rows:
                    trimmed_body_rows = [
                        row_idx
                        for row_idx in range(inferred_body_start, len(grid))
                        if any(_grid_cell(grid, row_idx, col_idx) for col_idx in range(table.n_cols))
                    ]
                if trimmed_body_rows != body_rows:
                    diagnostics.append(f"trimmed_body_rows_after_inferred_headers:start={inferred_body_start}")
                    body_rows = trimmed_body_rows

    leaf_header_row_idx: int | None = None
    if usable_header_rows:
        first_body_row = min(body_rows) if body_rows else None
        prior_header_rows = [row_idx for row_idx in usable_header_rows if first_body_row is None or row_idx < first_body_row]
        leaf_header_row_idx = max(prior_header_rows) if prior_header_rows else max(usable_header_rows)
    else:
        diagnostics.append("no_header_rows_available")
    leaf_header_row_indices = [leaf_header_row_idx] if leaf_header_row_idx is not None else []
    if leaf_header_row_idx is not None:
        prior_rows = [row_idx for row_idx in usable_header_rows if row_idx < leaf_header_row_idx]
        if trusted_separator_header_rows and len(usable_header_rows) > 3:
            leaf_header_row_indices = sorted(usable_header_rows)
            diagnostics.append(
                "merged_separator_wrapped_leaf_header_rows:"
                f"rows={','.join(map(str, leaf_header_row_indices))}"
            )
        elif prior_rows:
            bounded_header_rows = sorted(row_idx for row_idx in usable_header_rows if row_idx <= leaf_header_row_idx)
            row_bounds = table.metadata.get("row_bounds")
            rules = table.metadata.get("horizontal_rules")
            split_after_position: int | None = None
            if isinstance(row_bounds, list) and isinstance(rules, list):
                numeric_rules = sorted(float(rule) for rule in rules if isinstance(rule, (int, float)))
                for position, (upper_row_idx, lower_row_idx) in enumerate(
                    zip(bounded_header_rows, bounded_header_rows[1:], strict=False)
                ):
                    if upper_row_idx >= len(row_bounds) or lower_row_idx >= len(row_bounds):
                        continue
                    upper_bounds = row_bounds[upper_row_idx]
                    lower_bounds = row_bounds[lower_row_idx]
                    if (
                        not isinstance(upper_bounds, (list, tuple))
                        or not isinstance(lower_bounds, (list, tuple))
                        or len(upper_bounds) != 2
                        or len(lower_bounds) != 2
                    ):
                        continue
                    upper_bottom = float(upper_bounds[1])
                    lower_top = float(lower_bounds[0])
                    if any(upper_bottom - 2.0 <= rule <= lower_top + 2.0 for rule in numeric_rules):
                        split_after_position = position
            if split_after_position is not None:
                split_rows = bounded_header_rows[split_after_position + 1 :]
                if len(split_rows) > 1 and leaf_header_row_idx in split_rows:
                    dense_start = next(
                        (
                            position
                            for position, row_idx in enumerate(split_rows)
                            if _row_nonempty_count(grid, row_idx, table.n_cols) >= max(4, table.n_cols // 3)
                        ),
                        None,
                    )
                    if dense_start is not None and dense_start > 0:
                        diagnostics.append(
                            "trimmed_sparse_group_rows_from_leaf_header_split:"
                            f"rows={','.join(map(str, split_rows[:dense_start]))}"
                        )
                        split_rows = split_rows[dense_start:]
                    leaf_header_row_indices = split_rows
                    diagnostics.append(f"split_wrapped_leaf_header_rows_by_rule:rows={','.join(map(str, split_rows))}")
            if leaf_header_row_indices == [leaf_header_row_idx] and inferred_header_rows_used:
                stacked_rows = [leaf_header_row_idx]
                for prior_row_idx in sorted(prior_rows, reverse=True):
                    if _physical_row_gap(table.metadata, prior_row_idx, stacked_rows[0]) > 5.0:
                        break
                    if _row_nonempty_count(grid, prior_row_idx, table.n_cols) < max(4, table.n_cols // 3):
                        break
                    stacked_rows.insert(0, prior_row_idx)
                if len(stacked_rows) > 1:
                    leaf_header_row_indices = stacked_rows
                    diagnostics.append(f"merged_wrapped_leaf_header_rows:rows={','.join(map(str, stacked_rows))}")
    leaf_header_row_set = set(leaf_header_row_indices)

    schema_id = f"{table.table_id}:column_header_schema"
    original_col_indices = _original_col_indices(table, extracted_table)
    grid, leaf_extra_evidence_positions = _repair_leading_leaf_fragments_by_geometry(
        grid,
        table.n_cols,
        leaf_header_row_indices,
        table.metadata,
        original_col_indices,
    )
    source_page_num = table.metadata.get("source_page_num")
    page_num = source_page_num if isinstance(source_page_num, int) and source_page_num >= 1 else None
    extracted_cells = _extracted_cells_by_position(extracted_table)
    metadata_cells = table.metadata.get("table_cells")
    evidence: list[ColumnHeaderCellEvidence] = []
    evidence_by_position: dict[tuple[int, int], str] = {}
    leaf_stack_start = min(leaf_header_row_indices) if leaf_header_row_indices else leaf_header_row_idx

    def evidence_for(row_idx: int, col_idx: int) -> str:
        existing_id = evidence_by_position.get((row_idx, col_idx))
        if existing_id is not None:
            return existing_id
        original_col_idx = original_col_indices[col_idx] if col_idx < len(original_col_indices) else None
        cleaned_text = _grid_cell(grid, row_idx, col_idx)
        extracted_cell = (
            extracted_cells.get((row_idx, original_col_idx))
            if original_col_idx is not None
            else extracted_cells.get((row_idx, col_idx))
        )
        raw_text = extracted_cell.text if extracted_cell is not None else None
        bbox = extracted_cell.bbox if extracted_cell is not None else None
        evidence_page_num = extracted_cell.page_num if extracted_cell is not None else page_num
        source = "extracted_cell" if extracted_cell is not None else "normalized_cleaned_row"
        if extracted_cell is None:
            metadata_bbox = _metadata_cell_bbox(metadata_cells, row_idx, original_col_idx if original_col_idx is not None else col_idx)
            if metadata_bbox is not None:
                bbox = metadata_bbox
                source = "metadata_table_cells"
        evidence_id = f"{schema_id}:evidence:{len(evidence)}"
        evidence.append(
            ColumnHeaderCellEvidence(
                evidence_id=evidence_id,
                table_id=table.table_id,
                row_idx=row_idx,
                col_idx=col_idx,
                original_row_idx=row_idx if extracted_cell is not None else None,
                original_col_idx=original_col_idx,
                raw_text=raw_text,
                cleaned_text=cleaned_text,
                bbox=bbox,
                page_num=evidence_page_num,
                source=source,
            )
        )
        evidence_by_position[(row_idx, col_idx)] = evidence_id
        return evidence_id

    leaves: list[ColumnHeaderLeaf] = []
    for col_idx in range(table.n_cols):
        leaf_evidence_ids: list[str] = []
        leaf_label = ""
        if leaf_header_row_idx is not None:
            leaf_label = clean_text(" ".join(_grid_cell(grid, row_idx, col_idx) for row_idx in leaf_header_row_indices))
            if not leaf_label and col_idx == 0:
                upper_label = next(
                    (
                        _grid_cell(grid, row_idx, col_idx)
                        for row_idx in sorted(usable_header_rows)
                        if leaf_stack_start is not None
                        and row_idx < leaf_stack_start
                        and clean_text(_grid_cell(grid, row_idx, col_idx)).lower() in LABEL_COLUMN_TOKENS
                    ),
                    "",
                )
                if upper_label:
                    leaf_label = upper_label
                    diagnostics.append(f"used_upper_row_label_leaf_header:col={col_idx}")
            elif not leaf_label and _looks_like_count_column(grid, body_rows, col_idx):
                leaf_label = "n"
                diagnostics.append(f"inferred_count_leaf_header:col={col_idx}")
            leaf_evidence_ids.extend(evidence_for(row_idx, col_idx) for row_idx in leaf_header_row_indices)
            for row_idx in leaf_header_row_indices:
                leaf_evidence_ids.extend(
                    evidence_for(row_idx, source_col_idx)
                    for source_col_idx in leaf_extra_evidence_positions.get((row_idx, col_idx), [])
                )
            if not leaf_label:
                diagnostics.append(f"blank_leaf_header:col={col_idx}")
        body_nonempty_row_indices: list[int] = []
        for row_idx in body_rows:
            if _grid_cell(grid, row_idx, col_idx):
                body_nonempty_row_indices.append(row_idx)
        if leaf_header_row_idx is None and not leaf_label:
            diagnostics.append(f"generated_blank_leaf_without_header:col={col_idx}")
        leaf_evidence_ids = list(dict.fromkeys(leaf_evidence_ids))
        left, center, right = _column_coordinates(
            [item for item in evidence if item.evidence_id in set(leaf_evidence_ids) and item.bbox is not None]
        )
        if center is None:
            diagnostics.append(f"missing_coordinate_evidence:col={col_idx}")
        leaves.append(
            ColumnHeaderLeaf(
                leaf_id=f"{schema_id}:leaf:{col_idx}",
                table_id=table.table_id,
                col_idx=col_idx,
                original_col_idx=original_col_indices[col_idx] if col_idx < len(original_col_indices) else None,
                is_row_label_column=col_idx == 0,
                is_value_column=col_idx != 0,
                leaf_header_row_idx=leaf_header_row_idx,
                leaf_label=leaf_label,
                leaf_name=_normalize_header_name(leaf_label) or f"column_{col_idx}",
                body_nonempty_row_indices=body_nonempty_row_indices,
                evidence_ids=leaf_evidence_ids,
                coordinate_left=left,
                coordinate_center=center,
                coordinate_right=right,
            )
        )

    groups: list[ColumnHeaderGroup] = []
    relationships: list[ColumnHeaderRelationship] = []
    if leaf_header_row_idx is not None:
        group_runs = _header_runs_for_groups(
            grid,
            table.n_cols,
            [row_idx for row_idx in usable_header_rows if row_idx < leaf_header_row_idx and row_idx not in leaf_header_row_set],
            table.metadata,
        )
        for run in group_runs:
            if inferred_header_rows_used and run.col_start == run.col_end:
                diagnostics.append(f"skipped_single_leaf_header_group:row={run.row_idx}:col={run.col_start}")
                continue
            if run.col_start == 0 and run.col_end > 0:
                diagnostics.append(f"skipped_label_column_header_span:row={run.row_idx}:col=0")
                continue
            if run.col_start == 0 and clean_text(run.label).lower() in LABEL_COLUMN_TOKENS:
                diagnostics.append(f"skipped_label_column_header_group:row={run.row_idx}:col=0")
                continue
            leaf_col_indices = list(range(run.col_start, run.col_end + 1))
            group_evidence_ids = [
                evidence_for(row_idx, col_idx)
                for row_idx, col_idx in run.evidence_positions
                if run.col_start <= col_idx <= run.col_end
            ]
            if not group_evidence_ids:
                group_evidence_ids = [evidence_for(run.row_idx, run.col_start)]
            group_id = f"{schema_id}:group:{len(groups)}"
            groups.append(
                ColumnHeaderGroup(
                    group_id=group_id,
                    table_id=table.table_id,
                    row_idx=run.row_idx,
                    label=run.label,
                    name=_normalize_header_name(run.label) or f"group_{len(groups)}",
                    col_start=run.col_start,
                    col_end=run.col_end,
                    leaf_col_indices=leaf_col_indices,
                    evidence_ids=list(dict.fromkeys(group_evidence_ids)),
                    inference_rule=run.inference_rule,
                    confidence=run.confidence,
                )
            )
            for leaf_col_idx in leaf_col_indices:
                relationship_evidence_ids = list(dict.fromkeys([*group_evidence_ids, evidence_for(run.row_idx, leaf_col_idx)]))
                relationships.append(
                    ColumnHeaderRelationship(
                        relationship_id=f"{schema_id}:relationship:{len(relationships)}",
                        table_id=table.table_id,
                        parent_group_id=group_id,
                        child_leaf_id=f"{schema_id}:leaf:{leaf_col_idx}",
                        leaf_col_idx=leaf_col_idx,
                        evidence_ids=relationship_evidence_ids,
                        confidence=run.confidence,
                    )
                )

    schema = ColumnHeaderSchema(
        schema_id=schema_id,
        table_id=table.table_id,
        n_cols=table.n_cols,
        label_col_idx=0 if table.n_cols > 0 else None,
        header_rows_considered=header_rows,
        body_rows_considered=body_rows,
        leaf_header_row_idx=leaf_header_row_idx,
        leaves=leaves,
        groups=groups,
        relationships=relationships,
        evidence=evidence,
        diagnostics=list(dict.fromkeys(diagnostics)),
        confidence=_schema_confidence(diagnostics, leaves, groups),
    )
    return validate_column_header_schema(schema)


def build_column_header_schemas(
    tables: list[NormalizedTable],
    extracted_tables: list[ExtractedTable] | None = None,
) -> list[ColumnHeaderSchema]:
    """Build column header schemas for normalized tables while preserving order."""
    schemas = [
        build_column_header_schema(
            table,
            extracted_tables[index] if extracted_tables is not None and index < len(extracted_tables) else None,
        )
        for index, table in enumerate(tables)
    ]
    return _enrich_base_schema_leaf_labels_from_continuations(tables, schemas)


def column_header_schemas_to_payload(
    schemas: list[ColumnHeaderSchema],
) -> list[dict[str, object]]:
    """Serialize column header schemas as JSON-friendly records."""
    return [schema.model_dump(mode="json") for schema in schemas]


def column_header_descriptors(schema: ColumnHeaderSchema) -> list[ColumnHeaderDescriptor]:
    """Return canonical parser-facing column descriptors from a header schema."""
    groups_by_id = {group.group_id: group for group in schema.groups}
    context_by_leaf_id: dict[str, list[tuple[int, str, str]]] = {leaf.leaf_id: [] for leaf in schema.leaves}
    for relationship in schema.relationships:
        group = groups_by_id.get(relationship.parent_group_id)
        if group is not None:
            context_by_leaf_id.setdefault(relationship.child_leaf_id, []).append((group.row_idx, group.group_id, group.label))
    descriptors: list[ColumnHeaderDescriptor] = []
    for leaf in sorted(schema.leaves, key=lambda item: item.col_idx):
        context_items = sorted(context_by_leaf_id.get(leaf.leaf_id, []))
        context_labels = [label for _, _, label in context_items]
        context_ids = [group_id for _, group_id, _ in context_items]
        shared_context_label = clean_text(" ".join(context_labels)) if context_labels else None
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
                column_name=_normalize_header_name(column_label) or leaf.leaf_name or f"column_{leaf.col_idx}",
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
        normalized = normalized.replace("\u00a0", " ").replace("\u2009", " ").replace("\u202f", " ")
        normalized = HEADER_SPACE_PATTERN.sub(" ", normalized).strip().lower()
        normalized = normalized.strip(" .,:;")
        labels.append(HEADER_SPACE_PATTERN.sub(" ", normalized).strip())
    return labels


def _enrich_base_schema_leaf_labels_from_continuations(
    tables: list[NormalizedTable],
    schemas: list[ColumnHeaderSchema],
) -> list[ColumnHeaderSchema]:
    enriched = list(schemas)
    latest_base_by_number: dict[int, int] = {}
    for index, table in enumerate(tables):
        continuation_number = table.metadata.get("continuation_of_table_number")
        table_number = table.metadata.get("table_number")
        if isinstance(continuation_number, int):
            base_index = latest_base_by_number.get(continuation_number)
            if base_index is None or base_index >= len(enriched) or index >= len(enriched):
                continue
            base_schema = enriched[base_index]
            continuation_schema = enriched[index]
            if base_schema.n_cols != continuation_schema.n_cols:
                continue
            new_leaves: list[ColumnHeaderLeaf] = []
            changed_cols: list[int] = []
            for base_leaf, continuation_leaf in zip(base_schema.leaves, continuation_schema.leaves, strict=False):
                replacement = _compatible_more_complete_leaf_label(base_leaf.leaf_label, continuation_leaf.leaf_label)
                if replacement is None:
                    new_leaves.append(base_leaf)
                    continue
                changed_cols.append(base_leaf.col_idx)
                new_leaves.append(
                    base_leaf.model_copy(
                        update={
                            "leaf_label": replacement,
                            "leaf_name": _normalize_header_name(replacement) or base_leaf.leaf_name,
                        }
                    )
                )
            if changed_cols:
                diagnostics = [
                    *base_schema.diagnostics,
                    "enriched_leaf_labels_from_continuation:"
                    f"table_index={index}:cols={','.join(map(str, changed_cols))}",
                ]
                enriched[base_index] = base_schema.model_copy(
                    update={
                        "leaves": new_leaves,
                        "diagnostics": list(dict.fromkeys(diagnostics)),
                    }
                )
        elif isinstance(table_number, int):
            latest_base_by_number[table_number] = index
    return enriched


def _compatible_more_complete_leaf_label(base_label: str, continuation_label: str) -> str | None:
    base = clean_text(base_label)
    continuation = clean_text(continuation_label)
    if not continuation or len(continuation) <= len(base):
        return None
    if not base:
        return continuation
    base_tokens = _normalized_label_tokens(base)
    continuation_tokens = _normalized_label_tokens(continuation)
    if not base_tokens:
        return continuation
    cursor = 0
    for token in continuation_tokens:
        if cursor < len(base_tokens) and token == base_tokens[cursor]:
            cursor += 1
    return continuation if cursor == len(base_tokens) else None


def _normalized_label_tokens(label: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9]+", clean_text(label))]


def _grid_cell(grid: list[list[str]], row_idx: int, col_idx: int) -> str:
    if row_idx < 0 or row_idx >= len(grid) or col_idx < 0 or col_idx >= len(grid[row_idx]):
        return ""
    return grid[row_idx][col_idx]


def _extracted_cells_by_position(extracted_table: ExtractedTable | None) -> dict[tuple[int, int], TableCell]:
    if extracted_table is None:
        return {}
    return {(cell.row_idx, cell.col_idx): cell for cell in extracted_table.cells}


def _original_col_indices(table: NormalizedTable, extracted_table: ExtractedTable | None) -> list[int | None]:
    source_col_indices = table.metadata.get("source_col_indices")
    if isinstance(source_col_indices, list) and len(source_col_indices) == table.n_cols:
        return [value if isinstance(value, int) and value >= 0 else None for value in source_col_indices]
    raw_n_cols = extracted_table.n_cols if extracted_table is not None else table.n_cols
    dropped_leading_cols = _nonnegative_int(table.metadata.get("dropped_leading_cols"))
    dropped_trailing_cols = _nonnegative_int(table.metadata.get("dropped_trailing_cols"))
    right_bound = max(dropped_leading_cols, raw_n_cols - dropped_trailing_cols)
    selected_columns = list(range(dropped_leading_cols, right_bound))
    repairs = table.metadata.get("column_repairs")
    if isinstance(repairs, dict):
        dropped_after_repair = repairs.get("dropped_empty_columns_after_repair")
        if isinstance(dropped_after_repair, list):
            dropped_positions = {idx for idx in dropped_after_repair if isinstance(idx, int)}
            selected_columns = [
                original_col_idx
                for normalized_position, original_col_idx in enumerate(selected_columns)
                if normalized_position not in dropped_positions
            ]
        if repairs.get("extra_wide_value_column") is not None and len(selected_columns) != table.n_cols:
            return [None for _ in range(table.n_cols)]
    if len(selected_columns) == table.n_cols:
        return selected_columns
    if extracted_table is not None and extracted_table.n_cols == table.n_cols:
        return list(range(table.n_cols))
    return [None for _ in range(table.n_cols)]


def _metadata_cell_bbox(
    table_cells: object,
    row_idx: int,
    col_idx: int,
) -> tuple[float, float, float, float] | None:
    if not isinstance(table_cells, list) or row_idx >= len(table_cells):
        return None
    row = table_cells[row_idx]
    if not isinstance(row, list) or col_idx >= len(row):
        return None
    return _bbox_from_value(row[col_idx])


def _bbox_from_value(value: Any) -> tuple[float, float, float, float] | None:
    if isinstance(value, dict) and all(key in value for key in ("x0", "top", "x1", "bottom")):
        try:
            return (float(value["x0"]), float(value["top"]), float(value["x1"]), float(value["bottom"]))
        except (TypeError, ValueError):
            return None
    if isinstance(value, (list, tuple)) and len(value) == 4:
        try:
            return tuple(float(part) for part in value)
        except (TypeError, ValueError):
            return None
    return None


def _column_coordinates(
    coordinate_evidence: list[ColumnHeaderCellEvidence],
) -> tuple[float | None, float | None, float | None]:
    bboxes = [item.bbox for item in coordinate_evidence if item.bbox is not None]
    if not bboxes:
        return None, None, None
    left = median([bbox[0] for bbox in bboxes])
    right = median([bbox[2] for bbox in bboxes])
    return round(left, 4), round((left + right) / 2.0, 4), round(right, 4)


def _looks_like_title_or_continuation_header(row: list[str]) -> bool:
    populated = [cell for cell in row if cell]
    if not populated:
        return False
    joined = clean_text(" ".join(populated))
    if CONTINUATION_PATTERN.search(joined) or TABLE_TITLE_PATTERN.search(joined):
        return True
    unique_count = len(set(populated))
    if (
        len(joined) > 80
        and len(populated) >= max(4, int(len(row) * 0.5))
        and unique_count >= max(3, int(len(populated) * 0.6))
    ):
        return True
    return len(populated) == 1 and len(joined) > 60


def _physical_row_gap(metadata: dict[str, object], upper_row_idx: int, lower_row_idx: int) -> float:
    row_bounds = metadata.get("row_bounds")
    if not isinstance(row_bounds, list) or lower_row_idx >= len(row_bounds) or upper_row_idx >= len(row_bounds):
        return float("inf")
    upper = row_bounds[upper_row_idx]
    lower = row_bounds[lower_row_idx]
    if not isinstance(upper, (list, tuple)) or not isinstance(lower, (list, tuple)) or len(upper) != 2 or len(lower) != 2:
        return float("inf")
    try:
        return max(0.0, float(lower[0]) - float(upper[1]))
    except (TypeError, ValueError):
        return float("inf")


def _header_rows_before_first_rule(row_indices: list[int], metadata: dict[str, object]) -> bool:
    row_bounds = metadata.get("row_bounds")
    rules = metadata.get("horizontal_rules")
    if not isinstance(row_bounds, list) or not isinstance(rules, list) or not row_indices:
        return False
    numeric_rules = sorted(float(value) for value in rules if isinstance(value, (int, float)))
    if not numeric_rules:
        return False
    first_rule = numeric_rules[0]
    for row_idx in row_indices:
        if row_idx >= len(row_bounds):
            return False
        bounds = row_bounds[row_idx]
        if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
            return False
        try:
            if float(bounds[1]) > first_rule + 3.0:
                return False
        except (TypeError, ValueError):
            return False
    return True


def _infer_header_rows_from_geometry(
    grid: list[list[str]],
    n_cols: int,
    metadata: dict[str, object],
) -> tuple[list[int], int | None]:
    row_bounds_raw = metadata.get("row_bounds")
    rules_raw = metadata.get("horizontal_rules")
    if not isinstance(row_bounds_raw, list) or not isinstance(rules_raw, list):
        return [], None
    row_bounds: list[tuple[float, float]] = []
    for value in row_bounds_raw:
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            return [], None
        try:
            row_bounds.append((float(value[0]), float(value[1])))
        except (TypeError, ValueError):
            return [], None
    rules = sorted(float(value) for value in rules_raw if isinstance(value, (int, float)))
    if len(row_bounds) != len(grid) or not rules:
        return [], None
    first_body_row_idx = _first_numeric_body_row(grid, n_cols)
    if first_body_row_idx is None or first_body_row_idx <= 0:
        return [], first_body_row_idx
    body_top = row_bounds[first_body_row_idx][0]
    lower_rules = [rule for rule in rules if rule < body_top]
    if not lower_rules:
        return [], first_body_row_idx
    header_bottom_rule = max(lower_rules)
    upper_rules = [rule for rule in lower_rules if rule < header_bottom_rule]
    header_top_rule = min(upper_rules) if upper_rules else None
    header_rows = [
        row_idx
        for row_idx, bounds in enumerate(row_bounds[:first_body_row_idx])
        if bounds[0] <= header_bottom_rule + 3.0
        and bounds[1] <= body_top + 1.0
        and (header_top_rule is None or bounds[0] >= header_top_rule - 3.0)
        and _row_nonempty_count(grid, row_idx, n_cols) >= 2
    ]
    return header_rows, first_body_row_idx


def _infer_header_rows_from_grid(grid: list[list[str]], n_cols: int) -> tuple[list[int], int | None]:
    """Infer a header stack when normalized header rows are unusable."""
    if n_cols <= 1:
        return [], None
    first_body_row_idx = _first_numeric_body_row(grid, n_cols)
    if first_body_row_idx is None or first_body_row_idx == 0:
        return [], first_body_row_idx

    candidate_rows: list[int] = []
    for row_idx in range(first_body_row_idx):
        row = [_grid_cell(grid, row_idx, col_idx) for col_idx in range(n_cols)]
        if _looks_like_title_or_continuation_header(row):
            continue
        if _row_nonempty_count(grid, row_idx, n_cols) < 2:
            continue
        candidate_rows.append(row_idx)
    return candidate_rows, first_body_row_idx


def _first_numeric_body_row(grid: list[list[str]], n_cols: int) -> int | None:
    for row_idx in range(len(grid)):
        label_cell = _grid_cell(grid, row_idx, 0)
        value_cells = [_grid_cell(grid, row_idx, col_idx) for col_idx in range(1, n_cols) if _grid_cell(grid, row_idx, col_idx)]
        numeric_value_cells = [cell for cell in value_cells if _looks_like_numeric_body_value(cell)]
        numeric_share = len(numeric_value_cells) / max(1, len(value_cells))
        if label_cell and len(numeric_value_cells) >= 2 and numeric_share >= 0.65:
            return row_idx
    return None


def _row_nonempty_count(grid: list[list[str]], row_idx: int, n_cols: int) -> int:
    return sum(bool(_grid_cell(grid, row_idx, col_idx)) for col_idx in range(n_cols))


def _looks_like_numeric_body_value(value: str) -> bool:
    cleaned = clean_text(value)
    if not cleaned or not any(char.isdigit() for char in cleaned):
        return False
    alpha_count = sum(char.isalpha() for char in cleaned)
    digit_count = sum(char.isdigit() for char in cleaned)
    return digit_count >= alpha_count


def _looks_like_row_label_column(grid: list[list[str]], body_rows: list[int], col_idx: int) -> bool:
    values = [clean_text(_grid_cell(grid, row_idx, col_idx)) for row_idx in body_rows]
    populated = [value for value in values if value]
    if len(populated) < max(3, len(body_rows) // 4):
        return False
    alpha_values = sum(bool(ALPHA_BOUNDARY_SEPARATOR_PATTERN.search(value) or any(char.isalpha() for char in value)) for value in populated)
    numeric_like = sum(_looks_like_numeric_body_value(value) for value in populated)
    return alpha_values >= max(3, len(populated) // 2) and numeric_like <= max(1, len(populated) // 5)


def _looks_like_count_column(grid: list[list[str]], body_rows: list[int], col_idx: int) -> bool:
    populated = [clean_text(_grid_cell(grid, row_idx, col_idx)) for row_idx in body_rows if clean_text(_grid_cell(grid, row_idx, col_idx))]
    if len(populated) < max(3, len(body_rows) // 4):
        return False
    integer_like = sum(bool(re.fullmatch(r"\d[\d,]*", value)) for value in populated)
    decimal_like = sum(bool(re.search(r"\d+\.\d+", value)) for value in populated)
    alpha_like = sum(any(char.isalpha() for char in value) for value in populated)
    return (
        integer_like >= max(3, int(len(populated) * 0.65))
        and decimal_like == 0
        and alpha_like <= max(2, len(populated) // 8)
    )


def _repair_wrapped_header_fragments(
    grid: list[list[str]],
    n_cols: int,
    first_body_row_idx: int | None,
) -> list[list[str]]:
    if first_body_row_idx is None:
        return grid
    repaired = [list(row) for row in grid]
    for row_idx in range(min(first_body_row_idx, len(repaired))):
        row = repaired[row_idx]
        for col_idx in range(1, min(n_cols, len(row))):
            left = clean_text(row[col_idx - 1])
            right = clean_text(row[col_idx])
            if not left or not right or left.count("(") <= left.count(")"):
                continue
            balance = left.count("(") - left.count(")")
            prefix_tokens: list[str] = []
            suffix_tokens = right.split()
            while suffix_tokens and balance > 0:
                token = suffix_tokens.pop(0)
                prefix_tokens.append(token)
                balance += token.count("(") - token.count(")")
            if balance > 0 or not prefix_tokens:
                continue
            row[col_idx - 1] = clean_text(f"{left} {' '.join(prefix_tokens)}")
            row[col_idx] = clean_text(" ".join(suffix_tokens))
    return repaired


def _repair_leading_leaf_fragments_by_geometry(
    grid: list[list[str]],
    n_cols: int,
    row_indices: list[int],
    metadata: dict[str, object],
    original_col_indices: list[int | None],
) -> tuple[list[list[str]], dict[tuple[int, int], list[int]]]:
    repaired = [list(row) for row in grid]
    moved_evidence: dict[tuple[int, int], list[int]] = {}
    for row_idx in row_indices:
        for col_idx in range(1, n_cols):
            current = _grid_cell(repaired, row_idx, col_idx)
            previous = _grid_cell(repaired, row_idx, col_idx - 1)
            parts = current.split(maxsplit=1)
            if not previous or len(parts) != 2 or len(parts[0]) > 2 or not any(char.isalnum() for char in parts[0]):
                continue
            if (
                len(parts[0]) == 1
                and parts[0].isalpha()
                and parts[0].isupper()
                and parts[1][:1].islower()
            ):
                continue
            should_move = False
            previous_source_col = original_col_indices[col_idx - 1] if col_idx - 1 < len(original_col_indices) else None
            current_source_col = original_col_indices[col_idx] if col_idx < len(original_col_indices) else None
            if previous_source_col is not None and current_source_col is not None:
                previous_bbox = _metadata_cell_bbox(metadata.get("table_cells"), row_idx, previous_source_col)
                current_bbox = _metadata_cell_bbox(metadata.get("table_cells"), row_idx, current_source_col)
                if previous_bbox is not None and current_bbox is not None:
                    previous_center = (previous_bbox[0] + previous_bbox[2]) / 2.0
                    current_center = (current_bbox[0] + current_bbox[2]) / 2.0
                    boundary = (previous_center + current_center) / 2.0
                    first_share = min(0.5, max(0.05, len(parts[0]) / max(1, len(current))))
                    first_center = current_bbox[0] + ((current_bbox[2] - current_bbox[0]) * first_share / 2.0)
                    should_move = current_bbox[0] <= boundary and first_center < boundary
            if not should_move:
                previous_stack_has_text = any(
                    other_row_idx != row_idx and bool(_grid_cell(repaired, other_row_idx, col_idx - 1))
                    for other_row_idx in row_indices
                )
                current_stack_has_text = any(
                    other_row_idx != row_idx and bool(_grid_cell(repaired, other_row_idx, col_idx))
                    for other_row_idx in row_indices
                )
                current_remainder_has_alpha = any(char.isalpha() for char in parts[1])
                should_move = previous_stack_has_text and current_stack_has_text and current_remainder_has_alpha
            if should_move:
                repaired[row_idx][col_idx - 1] = clean_text(f"{previous} {parts[0]}")
                repaired[row_idx][col_idx] = clean_text(parts[1])
                moved_evidence.setdefault((row_idx, col_idx - 1), []).append(col_idx)
    return repaired, moved_evidence


def _header_runs_for_groups(
    grid: list[list[str]],
    n_cols: int,
    row_indices: list[int],
    metadata: dict[str, object],
) -> list[_HeaderRun]:
    runs: list[_HeaderRun] = []
    header_detection = metadata.get("header_detection")
    trust_structural_header_rows = (
        isinstance(header_detection, dict)
        and header_detection.get("source") in {"value_matrix_boundary", "value_region_anchor"}
    )
    for row_idx in sorted(row_indices):
        row = [_grid_cell(grid, row_idx, col_idx) for col_idx in range(n_cols)]
        if not trust_structural_header_rows and _looks_like_title_or_continuation_header(row):
            continue
        row_runs: list[_HeaderRun] = []
        geometry_gap_used = False
        if n_cols >= 4 and clean_text(row[0]).lower() in LABEL_COLUMN_TOKENS and all(row[col_idx] for col_idx in range(1, n_cols)):
            gaps: list[tuple[int, float]] = []
            for col_idx in range(1, n_cols - 1):
                left_bbox = _metadata_cell_bbox(metadata.get("table_cells"), row_idx, col_idx)
                right_bbox = _metadata_cell_bbox(metadata.get("table_cells"), row_idx, col_idx + 1)
                if left_bbox is not None and right_bbox is not None:
                    gaps.append((col_idx, float(right_bbox[0]) - float(left_bbox[2])))
            positive_gaps = [gap for _, gap in gaps if gap > 0]
            split_cols = [
                col_idx
                for col_idx, gap in gaps
                if positive_gaps and gap >= max(24.0, median(positive_gaps) * 3.0)
            ]
            if split_cols:
                geometry_gap_used = True
                start = 1
                for split_col in [*split_cols, n_cols - 1]:
                    label = clean_text(" ".join(row[col_idx] for col_idx in range(start, split_col + 1)))
                    if split_col > start and label:
                        positions = tuple((row_idx, col_idx) for col_idx in range(start, split_col + 1))
                        row_runs.append(
                            _HeaderRun(row_idx, row_idx, start, split_col, label, positions, "explicit_cell_span", 0.82)
                        )
                    start = split_col + 1
        if not row_runs:
            split_distinct_cols: set[int] = set()
            probe_col = 0
            while probe_col < n_cols:
                if not row[probe_col]:
                    probe_col += 1
                    continue
                segment_start = probe_col
                seen_segment: set[str] = set()
                while probe_col < n_cols and row[probe_col] and row[probe_col] not in seen_segment:
                    seen_segment.add(row[probe_col])
                    probe_col += 1
                if probe_col == n_cols and len(seen_segment) > 3 and segment_start <= max(1, n_cols // 3):
                    split_distinct_cols.update(range(segment_start, probe_col))
                while probe_col < n_cols and row[probe_col]:
                    probe_col += 1
            col_idx = 0
            while col_idx < n_cols:
                if not row[col_idx]:
                    col_idx += 1
                    continue
                start = col_idx
                values: list[str] = []
                positions: list[tuple[int, int]] = []
                repeated_block = start + 1 < n_cols and row[start + 1] == row[start]
                seen: set[str] = set()
                while col_idx < n_cols and row[col_idx] and (start != 0 or col_idx == 0):
                    if start in split_distinct_cols and col_idx > start:
                        break
                    if repeated_block and row[col_idx] != row[start]:
                        break
                    if not repeated_block and row[col_idx] in seen:
                        break
                    values.append(row[col_idx])
                    positions.append((row_idx, col_idx))
                    seen.add(row[col_idx])
                    col_idx += 1
                label = values[0] if len(set(values)) == 1 else clean_text(" ".join(values))
                inference_rule = "repeated_label_span" if len(values) > 1 and len(set(values)) == 1 else "explicit_cell_span"
                confidence = 0.92 if inference_rule == "repeated_label_span" else 0.86
                row_runs.append(_HeaderRun(row_idx, row_idx, start, col_idx - 1, label, tuple(positions), inference_rule, confidence))
        value_runs = [
            run
            for run in row_runs
            if not (run.col_start == 0 and clean_text(run.label).lower() in LABEL_COLUMN_TOKENS)
        ]
        has_blank_gap = any(
            next_run.col_start > run.col_end + 1
            for run, next_run in zip(value_runs, value_runs[1:], strict=False)
        )
        has_text_run = any(
            run.col_end > run.col_start and run.inference_rule == "explicit_cell_span"
            for run in value_runs
        )
        repeated_single_cell_labels = (
            len(value_runs) > 1
            and len({run.label for run in value_runs}) == 1
            and all(run.col_start == run.col_end for run in value_runs)
        )
        if repeated_single_cell_labels:
            expanded_repeated: list[_HeaderRun] = []
            for run in row_runs:
                if run in value_runs and run.col_start > 1 and not row[run.col_start - 1]:
                    expanded_repeated.append(
                        run._replace(
                            col_start=run.col_start - 1,
                            inference_rule="single_cell_blank_span",
                            confidence=min(run.confidence, 0.78),
                        )
                    )
                else:
                    expanded_repeated.append(run)
            row_runs = expanded_repeated
            value_runs = [
                run
                for run in row_runs
                if not (run.col_start == 0 and clean_text(run.label).lower() in LABEL_COLUMN_TOKENS)
            ]
        if not geometry_gap_used and len(value_runs) >= 2 and (has_blank_gap or has_text_run) and not repeated_single_cell_labels:
            expanded: list[_HeaderRun] = []
            for run in row_runs:
                if run not in value_runs:
                    expanded.append(run)
                    continue
                if has_text_run:
                    target_start = max(1, run.col_start - 1)
                else:
                    target_start = 1 if run == value_runs[0] and run.col_start > 1 else run.col_start
                next_starts = [next_run.col_start for next_run in value_runs if next_run.col_start > run.col_start]
                span_end = min(next_starts) - (2 if has_text_run else 1) if next_starts else n_cols - 1
                expanded.append(
                    run._replace(
                        col_start=target_start,
                        col_end=max(run.col_end, span_end, target_start),
                        inference_rule="single_cell_blank_span" if run.col_start == run.col_end else run.inference_rule,
                        confidence=min(run.confidence, 0.78) if span_end > run.col_end else run.confidence,
                    )
                )
            row_runs = expanded
        for run in row_runs:
            match_idx = next(
                (
                    idx
                    for idx in range(len(runs) - 1, -1, -1)
                    if _can_stack_header_runs(runs[idx], run, metadata)
                ),
                None,
            )
            if match_idx is None:
                runs.append(run)
            else:
                upper = runs[match_idx]
                runs[match_idx] = _HeaderRun(
                    upper.row_idx,
                    run.row_end_idx,
                    min(upper.col_start, run.col_start),
                    max(upper.col_end, run.col_end),
                    clean_text(f"{upper.label} {run.label}"),
                    (*upper.evidence_positions, *run.evidence_positions),
                    "explicit_cell_span",
                    min(upper.confidence, run.confidence),
                )
    return runs


def _can_stack_header_runs(
    upper: _HeaderRun,
    lower: _HeaderRun,
    metadata: dict[str, object],
) -> bool:
    if lower.row_idx <= upper.row_end_idx:
        return False
    if lower.row_idx - upper.row_end_idx > 1 and _physical_row_gap(metadata, upper.row_end_idx, lower.row_idx) > 5.0:
        return False
    overlap = min(upper.col_end, lower.col_end) - max(upper.col_start, lower.col_start) + 1
    smaller_width = min(upper.col_end - upper.col_start + 1, lower.col_end - lower.col_start + 1)
    return (
        overlap > 0
        and overlap / max(1, smaller_width) >= 0.75
        and upper.col_start == lower.col_start
        and upper.col_end == lower.col_end
    )


def _schema_confidence(
    diagnostics: list[str],
    leaves: list[ColumnHeaderLeaf],
    groups: list[ColumnHeaderGroup],
) -> float | None:
    if not leaves:
        return None
    base = 0.9
    if any(diagnostic.startswith("missing_cleaned_rows") for diagnostic in diagnostics):
        base -= 0.45
    if any(diagnostic.startswith("no_header_rows_available") for diagnostic in diagnostics):
        base -= 0.35
    missing_coordinate_count = sum(diagnostic.startswith("missing_coordinate_evidence") for diagnostic in diagnostics)
    if missing_coordinate_count:
        base -= min(0.2, missing_coordinate_count / max(1, len(leaves)) * 0.2)
    if not groups:
        base -= 0.05
    return round(max(0.05, min(0.98, base)), 4)


def _nonnegative_int(value: object) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def _normalize_header_name(value: str) -> str:
    cleaned = ALPHA_BOUNDARY_SEPARATOR_PATTERN.sub(" ", clean_text(value))
    return clean_text(NON_ALNUM_PATTERN.sub(" ", cleaned))
