"""Build provisional table-boundary evidence in canonical geometry."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from statistics import median

from table1_parser.schemas import (
    ExtractedTable,
    PaperPositionedDocument,
    PaperPositionedPage,
    PaperTextLine,
    PaperTextStream,
    TableBoundaryCandidate,
    TableBoundaryProposal,
    TableBoundaryRuleReference,
    TablePositionedEvidence,
)
from table1_parser.table_regions import _is_value_matrix_row, _value_like_count


def build_table_boundary_proposals(
    extracted_tables: Sequence[ExtractedTable],
    *,
    paper_positioned_document: PaperPositionedDocument | None,
    paper_text_stream: PaperTextStream | None = None,
) -> list[TableBoundaryProposal]:
    """Build geometry-only boundary alternatives for extracted tables."""
    pages_by_num = {
        page.page_num: page
        for page in (
            paper_positioned_document.pages
            if paper_positioned_document is not None
            else []
        )
    }
    body_style_record = (
        paper_text_stream.metadata.get("dominant_body_text_style")
        if paper_text_stream is not None
        else None
    )
    body_font = (
        str(body_style_record.get("font", "")).strip()
        if isinstance(body_style_record, Mapping)
        else ""
    )
    body_size_value = (
        body_style_record.get("font_size")
        if isinstance(body_style_record, Mapping)
        else None
    )
    body_text_style = (
        (body_font, round(float(body_size_value), 1))
        if body_font and isinstance(body_size_value, (int, float))
        else None
    )
    text_lines_by_page: dict[int, list[PaperTextLine]] = {}
    for line in paper_text_stream.lines if paper_text_stream is not None else []:
        text_lines_by_page.setdefault(line.page_num, []).append(line)
    table_starts: dict[str, tuple[int, str | None, float]] = {}
    for table in extracted_tables:
        raw_evidence = table.metadata.get("table_positioned_evidence")
        if not isinstance(raw_evidence, dict):
            continue
        evidence = TablePositionedEvidence.model_validate(raw_evidence)
        if evidence.canonical_bbox is None:
            continue
        start_y = evidence.canonical_bbox[1]
        if evidence.canonical_caption_bbox is not None:
            start_y = min(start_y, evidence.canonical_caption_bbox[1])
        table_starts[table.table_id] = (
            table.page_num,
            evidence.orientation_group_id,
            start_y,
        )
    proposals: list[TableBoundaryProposal] = []
    for table in extracted_tables:
        current_start = table_starts.get(table.table_id)
        next_table_start_y = None
        if current_start is not None:
            page_num, orientation_group_id, start_y = current_start
            next_table_start_y = min(
                (
                    other_start_y
                    for other_table_id, (
                        other_page_num,
                        other_orientation_group_id,
                        other_start_y,
                    ) in table_starts.items()
                    if other_table_id != table.table_id
                    and other_page_num == page_num
                    and other_orientation_group_id == orientation_group_id
                    and other_start_y > start_y
                ),
                default=None,
            )
        proposals.append(
            build_table_boundary_proposal(
                table,
                positioned_page=pages_by_num.get(table.page_num),
                text_lines=text_lines_by_page.get(table.page_num, []),
                body_text_style=body_text_style,
                next_table_start_y=next_table_start_y,
            )
        )
    return proposals


def build_table_boundary_proposal(
    table: ExtractedTable,
    *,
    positioned_page: PaperPositionedPage | None,
    text_lines: Sequence[PaperTextLine] = (),
    body_text_style: tuple[str, float] | None = None,
    next_table_start_y: float | None = None,
) -> TableBoundaryProposal:
    """Build one canonical boundary proposal without selecting row ownership."""
    concerns: list[str] = []
    diagnostics: list[str] = []
    raw_evidence = table.metadata.get("table_positioned_evidence")
    if not isinstance(raw_evidence, dict):
        return TableBoundaryProposal(
            table_id=table.table_id,
            page_num=table.page_num,
            review_required=True,
            concerns=["missing_table_positioned_evidence"],
        )
    evidence = TablePositionedEvidence.model_validate(raw_evidence)
    table_bbox = evidence.canonical_bbox
    if table_bbox is None:
        return TableBoundaryProposal(
            table_id=table.table_id,
            page_num=table.page_num,
            review_required=True,
            concerns=["missing_canonical_table_bbox"],
        )

    dx = 0.0
    dy = 0.0
    geometry_frame = str(table.metadata.get("geometry_coordinate_frame") or "")
    if geometry_frame == "table_local_rotated_normalized":
        old_source_bbox = table.metadata.get("geometry_transform_source_bbox")
        new_source_bbox = (
            evidence.canonical_transform.source_bbox
            if evidence.canonical_transform is not None
            else None
        )
        if (
            isinstance(old_source_bbox, (list, tuple))
            and len(old_source_bbox) == 4
            and new_source_bbox is not None
        ):
            old_left, old_top, old_right, old_bottom = (
                float(value) for value in old_source_bbox
            )
            new_left, new_top, new_right, new_bottom = new_source_bbox
            if evidence.rotation_direction == "vertical_text_up":
                dx = new_bottom - old_bottom
                dy = old_left - new_left
            elif evidence.rotation_direction == "vertical_text_down":
                dx = old_top - new_top
                dy = new_right - old_right
        else:
            diagnostics.append("missing_rotated_row_geometry_transform")
    elif geometry_frame != "page":
        diagnostics.append("unsupported_row_geometry_frame")

    raw_row_bounds = table.metadata.get("row_bounds")
    row_y_bounds: list[tuple[float, float] | None] = [None] * table.n_rows
    if isinstance(raw_row_bounds, list) and len(raw_row_bounds) == table.n_rows:
        for row_idx, item in enumerate(raw_row_bounds):
            if isinstance(item, (list, tuple)) and len(item) == 2:
                row_y_bounds[row_idx] = (float(item[0]) + dy, float(item[1]) + dy)

    grid = [["" for _ in range(table.n_cols)] for _ in range(table.n_rows)]
    positioned_columns_by_row: dict[int, set[int]] = {}
    cell_bboxes_by_row: dict[int, list[tuple[int, tuple[float, float, float, float]]]] = {}
    for cell in table.cells:
        if cell.row_idx < table.n_rows and cell.col_idx < table.n_cols:
            grid[cell.row_idx][cell.col_idx] = cell.text
        if cell.bbox is None or cell.row_idx >= table.n_rows:
            continue
        if cell.text.strip():
            positioned_columns_by_row.setdefault(cell.row_idx, set()).add(cell.col_idx)
        canonical_cell_bbox = (
            float(cell.bbox[0]) + dx,
            float(cell.bbox[1]) + dy,
            float(cell.bbox[2]) + dx,
            float(cell.bbox[3]) + dy,
        )
        cell_bboxes_by_row.setdefault(cell.row_idx, []).append(
            (cell.col_idx, canonical_cell_bbox)
        )
        if row_y_bounds[cell.row_idx] is None:
            row_y_bounds[cell.row_idx] = (
                canonical_cell_bbox[1],
                canonical_cell_bbox[3],
            )

    line_bbox_by_id = dict(
        zip(evidence.line_ids, evidence.canonical_line_bboxes, strict=False)
    )
    source_line_by_id = {
        line.line_id: line
        for line in (positioned_page.lines if positioned_page is not None else [])
    }
    row_styles: dict[int, set[tuple[str, float]]] = {}
    for row_idx, y_bounds in enumerate(row_y_bounds):
        if y_bounds is None:
            continue
        row_center = (y_bounds[0] + y_bounds[1]) / 2.0
        source_line_ids = [
            line_id
            for line_id, line_bbox in line_bbox_by_id.items()
            if line_bbox[1] - 1.0 <= row_center <= line_bbox[3] + 1.0
        ]
        styles = {
            (
                str(source_line_by_id[line_id].dominant_font or ""),
                round(float(source_line_by_id[line_id].dominant_font_size or 0.0), 1),
            )
            for line_id in source_line_ids
            if line_id in source_line_by_id
        }
        row_styles[row_idx] = styles
    if any(bounds is None for bounds in row_y_bounds):
        concerns.append("incomplete_canonical_row_geometry")

    value_left_candidates = [
        bbox[0]
        for row_cells in cell_bboxes_by_row.values()
        for col_idx, bbox in row_cells
        if col_idx > 0
    ]
    value_left = min(value_left_candidates) if value_left_candidates else None
    stub_band = (
        (table_bbox[0], value_left)
        if table_bbox is not None
        and value_left is not None
        and value_left > table_bbox[0]
        else None
    )
    value_band = (
        (value_left, table_bbox[2])
        if table_bbox is not None
        and value_left is not None
        and value_left < table_bbox[2]
        else None
    )

    char_heights = [
        bbox[3] - bbox[1]
        for bbox in evidence.canonical_char_bboxes
        if bbox[3] > bbox[1]
    ]
    rule_tolerance = max(0.5, median(char_heights) * 0.2) if char_heights else 1.0
    horizontal_records: list[
        tuple[float, TableBoundaryRuleReference]
    ] = []
    for source, indices, segments in (
        (
            "rule_segment",
            evidence.rule_segment_indices,
            evidence.canonical_rule_segments,
        ),
        (
            "stroked_rule_segment",
            evidence.stroked_rule_segment_indices,
            evidence.canonical_stroked_rule_segments,
        ),
    ):
        for source_index, segment in zip(indices, segments, strict=False):
            x0, y0, x1, y1 = segment
            if abs(y1 - y0) > rule_tolerance or abs(x1 - x0) <= 2.0 * rule_tolerance:
                continue
            horizontal_records.append(
                (
                    (y0 + y1) / 2.0,
                    TableBoundaryRuleReference(
                        source=source,
                        source_index=source_index,
                        canonical_segment=segment,
                    ),
                )
            )

    rule_clusters: list[list[tuple[float, TableBoundaryRuleReference]]] = []
    for record in sorted(horizontal_records, key=lambda item: item[0]):
        if (
            not rule_clusters
            or record[0] - median(item[0] for item in rule_clusters[-1]) > rule_tolerance
        ):
            rule_clusters.append([record])
        else:
            rule_clusters[-1].append(record)

    row_centers = {
        row_idx: (bounds[0] + bounds[1]) / 2.0
        for row_idx, bounds in enumerate(row_y_bounds)
        if bounds is not None
    }
    canonical_text_lines = sorted(
        (
            (line, line.canonical_bbox)
            for line in text_lines
            if line.canonical_bbox is not None
            and (
                evidence.orientation_group_id is None
                or line.orientation_group_id == evidence.orientation_group_id
            )
        ),
        key=lambda item: (item[1][1], item[1][0]),
    )
    line_start_gap = max(8.0, median(char_heights) * 1.5) if char_heights else 8.0
    line_continuation_gap = max(8.0, median(char_heights)) if char_heights else 8.0
    boundary_candidates: list[TableBoundaryCandidate] = []
    for cluster in rule_clusters:
        canonical_y = median(item[0] for item in cluster)
        rows_before = [row_idx for row_idx, center in row_centers.items() if center < canonical_y]
        rows_after = [row_idx for row_idx, center in row_centers.items() if center > canonical_y]
        row_before_idx = max(rows_before, default=None)
        row_after_idx = min(rows_after, default=None)
        segments = [item[1].canonical_segment for item in cluster]
        table_coverage = _coverage_fraction(segments, table_bbox)
        stub_coverage = _coverage_fraction(segments, stub_band)
        value_coverage = _coverage_fraction(segments, value_band)
        scope_coverages = [
            coverage
            for coverage in (stub_coverage, value_coverage)
            if coverage is not None
        ]
        if max(scope_coverages or [table_coverage]) < 0.8:
            continue
        font_change = None
        before_styles = (
            row_styles.get(row_before_idx, set())
            if row_before_idx is not None
            else set()
        )
        if row_after_idx is not None:
            after_styles = row_styles.get(row_after_idx, set())
            if before_styles and after_styles:
                font_change = before_styles != after_styles
        following_lines: list[tuple[PaperTextLine, tuple[float, float, float, float]]] = []
        rows_after_grid = grid[row_after_idx:] if row_after_idx is not None else []
        body_resumes = any(_is_value_matrix_row(row) for row in rows_after_grid)
        sparse_value_follows = bool(
            rows_after_grid and _value_like_count(rows_after_grid[0][1:]) > 0
        )
        if body_text_style is not None and not sparse_value_follows:
            structural_boundary_y = min(
                (
                    bbox[1]
                    for line, bbox in canonical_text_lines
                    if line.role == "heading"
                    and bbox[1] > canonical_y
                    and max(
                        0.0,
                        min(bbox[2], table_bbox[2])
                        - max(bbox[0], table_bbox[0]),
                    )
                    / max(bbox[2] - bbox[0], 1.0)
                    >= 0.25
                ),
                default=None,
            )
            lower_boundary_y = min(
                (
                    boundary_y
                    for boundary_y in (
                        next_table_start_y,
                        structural_boundary_y,
                        (
                            evidence.canonical_caption_bbox[1]
                            if evidence.canonical_caption_bbox is not None
                            and evidence.canonical_caption_bbox[1] > canonical_y
                            else None
                        ),
                    )
                    if boundary_y is not None and boundary_y > canonical_y
                ),
                default=None,
            )
            following_style: tuple[str, float] | None = None
            following_bottom: float | None = None
            for line, bbox in canonical_text_lines:
                if (bbox[1] + bbox[3]) / 2.0 <= canonical_y:
                    continue
                if lower_boundary_y is not None and bbox[1] >= lower_boundary_y - rule_tolerance:
                    break
                overlap = max(
                    0.0,
                    min(bbox[2], table_bbox[2]) - max(bbox[0], table_bbox[0]),
                )
                if overlap / max(bbox[2] - bbox[0], 1.0) < 0.25:
                    continue
                if line.dominant_font is None or line.dominant_font_size is None:
                    break
                line_style = (
                    line.dominant_font,
                    round(float(line.dominant_font_size), 1),
                )
                if not following_lines:
                    if bbox[1] - canonical_y > line_start_gap or line_style == body_text_style:
                        break
                    following_lines.append((line, bbox))
                    following_style = line_style
                    following_bottom = bbox[3]
                    continue
                if (
                    following_bottom is None
                    or bbox[1] > following_bottom + line_continuation_gap
                    or line_style != following_style
                ):
                    break
                following_lines.append((line, bbox))
                following_bottom = max(following_bottom, bbox[3])
        following_sizes = [
            round(float(line.dominant_font_size or 0.0), 1)
            for line, _ in following_lines
        ]
        smaller_than_before = bool(
            before_styles
            and following_sizes
            and max(following_sizes) < min(size for _, size in before_styles)
        )
        if body_resumes and not (
            font_change is True
            and len(following_lines) >= 2
            and smaller_than_before
        ):
            following_lines = []
        following_bbox = (
            (
                min(bbox[0] for _, bbox in following_lines),
                min(bbox[1] for _, bbox in following_lines),
                max(bbox[2] for _, bbox in following_lines),
                max(bbox[3] for _, bbox in following_lines),
            )
            if following_lines
            else None
        )
        boundary_candidates.append(
            TableBoundaryCandidate(
                canonical_y=canonical_y,
                row_before_idx=row_before_idx,
                row_after_idx=row_after_idx,
                rule_references=[item[1] for item in cluster],
                table_coverage_fraction=table_coverage,
                stub_coverage_fraction=stub_coverage,
                value_coverage_fraction=value_coverage,
                immediate_font_style_change=font_change,
                following_text_line_ids=[line.line_id for line, _ in following_lines],
                following_text_bbox=following_bbox,
                following_text_styles=list(
                    dict.fromkeys(
                        (
                            line.dominant_font or "",
                            round(float(line.dominant_font_size or 0.0), 1),
                        )
                        for line, _ in following_lines
                    )
                ),
            )
        )

    if len(boundary_candidates) > 3:
        retained_indices = {0, 1, len(boundary_candidates) - 1}
        for index, candidate in enumerate(boundary_candidates[1:-1], start=1):
            current_scope = (
                candidate.stub_coverage_fraction or 0.0,
                candidate.value_coverage_fraction or 0.0,
            )
            neighboring_scopes = [
                (
                    neighbor.stub_coverage_fraction or 0.0,
                    neighbor.value_coverage_fraction or 0.0,
                )
                for neighbor in (
                    boundary_candidates[index - 1],
                    boundary_candidates[index + 1],
                )
            ]
            if candidate.following_text_line_ids or candidate.immediate_font_style_change is True or any(
                max(abs(left - right) for left, right in zip(current_scope, scope))
                > 0.05
                for scope in neighboring_scopes
            ):
                retained_indices.add(index)
        boundary_candidates = [
            candidate
            for index, candidate in enumerate(boundary_candidates)
            if index in retained_indices
        ]

    if boundary_candidates:
        for candidate in boundary_candidates[:-1]:
            candidate.following_text_line_ids = []
            candidate.following_text_bbox = None
            candidate.following_text_styles = []
        first_candidate = boundary_candidates[0]
        first_candidate.possible_roles = ["table_start"]
        if first_candidate.row_before_idx is not None:
            first_candidate.possible_roles.append("header_body")
        for candidate in boundary_candidates[1:]:
            candidate.possible_roles = []
            if candidate.row_after_idx is None:
                candidate.possible_roles.append("table_end")
            else:
                candidate.possible_roles.append("header_body")
            if candidate.following_text_line_ids:
                candidate.possible_roles.append("body_footer")
    header_body_candidates = [
        candidate for candidate in boundary_candidates if "header_body" in candidate.possible_roles
    ]
    if not boundary_candidates:
        concerns.append("no_horizontal_rule_candidates")
    if not header_body_candidates:
        concerns.append("no_header_body_candidate")
    elif len(header_body_candidates) > 1:
        concerns.append("multiple_header_body_candidates")
    positioned_rows_by_column: dict[int, set[int]] = {}
    for row_idx, column_indices in positioned_columns_by_row.items():
        for col_idx in column_indices:
            positioned_rows_by_column.setdefault(col_idx, set()).add(row_idx)
    coherent_positioned_grid = bool(
        table.n_rows >= 2
        and table.n_cols >= 2
        and all(bounds is not None for bounds in row_y_bounds)
        and sum(len(column_indices) >= 2 for column_indices in positioned_columns_by_row.values()) >= 2
        and sum(len(row_indices) >= 2 for row_indices in positioned_rows_by_column.values()) >= 2
    )
    credible_rule_geometry = bool(boundary_candidates)
    if not credible_rule_geometry and not coherent_positioned_grid:
        concerns.append("no_credible_rules_or_coherent_positioned_grid")

    caption_bbox = evidence.canonical_caption_bbox
    if table.caption and caption_bbox is None:
        concerns.append("caption_missing_from_canonical_geometry")

    return TableBoundaryProposal(
        table_id=table.table_id,
        page_num=table.page_num,
        canonical_table_bbox=table_bbox,
        canonical_caption_bbox=caption_bbox,
        canonical_stub_band=stub_band,
        canonical_value_band=value_band,
        canonical_row_bounds=[
            bounds for bounds in row_y_bounds if bounds is not None
        ],
        boundary_candidates=boundary_candidates,
        credible_rule_geometry=credible_rule_geometry,
        coherent_positioned_grid=coherent_positioned_grid,
        review_required=bool(concerns or diagnostics),
        concerns=list(dict.fromkeys(concerns)),
        diagnostics=list(dict.fromkeys(diagnostics)),
    )


def table_boundary_proposals_to_payload(
    proposals: Sequence[TableBoundaryProposal],
) -> list[dict[str, object]]:
    """Serialize boundary proposals as JSON-ready dictionaries."""
    return [proposal.model_dump(mode="json") for proposal in proposals]


def _coverage_fraction(
    segments: Sequence[tuple[float, float, float, float]],
    band: tuple[float, ...] | None,
) -> float | None:
    if band is None:
        return None
    left = float(band[0])
    right = float(band[2] if len(band) == 4 else band[1])
    width = right - left
    if width <= 0.0:
        return None
    intervals = sorted(
        (
            max(left, min(segment[0], segment[2])),
            min(right, max(segment[0], segment[2])),
        )
        for segment in segments
        if min(right, max(segment[0], segment[2]))
        > max(left, min(segment[0], segment[2]))
    )
    covered = 0.0
    current: tuple[float, float] | None = None
    for interval in intervals:
        if current is None:
            current = interval
        elif interval[0] <= current[1]:
            current = (current[0], max(current[1], interval[1]))
        else:
            covered += current[1] - current[0]
            current = interval
    if current is not None:
        covered += current[1] - current[0]
    return min(1.0, max(0.0, covered / width))
