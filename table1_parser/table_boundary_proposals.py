"""Build provisional table-boundary evidence in canonical geometry."""

from __future__ import annotations

from collections.abc import Sequence
from statistics import median

from table1_parser.schemas import (
    ExtractedTable,
    PaperPositionedDocument,
    PaperPositionedPage,
    TableBoundaryCandidate,
    TableBoundaryProposal,
    TableBoundaryRuleReference,
    TablePositionedEvidence,
)


def build_table_boundary_proposals(
    extracted_tables: Sequence[ExtractedTable],
    *,
    paper_positioned_document: PaperPositionedDocument | None,
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
    return [
        build_table_boundary_proposal(
            table,
            positioned_page=pages_by_num.get(table.page_num),
        )
        for table in extracted_tables
    ]


def build_table_boundary_proposal(
    table: ExtractedTable,
    *,
    positioned_page: PaperPositionedPage | None,
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
    table_bbox = evidence.canonical_candidate_bbox or evidence.canonical_bbox
    if table_bbox is None:
        return TableBoundaryProposal(
            table_id=table.table_id,
            page_num=table.page_num,
            review_required=True,
            concerns=["missing_canonical_table_bbox"],
        )

    raw_row_bounds = table.metadata.get("row_bounds")
    row_y_bounds: list[tuple[float, float] | None] = [None] * table.n_rows
    if isinstance(raw_row_bounds, list) and len(raw_row_bounds) == table.n_rows:
        for row_idx, item in enumerate(raw_row_bounds):
            if isinstance(item, (list, tuple)) and len(item) == 2:
                row_y_bounds[row_idx] = (float(item[0]), float(item[1]))

    positioned_columns_by_row: dict[int, set[int]] = {}
    cell_bboxes_by_row: dict[
        int, list[tuple[int, tuple[float, float, float, float]]]
    ] = {}
    for cell in table.cells:
        if cell.bbox is None or cell.row_idx >= table.n_rows:
            continue
        if cell.text.strip():
            positioned_columns_by_row.setdefault(cell.row_idx, set()).add(cell.col_idx)
        canonical_cell_bbox = (
            float(cell.bbox[0]),
            float(cell.bbox[1]),
            float(cell.bbox[2]),
            float(cell.bbox[3]),
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
    horizontal_records: list[tuple[float, TableBoundaryRuleReference]] = []
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
            or record[0] - median(item[0] for item in rule_clusters[-1])
            > rule_tolerance
        ):
            rule_clusters.append([record])
        else:
            rule_clusters[-1].append(record)

    row_centers = {
        row_idx: (bounds[0] + bounds[1]) / 2.0
        for row_idx, bounds in enumerate(row_y_bounds)
        if bounds is not None
    }
    boundary_candidates: list[TableBoundaryCandidate] = []
    for cluster in rule_clusters:
        canonical_y = median(item[0] for item in cluster)
        rows_before = [
            row_idx for row_idx, center in row_centers.items() if center < canonical_y
        ]
        rows_after = [
            row_idx for row_idx, center in row_centers.items() if center > canonical_y
        ]
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
            if (
                candidate.immediate_font_style_change is True
                or any(
                    max(abs(left - right) for left, right in zip(current_scope, scope))
                    > 0.05
                    for scope in neighboring_scopes
                )
            ):
                retained_indices.add(index)
        boundary_candidates = [
            candidate
            for index, candidate in enumerate(boundary_candidates)
            if index in retained_indices
        ]

    if boundary_candidates:
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
    header_body_candidates = [
        candidate
        for candidate in boundary_candidates
        if "header_body" in candidate.possible_roles
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
        and sum(
            len(column_indices) >= 2
            for column_indices in positioned_columns_by_row.values()
        )
        >= 2
        and sum(
            len(row_indices) >= 2 for row_indices in positioned_rows_by_column.values()
        )
        >= 2
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
        canonical_row_bounds=[bounds for bounds in row_y_bounds if bounds is not None],
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
