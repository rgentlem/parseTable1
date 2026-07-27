"""Materialize canonical table grids from accepted positioned geometry."""

from __future__ import annotations

from collections.abc import Sequence

from table1_parser.extract.provisional_table import ProvisionalExtractedTable
from table1_parser.schemas import (
    ExtractedTable,
    HeaderStructureCandidate,
    LeafColumnCandidateTable,
    PaperPositionedDocument,
    TableBoundaryProposal,
    TableCell,
)


def finalize_canonical_extracted_tables(
    extracted_tables: Sequence[ProvisionalExtractedTable],
    *,
    paper_positioned_document: PaperPositionedDocument,
    table_boundary_proposals: Sequence[TableBoundaryProposal],
    leaf_column_candidates: Sequence[LeafColumnCandidateTable],
    header_structure_candidates: Sequence[HeaderStructureCandidate],
) -> list[ExtractedTable]:
    """Materialize occupancy columns with their accepted header structures."""
    pages_by_num = {
        page.page_num: page for page in paper_positioned_document.pages
    }
    proposals_by_table_id = {
        proposal.table_id: proposal for proposal in table_boundary_proposals
    }
    leaves_by_table_id = {
        candidate.table_id: candidate for candidate in leaf_column_candidates
    }
    headers_by_table_id = {
        candidate.table_id: candidate for candidate in header_structure_candidates
    }
    finalized_tables: list[ExtractedTable] = []

    for table in extracted_tables:
        diagnostics: list[str] = []
        page = pages_by_num.get(table.page_num)
        proposal = proposals_by_table_id.get(table.table_id)
        physical_band_candidate = leaves_by_table_id.get(table.table_id)
        header_candidate = headers_by_table_id.get(table.table_id)
        evidence = table.positioned_evidence

        if page is None:
            diagnostics.append("positioned_page_missing")
        if proposal is None:
            diagnostics.append("table_boundary_proposal_missing")
        elif not (
            proposal.credible_rule_geometry or proposal.coherent_positioned_grid
        ):
            diagnostics.append("credible_table_geometry_missing")
        if physical_band_candidate is None:
            diagnostics.append("physical_column_band_candidate_missing")
        elif physical_band_candidate.diagnostics or physical_band_candidate.concerns:
            diagnostics.append("physical_column_band_geometry_inadequate")
        elif len(physical_band_candidate.bands) < 2:
            diagnostics.append("physical_column_band_count_inadequate")
        if evidence.diagnostics:
            diagnostics.append("positioned_evidence_has_diagnostics")

        row_bounds = proposal.canonical_row_bounds if proposal is not None else []
        if len(row_bounds) != table.n_rows or not row_bounds:
            diagnostics.append("canonical_row_bounds_inadequate")
        elif any(
            bottom <= top
            for top, bottom in row_bounds
        ):
            diagnostics.append("canonical_row_bounds_invalid")

        physical_band_validation_concerns: list[str] = []
        if physical_band_candidate is None:
            physical_band_validation_concerns.append(
                "physical_column_band_candidate_missing"
            )
        else:
            physical_band_validation_concerns.extend(
                physical_band_candidate.diagnostics
            )
            physical_band_validation_concerns.extend(
                physical_band_candidate.concerns
            )
            if len(physical_band_candidate.bands) < 2:
                physical_band_validation_concerns.append(
                    "physical_column_band_count_inadequate"
                )

        header_structure_validation_concerns: list[str] = []
        if header_candidate is None:
            header_structure_validation_concerns.append(
                "header_structure_candidate_missing"
            )
        elif physical_band_candidate is not None:
            expected_band_ids = [
                band.band_id for band in physical_band_candidate.bands
            ]
            if header_candidate.page_num != table.page_num:
                header_structure_validation_concerns.append(
                    "header_structure_candidate_page_mismatch"
                )
            if header_candidate.physical_band_ids != expected_band_ids:
                header_structure_validation_concerns.append(
                    "header_physical_band_axis_mismatch"
                )

            ordered_leaves = sorted(
                header_candidate.leaf_candidates,
                key=lambda leaf: leaf.physical_col_idx,
            )
            if [leaf.physical_col_idx for leaf in ordered_leaves] != list(
                range(len(expected_band_ids))
            ):
                header_structure_validation_concerns.append(
                    "terminal_header_physical_column_mismatch"
                )
            if len({leaf.leaf_id for leaf in ordered_leaves}) != len(
                ordered_leaves
            ):
                header_structure_validation_concerns.append(
                    "terminal_header_leaf_ids_duplicate"
                )
            for leaf in ordered_leaves:
                if leaf.physical_col_idx >= len(expected_band_ids):
                    continue
                band = physical_band_candidate.bands[leaf.physical_col_idx]
                if (
                    leaf.physical_band_ids != [band.band_id]
                    or leaf.canonical_x_bounds != band.canonical_x_bounds
                ):
                    header_structure_validation_concerns.append(
                        f"terminal_header_band_mapping_mismatch:{leaf.leaf_id}"
                    )

            leaf_index_by_id = {
                leaf.leaf_id: leaf.physical_col_idx for leaf in ordered_leaves
            }
            if len(
                {group.group_id for group in header_candidate.group_candidates}
            ) != len(header_candidate.group_candidates):
                header_structure_validation_concerns.append(
                    "header_group_ids_duplicate"
                )
            group_spans: list[tuple[int, int, str]] = []
            for group in header_candidate.group_candidates:
                group_indices = [
                    leaf_index_by_id[leaf_id]
                    for leaf_id in group.leaf_ids
                    if leaf_id in leaf_index_by_id
                ]
                if (
                    not group.leaf_ids
                    or len(group_indices) != len(group.leaf_ids)
                    or len(set(group.leaf_ids)) != len(group.leaf_ids)
                ):
                    header_structure_validation_concerns.append(
                        f"header_group_leaf_reference_invalid:{group.group_id}"
                    )
                    continue
                ordered_group_indices = sorted(group_indices)
                if ordered_group_indices != list(
                    range(
                        ordered_group_indices[0],
                        ordered_group_indices[-1] + 1,
                    )
                ):
                    header_structure_validation_concerns.append(
                        f"header_group_noncontiguous:{group.group_id}"
                    )
                    continue
                group_spans.append(
                    (
                        ordered_group_indices[0],
                        ordered_group_indices[-1],
                        group.group_id,
                    )
                )
            for span_index, (left, right, group_id) in enumerate(group_spans):
                for other_left, other_right, other_group_id in group_spans[
                    span_index + 1 :
                ]:
                    if (left < other_left <= right < other_right) or (
                        other_left < left <= other_right < right
                    ):
                        header_structure_validation_concerns.append(
                            "header_group_spans_conflict:"
                            f"{group_id}:{other_group_id}"
                        )

        if header_structure_validation_concerns:
            diagnostics.append("header_structure_candidate_inconsistent")

        selection_metadata = {
            "status": "rejected" if diagnostics else "accepted",
            "source_artifacts": [
                "paper_positioned_document.json",
                "table_boundary_proposals.json",
                "leaf_column_candidates.json",
                "header_structure_candidates.json",
            ],
            "prior_column_count": table.n_cols,
            "selected_column_count": (
                len(physical_band_candidate.bands)
                if physical_band_candidate is not None
                else 0
            ),
            "selected_row_count": len(row_bounds),
            "physical_band_validation_concerns": list(
                dict.fromkeys(physical_band_validation_concerns)
            ),
            "header_structure_validation_concerns": list(
                dict.fromkeys(header_structure_validation_concerns)
            ),
            "diagnostics": diagnostics,
            "selected_column_source": "body_occupancy_physical_band_geometry",
        }
        if (
            diagnostics
            or page is None
            or proposal is None
            or physical_band_candidate is None
            or header_candidate is None
        ):
            finalized_table = ExtractedTable.model_validate(
                table.model_copy(
                    update={
                        "n_rows": 0,
                        "n_cols": 0,
                        "cells": [],
                        "metadata": {
                            **table.metadata,
                            "canonical_grid_selection": selection_metadata,
                        },
                    }
                ).model_dump()
            )
            finalized_tables.append(finalized_table)
            continue

        words_by_index = {
            word_index: page.words[word_index]
            for word_index in evidence.word_indices
            if 0 <= word_index < len(page.words)
        }
        caption_region = table.metadata.get("caption_region")
        caption_line_ids = (
            {
                str(line_id)
                for line_id in caption_region.get("line_ids", [])
            }
            if isinstance(caption_region, dict)
            else set()
        )
        line_id_by_position = {
            (line.block_index, line.line_index): line.line_id
            for line in page.lines
            if line.block_index is not None and line.line_index is not None
        }
        positioned_words = [
            (word_index, words_by_index[word_index], bbox)
            for word_index, bbox in zip(
                evidence.word_indices,
                evidence.canonical_word_bboxes,
                strict=False,
            )
            if word_index in words_by_index and words_by_index[word_index].text.strip()
            and line_id_by_position.get(
                (
                    words_by_index[word_index].block_index,
                    words_by_index[word_index].line_index,
                )
            ) not in caption_line_ids
        ]
        canonical_grid_source_rows = {
            *header_candidate.header_row_indices,
            *header_candidate.body_row_indices,
        }
        retained_row_indices = [
            row_idx
            for row_idx, (top, bottom) in enumerate(row_bounds)
            if row_idx in canonical_grid_source_rows
            and any(
                top - 1.0 <= (bbox[1] + bbox[3]) / 2.0 <= bottom + 1.0
                for _word_index, _word, bbox in positioned_words
            )
        ]
        row_bounds = [row_bounds[row_idx] for row_idx in retained_row_indices]
        if not row_bounds:
            selection_metadata["status"] = "rejected"
            selection_metadata["diagnostics"] = ["canonical_rows_empty"]
            finalized_table = ExtractedTable.model_validate(
                table.model_copy(
                    update={
                        "n_rows": 0,
                        "n_cols": 0,
                        "cells": [],
                        "metadata": {
                            **table.metadata,
                            "canonical_grid_selection": selection_metadata,
                        },
                    }
                ).model_dump()
            )
            finalized_tables.append(finalized_table)
            continue
        row_index_map = {
            source_row_idx: canonical_row_idx
            for canonical_row_idx, source_row_idx in enumerate(retained_row_indices)
        }
        selected_band_candidate = physical_band_candidate
        bands = selected_band_candidate.bands
        canonical_header_rows = {
            row_index_map[row_idx]
            for row_idx in header_candidate.header_row_indices
            if row_idx in row_index_map
        }
        canonical_body_rows = {
            row_index_map[row_idx]
            for row_idx in header_candidate.body_row_indices
            if row_idx in row_index_map
        }
        header_columns_by_evidence_id: dict[str, set[int]] = {}
        leaf_column_by_id = {
            leaf.leaf_id: leaf.physical_col_idx
            for leaf in header_candidate.leaf_candidates
        }
        for leaf in header_candidate.leaf_candidates:
            for evidence_id in leaf.evidence_ids:
                header_columns_by_evidence_id.setdefault(evidence_id, set()).add(
                    leaf.physical_col_idx
                )
        for group in header_candidate.group_candidates:
            group_columns = [
                leaf_column_by_id[leaf_id]
                for leaf_id in group.leaf_ids
                if leaf_id in leaf_column_by_id
            ]
            if not group_columns:
                continue
            anchor_col_idx = min(group_columns)
            for evidence_id in group.evidence_ids:
                header_columns_by_evidence_id.setdefault(evidence_id, set()).add(
                    anchor_col_idx
                )

        header_evidence_by_cell: dict[
            tuple[int, int],
            list[tuple[int, str, tuple[float, float, float, float]]],
        ] = {}
        for evidence_index, header_evidence in enumerate(header_candidate.evidence):
            evidence_columns = header_columns_by_evidence_id.get(
                header_evidence.evidence_id,
                set(),
            )
            evidence_rows = [
                row_index_map[row_idx]
                for row_idx in header_evidence.header_row_indices
                if row_idx in row_index_map
            ]
            if len(evidence_columns) != 1 or not evidence_rows:
                continue
            header_evidence_by_cell.setdefault(
                (min(evidence_rows), next(iter(evidence_columns))),
                [],
            ).append(
                (
                    evidence_index,
                    header_evidence.text,
                    header_evidence.canonical_bbox,
                )
            )

        words_by_cell: dict[
            tuple[int, int],
            list[tuple[int, str, tuple[float, float, float, float]]],
        ] = {}
        for word_index, word, bbox in positioned_words:
            center_y = (bbox[1] + bbox[3]) / 2.0
            candidate_rows = [
                row_idx
                for row_idx, (top, bottom) in enumerate(row_bounds)
                if top - 1.0 <= center_y <= bottom + 1.0
            ]
            if not candidate_rows:
                continue
            row_idx = min(
                candidate_rows,
                key=lambda index: abs(
                    center_y - sum(row_bounds[index]) / 2.0
                ),
            )
            if row_idx not in canonical_body_rows:
                continue
            overlaps = [
                max(
                    0.0,
                    min(bbox[2], band.canonical_x_bounds[1])
                    - max(bbox[0], band.canonical_x_bounds[0]),
                )
                for band in bands
            ]
            col_idx = max(range(len(bands)), key=lambda index: overlaps[index])
            if overlaps[col_idx] <= 0.0:
                continue
            words_by_cell.setdefault((row_idx, col_idx), []).append(
                (word_index, word.text.strip(), bbox)
            )

        cells: list[TableCell] = []
        table_cells: list[list[tuple[float, float, float, float] | None]] = []
        first_column_text_x0_by_row: dict[int, float] = {}
        confidence = table.metadata.get("candidate_score")
        for row_idx in range(len(row_bounds)):
            bbox_row: list[tuple[float, float, float, float] | None] = []
            for col_idx in range(len(bands)):
                if row_idx in canonical_header_rows:
                    cell_items = sorted(
                        header_evidence_by_cell.get((row_idx, col_idx), []),
                        key=lambda item: (item[2][1], item[2][0], item[0]),
                    )
                else:
                    cell_items = sorted(
                        words_by_cell.get((row_idx, col_idx), []),
                        key=lambda item: (item[2][0], item[0]),
                    )
                text = " ".join(item[1] for item in cell_items)
                bbox = (
                    (
                        min(item[2][0] for item in cell_items),
                        min(item[2][1] for item in cell_items),
                        max(item[2][2] for item in cell_items),
                        max(item[2][3] for item in cell_items),
                    )
                    if cell_items
                    else None
                )
                if col_idx == 0 and bbox is not None:
                    first_column_text_x0_by_row[row_idx] = bbox[0]
                bbox_row.append(bbox)
                cells.append(
                    TableCell(
                        row_idx=row_idx,
                        col_idx=col_idx,
                        text=text,
                        page_num=table.page_num,
                        bbox=bbox,
                        extractor_name="pymupdf",
                        confidence=(
                            float(confidence)
                            if isinstance(confidence, (int, float))
                            else None
                        ),
                    )
                )
            table_cells.append(bbox_row)

        selected_boundaries = [
            bands[0].canonical_x_bounds[0],
            *[
                separator.canonical_x
                for separator in selected_band_candidate.separators
            ],
            bands[-1].canonical_x_bounds[1],
        ]
        canonical_evidence = evidence.model_copy(
            update={
                "canonical_grid_bbox": (
                    bands[0].canonical_x_bounds[0],
                    row_bounds[0][0],
                    bands[-1].canonical_x_bounds[1],
                    row_bounds[-1][1],
                ),
                "canonical_row_bounds": list(row_bounds),
                "canonical_physical_column_bounds": [
                    band.canonical_x_bounds for band in bands
                ],
            }
        )
        metadata = dict(table.metadata)
        metadata.update(
            {
                "table_cells": table_cells,
                "row_bounds": row_bounds,
                "first_column_text_x0_by_row": first_column_text_x0_by_row,
                "canonical_extraction_layer": "pymupdf_positioned_geometry",
                "grid_refinement_source": "body_occupancy_physical_band_geometry",
                "canonical_grid_selection": {
                    **selection_metadata,
                    "selected_row_count": len(row_bounds),
                    "selected_column_boundaries": selected_boundaries,
                    "selected_band_ids": list(
                        band.band_id for band in bands
                    ),
                },
            }
        )
        for stale_key in (
            "value_matrix_column_anchors",
            "label_span_numeric_clusters",
            "label_column_numeric_anchor_suppression",
            "header_row_geometry_roles",
        ):
            metadata.pop(stale_key, None)
        finalized_table = ExtractedTable.model_validate(
            table.model_copy(
                update={
                    "n_rows": len(row_bounds),
                    "n_cols": len(bands),
                    "cells": cells,
                    "positioned_evidence": canonical_evidence,
                    "extraction_backend": "pymupdf",
                    "metadata": metadata,
                }
            ).model_dump()
        )
        finalized_tables.append(finalized_table)

    return finalized_tables
