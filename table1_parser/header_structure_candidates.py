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
    TablePositionedEvidence,
    TableRegion,
)
from table1_parser.text_cleaning import clean_text


def inherit_adjacent_continuation_leaf_labels(
    extracted_tables: Sequence[ExtractedTable],
    candidates: Sequence[HeaderStructureCandidate],
) -> list[HeaderStructureCandidate]:
    """Fill blank leaves only for an established adjacent continuation structure."""
    updated = list(candidates)
    candidate_index = {
        candidate.table_id: index for index, candidate in enumerate(updated)
    }
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
                continuation_number is not None and continuation_number != parent_number
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
            or any(
                not leaf.occupancy_band_ids
                for leaf in [*parent_leaves, *continuation_leaves]
            )
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
            if group.leaf_ids
            and all(leaf_id in parent_leaf_index for leaf_id in group.leaf_ids)
        )
        continuation_groups = sorted(
            (
                clean_text(group.label).casefold(),
                tuple(
                    sorted(
                        continuation_leaf_index[leaf_id] for leaf_id in group.leaf_ids
                    )
                ),
            )
            for group in continuation.group_candidates
            if group.leaf_ids
            and all(leaf_id in continuation_leaf_index for leaf_id in group.leaf_ids)
        )
        explicit_identity = continuation_number == parent_number
        if (
            not explicit_identity
            and (not parent_groups or parent_groups != continuation_groups)
        ) or any(
            clean_text(local.label)
            and clean_text(source.label)
            and clean_text(local.label).casefold()
            != clean_text(source.label).casefold()
            for source, local in zip(
                parent_leaves,
                continuation_leaves,
                strict=True,
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
        inheritance_evidence = [
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
                            "raw_text": source.label,
                            "base_text": source.label,
                            "label_source": "inherited_continuation",
                            "local_label": local.label,
                            "inherited_from_table_id": parent_table.table_id,
                            "inherited_from_leaf_id": source.leaf_id,
                            "inherited_from_page_num": parent_table.page_num,
                            "inheritance_evidence": inheritance_evidence,
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
    leaf_tables = {
        candidate.table_id: candidate for candidate in leaf_column_candidates
    }
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
    """Build one header candidate directly from settled rows and geometry."""
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
    leaf_ids = [
        f"{candidate_id}:leaf:{leaf_index}" for leaf_index in range(len(local_bands))
    ]

    horizontal_rules: list[tuple[float, TableBoundaryRuleReference]] = []
    seen_rule_references: set[tuple[str, int]] = set()
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
            if (
                abs(segment[3] - segment[1]) > 1.5
                or (source, source_index) in seen_rule_references
            ):
                continue
            seen_rule_references.add((source, source_index))
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

    raw_rule_levels: list[list[tuple[float, TableBoundaryRuleReference]]] = []
    for rule in sorted(horizontal_rules, key=lambda item: item[0]):
        if not raw_rule_levels or rule[0] - raw_rule_levels[-1][-1][0] > 1.5:
            raw_rule_levels.append([rule])
        else:
            raw_rule_levels[-1].append(rule)
    rule_levels = [
        (
            median(rule_y for rule_y, _ in level),
            [reference for _, reference in level],
        )
        for level in raw_rule_levels
    ]
    rule_domains_by_y: dict[
        float,
        list[tuple[float, float, list[TableBoundaryRuleReference]]],
    ] = {}
    for rule_y, level_references in rule_levels:
        domains: list[tuple[float, float, list[TableBoundaryRuleReference]]] = []
        for reference in sorted(
            level_references,
            key=lambda item: min(
                item.canonical_segment[0],
                item.canonical_segment[2],
            ),
        ):
            left, right = sorted(
                (
                    reference.canonical_segment[0],
                    reference.canonical_segment[2],
                )
            )
            if domains and left <= domains[-1][1] + 1.5:
                domains[-1] = (
                    domains[-1][0],
                    max(domains[-1][1], right),
                    [*domains[-1][2], reference],
                )
            else:
                domains.append((left, right, [reference]))
        rule_domains_by_y[rule_y] = domains

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
            for row_idx in header_rows
            if row_bounds[row_idx][0] - 1.0 <= center_y <= row_bounds[row_idx][1] + 1.0
        ]
        if not candidate_rows or not word.text.strip():
            continue
        row_idx = min(
            candidate_rows,
            key=lambda item: abs(center_y - sum(row_bounds[item]) / 2.0),
        )
        source_line_id = line_id_by_position.get(
            (word.block_index, word.line_index),
            f"{table.table_id}:header:row:{row_idx}",
        )
        words_by_row_line[(row_idx, source_line_id)].append(
            (word_index, word.text, bbox)
        )

    header_evidence: list[HeaderTextEvidence] = []
    for (row_idx, source_line_id), words in sorted(words_by_row_line.items()):
        words.sort(key=lambda item: item[2][0])
        heights = [bbox[3] - bbox[1] for _, _, bbox in words if bbox[3] > bbox[1]]
        gap_limit = max(3.0, median(heights) * 0.6) if heights else 4.0
        runs: list[list[tuple[int, str, tuple[float, float, float, float]]]] = []
        for word in words:
            if not runs or word[2][0] - runs[-1][-1][2][2] > gap_limit:
                runs.append([word])
            else:
                runs[-1].append(word)
        for run in runs:
            evidence_id = f"{candidate_id}:evidence:{len(header_evidence)}"
            header_evidence.append(
                HeaderTextEvidence(
                    evidence_id=evidence_id,
                    text=clean_text(" ".join(item[1] for item in run)),
                    header_row_indices=[row_idx],
                    source_line_ids=[source_line_id],
                    source_word_indices=[item[0] for item in run],
                    canonical_bbox=(
                        min(item[2][0] for item in run),
                        min(item[2][1] for item in run),
                        max(item[2][2] for item in run),
                        max(item[2][3] for item in run),
                    ),
                )
            )

    header_bottom = max(row_bounds[row_idx][1] for row_idx in header_rows)
    unruled_separator_y = header_bottom + 4.0
    evidence_by_separator: dict[float, list[HeaderTextEvidence]] = defaultdict(list)
    for item in header_evidence:
        row_bottom = max(row_bounds[row_idx][1] for row_idx in item.header_row_indices)
        item_center = (item.canonical_bbox[0] + item.canonical_bbox[2]) / 2.0
        possible_levels = [
            rule_y
            for rule_y, _ in rule_levels
            if row_bottom - 2.0 <= rule_y <= header_bottom + 4.0
            and any(
                left - 1.0 <= item_center <= right + 1.0
                for left, right, _ in rule_domains_by_y[rule_y]
            )
        ]
        evidence_by_separator[
            min(possible_levels) if possible_levels else unruled_separator_y
        ].append(item)

    leaf_parts: dict[int, list[HeaderTextEvidence]] = defaultdict(list)
    assigned_evidence_ids: set[str] = set()
    diagnosed_evidence_ids: set[str] = set()
    groups: list[HeaderGroupCandidate] = []
    relationships: list[HeaderStructureRelationship] = []
    group_coverages: list[tuple[int, int]] = []
    if header_evidence:
        leaf_separator_y = max(evidence_by_separator)
        leaf_band_item_anchors: dict[int, list[float]] = defaultdict(list)
        for item in evidence_by_separator[leaf_separator_y]:
            overlaps = [
                max(
                    0.0,
                    min(item.canonical_bbox[2], right)
                    - max(item.canonical_bbox[0], left),
                )
                for left, right in leaf_axis_bounds
            ]
            if overlaps:
                maximum_overlap = max(overlaps)
                matching_indices = [
                    index
                    for index, overlap in enumerate(overlaps)
                    if abs(overlap - maximum_overlap) <= 0.5
                ]
                item_center = (item.canonical_bbox[0] + item.canonical_bbox[2]) / 2.0
                leaf_band_item_anchors[
                    min(
                        matching_indices,
                        key=lambda index: abs(
                            item_center - sum(leaf_axis_bounds[index]) / 2.0
                        ),
                    )
                ].append(item_center)
        for item in sorted(
            evidence_by_separator[leaf_separator_y],
            key=lambda value: value.canonical_bbox[0],
        ):
            item_center = (item.canonical_bbox[0] + item.canonical_bbox[2]) / 2.0
            supporting_references = [
                reference
                for reference in next(
                    (
                        references
                        for rule_y, references in rule_levels
                        if rule_y == leaf_separator_y
                    ),
                    [],
                )
                if min(
                    reference.canonical_segment[0],
                    reference.canonical_segment[2],
                )
                - 1.0
                <= item_center
                <= max(
                    reference.canonical_segment[0],
                    reference.canonical_segment[2],
                )
                + 1.0
            ]
            if supporting_references:
                supporting_width = min(
                    abs(reference.canonical_segment[2] - reference.canonical_segment[0])
                    for reference in supporting_references
                )
                supporting_references = [
                    reference
                    for reference in supporting_references
                    if abs(
                        abs(
                            reference.canonical_segment[2]
                            - reference.canonical_segment[0]
                        )
                        - supporting_width
                    )
                    <= 1.0
                ]
                support_left = min(
                    min(
                        reference.canonical_segment[0],
                        reference.canonical_segment[2],
                    )
                    for reference in supporting_references
                )
                support_right = max(
                    max(
                        reference.canonical_segment[0],
                        reference.canonical_segment[2],
                    )
                    for reference in supporting_references
                )
                directly_covered_indices = [
                    index
                    for index, (left, right) in enumerate(leaf_axis_bounds)
                    if leaf_axis_roles[index] != "stub"
                    and (
                        any(
                            support_left - 1.0 <= anchor <= support_right + 1.0
                            for anchor in leaf_band_item_anchors[index]
                        )
                        if leaf_band_item_anchors[index]
                        else (
                            support_left - 1.0
                            <= (left + right) / 2.0
                            <= support_right + 1.0
                            or max(
                                0.0,
                                min(support_right, right) - max(support_left, left),
                            )
                            >= 0.2 * (right - left)
                        )
                    )
                ]
                if (
                    len(directly_covered_indices) >= 2
                    and directly_covered_indices
                    == list(
                        range(
                            directly_covered_indices[0],
                            directly_covered_indices[-1] + 1,
                        )
                    )
                    and item.canonical_bbox[2] - item.canonical_bbox[0]
                    >= 0.5 * (support_right - support_left)
                ):
                    group_id = f"{candidate_id}:group:{len(groups)}"
                    child_ids = [leaf_ids[index] for index in directly_covered_indices]
                    groups.append(
                        HeaderGroupCandidate(
                            group_id=group_id,
                            label=item.text,
                            raw_text=item.text,
                            base_text=item.text,
                            canonical_x_bounds=(
                                leaf_axis_bounds[directly_covered_indices[0]][0],
                                leaf_axis_bounds[directly_covered_indices[-1]][1],
                            ),
                            leaf_ids=child_ids,
                            evidence_ids=[item.evidence_id],
                            rule_references=list(
                                {
                                    (
                                        reference.source,
                                        reference.source_index,
                                    ): reference
                                    for reference in supporting_references
                                }.values()
                            ),
                        )
                    )
                    for child_id in child_ids:
                        relationships.append(
                            HeaderStructureRelationship(
                                relationship_id=(
                                    f"{candidate_id}:relationship:{len(relationships)}"
                                ),
                                parent_group_id=group_id,
                                child_leaf_id=child_id,
                            )
                        )
                    group_coverages.append(
                        (
                            directly_covered_indices[0],
                            directly_covered_indices[-1],
                        )
                    )
                    assigned_evidence_ids.add(item.evidence_id)
                    continue
            overlaps = [
                max(
                    0.0,
                    min(item.canonical_bbox[2], right)
                    - max(item.canonical_bbox[0], left),
                )
                for left, right in leaf_axis_bounds
            ]
            if not overlaps:
                continue
            maximum_overlap = max(overlaps)
            if maximum_overlap > 0.0:
                matching_indices = [
                    index
                    for index, overlap in enumerate(overlaps)
                    if abs(overlap - maximum_overlap) <= 0.5
                ]
                leaf_index = min(
                    matching_indices,
                    key=lambda index: abs(
                        item_center - sum(leaf_axis_bounds[index]) / 2.0
                    ),
                )
                if len(matching_indices) > 1:
                    concerns.append(
                        f"ambiguous_leaf_band_assignment:{item.evidence_id}"
                    )
            else:
                leaf_index = min(
                    range(len(leaf_axis_bounds)),
                    key=lambda index: abs(
                        item_center - sum(leaf_axis_bounds[index]) / 2.0
                    ),
                )
                concerns.append(f"nearest_leaf_band_assignment:{item.evidence_id}")
            leaf_parts[leaf_index].append(item)
            assigned_evidence_ids.add(item.evidence_id)

        for separator_y in sorted(
            (value for value in evidence_by_separator if value != leaf_separator_y),
            reverse=True,
        ):
            clusters: list[list[HeaderTextEvidence]] = []
            for item in sorted(
                evidence_by_separator[separator_y],
                key=lambda value: (
                    value.canonical_bbox[1],
                    value.canonical_bbox[0],
                ),
            ):
                item_width = item.canonical_bbox[2] - item.canonical_bbox[0]
                matching_clusters: list[list[HeaderTextEvidence]] = []
                for cluster in clusters:
                    cluster_left = min(part.canonical_bbox[0] for part in cluster)
                    cluster_right = max(part.canonical_bbox[2] for part in cluster)
                    overlap = max(
                        0.0,
                        min(item.canonical_bbox[2], cluster_right)
                        - max(item.canonical_bbox[0], cluster_left),
                    )
                    if overlap >= 0.35 * min(
                        item_width,
                        cluster_right - cluster_left,
                    ):
                        matching_clusters.append(cluster)
                if len(matching_clusters) == 1:
                    matching_clusters[0].append(item)
                else:
                    clusters.append([item])

            domains = rule_domains_by_y.get(separator_y, [])

            clusters_by_domain: dict[int, list[list[HeaderTextEvidence]]] = defaultdict(
                list
            )
            unmatched_clusters: list[list[HeaderTextEvidence]] = []
            for cluster in clusters:
                cluster_center = (
                    min(item.canonical_bbox[0] for item in cluster)
                    + max(item.canonical_bbox[2] for item in cluster)
                ) / 2.0
                matching_domains = [
                    index
                    for index, (left, right, _) in enumerate(domains)
                    if left - 1.0 <= cluster_center <= right + 1.0
                ]
                if matching_domains:
                    domain_index = min(
                        matching_domains,
                        key=lambda index: domains[index][1] - domains[index][0],
                    )
                    clusters_by_domain[domain_index].append(cluster)
                else:
                    unmatched_clusters.append(cluster)

            cluster_assignments: list[
                tuple[
                    list[HeaderTextEvidence],
                    list[int],
                    list[TableBoundaryRuleReference],
                    tuple[float, float] | None,
                ]
            ] = []
            leaf_anchors = [
                median(
                    (item.canonical_bbox[0] + item.canonical_bbox[2]) / 2.0
                    for item in leaf_parts[index]
                )
                if leaf_parts[index]
                else sum(bounds) / 2.0
                for index, bounds in enumerate(leaf_axis_bounds)
            ]
            for domain_index, peer_clusters in clusters_by_domain.items():
                domain_left, domain_right, domain_references = domains[domain_index]
                covered_indices = [
                    index
                    for index, anchor in enumerate(leaf_anchors)
                    if leaf_axis_roles[index] != "stub"
                    and domain_left - 1.0 <= anchor <= domain_right + 1.0
                ]
                ordered_peers = sorted(
                    peer_clusters,
                    key=lambda cluster: (
                        (
                            min(item.canonical_bbox[0] for item in cluster)
                            + max(item.canonical_bbox[2] for item in cluster)
                        )
                        / 2.0
                    ),
                )
                remaining_peers: list[list[HeaderTextEvidence]] = []
                for cluster in ordered_peers:
                    peer_center = (
                        min(item.canonical_bbox[0] for item in cluster)
                        + max(item.canonical_bbox[2] for item in cluster)
                    ) / 2.0
                    matching_stub_indices = [
                        index
                        for index, (left, right) in enumerate(leaf_axis_bounds)
                        if leaf_axis_roles[index] == "stub"
                        and left - 1.0 <= peer_center <= right + 1.0
                    ]
                    if len(matching_stub_indices) == 1:
                        cluster_assignments.append(
                            (
                                cluster,
                                matching_stub_indices,
                                domain_references,
                                (domain_left, domain_right),
                            )
                        )
                    else:
                        remaining_peers.append(cluster)
                ordered_peers = remaining_peers
                if not ordered_peers:
                    continue
                local_assignments: list[
                    tuple[
                        list[int],
                        list[TableBoundaryRuleReference],
                        tuple[float, float],
                    ]
                    | None
                ] = []
                ordered_peer_centers = [
                    (
                        min(item.canonical_bbox[0] for item in cluster)
                        + max(item.canonical_bbox[2] for item in cluster)
                    )
                    / 2.0
                    for cluster in ordered_peers
                ]
                for peer_index, cluster in enumerate(ordered_peers):
                    cluster_center = (
                        min(item.canonical_bbox[0] for item in cluster)
                        + max(item.canonical_bbox[2] for item in cluster)
                    ) / 2.0
                    references_by_segment: dict[
                        tuple[float, float],
                        list[TableBoundaryRuleReference],
                    ] = defaultdict(list)
                    for reference in domain_references:
                        left, right = sorted(
                            (
                                reference.canonical_segment[0],
                                reference.canonical_segment[2],
                            )
                        )
                        if left - 1.0 <= cluster_center <= right + 1.0:
                            if any(
                                index != peer_index
                                and left - 1.0 <= peer_center <= right + 1.0
                                for index, peer_center in enumerate(
                                    ordered_peer_centers
                                )
                            ):
                                continue
                            references_by_segment[
                                (round(left, 1), round(right, 1))
                            ].append(reference)
                    options = [
                        (
                            [
                                index
                                for index, anchor in enumerate(leaf_anchors)
                                if leaf_axis_roles[index] != "stub"
                                and left - 1.0 <= anchor <= right + 1.0
                            ],
                            references,
                            (left, right),
                        )
                        for (left, right), references in references_by_segment.items()
                    ]
                    multileaf_options = [
                        option
                        for option in options
                        if len(option[0]) >= 2
                        and option[0] == list(range(option[0][0], option[0][-1] + 1))
                    ]
                    single_leaf_options = [
                        option for option in options if len(option[0]) == 1
                    ]
                    local_assignments.append(
                        min(
                            multileaf_options,
                            key=lambda option: option[2][1] - option[2][0],
                        )
                        if multileaf_options
                        else min(
                            single_leaf_options,
                            key=lambda option: option[2][1] - option[2][0],
                        )
                        if single_leaf_options
                        else None
                    )
                if any(
                    assignment is not None and len(assignment[0]) >= 2
                    for assignment in local_assignments
                ):
                    claimed_indices = [
                        index
                        for assignment in local_assignments
                        if assignment is not None
                        for index in assignment[0]
                    ]
                    remaining_runs: list[list[int]] = []
                    for index in (
                        value
                        for value in covered_indices
                        if value not in claimed_indices
                    ):
                        if not remaining_runs or index != remaining_runs[-1][-1] + 1:
                            remaining_runs.append([index])
                        else:
                            remaining_runs[-1].append(index)
                    if len(claimed_indices) == len(set(claimed_indices)) and sum(
                        assignment is None for assignment in local_assignments
                    ) == len(remaining_runs):
                        remaining_run_index = 0
                        for cluster, assignment in zip(
                            ordered_peers,
                            local_assignments,
                            strict=True,
                        ):
                            if assignment is None:
                                cluster_assignments.append(
                                    (
                                        cluster,
                                        remaining_runs[remaining_run_index],
                                        domain_references,
                                        (domain_left, domain_right),
                                    )
                                )
                                remaining_run_index += 1
                            else:
                                cluster_assignments.append(
                                    (
                                        cluster,
                                        assignment[0],
                                        assignment[1],
                                        assignment[2],
                                    )
                                )
                        continue
                if not covered_indices:
                    for cluster in ordered_peers:
                        cluster_assignments.append(
                            (
                                cluster,
                                [],
                                domain_references,
                                (domain_left, domain_right),
                            )
                        )
                    continue
                peer_starts = [
                    min(
                        covered_indices,
                        key=lambda index: abs(
                            leaf_anchors[index]
                            - min(item.canonical_bbox[0] for item in cluster)
                        ),
                    )
                    for cluster in ordered_peers
                ]
                assigned_indices_by_peer: dict[int, list[int]] = defaultdict(list)
                for leaf_index in covered_indices:
                    eligible_peers = [
                        index
                        for index, start in enumerate(peer_starts)
                        if start <= leaf_index
                    ]
                    if eligible_peers:
                        assigned_indices_by_peer[
                            max(eligible_peers, key=peer_starts.__getitem__)
                        ].append(leaf_index)
                for peer_index, cluster in enumerate(ordered_peers):
                    cluster_assignments.append(
                        (
                            cluster,
                            assigned_indices_by_peer[peer_index],
                            domain_references,
                            (domain_left, domain_right),
                        )
                    )

            for cluster in unmatched_clusters:
                cluster_left = min(item.canonical_bbox[0] for item in cluster)
                cluster_right = max(item.canonical_bbox[2] for item in cluster)
                covered_indices = [
                    index
                    for index, anchor in enumerate(leaf_anchors)
                    if cluster_left - 1.0 <= anchor <= cluster_right + 1.0
                ]
                if not covered_indices:
                    overlaps = [
                        max(
                            0.0,
                            min(cluster_right, right) - max(cluster_left, left),
                        )
                        for left, right in leaf_axis_bounds
                    ]
                    maximum_overlap = max(overlaps, default=0.0)
                    matching_indices = [
                        index
                        for index, overlap in enumerate(overlaps)
                        if maximum_overlap > 0.0
                        and abs(overlap - maximum_overlap) <= 0.5
                    ]
                    if len(matching_indices) == 1:
                        covered_indices = matching_indices
                cluster_assignments.append((cluster, covered_indices, [], None))

            for (
                cluster,
                covered_indices,
                rule_references,
                domain,
            ) in cluster_assignments:
                covered_indices = sorted(set(covered_indices))
                cluster_evidence_ids = [
                    item.evidence_id
                    for item in sorted(
                        cluster,
                        key=lambda value: (
                            value.canonical_bbox[1],
                            value.canonical_bbox[0],
                        ),
                    )
                ]
                if len(covered_indices) == 1:
                    leaf_parts[covered_indices[0]].extend(cluster)
                    assigned_evidence_ids.update(cluster_evidence_ids)
                    continue
                cluster_left = min(item.canonical_bbox[0] for item in cluster)
                cluster_right = max(item.canonical_bbox[2] for item in cluster)
                contiguous = (
                    covered_indices
                    == list(range(covered_indices[0], covered_indices[-1] + 1))
                    if covered_indices
                    else False
                )
                supported = domain is None or (
                    cluster_left >= domain[0] - 3.0 and cluster_right <= domain[1] + 3.0
                )
                span = (
                    (covered_indices[0], covered_indices[-1])
                    if covered_indices
                    else None
                )
                crosses_existing = span is not None and any(
                    existing == span
                    or existing[0] < span[0] <= existing[1] < span[1]
                    or span[0] < existing[0] <= span[1] < existing[1]
                    for existing in group_coverages
                )
                if (
                    len(covered_indices) < 2
                    or not contiguous
                    or any(
                        leaf_axis_roles[index] == "stub" for index in covered_indices
                    )
                    or not supported
                    or crosses_existing
                ):
                    concerns.append(
                        "unresolved_upper_header_run:" + ",".join(cluster_evidence_ids)
                    )
                    diagnosed_evidence_ids.update(cluster_evidence_ids)
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
                child_ids = [leaf_ids[index] for index in covered_indices]
                unique_rule_references = list(
                    {
                        (reference.source, reference.source_index): reference
                        for reference in rule_references
                    }.values()
                )
                groups.append(
                    HeaderGroupCandidate(
                        group_id=group_id,
                        label=group_label,
                        raw_text=group_label,
                        base_text=group_label,
                        canonical_x_bounds=(
                            leaf_axis_bounds[covered_indices[0]][0],
                            leaf_axis_bounds[covered_indices[-1]][1],
                        ),
                        leaf_ids=child_ids,
                        evidence_ids=cluster_evidence_ids,
                        rule_references=unique_rule_references,
                    )
                )
                for child_id in child_ids:
                    relationships.append(
                        HeaderStructureRelationship(
                            relationship_id=(
                                f"{candidate_id}:relationship:{len(relationships)}"
                            ),
                            parent_group_id=group_id,
                            child_leaf_id=child_id,
                        )
                    )
                group_coverages.append((covered_indices[0], covered_indices[-1]))
                assigned_evidence_ids.update(cluster_evidence_ids)

    leaves: list[HeaderLeafCandidate] = []
    for leaf_index, (band_id, bounds) in enumerate(
        zip(leaf_axis_ids, leaf_axis_bounds, strict=True)
    ):
        parts = sorted(
            leaf_parts[leaf_index],
            key=lambda item: (item.canonical_bbox[1], item.canonical_bbox[0]),
        )
        label = clean_text(" ".join(item.text for item in parts))
        if not label:
            concerns.append(f"blank_header_leaf:{leaf_index}")
        leaves.append(
            HeaderLeafCandidate(
                leaf_id=leaf_ids[leaf_index],
                leaf_index=leaf_index,
                label=label,
                raw_text=label,
                base_text=label,
                canonical_x_bounds=bounds,
                evidence_ids=[item.evidence_id for item in parts],
                occupancy_band_ids=[band_id],
                occupancy_alignment="one_to_one",
            )
        )
    for item in header_evidence:
        if (
            item.evidence_id not in assigned_evidence_ids
            and item.evidence_id not in diagnosed_evidence_ids
        ):
            concerns.append(f"unassigned_header_evidence:{item.evidence_id}")

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
        if annotation.row_idx not in header_rows:
            continue
        marker_bboxes = [
            marker_char_bboxes[index]
            for index in annotation.source_char_indices
            if index in marker_char_bboxes
        ]
        marker_id = annotation.annotation_id or (
            f"{table.table_id}:marker:{annotation_index}"
        )
        source_line_ids = {
            reference.line_id for reference in annotation.source_span_references
        }
        source_evidence = [
            item
            for item in header_evidence
            if source_line_ids.intersection(item.source_line_ids)
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

    if len(leaves) != len(leaf_axis_ids):
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
