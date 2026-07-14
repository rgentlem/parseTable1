"""Materialize canonical table grids from accepted positioned geometry."""

from __future__ import annotations

from collections.abc import Sequence

from table1_parser.extract.provisional_table import ProvisionalExtractedTable
from table1_parser.schemas import (
    ExtractedTable,
    LeafColumnCandidateTable,
    PaperPositionedDocument,
    PaperPositionedWord,
    TableBoundaryProposal,
    TableCell,
    TablePositionedEvidence,
    TokenStartEvidenceTable,
)


def _confirmed_continuation_parent_leaf_candidate(
    table: ProvisionalExtractedTable,
    *,
    extracted_tables: Sequence[ProvisionalExtractedTable],
    finalized_tables_by_id: dict[str, ExtractedTable],
    leaves_by_table_id: dict[str, LeafColumnCandidateTable],
    token_starts: TokenStartEvidenceTable | None,
) -> tuple[LeafColumnCandidateTable | None, dict[str, object] | None]:
    """Return parent bands only when direct continuation evidence fully agrees."""
    if table.metadata.get("is_continuation") is not True:
        return None, None
    continuation_number = table.metadata.get("continuation_of_table_number")
    if (
        not isinstance(continuation_number, int)
        or isinstance(continuation_number, bool)
    ):
        return None, None
    local_leaf_candidate = leaves_by_table_id.get(table.table_id)
    if (
        local_leaf_candidate is None
        or local_leaf_candidate.diagnostics
        or local_leaf_candidate.concerns
        or len(local_leaf_candidate.bands) >= table.n_cols
        or table.n_cols < 2
        or token_starts is None
        or not token_starts.evaluated
        or token_starts.diagnostics
        or "grid_count_disagreement" not in token_starts.evaluation_reasons
        or token_starts.bin_width is None
        or token_starts.body_line_count <= 0
        or token_starts.observed_line_count != token_starts.body_line_count
        or len(token_starts.lines) != token_starts.body_line_count
    ):
        return None, None

    table_index = next(
        (
            index
            for index, candidate in enumerate(extracted_tables)
            if candidate.table_id == table.table_id
        ),
        None,
    )
    if table_index is None:
        return None, None
    parent_table = next(
        (
            candidate
            for candidate in reversed(extracted_tables[:table_index])
            if candidate.page_num == table.page_num - 1
            and candidate.metadata.get("table_number") == continuation_number
            and candidate.metadata.get("is_continuation") is not True
        ),
        None,
    )
    if parent_table is None or parent_table.n_cols != table.n_cols:
        return None, None
    finalized_parent = finalized_tables_by_id.get(parent_table.table_id)
    parent_leaf_candidate = leaves_by_table_id.get(parent_table.table_id)
    if (
        finalized_parent is None
        or finalized_parent.n_cols != table.n_cols
        or parent_leaf_candidate is None
        or parent_leaf_candidate.diagnostics
        or parent_leaf_candidate.concerns
        or len(parent_leaf_candidate.bands) != table.n_cols
        or not parent_leaf_candidate.bands
        or not local_leaf_candidate.bands
        or parent_leaf_candidate.coordinate_frame
        != local_leaf_candidate.coordinate_frame
    ):
        return None, None

    header_rows_and_labels: list[tuple[int, list[str]]] = []
    for candidate in (parent_table, table):
        raw_roles = candidate.metadata.get("header_row_geometry_roles")
        if not isinstance(raw_roles, list):
            return None, None
        leaf_header_rows = [
            row_idx
            for row_idx, role in enumerate(raw_roles)
            if role == "leaf_header" and row_idx < candidate.n_rows
        ]
        if not leaf_header_rows:
            return None, None
        leaf_header_row = max(leaf_header_rows)
        cells_by_col = {
            cell.col_idx: cell
            for cell in candidate.cells
            if cell.row_idx == leaf_header_row
        }
        if set(cells_by_col) != set(range(candidate.n_cols)):
            return None, None
        header_rows_and_labels.append(
            (
                leaf_header_row,
                [
                    " ".join(cells_by_col[col_idx].text.split()).casefold()
                    for col_idx in range(candidate.n_cols)
                ],
            )
        )
    if (
        header_rows_and_labels[0][1] != header_rows_and_labels[1][1]
        or not any(header_rows_and_labels[1][1])
    ):
        return None, None

    aligned_anchor_sets: list[list[float]] = []
    for candidate in (parent_table, table):
        raw_anchors = candidate.metadata.get("value_matrix_column_anchors")
        if not isinstance(raw_anchors, list) or len(raw_anchors) != table.n_cols - 1:
            return None, None
        anchors: list[float] = []
        for value in raw_anchors:
            if isinstance(value, bool):
                return None, None
            try:
                anchors.append(float(value))
            except (TypeError, ValueError):
                return None, None
        aligned_anchor_sets.append(anchors)
    anchor_deltas = [
        abs(parent_anchor - continuation_anchor)
        for parent_anchor, continuation_anchor in zip(
            aligned_anchor_sets[0],
            aligned_anchor_sets[1],
            strict=True,
        )
    ]
    alignment_tolerance = token_starts.bin_width
    if max(anchor_deltas, default=float("inf")) > alignment_tolerance:
        return None, None

    parent_left = parent_leaf_candidate.bands[0].canonical_x_bounds[0]
    parent_right = parent_leaf_candidate.bands[-1].canonical_x_bounds[1]
    local_left = local_leaf_candidate.bands[0].canonical_x_bounds[0]
    local_right = local_leaf_candidate.bands[-1].canonical_x_bounds[1]
    if (
        abs(parent_left - local_left) > alignment_tolerance
        or abs(parent_right - local_right) > alignment_tolerance
    ):
        return None, None

    for line in token_starts.lines:
        for band_index, band in enumerate(parent_leaf_candidate.bands[1:], start=1):
            band_left, band_right = band.canonical_x_bounds
            if not any(
                band_left <= observation.canonical_x
                and (
                    observation.canonical_x < band_right
                    or (
                        band_index == len(parent_leaf_candidate.bands) - 1
                        and observation.canonical_x <= band_right
                    )
                )
                for observation in line.observations
            ):
                return None, None

    return parent_leaf_candidate, {
        "status": "confirmed",
        "parent_table_id": parent_table.table_id,
        "parent_page_num": parent_table.page_num,
        "continuation_page_num": table.page_num,
        "column_count": table.n_cols,
        "parent_leaf_header_row_idx": header_rows_and_labels[0][0],
        "continuation_leaf_header_row_idx": header_rows_and_labels[1][0],
        "parent_value_anchors": aligned_anchor_sets[0],
        "continuation_value_anchors": aligned_anchor_sets[1],
        "maximum_anchor_delta": max(anchor_deltas, default=0.0),
        "anchor_alignment_tolerance": alignment_tolerance,
        "token_body_line_count": token_starts.body_line_count,
        "token_observed_line_count": token_starts.observed_line_count,
        "all_parent_value_bands_supported_on_every_body_line": True,
    }


def _confirmed_local_positioned_axis(
    table: ProvisionalExtractedTable,
    *,
    leaf_candidate: LeafColumnCandidateTable,
    token_starts: TokenStartEvidenceTable | None,
    retained_row_indices: Sequence[int],
    retained_column_indices: Sequence[int],
    selected_boundaries: Sequence[float],
    source_row_bounds: Sequence[tuple[float, float]],
    positioned_words: Sequence[
        tuple[int, PaperPositionedWord, tuple[float, float, float, float]]
    ],
) -> dict[str, object] | None:
    """Confirm a positioned axis from distinct header lines and body starts."""
    if (
        table.metadata.get("strong_ruled_geometry") is not True
        or leaf_candidate.diagnostics
        or leaf_candidate.concerns
        or len(retained_column_indices) <= len(leaf_candidate.bands)
        or list(retained_column_indices)
        != list(range(len(retained_column_indices)))
        or len(selected_boundaries) != len(retained_column_indices) + 1
        or len(source_row_bounds) != table.n_rows
        or token_starts is None
        or not token_starts.evaluated
        or "grid_count_disagreement" not in token_starts.evaluation_reasons
        or token_starts.diagnostics
        or token_starts.observed_line_count != token_starts.body_line_count
        or len(token_starts.lines) != token_starts.body_line_count
    ):
        return None
    raw_anchors = table.metadata.get("value_matrix_column_anchors")
    if (
        not isinstance(raw_anchors, list)
        or len(raw_anchors)
        not in {
            len(retained_column_indices) - 1,
            len(retained_column_indices),
        }
    ):
        return None

    body_row_indices = {
        row_idx
        for line in token_starts.lines
        for row_idx in line.source_row_indices
        if row_idx in retained_row_indices
    }
    header_row_indices = [
        row_idx
        for row_idx in retained_row_indices
        if row_idx not in body_row_indices
    ]
    if not header_row_indices:
        return None

    qualifying_header_rows: list[int] = []
    header_line_columns_by_row: dict[int, list[int]] = {}
    for row_idx in header_row_indices:
        top, bottom = source_row_bounds[row_idx]
        line_bboxes: dict[
            tuple[int | None, int | None],
            list[tuple[float, float, float, float]],
        ] = {}
        for _word_index, word, bbox in positioned_words:
            center_y = (bbox[1] + bbox[3]) / 2.0
            if not top - 1.0 <= center_y <= bottom + 1.0:
                continue
            line_bboxes.setdefault(
                (word.block_index, word.line_index), []
            ).append(bbox)
        contained_columns: set[int] = set()
        for bboxes in line_bboxes.values():
            line_left = min(bbox[0] for bbox in bboxes)
            for col_idx, (left, right) in enumerate(
                zip(
                    selected_boundaries,
                    selected_boundaries[1:],
                    strict=False,
                )
            ):
                if left - 1.0 <= line_left < right:
                    contained_columns.add(col_idx)
                    break
        if (
            set(range(1, len(retained_column_indices))).issubset(
                contained_columns
            )
        ):
            qualifying_header_rows.append(row_idx)
            header_line_columns_by_row[row_idx] = sorted(contained_columns)
    if not qualifying_header_rows:
        return None

    supported_body_rows_by_column: list[set[int]] = [
        set() for _ in retained_column_indices
    ]
    for line in token_starts.lines:
        for observation in line.observations:
            for col_idx, (left, right) in enumerate(
                zip(selected_boundaries, selected_boundaries[1:], strict=False)
            ):
                left_tolerance = 1.0 if col_idx == 0 else 0.0
                right_tolerance = (
                    1.0
                    if col_idx == len(retained_column_indices) - 1
                    else 0.0
                )
                if (
                    left - left_tolerance
                    <= observation.canonical_x
                    < right + right_tolerance
                ):
                    supported_body_rows_by_column[col_idx].update(
                        line.source_row_indices
                    )
                    break
    body_support_counts = [
        len(row_indices) for row_indices in supported_body_rows_by_column
    ]
    if (
        body_support_counts[0] != token_starts.body_line_count
        or min(body_support_counts[1:]) < 3
    ):
        return None

    return {
        "status": "confirmed",
        "positioned_column_count": len(retained_column_indices),
        "local_occupancy_column_count": len(leaf_candidate.bands),
        "trimmed_empty_outer_column_count": (
            table.n_cols - len(retained_column_indices)
        ),
        "positioned_column_boundaries": list(selected_boundaries),
        "value_matrix_column_anchors": [float(value) for value in raw_anchors],
        "distinct_header_line_row_indices": qualifying_header_rows,
        "header_line_columns_by_row": header_line_columns_by_row,
        "token_supported_body_row_count_by_column": body_support_counts,
        "all_token_body_lines_support_label_column": True,
        "token_body_line_count": token_starts.body_line_count,
        "token_observed_line_count": token_starts.observed_line_count,
    }


def finalize_canonical_extracted_tables(
    extracted_tables: Sequence[ProvisionalExtractedTable],
    *,
    paper_positioned_document: PaperPositionedDocument,
    table_boundary_proposals: Sequence[TableBoundaryProposal],
    leaf_column_candidates: Sequence[LeafColumnCandidateTable],
    token_start_evidence: Sequence[TokenStartEvidenceTable],
) -> list[ExtractedTable]:
    """Select and materialize one positioned physical grid per table."""
    pages_by_num = {
        page.page_num: page for page in paper_positioned_document.pages
    }
    proposals_by_table_id = {
        proposal.table_id: proposal for proposal in table_boundary_proposals
    }
    leaves_by_table_id = {
        candidate.table_id: candidate for candidate in leaf_column_candidates
    }
    token_starts_by_table_id = {
        evidence.table_id: evidence for evidence in token_start_evidence
    }
    finalized_tables: list[ExtractedTable] = []
    finalized_tables_by_id: dict[str, ExtractedTable] = {}

    for table in extracted_tables:
        diagnostics: list[str] = []
        page = pages_by_num.get(table.page_num)
        proposal = proposals_by_table_id.get(table.table_id)
        leaf_candidate = leaves_by_table_id.get(table.table_id)
        token_starts = token_starts_by_table_id.get(table.table_id)
        confirmed_parent_leaf_candidate, continuation_confirmation = (
            _confirmed_continuation_parent_leaf_candidate(
                table,
                extracted_tables=extracted_tables,
                finalized_tables_by_id=finalized_tables_by_id,
                leaves_by_table_id=leaves_by_table_id,
                token_starts=token_starts,
            )
        )
        raw_evidence = table.metadata.get("table_positioned_evidence")
        evidence = (
            TablePositionedEvidence.model_validate(raw_evidence)
            if isinstance(raw_evidence, dict)
            else None
        )

        if page is None:
            diagnostics.append("positioned_page_missing")
        if proposal is None:
            diagnostics.append("table_boundary_proposal_missing")
        elif not (
            proposal.credible_rule_geometry or proposal.coherent_positioned_grid
        ):
            diagnostics.append("credible_table_geometry_missing")
        if leaf_candidate is None:
            diagnostics.append("leaf_column_candidate_missing")
        elif leaf_candidate.diagnostics or leaf_candidate.concerns:
            diagnostics.append("leaf_column_geometry_inadequate")
        elif len(leaf_candidate.bands) < 2:
            diagnostics.append("leaf_column_count_inadequate")
        if evidence is None:
            diagnostics.append("table_positioned_evidence_missing")
        elif evidence.diagnostics:
            diagnostics.append("table_positioned_evidence_has_diagnostics")

        row_bounds = proposal.canonical_row_bounds if proposal is not None else []
        if len(row_bounds) != table.n_rows or not row_bounds:
            diagnostics.append("canonical_row_bounds_inadequate")
        elif any(
            bottom <= top
            for top, bottom in row_bounds
        ):
            diagnostics.append("canonical_row_bounds_invalid")

        leaf_validation_concerns: list[str] = []
        if leaf_candidate is None:
            leaf_validation_concerns.append("leaf_column_candidate_missing")
        else:
            leaf_validation_concerns.extend(leaf_candidate.diagnostics)
            leaf_validation_concerns.extend(leaf_candidate.concerns)
            if len(leaf_candidate.bands) < 2:
                leaf_validation_concerns.append("leaf_column_count_inadequate")

        selection_metadata = {
            "status": "rejected" if diagnostics else "accepted",
            "source_artifacts": [
                "paper_positioned_document.json",
                "table_boundary_proposals.json",
                "leaf_column_candidates.json",
                "token_start_evidence.json",
            ],
            "prior_column_count": table.n_cols,
            "selected_column_count": (
                len(confirmed_parent_leaf_candidate.bands)
                if confirmed_parent_leaf_candidate is not None
                else (
                    len(leaf_candidate.bands)
                    if leaf_candidate is not None
                    else 0
                )
            ),
            "selected_row_count": len(row_bounds),
            "token_start_evidence_evaluated": bool(
                token_starts is not None and token_starts.evaluated
            ),
            "token_start_evaluation_reasons": (
                list(token_starts.evaluation_reasons)
                if token_starts is not None
                else []
            ),
            "leaf_geometry_validation_concerns": list(
                dict.fromkeys(leaf_validation_concerns)
            ),
            "diagnostics": diagnostics,
        }
        if continuation_confirmation is not None:
            selection_metadata["selected_column_source"] = (
                "confirmed_continuation_parent_leaf_geometry"
            )
            selection_metadata["continuation_parent_band_confirmation"] = (
                continuation_confirmation
            )
            selection_metadata["selected_column_count"] = len(
                confirmed_parent_leaf_candidate.bands
            )
        else:
            selection_metadata["selected_column_source"] = (
                "body_occupancy_leaf_geometry"
            )
        if (
            diagnostics
            or page is None
            or proposal is None
            or leaf_candidate is None
            or evidence is None
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
            finalized_tables_by_id[table.table_id] = finalized_table
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
        source_row_bounds = list(row_bounds)
        retained_row_indices = [
            row_idx
            for row_idx, (top, bottom) in enumerate(row_bounds)
            if any(
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
            finalized_tables_by_id[table.table_id] = finalized_table
            continue
        nonempty_source_columns = sorted(
            {
                cell.col_idx
                for cell in table.cells
                if cell.row_idx in retained_row_indices
                and 0 <= cell.col_idx < table.n_cols
                and cell.text.strip()
            }
        )
        retained_column_indices = (
            list(
                range(
                    nonempty_source_columns[0],
                    nonempty_source_columns[-1] + 1,
                )
            )
            if nonempty_source_columns
            else []
        )
        selected_positioned_boundaries: list[float] = []
        raw_column_starts = table.metadata.get(
            "positioned_column_start_boundaries"
        )
        table_bbox = evidence.canonical_candidate_bbox or evidence.canonical_bbox
        if (
            retained_column_indices
            and isinstance(raw_column_starts, list)
            and table_bbox is not None
        ):
            positioned_boundaries = [float(value) for value in raw_column_starts]
            if (
                retained_column_indices[0] == 0
                and len(positioned_boundaries)
                == len(retained_column_indices) - 1
            ):
                selected_positioned_boundaries = [
                    table_bbox[0],
                    *positioned_boundaries,
                    table_bbox[2],
                ]
            elif len(positioned_boundaries) == table.n_cols - 1:
                source_boundaries = [
                    table_bbox[0],
                    *positioned_boundaries,
                    table_bbox[2],
                ]
                selected_positioned_boundaries = source_boundaries[
                    retained_column_indices[0] : retained_column_indices[-1] + 2
                ]

        local_positioned_confirmation = (
            _confirmed_local_positioned_axis(
                table,
                leaf_candidate=leaf_candidate,
                token_starts=token_starts,
                retained_row_indices=retained_row_indices,
                retained_column_indices=retained_column_indices,
                selected_boundaries=selected_positioned_boundaries,
                source_row_bounds=source_row_bounds,
                positioned_words=positioned_words,
            )
            if continuation_confirmation is None
            and len(retained_column_indices) >= 2
            else None
        )
        positioned_header_cell_conflicts: dict[int, list[dict[str, object]]] = {}
        selected_header_body_rows = proposal.selected_header_body_rows
        if (
            len(retained_column_indices) >= 2
            and len(retained_column_indices) == len(leaf_candidate.bands)
            and selected_header_body_rows is not None
            and len(selected_header_body_rows) == 2
        ):
            body_start_row_idx = selected_header_body_rows[1]
            canonical_col_by_source_col = {
                source_col_idx: canonical_col_idx
                for canonical_col_idx, source_col_idx in enumerate(
                    retained_column_indices
                )
            }
            for cell in table.cells:
                canonical_col_idx = canonical_col_by_source_col.get(cell.col_idx)
                if (
                    canonical_col_idx is None
                    or cell.row_idx not in retained_row_indices
                    or cell.row_idx >= body_start_row_idx
                    or not cell.text.strip()
                    or cell.bbox is None
                ):
                    continue
                containing_leaf_indices = [
                    leaf_index
                    for leaf_index, band in enumerate(leaf_candidate.bands)
                    if band.canonical_x_bounds[0] - 1.0 <= cell.bbox[0]
                    and cell.bbox[2] <= band.canonical_x_bounds[1] + 1.0
                ]
                if (
                    len(containing_leaf_indices) == 1
                    and containing_leaf_indices[0] != canonical_col_idx
                ):
                    positioned_header_cell_conflicts.setdefault(
                        cell.row_idx, []
                    ).append(
                        {
                            "source_column_index": cell.col_idx,
                            "canonical_column_index": canonical_col_idx,
                            "containing_leaf_index": containing_leaf_indices[0],
                            "bbox": cell.bbox,
                        }
                    )
        conflicting_header_rows = {
            row_idx: conflicts
            for row_idx, conflicts in positioned_header_cell_conflicts.items()
            if len(conflicts) >= 2
        }
        positioned_leaf_count_agreement = (
            continuation_confirmation is None
            and len(retained_column_indices) >= 2
            and len(retained_column_indices) == len(leaf_candidate.bands)
            and not conflicting_header_rows
        )
        use_positioned_grid = (
            positioned_leaf_count_agreement
            or local_positioned_confirmation is not None
        )
        if use_positioned_grid:
            selection_metadata["selected_column_source"] = (
                "positioned_grid_confirmed_by_leaf_count_agreement"
                if positioned_leaf_count_agreement
                else "header_line_and_token_confirmed_positioned_grid_geometry"
            )
            if local_positioned_confirmation is not None:
                selection_metadata["local_positioned_axis_confirmation"] = (
                    local_positioned_confirmation
                )
        elif conflicting_header_rows:
            selection_metadata["positioned_grid_validation"] = {
                "status": "rejected",
                "reason": (
                    "repeated_header_cells_contained_by_different_leaf_bands"
                ),
                "conflicts_by_source_row": conflicting_header_rows,
            }

        if use_positioned_grid:
            row_index_map = {
                source_row_idx: canonical_row_idx
                for canonical_row_idx, source_row_idx in enumerate(
                    retained_row_indices
                )
            }
            column_index_map = {
                source_col_idx: canonical_col_idx
                for canonical_col_idx, source_col_idx in enumerate(
                    retained_column_indices
                )
            }
            source_cells = {
                (cell.row_idx, cell.col_idx): cell
                for cell in table.cells
                if cell.row_idx in row_index_map
                and cell.col_idx in column_index_map
            }
            confidence = table.metadata.get("candidate_score")
            cells: list[TableCell] = []
            table_cells: list[list[tuple[float, float, float, float] | None]] = []
            first_column_text_x0_by_row: dict[int, float] = {}
            for source_row_idx in retained_row_indices:
                canonical_row_idx = row_index_map[source_row_idx]
                bbox_row: list[tuple[float, float, float, float] | None] = []
                for source_col_idx in retained_column_indices:
                    canonical_col_idx = column_index_map[source_col_idx]
                    source_cell = source_cells.get(
                        (source_row_idx, source_col_idx)
                    )
                    bbox = source_cell.bbox if source_cell is not None else None
                    text = source_cell.text if source_cell is not None else ""
                    if canonical_col_idx == 0 and bbox is not None:
                        first_column_text_x0_by_row[canonical_row_idx] = bbox[0]
                    bbox_row.append(bbox)
                    cells.append(
                        TableCell(
                            row_idx=canonical_row_idx,
                            col_idx=canonical_col_idx,
                            text=text,
                            page_num=table.page_num,
                            bbox=bbox,
                            extractor_name=(
                                source_cell.extractor_name
                                if source_cell is not None
                                else "pymupdf"
                            ),
                            confidence=(
                                source_cell.confidence
                                if source_cell is not None
                                else (
                                    float(confidence)
                                    if isinstance(confidence, (int, float))
                                    else None
                                )
                            ),
                        )
                    )
                table_cells.append(bbox_row)

            metadata = dict(table.metadata)
            raw_header_roles = metadata.get("header_row_geometry_roles")
            if isinstance(raw_header_roles, list):
                metadata["header_row_geometry_roles"] = [
                    raw_header_roles[row_idx]
                    for row_idx in retained_row_indices
                    if row_idx < len(raw_header_roles)
                ]
            selection_metadata.update(
                {
                    "selected_row_count": len(row_bounds),
                    "selected_column_count": len(retained_column_indices),
                    "selected_column_boundaries": selected_positioned_boundaries,
                    "selected_band_ids": [
                        f"{table.table_id}:positioned_column:{source_col_idx}"
                        for source_col_idx in retained_column_indices
                    ],
                    "removed_caption_or_empty_row_indices": [
                        row_idx
                        for row_idx in range(table.n_rows)
                        if row_idx not in row_index_map
                    ],
                    "removed_empty_outer_column_indices": [
                        col_idx
                        for col_idx in range(table.n_cols)
                        if col_idx not in column_index_map
                    ],
                }
            )
            metadata.update(
                {
                    "table_cells": table_cells,
                    "row_bounds": row_bounds,
                    "first_column_text_x0_by_row": first_column_text_x0_by_row,
                    "canonical_extraction_layer": "pymupdf_positioned_geometry",
                    "grid_refinement_source": "text_position_column_geometry",
                    "canonical_grid_selection": selection_metadata,
                }
            )
            finalized_table = ExtractedTable.model_validate(
                table.model_copy(
                    update={
                        "n_rows": len(row_bounds),
                        "n_cols": len(retained_column_indices),
                        "cells": cells,
                        "extraction_backend": "pymupdf",
                        "metadata": metadata,
                    }
                ).model_dump()
            )
            finalized_tables.append(finalized_table)
            finalized_tables_by_id[table.table_id] = finalized_table
            continue

        selected_leaf_candidate = (
            confirmed_parent_leaf_candidate or leaf_candidate
        )
        bands = selected_leaf_candidate.bands
        words_by_cell: dict[tuple[int, int], list[tuple[int, str, tuple[float, float, float, float]]]] = {}
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
                center_x = (bbox[0] + bbox[2]) / 2.0
                col_idx = min(
                    range(len(bands)),
                    key=lambda index: abs(
                        center_x - sum(bands[index].canonical_x_bounds) / 2.0
                    ),
                )
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
                cell_words = sorted(
                    words_by_cell.get((row_idx, col_idx), []),
                    key=lambda item: (item[2][0], item[0]),
                )
                text = " ".join(item[1] for item in cell_words)
                bbox = (
                    (
                        min(item[2][0] for item in cell_words),
                        min(item[2][1] for item in cell_words),
                        max(item[2][2] for item in cell_words),
                        max(item[2][3] for item in cell_words),
                    )
                    if cell_words
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
                for separator in selected_leaf_candidate.separators
            ],
            bands[-1].canonical_x_bounds[1],
        ]
        metadata = dict(table.metadata)
        metadata.update(
            {
                "table_cells": table_cells,
                "row_bounds": row_bounds,
                "first_column_text_x0_by_row": first_column_text_x0_by_row,
                "canonical_extraction_layer": "pymupdf_positioned_geometry",
                "grid_refinement_source": (
                    "confirmed_continuation_parent_leaf_geometry"
                    if continuation_confirmation is not None
                    else "body_occupancy_leaf_geometry"
                ),
                "canonical_grid_selection": {
                    **selection_metadata,
                    "selected_row_count": len(row_bounds),
                    "selected_column_boundaries": selected_boundaries,
                    "selected_band_ids": list(
                        selected_leaf_candidate.provisional_grid_band_ids
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
                    "extraction_backend": "pymupdf",
                    "metadata": metadata,
                }
            ).model_dump()
        )
        finalized_tables.append(finalized_table)
        finalized_tables_by_id[table.table_id] = finalized_table

    return finalized_tables
