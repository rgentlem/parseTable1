"""Classify row roles around the geometry-defined table body."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from table1_parser.context.paper_document import (
    iter_paper_discovery_lines,
)
from table1_parser.context.visual_references import VISUAL_OBJECT_DOI_PATTERN
from table1_parser.normalize.header_detector import detect_header_rows_with_metadata
from table1_parser.paper_discovery import PaperDiscoveryState
from table1_parser.schemas import (
    CellTextAnnotationTable,
    ExtractedTable,
    PaperPageFurniture,
    PaperPositionedDocument,
    PaperPositionedPage,
    TableBoundaryProposal,
    TablePositionedEvidence,
)
from table1_parser.schemas.table_region import TableRegion, TableRegionRow
from table1_parser.table1_continuations import CONTINUATION_PATTERN
from table1_parser.text_cleaning import clean_text


RULE_TOLERANCE = 3.0
CAPTION_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")
TABLE_CAPTION_PATTERN = re.compile(r"^\s*table\s*\d+\b", re.IGNORECASE)


def build_table_regions(
    extracted_tables: Sequence[ExtractedTable],
    *,
    paper_discovery: PaperDiscoveryState | None = None,
    paper_page_furniture: PaperPageFurniture | None = None,
    cell_text_annotations: Sequence[CellTextAnnotationTable] | None = None,
    table_boundary_proposals: Sequence[TableBoundaryProposal] | None = None,
    paper_positioned_document: PaperPositionedDocument | None = None,
) -> list[TableRegion]:
    """Build row-region decisions for extracted tables."""
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
    page_furniture_rule_bboxes_by_page: dict[
        int, list[tuple[float, float, float, float]]
    ] = {}
    for region in (
        paper_page_furniture.ignored_rule_regions
        if paper_page_furniture is not None
        else []
    ):
        page_furniture_rule_bboxes_by_page.setdefault(region.page_num, []).append(
            region.bbox
        )
    positioned_text_lines_by_id = {
        line.line_id: line
        for line in (
            iter_paper_discovery_lines(paper_discovery, paper_positioned_document)
            if paper_discovery is not None and paper_positioned_document is not None
            else []
        )
    }
    visual_object_owned_line_ids = {
        line.line_id
        for line in positioned_text_lines_by_id.values()
        if VISUAL_OBJECT_DOI_PATTERN.fullmatch(clean_text(line.raw_text)) is not None
    }
    prose_owned_line_ids = (
        set(paper_discovery.prose_line_ids)
        if paper_discovery is not None
        else None
    )
    return [
        build_table_region(
            table,
            table_boundary_proposal=proposals_by_table_id.get(table.table_id),
            positioned_page=pages_by_num.get(table.page_num),
            positioned_text_lines_by_id=positioned_text_lines_by_id,
            visual_object_owned_line_ids=visual_object_owned_line_ids,
            prose_owned_line_ids=prose_owned_line_ids,
            annotation_table=annotations_by_table_id.get(table.table_id),
            page_furniture_rule_bboxes=page_furniture_rule_bboxes_by_page.get(
                table.page_num,
                [],
            ),
        )
        for table in extracted_tables
    ]


def build_table_region(
    table: ExtractedTable,
    *,
    table_boundary_proposal: TableBoundaryProposal | None = None,
    positioned_page: PaperPositionedPage | None = None,
    positioned_text_lines_by_id: Mapping[str, object] | None = None,
    visual_object_owned_line_ids: set[str] | None = None,
    prose_owned_line_ids: set[str] | None = None,
    annotation_table: CellTextAnnotationTable | None = None,
    page_furniture_rule_bboxes: Sequence[
        tuple[float, float, float, float]
    ] = (),
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
    continuation_note_rows: list[int] = []
    header_rows: list[int]
    body_rows: list[int]
    footer_rows: list[int] = []
    footer_line_ids: list[str] = []
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
            continuation_note_rows=continuation_note_rows,
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
    detected_preamble_rows = header_detection.get("preamble_rows")
    detected_post_header_note_rows = header_detection.get("post_header_note_rows")
    detected_continuation_note_rows = header_detection.get("continuation_note_rows")
    if isinstance(detected_preamble_rows, list):
        preamble_rows.extend(
            row_idx + content_start
            for row_idx in detected_preamble_rows
            if isinstance(row_idx, int)
        )
    if isinstance(detected_post_header_note_rows, list):
        preamble_rows.extend(
            row_idx + content_start
            for row_idx in detected_post_header_note_rows
            if isinstance(row_idx, int)
        )
    preamble_rows = sorted(set(preamble_rows))
    continuation_note_rows = (
        sorted(
            row_idx + content_start
            for row_idx in detected_continuation_note_rows
            if isinstance(row_idx, int)
        )
        if isinstance(detected_continuation_note_rows, list)
        else []
    )
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
                and lower_rule <= row_bounds[following_row][0] + RULE_TOLERANCE
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
                header_characters, header_bold_characters = style_counts[first_body_row]
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

    if table_boundary_proposal is not None:
        for candidate in table_boundary_proposal.boundary_candidates:
            if "body_footer" in candidate.possible_roles:
                candidate.possible_roles.remove("body_footer")
            candidate.following_text_line_ids = []
            candidate.following_text_bbox = None
            candidate.following_text_styles = []

    if table.metadata.get("continues_on_next_page") is True:
        diagnostics.append("footer_detection_skipped:continues_on_next_page")

    if (
        table.metadata.get("continues_on_next_page") is not True
        and table_boundary_proposal is not None
        and row_bounds is not None
    ):
        raw_positioned_evidence = table.metadata.get("table_positioned_evidence")
        positioned_evidence = (
            TablePositionedEvidence.model_validate(raw_positioned_evidence)
            if isinstance(raw_positioned_evidence, Mapping)
            else None
        )
        if (
            positioned_text_lines_by_id is not None
            and positioned_evidence is not None
        ):
            table_bbox = (
                table_boundary_proposal.canonical_table_bbox
                or positioned_evidence.canonical_candidate_bbox
                or positioned_evidence.canonical_bbox
            )
            if table_bbox is not None:
                raw_caption_region = table.metadata.get("caption_region")
                caption_line_ids = {
                    str(line_id)
                    for line_id in (
                        raw_caption_region.get("line_ids", [])
                        if isinstance(raw_caption_region, Mapping)
                        else []
                    )
                }
                aligned_page_lines = sorted(
                    (
                        (line, line.canonical_bbox)
                        for line in positioned_text_lines_by_id.values()
                        if line.page_num == table.page_num
                        and line.line_id not in caption_line_ids
                        and line.canonical_bbox is not None
                        and (
                            positioned_evidence.orientation_group_id is None
                            or line.orientation_group_id
                            == positioned_evidence.orientation_group_id
                        )
                        and min(line.canonical_bbox[2], table_bbox[2])
                        > max(line.canonical_bbox[0], table_bbox[0])
                        and table_bbox[1]
                        <= (line.canonical_bbox[1] + line.canonical_bbox[3]) / 2.0
                    ),
                    key=lambda item: (item[1][1], item[1][0]),
                )
                visual_object_barrier = min(
                    (
                        record
                        for record in aligned_page_lines
                        if record[0].line_id
                        in (visual_object_owned_line_ids or set())
                    ),
                    key=lambda item: (item[1][1], item[1][0]),
                    default=None,
                )
                visual_object_doi_barrier_y = (
                    visual_object_barrier[1][1]
                    if visual_object_barrier is not None
                    else None
                )
                raw_candidate_visual_object_barrier_bbox = table.metadata.get(
                    "candidate_visual_object_barrier_bbox"
                )
                candidate_visual_object_barrier_y = (
                    float(raw_candidate_visual_object_barrier_bbox[1])
                    if isinstance(
                        raw_candidate_visual_object_barrier_bbox, (list, tuple)
                    )
                    and len(raw_candidate_visual_object_barrier_bbox) == 4
                    and all(
                        isinstance(value, (int, float))
                        for value in raw_candidate_visual_object_barrier_bbox
                    )
                    and float(raw_candidate_visual_object_barrier_bbox[1])
                    >= table_bbox[3]
                    else None
                )
                visual_object_barrier_y = min(
                    (
                        barrier_y
                        for barrier_y in (
                            visual_object_doi_barrier_y,
                            candidate_visual_object_barrier_y,
                        )
                        if barrier_y is not None
                    ),
                    default=None,
                )
                page_furniture_rule_y = min(
                    (
                        (bbox[1] + bbox[3]) / 2.0
                        for bbox in page_furniture_rule_bboxes
                        if positioned_evidence.rotation_direction is None
                        and bbox[2] - bbox[0] > bbox[3] - bbox[1]
                        and bbox[1] >= table_bbox[3]
                    ),
                    default=None,
                )
                footer_scan_bottom_y = min(
                    (
                        boundary_y
                        for boundary_y in (
                            visual_object_barrier_y,
                            page_furniture_rule_y,
                        )
                        if boundary_y is not None
                    ),
                    default=None,
                )
                raw_lines = [
                    record
                    for record in aligned_page_lines
                    if record[1][3] <= table_bbox[3]
                    and (
                        footer_scan_bottom_y is None
                        or record[1][1] < footer_scan_bottom_y
                    )
                ]
                closing_rule_y = max(
                    (
                        float(rule_y)
                        for rule_y in horizontal_rules
                        if float(rule_y) <= table_bbox[3]
                        and (
                            footer_scan_bottom_y is None
                            or float(rule_y) < footer_scan_bottom_y
                        )
                    ),
                    default=None,
                )
                if (
                    closing_rule_y is not None
                    and closing_rule_y == table_bbox[3]
                ):
                    external_groups: list[
                        list[
                            tuple[
                                object,
                                tuple[float, float, float, float],
                            ]
                        ]
                    ] = []
                    for record in aligned_page_lines:
                        if (
                            footer_scan_bottom_y is not None
                            and record[1][1] >= footer_scan_bottom_y
                        ):
                            break
                        if record[1][1] < table_bbox[3]:
                            continue
                        if (
                            not external_groups
                            or record[1][1]
                            >= min(item[1][3] for item in external_groups[-1])
                            or record[1][3]
                            <= max(item[1][1] for item in external_groups[-1])
                        ):
                            external_groups.append([record])
                        else:
                            external_groups[-1].append(record)

                    adjacent_external_lines: list[
                        tuple[
                            object,
                            tuple[float, float, float, float],
                        ]
                    ] = []
                    external_footer_style: tuple[str, float] | None = None
                    external_footer_fonts: set[str] = set()
                    previous_external_block_indices: set[int] = set()
                    for group in external_groups:
                        if any(line.role == "heading" for line, _bbox in group):
                            diagnostics.append(
                                "footer_external_scan_stopped_at_positioned_heading:"
                                f"{min(line.line_id for line, _bbox in group)}"
                            )
                            break
                        if any(
                            line.line_id in (visual_object_owned_line_ids or set())
                            for line, _bbox in group
                        ):
                            diagnostics.append(
                                "footer_external_scan_stopped_at_visual_object_doi:"
                                f"{min(line.line_id for line, _bbox in group)}"
                            )
                            break
                        group_styles = {
                            (
                                str(line.dominant_font),
                                float(line.dominant_font_size),
                            )
                            for line, _bbox in group
                            if line.dominant_font is not None
                            and line.dominant_font_size is not None
                        }
                        group_style = (
                            next(iter(group_styles))
                            if len(group_styles) == 1
                            else None
                        )
                        group_fonts = {
                            str(line.dominant_font)
                            for line, _bbox in group
                            if line.dominant_font is not None
                        }
                        group_block_indices = {
                            line.block_index
                            for line, _bbox in group
                            if line.block_index is not None
                        }
                        if adjacent_external_lines:
                            same_font_within_block = (
                                len(group_fonts) == 1
                                and group_fonts == external_footer_fonts
                                and bool(group_block_indices)
                                and group_block_indices
                                == previous_external_block_indices
                            )
                            if (
                                group_style != external_footer_style
                                and not same_font_within_block
                            ):
                                diagnostics.append(
                                    "footer_external_scan_stopped_at_font_or_size_change:"
                                    f"{min(line.line_id for line, _bbox in group)}"
                                )
                                break
                        else:
                            external_footer_style = group_style
                            external_footer_fonts = group_fonts
                        adjacent_external_lines.extend(group)
                        previous_external_block_indices = group_block_indices
                    raw_lines.extend(adjacent_external_lines)
                    raw_lines.sort(key=lambda item: (item[1][1], item[1][0]))
                physical_line_groups: list[
                    list[
                        tuple[
                            object,
                            tuple[float, float, float, float],
                        ]
                    ]
                ] = []
                for record in raw_lines:
                    if (
                        not physical_line_groups
                        or record[1][1]
                        >= min(item[1][3] for item in physical_line_groups[-1])
                        or record[1][3]
                        <= max(item[1][1] for item in physical_line_groups[-1])
                    ):
                        physical_line_groups.append([record])
                    else:
                        physical_line_groups[-1].append(record)

                classified_groups: list[
                    tuple[
                        float,
                        tuple[str, float] | None,
                        bool,
                        bool,
                        list[int],
                        list[
                            tuple[
                                object,
                                tuple[float, float, float, float],
                            ]
                        ],
                    ]
                ] = []
                for group in physical_line_groups:
                    ordered_group = sorted(group, key=lambda item: item[1][0])
                    valid_footer_text = True
                    for line, _bbox in ordered_group:
                        text = clean_text(line.raw_text)
                        if (
                            not text
                            or line.dominant_font is None
                            or line.dominant_font_size is None
                            or CONTINUATION_PATTERN.fullmatch(text) is not None
                            or VISUAL_OBJECT_DOI_PATTERN.fullmatch(text) is not None
                        ):
                            valid_footer_text = False
                            break

                    has_separated_fragments = any(
                        right_record[1][0] > left_record[1][2]
                        for left_record, right_record in zip(
                            ordered_group,
                            ordered_group[1:],
                            strict=False,
                        )
                    )

                    group_top = min(bbox[1] for _line, bbox in ordered_group)
                    group_bottom = max(bbox[3] for _line, bbox in ordered_group)
                    group_styles = {
                        (
                            str(line.dominant_font),
                            round(float(line.dominant_font_size), 1),
                        )
                        for line, _bbox in ordered_group
                        if line.dominant_font is not None
                        and line.dominant_font_size is not None
                    }
                    group_style = (
                        next(iter(group_styles)) if len(group_styles) == 1 else None
                    )
                    group_rows = sorted(
                        {
                            row_idx
                            for _line, bbox in ordered_group
                            for row_idx in range(len(row_bounds))
                            if row_bounds[row_idx][0]
                            <= (bbox[1] + bbox[3]) / 2.0
                            <= row_bounds[row_idx][1]
                        }
                    )
                    classified_groups.append(
                        (
                            (group_top + group_bottom) / 2.0,
                            group_style,
                            valid_footer_text,
                            has_separated_fragments,
                            group_rows,
                            ordered_group,
                        )
                    )

                ordered_events = [
                    (group[0], "line", group_index)
                    for group_index, group in enumerate(classified_groups)
                ]
                ordered_events.extend(
                    (float(rule_y), "rule", -1)
                    for rule_y in horizontal_rules
                    if table_bbox[1] <= float(rule_y) <= table_bbox[3]
                    and (
                        footer_scan_bottom_y is None
                        or float(rule_y) < footer_scan_bottom_y
                    )
                )
                ordered_events.sort(
                    key=lambda item: (item[0], 1 if item[1] == "rule" else 0)
                )

                if ordered_events:
                    event_index = len(ordered_events) - 1
                    started_after_closing_rule = (
                        ordered_events[event_index][1] == "rule"
                    )
                    if started_after_closing_rule:
                        event_index -= 1

                    if (
                        event_index >= 0
                        and ordered_events[event_index][1] == "line"
                    ):
                        first_group = classified_groups[
                            ordered_events[event_index][2]
                        ]
                        (
                            _first_center,
                            footer_style,
                            valid_footer_text,
                            has_separated_fragments,
                            first_group_rows,
                            first_lines,
                        ) = first_group
                        if (
                            valid_footer_text
                            and not has_separated_fragments
                        ):
                            complete_lines = list(first_lines)
                            candidate_footer_rows = set(first_group_rows)
                            stopping_rule_y: float | None = None
                            stop_reason = "candidate_start"
                            current_footer_block_indices = {
                                line.block_index
                                for line, _bbox in first_lines
                                if line.block_index is not None
                            }
                            current_footer_fonts = {
                                str(line.dominant_font)
                                for line, _bbox in first_lines
                                if line.dominant_font is not None
                            }
                            event_index -= 1

                            while event_index >= 0:
                                _event_y, event_kind, group_index = ordered_events[
                                    event_index
                                ]
                                if event_kind == "rule":
                                    stopping_rule_y = ordered_events[event_index][0]
                                    stop_reason = "horizontal_rule"
                                    break
                                (
                                    _group_center,
                                    group_style,
                                    valid_footer_text,
                                    has_separated_fragments,
                                    group_rows,
                                    group_lines,
                                ) = classified_groups[group_index]
                                if not valid_footer_text:
                                    stop_reason = "not_footer_text"
                                    complete_lines = []
                                    candidate_footer_rows.clear()
                                    break
                                if has_separated_fragments:
                                    stop_reason = "data_spacing"
                                    break
                                group_block_indices = {
                                    line.block_index
                                    for line, _bbox in group_lines
                                    if line.block_index is not None
                                }
                                group_fonts = {
                                    str(line.dominant_font)
                                    for line, _bbox in group_lines
                                    if line.dominant_font is not None
                                }
                                same_font_within_block = (
                                    len(group_fonts) == 1
                                    and group_fonts == current_footer_fonts
                                    and bool(group_block_indices)
                                    and group_block_indices
                                    == current_footer_block_indices
                                )
                                if (
                                    group_style != footer_style
                                    and not same_font_within_block
                                ):
                                    stop_reason = "font_or_size_change"
                                    break
                                else:
                                    complete_lines.extend(group_lines)
                                    candidate_footer_rows.update(group_rows)
                                current_footer_block_indices = group_block_indices
                                current_footer_fonts = group_fonts
                                event_index -= 1

                            table_end_candidates = [
                                candidate
                                for candidate in (
                                    table_boundary_proposal.boundary_candidates
                                )
                                if "table_end" in candidate.possible_roles
                                and candidate.row_after_idx is None
                            ]
                            has_table_end_rule = len(table_end_candidates) == 1
                            if complete_lines and not has_table_end_rule:
                                candidate_line_ids = {
                                    line.line_id for line, _bbox in complete_lines
                                }
                                candidate_fonts = {
                                    line.dominant_font
                                    for line, _bbox in complete_lines
                                    if line.dominant_font is not None
                                }
                                other_table_fonts = {
                                    line.dominant_font
                                    for line_id in positioned_evidence.line_ids
                                    if line_id not in candidate_line_ids
                                    and line_id not in caption_line_ids
                                    and (
                                        line := positioned_text_lines_by_id.get(line_id)
                                    )
                                    is not None
                                    and line.dominant_font is not None
                                }
                                if (
                                    not candidate_fonts
                                    or not other_table_fonts
                                    or not candidate_fonts.isdisjoint(
                                        other_table_fonts
                                    )
                                ):
                                    diagnostics.append(
                                        "footer_candidate_rejected:"
                                        "no_table_end_rule_without_distinct_table_font"
                                    )
                                    complete_lines = []
                                    candidate_footer_rows.clear()
                                    stopping_rule_y = None

                            complete_lines.sort(
                                key=lambda item: (item[1][1], item[1][0])
                            )
                            footer_rows = sorted(candidate_footer_rows)
                            boundary_candidate = (
                                table_end_candidates[0]
                                if len(table_end_candidates) == 1
                                else None
                            )

                            if footer_rows:
                                footer_line_ids = [
                                    line.line_id for line, _bbox in complete_lines
                                ]
                                footer_set = set(footer_rows)
                                body_rows = [
                                    row_idx
                                    for row_idx in body_rows
                                    if row_idx not in footer_set
                                ]
                                body_footer_rule_y = stopping_rule_y
                            elif complete_lines and boundary_candidate is not None:
                                external_footer_line_ids = [
                                    line.line_id for line, _bbox in complete_lines
                                ]
                                if prose_owned_line_ids is None:
                                    diagnostics.append(
                                        "footer_candidate_rejected:"
                                        "canonical_prose_ownership_unavailable"
                                    )
                                    complete_lines = []
                                elif any(
                                    line_id in prose_owned_line_ids
                                    for line_id in external_footer_line_ids
                                ):
                                    diagnostics.append(
                                        "footer_candidate_rejected:canonical_prose_owner"
                                    )
                                    complete_lines = []
                                else:
                                    footer_line_ids = external_footer_line_ids
                                    boundary_candidate.following_text_line_ids = (
                                        external_footer_line_ids
                                    )
                                    boundary_candidate.following_text_bbox = (
                                        min(bbox[0] for _line, bbox in complete_lines),
                                        min(bbox[1] for _line, bbox in complete_lines),
                                        max(bbox[2] for _line, bbox in complete_lines),
                                        max(bbox[3] for _line, bbox in complete_lines),
                                    )
                                    boundary_candidate.following_text_styles = (
                                        [footer_style]
                                        if footer_style is not None
                                        else []
                                    )
                                    boundary_candidate.possible_roles.append(
                                        "body_footer"
                                    )
                                    body_footer_rule_y = boundary_candidate.canonical_y
                            else:
                                complete_lines = []
                                diagnostics.append(
                                    "raw_positioned_footer_unowned:"
                                    "no_internal_rows_or_boundary_rule"
                                )

                            if complete_lines:
                                diagnostics.append(
                                    "raw_positioned_footer_accepted:"
                                    f"lines={len(complete_lines)}:"
                                    f"rows={len(footer_rows)}:"
                                    f"footer_style={footer_style}:"
                                    f"started_after_closing_rule="
                                    f"{str(started_after_closing_rule).lower()}:"
                                    f"stop={stop_reason}:"
                                    "exact_rule_and_positioned_row_structure"
                                )

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
        continuation_note_rows=continuation_note_rows,
        column_header_rows=header_rows,
        body_rows=body_rows,
        footer_note_rows=footer_rows,
        footer_line_ids=footer_line_ids,
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
        {float(item) for item in value if isinstance(item, (int, float))}
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
