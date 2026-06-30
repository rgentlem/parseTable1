"""Build the resolved semantic table working set."""

from __future__ import annotations

import re

from table1_parser.column_header_schema import column_header_comparison_labels
from table1_parser.schemas import (
    ColumnHeaderSchema,
    ColumnSchemaCompatibilityDecision,
    DroppedSourceRow,
    IntegrationBoundary,
    NormalizedTable,
    ResolvedRowProvenance,
    ResolvedTable,
    ResolvedTableSet,
    SourceTableResolution,
    TableResolutionDecision,
)


TABLE_NUMBER_PATTERN = re.compile(r"\btable\s*(\d+)\b", re.IGNORECASE)
CONTINUATION_PATTERN = re.compile(r"\bcont(?:inued)?\.?\b|\(\s*continued\s*\)", re.IGNORECASE)
CONTINUED_ROW_PATTERN = re.compile(r"^\(?\s*continued\s*\)?$", re.IGNORECASE)


def _trailing_continuation_table_number(table: NormalizedTable) -> int | None:
    trailing_rows = table.metadata.get("trailing_non_table_rows")
    if not isinstance(trailing_rows, dict):
        return None
    reasons = trailing_rows.get("reasons")
    if not isinstance(reasons, list) or "trailing_continuation_note" not in {str(reason) for reason in reasons}:
        return None
    table_number = trailing_rows.get("continuation_table_number")
    if isinstance(table_number, int) and not isinstance(table_number, bool) and table_number >= 1:
        return table_number
    return None


def _has_trailing_continuation_note(table: NormalizedTable) -> bool:
    trailing_rows = table.metadata.get("trailing_non_table_rows")
    if not isinstance(trailing_rows, dict):
        return False
    reasons = trailing_rows.get("reasons")
    return isinstance(reasons, list) and "trailing_continuation_note" in {str(reason) for reason in reasons}


def _has_post_header_continuation_note(table: NormalizedTable) -> bool:
    header_detection = table.metadata.get("header_detection")
    note_rows = header_detection.get("continuation_note_rows") if isinstance(header_detection, dict) else None
    return isinstance(note_rows, list) and bool(note_rows)


def build_resolved_table_set(
    normalized_tables: list[NormalizedTable],
    column_header_schemas: list[ColumnHeaderSchema] | None = None,
) -> ResolvedTableSet:
    """Return the initial resolved working set from normalized tables."""
    resolved_tables: list[ResolvedTable] = []
    decisions: list[TableResolutionDecision] = []
    source_tables: list[SourceTableResolution] = []
    latest_fragment_by_number: dict[int, int] = {}
    parent_indices_by_number: dict[int, list[int]] = {}
    source_to_resolved_index: dict[int, int] = {}

    for source_index, table in enumerate(normalized_tables):
        decision_id = f"resolved_table_decision_{source_index}"
        page_num = table.metadata.get("source_page_num")
        source_page_num = (
            page_num if isinstance(page_num, int) and not isinstance(page_num, bool) and page_num >= 1 else None
        )
        source_page_num_by_row_idx: dict[int, int] = {}
        source_row_page_nums = table.metadata.get("source_row_page_nums")
        if isinstance(source_row_page_nums, list):
            for row_idx, row_page_num in enumerate(source_row_page_nums):
                if isinstance(row_page_num, int) and not isinstance(row_page_num, bool) and row_page_num >= 1:
                    source_page_num_by_row_idx[row_idx] = row_page_num
        elif isinstance(source_row_page_nums, dict):
            for row_idx_value, row_page_num in source_row_page_nums.items():
                row_idx = None
                if isinstance(row_idx_value, int) and not isinstance(row_idx_value, bool):
                    row_idx = row_idx_value
                elif isinstance(row_idx_value, str) and row_idx_value.isdecimal():
                    row_idx = int(row_idx_value)
                if (
                    row_idx is not None
                    and row_idx >= 0
                    and isinstance(row_page_num, int)
                    and not isinstance(row_page_num, bool)
                    and row_page_num >= 1
                ):
                    source_page_num_by_row_idx[row_idx] = row_page_num
        logical_table_number = table.metadata.get("table_number")
        if (
            not isinstance(logical_table_number, int)
            or isinstance(logical_table_number, bool)
            or logical_table_number < 1
        ):
            logical_table_number = None
        trailing_continuation_number = _trailing_continuation_table_number(table)

        title_caption_text = " ".join(part for part in [table.title, table.caption] if part)
        if logical_table_number is None:
            table_number_match = TABLE_NUMBER_PATTERN.search(title_caption_text)
            if table_number_match is not None:
                logical_table_number = int(table_number_match.group(1))

        cleaned_rows = table.metadata.get("cleaned_rows")
        first_rows_text = ""
        if isinstance(cleaned_rows, list):
            first_row_texts: list[str] = []
            for row in cleaned_rows[:2]:
                if isinstance(row, list):
                    first_row_texts.append(" ".join(str(cell) for cell in row if cell))
                elif row:
                    first_row_texts.append(str(row))
            first_rows_text = " ".join(first_row_texts)

        continuation_number: int | None = None
        continuation_identity_evidence: list[str] = []
        metadata_continuation_number = table.metadata.get("continuation_of_table_number")
        metadata_is_continuation = table.metadata.get("is_continuation") is True

        if isinstance(metadata_continuation_number, int) and not isinstance(metadata_continuation_number, bool):
            if metadata_continuation_number >= 1 and (
                metadata_is_continuation
                or CONTINUATION_PATTERN.search(title_caption_text)
                or CONTINUATION_PATTERN.search(first_rows_text)
            ):
                continuation_number = metadata_continuation_number
                continuation_identity_evidence.append(
                    f"metadata_continuation_of_table_number:{metadata_continuation_number}"
                )
                if metadata_is_continuation:
                    continuation_identity_evidence.append("metadata_is_continuation:true")

        if continuation_number is None and metadata_is_continuation and logical_table_number is not None:
            continuation_number = logical_table_number
            continuation_identity_evidence.append("metadata_is_continuation:true")
            continuation_identity_evidence.append(f"metadata_table_number:{logical_table_number}")

        if continuation_number is None and CONTINUATION_PATTERN.search(title_caption_text):
            match = TABLE_NUMBER_PATTERN.search(title_caption_text)
            if match is not None:
                continuation_number = int(match.group(1))
                continuation_identity_evidence.append(f"title_or_caption_table_continued:{continuation_number}")

        if continuation_number is None and CONTINUATION_PATTERN.search(first_rows_text):
            match = TABLE_NUMBER_PATTERN.search(first_rows_text)
            if match is not None:
                continuation_number = int(match.group(1))
                continuation_identity_evidence.append(f"first_rows_table_continued:{continuation_number}")

        boundary_parent_index: int | None = None
        if (
            continuation_number is None
            and not title_caption_text
            and logical_table_number is None
            and not metadata_is_continuation
            and source_index > 0
            and isinstance(source_page_num, int)
            and not isinstance(source_page_num, bool)
        ):
            prior_table = normalized_tables[source_index - 1]
            prior_page = prior_table.metadata.get("source_page_num")
            prior_trailing_number = _trailing_continuation_table_number(prior_table)
            if (
                isinstance(prior_page, int)
                and not isinstance(prior_page, bool)
                and source_page_num == prior_page + 1
                and _has_post_header_continuation_note(table)
                and _has_trailing_continuation_note(prior_table)
            ):
                boundary_parent_index = source_index - 1
                continuation_number = prior_trailing_number
                continuation_identity_evidence.extend(
                    [
                        "adjacent_page_boundary_continuation_notes",
                        f"prior_trailing_continuation_note:{prior_table.table_id}",
                        f"current_post_header_continuation_note:{table.table_id}",
                    ]
                )
                if prior_trailing_number is not None:
                    continuation_identity_evidence.append(f"prior_trailing_continuation_table_number:{prior_trailing_number}")

        if (
            continuation_number is None
            and not title_caption_text
            and logical_table_number is None
            and not metadata_is_continuation
            and source_index > 0
            and isinstance(source_page_num, int)
            and not isinstance(source_page_num, bool)
        ):
            prior_table = normalized_tables[source_index - 1]
            prior_page = prior_table.metadata.get("source_page_num")
            prior_rows = prior_table.metadata.get("cleaned_rows")
            prior_last_body_row_idx = prior_table.body_rows[-1] if prior_table.body_rows else None
            prior_last_body_row = (
                prior_rows[prior_last_body_row_idx]
                if isinstance(prior_rows, list)
                and isinstance(prior_last_body_row_idx, int)
                and prior_last_body_row_idx < len(prior_rows)
                else None
            )
            if (
                isinstance(prior_page, int)
                and not isinstance(prior_page, bool)
                and source_page_num == prior_page + 1
                and isinstance(prior_last_body_row, list)
                and prior_last_body_row
                and CONTINUED_ROW_PATTERN.fullmatch(str(prior_last_body_row[0]).strip()) is not None
                and all(not str(cell).strip() for cell in prior_last_body_row[1:])
            ):
                boundary_parent_index = source_index - 1
                continuation_identity_evidence.extend(
                    [
                        "adjacent_page_after_empty_continued_row",
                        f"prior_trailing_continued_row:{prior_table.table_id}",
                    ]
                )

        if (
            continuation_number is None
            and not title_caption_text
            and logical_table_number is None
            and not metadata_is_continuation
            and not CONTINUATION_PATTERN.search(first_rows_text)
            and isinstance(cleaned_rows, list)
            and bool(table.body_rows)
            and table.n_cols >= 2
        ):
            prior_items = sorted(latest_fragment_by_number.items(), key=lambda item: item[1], reverse=True)
            for prior_table_number, prior_index in prior_items:
                prior_page = normalized_tables[prior_index].metadata.get("source_page_num")
                if (
                    isinstance(prior_page, int)
                    and not isinstance(prior_page, bool)
                    and isinstance(source_page_num, int)
                    and source_page_num == prior_page + 1
                ):
                    continuation_number = prior_table_number
                    continuation_identity_evidence.append(
                        f"adjacent_uncaptioned_fragment_after_table:{prior_table_number}"
                    )
                    break

        is_continuation_candidate = bool(continuation_identity_evidence) and (
            continuation_number is not None or boundary_parent_index is not None
        )
        parent_index: int | None = None
        parent_id: str | None = None
        parent_diagnostics: list[str] = []
        if is_continuation_candidate and boundary_parent_index is not None:
            parent_index = boundary_parent_index
            parent_id = normalized_tables[parent_index].table_id
            continuation_identity_evidence.append(f"parent_selected:{parent_id}")
            parent_diagnostics.append(f"parent_table_index:{parent_index}")
            parent_diagnostics.append("parent_selected_from_adjacent_boundary_continuation_notes")
        elif is_continuation_candidate and continuation_number is not None:
            parent_candidates = [
                index
                for index in parent_indices_by_number.get(continuation_number, [])
                if index < source_index
            ]
            compatible_parent_indices: list[int] = []
            for candidate_index in reversed(parent_candidates):
                candidate = normalized_tables[candidate_index]
                candidate_page = candidate.metadata.get("source_page_num")
                candidate_orientation = candidate.metadata.get("orientation_strategy")
                continuation_orientation = table.metadata.get("orientation_strategy")
                if (
                    isinstance(candidate_page, int)
                    and not isinstance(candidate_page, bool)
                    and source_page_num is not None
                    and candidate_page > source_page_num
                ):
                    parent_diagnostics.append(f"parent_page_after_continuation:table_index={candidate_index}")
                    continue
                if (
                    isinstance(candidate_orientation, str)
                    and isinstance(continuation_orientation, str)
                    and candidate_orientation != continuation_orientation
                ):
                    parent_diagnostics.append(f"parent_orientation_mismatch:table_index={candidate_index}")
                    continue
                compatible_parent_indices.append(candidate_index)

            if compatible_parent_indices:
                closest_parent_index = compatible_parent_indices[0]
                closest_parent_page = normalized_tables[closest_parent_index].metadata.get("source_page_num")
                same_page_parent_indices = [
                    index
                    for index in compatible_parent_indices
                    if closest_parent_page is not None
                    and normalized_tables[index].metadata.get("source_page_num") == closest_parent_page
                ]
                if len(same_page_parent_indices) > 1:
                    parent_diagnostics.append(
                        "ambiguous_parent_candidates_same_page:"
                        + ",".join(str(index) for index in same_page_parent_indices)
                    )
                else:
                    parent_index = closest_parent_index
                    parent_id = normalized_tables[parent_index].table_id
                    continuation_identity_evidence.append(f"parent_selected:{parent_id}")
                    parent_diagnostics.append(f"parent_table_index:{parent_index}")
            else:
                parent_diagnostics.append("no_compatible_parent_fragment")

        column_schema_decision: ColumnSchemaCompatibilityDecision | None = None
        if is_continuation_candidate and parent_index is not None:
            base_table = normalized_tables[parent_index]
            base_schema = (
                column_header_schemas[parent_index]
                if column_header_schemas is not None and parent_index < len(column_header_schemas)
                else None
            )
            continuation_schema = (
                column_header_schemas[source_index]
                if column_header_schemas is not None and source_index < len(column_header_schemas)
                else None
            )
            base_schema_usable = base_schema is not None and base_schema.table_id == base_table.table_id and bool(base_schema.leaves)
            continuation_schema_usable = (
                continuation_schema is not None
                and continuation_schema.table_id == table.table_id
                and bool(continuation_schema.leaves)
            )
            base_headers = column_header_comparison_labels(base_schema) if base_schema_usable else []
            continuation_headers = (
                column_header_comparison_labels(continuation_schema) if continuation_schema_usable else []
            )
            base_headers_for_match = base_headers
            continuation_headers_for_match = continuation_headers
            if (
                boundary_parent_index is not None
                and base_schema_usable
                and continuation_schema_usable
            ):
                row_label_columns = {
                    leaf.col_idx
                    for leaf in [*base_schema.leaves, *continuation_schema.leaves]
                    if leaf.is_row_label_column
                }
                if row_label_columns:
                    base_headers_for_match = [
                        header for col_idx, header in enumerate(base_headers) if col_idx not in row_label_columns
                    ]
                    continuation_headers_for_match = [
                        header
                        for col_idx, header in enumerate(continuation_headers)
                        if col_idx not in row_label_columns
                    ]
            normalized_column_count_match = base_table.n_cols == table.n_cols
            column_diagnostics: list[str] = []

            if not base_schema_usable:
                column_diagnostics.append(f"column_header_schema_missing_or_empty:table_index={parent_index}")
            if not continuation_schema_usable:
                column_diagnostics.append(f"column_header_schema_missing_or_empty:table_index={source_index}")
            if not normalized_column_count_match:
                column_diagnostics.append(
                    f"normalized_column_count_mismatch:base={base_table.n_cols}:continuation={table.n_cols}"
                )
            if (
                base_schema_usable
                and continuation_schema_usable
                and base_headers_for_match != continuation_headers_for_match
            ):
                column_diagnostics.append(
                    f"column_header_mismatch:base={base_headers}:continuation={continuation_headers}"
                )
            elif (
                base_schema_usable
                and continuation_schema_usable
                and base_headers != continuation_headers
            ):
                column_diagnostics.append("row_label_column_header_mismatch_ignored_for_boundary_continuation")

            if not base_schema_usable or not continuation_schema_usable:
                column_schema_decision = ColumnSchemaCompatibilityDecision(
                    decision_id=f"column_schema_decision_{parent_index}_{source_index}",
                    base_table_id=base_table.table_id,
                    continuation_table_id=table.table_id,
                    status="schema_missing",
                    base_column_headers=base_headers,
                    continuation_column_headers=continuation_headers,
                    normalized_column_count_match=normalized_column_count_match,
                    decision_reason="column_header_schema_missing",
                    diagnostics=column_diagnostics,
                    confidence=0.0,
                )
            elif normalized_column_count_match and base_headers_for_match == continuation_headers_for_match:
                column_schema_decision = ColumnSchemaCompatibilityDecision(
                    decision_id=f"column_schema_decision_{parent_index}_{source_index}",
                    base_table_id=base_table.table_id,
                    continuation_table_id=table.table_id,
                    status="match",
                    base_column_headers=base_headers,
                    continuation_column_headers=continuation_headers,
                    normalized_column_count_match=True,
                    decision_reason="schema_headers_and_column_count_match",
                    diagnostics=column_diagnostics,
                    confidence=0.95,
                )
            else:
                column_schema_decision = ColumnSchemaCompatibilityDecision(
                    decision_id=f"column_schema_decision_{parent_index}_{source_index}",
                    base_table_id=base_table.table_id,
                    continuation_table_id=table.table_id,
                    status="rejected",
                    base_column_headers=base_headers,
                    continuation_column_headers=continuation_headers,
                    normalized_column_count_match=normalized_column_count_match,
                    decision_reason="schema_headers_or_column_count_mismatch",
                    diagnostics=column_diagnostics,
                    confidence=0.2,
                )

        if column_schema_decision is not None and column_schema_decision.status == "match" and parent_index is not None:
            parent_resolved_index = source_to_resolved_index.get(parent_index)
            parent_resolved = resolved_tables[parent_resolved_index] if parent_resolved_index is not None else None
            parent_rows = parent_resolved.table.metadata.get("cleaned_rows") if parent_resolved is not None else None
            continuation_rows = table.metadata.get("cleaned_rows")
            if parent_resolved is not None and isinstance(parent_rows, list) and isinstance(continuation_rows, list):
                integrated_rows = [[str(cell) for cell in row] for row in parent_rows if isinstance(row, list)]
                dropped_parent_row_idx: int | None = None
                if parent_resolved.table.body_rows:
                    parent_last_body_row_idx = parent_resolved.table.body_rows[-1]
                    parent_last_body_row = (
                        parent_rows[parent_last_body_row_idx]
                        if parent_last_body_row_idx < len(parent_rows)
                        and isinstance(parent_rows[parent_last_body_row_idx], list)
                        else None
                    )
                    if (
                        isinstance(parent_last_body_row, list)
                        and parent_last_body_row
                        and CONTINUED_ROW_PATTERN.fullmatch(str(parent_last_body_row[0]).strip()) is not None
                        and all(not str(cell).strip() for cell in parent_last_body_row[1:])
                    ):
                        dropped_parent_row_idx = parent_last_body_row_idx
                        integrated_rows = [
                            row for row_idx, row in enumerate(integrated_rows) if row_idx != dropped_parent_row_idx
                        ]
                row_provenance = [
                    provenance.model_copy(
                        update={
                            "source_role": (
                                "base_fragment"
                                if provenance.source_table_index == parent_index
                                else provenance.source_role
                            )
                        }
                    )
                    for provenance in parent_resolved.row_provenance
                    if provenance.resolved_row_idx != dropped_parent_row_idx
                ]
                continuation_row_views_by_row_idx = {row_view.row_idx: row_view for row_view in table.row_views}
                appended_body_rows: list[int] = []
                for source_row_idx in table.body_rows:
                    if source_row_idx >= len(continuation_rows) or not isinstance(continuation_rows[source_row_idx], list):
                        continue
                    resolved_row_idx = len(integrated_rows)
                    integrated_row = [str(cell) for cell in continuation_rows[source_row_idx]]
                    integrated_rows.append(integrated_row)
                    appended_body_rows.append(resolved_row_idx)
                    row_provenance.append(
                        ResolvedRowProvenance(
                            resolved_row_idx=resolved_row_idx,
                            source_table_id=table.table_id,
                            source_table_index=source_index,
                            source_row_idx=source_row_idx,
                            source_page_num=source_page_num_by_row_idx.get(source_row_idx, source_page_num),
                            source_role="continuation_fragment",
                        )
                    )

                parent_dropped_rows = []
                if dropped_parent_row_idx is not None:
                    source_page_for_dropped_parent = next(
                        (
                            provenance.source_page_num
                            for provenance in parent_resolved.row_provenance
                            if provenance.resolved_row_idx == dropped_parent_row_idx
                        ),
                        None,
                    )
                    parent_dropped_rows.append(
                        DroppedSourceRow(
                            source_table_id=parent_resolved.table.table_id,
                            source_table_index=parent_index,
                            source_row_idx=dropped_parent_row_idx,
                            source_page_num=source_page_for_dropped_parent,
                            reason="base_trailing_empty_continued_row_dropped_after_schema_match",
                        )
                    )
                dropped_rows = [
                    DroppedSourceRow(
                        source_table_id=table.table_id,
                        source_table_index=source_index,
                        source_row_idx=row_idx,
                        source_page_num=source_page_num_by_row_idx.get(row_idx, source_page_num),
                        reason=(
                            "continuation_header_row_dropped_after_schema_match"
                            if row_idx in table.header_rows
                            else "continuation_non_body_row_dropped_after_schema_match"
                        ),
                    )
                    for row_idx in range(len(continuation_rows))
                    if row_idx not in set(table.body_rows)
                ]
                integration_boundary = IntegrationBoundary(
                    boundary_id=f"resolved_table_boundary_{parent_index}_{source_index}",
                    previous_source_table_id=parent_resolved.source_table_ids[-1],
                    next_source_table_id=table.table_id,
                    before_resolved_row_idx=len(integrated_rows) - len(appended_body_rows) - 1
                    if integrated_rows and appended_body_rows
                    else None,
                    after_resolved_row_idx=appended_body_rows[0] if appended_body_rows else None,
                    dropped_rows=[*parent_dropped_rows, *dropped_rows],
                    decision_id=decision_id,
                    notes=["parent_headers_carried_forward_after_schema_match"],
                )
                continuation_row_views = []
                for source_row_idx, resolved_row_idx in zip(table.body_rows, appended_body_rows, strict=False):
                    source_row_view = continuation_row_views_by_row_idx.get(source_row_idx)
                    if source_row_view is not None:
                        continuation_row_views.append(
                            source_row_view.model_copy(
                                update={
                                    "row_idx": resolved_row_idx,
                                    "raw_cells": integrated_rows[resolved_row_idx],
                                }
                            )
                        )

                integrated_source_table_ids = [*parent_resolved.source_table_ids, table.table_id]
                integrated_table_id = (
                    parent_resolved.table_id
                    if parent_resolved.resolution_type == "integrated_continuation"
                    else f"{parent_resolved.table_id}-resolved-continuation"
                )
                integrated_metadata = {
                    **parent_resolved.table.metadata,
                    "cleaned_rows": integrated_rows,
                    "resolved_table": {
                        "resolution_type": "integrated_continuation",
                        "source_table_ids": integrated_source_table_ids,
                        "column_schema_decision_id": column_schema_decision.decision_id,
                        "parent_headers_carried_forward": True,
                    },
                }
                integrated_table = parent_resolved.table.model_copy(
                    update={
                        "table_id": integrated_table_id,
                        "header_rows": list(parent_resolved.table.header_rows),
                        "body_rows": [
                            *[
                                row_idx
                                for row_idx in parent_resolved.table.body_rows
                                if row_idx != dropped_parent_row_idx
                            ],
                            *appended_body_rows,
                        ],
                        "row_views": [
                            *[
                                row_view
                                for row_view in parent_resolved.table.row_views
                                if row_view.row_idx != dropped_parent_row_idx
                            ],
                            *continuation_row_views,
                        ],
                        "n_rows": len(integrated_rows),
                        "n_cols": parent_resolved.table.n_cols,
                        "metadata": integrated_metadata,
                    }
                )
                resolved_tables[parent_resolved_index] = ResolvedTable(
                    table_id=integrated_table_id,
                    resolution_type="integrated_continuation",
                    logical_table_number=continuation_number,
                    title=parent_resolved.title,
                    caption=parent_resolved.caption,
                    table=integrated_table,
                    source_table_ids=integrated_source_table_ids,
                    row_provenance=row_provenance,
                    integration_boundaries=[*parent_resolved.integration_boundaries, integration_boundary],
                    column_schema_decisions=[*parent_resolved.column_schema_decisions, column_schema_decision],
                    confidence=0.95,
                    notes=[
                        *parent_resolved.notes,
                        f"integrated_continuation:{table.table_id}",
                        "parent_headers_carried_forward_after_schema_match",
                    ],
                )
                decisions.append(
                    TableResolutionDecision(
                        decision_id=decision_id,
                        decision_type="integrated_continuation",
                        status="accepted",
                        base_table_id=parent_id,
                        continuation_table_id=table.table_id,
                        resolved_table_id=integrated_table_id,
                        source_table_ids=integrated_source_table_ids,
                        identity_evidence=continuation_identity_evidence,
                        reason="continuation_integrated_after_schema_match",
                        diagnostics=[*parent_diagnostics, *column_schema_decision.diagnostics],
                        confidence=0.95,
                    )
                )
                if parent_index < len(source_tables):
                    parent_source_role = source_tables[parent_index].role
                    source_tables[parent_index] = source_tables[parent_index].model_copy(
                        update={
                            "role": (
                                "base_fragment"
                                if parent_source_role != "continuation_fragment"
                                else parent_source_role
                            ),
                            "resolved_table_id": integrated_table_id,
                            "consumed_by": integrated_table_id,
                            "decision_id": decision_id,
                            "notes": [
                                *source_tables[parent_index].notes,
                                f"integrated_with:{table.table_id}",
                                f"column_schema_decision:{column_schema_decision.decision_id}",
                                f"column_schema_status:{column_schema_decision.status}",
                            ],
                        }
                    )
                source_tables.append(
                    SourceTableResolution(
                        source_table_id=table.table_id,
                        source_table_index=source_index,
                        source_page_num=source_page_num,
                        role="continuation_fragment",
                        resolved_table_id=integrated_table_id,
                        consumed_by=integrated_table_id,
                        decision_id=decision_id,
                        notes=[
                            *continuation_identity_evidence,
                            *parent_diagnostics,
                            f"column_schema_decision:{column_schema_decision.decision_id}",
                            f"column_schema_status:{column_schema_decision.status}",
                        ],
                    )
                )
                source_to_resolved_index[source_index] = parent_resolved_index
                if continuation_number is not None:
                    latest_fragment_by_number[continuation_number] = source_index
                continue
            column_schema_decision = column_schema_decision.model_copy(
                update={
                    "status": "rejected",
                    "decision_reason": "schema_match_but_cleaned_rows_missing",
                    "diagnostics": [
                        *column_schema_decision.diagnostics,
                        "parent_or_continuation_cleaned_rows_missing",
                    ],
                    "confidence": 0.2,
                }
            )

        source_role = "rejected_continuation" if is_continuation_candidate else "singleton"
        row_provenance = [
            ResolvedRowProvenance(
                resolved_row_idx=row_idx,
                source_table_id=table.table_id,
                source_table_index=source_index,
                source_row_idx=row_idx,
                source_page_num=source_page_num_by_row_idx.get(row_idx, source_page_num),
                source_role=source_role,
            )
            for row_idx in range(table.n_rows)
        ]
        resolved_notes = ["singleton_source_table"]
        if is_continuation_candidate:
            continuation_label = (
                f"table_number={continuation_number}"
                if continuation_number is not None
                else "table_number=unknown_boundary_note"
            )
            resolved_notes.extend(
                [
                    f"continuation_identity_gate_passed:{continuation_label}",
                    (
                        f"parent_fragment_selected:{parent_id}"
                        if parent_id is not None
                        else "parent_fragment_not_selected"
                    ),
                    "integration_deferred_until_column_compatibility",
                ]
            )

        resolved_tables.append(
            ResolvedTable(
                table_id=table.table_id,
                resolution_type="singleton",
                logical_table_number=continuation_number if is_continuation_candidate else logical_table_number,
                title=table.title,
                caption=table.caption,
                table=table,
                source_table_ids=[table.table_id],
                row_provenance=row_provenance,
                column_schema_decisions=[column_schema_decision] if column_schema_decision is not None else [],
                confidence=1.0,
                notes=resolved_notes,
            )
        )
        if is_continuation_candidate:
            decisions.append(
                TableResolutionDecision(
                    decision_id=decision_id,
                    decision_type="rejected_continuation",
                    status="rejected",
                    base_table_id=parent_id,
                    continuation_table_id=table.table_id,
                    resolved_table_id=table.table_id,
                    source_table_ids=[parent_id, table.table_id] if parent_id is not None else [table.table_id],
                    identity_evidence=continuation_identity_evidence,
                    reason=(
                        "continuation_identity_detected_column_schema_rejected"
                        if column_schema_decision is not None
                        else "continuation_identity_detected_no_unambiguous_parent"
                        if parent_id is None
                        else "continuation_identity_detected_parent_selected_column_gate_pending"
                    ),
                    diagnostics=(
                        [
                            *parent_diagnostics,
                            *column_schema_decision.diagnostics,
                            "integration_rejected_by_column_schema_gate",
                        ]
                        if column_schema_decision is not None
                        else [*parent_diagnostics, "continuation_identity_detected_no_unambiguous_parent"]
                    ),
                    confidence=0.85,
                )
            )
            rejected_source_notes = [*continuation_identity_evidence, *parent_diagnostics]
            if column_schema_decision is not None:
                rejected_source_notes.extend(
                    [
                        f"column_schema_decision:{column_schema_decision.decision_id}",
                        f"column_schema_status:{column_schema_decision.status}",
                        *column_schema_decision.diagnostics,
                    ]
                )
            source_tables.append(
                SourceTableResolution(
                    source_table_id=table.table_id,
                    source_table_index=source_index,
                    source_page_num=source_page_num,
                    role="rejected_continuation",
                    resolved_table_id=table.table_id,
                    decision_id=decision_id,
                    notes=rejected_source_notes,
                )
            )
        else:
            decisions.append(
                TableResolutionDecision(
                    decision_id=decision_id,
                    decision_type="singleton",
                    status="accepted",
                    resolved_table_id=table.table_id,
                    source_table_ids=[table.table_id],
                    reason="source_table_passed_through_as_singleton",
                    confidence=1.0,
                )
            )
            source_tables.append(
                SourceTableResolution(
                    source_table_id=table.table_id,
                    source_table_index=source_index,
                    source_page_num=source_page_num,
                    role="singleton",
                    resolved_table_id=table.table_id,
                    decision_id=decision_id,
                )
            )
            source_to_resolved_index[source_index] = len(resolved_tables) - 1

        if is_continuation_candidate and continuation_number is not None:
            latest_fragment_by_number[continuation_number] = source_index
        else:
            parent_number = logical_table_number or trailing_continuation_number
            if parent_number is not None:
                latest_fragment_by_number[parent_number] = source_index
                parent_indices_by_number.setdefault(parent_number, []).append(source_index)

    return ResolvedTableSet(
        resolved_tables=resolved_tables,
        decisions=decisions,
        source_tables=source_tables,
    )
