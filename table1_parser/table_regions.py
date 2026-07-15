"""Geometry-first row-region detection for extracted tables."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from table1_parser.body_occupancy import (
    build_body_occupancy_table,
    collect_paper_space_widths_by_style,
)
from table1_parser.heuristics.value_pattern_detector import detect_value_pattern
from table1_parser.normalize.header_detector import detect_header_rows_with_metadata
from table1_parser.schemas import (
    CellTextAnnotationTable,
    ExtractedTable,
    PaperPositionedDocument,
    PaperPositionedPage,
    TableBoundaryCandidate,
    TableBoundaryProposal,
)
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
    table_boundary_proposals: Sequence[TableBoundaryProposal] | None = None,
    paper_positioned_document: PaperPositionedDocument | None = None,
) -> list[TableRegion]:
    """Build row-region decisions for extracted tables."""
    footer_marker_rows_by_table_id = _footer_marker_rows_by_table_id(
        cell_text_annotations or [], extracted_tables
    )
    proposals_by_table_id = {
        proposal.table_id: proposal for proposal in table_boundary_proposals or []
    }
    annotations_by_table_id = {
        annotation_table.table_id: annotation_table
        for annotation_table in cell_text_annotations or []
    }
    pages_by_num = {
        page.page_num: page
        for page in (
            paper_positioned_document.pages
            if paper_positioned_document is not None
            else []
        )
    }
    paper_space_widths_by_style = (
        collect_paper_space_widths_by_style(paper_positioned_document)
        if paper_positioned_document is not None
        else {}
    )
    return [
        build_table_region(
            table,
            footer_marker_rows=footer_marker_rows_by_table_id.get(
                table.table_id, set()
            ),
            table_boundary_proposal=proposals_by_table_id.get(table.table_id),
            positioned_page=pages_by_num.get(table.page_num),
            annotation_table=annotations_by_table_id.get(table.table_id),
            paper_space_widths_by_style=paper_space_widths_by_style,
        )
        for table in extracted_tables
    ]


def build_table_region(
    table: ExtractedTable,
    *,
    footer_marker_rows: set[int] | None = None,
    table_boundary_proposal: TableBoundaryProposal | None = None,
    positioned_page: PaperPositionedPage | None = None,
    annotation_table: CellTextAnnotationTable | None = None,
    paper_space_widths_by_style: Mapping[tuple[str, float], Sequence[float]]
    | None = None,
) -> TableRegion:
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

    content_start = 0
    if row_bounds is not None and boundary_rules:
        preamble_candidates, start_rule_y = _rows_before_first_table_rule(
            grid, row_bounds, boundary_rules, table
        )
        caption_rows = (
            list(preamble_candidates)
            if _rows_match_caption(
                [grid[row_idx] for row_idx in preamble_candidates], table
            )
            else [
                row_idx
                for row_idx in preamble_candidates
                if _row_matches_caption(grid[row_idx], table)
            ]
        )
        preamble_rows = [
            row_idx
            for row_idx in preamble_candidates
            if row_idx not in set(caption_rows)
        ]
        content_start = max(preamble_candidates) + 1 if preamble_candidates else 0
    elif row_bounds is None:
        diagnostics.append("missing_rule_or_row_bound_geometry")

    if (
        table_boundary_proposal is not None
        and not table_boundary_proposal.credible_rule_geometry
        and not table_boundary_proposal.coherent_positioned_grid
    ):
        detection_basis = "table_region_fail_closed_insufficient_geometry"
        diagnostics.append("fail_closed_no_credible_rules_or_coherent_positioned_grid")
        return TableRegion(
            region_id=f"{table.table_id}:table_region",
            table_id=table.table_id,
            source_pdf=table.source_pdf,
            page_num=table.page_num,
            n_rows=table.n_rows,
            n_cols=table.n_cols,
            caption_rows=caption_rows,
            preamble_rows=preamble_rows,
            column_header_rows=[],
            body_rows=[],
            footer_note_rows=[],
            row_regions=_row_regions(
                table.n_rows,
                grid,
                caption_rows,
                preamble_rows,
                [],
                [],
                [],
                detection_basis,
            ),
            horizontal_rules=horizontal_rules,
            full_width_horizontal_rules=full_width_rules,
            start_rule_y=start_rule_y,
            detection_basis=detection_basis,
            confidence=0.0,
            diagnostics=diagnostics,
        )

    content_grid = grid[content_start:]
    content_row_bounds = row_bounds[content_start:] if row_bounds is not None else None
    local_header_rows, local_body_rows, header_detection = (
        detect_header_rows_with_metadata(
            content_grid,
            row_bounds=content_row_bounds,
            horizontal_rules=horizontal_rules,
            separator_horizontal_rules=full_width_rules or None,
        )
    )
    header_rows = [
        row_idx + content_start
        for row_idx in local_header_rows
        if any(clean_text(cell) for cell in content_grid[row_idx])
    ]
    body_rows = [
        row_idx + content_start
        for row_idx in local_body_rows
        if any(clean_text(cell) for cell in content_grid[row_idx])
    ]
    header_body_rule = header_detection.get("separator_rule_y")
    header_body_rule_y = (
        float(header_body_rule) if isinstance(header_body_rule, (int, float)) else None
    )
    header_source = str(header_detection.get("source") or "unclassified")
    detection_basis = f"table_region_{header_source}"
    confidence = (
        0.92
        if header_source == "horizontal_rule_separator"
        else 0.78
        if header_source == "value_region_anchor"
        else 0.35
    )

    if (
        header_source == "unclassified_no_separator_or_value_anchor"
        and not header_rows
        and body_rows
        and row_bounds is not None
        and full_width_rules
        and positioned_page is not None
        and table.n_cols > 0
        and body_rows[0] == content_start
        and _nonempty_count(grid[body_rows[0]]) == table.n_cols
    ):
        first_body_row = body_rows[0]
        following_row = next(
            (row_idx for row_idx in body_rows if row_idx > first_body_row),
            None,
        )
        if following_row is not None:
            row_top, row_bottom = row_bounds[first_body_row]
            row_height = row_bottom - row_top
            upper_rule = max(
                (
                    rule_y
                    for rule_y in full_width_rules
                    if rule_y <= row_top + RULE_TOLERANCE
                ),
                default=None,
            )
            lower_rule = min(
                (
                    rule_y
                    for rule_y in full_width_rules
                    if rule_y >= row_bottom - RULE_TOLERANCE
                ),
                default=None,
            )
            positioned_evidence = table.metadata.get("table_positioned_evidence")
            line_ids = (
                positioned_evidence.get("line_ids")
                if isinstance(positioned_evidence, dict)
                else None
            )
            canonical_line_bboxes = (
                positioned_evidence.get("canonical_line_bboxes")
                if isinstance(positioned_evidence, dict)
                else None
            )
            if (
                upper_rule is not None
                and lower_rule is not None
                and lower_rule > upper_rule
                and row_top - upper_rule <= max(RULE_TOLERANCE, row_height)
                and lower_rule - row_bottom <= max(RULE_TOLERANCE, row_height)
                and lower_rule
                <= row_bounds[following_row][0] + RULE_TOLERANCE
                and isinstance(line_ids, list)
                and isinstance(canonical_line_bboxes, list)
                and len(line_ids) == len(canonical_line_bboxes)
            ):
                lines_by_id = {line.line_id: line for line in positioned_page.lines}
                style_counts = {
                    first_body_row: [0, 0],
                    following_row: [0, 0],
                }
                for line_id, line_bbox in zip(
                    line_ids,
                    canonical_line_bboxes,
                    strict=True,
                ):
                    if (
                        not isinstance(line_id, str)
                        or not isinstance(line_bbox, (list, tuple))
                        or len(line_bbox) != 4
                        or line_id not in lines_by_id
                    ):
                        continue
                    line_center_y = (float(line_bbox[1]) + float(line_bbox[3])) / 2.0
                    matched_row = next(
                        (
                            row_idx
                            for row_idx in style_counts
                            if row_bounds[row_idx][0] - 0.5
                            <= line_center_y
                            <= row_bounds[row_idx][1] + 0.5
                        ),
                        None,
                    )
                    if matched_row is None:
                        continue
                    for span in lines_by_id[line_id].spans:
                        visible_characters = len("".join(span.text.split()))
                        style_counts[matched_row][0] += visible_characters
                        font_key = (span.font or "").casefold()
                        if (
                            "bold" in font_key
                            or "semibold" in font_key
                            or (span.flags is not None and span.flags & 16)
                        ):
                            style_counts[matched_row][1] += visible_characters
                header_characters, header_bold_characters = style_counts[
                    first_body_row
                ]
                following_characters, following_bold_characters = style_counts[
                    following_row
                ]
                if (
                    header_characters > 0
                    and header_bold_characters / header_characters >= 0.7
                    and following_characters > 0
                    and following_bold_characters / following_characters < 0.7
                ):
                    header_rows = [first_body_row]
                    body_rows = body_rows[1:]
                    header_body_rule_y = lower_rule
                    detection_basis = "table_region_text_header_rule_typography"
                    confidence = 0.9
                    diagnostics.append(
                        "text_header_from_complete_bold_rule_bounded_first_row"
                    )

    if (
        table_boundary_proposal is not None
        and positioned_page is not None
        and body_rows
    ):
        first_body_row = min(body_rows)
        last_body_row = max(body_rows)
        later_boundaries = [
            candidate
            for candidate in table_boundary_proposal.boundary_candidates
            if (
                candidate.row_before_idx is not None
                and candidate.row_after_idx is not None
                and candidate.row_before_idx >= first_body_row
                and candidate.row_before_idx < last_body_row
                and candidate.row_after_idx > candidate.row_before_idx
            )
        ]
        supported_footer_boundaries = [
            candidate
            for candidate in later_boundaries
            if "body_footer" in candidate.possible_roles
        ]
        selected_candidate: TableBoundaryCandidate | None = None
        if len(supported_footer_boundaries) == 1:
            selected_candidate = supported_footer_boundaries[0]
            diagnostics.append("body_interval_selected_by_boundary_evidence")
        else:
            competing_boundaries = (
                supported_footer_boundaries
                if supported_footer_boundaries
                else later_boundaries
            )
            competing_body_ends = {
                candidate.row_before_idx: candidate
                for candidate in competing_boundaries
                if candidate.row_before_idx is not None
            }
            if not supported_footer_boundaries and competing_body_ends:
                competing_body_ends[last_body_row] = None
            if len(competing_body_ends) > 1:
                interval_candidates: list[
                    tuple[int, int, int, TableBoundaryCandidate | None]
                ] = []
                for body_end, candidate in competing_body_ends.items():
                    candidate_rows = [
                        row_idx for row_idx in body_rows if row_idx <= body_end
                    ]
                    candidate_occupancy = build_body_occupancy_table(
                        table,
                        positioned_page=positioned_page,
                        body_row_indices=candidate_rows,
                        table_boundary_proposal=table_boundary_proposal,
                        annotation_table=annotation_table,
                        paper_space_widths_by_style=(paper_space_widths_by_style or {}),
                    )
                    if candidate_occupancy.diagnostics:
                        continue
                    interval_candidates.append(
                        (
                            len(candidate_occupancy.qualified_zero_gaps),
                            len(candidate_rows),
                            body_end,
                            candidate,
                        )
                    )
                if len(interval_candidates) > 1:
                    maximum_separator_count = max(
                        separator_count
                        for separator_count, _, _, _ in interval_candidates
                    )
                    _, _, _, selected_candidate = max(
                        (
                            item
                            for item in interval_candidates
                            if item[0] == maximum_separator_count
                        ),
                        key=lambda item: item[1],
                    )
                    diagnostics.append(
                        "body_interval_selected_from_competing_models:"
                        f"models={len(interval_candidates)}:"
                        f"separators={maximum_separator_count}"
                    )
        if selected_candidate is not None:
            selected_row_before = selected_candidate.row_before_idx
            if isinstance(selected_row_before, int):
                footer_rows = [
                    row_idx for row_idx in body_rows if row_idx > selected_row_before
                ]
                body_rows = [
                    row_idx for row_idx in body_rows if row_idx <= selected_row_before
                ]
                body_footer_rule_y = selected_candidate.canonical_y
    elif row_bounds is not None and body_rows:
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
        row_regions=_row_regions(
            table.n_rows,
            grid,
            caption_rows,
            preamble_rows,
            header_rows,
            body_rows,
            footer_rows,
            detection_basis,
        ),
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
    first_populated_cell_by_row: dict[
        str, dict[int, tuple[int, tuple[float, float, float, float] | None]]
    ] = {}
    for table in extracted_tables:
        row_cells: dict[
            int, list[tuple[int, tuple[float, float, float, float] | None, str]]
        ] = {}
        for cell in table.cells:
            if clean_text(cell.text):
                row_cells.setdefault(cell.row_idx, []).append(
                    (cell.col_idx, cell.bbox, cell.text)
                )
        first_populated_cell_by_row[table.table_id] = {
            row_idx: (
                min(cells, key=lambda item: item[0])[0],
                min(cells, key=lambda item: item[0])[1],
            )
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
            if (
                first_bbox is not None
                and annotation.bbox is not None
                and annotation.bbox[0] > first_bbox[0] + 6.0
            ):
                continue
            marker_rows.setdefault(annotation_table.table_id, set()).add(
                annotation.row_idx
            )
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
        bounds[cell.row_idx] = (
            (top, bottom)
            if current is None
            else (min(current[0], top), max(current[1], bottom))
        )
    return (
        [bound for bound in bounds]
        if all(bound is not None for bound in bounds)
        else None
    )


def _rules(value: object) -> list[float]:
    if not isinstance(value, list):
        return []
    return sorted(
        {round(float(item), 3) for item in value if isinstance(item, (int, float))}
    )


def _rows_before_first_table_rule(
    grid: list[list[str]],
    row_bounds: list[tuple[float, float]],
    rules: list[float],
    table: ExtractedTable,
) -> tuple[list[int], float | None]:
    first_text_row = next(
        (
            row_idx
            for row_idx, row in enumerate(grid)
            if any(clean_text(cell) for cell in row)
        ),
        None,
    )
    if first_text_row is not None and rules:
        first_rule = rules[0]
        if first_rule <= row_bounds[first_text_row][0] + RULE_TOLERANCE and any(
            rule > first_rule + RULE_TOLERANCE for rule in rules
        ):
            return [], first_rule

    for rule_y in rules:
        rows_above = [
            row_idx
            for row_idx, (_, bottom) in enumerate(row_bounds)
            if bottom <= rule_y + RULE_TOLERANCE
        ]
        rows_below = [
            row_idx
            for row_idx, (top, _) in enumerate(row_bounds)
            if top >= rule_y - RULE_TOLERANCE
        ]
        if not rows_above or not rows_below or len(rows_above) > 4:
            continue
        later_rule_exists = any(
            other_rule > rule_y + RULE_TOLERANCE for other_rule in rules
        )
        if later_rule_exists and _rows_match_caption(
            [grid[row_idx] for row_idx in rows_above], table
        ):
            return rows_above, rule_y
        if (
            max((_nonempty_count(grid[row_idx]) for row_idx in rows_above), default=0)
            <= 2
        ):
            return rows_above, rule_y
    return [], None


def _footer_rows(
    grid: list[list[str]],
    row_bounds: list[tuple[float, float]],
    rules: list[float],
    body_rows: list[int],
    *,
    footer_marker_rows: set[int],
) -> tuple[list[int], float | None, str]:
    for rule_y in rules:
        rows_above = [
            row_idx
            for row_idx in body_rows
            if row_bounds[row_idx][1] <= rule_y + RULE_TOLERANCE
        ]
        rows_below = [
            row_idx
            for row_idx in body_rows
            if row_bounds[row_idx][0] >= rule_y - RULE_TOLERANCE
        ]
        if (
            rows_above
            and rows_below
            and any(_is_value_matrix_row(grid[row_idx]) for row_idx in rows_above)
            and not any(_is_value_matrix_row(grid[row_idx]) for row_idx in rows_below)
            and _value_like_count(grid[rows_below[0]][1:]) == 0
        ):
            return rows_below, rule_y, "after_body_footer_rule"

    value_rows = [
        row_idx for row_idx in body_rows if _is_value_matrix_row(grid[row_idx])
    ]
    if not value_rows:
        return [], None, "no_value_matrix_rows"
    last_value = max(value_rows)
    footer_rows = [
        row_idx
        for row_idx in body_rows
        if row_idx > last_value
        and row_idx in footer_marker_rows
        and _value_like_count(grid[row_idx][1:]) == 0
    ]
    return (
        (footer_rows, None, "after_last_value_matrix_row_with_structured_marker")
        if footer_rows
        else ([], None, "no_footer_rows")
    )


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
            detection_basis=detection_basis
            if row_idx in role_by_row
            else "not_assigned_by_table_region_detector",
        )
        for row_idx in range(n_rows)
    ]


def _row_text(row: list[str]) -> str:
    return clean_text(" ".join(cell for cell in row if clean_text(cell)))


def _nonempty_count(row: list[str]) -> int:
    return sum(bool(clean_text(cell)) for cell in row)


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
    return (
        any(char.isdigit() for char in text)
        and sum(char.isalpha() for char in text) <= 3
    )


def _row_matches_caption(row: list[str], table: ExtractedTable) -> bool:
    return _rows_match_caption([row], table)


def _rows_match_caption(rows: list[list[str]], table: ExtractedTable) -> bool:
    text = _row_text([cell for row in rows for cell in row])
    if not text:
        return False
    if TABLE_CAPTION_PATTERN.search(text):
        return True
    caption = clean_text(
        " ".join(part for part in [table.title or "", table.caption or ""] if part)
    )
    if not caption:
        return False
    text_tokens = CAPTION_TOKEN_PATTERN.findall(text.casefold())
    caption_tokens = set(CAPTION_TOKEN_PATTERN.findall(caption.casefold()))
    return (
        bool(text_tokens)
        and sum(token in caption_tokens for token in text_tokens) / len(text_tokens)
        >= 0.75
    )
