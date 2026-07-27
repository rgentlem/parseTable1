"""Build raw body-character occupancy in canonical table geometry."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from math import ceil, floor
from statistics import median
from typing import Literal

from table1_parser.schemas import (
    BodyOccupancyGap,
    BodyOccupancyLine,
    BodyOccupancyTable,
    CellTextAnnotationTable,
    ExtractedTable,
    PaperPositionedDocument,
    PaperPositionedPage,
    TableBoundaryProposal,
    TableCell,
    TableRegion,
)


def collect_paper_space_widths_by_style(
    paper_positioned_document: PaperPositionedDocument,
) -> dict[tuple[str, float], list[float]]:
    """Collect observed space advances by font and size from positioned text."""
    widths_by_style: dict[tuple[str, float], list[float]] = {}
    for page in paper_positioned_document.pages:
        line_by_position = {
            (line.block_index, line.line_index): line
            for line in page.lines
            if line.block_index is not None and line.line_index is not None
        }
        for char in page.chars:
            if not char.text.isspace() or char.font is None or char.font_size is None:
                continue
            line = line_by_position.get((char.block_index, char.line_index))
            direction = line.direction if line is not None else None
            if direction is not None and abs(direction[1]) > abs(direction[0]):
                width = char.bottom - char.top
            else:
                width = char.x1 - char.x0
            if width > 0.0:
                widths_by_style.setdefault(
                    (char.font, round(char.font_size, 3)),
                    [],
                ).append(width)
    return widths_by_style


def build_body_occupancy_tables(
    extracted_tables: Sequence[ExtractedTable],
    *,
    paper_positioned_document: PaperPositionedDocument,
    table_regions: Sequence[TableRegion],
    table_boundary_proposals: Sequence[TableBoundaryProposal],
    cell_text_annotations: Sequence[CellTextAnnotationTable],
) -> list[BodyOccupancyTable]:
    """Build one raw occupancy record per extracted table."""
    paper_space_widths_by_style = collect_paper_space_widths_by_style(
        paper_positioned_document
    )
    pages_by_num = {page.page_num: page for page in paper_positioned_document.pages}
    regions_by_table_id = {region.table_id: region for region in table_regions}
    proposals_by_table_id = {
        proposal.table_id: proposal for proposal in table_boundary_proposals
    }
    annotations_by_table_id = {
        annotation_table.table_id: annotation_table
        for annotation_table in cell_text_annotations
    }
    return [
        build_body_occupancy_table(
            table,
            positioned_page=pages_by_num.get(table.page_num),
            body_row_indices=(
                regions_by_table_id[table.table_id].body_rows
                if table.table_id in regions_by_table_id
                else []
            ),
            table_region_missing=table.table_id not in regions_by_table_id,
            table_boundary_proposal=proposals_by_table_id.get(table.table_id),
            annotation_table=annotations_by_table_id.get(table.table_id),
            paper_space_widths_by_style=paper_space_widths_by_style,
        )
        for table in extracted_tables
    ]


def build_body_occupancy_table(
    table: ExtractedTable,
    *,
    positioned_page: PaperPositionedPage | None,
    body_row_indices: Sequence[int],
    table_boundary_proposal: TableBoundaryProposal | None,
    annotation_table: CellTextAnnotationTable | None,
    paper_space_widths_by_style: Mapping[tuple[str, float], Sequence[float]],
    table_region_missing: bool = False,
) -> BodyOccupancyTable:
    """Build raw physical-line occupancy for one table body."""
    diagnostics: list[str] = []
    source_artifacts = [
        "paper_positioned_document.json",
        "table_boundary_proposals.json",
        "table_regions.json",
        "cell_text_annotations.json",
    ]
    body_row_indices = list(body_row_indices)
    if table_region_missing:
        diagnostics.append("table_region_missing")
    if not body_row_indices:
        diagnostics.append("body_rows_missing")
    if table_boundary_proposal is None:
        diagnostics.append("table_boundary_proposal_missing")
    if positioned_page is None:
        diagnostics.append("positioned_page_missing")
    if (
        diagnostics
        or table_boundary_proposal is None
        or positioned_page is None
    ):
        return BodyOccupancyTable(
            table_id=table.table_id,
            page_num=table.page_num,
            source_artifacts=source_artifacts,
            body_row_indices=body_row_indices,
            diagnostics=diagnostics,
        )

    evidence = table.positioned_evidence
    table_bbox = table_boundary_proposal.canonical_table_bbox
    if table_bbox is None:
        diagnostics.append("canonical_table_bbox_missing")
    if len(table_boundary_proposal.canonical_row_bounds) != table.n_rows:
        diagnostics.append("canonical_row_bounds_incomplete")
    if diagnostics or table_bbox is None:
        return BodyOccupancyTable(
            table_id=table.table_id,
            page_num=table.page_num,
            source_artifacts=source_artifacts,
            body_row_indices=body_row_indices,
            x_min=table_bbox[0] if table_bbox is not None else None,
            x_max=table_bbox[2] if table_bbox is not None else None,
            diagnostics=diagnostics,
        )

    body_bounds = [
        (row_idx, table_boundary_proposal.canonical_row_bounds[row_idx])
        for row_idx in body_row_indices
        if 0 <= row_idx < len(table_boundary_proposal.canonical_row_bounds)
    ]
    marker_ids_by_char_index: dict[int, set[str]] = {}
    marker_rows_by_char_index: dict[int, set[int]] = {}
    unlinked_marker_ids: list[str] = []
    body_row_set = set(body_row_indices)
    for annotation_index, annotation in enumerate(
        annotation_table.annotations if annotation_table is not None else []
    ):
        if annotation.row_idx not in body_row_set:
            continue
        marker_id = (
            annotation.annotation_id or f"{table.table_id}:marker:{annotation_index}"
        )
        if not annotation.source_char_indices:
            unlinked_marker_ids.append(marker_id)
            continue
        for char_index in annotation.source_char_indices:
            marker_ids_by_char_index.setdefault(char_index, set()).add(marker_id)
            marker_rows_by_char_index.setdefault(char_index, set()).add(
                annotation.row_idx
            )

    page_chars_by_index = {char.char_index: char for char in positioned_page.chars}
    source_line_id_by_position = {
        (line.block_index, line.line_index): line.line_id
        for line in positioned_page.lines
        if line.block_index is not None and line.line_index is not None
    }
    evidence_char_indices = set(evidence.char_indices)
    linked_marker_indices = set(marker_ids_by_char_index)
    if linked_marker_indices - evidence_char_indices:
        diagnostics.append("linked_marker_chars_outside_table_evidence")
    ordinary_char_records: list[
        tuple[
            int,
            tuple[float, float, float, float],
            int,
            str | None,
        ]
    ] = []
    excluded_marker_records: list[
        tuple[
            int,
            tuple[float, float, float, float],
            set[int],
            set[str],
        ]
    ] = []
    for char_index, bbox in zip(
        evidence.char_indices,
        evidence.canonical_char_bboxes,
        strict=False,
    ):
        source_char = page_chars_by_index.get(char_index)
        if source_char is None or not source_char.text.strip():
            continue
        marker_ids = marker_ids_by_char_index.get(char_index)
        if marker_ids:
            excluded_marker_records.append(
                (
                    char_index,
                    bbox,
                    marker_rows_by_char_index.get(char_index, set()),
                    marker_ids,
                )
            )
            continue
        char_center = (bbox[1] + bbox[3]) / 2.0
        candidate_rows = [
            (row_idx, bounds)
            for row_idx, bounds in body_bounds
            if bounds[0] - 1.0 <= char_center <= bounds[1] + 1.0
        ]
        if not candidate_rows or bbox[2] <= bbox[0]:
            continue
        source_row_idx = min(
            candidate_rows,
            key=lambda item: abs(char_center - (item[1][0] + item[1][1]) / 2.0),
        )[0]
        source_line_id = source_line_id_by_position.get(
            (source_char.block_index, source_char.line_index)
        )
        ordinary_char_records.append((char_index, bbox, source_row_idx, source_line_id))

    ordinary_char_records.sort(
        key=lambda item: (
            (item[1][1] + item[1][3]) / 2.0,
            item[1][0],
            item[0],
        )
    )
    character_line_groups: list[
        list[
            tuple[
                int,
                tuple[float, float, float, float],
                int,
                str | None,
            ]
        ]
    ] = []
    for char_record in ordinary_char_records:
        if not character_line_groups:
            character_line_groups.append([char_record])
            continue
        current_group = character_line_groups[-1]
        group_center = median((item[1][1] + item[1][3]) / 2.0 for item in current_group)
        group_height = median(item[1][3] - item[1][1] for item in current_group)
        char_center = (char_record[1][1] + char_record[1][3]) / 2.0
        char_height = char_record[1][3] - char_record[1][1]
        if abs(char_center - group_center) <= 0.25 * min(
            group_height,
            char_height,
        ):
            current_group.append(char_record)
        else:
            character_line_groups.append([char_record])

    selected_lines: list[
        tuple[
            str,
            tuple[float, float, float, float],
            list[int],
            list[str],
        ]
    ] = []
    ordinary_chars_by_line: dict[
        str,
        list[tuple[int, tuple[float, float, float, float]]],
    ] = {}
    for line_index, group in enumerate(character_line_groups):
        line_id = f"{table.table_id}:body_occupancy:line:{line_index}"
        ordinary_chars_by_line[line_id] = [
            (char_index, bbox) for char_index, bbox, _, _ in group
        ]
        selected_lines.append(
            (
                line_id,
                (
                    min(bbox[0] for _, bbox, _, _ in group),
                    min(bbox[1] for _, bbox, _, _ in group),
                    max(bbox[2] for _, bbox, _, _ in group),
                    max(bbox[3] for _, bbox, _, _ in group),
                ),
                sorted({row_idx for _, _, row_idx, _ in group}),
                sorted(
                    {
                        source_line_id
                        for _, _, _, source_line_id in group
                        if source_line_id is not None
                    }
                ),
            )
        )

    excluded_char_indices_by_line: dict[str, list[int]] = {
        line_id: [] for line_id, _, _, _ in selected_lines
    }
    excluded_marker_ids_by_line: dict[str, set[str]] = {
        line_id: set() for line_id, _, _, _ in selected_lines
    }
    excluded_marker_ids: set[str] = set()
    for char_index, bbox, source_rows, marker_ids in excluded_marker_records:
        excluded_marker_ids.update(marker_ids)
        marker_center = (bbox[1] + bbox[3]) / 2.0
        candidate_lines = [
            line for line in selected_lines if source_rows.intersection(line[2])
        ]
        if not candidate_lines:
            diagnostics.append("linked_marker_without_body_line")
            continue
        line_id = min(
            candidate_lines,
            key=lambda line: abs(marker_center - (line[1][1] + line[1][3]) / 2.0),
        )[0]
        excluded_char_indices_by_line[line_id].append(char_index)
        excluded_marker_ids_by_line[line_id].update(marker_ids)

    ordinary_widths = [
        bbox[2] - bbox[0]
        for chars in ordinary_chars_by_line.values()
        for _, bbox in chars
        if bbox[2] > bbox[0]
    ]
    if not ordinary_widths:
        diagnostics.append("ordinary_body_characters_missing")
        return BodyOccupancyTable(
            table_id=table.table_id,
            page_num=table.page_num,
            source_artifacts=source_artifacts,
            body_row_indices=body_row_indices,
            x_min=table_bbox[0],
            x_max=table_bbox[2],
            excluded_marker_ids=sorted(excluded_marker_ids),
            unlinked_marker_ids=sorted(set(unlinked_marker_ids)),
            diagnostics=list(dict.fromkeys(diagnostics)),
        )

    x_min = table_bbox[0]
    x_max = table_bbox[2]
    bin_width = median(ordinary_widths)
    bin_count = ceil((x_max - x_min) / bin_width)
    occupancy_matrix: list[list[Literal[0, 1]]] = []
    lines: list[BodyOccupancyLine] = []
    for line_id, line_bbox, source_rows, source_line_ids in selected_lines:
        occupancy: list[Literal[0, 1]] = [0] * bin_count
        for _, bbox in ordinary_chars_by_line[line_id]:
            clipped_left = max(x_min, bbox[0])
            clipped_right = min(x_max, bbox[2])
            if clipped_right <= clipped_left:
                continue
            start_bin = max(0, floor((clipped_left - x_min) / bin_width))
            end_bin = min(
                bin_count - 1,
                ceil((clipped_right - x_min) / bin_width) - 1,
            )
            for bin_idx in range(start_bin, end_bin + 1):
                occupancy[bin_idx] = 1
        line_marker_ids = sorted(excluded_marker_ids_by_line[line_id])
        excluded_marker_ids.update(line_marker_ids)
        lines.append(
            BodyOccupancyLine(
                line_id=line_id,
                source_line_ids=source_line_ids,
                source_row_indices=source_rows,
                canonical_bbox=line_bbox,
                ordinary_character_count=len(ordinary_chars_by_line[line_id]),
                excluded_marker_ids=line_marker_ids,
                excluded_marker_char_indices=sorted(
                    excluded_char_indices_by_line[line_id]
                ),
            )
        )
        occupancy_matrix.append(occupancy)

    occupied_line_counts = [
        sum(row[bin_idx] for row in occupancy_matrix) for bin_idx in range(bin_count)
    ]
    line_count = len(occupancy_matrix)
    style_counts = Counter(
        (
            page_chars_by_index[char_index].font,
            round(page_chars_by_index[char_index].font_size, 3),
        )
        for char_index, _, _, _ in ordinary_char_records
        if page_chars_by_index[char_index].font is not None
        and page_chars_by_index[char_index].font_size is not None
    )
    dominant_style = style_counts.most_common(1)[0][0] if style_counts else None
    table_space_widths: list[float] = []
    if dominant_style is not None:
        for char_index, bbox in zip(
            evidence.char_indices,
            evidence.canonical_char_bboxes,
            strict=False,
        ):
            source_char = page_chars_by_index.get(char_index)
            if (
                source_char is not None
                and source_char.text.isspace()
                and source_char.font == dominant_style[0]
                and source_char.font_size is not None
                and round(source_char.font_size, 3) == dominant_style[1]
                and bbox[2] > bbox[0]
            ):
                table_space_widths.append(bbox[2] - bbox[0])
    if table_space_widths:
        space_widths = table_space_widths
        space_width_source: Literal["table_evidence", "paper_font_style"] | None = (
            "table_evidence"
        )
    elif dominant_style is not None:
        space_widths = list(paper_space_widths_by_style.get(dominant_style, []))
        space_width_source = "paper_font_style" if space_widths else None
    else:
        space_widths = []
        space_width_source = None

    qualified_zero_gaps: list[BodyOccupancyGap] = []
    median_space_width: float | None = None
    minimum_separator_gap_width: float | None = None
    if not space_widths:
        diagnostics.append("dominant_body_font_space_width_missing")
    else:
        median_space_width = median(space_widths)
        minimum_separator_gap_width = 2.0 * median_space_width
        character_intervals = sorted(
            (
                max(x_min, bbox[0]),
                min(x_max, bbox[2]),
            )
            for chars in ordinary_chars_by_line.values()
            for _, bbox in chars
            if min(x_max, bbox[2]) > max(x_min, bbox[0])
        )
        merged_intervals: list[list[float]] = []
        for interval_left, interval_right in character_intervals:
            if not merged_intervals or interval_left > merged_intervals[-1][1]:
                merged_intervals.append([interval_left, interval_right])
            elif interval_right > merged_intervals[-1][1]:
                merged_intervals[-1][1] = interval_right
        for left_interval, right_interval in zip(
            merged_intervals,
            merged_intervals[1:],
            strict=False,
        ):
            gap_left = left_interval[1]
            gap_right = right_interval[0]
            gap_width = gap_right - gap_left
            if gap_width >= minimum_separator_gap_width:
                qualified_zero_gaps.append(
                    BodyOccupancyGap(
                        canonical_x_bounds=(gap_left, gap_right),
                        width=gap_width,
                    )
                )
        nonempty_source_columns = sorted(
            {
                cell.col_idx
                for cell in table.cells
                if cell.row_idx in body_row_set and cell.text.strip()
            }
        )
        if (
            qualified_zero_gaps
            and nonempty_source_columns
            and nonempty_source_columns == list(
                range(nonempty_source_columns[0], nonempty_source_columns[-1] + 1)
            )
            and len(qualified_zero_gaps) + 2 == len(nonempty_source_columns)
        ):
            stub_col_idx = nonempty_source_columns[0]
            last_col_idx = nonempty_source_columns[-1]
            cells_by_row: dict[int, dict[int, TableCell]] = {}
            for cell in table.cells:
                if cell.row_idx in body_row_set:
                    cells_by_row.setdefault(cell.row_idx, {})[cell.col_idx] = cell
            first_data_lefts: list[float] = []
            for cells_by_col in cells_by_row.values():
                first_data_cell = cells_by_col.get(stub_col_idx + 1)
                if (
                    first_data_cell is None
                    or not first_data_cell.text.strip()
                    or first_data_cell.bbox is None
                ):
                    continue
                stub_cell = cells_by_col.get(stub_col_idx)
                stub_bbox = stub_cell.bbox if stub_cell is not None else None
                has_later_data = any(
                    (cell := cells_by_col.get(col_idx)) is not None
                    and cell.text.strip()
                    for col_idx in range(stub_col_idx + 2, last_col_idx + 1)
                )
                if has_later_data or (
                    stub_bbox is not None
                    and first_data_cell.bbox[0] - stub_bbox[2]
                    >= minimum_separator_gap_width
                ):
                    first_data_lefts.append(first_data_cell.bbox[0])
            first_data_occupancy_x = min(first_data_lefts, default=None)
            long_sparse_rows: set[int] = set()
            if first_data_occupancy_x is not None:
                for row_idx in body_row_indices:
                    cells_by_col = cells_by_row.get(row_idx, {})
                    populated_ordinary_columns = [
                        col_idx
                        for col_idx in range(stub_col_idx + 1, last_col_idx)
                        if (
                            (cell := cells_by_col.get(col_idx)) is not None
                            and cell.text.strip()
                        )
                    ]
                    stub_cell = cells_by_col.get(stub_col_idx)
                    stub_bbox = stub_cell.bbox if stub_cell is not None else None
                    label_right = stub_bbox[2] if stub_bbox is not None else None
                    if populated_ordinary_columns == [stub_col_idx + 1]:
                        first_cell = cells_by_col.get(stub_col_idx + 1)
                        first_bbox = first_cell.bbox if first_cell is not None else None
                        if (
                            stub_bbox is not None
                            and first_bbox is not None
                            and first_bbox[0] - stub_bbox[2]
                            < minimum_separator_gap_width
                        ):
                            label_right = first_bbox[2]
                        else:
                            continue
                    elif populated_ordinary_columns:
                        continue
                    if (
                        label_right is not None
                        and label_right
                        >= first_data_occupancy_x - minimum_separator_gap_width
                    ):
                        long_sparse_rows.add(row_idx)
            if long_sparse_rows:
                filtered_intervals = sorted(
                    (
                        max(x_min, bbox[0]),
                        min(x_max, bbox[2]),
                    )
                    for _, bbox, row_idx, _ in ordinary_char_records
                    if (
                        row_idx not in long_sparse_rows
                        or bbox[0] >= first_data_occupancy_x
                    )
                    and min(x_max, bbox[2]) > max(x_min, bbox[0])
                )
                filtered_merged: list[list[float]] = []
                for interval_left, interval_right in filtered_intervals:
                    if (
                        not filtered_merged
                        or interval_left > filtered_merged[-1][1]
                    ):
                        filtered_merged.append([interval_left, interval_right])
                    elif interval_right > filtered_merged[-1][1]:
                        filtered_merged[-1][1] = interval_right
                preceding_gaps = [
                    (left[1], right[0])
                    for left, right in zip(
                        filtered_merged,
                        filtered_merged[1:],
                        strict=False,
                    )
                    if right[0] - left[1] >= minimum_separator_gap_width
                    and right[0] <= qualified_zero_gaps[0].canonical_x_bounds[0]
                ]
                if preceding_gaps:
                    gap_left, gap_right = max(
                        preceding_gaps,
                        key=lambda gap: gap[1],
                    )
                    qualified_zero_gaps.insert(
                        0,
                        BodyOccupancyGap(
                            canonical_x_bounds=(gap_left, gap_right),
                            width=gap_right - gap_left,
                        ),
                    )
    return BodyOccupancyTable(
        table_id=table.table_id,
        page_num=table.page_num,
        source_artifacts=source_artifacts,
        body_row_indices=body_row_indices,
        x_min=x_min,
        x_max=x_max,
        bin_width=bin_width,
        bin_count=bin_count,
        lines=lines,
        occupancy_matrix=occupancy_matrix,
        occupied_line_counts=occupied_line_counts,
        occupied_line_proportions=[
            count / line_count for count in occupied_line_counts
        ],
        dominant_body_font=dominant_style[0] if dominant_style else None,
        dominant_body_font_size=dominant_style[1] if dominant_style else None,
        median_body_space_width=median_space_width,
        space_width_source=space_width_source,
        minimum_separator_gap_width=minimum_separator_gap_width,
        qualified_zero_gaps=qualified_zero_gaps,
        excluded_marker_ids=sorted(excluded_marker_ids),
        unlinked_marker_ids=sorted(set(unlinked_marker_ids)),
        diagnostics=list(dict.fromkeys(diagnostics)),
    )


def body_occupancy_tables_to_payload(
    tables: Sequence[BodyOccupancyTable],
) -> list[dict[str, object]]:
    """Serialize body occupancy records as JSON-ready dictionaries."""
    return [table.model_dump(mode="json") for table in tables]
