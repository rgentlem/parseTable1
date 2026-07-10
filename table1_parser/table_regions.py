"""Geometry-first row-region detection for extracted tables."""

from __future__ import annotations

import re
from collections.abc import Sequence

from table1_parser.heuristics.value_pattern_detector import detect_value_pattern
from table1_parser.schemas import CellTextAnnotationTable, ExtractedTable
from table1_parser.schemas.table_region import TableRegion, TableRegionRow
from table1_parser.text_cleaning import clean_text


RULE_TOLERANCE = 3.0
CAPTION_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")
TABLE_CAPTION_PATTERN = re.compile(r"^\s*table\s*\d+\b", re.IGNORECASE)


def build_table_regions(
    extracted_tables: Sequence[ExtractedTable],
    *,
    paper_text_stream: object | None = None,
    paper_page_furniture: object | None = None,
    cell_text_annotations: Sequence[CellTextAnnotationTable] | None = None,
) -> list[TableRegion]:
    """Build row-region decisions for extracted tables."""
    footer_marker_rows_by_table_id = _footer_marker_rows_by_table_id(cell_text_annotations or [], extracted_tables)
    return [
        build_table_region(
            table,
            footer_marker_rows=footer_marker_rows_by_table_id.get(table.table_id, set()),
        )
        for table in extracted_tables
    ]


def build_table_region(table: ExtractedTable, *, footer_marker_rows: set[int] | None = None) -> TableRegion:
    """Assign extracted rows to caption, column-header, body, and footer regions."""
    grid = _cell_grid(table)
    row_bounds = _row_bounds(table)
    horizontal_rules = _rules(table.metadata.get("horizontal_rules"))
    full_width_rules = _rules(table.metadata.get("full_width_horizontal_rules"))
    boundary_rules = full_width_rules or horizontal_rules
    diagnostics: list[str] = []

    caption_rows: list[int] = []
    preamble_rows: list[int] = []
    header_rows: list[int]
    body_rows: list[int]
    footer_rows: list[int] = []
    start_rule_y: float | None = None
    header_body_rule_y: float | None = None
    body_footer_rule_y: float | None = None

    if row_bounds is not None and boundary_rules:
        preamble_candidates, start_rule_y = _rows_before_first_table_rule(grid, row_bounds, boundary_rules, table)
        caption_rows = (
            list(preamble_candidates)
            if _rows_match_caption([grid[row_idx] for row_idx in preamble_candidates], table)
            else [row_idx for row_idx in preamble_candidates if _row_matches_caption(grid[row_idx], table)]
        )
        preamble_rows = [row_idx for row_idx in preamble_candidates if row_idx not in set(caption_rows)]
        content_start = max(preamble_candidates) + 1 if preamble_candidates else 0
        header_rows, body_rows, header_body_rule_y = _header_body_from_rules(
            grid,
            row_bounds,
            boundary_rules,
            content_start_row_idx=content_start,
            start_rule_y=start_rule_y,
        )
        if header_rows and body_rows:
            detection_basis = "table_region_horizontal_rules"
            confidence = 0.92
        else:
            header_rows, body_rows = _header_body_from_values(grid, content_start_row_idx=content_start)
            detection_basis = "table_region_value_anchor"
            confidence = 0.72
    else:
        diagnostics.append("missing_rule_or_row_bound_geometry")
        header_rows, body_rows = _header_body_from_values(grid, content_start_row_idx=0)
        detection_basis = "table_region_value_anchor"
        confidence = 0.72 if header_rows and body_rows else 0.35

    if row_bounds is not None and body_rows:
        footer_rule_source = full_width_rules or boundary_rules
        footer_rows, body_footer_rule_y, footer_basis = _footer_rows(
            grid,
            row_bounds,
            footer_rule_source,
            body_rows,
            footer_marker_rows=footer_marker_rows or set(),
        )
        if footer_rows:
            footer_set = set(footer_rows)
            body_rows = [row_idx for row_idx in body_rows if row_idx not in footer_set]
            diagnostics.append(f"footer_rows_detected:{footer_basis}")

    assigned = {*caption_rows, *preamble_rows, *header_rows, *body_rows, *footer_rows}
    if len(assigned) < table.n_rows:
        diagnostics.append("some_rows_unassigned")

    return TableRegion(
        region_id=f"{table.table_id}:table_region",
        table_id=table.table_id,
        source_pdf=table.source_pdf,
        page_num=table.page_num,
        n_rows=table.n_rows,
        n_cols=table.n_cols,
        caption_rows=caption_rows,
        preamble_rows=preamble_rows,
        column_header_rows=header_rows,
        body_rows=body_rows,
        footer_note_rows=footer_rows,
        row_regions=_row_regions(table.n_rows, grid, caption_rows, preamble_rows, header_rows, body_rows, footer_rows, detection_basis),
        horizontal_rules=horizontal_rules,
        full_width_horizontal_rules=full_width_rules,
        start_rule_y=start_rule_y,
        header_body_rule_y=header_body_rule_y,
        body_footer_rule_y=body_footer_rule_y,
        detection_basis=detection_basis,
        confidence=confidence,
        diagnostics=list(dict.fromkeys(diagnostics)),
    )


def table_regions_to_payload(regions: Sequence[TableRegion]) -> list[dict[str, object]]:
    """Serialize table regions as JSON-friendly records."""
    return [region.model_dump(mode="json") for region in regions]


def _footer_marker_rows_by_table_id(
    cell_text_annotations: Sequence[CellTextAnnotationTable],
    extracted_tables: Sequence[ExtractedTable],
) -> dict[str, set[int]]:
    tables_by_id = {table.table_id: table for table in extracted_tables}
    first_populated_cell_by_row: dict[str, dict[int, tuple[int, tuple[float, float, float, float] | None]]] = {}
    for table in extracted_tables:
        row_cells: dict[int, list[tuple[int, tuple[float, float, float, float] | None, str]]] = {}
        for cell in table.cells:
            if clean_text(cell.text):
                row_cells.setdefault(cell.row_idx, []).append((cell.col_idx, cell.bbox, cell.text))
        first_populated_cell_by_row[table.table_id] = {
            row_idx: (min(cells, key=lambda item: item[0])[0], min(cells, key=lambda item: item[0])[1])
            for row_idx, cells in row_cells.items()
        }

    marker_rows: dict[str, set[int]] = {}
    for annotation_table in cell_text_annotations:
        if annotation_table.table_id not in tables_by_id:
            continue
        first_cells = first_populated_cell_by_row.get(annotation_table.table_id, {})
        for annotation in annotation_table.annotations:
            if annotation.annotation_type != "superscript":
                continue
            first_cell = first_cells.get(annotation.row_idx)
            if first_cell is None:
                continue
            first_col_idx, first_bbox = first_cell
            if annotation.col_idx != first_col_idx:
                continue
            if first_bbox is not None and annotation.bbox is not None and annotation.bbox[0] > first_bbox[0] + 6.0:
                continue
            marker_rows.setdefault(annotation_table.table_id, set()).add(annotation.row_idx)
    return marker_rows


def _cell_grid(table: ExtractedTable) -> list[list[str]]:
    grid = [["" for _ in range(table.n_cols)] for _ in range(table.n_rows)]
    for cell in table.cells:
        if cell.row_idx < table.n_rows and cell.col_idx < table.n_cols:
            grid[cell.row_idx][cell.col_idx] = cell.text
    return grid


def _row_bounds(table: ExtractedTable) -> list[tuple[float, float]] | None:
    raw_bounds = table.metadata.get("row_bounds")
    if isinstance(raw_bounds, list) and len(raw_bounds) == table.n_rows:
        bounds: list[tuple[float, float]] = []
        for item in raw_bounds:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                return None
            bounds.append((float(item[0]), float(item[1])))
        return bounds

    bounds: list[tuple[float, float] | None] = [None] * table.n_rows
    for cell in table.cells:
        if cell.bbox is None or cell.row_idx >= table.n_rows:
            continue
        top, bottom = float(cell.bbox[1]), float(cell.bbox[3])
        current = bounds[cell.row_idx]
        bounds[cell.row_idx] = (top, bottom) if current is None else (min(current[0], top), max(current[1], bottom))
    return [bound for bound in bounds] if all(bound is not None for bound in bounds) else None


def _rules(value: object) -> list[float]:
    if not isinstance(value, list):
        return []
    return sorted({round(float(item), 3) for item in value if isinstance(item, (int, float))})


def _rows_before_first_table_rule(
    grid: list[list[str]],
    row_bounds: list[tuple[float, float]],
    rules: list[float],
    table: ExtractedTable,
) -> tuple[list[int], float | None]:
    first_text_row = next(
        (row_idx for row_idx, row in enumerate(grid) if any(clean_text(cell) for cell in row)),
        None,
    )
    if first_text_row is not None and rules:
        first_rule = rules[0]
        if (
            first_rule <= row_bounds[first_text_row][0] + RULE_TOLERANCE
            and any(rule > first_rule + RULE_TOLERANCE for rule in rules)
        ):
            return [], first_rule

    for rule_y in rules:
        rows_above = [row_idx for row_idx, (_, bottom) in enumerate(row_bounds) if bottom <= rule_y + RULE_TOLERANCE]
        rows_below = [row_idx for row_idx, (top, _) in enumerate(row_bounds) if top >= rule_y - RULE_TOLERANCE]
        if not rows_above or not rows_below or len(rows_above) > 4:
            continue
        later_rule_exists = any(other_rule > rule_y + RULE_TOLERANCE for other_rule in rules)
        if later_rule_exists and _rows_match_caption([grid[row_idx] for row_idx in rows_above], table):
            return rows_above, rule_y
        if max((_nonempty_count(grid[row_idx]) for row_idx in rows_above), default=0) <= 2:
            return rows_above, rule_y
    return [], None


def _header_body_from_rules(
    grid: list[list[str]],
    row_bounds: list[tuple[float, float]],
    rules: list[float],
    *,
    content_start_row_idx: int,
    start_rule_y: float | None,
) -> tuple[list[int], list[int], float | None]:
    for rule_y in rules:
        if start_rule_y is not None and rule_y <= start_rule_y + RULE_TOLERANCE:
            continue
        header_rows = [
            row_idx
            for row_idx, (top, bottom) in enumerate(row_bounds)
            if row_idx >= content_start_row_idx
            and bottom <= rule_y + RULE_TOLERANCE
            and (start_rule_y is None or top >= start_rule_y - RULE_TOLERANCE)
        ]
        if not header_rows or len(header_rows) > 12:
            continue
        body_start = next(
            (
                row_idx
                for row_idx, (top, _) in enumerate(row_bounds)
                if top >= rule_y - RULE_TOLERANCE and any(clean_text(cell) for cell in grid[row_idx])
            ),
            None,
        )
        if body_start is None or not _body_start_supported(grid, body_start):
            continue
        return header_rows, _nonempty_rows_from(grid, body_start), rule_y
    return [], [], None


def _header_body_from_values(grid: list[list[str]], *, content_start_row_idx: int) -> tuple[list[int], list[int]]:
    first_value_row = next(
        (row_idx for row_idx in range(content_start_row_idx, len(grid)) if _is_value_matrix_row(grid[row_idx])),
        None,
    )
    if first_value_row is None:
        header_rows = [row_idx for row_idx in range(min(1, len(grid))) if any(clean_text(cell) for cell in grid[row_idx])]
        return header_rows, [row_idx for row_idx in range(len(grid)) if row_idx not in set(header_rows) and any(clean_text(cell) for cell in grid[row_idx])]

    body_start = first_value_row
    for row_idx in range(first_value_row - 1, content_start_row_idx - 1, -1):
        row = grid[row_idx]
        trailing_nonempty = sum(bool(clean_text(cell)) for cell in row[1:])
        if clean_text(row[0] if row else "") and trailing_nonempty <= 1 and _value_like_count(row[1:]) <= 1:
            body_start = row_idx
            continue
        break
    header_rows = [row_idx for row_idx in range(content_start_row_idx, body_start) if any(clean_text(cell) for cell in grid[row_idx])]
    return header_rows, _nonempty_rows_from(grid, body_start)


def _footer_rows(
    grid: list[list[str]],
    row_bounds: list[tuple[float, float]],
    rules: list[float],
    body_rows: list[int],
    *,
    footer_marker_rows: set[int],
) -> tuple[list[int], float | None, str]:
    for rule_y in rules:
        rows_above = [row_idx for row_idx in body_rows if row_bounds[row_idx][1] <= rule_y + RULE_TOLERANCE]
        rows_below = [row_idx for row_idx in body_rows if row_bounds[row_idx][0] >= rule_y - RULE_TOLERANCE]
        if (
            rows_above
            and rows_below
            and any(_is_value_matrix_row(grid[row_idx]) for row_idx in rows_above)
            and not any(_is_value_matrix_row(grid[row_idx]) for row_idx in rows_below)
        ):
            return rows_below, rule_y, "after_body_footer_rule"

    value_rows = [row_idx for row_idx in body_rows if _is_value_matrix_row(grid[row_idx])]
    if not value_rows:
        return [], None, "no_value_matrix_rows"
    last_value = max(value_rows)
    footer_rows = [
        row_idx
        for row_idx in body_rows
        if row_idx > last_value and row_idx in footer_marker_rows and _value_like_count(grid[row_idx][1:]) == 0
    ]
    return (footer_rows, None, "after_last_value_matrix_row_with_structured_marker") if footer_rows else ([], None, "no_footer_rows")


def _row_regions(
    n_rows: int,
    grid: list[list[str]],
    caption_rows: list[int],
    preamble_rows: list[int],
    header_rows: list[int],
    body_rows: list[int],
    footer_rows: list[int],
    detection_basis: str,
) -> list[TableRegionRow]:
    role_by_row = {
        **{row_idx: "caption" for row_idx in caption_rows},
        **{row_idx: "preamble" for row_idx in preamble_rows},
        **{row_idx: "column_header" for row_idx in header_rows},
        **{row_idx: "body" for row_idx in body_rows},
        **{row_idx: "footer_note" for row_idx in footer_rows},
    }
    return [
        TableRegionRow(
            row_idx=row_idx,
            role=role_by_row.get(row_idx, "unknown"),
            text=_row_text(grid[row_idx]) if row_idx < len(grid) else "",
            detection_basis=detection_basis if row_idx in role_by_row else "not_assigned_by_table_region_detector",
        )
        for row_idx in range(n_rows)
    ]


def _row_text(row: list[str]) -> str:
    return clean_text(" ".join(cell for cell in row if clean_text(cell)))


def _nonempty_rows_from(grid: list[list[str]], start_row_idx: int) -> list[int]:
    return [row_idx for row_idx in range(start_row_idx, len(grid)) if any(clean_text(cell) for cell in grid[row_idx])]


def _nonempty_count(row: list[str]) -> int:
    return sum(bool(clean_text(cell)) for cell in row)


def _body_start_supported(grid: list[list[str]], body_start: int) -> bool:
    if _is_value_matrix_row(grid[body_start]):
        return True
    first_cell = clean_text(grid[body_start][0] if grid[body_start] else "")
    return bool(first_cell) and any(
        _is_value_matrix_row(grid[row_idx])
        for row_idx in range(body_start + 1, min(len(grid), body_start + 4))
    )


def _is_value_matrix_row(row: list[str]) -> bool:
    trailing = [cell for cell in row[1:] if clean_text(cell)]
    if not trailing:
        return False
    required = 1 if len(row) <= 3 else 2
    return _value_like_count(trailing) >= required


def _value_like_count(cells: list[str]) -> int:
    return sum(_is_value_like(cell) for cell in cells if clean_text(cell))


def _is_value_like(value: str) -> bool:
    text = clean_text(value)
    pattern = detect_value_pattern(text).pattern
    if pattern == "p_value" and not any(char.isdigit() for char in text):
        return False
    if pattern != "unknown":
        return True
    return any(char.isdigit() for char in text) and sum(char.isalpha() for char in text) <= 3


def _row_matches_caption(row: list[str], table: ExtractedTable) -> bool:
    return _rows_match_caption([row], table)


def _rows_match_caption(rows: list[list[str]], table: ExtractedTable) -> bool:
    text = _row_text([cell for row in rows for cell in row])
    if not text:
        return False
    if TABLE_CAPTION_PATTERN.search(text):
        return True
    caption = clean_text(" ".join(part for part in [table.title or "", table.caption or ""] if part))
    if not caption:
        return False
    text_tokens = CAPTION_TOKEN_PATTERN.findall(text.casefold())
    caption_tokens = set(CAPTION_TOKEN_PATTERN.findall(caption.casefold()))
    return bool(text_tokens) and sum(token in caption_tokens for token in text_tokens) / len(text_tokens) >= 0.75
