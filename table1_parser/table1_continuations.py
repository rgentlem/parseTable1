"""Artifact-only grouping and merging for Table 1 continuations."""

from __future__ import annotations

import re

from table1_parser.column_header_schema import column_header_labels
from table1_parser.schemas import ColumnHeaderSchema, NormalizedTable, RowView, Table1ContinuationGroup, Table1ContinuationMember


TABLE_1_CAPTION_PATTERN = re.compile(r"\btable\s*1\b", re.IGNORECASE)
CONTINUATION_PATTERN = re.compile(r"\bcont(?:inued)?\.?\b|\(\s*continued\s*\)", re.IGNORECASE)
MARKUP_PATTERN = re.compile(r"[*_`]+")
SPACE_PATTERN = re.compile(r"\s+")


def build_table1_continuation_artifacts(
    normalized_tables: list[NormalizedTable],
    column_header_schemas: list[ColumnHeaderSchema] | None = None,
) -> tuple[list[Table1ContinuationGroup], list[NormalizedTable]]:
    """Build Table 1 continuation decision records and merged normalized-table artifacts."""
    groups: list[Table1ContinuationGroup] = []
    merged_tables: list[NormalizedTable] = []
    consumed_continuation_indices: set[int] = set()

    for table_index, table in enumerate(normalized_tables):
        if table_index in consumed_continuation_indices:
            continue
        base_index = _previous_table1_index(normalized_tables, table_index)
        prior_page = normalized_tables[base_index].metadata.get("source_page_num") if base_index is not None else None
        page = table.metadata.get("source_page_num")
        rows = table.metadata.get("cleaned_rows")
        inferred_continuation = (
            base_index is not None
            and not _is_table_1(table)
            and not _is_explicit_continuation(table)
            and not table.title
            and not table.caption
            and table.metadata.get("table_number") is None
            and not (isinstance(prior_page, int) and isinstance(page, int) and page != prior_page + 1)
            and isinstance(rows, list)
            and bool(table.body_rows)
            and table.n_cols >= 2
        )
        if not ((_is_table_1(table) and _is_explicit_continuation(table)) or inferred_continuation):
            continue

        if base_index is None:
            groups.append(
                _build_group(
                    group_id=f"table1_continuation_{len(groups)}",
                    normalized_tables=normalized_tables,
                    source_indices=[table_index],
                    merge_decision="skip",
                    decision_reason="no_prior_table1_fragment",
                    confidence=0.0,
                    column_headers=[],
                    diagnostics=[
                        "Continuation signal found but no prior Table 1 fragment was available.",
                        "column_header_schema_required_for_column_comparison",
                    ],
                )
            )
            continue

        source_indices = [base_index, table_index]
        next_index = table_index + 1
        while next_index < len(normalized_tables):
            next_table = normalized_tables[next_index]
            if _is_table_1(next_table) and _is_explicit_continuation(next_table):
                source_indices.append(next_index)
                consumed_continuation_indices.add(next_index)
                next_index += 1
                continue
            break

        base_headers = _column_headers(normalized_tables[base_index], column_header_schemas, base_index)
        diagnostics: list[str] = []
        if not base_headers:
            diagnostics.append(f"column_header_schema_missing_or_empty:table_index={base_index}")
        headers_match = bool(base_headers)
        for source_index in source_indices[1:]:
            continuation_headers = _column_headers(normalized_tables[source_index], column_header_schemas, source_index)
            if not continuation_headers:
                diagnostics.append(f"column_header_schema_missing_or_empty:table_index={source_index}")
            if continuation_headers != base_headers:
                headers_match = False
                diagnostics.append(
                    "column_header_mismatch:"
                    f"table_index={source_index}:"
                    f"expected={base_headers}:observed={continuation_headers}"
                )

        group_id = f"table1_continuation_{len(groups)}"
        if headers_match:
            reason = (
                "uncaptioned_table1_continuation_candidate_and_matching_columns"
                if inferred_continuation
                else "explicit_table1_continuation_and_matching_columns"
            )
            groups.append(
                _build_group(
                    group_id=group_id,
                    normalized_tables=normalized_tables,
                    source_indices=source_indices,
                    merge_decision="merge",
                    decision_reason=reason,
                    confidence=0.82 if inferred_continuation else 0.98,
                    column_headers=base_headers,
                    diagnostics=diagnostics,
                )
            )
            merged_tables.append(_merge_table1_group(group_id, normalized_tables, source_indices, base_headers))
            consumed_continuation_indices.update(source_indices[1:])
        else:
            reason = (
                "uncaptioned_table1_continuation_candidate_but_incompatible_columns"
                if inferred_continuation
                else "explicit_table1_continuation_but_incompatible_columns"
            )
            groups.append(
                _build_group(
                    group_id=group_id,
                    normalized_tables=normalized_tables,
                    source_indices=source_indices,
                    merge_decision="skip",
                    decision_reason=reason,
                    confidence=0.3 if inferred_continuation else 0.35,
                    column_headers=base_headers,
                    diagnostics=diagnostics,
                )
            )
            consumed_continuation_indices.update(source_indices[1:])

    return groups, merged_tables


def table1_continuation_groups_to_payload(groups: list[Table1ContinuationGroup]) -> list[dict[str, object]]:
    """Serialize Table 1 continuation groups as JSON-friendly records."""
    return [group.model_dump(mode="json") for group in groups]


def _is_table_1(table: NormalizedTable) -> bool:
    metadata_number = table.metadata.get("table_number")
    if metadata_number == 1:
        return True
    text = " ".join(part for part in [table.title, table.caption] if part)
    return bool(TABLE_1_CAPTION_PATTERN.search(text))


def _is_explicit_continuation(table: NormalizedTable) -> bool:
    if table.metadata.get("is_continuation") is True:
        return True
    text = " ".join(part for part in [table.title, table.caption] if part)
    if CONTINUATION_PATTERN.search(text):
        return True
    rows = table.metadata.get("cleaned_rows")
    if isinstance(rows, list) and rows:
        first_row_text = " ".join(str(cell) for cell in rows[0] if cell)
        return bool(CONTINUATION_PATTERN.search(first_row_text))
    return False


def _previous_table1_index(tables: list[NormalizedTable], table_index: int) -> int | None:
    for prior_index in range(table_index - 1, -1, -1):
        prior_table = tables[prior_index]
        prior_number = prior_table.metadata.get("table_number")
        if isinstance(prior_number, int) and prior_number != 1:
            return None
        if _is_table_1(prior_table):
            return prior_index
    return None


def _column_headers(
    table: NormalizedTable,
    column_header_schemas: list[ColumnHeaderSchema] | None = None,
    table_index: int | None = None,
) -> list[str]:
    if column_header_schemas is None or table_index is None or table_index >= len(column_header_schemas):
        return []
    schema = column_header_schemas[table_index]
    if schema.table_id != table.table_id or not schema.leaves:
        return []
    return [_normalize_header_cell(item) for item in column_header_labels(schema)]


def _normalize_header_cell(text: str) -> str:
    normalized = MARKUP_PATTERN.sub("", text)
    normalized = normalized.replace("\u00a0", " ").replace("\u2009", " ").replace("\u202f", " ")
    normalized = SPACE_PATTERN.sub(" ", normalized).strip().lower()
    normalized = normalized.strip(" .,:;")
    return SPACE_PATTERN.sub(" ", normalized).strip()


def _build_group(
    *,
    group_id: str,
    normalized_tables: list[NormalizedTable],
    source_indices: list[int],
    merge_decision: str,
    decision_reason: str,
    confidence: float,
    column_headers: list[str],
    diagnostics: list[str],
) -> Table1ContinuationGroup:
    members = []
    for member_position, source_index in enumerate(source_indices):
        table = normalized_tables[source_index]
        members.append(
            Table1ContinuationMember(
                table_index=source_index,
                table_id=table.table_id,
                role="base" if member_position == 0 else "continuation",
                title=table.title,
                caption=table.caption,
                n_rows=table.n_rows,
                n_cols=table.n_cols,
                header_rows=table.header_rows,
                body_rows=table.body_rows,
            )
        )
    return Table1ContinuationGroup(
        group_id=group_id,
        source_table_indices=source_indices,
        source_table_ids=[normalized_tables[index].table_id for index in source_indices],
        merge_decision=merge_decision,
        decision_reason=decision_reason,
        confidence=confidence,
        column_headers_match=merge_decision == "merge",
        column_headers=column_headers,
        diagnostics=diagnostics,
        members=members,
    )


def _merge_table1_group(
    group_id: str,
    normalized_tables: list[NormalizedTable],
    source_indices: list[int],
    column_headers: list[str],
) -> NormalizedTable:
    base_table = normalized_tables[source_indices[0]]
    merged_rows: list[list[str]] = []
    row_provenance: list[dict[str, object]] = []
    row_views_by_source: dict[tuple[int, int], RowView] = {}

    for source_index in source_indices:
        for row_view in normalized_tables[source_index].row_views:
            row_views_by_source[(source_index, row_view.row_idx)] = row_view

    for source_position, source_index in enumerate(source_indices):
        table = normalized_tables[source_index]
        rows = table.metadata.get("cleaned_rows")
        if not isinstance(rows, list):
            continue
        source_row_indices = list(range(len(rows))) if source_position == 0 else list(table.body_rows)
        for source_row_idx in source_row_indices:
            if source_row_idx >= len(rows) or not isinstance(rows[source_row_idx], list):
                continue
            merged_row_idx = len(merged_rows)
            merged_row = [str(cell) for cell in rows[source_row_idx]]
            merged_rows.append(merged_row)
            row_provenance.append(
                {
                    "merged_row_idx": merged_row_idx,
                    "source_table_index": source_index,
                    "source_table_id": table.table_id,
                    "source_row_idx": source_row_idx,
                    "source_page_num": table.metadata.get("source_page_num"),
                    "source_role": "header" if source_row_idx in table.header_rows else "body",
                }
            )

    merged_row_views: list[RowView] = []
    for provenance in row_provenance:
        if provenance["source_role"] != "body":
            continue
        source_index = int(provenance["source_table_index"])
        source_row_idx = int(provenance["source_row_idx"])
        source_view = row_views_by_source.get((source_index, source_row_idx))
        if source_view is None:
            continue
        merged_row_idx = int(provenance["merged_row_idx"])
        merged_row_views.append(
            source_view.model_copy(
                update={
                    "row_idx": merged_row_idx,
                    "raw_cells": merged_rows[merged_row_idx],
                }
            )
        )

    merged_header_rows = list(base_table.header_rows)
    merged_body_rows = [
        int(provenance["merged_row_idx"])
        for provenance in row_provenance
        if provenance["source_role"] == "body"
    ]
    merged_metadata = {
        **base_table.metadata,
        "cleaned_rows": merged_rows,
        "table1_continuation_merge": {
            "group_id": group_id,
            "source_table_indices": source_indices,
            "source_table_ids": [normalized_tables[index].table_id for index in source_indices],
            "column_headers": column_headers,
            "row_provenance": row_provenance,
            "artifact_only": True,
        },
    }
    return base_table.model_copy(
        update={
            "table_id": f"{base_table.table_id}-merged-table1",
            "title": base_table.title,
            "caption": base_table.caption,
            "header_rows": merged_header_rows,
            "body_rows": merged_body_rows,
            "row_views": merged_row_views,
            "n_rows": len(merged_rows),
            "n_cols": max((len(row) for row in merged_rows), default=base_table.n_cols),
            "metadata": merged_metadata,
        }
    )
