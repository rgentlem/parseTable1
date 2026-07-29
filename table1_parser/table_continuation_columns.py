"""Column compatibility checks for explicitly identified table continuations."""

from __future__ import annotations

import re

from table1_parser.column_header_schema import column_header_comparison_labels
from table1_parser.extract.table_detector import TABLE_IDENTIFIER_PATTERN
from table1_parser.schemas import ColumnHeaderSchema, ExtractedTable, NormalizedTable, TableProfile
from table1_parser.schemas.table_continuation_column_check import TableContinuationColumnCheck


TABLE_NUMBER_PATTERN = re.compile(
    rf"\btable\s*(?P<table_number>{TABLE_IDENTIFIER_PATTERN.pattern})\b",
    re.IGNORECASE,
)
CONTINUATION_PATTERN = re.compile(r"\bcont(?:inued)?\.?\b|\(\s*continued\s*\)", re.IGNORECASE)


def build_table_continuation_column_checks(
    normalized_tables: list[NormalizedTable],
    extracted_tables: list[ExtractedTable] | None = None,
    table_profiles: list[TableProfile] | None = None,
    table_categories: list[str | None] | None = None,
    column_header_schemas: list[ColumnHeaderSchema] | None = None,
) -> list[TableContinuationColumnCheck]:
    """Build column-compatibility diagnostics for demographic-table continuations."""
    checks: list[TableContinuationColumnCheck] = []
    latest_fragment_by_number: dict[str, int] = {}

    for table_index, table in enumerate(normalized_tables):
        continuation_number = _clear_continuation_table_number(table)
        if continuation_number is None:
            continuation_number = _inferred_uncaptioned_continuation_number(
                normalized_tables,
                table_profiles,
                table_categories,
                latest_fragment_by_number,
                table_index,
            )
        if continuation_number is None:
            table_number = _table_number(table)
            if table_number is not None:
                latest_fragment_by_number[table_number] = table_index
            continue

        base_index = latest_fragment_by_number.get(continuation_number)
        if base_index is None:
            for prior_index in range(table_index - 1, -1, -1):
                if _table_number(normalized_tables[prior_index]) == continuation_number:
                    base_index = prior_index
                    break

        if not _continuation_pair_is_demographic(
            table_profiles,
            table_categories,
            base_index,
            table_index,
        ):
            latest_fragment_by_number[continuation_number] = table_index
            continue

        checks.append(
            _build_column_check(
                check_id=f"table_continuation_column_check_{len(checks)}",
                table_number=continuation_number,
                normalized_tables=normalized_tables,
                table_profiles=table_profiles,
                table_categories=table_categories,
                column_header_schemas=column_header_schemas,
                base_index=base_index,
                continuation_index=table_index,
            )
        )
        latest_fragment_by_number[continuation_number] = table_index

    return checks


def table_continuation_column_checks_to_payload(
    checks: list[TableContinuationColumnCheck],
) -> list[dict[str, object]]:
    """Serialize continuation column checks as JSON-friendly records."""
    return [check.model_dump(mode="json") for check in checks]


def _build_column_check(
    *,
    check_id: str,
    table_number: str,
    normalized_tables: list[NormalizedTable],
    table_profiles: list[TableProfile] | None,
    table_categories: list[str | None] | None,
    column_header_schemas: list[ColumnHeaderSchema] | None,
    base_index: int | None,
    continuation_index: int,
) -> TableContinuationColumnCheck:
    continuation_table = normalized_tables[continuation_index]

    if base_index is None:
        return TableContinuationColumnCheck(
            check_id=check_id,
            table_number=table_number,
            continuation_table_index=continuation_index,
            continuation_table_id=continuation_table.table_id,
            continuation_page_num=_source_page_num(continuation_table),
            continuation_n_cols=continuation_table.n_cols,
            continuation_table_family=_table_family_at(table_profiles, continuation_index),
            continuation_table_category=_table_category_at(table_categories, continuation_index),
            column_header_status="missing_base",
            continuation_column_headers=_column_headers(
                continuation_table,
                _column_schema_at(column_header_schemas, continuation_index),
            ),
            overall_status="no_parent",
            confidence=0.0,
            diagnostics=["explicit_continuation_has_no_prior_fragment_for_table_number"],
        )

    base_table = normalized_tables[base_index]
    base_headers = _column_headers(base_table, _column_schema_at(column_header_schemas, base_index))
    continuation_headers = _column_headers(
        continuation_table,
        _column_schema_at(column_header_schemas, continuation_index),
    )
    column_header_status = _column_header_status(base_headers, continuation_headers)
    normalized_column_count_match = base_table.n_cols == continuation_table.n_cols
    diagnostics: list[str] = []

    if not normalized_column_count_match:
        diagnostics.append(
            f"normalized_column_count_mismatch:base={base_table.n_cols}:continuation={continuation_table.n_cols}"
        )
    if column_header_status == "mismatch":
        diagnostics.append(
            f"column_header_mismatch:base={base_headers}:continuation={continuation_headers}"
        )
    if column_header_status in {"missing_base", "missing_both"}:
        diagnostics.append(f"column_header_schema_missing_or_empty:table_index={base_index}")
    if column_header_status in {"missing_continuation", "missing_both"}:
        diagnostics.append(f"column_header_schema_missing_or_empty:table_index={continuation_index}")

    overall_status = "incompatible"
    confidence = 0.2
    if column_header_status != "match":
        pass
    elif normalized_column_count_match:
        overall_status = "compatible"
        confidence = 0.95

    return TableContinuationColumnCheck(
        check_id=check_id,
        table_number=table_number,
        base_table_index=base_index,
        continuation_table_index=continuation_index,
        base_table_id=base_table.table_id,
        continuation_table_id=continuation_table.table_id,
        base_page_num=_source_page_num(base_table),
        continuation_page_num=_source_page_num(continuation_table),
        base_n_cols=base_table.n_cols,
        continuation_n_cols=continuation_table.n_cols,
        base_table_family=_table_family_at(table_profiles, base_index),
        continuation_table_family=_table_family_at(table_profiles, continuation_index),
        base_table_category=_table_category_at(table_categories, base_index),
        continuation_table_category=_table_category_at(table_categories, continuation_index),
        normalized_column_count_match=normalized_column_count_match,
        column_header_status=column_header_status,
        base_column_headers=base_headers,
        continuation_column_headers=continuation_headers,
        overall_status=overall_status,
        confidence=confidence,
        diagnostics=diagnostics,
    )


def _continuation_pair_is_demographic(
    table_profiles: list[TableProfile] | None,
    table_categories: list[str | None] | None,
    base_index: int | None,
    continuation_index: int,
) -> bool:
    if table_categories is not None:
        return _table_category_at(table_categories, base_index) == "demographic_description" or (
            _table_category_at(table_categories, continuation_index) == "demographic_description"
        )
    if table_profiles is None:
        return True
    return _table_family_at(table_profiles, base_index) == "descriptive_characteristics" or (
        _table_family_at(table_profiles, continuation_index) == "descriptive_characteristics"
    )


def _table_family_at(table_profiles: list[TableProfile] | None, table_index: int | None) -> str | None:
    if table_profiles is None or table_index is None or table_index >= len(table_profiles):
        return None
    return table_profiles[table_index].table_family


def _table_category_at(table_categories: list[str | None] | None, table_index: int | None) -> str | None:
    if table_categories is None or table_index is None or table_index >= len(table_categories):
        return None
    return table_categories[table_index]


def _clear_continuation_table_number(table: NormalizedTable) -> str | None:
    metadata_number = table.metadata.get("continuation_of_table_number")
    if (
        isinstance(metadata_number, str)
        and TABLE_IDENTIFIER_PATTERN.fullmatch(metadata_number) is not None
    ):
        if table.metadata.get("is_continuation") is True or _has_continuation_text(table):
            return metadata_number

    text = " ".join(part for part in [table.title, table.caption] if part)
    if not CONTINUATION_PATTERN.search(text):
        rows = table.metadata.get("cleaned_rows")
        if isinstance(rows, list) and rows:
            first_row_text = " ".join(str(cell) for cell in rows[0] if cell)
            if not CONTINUATION_PATTERN.search(first_row_text):
                return None
        else:
            return None

    match = TABLE_NUMBER_PATTERN.search(text)
    if match is not None:
        return match.group("table_number")
    table_number = _table_number(table)
    return table_number if table_number is not None else None


def _has_continuation_text(table: NormalizedTable) -> bool:
    text = " ".join(part for part in [table.title, table.caption] if part)
    if CONTINUATION_PATTERN.search(text):
        return True
    rows = table.metadata.get("cleaned_rows")
    if isinstance(rows, list) and rows:
        first_row_text = " ".join(str(cell) for cell in rows[0] if cell)
        return bool(CONTINUATION_PATTERN.search(first_row_text))
    return False


def _inferred_uncaptioned_continuation_number(
    normalized_tables: list[NormalizedTable],
    table_profiles: list[TableProfile] | None,
    table_categories: list[str | None] | None,
    latest_fragment_by_number: dict[str, int],
    table_index: int,
) -> str | None:
    table = normalized_tables[table_index]
    if _table_number(table) is not None or _has_continuation_text(table) or table.title or table.caption:
        return None
    rows = table.metadata.get("cleaned_rows")
    if not isinstance(rows, list) or not table.body_rows or table.n_cols < 2:
        return None
    prior_items = sorted(latest_fragment_by_number.items(), key=lambda item: item[1], reverse=True)
    for table_number, prior_index in prior_items:
        if prior_index >= table_index:
            continue
        prior_page = _source_page_num(normalized_tables[prior_index])
        page = _source_page_num(table)
        if prior_page is not None and page is not None and page != prior_page + 1:
            continue
        if _continuation_pair_is_demographic(table_profiles, table_categories, prior_index, table_index):
            return table_number
    return None


def _table_number(table: NormalizedTable) -> str | None:
    metadata_number = table.metadata.get("table_number")
    if (
        isinstance(metadata_number, str)
        and TABLE_IDENTIFIER_PATTERN.fullmatch(metadata_number) is not None
    ):
        return metadata_number
    text = " ".join(part for part in [table.title, table.caption] if part)
    match = TABLE_NUMBER_PATTERN.search(text)
    return match.group("table_number") if match is not None else None


def _source_page_num(table: NormalizedTable) -> int | None:
    value = table.metadata.get("source_page_num")
    return value if isinstance(value, int) and value >= 1 else None


def _column_schema_at(
    column_header_schemas: list[ColumnHeaderSchema] | None,
    table_index: int | None,
) -> ColumnHeaderSchema | None:
    if column_header_schemas is None or table_index is None or table_index >= len(column_header_schemas):
        return None
    return column_header_schemas[table_index]


def _column_headers(
    table: NormalizedTable,
    column_schema: ColumnHeaderSchema | None = None,
) -> list[str]:
    if column_schema is not None and column_schema.table_id == table.table_id:
        return column_header_comparison_labels(column_schema)
    return []


def _column_header_status(base_headers: list[str], continuation_headers: list[str]) -> str:
    if not base_headers and not continuation_headers:
        return "missing_both"
    if not base_headers:
        return "missing_base"
    if not continuation_headers:
        return "missing_continuation"
    return "match" if base_headers == continuation_headers else "mismatch"
