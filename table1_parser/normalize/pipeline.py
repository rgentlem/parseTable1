"""Pipeline helper for converting extracted tables into normalized tables."""

from __future__ import annotations

from table1_parser.normalize.header_detector import compare_header_body_split_rules
from table1_parser.normalize.row_signature import build_row_signature
from table1_parser.schemas import ExtractedTable, NormalizedTable
from table1_parser.schemas.table_region import TableRegion
from table1_parser.text_cleaning import clean_text, summarize_text_cleaning_provenance


def normalize_extracted_table(
    table: ExtractedTable,
    table_region: TableRegion,
) -> NormalizedTable:
    """Convert a raw extracted table into the normalized intermediate schema."""
    raw_rows = [["" for _ in range(table.n_cols)] for _ in range(table.n_rows)]
    for cell in table.cells:
        if cell.row_idx < table.n_rows and cell.col_idx < table.n_cols:
            raw_rows[cell.row_idx][cell.col_idx] = cell.text
    source_col_indices: list[int | None] = list(range(table.n_cols))
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
    horizontal_rules = (
        [float(value) for value in raw_rules] if isinstance(raw_rules, list) else None
    )
    raw_separator_rules = table.metadata.get("full_width_horizontal_rules")
    separator_horizontal_rules = (
        [float(value) for value in raw_separator_rules]
        if isinstance(raw_separator_rules, list)
        else None
    )
    header_row_bounds = row_bounds
    header_horizontal_rules = horizontal_rules
    header_separator_rules = separator_horizontal_rules
    header_rows = list(table_region.column_header_rows)
    body_rows = list(table_region.body_rows)
    invalid_region_rows = [
        row_idx
        for row_idx in [*header_rows, *body_rows]
        if row_idx < 0 or row_idx >= table.n_rows
    ]
    if invalid_region_rows:
        raise ValueError(
            f"TableRegion {table_region.region_id} references rows outside "
            f"ExtractedTable {table.table_id}: {invalid_region_rows}"
        )
    fail_closed = (
        table_region.detection_basis == "table_region_fail_closed_insufficient_geometry"
    )
    header_detection: dict[str, object] = {
        "source": "table_region_fail_closed" if fail_closed else "table_region",
        "table_region_id": table_region.region_id,
        "table_region_detection_basis": table_region.detection_basis,
        "table_region_confidence": table_region.confidence,
        "caption_rows": list(table_region.caption_rows),
        "preamble_rows": list(table_region.preamble_rows),
        "footer_note_rows": list(table_region.footer_note_rows),
        "diagnostics": list(table_region.diagnostics),
    }
    first_column_bboxes: dict[int, tuple[float, float, float, float]] = {}
    x0_values: list[float] = []
    first_column_text_x0_by_row: dict[int, float] = {}
    raw_text_x0_by_row = table.metadata.get("first_column_text_x0_by_row")
    if isinstance(raw_text_x0_by_row, dict):
        for row_idx_key, value in raw_text_x0_by_row.items():
            try:
                first_column_text_x0_by_row[int(row_idx_key)] = float(value)
            except (TypeError, ValueError):
                continue
    for cell in table.cells:
        if cell.col_idx != 0 or cell.bbox is None or cell.row_idx >= table.n_rows:
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
    indent_levels = [
        row_view.indent_level
        for row_view in row_views
        if row_view.indent_level is not None
    ]
    if len(indent_levels) < 3:
        indentation_informative = False
    else:
        baseline = min(indent_levels)
        meaningful_offsets = [
            level - baseline for level in indent_levels if level - baseline >= 2
        ]
        indentation_informative = (
            len(meaningful_offsets) >= 2 and len(set(indent_levels)) >= 2
        )
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
        "dropped_leading_cols": 0,
        "dropped_trailing_cols": 0,
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
        n_cols=table.n_cols,
        metadata=metadata,
    )


def normalize_extracted_tables(
    tables: list[ExtractedTable],
    table_regions: list[TableRegion],
) -> list[NormalizedTable]:
    """Normalize a list of extracted tables while preserving input order."""
    region_by_table_id = {region.table_id: region for region in table_regions}
    missing_region_table_ids = [
        table.table_id for table in tables if table.table_id not in region_by_table_id
    ]
    if missing_region_table_ids:
        raise ValueError(
            "TableRegion missing for ExtractedTable IDs: "
            + ", ".join(missing_region_table_ids)
        )
    return [
        normalize_extracted_table(
            table, table_region=region_by_table_id[table.table_id]
        )
        for table in tables
    ]
