"""Build preliminary header structure from positioned geometry."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from statistics import median

from table1_parser.schemas import (
    CellTextAnnotationTable,
    ExtractedTable,
    HeaderGroupCandidate,
    HeaderLeafCandidate,
    HeaderMarkerAttachmentCandidate,
    HeaderStructureCandidate,
    HeaderStructureRelationship,
    HeaderTextEvidence,
    LeafColumnCandidateTable,
    PaperPositionedDocument,
    PaperPositionedPage,
    TableBoundaryProposal,
    TableBoundaryRuleReference,
    TableCell,
    TablePositionedEvidence,
    TableRegion,
)
from table1_parser.text_cleaning import clean_text


HeaderCluster = list[HeaderTextEvidence]
PositionedRule = tuple[float, TableBoundaryRuleReference]


def _cluster_x_bounds(cluster: HeaderCluster) -> tuple[float, float]:
    """Return the horizontal extent of one header evidence cluster."""
    return (
        min(item.canonical_bbox[0] for item in cluster),
        max(item.canonical_bbox[2] for item in cluster),
    )


def _covered_anchor_band_ids(
    x_bounds: tuple[float, float],
    leaf_axis_ids: Sequence[str],
    observed_anchor_x_by_band: dict[str, float],
) -> list[str]:
    """Return ordered bands whose observed body anchor lies in an x interval."""
    left, right = sorted(x_bounds)
    return [
        band_id
        for band_id in leaf_axis_ids
        if band_id in observed_anchor_x_by_band
        and left - 1.0 <= observed_anchor_x_by_band[band_id] <= right + 1.0
    ]


def _matching_header_clusters(
    item: HeaderTextEvidence,
    clusters: Sequence[HeaderCluster],
    horizontal_rules: Sequence[PositionedRule],
    *,
    respect_intervening_rules: bool,
) -> list[HeaderCluster]:
    """Return clusters with strong x overlap and no separating rule."""
    matches: list[HeaderCluster] = []
    item_width = item.canonical_bbox[2] - item.canonical_bbox[0]
    for cluster in clusters:
        cluster_left, cluster_right = _cluster_x_bounds(cluster)
        overlap = max(
            0.0,
            min(item.canonical_bbox[2], cluster_right)
            - max(item.canonical_bbox[0], cluster_left),
        )
        separated_by_rule = respect_intervening_rules and any(
            max(part.canonical_bbox[3] for part in cluster)
            < rule_y
            < item.canonical_bbox[1]
            for rule_y, _ in horizontal_rules
        )
        if (
            overlap >= 0.35 * min(item_width, cluster_right - cluster_left)
            and not separated_by_rule
        ):
            matches.append(cluster)
    return matches


def _cluster_header_evidence(
    items: Sequence[HeaderTextEvidence],
    horizontal_rules: Sequence[PositionedRule],
) -> list[HeaderCluster]:
    """Join vertically wrapped evidence while preserving rule-separated rows."""
    clusters: list[HeaderCluster] = []
    for item in sorted(
        items,
        key=lambda value: (value.canonical_bbox[1], value.canonical_bbox[0]),
    ):
        matches = _matching_header_clusters(
            item,
            clusters,
            horizontal_rules,
            respect_intervening_rules=True,
        )
        if len(matches) == 1:
            matches[0].append(item)
        else:
            clusters.append([item])
    return clusters


def inherit_adjacent_continuation_leaf_labels(
    extracted_tables: Sequence[ExtractedTable],
    candidates: Sequence[HeaderStructureCandidate],
) -> list[HeaderStructureCandidate]:
    """Fill blank leaves only for an established adjacent continuation structure."""
    updated = list(candidates)
    candidate_index = {candidate.table_id: index for index, candidate in enumerate(updated)}
    ordered_tables = sorted(extracted_tables, key=lambda table: table.page_num)
    for parent_table, continuation_table in zip(
        ordered_tables,
        ordered_tables[1:],
        strict=False,
    ):
        parent_number = parent_table.metadata.get("table_number")
        continuation_number = continuation_table.metadata.get(
            "continuation_of_table_number"
        ) or continuation_table.metadata.get("table_number")
        if (
            continuation_table.page_num != parent_table.page_num + 1
            or not isinstance(parent_number, int)
            or isinstance(parent_number, bool)
            or parent_number < 1
            or (
                continuation_number is not None
                and continuation_number != parent_number
            )
            or (
                (continuation_table.title or continuation_table.caption)
                and continuation_number != parent_number
            )
        ):
            continue
        parent_index = candidate_index.get(parent_table.table_id)
        continuation_index = candidate_index.get(continuation_table.table_id)
        if parent_index is None or continuation_index is None:
            continue
        parent = updated[parent_index]
        continuation = updated[continuation_index]
        parent_leaves = sorted(parent.leaf_candidates, key=lambda leaf: leaf.leaf_index)
        continuation_leaves = sorted(
            continuation.leaf_candidates,
            key=lambda leaf: leaf.leaf_index,
        )
        expected_indices = list(range(parent_table.n_cols))
        if (
            parent_table.n_cols != continuation_table.n_cols
            or [leaf.leaf_index for leaf in parent_leaves] != expected_indices
            or [leaf.leaf_index for leaf in continuation_leaves] != expected_indices
            or any(not leaf.occupancy_band_ids for leaf in [*parent_leaves, *continuation_leaves])
        ):
            continue
        parent_leaf_index = {leaf.leaf_id: leaf.leaf_index for leaf in parent_leaves}
        continuation_leaf_index = {
            leaf.leaf_id: leaf.leaf_index for leaf in continuation_leaves
        }
        parent_groups = sorted(
            (
                clean_text(group.label).casefold(),
                tuple(sorted(parent_leaf_index[leaf_id] for leaf_id in group.leaf_ids)),
            )
            for group in parent.group_candidates
            if group.leaf_ids and all(leaf_id in parent_leaf_index for leaf_id in group.leaf_ids)
        )
        continuation_groups = sorted(
            (
                clean_text(group.label).casefold(),
                tuple(
                    sorted(
                        continuation_leaf_index[leaf_id]
                        for leaf_id in group.leaf_ids
                    )
                ),
            )
            for group in continuation.group_candidates
            if group.leaf_ids
            and all(leaf_id in continuation_leaf_index for leaf_id in group.leaf_ids)
        )
        explicit_identity = continuation_number == parent_number
        if (
            (not explicit_identity and (not parent_groups or parent_groups != continuation_groups))
            or any(
                clean_text(local.label)
                and clean_text(source.label)
                and clean_text(local.label).casefold() != clean_text(source.label).casefold()
                for source, local in zip(parent_leaves, continuation_leaves, strict=True)
            )
        ):
            continue
        inherited_indices = [
            local.leaf_index
            for source, local in zip(parent_leaves, continuation_leaves, strict=True)
            if not clean_text(local.label) and clean_text(source.label)
        ]
        if not inherited_indices:
            continue
        evidence = [
            f"adjacent_pages:{parent_table.page_num}->{continuation_table.page_num}",
            (
                f"explicit_same_table_identity:{parent_number}"
                if explicit_identity
                else f"existing_uncaptioned_adjacent_identity:{parent_number}"
            ),
            f"complete_one_to_one_occupancy_leaf_alignment:{len(parent_leaves)}",
            f"matching_header_group_spans:{len(parent_groups)}",
            "nonblank_local_leaf_labels_compatible",
        ]
        updated[continuation_index] = continuation.model_copy(
            update={
                "leaf_candidates": [
                    local.model_copy(
                        update={
                            "label": source.label,
                            "label_source": "inherited_continuation",
                            "local_label": local.label,
                            "inherited_from_table_id": parent_table.table_id,
                            "inherited_from_leaf_id": source.leaf_id,
                            "inherited_from_page_num": parent_table.page_num,
                            "inheritance_evidence": evidence,
                        }
                    )
                    if local.leaf_index in inherited_indices
                    else local
                    for source, local in zip(
                        parent_leaves,
                        continuation_leaves,
                        strict=True,
                    )
                ],
                "diagnostics": [
                    *continuation.diagnostics,
                    "inherited_blank_continuation_leaf_labels:"
                    + ",".join(str(index) for index in inherited_indices),
                ],
            }
        )
    return updated


def build_header_structure_candidates(
    extracted_tables: Sequence[ExtractedTable],
    *,
    paper_positioned_document: PaperPositionedDocument,
    table_regions: Sequence[TableRegion],
    table_boundary_proposals: Sequence[TableBoundaryProposal],
    leaf_column_candidates: Sequence[LeafColumnCandidateTable],
    cell_text_annotations: Sequence[CellTextAnnotationTable],
) -> list[HeaderStructureCandidate]:
    """Build one preliminary header candidate per extracted table."""
    pages = {page.page_num: page for page in paper_positioned_document.pages}
    regions = {region.table_id: region for region in table_regions}
    proposals = {proposal.table_id: proposal for proposal in table_boundary_proposals}
    leaf_tables = {candidate.table_id: candidate for candidate in leaf_column_candidates}
    annotations = {item.table_id: item for item in cell_text_annotations}
    return [
        build_header_structure_candidate(
            table,
            positioned_page=pages.get(table.page_num),
            table_region=regions.get(table.table_id),
            table_boundary_proposal=proposals.get(table.table_id),
            leaf_column_candidate=leaf_tables.get(table.table_id),
            annotation_table=annotations.get(table.table_id),
        )
        for table in extracted_tables
    ]


def build_header_structure_candidate(
    table: ExtractedTable,
    *,
    positioned_page: PaperPositionedPage | None,
    table_region: TableRegion | None,
    table_boundary_proposal: TableBoundaryProposal | None,
    leaf_column_candidate: LeafColumnCandidateTable | None,
    annotation_table: CellTextAnnotationTable | None,
) -> HeaderStructureCandidate:
    """Build a geometry-only LaTeX-like header candidate for one table."""
    candidate_id = f"{table.table_id}:header_structure_candidate"
    source_artifacts = [
        "paper_positioned_document.json",
        "extracted_tables.json:metadata.table_positioned_evidence",
        "table_regions.json",
        "table_boundary_proposals.json",
        "leaf_column_candidates.json",
        "cell_text_annotations.json",
    ]
    diagnostics: list[str] = []
    concerns: list[str] = []
    header_rows = table_region.column_header_rows if table_region is not None else []
    body_rows = table_region.body_rows if table_region is not None else []
    if table_region is None:
        diagnostics.append("table_region_missing")
    if not header_rows:
        diagnostics.append("header_rows_missing")
    if table_boundary_proposal is None:
        diagnostics.append("table_boundary_proposal_missing")
    if leaf_column_candidate is None:
        diagnostics.append("leaf_column_candidate_missing")
    if positioned_page is None:
        diagnostics.append("positioned_page_missing")
    raw_evidence = table.metadata.get("table_positioned_evidence")
    if not isinstance(raw_evidence, dict):
        diagnostics.append("table_positioned_evidence_missing")
    local_bands = (
        leaf_column_candidate.bands if leaf_column_candidate is not None else []
    )
    if not local_bands:
        diagnostics.append("occupancy_bands_missing")
    if (
        diagnostics
        or table_boundary_proposal is None
        or positioned_page is None
        or not isinstance(raw_evidence, dict)
    ):
        return HeaderStructureCandidate(
            candidate_id=candidate_id,
            table_id=table.table_id,
            page_num=table.page_num,
            source_artifacts=source_artifacts,
            header_row_indices=list(header_rows),
            body_row_indices=list(body_rows),
            occupancy_band_ids=[band.band_id for band in local_bands],
            diagnostics=diagnostics,
        )

    evidence = TablePositionedEvidence.model_validate(raw_evidence)
    row_bounds = table_boundary_proposal.canonical_row_bounds
    if len(row_bounds) != table.n_rows:
        return HeaderStructureCandidate(
            candidate_id=candidate_id,
            table_id=table.table_id,
            page_num=table.page_num,
            source_artifacts=source_artifacts,
            header_row_indices=list(header_rows),
            body_row_indices=list(body_rows),
            occupancy_band_ids=[band.band_id for band in local_bands],
            diagnostics=["canonical_row_bounds_incomplete"],
        )

    leaf_axis_ids = [band.band_id for band in local_bands]
    leaf_axis_roles = [band.provisional_role for band in local_bands]
    leaf_axis_bounds = [band.canonical_x_bounds for band in local_bands]
    flat_header_cells: list[TableCell] = []
    raw_selection = table.metadata.get("canonical_grid_selection")
    if len(header_rows) == 1 and isinstance(raw_selection, dict):
        raw_boundaries = raw_selection.get("selected_column_boundaries")
        raw_band_ids = raw_selection.get("selected_band_ids")
        selected_boundaries: list[float] = []
        if isinstance(raw_boundaries, list):
            for value in raw_boundaries:
                if isinstance(value, bool):
                    selected_boundaries = []
                    break
                try:
                    selected_boundaries.append(float(value))
                except (TypeError, ValueError):
                    selected_boundaries = []
                    break
        cells_by_col = {
            cell.col_idx: cell
            for cell in table.cells
            if cell.row_idx == header_rows[0]
        }
        if (
            raw_selection.get("status") == "accepted"
            and len(local_bands) == table.n_cols
            and len(selected_boundaries) == table.n_cols + 1
            and all(
                right > left
                for left, right in zip(
                    selected_boundaries,
                    selected_boundaries[1:],
                    strict=False,
                )
            )
            and isinstance(raw_band_ids, list)
            and len(raw_band_ids) == table.n_cols
            and all(isinstance(value, str) and value for value in raw_band_ids)
            and set(cells_by_col) == set(range(table.n_cols))
            and all(
                cells_by_col[col_idx].text.strip()
                for col_idx in range(table.n_cols)
            )
        ):
            flat_header_cells = [
                cells_by_col[col_idx] for col_idx in range(table.n_cols)
            ]
            leaf_axis_ids = list(raw_band_ids)
            leaf_axis_roles = [
                "stub" if col_idx == 0 else "value"
                for col_idx in range(table.n_cols)
            ]
            leaf_axis_bounds = list(
                zip(
                    selected_boundaries,
                    selected_boundaries[1:],
                    strict=False,
                )
            )
            if len(local_bands) != table.n_cols:
                concerns.append(
                    "local_leaf_axis_disagrees_with_canonical_grid:"
                    f"local={len(local_bands)}:canonical={table.n_cols}"
                )

    body_cell_centers_by_band: dict[str, list[float]] = defaultdict(list)
    for cell in table.cells:
        if (
            cell.row_idx not in body_rows
            or cell.bbox is None
            or not cell.text.strip()
        ):
            continue
        selected_band_id: str | None = None
        if len(leaf_axis_ids) == table.n_cols and cell.col_idx < len(leaf_axis_ids):
            selected_band_id = leaf_axis_ids[cell.col_idx]
        else:
            overlaps = [
                max(
                    0.0,
                    min(cell.bbox[2], bounds[1])
                    - max(cell.bbox[0], bounds[0]),
                )
                for bounds in leaf_axis_bounds
            ]
            if overlaps and max(overlaps) > 0.0:
                selected_band_id = leaf_axis_ids[
                    max(range(len(overlaps)), key=overlaps.__getitem__)
                ]
        if selected_band_id is not None:
            body_cell_centers_by_band[selected_band_id].append(
                (cell.bbox[0] + cell.bbox[2]) / 2.0
            )
    observed_anchor_x_by_band = {
        band_id: median(centers)
        for band_id, centers in body_cell_centers_by_band.items()
        if centers
    }

    horizontal_rules: list[PositionedRule] = []
    for source, indices, segments in (
        ("rule_segment", evidence.rule_segment_indices, evidence.canonical_rule_segments),
        (
            "stroked_rule_segment",
            evidence.stroked_rule_segment_indices,
            evidence.canonical_stroked_rule_segments,
        ),
    ):
        for source_index, segment in zip(indices, segments, strict=False):
            if abs(segment[3] - segment[1]) > 1.5:
                continue
            horizontal_rules.append(
                (
                    (segment[1] + segment[3]) / 2.0,
                    TableBoundaryRuleReference(
                        source=source,
                        source_index=source_index,
                        canonical_segment=segment,
                    ),
                )
            )

    mixed_header_body_row: int | None = None
    mixed_header_value_band_ids: set[str] = set()
    if header_rows and body_rows:
        last_header_row = max(header_rows)
        first_body_row = min(body_rows)
        if first_body_row == last_header_row + 1:
            intervening_spans: set[tuple[float, float, float]] = set()
            intervening_band_ids: set[str] = set()
            for rule_y, reference in horizontal_rules:
                if not (
                    row_bounds[last_header_row][1] - 1.0
                    <= rule_y
                    <= row_bounds[first_body_row][0] + 1.0
                ):
                    continue
                segment = reference.canonical_segment
                covered_anchor_band_ids = _covered_anchor_band_ids(
                    (segment[0], segment[2]),
                    leaf_axis_ids,
                    observed_anchor_x_by_band,
                )
                if any(
                    leaf_axis_roles[leaf_axis_ids.index(band_id)] == "stub"
                    for band_id in covered_anchor_band_ids
                ):
                    continue
                covered_band_ids = [
                    band_id
                    for band_id in covered_anchor_band_ids
                    if leaf_axis_roles[leaf_axis_ids.index(band_id)] != "stub"
                ]
                if len(covered_band_ids) < 2:
                    continue
                intervening_spans.add(
                    (
                        round(min(segment[0], segment[2]), 1),
                        round(max(segment[0], segment[2]), 1),
                        round(rule_y, 1),
                    )
                )
                intervening_band_ids.update(covered_band_ids)

            lower_boundary_supported = False
            for candidate in table_boundary_proposal.boundary_candidates:
                if (
                    "header_body" not in candidate.possible_roles
                    or candidate.row_before_idx != first_body_row
                    or candidate.row_after_idx is None
                    or candidate.row_after_idx <= first_body_row
                ):
                    continue
                covered_by_lower_rule = {
                    band_id
                    for reference in candidate.rule_references
                    for band_id in _covered_anchor_band_ids(
                        (
                            reference.canonical_segment[0],
                            reference.canonical_segment[2],
                        ),
                        leaf_axis_ids,
                        observed_anchor_x_by_band,
                    )
                    if leaf_axis_roles[leaf_axis_ids.index(band_id)] != "stub"
                }
                if len(covered_by_lower_rule.intersection(intervening_band_ids)) >= 2:
                    lower_boundary_supported = True
                    break

            populated_first_body_bands: set[str] = set()
            for cell in table.cells:
                if (
                    cell.row_idx != first_body_row
                    or cell.bbox is None
                    or not cell.text.strip()
                ):
                    continue
                selected_band_id = None
                if (
                    len(leaf_axis_ids) == table.n_cols
                    and cell.col_idx < len(leaf_axis_ids)
                ):
                    selected_band_id = leaf_axis_ids[cell.col_idx]
                else:
                    center_x = (cell.bbox[0] + cell.bbox[2]) / 2.0
                    selected_band_id = next(
                        (
                            band_id
                            for band_id, bounds in zip(
                                leaf_axis_ids,
                                leaf_axis_bounds,
                                strict=True,
                            )
                            if bounds[0] <= center_x <= bounds[1]
                        ),
                        None,
                    )
                if selected_band_id is not None:
                    populated_first_body_bands.add(selected_band_id)

            supported_value_bands = intervening_band_ids.intersection(
                populated_first_body_bands
            )
            if (
                intervening_spans
                and lower_boundary_supported
                and len(supported_value_bands) >= 2
            ):
                mixed_header_body_row = first_body_row
                mixed_header_value_band_ids = supported_value_bands

    evidence_header_rows = list(header_rows)
    if mixed_header_body_row is not None:
        evidence_header_rows.append(mixed_header_body_row)

    line_id_by_position = {
        (line.block_index, line.line_index): line.line_id
        for line in positioned_page.lines
        if line.block_index is not None and line.line_index is not None
    }
    words_by_row_line: dict[
        tuple[int, str],
        list[tuple[int, str, tuple[float, float, float, float]]],
    ] = defaultdict(list)
    for word_index, bbox in zip(
        evidence.word_indices,
        evidence.canonical_word_bboxes,
        strict=False,
    ):
        if word_index >= len(positioned_page.words):
            continue
        word = positioned_page.words[word_index]
        center_y = (bbox[1] + bbox[3]) / 2.0
        candidate_rows = [
            row_idx
            for row_idx in evidence_header_rows
            if row_bounds[row_idx][0] - 1.0 <= center_y <= row_bounds[row_idx][1] + 1.0
        ]
        if not candidate_rows or not word.text.strip():
            continue
        row_idx = min(
            candidate_rows,
            key=lambda item: abs(center_y - sum(row_bounds[item]) / 2.0),
        )
        if row_idx == mixed_header_body_row:
            center_x = (bbox[0] + bbox[2]) / 2.0
            word_band_id = next(
                (
                    band_id
                    for band_id, bounds in zip(
                        leaf_axis_ids,
                        leaf_axis_bounds,
                        strict=True,
                    )
                    if bounds[0] <= center_x <= bounds[1]
                ),
                None,
            )
            if word_band_id not in mixed_header_value_band_ids:
                continue
        source_line_id = line_id_by_position.get(
            (word.block_index, word.line_index),
            f"{table.table_id}:header:row:{row_idx}",
        )
        words_by_row_line[(row_idx, source_line_id)].append(
            (word_index, word.text, bbox)
        )

    header_evidence: list[HeaderTextEvidence] = []
    run_rows: dict[str, int] = {}
    run_words: dict[str, list[tuple[int, str, tuple[float, float, float, float]]]] = {}
    if flat_header_cells:
        words_by_col: dict[
            int,
            list[tuple[int, str, tuple[float, float, float, float]]],
        ] = defaultdict(list)
        line_ids_by_col: dict[int, list[str]] = defaultdict(list)
        for (row_idx, source_line_id), words in sorted(words_by_row_line.items()):
            if row_idx != header_rows[0]:
                continue
            for word in words:
                overlaps = [
                    max(
                        0.0,
                        min(word[2][2], bounds[1])
                        - max(word[2][0], bounds[0]),
                    )
                    for bounds in leaf_axis_bounds
                ]
                col_idx = max(
                    range(len(leaf_axis_bounds)),
                    key=lambda index: overlaps[index],
                )
                if overlaps[col_idx] <= 0.0:
                    center_x = (word[2][0] + word[2][2]) / 2.0
                    col_idx = min(
                        range(len(leaf_axis_bounds)),
                        key=lambda index: abs(
                            center_x - sum(leaf_axis_bounds[index]) / 2.0
                        ),
                    )
                words_by_col[col_idx].append(word)
                if source_line_id not in line_ids_by_col[col_idx]:
                    line_ids_by_col[col_idx].append(source_line_id)
        if not all(words_by_col[col_idx] for col_idx in range(table.n_cols)):
            flat_header_cells = []
            leaf_axis_ids = [band.band_id for band in local_bands]
            leaf_axis_roles = [band.provisional_role for band in local_bands]
            leaf_axis_bounds = [band.canonical_x_bounds for band in local_bands]
            concerns = [
                concern
                for concern in concerns
                if not concern.startswith(
                    "local_leaf_axis_disagrees_with_canonical_grid:"
                )
            ]
        else:
            ordered_flat_cells = sorted(
                enumerate(flat_header_cells),
                key=lambda item: (min(line_ids_by_col[item[0]]), item[0]),
            )
            for col_idx, cell in ordered_flat_cells:
                run = sorted(
                    words_by_col[col_idx],
                    key=lambda item: (item[2][0], item[0]),
                )
                evidence_id = f"{candidate_id}:evidence:{len(header_evidence)}"
                bbox = cell.bbox or (
                    min(item[2][0] for item in run),
                    min(item[2][1] for item in run),
                    max(item[2][2] for item in run),
                    max(item[2][3] for item in run),
                )
                header_evidence.append(
                    HeaderTextEvidence(
                        evidence_id=evidence_id,
                        text=clean_text(cell.text),
                        header_row_indices=[header_rows[0]],
                        source_line_ids=line_ids_by_col[col_idx],
                        source_word_indices=[item[0] for item in run],
                        canonical_bbox=bbox,
                    )
                )
                run_rows[evidence_id] = header_rows[0]
                run_words[evidence_id] = run

    if not flat_header_cells:
        for (row_idx, source_line_id), words in sorted(words_by_row_line.items()):
            words.sort(key=lambda item: item[2][0])
            heights = [
                bbox[3] - bbox[1]
                for _, _, bbox in words
                if bbox[3] > bbox[1]
            ]
            gap_limit = max(3.0, median(heights) * 0.75) if heights else 4.0
            runs: list[
                list[tuple[int, str, tuple[float, float, float, float]]]
            ] = []
            for word in words:
                if not runs or word[2][0] - runs[-1][-1][2][2] > gap_limit:
                    runs.append([word])
                else:
                    runs[-1].append(word)
            for run in runs:
                evidence_id = f"{candidate_id}:evidence:{len(header_evidence)}"
                bbox = (
                    min(item[2][0] for item in run),
                    min(item[2][1] for item in run),
                    max(item[2][2] for item in run),
                    max(item[2][3] for item in run),
                )
                header_evidence.append(
                    HeaderTextEvidence(
                        evidence_id=evidence_id,
                        text=clean_text(" ".join(item[1] for item in run)),
                        header_row_indices=[row_idx],
                        source_line_ids=[source_line_id],
                        source_word_indices=[item[0] for item in run],
                        canonical_bbox=bbox,
                    )
                )
                run_rows[evidence_id] = row_idx
                run_words[evidence_id] = run

    internal_rule_ys = [
        rule_y
        for rule_y, _ in horizontal_rules
        if any(row_bounds[row_idx][1] < rule_y for row_idx in evidence_header_rows)
        and any(row_bounds[row_idx][0] > rule_y for row_idx in evidence_header_rows)
    ]
    leaf_floor = max(internal_rule_ys) if internal_rule_ys else None
    leaf_evidence = [
        item
        for item in header_evidence
        if (
            leaf_floor is None
            and run_rows[item.evidence_id] == max(evidence_header_rows)
        )
        or (
            leaf_floor is not None
            and item.canonical_bbox[1] > leaf_floor - 1.0
        )
    ]
    upper_evidence = [
        item for item in header_evidence if item.evidence_id not in {x.evidence_id for x in leaf_evidence}
    ]

    value_evidence_count_by_row: dict[int, int] = defaultdict(int)
    for item in header_evidence:
        item_center = (item.canonical_bbox[0] + item.canonical_bbox[2]) / 2.0
        center_band_index = next(
            (
                index
                for index, bounds in enumerate(leaf_axis_bounds)
                if bounds[0] <= item_center <= bounds[1]
            ),
            None,
        )
        if (
            center_band_index is not None
            and leaf_axis_roles[center_band_index] != "stub"
        ):
            value_evidence_count_by_row[run_rows[item.evidence_id]] += 1

    explicit_group_band_ids: dict[str, list[str]] = {}
    explicit_group_rule_references: dict[
        str,
        list[TableBoundaryRuleReference],
    ] = {}
    classified_group_band_ids: dict[str, list[str]] = {}
    direct_group_evidence: list[HeaderTextEvidence] = []
    retained_leaf_evidence: list[HeaderTextEvidence] = []
    for item in leaf_evidence:
        covered_band_ids = _covered_anchor_band_ids(
            (item.canonical_bbox[0], item.canonical_bbox[2]),
            leaf_axis_ids,
            observed_anchor_x_by_band,
        )
        covered_value_band_ids = [
            band_id
            for band_id in covered_band_ids
            if leaf_axis_roles[leaf_axis_ids.index(band_id)] != "stub"
        ]
        if (
            len(covered_value_band_ids) >= 2
            and len(covered_value_band_ids) == len(covered_band_ids)
        ):
            direct_group_evidence.append(item)
            explicit_group_band_ids[item.evidence_id] = covered_value_band_ids
            classified_group_band_ids[item.evidence_id] = covered_value_band_ids
            explicit_group_rule_references[item.evidence_id] = []
        else:
            retained_leaf_evidence.append(item)
    leaf_evidence = retained_leaf_evidence

    leaf_evidence_centers_by_band: dict[str, list[float]] = defaultdict(list)
    leaf_evidence_texts_by_band: dict[str, set[str]] = defaultdict(set)
    for item in leaf_evidence:
        overlap_by_band = [
            (
                max(
                    0.0,
                    min(item.canonical_bbox[2], bounds[1])
                    - max(item.canonical_bbox[0], bounds[0]),
                ),
                band_id,
            )
            for band_id, bounds in zip(
                leaf_axis_ids,
                leaf_axis_bounds,
                strict=True,
            )
        ]
        maximum_overlap = max(
            (overlap for overlap, _ in overlap_by_band),
            default=0.0,
        )
        matching_band_ids = [
            band_id
            for overlap, band_id in overlap_by_band
            if maximum_overlap > 0.0 and abs(overlap - maximum_overlap) <= 0.5
        ]
        if len(matching_band_ids) == 1:
            leaf_evidence_centers_by_band[matching_band_ids[0]].append(
                (item.canonical_bbox[0] + item.canonical_bbox[2]) / 2.0
            )
            leaf_evidence_texts_by_band[matching_band_ids[0]].add(
                clean_text(item.text)
            )
    header_anchor_x_by_band = dict(observed_anchor_x_by_band)
    header_anchor_x_by_band.update(
        {
            band_id: median(centers)
            for band_id, centers in leaf_evidence_centers_by_band.items()
            if centers
        }
    )
    non_stub_leaf_evidence_texts = {
        text
        for band_id, role in zip(leaf_axis_ids, leaf_axis_roles, strict=True)
        if role != "stub"
        for text in leaf_evidence_texts_by_band.get(band_id, set())
        if text
    }
    group_eligible_anchor_band_ids = {
        band_id
        for band_id, role in zip(leaf_axis_ids, leaf_axis_roles, strict=True)
        if role != "stub"
        or bool(
            leaf_evidence_texts_by_band.get(band_id, set()).intersection(
                non_stub_leaf_evidence_texts
            )
        )
    }
    active_value_anchor_band_ids = [
        band_id
        for band_id in leaf_axis_ids
        if band_id in group_eligible_anchor_band_ids
        and band_id in header_anchor_x_by_band
    ]

    leaf_clusters = _cluster_header_evidence(leaf_evidence, horizontal_rules)
    group_evidence: list[HeaderTextEvidence] = list(direct_group_evidence)
    legacy_leaf_header_top = min(
        (item.canonical_bbox[1] for item in leaf_evidence),
        default=float("inf"),
    )
    for item in sorted(
        upper_evidence if leaf_floor is None else [],
        key=lambda value: value.canonical_bbox[1],
        reverse=True,
    ):
        item_center = (item.canonical_bbox[0] + item.canonical_bbox[2]) / 2.0
        rules_below = [
            (rule_y, reference)
            for rule_y, reference in horizontal_rules
            if item.canonical_bbox[3] - 1.0
            <= rule_y
            <= legacy_leaf_header_top + 1.0
            and min(
                reference.canonical_segment[0],
                reference.canonical_segment[2],
            )
            <= item_center
            <= max(
                reference.canonical_segment[0],
                reference.canonical_segment[2],
            )
        ]
        nearest_rule_y = min((rule_y for rule_y, _ in rules_below), default=None)
        covering_rules = [
            reference
            for rule_y, reference in rules_below
            if nearest_rule_y is not None and abs(rule_y - nearest_rule_y) <= 1.5
        ]
        rule_covered_band_ids = list(
            dict.fromkeys(
                band_id
                for reference in covering_rules
                for band_id in _covered_anchor_band_ids(
                    (
                        reference.canonical_segment[0],
                        reference.canonical_segment[2],
                    ),
                    leaf_axis_ids,
                    header_anchor_x_by_band,
                )
                if band_id in group_eligible_anchor_band_ids
            )
        )
        same_row_peer_items = [
            peer
            for peer in upper_evidence
            if run_rows[peer.evidence_id] == run_rows[item.evidence_id]
            and any(
                band_id in group_eligible_anchor_band_ids
                and bounds[0]
                <= (peer.canonical_bbox[0] + peer.canonical_bbox[2]) / 2.0
                <= bounds[1]
                for band_id, bounds in zip(
                    leaf_axis_ids,
                    leaf_axis_bounds,
                    strict=True,
                )
            )
        ]
        selected_rule_band_ids = rule_covered_band_ids
        peer_partition_band_ids: list[str] = []
        if len(same_row_peer_items) > 1:
            peer_centers = {
                peer.evidence_id: (
                    peer.canonical_bbox[0] + peer.canonical_bbox[2]
                )
                / 2.0
                for peer in same_row_peer_items
            }
            peer_partition_band_ids = [
                band_id
                for band_id in active_value_anchor_band_ids
                if min(
                    same_row_peer_items,
                    key=lambda peer: (
                        abs(
                            header_anchor_x_by_band[band_id]
                            - peer_centers[peer.evidence_id]
                        ),
                        peer_centers[peer.evidence_id],
                        peer.evidence_id,
                    ),
                ).evidence_id
                == item.evidence_id
            ]
        if (
            peer_partition_band_ids
            and (
                set(rule_covered_band_ids) == set(active_value_anchor_band_ids)
                or (
                    len(peer_partition_band_ids) >= 2
                    and bool(rule_covered_band_ids)
                    and set(rule_covered_band_ids).issubset(
                        peer_partition_band_ids
                    )
                )
            )
        ):
            selected_rule_band_ids = peer_partition_band_ids
        selected_rule_band_id_set = set(selected_rule_band_ids)
        rule_crosses_existing_group = any(
            selected_rule_band_id_set.intersection(existing_band_ids)
            and not selected_rule_band_id_set.issubset(existing_band_ids)
            and not set(existing_band_ids).issubset(selected_rule_band_id_set)
            for existing_band_ids in classified_group_band_ids.values()
        )
        if len(selected_rule_band_ids) >= 2 and not rule_crosses_existing_group:
            group_evidence.append(item)
            explicit_group_band_ids[item.evidence_id] = selected_rule_band_ids
            classified_group_band_ids[item.evidence_id] = selected_rule_band_ids
            explicit_group_rule_references[item.evidence_id] = (
                covering_rules
                if set(rule_covered_band_ids) == selected_rule_band_id_set
                else []
            )
            continue
        covered_band_ids = _covered_anchor_band_ids(
            (item.canonical_bbox[0], item.canonical_bbox[2]),
            leaf_axis_ids,
            header_anchor_x_by_band,
        )
        covered_value_band_ids = [
            band_id
            for band_id in covered_band_ids
            if band_id in group_eligible_anchor_band_ids
        ]
        if (
            len(covered_value_band_ids) >= 2
            and len(covered_value_band_ids) == len(covered_band_ids)
        ):
            group_evidence.append(item)
            explicit_group_band_ids[item.evidence_id] = covered_value_band_ids
            classified_group_band_ids[item.evidence_id] = covered_value_band_ids
            explicit_group_rule_references[item.evidence_id] = []
            continue
        matching_clusters = _matching_header_clusters(
            item,
            leaf_clusters,
            horizontal_rules,
            respect_intervening_rules=False,
        )
        if len(matching_clusters) == 1:
            matching_clusters[0].append(item)
            continue
        item_band = next(
            (
                band_id
                for band_id, bounds in zip(
                    leaf_axis_ids,
                    leaf_axis_bounds,
                    strict=True,
                )
                if bounds[0] <= item_center <= bounds[1]
            ),
            None,
        )
        represented = any(
            item_band is not None
            and leaf_axis_bounds[leaf_axis_ids.index(item_band)][0]
            <= (
                _cluster_x_bounds(cluster)[0]
                + _cluster_x_bounds(cluster)[1]
            )
            / 2.0
            <= leaf_axis_bounds[leaf_axis_ids.index(item_band)][1]
            for cluster in leaf_clusters
        )
        if not represented:
            leaf_clusters.append([item])
        else:
            group_evidence.append(item)

    attached_ids = {
        item.evidence_id for cluster in leaf_clusters for item in cluster
    }
    remaining_upper = [
        item
        for item in upper_evidence
        if item.evidence_id not in attached_ids
        and item.evidence_id not in {value.evidence_id for value in group_evidence}
    ]
    leaf_header_top = min(
        (item.canonical_bbox[1] for item in leaf_evidence),
        default=float("inf"),
    )
    direct_leaf_clusters: list[HeaderCluster] = []
    for item in remaining_upper:
        matching_direct_clusters = _matching_header_clusters(
            item,
            direct_leaf_clusters,
            horizontal_rules,
            respect_intervening_rules=False,
        )
        if len(matching_direct_clusters) == 1:
            matching_direct_clusters[0].append(item)
            continue
        item_center = (item.canonical_bbox[0] + item.canonical_bbox[2]) / 2.0
        rules_below = [
            (rule_y, reference)
            for rule_y, reference in horizontal_rules
            if item.canonical_bbox[3] - 1.0 <= rule_y <= leaf_header_top + 1.0
            and min(reference.canonical_segment[0], reference.canonical_segment[2])
            <= item_center
            <= max(reference.canonical_segment[0], reference.canonical_segment[2])
        ]
        nearest_rule_y = min((rule_y for rule_y, _ in rules_below), default=None)
        covering_internal_rules = [
            reference
            for rule_y, reference in rules_below
            if nearest_rule_y is not None and abs(rule_y - nearest_rule_y) <= 1.5
        ]
        rule_covered_band_ids = list(
            dict.fromkeys(
                band_id
                for reference in covering_internal_rules
                for band_id in _covered_anchor_band_ids(
                    (
                        reference.canonical_segment[0],
                        reference.canonical_segment[2],
                    ),
                    leaf_axis_ids,
                    header_anchor_x_by_band,
                )
                if band_id in group_eligible_anchor_band_ids
            )
        )
        item_covered_band_ids = _covered_anchor_band_ids(
            (item.canonical_bbox[0], item.canonical_bbox[2]),
            leaf_axis_ids,
            header_anchor_x_by_band,
        )
        item_covered_value_band_ids = [
            band_id
            for band_id in item_covered_band_ids
            if band_id in group_eligible_anchor_band_ids
        ]
        item_defines_group = (
            len(item_covered_value_band_ids) >= 2
            and len(item_covered_value_band_ids) == len(item_covered_band_ids)
        )
        same_row_peer_items = [
            peer
            for peer in remaining_upper
            if run_rows[peer.evidence_id] == run_rows[item.evidence_id]
            and any(
                band_id in group_eligible_anchor_band_ids
                and bounds[0]
                <= (peer.canonical_bbox[0] + peer.canonical_bbox[2]) / 2.0
                <= bounds[1]
                for band_id, bounds in zip(
                    leaf_axis_ids,
                    leaf_axis_bounds,
                    strict=True,
                )
            )
        ]
        peer_partition_band_ids: list[str] = []
        if len(same_row_peer_items) > 1:
            peer_centers = {
                peer.evidence_id: (
                    peer.canonical_bbox[0] + peer.canonical_bbox[2]
                )
                / 2.0
                for peer in same_row_peer_items
            }
            peer_partition_band_ids = [
                band_id
                for band_id in active_value_anchor_band_ids
                if min(
                    same_row_peer_items,
                    key=lambda peer: (
                        abs(
                            header_anchor_x_by_band[band_id]
                            - peer_centers[peer.evidence_id]
                        ),
                        peer_centers[peer.evidence_id],
                        peer.evidence_id,
                    ),
                ).evidence_id
                == item.evidence_id
            ]
        peer_partition_supported = bool(peer_partition_band_ids) and (
            set(rule_covered_band_ids) == set(active_value_anchor_band_ids)
            or (
                len(peer_partition_band_ids) >= 2
                and bool(rule_covered_band_ids)
                and set(rule_covered_band_ids).issubset(
                    peer_partition_band_ids
                )
            )
        )
        partition_band_id_set = set(peer_partition_band_ids)
        partition_crosses_existing_group = any(
            partition_band_id_set.intersection(existing_band_ids)
            and not partition_band_id_set.issubset(existing_band_ids)
            and not set(existing_band_ids).issubset(partition_band_id_set)
            for existing_band_ids in classified_group_band_ids.values()
        )
        peer_partition_defines_group = (
            len(peer_partition_band_ids) >= 2
            and peer_partition_supported
            and not partition_crosses_existing_group
        )
        rule_band_id_set = set(rule_covered_band_ids)
        rule_crosses_existing_group = any(
            rule_band_id_set.intersection(existing_band_ids)
            and not rule_band_id_set.issubset(existing_band_ids)
            and not set(existing_band_ids).issubset(rule_band_id_set)
            for existing_band_ids in classified_group_band_ids.values()
        )
        rule_defines_group = (
            len(rule_covered_band_ids) >= 2
            and not rule_crosses_existing_group
            and (
                set(rule_covered_band_ids) != set(active_value_anchor_band_ids)
                or value_evidence_count_by_row[run_rows[item.evidence_id]] == 1
            )
        )
        if item_defines_group or peer_partition_defines_group or rule_defines_group:
            group_evidence.append(item)
            selected_group_band_ids = (
                peer_partition_band_ids
                if peer_partition_defines_group
                else rule_covered_band_ids
                if rule_defines_group
                else item_covered_value_band_ids
                if item_defines_group
                else rule_covered_band_ids
            )
            classified_group_band_ids[item.evidence_id] = selected_group_band_ids
            explicit_group_band_ids[item.evidence_id] = selected_group_band_ids
            explicit_group_rule_references[item.evidence_id] = (
                covering_internal_rules
                if rule_defines_group
                and set(rule_covered_band_ids) == set(selected_group_band_ids)
                else []
            )
            continue
        matching_clusters = _matching_header_clusters(
            item,
            leaf_clusters,
            horizontal_rules,
            respect_intervening_rules=False,
        )
        if len(matching_clusters) == 1:
            matching_clusters[0].append(item)
        else:
            cluster = [item]
            leaf_clusters.append(cluster)
            direct_leaf_clusters.append(cluster)

    upper_evidence_by_row: dict[int, list[HeaderTextEvidence]] = defaultdict(list)
    for item in upper_evidence:
        item_center = (item.canonical_bbox[0] + item.canonical_bbox[2]) / 2.0
        if any(
            band_id in group_eligible_anchor_band_ids
            and bounds[0] <= item_center <= bounds[1]
            for band_id, bounds in zip(
                leaf_axis_ids,
                leaf_axis_bounds,
                strict=True,
            )
        ):
            upper_evidence_by_row[run_rows[item.evidence_id]].append(item)
    group_evidence_ids = {item.evidence_id for item in group_evidence}
    for row_items in upper_evidence_by_row.values():
        row_items = sorted(
            row_items,
            key=lambda item: (
                item.canonical_bbox[0] + item.canonical_bbox[2]
            )
            / 2.0,
        )
        if (
            len(row_items) < 3
            or len(active_value_anchor_band_ids) % len(row_items) != 0
            or sum(
                item.evidence_id in group_evidence_ids for item in row_items
            )
            < 2
        ):
            continue
        block_size = len(active_value_anchor_band_ids) // len(row_items)
        if block_size < 2:
            continue
        partition_band_ids_by_evidence_id = {
            item.evidence_id: active_value_anchor_band_ids[
                item_index * block_size : (item_index + 1) * block_size
            ]
            for item_index, item in enumerate(row_items)
        }
        nearest_rules_by_evidence_id: dict[
            str,
            list[TableBoundaryRuleReference],
        ] = {}
        rule_band_ids_by_evidence_id: dict[str, set[str]] = {}
        row_is_rule_supported = True
        for item in row_items:
            item_center = (
                item.canonical_bbox[0] + item.canonical_bbox[2]
            ) / 2.0
            local_rules = [
                (rule_y, reference)
                for rule_y, reference in horizontal_rules
                if item.canonical_bbox[3] - 1.0
                <= rule_y
                <= leaf_header_top + 1.0
                and min(
                    reference.canonical_segment[0],
                    reference.canonical_segment[2],
                )
                <= item_center
                <= max(
                    reference.canonical_segment[0],
                    reference.canonical_segment[2],
                )
            ]
            nearest_rule_y = min(
                (rule_y for rule_y, _ in local_rules),
                default=None,
            )
            nearest_rules = [
                reference
                for rule_y, reference in local_rules
                if nearest_rule_y is not None
                and abs(rule_y - nearest_rule_y) <= 1.5
            ]
            rule_band_ids = {
                band_id
                for reference in nearest_rules
                for band_id in _covered_anchor_band_ids(
                    (
                        reference.canonical_segment[0],
                        reference.canonical_segment[2],
                    ),
                    leaf_axis_ids,
                    header_anchor_x_by_band,
                )
                if band_id in group_eligible_anchor_band_ids
            }
            partition_band_ids = partition_band_ids_by_evidence_id[
                item.evidence_id
            ]
            if not rule_band_ids.intersection(partition_band_ids):
                row_is_rule_supported = False
                break
            nearest_rules_by_evidence_id[item.evidence_id] = nearest_rules
            rule_band_ids_by_evidence_id[item.evidence_id] = rule_band_ids
        if not row_is_rule_supported:
            continue
        for item in row_items:
            partition_band_ids = partition_band_ids_by_evidence_id[
                item.evidence_id
            ]
            classified_group_band_ids[item.evidence_id] = partition_band_ids
            explicit_group_band_ids[item.evidence_id] = partition_band_ids
            explicit_group_rule_references[item.evidence_id] = (
                nearest_rules_by_evidence_id[item.evidence_id]
                if rule_band_ids_by_evidence_id[item.evidence_id]
                == set(partition_band_ids)
                else []
            )
            if item.evidence_id in group_evidence_ids:
                continue
            group_evidence.append(item)
            group_evidence_ids.add(item.evidence_id)
            for cluster in leaf_clusters:
                cluster[:] = [
                    value
                    for value in cluster
                    if value.evidence_id != item.evidence_id
                ]

    header_parts_by_band: dict[
        str,
        list[tuple[float, float, str, str]],
    ] = defaultdict(list)
    evidence_ids_by_band: dict[str, list[str]] = defaultdict(list)
    for cluster in leaf_clusters:
        for item in cluster:
            overlap_by_band = [
                (
                    max(
                        0.0,
                        min(item.canonical_bbox[2], bounds[1])
                        - max(item.canonical_bbox[0], bounds[0]),
                    ),
                    (band_id, bounds),
                )
                for band_id, bounds in zip(
                    leaf_axis_ids,
                    leaf_axis_bounds,
                    strict=True,
                )
            ]
            maximum_overlap = max(
                (overlap for overlap, _ in overlap_by_band),
                default=0.0,
            )
            matching_bands = [
                band
                for overlap, band in overlap_by_band
                if maximum_overlap > 0.0 and abs(overlap - maximum_overlap) <= 0.5
            ]
            if len(matching_bands) > 1:
                item_center = (
                    item.canonical_bbox[0] + item.canonical_bbox[2]
                ) / 2.0
                center_bands = [
                    band
                    for band in matching_bands
                    if band[1][0]
                    <= item_center
                    <= band[1][1]
                ]
                if len(center_bands) == 1:
                    matching_bands = center_bands
            if len(matching_bands) != 1:
                concerns.append(
                    f"ambiguous_header_evidence_band:{item.evidence_id}"
                )
                continue
            selected_band_id = matching_bands[0][0]
            header_parts_by_band[selected_band_id].append(
                (
                    item.canonical_bbox[1],
                    item.canonical_bbox[0],
                    item.evidence_id,
                    item.text,
                )
            )
            evidence_ids_by_band[selected_band_id].append(item.evidence_id)

            word_band_ids: list[str] = []
            for _, _, word_bbox in run_words.get(item.evidence_id, []):
                word_center = (word_bbox[0] + word_bbox[2]) / 2.0
                word_band = next(
                    (
                        band_id
                        for band_id, bounds in zip(
                            leaf_axis_ids,
                            leaf_axis_bounds,
                            strict=True,
                        )
                        if bounds[0]
                        <= word_center
                        <= bounds[1]
                    ),
                    None,
                )
                if word_band is not None and word_band not in word_band_ids:
                    word_band_ids.append(word_band)
            observed_band_ids = _covered_anchor_band_ids(
                (item.canonical_bbox[0], item.canonical_bbox[2]),
                leaf_axis_ids,
                observed_anchor_x_by_band,
            )
            if (
                len(word_band_ids) > 1
                and set(observed_band_ids) != {selected_band_id}
            ):
                concerns.append(
                    "header_evidence_words_cross_occupancy_bands:"
                    f"{item.evidence_id}:bands={','.join(word_band_ids)}"
                )

    leaves: list[HeaderLeafCandidate] = []
    for band_id, band_role, bounds in zip(
        leaf_axis_ids,
        leaf_axis_roles,
        leaf_axis_bounds,
        strict=True,
    ):
        header_parts = sorted(header_parts_by_band.get(band_id, []))
        label = clean_text(" ".join(part[3] for part in header_parts))
        if not label:
            concerns.append(
                "blank_stub_header_candidate"
                if band_role == "stub"
                else f"header_band_without_text:{band_id}"
            )
        leaves.append(
            HeaderLeafCandidate(
                leaf_id=f"{candidate_id}:leaf:{len(leaves)}",
                leaf_index=len(leaves),
                label=label,
                canonical_x_bounds=bounds,
                evidence_ids=evidence_ids_by_band.get(band_id, []),
                occupancy_band_ids=[band_id],
                occupancy_alignment="one_to_one",
            )
        )

    groups: list[HeaderGroupCandidate] = []
    relationships: list[HeaderStructureRelationship] = []
    leaf_centers = {
        leaf.leaf_id: sum(leaf.canonical_x_bounds) / 2.0 for leaf in leaves
    }
    leaf_id_by_band_id = {
        leaf.occupancy_band_ids[0]: leaf.leaf_id
        for leaf in leaves
        if leaf.occupancy_band_ids
    }
    group_clusters = _cluster_header_evidence(group_evidence, horizontal_rules)
    ordered_group_clusters = sorted(
        group_clusters,
        key=lambda cluster: (
            _cluster_x_bounds(cluster)[0]
            + _cluster_x_bounds(cluster)[1]
        )
        / 2.0,
    )
    group_centers = [
        (
            _cluster_x_bounds(cluster)[0]
            + _cluster_x_bounds(cluster)[1]
        )
        / 2.0
        for cluster in ordered_group_clusters
    ]
    for group_index, cluster in enumerate(ordered_group_clusters):
        item_center = group_centers[group_index]
        explicit_band_ids = [
            band_id
            for band_id in leaf_axis_ids
            if any(
                band_id in explicit_group_band_ids.get(item.evidence_id, [])
                for item in cluster
            )
        ]
        if explicit_band_ids:
            rule_references = list(
                {
                    (reference.source, reference.source_index): reference
                    for item in cluster
                    for reference in explicit_group_rule_references.get(
                        item.evidence_id,
                        [],
                    )
                }.values()
            )
            if rule_references:
                group_left = min(
                    min(
                        reference.canonical_segment[0],
                        reference.canonical_segment[2],
                    )
                    for reference in rule_references
                )
                group_right = max(
                    max(
                        reference.canonical_segment[0],
                        reference.canonical_segment[2],
                    )
                    for reference in rule_references
                )
            else:
                group_left, group_right = _cluster_x_bounds(cluster)
            child_ids = [
                leaf_id_by_band_id[band_id]
                for band_id in explicit_band_ids
                if band_id in leaf_id_by_band_id
            ]
        else:
            item_bottom = max(item.canonical_bbox[3] for item in cluster)
            domain_left = (
                (group_centers[group_index - 1] + item_center) / 2.0
                if group_index > 0
                else float("-inf")
            )
            domain_right = (
                (item_center + group_centers[group_index + 1]) / 2.0
                if group_index + 1 < len(group_centers)
                else float("inf")
            )
            rule_candidates = [
                (rule_y, reference)
                for rule_y, reference in horizontal_rules
                if rule_y >= item_bottom - 1.0
            ]
            nearest_rule_y = min(
                (rule_y for rule_y, _ in rule_candidates),
                default=None,
            )
            rule_references = [
                reference
                for rule_y, reference in rule_candidates
                if nearest_rule_y is not None
                and abs(rule_y - nearest_rule_y) <= 1.5
                and min(
                    reference.canonical_segment[0],
                    reference.canonical_segment[2],
                )
                <= item_center
                <= max(
                    reference.canonical_segment[0],
                    reference.canonical_segment[2],
                )
            ]
            if rule_references and nearest_rule_y is not None:
                group_left = min(
                    min(
                        reference.canonical_segment[0],
                        reference.canonical_segment[2],
                    )
                    for reference in rule_references
                )
                group_right = max(
                    max(
                        reference.canonical_segment[0],
                        reference.canonical_segment[2],
                    )
                    for reference in rule_references
                )
                if group_index == 0:
                    outside_left_centers = [
                        center
                        for center in leaf_centers.values()
                        if center < group_left - 1.0
                    ]
                    if outside_left_centers:
                        domain_left = max(
                            domain_left,
                            (max(outside_left_centers) + item_center) / 2.0,
                        )
                same_y_references = [
                    reference
                    for rule_y, reference in rule_candidates
                    if abs(rule_y - nearest_rule_y) <= 1.5
                    and reference not in rule_references
                    and domain_left
                    <= (
                        reference.canonical_segment[0]
                        + reference.canonical_segment[2]
                    )
                    / 2.0
                    <= domain_right
                ]
                changed = True
                while changed:
                    changed = False
                    for reference in list(same_y_references):
                        left = min(
                            reference.canonical_segment[0],
                            reference.canonical_segment[2],
                        )
                        right = max(
                            reference.canonical_segment[0],
                            reference.canonical_segment[2],
                        )
                        if left <= group_right + 1.0 and right >= group_left - 1.0:
                            rule_references.append(reference)
                            same_y_references.remove(reference)
                            group_left = min(group_left, left)
                            group_right = max(group_right, right)
                            changed = True
            if rule_references:
                group_left = min(
                    min(
                        reference.canonical_segment[0],
                        reference.canonical_segment[2],
                    )
                    for reference in rule_references
                )
                group_right = max(
                    max(
                        reference.canonical_segment[0],
                        reference.canonical_segment[2],
                    )
                    for reference in rule_references
                )
            else:
                group_left = (
                    domain_left
                    if domain_left != float("-inf")
                    else min(leaf_centers.values(), default=item_center)
                )
                group_right = (
                    domain_right
                    if domain_right != float("inf")
                    else max(leaf_centers.values(), default=item_center)
                )
            child_ids = [
                leaf_id
                for leaf_id, center in leaf_centers.items()
                if group_left - 1.0 <= center <= group_right + 1.0
            ]
        if not child_ids:
            concerns.append(
                "unresolved_upper_header_run:"
                + ",".join(item.evidence_id for item in cluster)
            )
            continue
        group_label = clean_text(
            " ".join(
                item.text
                for item in sorted(
                    cluster,
                    key=lambda value: (
                        value.canonical_bbox[1],
                        value.canonical_bbox[0],
                    ),
                )
            )
        )
        group_id = f"{candidate_id}:group:{len(groups)}"
        groups.append(
            HeaderGroupCandidate(
                group_id=group_id,
                label=group_label,
                canonical_x_bounds=(group_left, group_right),
                leaf_ids=child_ids,
                evidence_ids=[item.evidence_id for item in cluster],
                rule_references=rule_references,
            )
        )
        for child_id in child_ids:
            relationships.append(
                HeaderStructureRelationship(
                    relationship_id=f"{candidate_id}:relationship:{len(relationships)}",
                    parent_group_id=group_id,
                    child_leaf_id=child_id,
                )
            )

    marker_char_bboxes = dict(
        zip(evidence.char_indices, evidence.canonical_char_bboxes, strict=False)
    )
    node_ids_by_evidence_id: dict[str, list[str]] = defaultdict(list)
    nodes_by_id: dict[str, HeaderLeafCandidate | HeaderGroupCandidate] = {}
    for leaf in leaves:
        nodes_by_id[leaf.leaf_id] = leaf
        for evidence_id in leaf.evidence_ids:
            node_ids_by_evidence_id[evidence_id].append(leaf.leaf_id)
    for group in groups:
        nodes_by_id[group.group_id] = group
        for evidence_id in group.evidence_ids:
            node_ids_by_evidence_id[evidence_id].append(group.group_id)
    marker_attachment_candidates: list[HeaderMarkerAttachmentCandidate] = []
    for annotation_index, annotation in enumerate(
        annotation_table.annotations if annotation_table is not None else []
    ):
        if annotation.row_idx not in evidence_header_rows:
            continue
        marker_bboxes = [
            marker_char_bboxes[index]
            for index in annotation.source_char_indices
            if index in marker_char_bboxes
        ]
        marker_id = annotation.annotation_id or f"{table.table_id}:marker:{annotation_index}"
        source_line_ids = {
            reference.line_id for reference in annotation.source_span_references
        }
        source_evidence = [
            item
            for item in header_evidence
            if source_line_ids.intersection(item.source_line_ids)
        ]
        if not source_evidence:
            source_evidence = [
                item
                for item in header_evidence
                if annotation.row_idx in item.header_row_indices
            ]
        selected_evidence_ids: list[str] = []
        if marker_bboxes and source_evidence:
            marker_left = min(bbox[0] for bbox in marker_bboxes)
            marker_right = max(bbox[2] for bbox in marker_bboxes)
            distances = [
                (
                    max(
                        0.0,
                        item.canonical_bbox[0] - marker_right,
                        marker_left - item.canonical_bbox[2],
                    ),
                    item.evidence_id,
                )
                for item in source_evidence
            ]
            minimum_distance = min(distance for distance, _ in distances)
            selected_evidence_ids = [
                evidence_id
                for distance, evidence_id in distances
                if abs(distance - minimum_distance) <= 0.5
            ]
        elif len(source_evidence) == 1:
            selected_evidence_ids = [source_evidence[0].evidence_id]
        candidate_node_ids = list(
            dict.fromkeys(
                node_id
                for evidence_id in selected_evidence_ids
                for node_id in node_ids_by_evidence_id.get(evidence_id, [])
            )
        )
        if marker_bboxes and len(candidate_node_ids) > 1:
            marker_center = (
                min(bbox[0] for bbox in marker_bboxes)
                + max(bbox[2] for bbox in marker_bboxes)
            ) / 2.0
            geometrically_matching_node_ids = [
                node_id
                for node_id in candidate_node_ids
                if nodes_by_id[node_id].canonical_x_bounds[0] - 1.0
                <= marker_center
                <= nodes_by_id[node_id].canonical_x_bounds[1] + 1.0
            ]
            if geometrically_matching_node_ids:
                candidate_node_ids = geometrically_matching_node_ids
        selected_node_id = (
            candidate_node_ids[0] if len(candidate_node_ids) == 1 else None
        )
        status = (
            "linked"
            if selected_node_id is not None
            else "ambiguous"
            if candidate_node_ids
            else "unresolved"
        )
        if selected_node_id is not None:
            nodes_by_id[selected_node_id].marker_ids.append(marker_id)
        else:
            concerns.append(f"{status}_header_marker_attachment:{marker_id}")
        marker_attachment_candidates.append(
            HeaderMarkerAttachmentCandidate(
                attachment_id=(
                    f"{candidate_id}:marker_attachment:"
                    f"{len(marker_attachment_candidates)}"
                ),
                marker_id=marker_id,
                source_evidence_ids=selected_evidence_ids,
                candidate_node_ids=candidate_node_ids,
                selected_node_id=selected_node_id,
                status=status,
            )
        )

    if len(leaves) not in {0, len(leaf_axis_ids)}:
        diagnostics.append("header_leaf_geometry_disagrees")

    return HeaderStructureCandidate(
        candidate_id=candidate_id,
        table_id=table.table_id,
        page_num=table.page_num,
        source_artifacts=source_artifacts,
        header_row_indices=list(header_rows),
        body_row_indices=list(body_rows),
        occupancy_band_ids=leaf_axis_ids,
        leaf_candidates=leaves,
        group_candidates=groups,
        relationships=relationships,
        marker_attachment_candidates=marker_attachment_candidates,
        evidence=header_evidence,
        concerns=list(dict.fromkeys(concerns)),
        diagnostics=list(dict.fromkeys(diagnostics)),
    )


def header_structure_candidates_to_payload(
    candidates: Sequence[HeaderStructureCandidate],
) -> list[dict[str, object]]:
    """Serialize header structure candidates as JSON-friendly records."""
    payload = [candidate.model_dump(mode="json") for candidate in candidates]
    for candidate, item in zip(candidates, payload, strict=True):
        for leaf, leaf_payload in zip(
            candidate.leaf_candidates,
            item["leaf_candidates"],
            strict=True,
        ):
            if leaf.label_source == "local_positioned_text":
                for key in (
                    "label_source",
                    "local_label",
                    "inherited_from_table_id",
                    "inherited_from_leaf_id",
                    "inherited_from_page_num",
                    "inheritance_evidence",
                ):
                    leaf_payload.pop(key, None)
    return payload
