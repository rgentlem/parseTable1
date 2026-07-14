"""Build provisional leaf columns from raw body occupancy and rule endpoints."""

from __future__ import annotations

from collections.abc import Sequence

from table1_parser.schemas import (
    BodyOccupancyTable,
    ExtractedTable,
    LeafColumnBandCandidate,
    LeafColumnCandidateTable,
    LeafColumnRuleEndpointEvidence,
    LeafColumnSeparatorCandidate,
    TablePositionedEvidence,
)


def build_leaf_column_candidate_tables(
    body_occupancy_tables: Sequence[BodyOccupancyTable],
    extracted_tables: Sequence[ExtractedTable],
) -> list[LeafColumnCandidateTable]:
    """Build one provisional geometry-only leaf-column record per table."""
    extracted_by_table_id = {table.table_id: table for table in extracted_tables}
    return [
        build_leaf_column_candidate_table(
            occupancy,
            extracted_table=extracted_by_table_id.get(occupancy.table_id),
        )
        for occupancy in body_occupancy_tables
    ]


def build_leaf_column_candidate_table(
    occupancy: BodyOccupancyTable,
    *,
    extracted_table: ExtractedTable | None,
) -> LeafColumnCandidateTable:
    """Build raw zero-valley leaf candidates for one table body."""
    source_artifacts = [
        "body_occupancy.json",
        "extracted_tables.json:metadata.table_positioned_evidence",
    ]
    diagnostics: list[str] = []
    concerns: list[str] = []
    if occupancy.diagnostics:
        diagnostics.append("body_occupancy_has_diagnostics")
    if extracted_table is None:
        diagnostics.append("extracted_table_missing")
    if (
        occupancy.x_min is None
        or occupancy.x_max is None
        or occupancy.bin_width is None
        or not occupancy.occupied_line_counts
    ):
        diagnostics.append("body_occupancy_incomplete")
    if diagnostics or extracted_table is None:
        return LeafColumnCandidateTable(
            table_id=occupancy.table_id,
            page_num=occupancy.page_num,
            source_artifacts=source_artifacts,
            body_line_count=len(occupancy.lines),
            bin_width=occupancy.bin_width,
            diagnostics=list(dict.fromkeys(diagnostics)),
        )

    raw_evidence = extracted_table.metadata.get("table_positioned_evidence")
    if not isinstance(raw_evidence, dict):
        diagnostics.append("table_positioned_evidence_missing")
        return LeafColumnCandidateTable(
            table_id=occupancy.table_id,
            page_num=occupancy.page_num,
            source_artifacts=source_artifacts,
            body_line_count=len(occupancy.lines),
            bin_width=occupancy.bin_width,
            diagnostics=diagnostics,
        )
    evidence = TablePositionedEvidence.model_validate(raw_evidence)

    counts = occupancy.occupied_line_counts
    if occupancy.minimum_separator_gap_width is None:
        diagnostics.append("minimum_separator_gap_width_missing")
        return LeafColumnCandidateTable(
            table_id=occupancy.table_id,
            page_num=occupancy.page_num,
            source_artifacts=source_artifacts,
            body_line_count=len(occupancy.lines),
            bin_width=occupancy.bin_width,
            diagnostics=diagnostics,
        )

    separators: list[LeafColumnSeparatorCandidate] = []
    horizontal_segments: list[tuple[str, int, tuple[float, float, float, float]]] = []
    for source, segments in (
        ("rule_segment", evidence.canonical_rule_segments),
        ("stroked_rule_segment", evidence.canonical_stroked_rule_segments),
    ):
        horizontal_segments.extend(
            (source, segment_index, segment)
            for segment_index, segment in enumerate(segments)
            if abs(segment[3] - segment[1]) <= 1.5
        )

    for separator_index, gap in enumerate(occupancy.qualified_zero_gaps):
        x_left, x_right = gap.canonical_x_bounds
        endpoint_evidence: list[LeafColumnRuleEndpointEvidence] = []
        for source, source_index, segment in horizontal_segments:
            segment_left = min(segment[0], segment[2])
            segment_right = max(segment[0], segment[2])
            for endpoint, endpoint_x in (
                ("left", segment_left),
                ("right", segment_right),
            ):
                if x_left <= endpoint_x <= x_right:
                    endpoint_evidence.append(
                        LeafColumnRuleEndpointEvidence(
                            source=source,
                            source_index=source_index,
                            endpoint=endpoint,
                            canonical_x=endpoint_x,
                            canonical_segment=segment,
                        )
                    )
        separators.append(
            LeafColumnSeparatorCandidate(
                separator_id=f"{occupancy.table_id}:separator:{separator_index}",
                canonical_x_bounds=(x_left, x_right),
                canonical_x=(x_left + x_right) / 2.0,
                gap_width=gap.width,
                minimum_gap_width=occupancy.minimum_separator_gap_width,
                rule_endpoints=endpoint_evidence,
            )
        )

    if not separators:
        concerns.append("no_qualified_zero_occupancy_column_separator")
        return LeafColumnCandidateTable(
            table_id=occupancy.table_id,
            page_num=occupancy.page_num,
            source_artifacts=source_artifacts,
            body_line_count=len(occupancy.lines),
            bin_width=occupancy.bin_width,
            concerns=concerns,
        )

    bands: list[LeafColumnBandCandidate] = []
    band_bounds = [occupancy.x_min]
    band_bounds.extend(separator.canonical_x for separator in separators)
    band_bounds.append(occupancy.x_max)
    for band_index, (band_left, band_right) in enumerate(
        zip(band_bounds, band_bounds[1:], strict=False)
    ):
        left_separator = separators[band_index - 1] if band_index > 0 else None
        right_separator = (
            separators[band_index] if band_index < len(separators) else None
        )
        band_counts = [
            count
            for bin_index, count in enumerate(counts)
            if count > 0
            and band_left
            <= occupancy.x_min + (bin_index + 0.5) * occupancy.bin_width
            < band_right
        ]
        if not band_counts:
            diagnostics.append(f"occupied_band_support_missing:{band_index}")
            continue
        bands.append(
            LeafColumnBandCandidate(
                band_id=f"{occupancy.table_id}:band:{band_index}",
                provisional_role="stub" if band_index == 0 else "value",
                canonical_x_bounds=(band_left, band_right),
                left_separator_id=(
                    left_separator.separator_id if left_separator else None
                ),
                right_separator_id=(
                    right_separator.separator_id if right_separator else None
                ),
                minimum_occupied_line_count=min(band_counts),
                maximum_occupied_line_count=max(band_counts),
            )
        )

    return LeafColumnCandidateTable(
        table_id=occupancy.table_id,
        page_num=occupancy.page_num,
        source_artifacts=source_artifacts,
        body_line_count=len(occupancy.lines),
        bin_width=occupancy.bin_width,
        separators=separators,
        bands=bands,
        provisional_grid_band_ids=[band.band_id for band in bands],
        provisional_stub_band_id=bands[0].band_id,
        concerns=concerns,
        diagnostics=diagnostics,
    )


def leaf_column_candidate_tables_to_payload(
    tables: Sequence[LeafColumnCandidateTable],
) -> list[dict[str, object]]:
    """Serialize provisional leaf-column records as JSON-ready dictionaries."""
    return [table.model_dump(mode="json") for table in tables]
