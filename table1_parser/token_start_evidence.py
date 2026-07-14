"""Build non-operative token-left-edge evidence for unresolved table grids."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from math import floor

from table1_parser.schemas import (
    BodyOccupancyTable,
    ExtractedTable,
    HeaderStructureCandidate,
    LeafColumnCandidateTable,
    PaperPositionedDocument,
    PaperPositionedPage,
    TablePositionedEvidence,
    TokenStartEvidenceTable,
    TokenStartEvaluationReason,
    TokenStartLineEvidence,
    TokenStartObservation,
)


def build_token_start_evidence_tables(
    extracted_tables: Sequence[ExtractedTable],
    *,
    paper_positioned_document: PaperPositionedDocument,
    body_occupancy_tables: Sequence[BodyOccupancyTable],
    leaf_column_candidates: Sequence[LeafColumnCandidateTable],
    header_structure_candidates: Sequence[HeaderStructureCandidate],
) -> list[TokenStartEvidenceTable]:
    """Build token-start records, measuring only tables with refinement signals."""
    pages = {page.page_num: page for page in paper_positioned_document.pages}
    occupancy_by_table_id = {
        occupancy.table_id: occupancy for occupancy in body_occupancy_tables
    }
    leaves_by_table_id = {
        candidate.table_id: candidate for candidate in leaf_column_candidates
    }
    headers_by_table_id = {
        candidate.table_id: candidate for candidate in header_structure_candidates
    }
    return [
        build_token_start_evidence_table(
            table,
            positioned_page=pages.get(table.page_num),
            body_occupancy=occupancy_by_table_id.get(table.table_id),
            leaf_column_candidate=leaves_by_table_id.get(table.table_id),
            header_structure_candidate=headers_by_table_id.get(table.table_id),
        )
        for table in extracted_tables
    ]


def build_token_start_evidence_table(
    table: ExtractedTable,
    *,
    positioned_page: PaperPositionedPage | None,
    body_occupancy: BodyOccupancyTable | None,
    leaf_column_candidate: LeafColumnCandidateTable | None,
    header_structure_candidate: HeaderStructureCandidate | None,
) -> TokenStartEvidenceTable:
    """Build exact token starts for one table when existing evidence is unresolved."""
    source_artifacts = [
        "paper_positioned_document.json",
        "extracted_tables.json:metadata.table_positioned_evidence",
        "body_occupancy.json",
        "leaf_column_candidates.json",
        "header_structure_candidates.json",
    ]
    reasons: list[TokenStartEvaluationReason] = []
    if (
        leaf_column_candidate is not None
        and len(leaf_column_candidate.bands) != table.n_cols
    ):
        reasons.append("grid_count_disagreement")
    header_concerns = (
        header_structure_candidate.concerns
        if header_structure_candidate is not None
        else []
    )
    if any(
        concern.startswith("header_evidence_words_cross_occupancy_bands:")
        for concern in header_concerns
    ):
        reasons.append("cross_band_header_run")
    if any(
        concern.startswith("header_band_without_text:") for concern in header_concerns
    ):
        reasons.append("non_stub_band_without_header_text")
    if any(
        concern.startswith("ambiguous_header_evidence_band:")
        for concern in header_concerns
    ):
        reasons.append("ambiguous_header_attachment")
    if leaf_column_candidate is not None and (
        leaf_column_candidate.concerns or leaf_column_candidate.diagnostics
    ):
        reasons.append("leaf_candidate_concern_or_diagnostic")
    if header_structure_candidate is not None and (
        header_structure_candidate.diagnostics
    ):
        reasons.append("header_candidate_diagnostic")

    body_line_count = len(body_occupancy.lines) if body_occupancy is not None else 0
    if not reasons:
        return TokenStartEvidenceTable(
            table_id=table.table_id,
            page_num=table.page_num,
            source_artifacts=source_artifacts,
            body_line_count=body_line_count,
            x_min=body_occupancy.x_min if body_occupancy is not None else None,
            bin_width=(
                body_occupancy.bin_width if body_occupancy is not None else None
            ),
            bin_count=body_occupancy.bin_count if body_occupancy is not None else 0,
        )

    diagnostics: list[str] = []
    if positioned_page is None:
        diagnostics.append("positioned_page_missing")
    if body_occupancy is None:
        diagnostics.append("body_occupancy_missing")
    elif (
        body_occupancy.x_min is None
        or body_occupancy.bin_width is None
        or body_occupancy.bin_count == 0
        or not body_occupancy.body_row_indices
    ):
        diagnostics.append("body_occupancy_incomplete")
    if leaf_column_candidate is None:
        diagnostics.append("leaf_column_candidate_missing")
    if header_structure_candidate is None:
        diagnostics.append("header_structure_candidate_missing")
    raw_evidence = table.metadata.get("table_positioned_evidence")
    if not isinstance(raw_evidence, dict):
        diagnostics.append("table_positioned_evidence_missing")
    if diagnostics or positioned_page is None or body_occupancy is None:
        return TokenStartEvidenceTable(
            table_id=table.table_id,
            page_num=table.page_num,
            source_artifacts=source_artifacts,
            evaluated=True,
            evaluation_reasons=reasons,
            body_line_count=body_line_count,
            x_min=body_occupancy.x_min if body_occupancy is not None else None,
            bin_width=(
                body_occupancy.bin_width if body_occupancy is not None else None
            ),
            bin_count=body_occupancy.bin_count if body_occupancy is not None else 0,
            diagnostics=diagnostics,
        )

    evidence = TablePositionedEvidence.model_validate(raw_evidence)
    line_id_by_position = {
        (line.block_index, line.line_index): line.line_id
        for line in positioned_page.lines
        if line.block_index is not None and line.line_index is not None
    }
    excluded_marker_char_indices = {
        char_index
        for line in body_occupancy.lines
        for char_index in line.excluded_marker_char_indices
    }
    canonical_chars = []
    for char_index, bbox in zip(
        evidence.char_indices,
        evidence.canonical_char_bboxes,
        strict=False,
    ):
        if char_index >= len(positioned_page.chars):
            continue
        char = positioned_page.chars[char_index]
        canonical_chars.append((char_index, char, bbox))

    observations_by_line: dict[str, list[TokenStartObservation]] = defaultdict(list)
    words_without_characters = 0
    body_row_indices = set(body_occupancy.body_row_indices)
    bands = leaf_column_candidate.bands if leaf_column_candidate is not None else []
    for word_index, word_bbox in zip(
        evidence.word_indices,
        evidence.canonical_word_bboxes,
        strict=False,
    ):
        if word_index >= len(positioned_page.words):
            continue
        word = positioned_page.words[word_index]
        if not word.text.strip():
            continue
        source_line_id = line_id_by_position.get((word.block_index, word.line_index))
        if source_line_id is None:
            continue
        center_y = (word_bbox[1] + word_bbox[3]) / 2.0
        candidate_lines = [
            line
            for line in body_occupancy.lines
            if source_line_id in line.source_line_ids
            and body_row_indices.intersection(line.source_row_indices)
        ]
        if not candidate_lines:
            continue
        body_line = min(
            candidate_lines,
            key=lambda line: abs(
                center_y - (line.canonical_bbox[1] + line.canonical_bbox[3]) / 2.0
            ),
        )
        row_idx = min(body_row_indices.intersection(body_line.source_row_indices))
        word_characters = [
            (char_index, char, bbox)
            for char_index, char, bbox in canonical_chars
            if char.block_index == word.block_index
            and char.line_index == word.line_index
            and word_bbox[0] - 1.0 <= (bbox[0] + bbox[2]) / 2.0 <= word_bbox[2] + 1.0
            and word_bbox[1] - 1.0 <= (bbox[1] + bbox[3]) / 2.0 <= word_bbox[3] + 1.0
            and char.text.strip()
        ]
        ordinary_characters = [
            item
            for item in word_characters
            if item[0] not in excluded_marker_char_indices
        ]
        if not ordinary_characters:
            if not word_characters:
                words_without_characters += 1
            continue
        source_char_index, _, first_char_bbox = min(
            ordinary_characters,
            key=lambda item: (item[2][0], item[0]),
        )
        canonical_x = first_char_bbox[0]
        occupancy_band_id = next(
            (
                band.band_id
                for band_index, band in enumerate(bands)
                if band.canonical_x_bounds[0] <= canonical_x
                and (
                    canonical_x < band.canonical_x_bounds[1]
                    or (
                        band_index == len(bands) - 1
                        and canonical_x <= band.canonical_x_bounds[1]
                    )
                )
            ),
            None,
        )
        observation_id = f"{table.table_id}:token_start:{word_index}"
        observations_by_line[body_line.line_id].append(
            TokenStartObservation(
                observation_id=observation_id,
                source_word_index=word_index,
                source_char_index=source_char_index,
                source_line_id=source_line_id,
                source_row_idx=row_idx,
                canonical_x=canonical_x,
                canonical_bbox=word_bbox,
                occupancy_band_id=occupancy_band_id,
            )
        )

    if words_without_characters:
        diagnostics.append(
            f"positioned_words_without_ordinary_characters:{words_without_characters}"
        )
    lines: list[TokenStartLineEvidence] = []
    for body_line in body_occupancy.lines:
        observations = observations_by_line.get(body_line.line_id, [])
        if not observations:
            continue
        observations.sort(key=lambda item: (item.canonical_x, item.source_word_index))
        lines.append(
            TokenStartLineEvidence(
                line_id=body_line.line_id,
                source_line_ids=body_line.source_line_ids,
                source_row_indices=body_line.source_row_indices,
                observations=observations,
            )
        )

    token_start_counts = [0] * body_occupancy.bin_count
    line_ids_by_bin: list[set[str]] = [set() for _ in range(body_occupancy.bin_count)]
    for line in lines:
        for observation in line.observations:
            bin_index = floor(
                (observation.canonical_x - body_occupancy.x_min)
                / body_occupancy.bin_width
            )
            if 0 <= bin_index < body_occupancy.bin_count:
                token_start_counts[bin_index] += 1
                line_ids_by_bin[bin_index].add(line.line_id)
    observation_count = sum(len(line.observations) for line in lines)
    return TokenStartEvidenceTable(
        table_id=table.table_id,
        page_num=table.page_num,
        source_artifacts=source_artifacts,
        evaluated=True,
        evaluation_reasons=reasons,
        body_line_count=body_line_count,
        observed_line_count=len(lines),
        observation_count=observation_count,
        x_min=body_occupancy.x_min,
        bin_width=body_occupancy.bin_width,
        bin_count=body_occupancy.bin_count,
        token_start_counts=token_start_counts,
        token_start_line_counts=[len(line_ids) for line_ids in line_ids_by_bin],
        lines=lines,
        diagnostics=diagnostics,
    )


def token_start_evidence_tables_to_payload(
    tables: Sequence[TokenStartEvidenceTable],
) -> list[dict[str, object]]:
    """Serialize token-start evidence as JSON-ready dictionaries."""
    return [table.model_dump(mode="json") for table in tables]
