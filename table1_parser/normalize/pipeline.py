"""Pipeline helper for converting extracted tables into normalized tables."""

from __future__ import annotations

import re

from table1_parser.normalize.header_detector import (
    compare_header_body_split_rules,
    detect_header_rows_with_metadata,
)
from table1_parser.normalize.row_signature import build_row_signature
from table1_parser.schemas import ExtractedTable, NormalizedTable
from table1_parser.schemas.table_region import TableRegion
from table1_parser.text_cleaning import clean_text, summarize_text_cleaning_provenance


ALPHA_PATTERN = re.compile(r"[A-Za-z]")
ALNUM_PATTERN = re.compile(r"[A-Za-z0-9]")
NA_LIKE_VALUE_PATTERN = re.compile(r"^(?:N/?A|NR|not reported)$", re.IGNORECASE)


def _is_noninformative_cell(value: str) -> bool:
    """Return whether a cell is empty or too weak to act as a reliable row label."""
    cleaned = clean_text(value)
    if not cleaned:
        return True
    if not ALNUM_PATTERN.search(cleaned):
        return True
    return len(cleaned) <= 2 and not ALPHA_PATTERN.search(cleaned)


def _looks_like_label_cell(value: str) -> bool:
    """Return whether a cell resembles a meaningful row-label cell."""
    cleaned = clean_text(value)
    if NA_LIKE_VALUE_PATTERN.fullmatch(cleaned):
        return False
    return bool(cleaned) and bool(ALPHA_PATTERN.search(cleaned)) and len(cleaned) >= 2


def _region_header_body_rows(
    table_region: TableRegion | None,
    cleaned_rows: list[list[str]],
) -> tuple[list[int], list[int], dict[str, object]] | None:
    """Return region-owned header/body rows when available."""
    if table_region is None:
        return None
    header_rows = [
        row_idx
        for row_idx in table_region.column_header_rows
        if isinstance(row_idx, int) and 0 <= row_idx < len(cleaned_rows)
    ]
    body_rows = [
        row_idx
        for row_idx in table_region.body_rows
        if isinstance(row_idx, int) and 0 <= row_idx < len(cleaned_rows)
    ]
    fail_closed = (
        table_region.detection_basis
        == "table_region_fail_closed_insufficient_geometry"
    )
    if not header_rows and not body_rows and not fail_closed:
        return None
    return header_rows, body_rows, {
        "source": "table_region_fail_closed" if fail_closed else "table_region",
        "table_region_id": table_region.region_id,
        "table_region_detection_basis": table_region.detection_basis,
        "table_region_confidence": table_region.confidence,
        "caption_rows": list(table_region.caption_rows),
        "preamble_rows": list(table_region.preamble_rows),
        "footer_note_rows": list(table_region.footer_note_rows),
        "diagnostics": list(table_region.diagnostics),
    }


def _detect_or_apply_region_header_rows(
    cleaned_rows: list[list[str]],
    *,
    table_region: TableRegion | None,
    row_bounds: list[tuple[float, float]] | None,
    horizontal_rules: list[float] | None,
    separator_horizontal_rules: list[float] | None,
) -> tuple[list[int], list[int], dict[str, object]]:
    region_rows = _region_header_body_rows(table_region, cleaned_rows)
    if region_rows is not None:
        return region_rows
    return detect_header_rows_with_metadata(
        cleaned_rows,
        row_bounds=row_bounds,
        horizontal_rules=horizontal_rules,
        separator_horizontal_rules=separator_horizontal_rules,
    )


def normalize_extracted_table(
    table: ExtractedTable,
    table_region: TableRegion | None = None,
) -> NormalizedTable:
    """Convert a raw extracted table into the normalized intermediate schema."""
    raw_rows = [["" for _ in range(table.n_cols)] for _ in range(table.n_rows)]
    for cell in table.cells:
        if cell.row_idx < table.n_rows and cell.col_idx < table.n_cols:
            raw_rows[cell.row_idx][cell.col_idx] = cell.text
    if not raw_rows:
        dropped_leading_cols = 0
        dropped_trailing_cols = 0
    else:
        if raw_rows[0] and len(raw_rows[0]) >= 2:
            first_column = [row[0] for row in raw_rows]
            second_column = [row[1] for row in raw_rows]
            first_noninformative = sum(_is_noninformative_cell(value) for value in first_column)
            first_meaningful = sum(_looks_like_label_cell(value) for value in first_column)
            second_label_like = sum(_looks_like_label_cell(value) for value in second_column)
            row_count = len(raw_rows)
            dropped_leading_cols = int(
                first_noninformative / row_count >= 0.85
                and first_meaningful <= max(1, row_count // 10)
                and second_label_like >= max(3, row_count // 3)
            )
        else:
            dropped_leading_cols = 0
        rows_after_leading = [row[dropped_leading_cols:] for row in raw_rows]
        if rows_after_leading and rows_after_leading[0] and len(rows_after_leading[0]) >= 2:
            last_column = [row[-1] for row in rows_after_leading]
            previous_column = [row[-2] for row in rows_after_leading]
            last_noninformative = sum(_is_noninformative_cell(value) for value in last_column)
            previous_informative = sum(not _is_noninformative_cell(value) for value in previous_column)
            row_count = len(rows_after_leading)
            dropped_trailing_cols = int(
                last_noninformative / row_count >= 0.9
                and previous_informative >= max(2, row_count // 4)
            )
        else:
            dropped_trailing_cols = 0
        raw_rows = [row[:-dropped_trailing_cols] for row in rows_after_leading] if dropped_trailing_cols else rows_after_leading
    source_col_indices: list[int | None] = list(range(dropped_leading_cols, table.n_cols - dropped_trailing_cols))
    cleaned_rows = [[clean_text(cell) for cell in row] for row in raw_rows]
    raw_bounds = table.metadata.get("row_bounds")
    if isinstance(raw_bounds, list) and len(raw_bounds) == table.n_rows:
        row_bounds: list[tuple[float, float]] | None = []
        for item in raw_bounds:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                row_bounds = None
                break
            row_bounds.append((float(item[0]), float(item[1])))
    else:
        row_bounds = None
    raw_rules = table.metadata.get("horizontal_rules")
    horizontal_rules = [float(value) for value in raw_rules] if isinstance(raw_rules, list) else None
    raw_separator_rules = table.metadata.get("full_width_horizontal_rules")
    separator_horizontal_rules = (
        [float(value) for value in raw_separator_rules]
        if isinstance(raw_separator_rules, list)
        else None
    )
    header_row_bounds = row_bounds
    header_horizontal_rules = horizontal_rules
    header_separator_rules = separator_horizontal_rules
    header_rows, body_rows, header_detection = _detect_or_apply_region_header_rows(
        cleaned_rows,
        table_region=table_region,
        row_bounds=header_row_bounds,
        horizontal_rules=header_horizontal_rules,
        separator_horizontal_rules=header_separator_rules,
    )
    first_column_bboxes: dict[int, tuple[float, float, float, float]] = {}
    x0_values: list[float] = []
    first_column_text_x0_by_row: dict[int, float] = {}
    raw_text_x0_by_row = table.metadata.get("first_column_text_x0_by_row")
    if dropped_leading_cols == 0 and isinstance(raw_text_x0_by_row, dict):
        for row_idx_key, value in raw_text_x0_by_row.items():
            try:
                first_column_text_x0_by_row[int(row_idx_key)] = float(value)
            except (TypeError, ValueError):
                continue
    for cell in table.cells:
        if cell.col_idx != dropped_leading_cols or cell.bbox is None or cell.row_idx >= table.n_rows:
            continue
        first_column_bboxes[cell.row_idx] = cell.bbox
        x0_values.append(cell.bbox[0])
    base_x0 = min(x0_values) if x0_values else None
    body_text_x0_values = [
        first_column_text_x0_by_row[row_idx]
        for row_idx in body_rows
        if row_idx in first_column_text_x0_by_row
    ]
    base_text_x0 = min(body_text_x0_values) if body_text_x0_values else None
    row_views = [
        build_row_signature(
            row_idx,
            raw_rows[row_idx],
            first_cell_bbox=first_column_bboxes.get(row_idx),
            base_x0=base_x0,
            first_cell_text_x0=first_column_text_x0_by_row.get(row_idx),
            base_text_x0=base_text_x0,
        )
        for row_idx in body_rows
    ]
    indent_levels = [row_view.indent_level for row_view in row_views if row_view.indent_level is not None]
    if len(indent_levels) < 3:
        indentation_informative = False
    else:
        baseline = min(indent_levels)
        meaningful_offsets = [level - baseline for level in indent_levels if level - baseline >= 2]
        indentation_informative = len(meaningful_offsets) >= 2 and len(set(indent_levels)) >= 2
    text_cleaning_provenance = summarize_text_cleaning_provenance(raw_rows)
    header_body_split_rule_comparison = compare_header_body_split_rules(
        cleaned_rows,
        row_bounds=header_row_bounds,
        horizontal_rules=header_horizontal_rules,
        separator_horizontal_rules=header_separator_rules,
        selected_header_rows=header_rows,
        selected_body_rows=body_rows,
    )

    metadata = {
        **table.metadata,
        "source_page_num": table.page_num,
        "extraction_backend": table.extraction_backend,
        "cleaned_rows": cleaned_rows,
        "dropped_leading_cols": dropped_leading_cols,
        "dropped_trailing_cols": dropped_trailing_cols,
        "source_col_indices": source_col_indices,
        "column_repairs": {},
        "header_detection": header_detection,
        "header_body_split_rule_comparison": header_body_split_rule_comparison,
        "indentation_informative": indentation_informative,
        "text_cleaning_provenance": text_cleaning_provenance,
    }
    return NormalizedTable(
        table_id=table.table_id,
        title=table.title,
        caption=table.caption,
        header_rows=header_rows,
        body_rows=body_rows,
        row_views=row_views,
        n_rows=table.n_rows,
        n_cols=len(raw_rows[0]) if raw_rows else 0,
        metadata=metadata,
    )


def normalize_extracted_tables(
    tables: list[ExtractedTable],
    table_regions: list[TableRegion] | None = None,
) -> list[NormalizedTable]:
    """Normalize a list of extracted tables while preserving input order."""
    region_by_table_id = {region.table_id: region for region in table_regions or []}
    return [
        normalize_extracted_table(table, table_region=region_by_table_id.get(table.table_id))
        for table in tables
    ]
