"""PyMuPDF4LLM-based extraction backend."""

from __future__ import annotations

import contextlib
import io
import json
import re
from pathlib import Path
from collections.abc import Sequence
from typing import Any

from table1_parser.config import Settings
from table1_parser.extract.base import BaseExtractor
from table1_parser.extract.layout_fallback import (
    build_row_grid_from_lines,
    build_text_layout_candidates,
    build_word_lines,
    detect_horizontal_rules,
    normalize_positioned_geometry_for_rotation,
    trim_trailing_non_table_rows,
)
from table1_parser.extract.pymupdf_page_adapter import (
    extract_clipped_line_directions,
    extract_page_chars,
    extract_page_rule_segments,
    extract_page_text,
    extract_page_words,
    join_pymupdf_line_spans,
    open_pymupdf_document,
)
from table1_parser.extract.table_detector import (
    DetectedTableCandidate,
    _caption_for_index,
    _find_table_caption_lines,
    _normalize_rows,
    score_candidate,
)
from table1_parser.extract.table_selector import select_top_candidates
from table1_parser.page_furniture_mask import (
    filter_positioned_items_for_page_furniture,
    filter_table_rows_for_page_furniture,
    page_furniture_cluster_ids_for_bbox,
)
from table1_parser.reference_sections import text_has_reference_section_start
from table1_parser.schemas import ExtractedTable, PaperPageFurniture, PaperTableMention, TableCell
from table1_parser.text_cleaning import clean_text


MODEL_HEADER_PATTERN = re.compile(r"\bmodel[_\s]*\d+\b", re.IGNORECASE)
ESTIMATE_HEADER_PATTERN = re.compile(r"\b(?:or\b|95%\s*ci|p(?:-value)?\b)\b", re.IGNORECASE)
INTRODUCTION_HEADING_PATTERN = re.compile(
    r"^(?:\d+(?:\.\d+)*\.?\s+)?introduction\b",
    re.IGNORECASE,
)


class PyMuPDF4LLMExtractor(BaseExtractor):
    """Extract raw table grids with PyMuPDF4LLM."""

    backend_name = "pymupdf4llm"

    def __init__(
        self,
        max_candidates: int | None = None,
        heuristic_confidence_threshold: float | None = None,
    ) -> None:
        settings = Settings()
        self.max_candidates = max_candidates or settings.max_table_candidates
        self.heuristic_confidence_threshold = (
            heuristic_confidence_threshold
            if heuristic_confidence_threshold is not None
            else settings.heuristic_confidence_threshold
        )

    def extract(
        self,
        pdf_path: str,
        *,
        paper_page_furniture: PaperPageFurniture | None = None,
        paper_table_mentions: Sequence[PaperTableMention] | None = None,
    ) -> list[ExtractedTable]:
        """Extract and rank raw table candidates from a PDF."""
        try:
            candidates = self._detect_table_candidates(
                pdf_path,
                paper_page_furniture=paper_page_furniture,
                paper_table_mentions=paper_table_mentions,
            )
        except Exception:
            return []

        if not candidates:
            return []

        selected_candidates = select_top_candidates(
            candidates=candidates,
            max_candidates=self.max_candidates,
            confidence_threshold=self.heuristic_confidence_threshold,
        )
        if not selected_candidates:
            return []

        tables = [
            self._build_extracted_table(pdf_path=pdf_path, candidate=candidate)
            for candidate in selected_candidates
        ]
        observed_table_numbers = sorted(
            {
                table_number
                for table_number in (table.metadata.get("table_number") for table in tables)
                if isinstance(table_number, int)
            }
        )
        if observed_table_numbers:
            missing_table_numbers = [
                table_number
                for table_number in range(observed_table_numbers[0], observed_table_numbers[-1] + 1)
                if table_number not in observed_table_numbers
            ]
        else:
            missing_table_numbers = []
        table_numbering_audit = {
            "observed_table_numbers": observed_table_numbers,
            "missing_table_numbers": missing_table_numbers,
        }
        return [
            table.model_copy(
                update={
                    "metadata": {
                        **table.metadata,
                        "table_numbering_audit": table_numbering_audit,
                    }
                }
            )
            for table in tables
        ]

    def _detect_table_candidates(
        self,
        pdf_path: str,
        *,
        paper_page_furniture: PaperPageFurniture | None = None,
        paper_table_mentions: Sequence[PaperTableMention] | None = None,
    ) -> list[DetectedTableCandidate]:
        try:
            import pymupdf4llm
        except ModuleNotFoundError as exc:
            raise ModuleNotFoundError(
                "pymupdf4llm is required for the pymupdf4llm extraction backend."
            ) from exc
        stdout_buffer = io.StringIO()
        with contextlib.redirect_stdout(stdout_buffer):
            payload = json.loads(pymupdf4llm.to_json(pdf_path))
        pages = {
            int(page.get("page_number", 0)): page
            for page in payload.get("pages", [])
            if isinstance(page, dict)
        }
        if not pages:
            return []
        candidates: list[DetectedTableCandidate] = []
        explicit_page_nums: set[int] = set()
        try:
            document = open_pymupdf_document(pdf_path)
        except Exception:
            document = None
        try:
            in_references_section = False
            references_start_page_num: int | None = None
            front_matter_intervals = _front_matter_intervals_by_page(document)
            for page_num, payload_page in sorted(pages.items()):
                page = None
                if document is not None and 0 <= page_num - 1 < getattr(document, "page_count", 0):
                    page = document.load_page(page_num - 1)
                page_boxes = payload_page.get("boxes", []) or []
                page_text = _collect_page_text(page_boxes)
                extracted_page_text = ""
                if page is not None:
                    extracted_page_text = extract_page_text(page)
                    if extracted_page_text and extracted_page_text not in page_text:
                        page_text = f"{page_text}\n{extracted_page_text}".strip()
                if text_has_reference_section_start(page_text):
                    in_references_section = True
                    if references_start_page_num is None:
                        references_start_page_num = page_num
                if in_references_section:
                    continue
                page_word_mask_metadata: dict[str, object] | None = None
                page_char_mask_metadata: dict[str, object] | None = None
                if page is None:
                    page_words = []
                    page_chars = []
                    page_rule_segments = []
                    page_stroked_rule_segments = []
                else:
                    page_words, page_word_mask_metadata = filter_positioned_items_for_page_furniture(
                        extract_page_words(page),
                        paper_page_furniture,
                        page_num=page_num,
                    )
                    page_chars, page_char_mask_metadata = filter_positioned_items_for_page_furniture(
                        _extract_page_chars_with_page_num(page, page_num),
                        paper_page_furniture,
                        page_num=page_num,
                    )
                    page_rule_segments = extract_page_rule_segments(page)
                    page_stroked_rule_segments = extract_page_rule_segments(page, include_filled=False)
                page_item_furniture_mask = {
                    key: value
                    for key, value in {
                        "word_items": page_word_mask_metadata,
                        "char_items": page_char_mask_metadata,
                    }.items()
                    if value is not None
                }
                page_candidates: list[DetectedTableCandidate] = []
                table_boxes = [
                    box
                    for box in page_boxes
                    if isinstance(box, dict)
                    and box.get("table")
                    and not page_furniture_cluster_ids_for_bbox(
                        paper_page_furniture,
                        page_num=page_num,
                        bbox=_as_bbox((box.get("table") or {}).get("bbox")) or _box_bbox(box),
                        min_overlap_fraction=0.8,
                    )
                ]
                table_count = len(table_boxes)
                table_box_bboxes = [
                    _as_bbox((table_box.get("table") or {}).get("bbox")) or _box_bbox(table_box)
                    for table_box in table_boxes
                ]
                caption_boxes: list[tuple[tuple[float, float, float, float], str]] = []
                for candidate_box in page_boxes:
                    if candidate_box.get("boxclass") == "table":
                        continue
                    candidate_bbox = _box_bbox(candidate_box)
                    if candidate_bbox is None:
                        continue
                    caption_lines = _find_table_caption_lines(_extract_box_text(candidate_box))
                    if not caption_lines:
                        continue
                    caption_boxes.append((candidate_bbox, caption_lines[-1]))
                for table_index, box in enumerate(table_boxes):
                    table = box.get("table") or {}
                    original_raw_rows = _normalize_rows(table.get("extract") or [])
                    raw_rows = original_raw_rows
                    if not original_raw_rows:
                        continue
                    bbox = (
                        table_box_bboxes[table_index]
                        if table_index < len(table_box_bboxes)
                        else None
                    )
                    nearby_caption_candidates: list[tuple[float, tuple[float, float, float, float], str]] = []
                    table_top = bbox[1] if bbox else float("inf")
                    for candidate_bbox, caption_line in caption_boxes:
                        if candidate_bbox[3] > table_top + 2.0:
                            continue
                        intervening_table = any(
                            other_index != table_index
                            and other_bbox is not None
                            and other_bbox[1] > candidate_bbox[3] + 2.0
                            and other_bbox[1] < table_top - 2.0
                            for other_index, other_bbox in enumerate(table_box_bboxes)
                        )
                        if intervening_table:
                            continue
                        nearby_caption_candidates.append(
                            (table_top - candidate_bbox[3], candidate_bbox, caption_line)
                        )
                    if nearby_caption_candidates:
                        _, nearby_caption_bbox, nearby_caption = min(
                            nearby_caption_candidates,
                            key=lambda item: item[0],
                        )
                        caption_lines = [nearby_caption]
                        for text_box in page_boxes:
                            if text_box.get("boxclass") in {"table", "page-header", "page-footer"}:
                                continue
                            text_bbox = _box_bbox(text_box)
                            if text_bbox is None:
                                continue
                            if text_bbox[1] < nearby_caption_bbox[3] - 2.0 or text_bbox[3] > table_top + 2.0:
                                continue
                            text = _extract_box_text(text_box)
                            if not text or _find_table_caption_lines(text):
                                continue
                            caption_lines.append(text)
                        nearby_caption = "\n".join(caption_lines)
                    else:
                        nearby_caption_bbox = None
                        nearby_caption = None
                    cell_bboxes = _coerce_cell_bboxes(table.get("cells") or [])
                    orientation_metadata = _infer_table_orientation_metadata(page, bbox)
                    refinement = _refine_explicit_table_candidate_grid(
                        raw_rows=raw_rows,
                        cell_bboxes=cell_bboxes,
                        bbox=bbox,
                        caption_bbox=nearby_caption_bbox,
                        page_words=page_words,
                        page_chars=page_chars,
                        page_rule_segments=page_rule_segments,
                        full_width_rule_segments=page_stroked_rule_segments,
                        orientation_metadata=orientation_metadata,
                    )
                    raw_rows = refinement["raw_rows"]
                    cell_bboxes = refinement["table_cells"]
                    row_bounds = refinement["row_bounds"]
                    horizontal_rules = refinement["horizontal_rules"]
                    full_width_horizontal_rules = refinement["full_width_horizontal_rules"]
                    geometry_coordinate_frame = str(refinement["geometry_coordinate_frame"])
                    table_bbox_cluster_ids = page_furniture_cluster_ids_for_bbox(
                        paper_page_furniture,
                        page_num=page_num,
                        bbox=bbox,
                        min_overlap_fraction=0.0,
                    )
                    page_furniture_overlap = {
                        "source_artifact": "paper_page_furniture.json",
                        "has_overlap": bool(table_bbox_cluster_ids),
                        "table_bbox_cluster_ids": table_bbox_cluster_ids,
                    }
                    row_furniture_mask: dict[str, object] | None = None
                    if geometry_coordinate_frame == "page":
                        row_mask = filter_table_rows_for_page_furniture(
                            raw_rows,
                            cell_bboxes=cell_bboxes,
                            row_bounds=row_bounds,
                            paper_page_furniture=paper_page_furniture,
                            page_num=page_num,
                        )
                        raw_rows = row_mask.raw_rows
                        cell_bboxes = row_mask.cell_bboxes
                        row_bounds = row_mask.row_bounds
                        row_furniture_mask = row_mask.metadata
                        if not raw_rows:
                            continue
                    is_block_scoped_rotated_stream = (
                        geometry_coordinate_frame
                        in {
                            "table_local_rotated_normalized",
                            "table_local_rotated_transposed_normalized",
                        }
                        and orientation_metadata.get("rotated_text_block_bbox") is not None
                    )
                    trailing_non_table_rows: dict[str, object] | None = None
                    if not is_block_scoped_rotated_stream:
                        trimmed = trim_trailing_non_table_rows(
                            raw_rows,
                            cell_bboxes=cell_bboxes,
                            row_bounds=row_bounds,
                        )
                        raw_rows = trimmed.raw_rows
                        cell_bboxes = trimmed.cell_bboxes
                        row_bounds = trimmed.row_bounds
                        trailing_non_table_rows = trimmed.metadata
                        if trailing_non_table_rows is not None and row_bounds:
                            table_bottom = row_bounds[-1][1]
                            horizontal_rules = [
                                rule for rule in horizontal_rules if float(rule) <= table_bottom + 2.0
                            ]
                            full_width_horizontal_rules = [
                                rule for rule in full_width_horizontal_rules if float(rule) <= table_bottom + 2.0
                            ]
                    first_column_text_x0_by_row = (
                        _infer_first_column_text_x0_by_row(
                            raw_rows=raw_rows,
                            cell_bboxes=cell_bboxes,
                            page_words=page_words,
                        )
                        if geometry_coordinate_frame == "page"
                        else {}
                    )
                    if nearby_caption is not None:
                        caption = _caption_for_index(
                            nearby_caption,
                            page_text,
                            table_index,
                            table_count,
                        )
                    elif caption_boxes:
                        caption = None
                    else:
                        caption = _caption_for_index(
                            None,
                            page_text,
                            table_index,
                            table_count,
                        )
                    scored_candidate = score_candidate(
                        DetectedTableCandidate(
                            page_num=page_num,
                            table_index=table_index,
                            bbox=bbox,
                            raw_rows=raw_rows,
                            caption=caption,
                            page_text=page_text,
                            metadata={
                                "layout_source": "pymupdf4llm_json",
                                "caption_source": (
                                    "nearby_above_table"
                                    if nearby_caption is not None and caption == nearby_caption
                                    else "page_text_fallback" if caption is not None else None
                                ),
                                "primary_representation": "json",
                                "extractor_used": self.backend_name,
                                "fallback_used": False,
                                "row_count": table.get("row_count"),
                                "col_count": table.get("col_count"),
                                "explicit_grid_refined_from_words": raw_rows != original_raw_rows,
                                "grid_refinement_source": refinement["grid_refinement_source"],
                                "geometry_coordinate_frame": geometry_coordinate_frame,
                                "geometry_transform_source_bbox": refinement.get(
                                    "geometry_transform_source_bbox"
                                ),
                                "geometry_transform_transposed": refinement.get(
                                    "geometry_transform_transposed"
                                ),
                                "geometry_transform_applied": refinement.get(
                                    "geometry_transform_applied"
                                ),
                                "value_matrix_column_anchors": refinement.get(
                                    "value_matrix_column_anchors"
                                ),
                                "table_markdown": table.get("markdown"),
                                "table_cells": cell_bboxes,
                                "first_column_text_x0_by_row": first_column_text_x0_by_row,
                                "refined_table_cells": refinement["refined_table_cells"],
                                "original_table_cells": (
                                    table.get("cells")
                                    if raw_rows != original_raw_rows
                                    else None
                                ),
                                "original_backend_rows": (
                                    table.get("extract")
                                    if raw_rows != original_raw_rows
                                    else None
                                ),
                                "row_bounds": row_bounds,
                                "horizontal_rules": horizontal_rules,
                                "full_width_horizontal_rules": full_width_horizontal_rules,
                                "trailing_non_table_rows": trailing_non_table_rows,
                                "page_furniture_overlap": page_furniture_overlap,
                                "page_furniture_mask": {
                                    key: value
                                    for key, value in {
                                        **page_item_furniture_mask,
                                        "rows": row_furniture_mask,
                                    }.items()
                                    if value is not None
                                },
                                **orientation_metadata,
                            },
                        )
                    )
                    populated_cells = [
                        cell.strip()
                        for row in scored_candidate.raw_rows
                        for cell in row
                        if cell.strip()
                    ]
                    prose_like_cells = sum(
                        len(cell.split()) >= 5 and bool(re.search(r"[A-Za-z]", cell))
                        for cell in populated_cells
                    )
                    value_like_cells = sum(
                        bool(re.fullmatch(r"(?:[<>]=?\s*)?[\d.,/%()\s+-]+", cell))
                        and bool(re.search(r"\d", cell))
                        for cell in populated_cells
                    )
                    uncaptioned_prose_shard = (
                        scored_candidate.caption is None
                        and len(scored_candidate.raw_rows) == 1
                        and _column_count(scored_candidate) >= 8
                        and prose_like_cells >= max(4, len(populated_cells) // 3)
                        and value_like_cells <= max(1, len(populated_cells) // 10)
                    )
                    if uncaptioned_prose_shard:
                        continue
                    if _is_uncaptioned_front_matter_layout_candidate(
                        scored_candidate,
                        front_matter_intervals.get(page_num),
                    ):
                        continue
                    page_candidates.append(scored_candidate)
                    rotated_block_candidate = _build_rotated_block_candidate_from_mixed_table_box(
                        page_num=page_num,
                        table_index=table_index,
                        page=page,
                        page_text=page_text,
                        page_words=page_words,
                        page_chars=page_chars,
                        page_rule_segments=page_rule_segments,
                        page_stroked_rule_segments=page_stroked_rule_segments,
                        source_bbox=bbox,
                        source_table=table,
                        source_candidate=scored_candidate,
                        caption=caption,
                        paper_page_furniture=paper_page_furniture,
                    )
                    if rotated_block_candidate is not None:
                        page_candidates.append(rotated_block_candidate)
                page_candidates = self._rescue_low_quality_page_candidates(
                    page_num=page_num,
                    page=page,
                    page_text=page_text,
                    page_candidates=page_candidates,
                    paper_page_furniture=paper_page_furniture,
                    paper_table_mentions=paper_table_mentions,
                )
                if page is not None and page_words:
                    extracted_page_text = extract_page_text(page)
                    sideways_page_text = page_text
                    if extracted_page_text and extracted_page_text not in sideways_page_text:
                        sideways_page_text = f"{sideways_page_text}\n{extracted_page_text}".strip()
                    page_rect = getattr(page, "rect", None)
                    if page_rect is not None and all(hasattr(page_rect, attr) for attr in ("width", "height")):
                        page_bbox = (0.0, 0.0, float(page_rect.width), float(page_rect.height))
                    else:
                        page_bbox = (
                            min(float(word["x0"]) for word in page_words),
                            min(float(word["top"]) for word in page_words),
                            max(float(word["x1"]) for word in page_words),
                            max(float(word["bottom"]) for word in page_words),
                        )
                    page_width = max(1.0, page_bbox[2] - page_bbox[0])
                    page_height = max(1.0, page_bbox[3] - page_bbox[1])
                    page_rotation = int(getattr(page, "rotation", 0) or 0)
                    page_directions = extract_clipped_line_directions(page, page_bbox)
                    horizontal_count = 0
                    vertical_up_count = 0
                    vertical_down_count = 0
                    for dx, dy in page_directions:
                        if abs(dx) >= 0.8 and abs(dy) <= 0.2:
                            horizontal_count += 1
                            continue
                        if abs(dy) >= 0.8 and abs(dx) <= 0.2:
                            if dy < 0:
                                vertical_up_count += 1
                            else:
                                vertical_down_count += 1
                    vertical_count = vertical_up_count + vertical_down_count
                    considered_count = horizontal_count + vertical_count
                    vertical_confidence = (
                        vertical_count / considered_count
                        if considered_count
                        else 0.0
                    )
                    caption_lines = _find_table_caption_lines(sideways_page_text)
                    collapsed_page_candidate = any(
                        _looks_like_collapsed_grid_candidate(candidate)
                        for candidate in page_candidates
                    )
                    sideways_signals: list[str] = []
                    if page_width < page_height:
                        sideways_signals.append("portrait_page")
                    if page_rotation == 0:
                        sideways_signals.append("page_rotation_zero")
                    if vertical_confidence >= 0.75 and vertical_count >= max(8, horizontal_count * 2):
                        sideways_signals.append("vertical_line_directions")
                    if caption_lines:
                        sideways_signals.append("table_caption_in_page_text")
                    if collapsed_page_candidate:
                        sideways_signals.append("collapsed_upright_candidate")
                    is_sideways_page = (
                        (
                            page_width < page_height
                            and page_rotation == 0
                            and vertical_confidence >= 0.75
                            and vertical_count >= max(8, horizontal_count * 2)
                            and bool(caption_lines)
                        )
                        or (
                            vertical_confidence >= 0.75
                            and vertical_count >= 20
                            and bool(caption_lines)
                            and collapsed_page_candidate
                        )
                    )
                    if is_sideways_page:
                        rotation_direction = (
                            "vertical_text_up"
                            if vertical_up_count >= vertical_down_count
                            else "vertical_text_down"
                        )
                        (
                            transformed_words,
                            transformed_chars,
                            transformed_rule_segments,
                            _transformed_bbox,
                        ) = normalize_positioned_geometry_for_rotation(
                            words=page_words,
                            chars=page_chars,
                            rule_segments=page_rule_segments,
                            bbox=page_bbox,
                            rotation_direction=rotation_direction,
                        )
                        sideways_candidates = build_text_layout_candidates(
                            page_num=page_num,
                            page_text=sideways_page_text,
                            words=transformed_words,
                            chars=transformed_chars,
                            rule_segments=transformed_rule_segments,
                            layout_source="sideways_text_positions",
                            paper_table_mentions=paper_table_mentions,
                        )
                        for sideways_candidate in sideways_candidates:
                            n_cols = _column_count(sideways_candidate)
                            data_like_rows = sum(
                                sum(
                                    bool(re.search(r"\d", cell))
                                    for cell in row[1:]
                                    if cell.strip()
                                )
                                >= 2
                                for row in sideways_candidate.raw_rows[1:]
                            )
                            if (
                                len(sideways_candidate.raw_rows) < 4
                                or n_cols < 3
                                or data_like_rows < 2
                            ):
                                continue
                            target_table_index = sideways_candidate.table_index
                            sideways_table_number = sideways_candidate.metadata.get("table_number")
                            same_number_candidates = [
                                candidate
                                for candidate in page_candidates
                                if candidate.metadata.get("table_number") == sideways_table_number
                                and sideways_table_number is not None
                            ]
                            if same_number_candidates:
                                target_table_index = same_number_candidates[0].table_index
                            elif len(sideways_candidates) == 1 and len(page_candidates) == 1:
                                target_table_index = page_candidates[0].table_index
                            replacement_candidate = sideways_candidate.model_copy(
                                update={
                                    "table_index": target_table_index,
                                    "metadata": {
                                        **sideways_candidate.metadata,
                                        "primary_representation": "json",
                                        "extractor_used": self.backend_name,
                                        "fallback_used": True,
                                        "orientation_strategy": "sideways_transformed",
                                        "sideways_candidate": True,
                                        "sideways_detection_signals": sideways_signals,
                                        "sideways_vertical_confidence": round(vertical_confidence, 4),
                                        "rotation_direction": rotation_direction,
                                        "caption_detection_space": "transformed_coordinates",
                                        "geometry_coordinate_frame": "page_sideways_transformed",
                                        "geometry_transform_source_bbox": page_bbox,
                                        "geometry_transform_transposed": False,
                                        "geometry_transform_applied": True,
                                        "grid_refinement_source": "sideways_text_positions",
                                        "table_orientation": "rotated",
                                        "rotation_source": "pymupdf_page_line_direction",
                                        "rotation_confidence": round(vertical_confidence, 4),
                                        "page_furniture_mask": page_item_furniture_mask,
                                    },
                                }
                            )
                            replaced_candidate = False
                            for candidate_index, existing_candidate in enumerate(page_candidates):
                                if existing_candidate.table_index != target_table_index:
                                    continue
                                higher_quality_replacement = (
                                    replacement_candidate.score >= existing_candidate.score
                                    and (
                                        _column_count(replacement_candidate) > _column_count(existing_candidate)
                                        or len(replacement_candidate.raw_rows) > len(existing_candidate.raw_rows)
                                    )
                                )
                                structural_replacement = (
                                    _looks_like_collapsed_grid_candidate(existing_candidate)
                                    and replacement_candidate.score >= self.heuristic_confidence_threshold
                                    and _column_count(replacement_candidate) > _column_count(existing_candidate)
                                    and len(replacement_candidate.raw_rows) >= len(existing_candidate.raw_rows)
                                )
                                if higher_quality_replacement or structural_replacement:
                                    page_candidates[candidate_index] = replacement_candidate
                                    replaced_candidate = True
                                break
                            if not replaced_candidate:
                                page_candidates.append(replacement_candidate)
                if page_candidates:
                    explicit_page_nums.add(page_num)
                    candidates.extend(page_candidates)

            if pages and len(explicit_page_nums) == len(pages):
                return candidates

            for page_index in range(getattr(document, "page_count", 0) if document is not None else 0):
                page_num = page_index + 1
                if page_num in explicit_page_nums:
                    continue
                page = document.load_page(page_index)
                payload_page = pages.get(page_num, {})
                page_boxes = payload_page.get("boxes", []) or []
                page_text = _collect_page_text(page_boxes)
                extracted_page_text = extract_page_text(page)
                if extracted_page_text and extracted_page_text not in page_text:
                    page_text = f"{page_text}\n{extracted_page_text}".strip()
                if references_start_page_num is not None and page_num >= references_start_page_num:
                    continue
                if text_has_reference_section_start(page_text):
                    references_start_page_num = page_num
                    continue
                for candidate in build_text_layout_candidates(
                    page_num=page_num,
                    page_text=page_text,
                    words=extract_page_words(page),
                    chars=_extract_page_chars_with_page_num(page, page_num),
                    rule_segments=extract_page_rule_segments(page, include_filled=False),
                    layout_source="pymupdf_text_positions",
                    paper_page_furniture=paper_page_furniture,
                    paper_table_mentions=paper_table_mentions,
                ):
                    candidates.append(
                        candidate.model_copy(
                            update={
                                "metadata": {
                                    **candidate.metadata,
                                    "primary_representation": "json",
                                    "extractor_used": self.backend_name,
                                    "fallback_used": False,
                                    **_infer_table_orientation_metadata(page, candidate.bbox),
                                }
                            }
                        )
                    )
        finally:
            close = getattr(document, "close", None)
            if callable(close):
                close()
        return candidates

    def _build_extracted_table(
        self,
        pdf_path: str,
        candidate: DetectedTableCandidate,
    ) -> ExtractedTable:
        if not candidate.caption:
            title, caption = None, None
        else:
            lines = [line.strip() for line in candidate.caption.splitlines() if line.strip()]
            if not lines:
                title, caption = None, None
            elif len(lines) == 1:
                title, caption = lines[0], lines[0]
            else:
                title, caption = lines[0], " ".join(lines)
        cells: list[TableCell] = []
        table_cells = candidate.metadata.get("table_cells") or []
        cell_bboxes = _coerce_cell_bboxes(table_cells)
        for row_idx, row in enumerate(candidate.raw_rows):
            for col_idx, cell_text in enumerate(row):
                bbox = None
                if row_idx < len(cell_bboxes) and col_idx < len(cell_bboxes[row_idx]):
                    bbox = cell_bboxes[row_idx][col_idx]
                cells.append(
                    TableCell(
                        row_idx=row_idx,
                        col_idx=col_idx,
                        text=cell_text,
                        page_num=candidate.page_num,
                        bbox=bbox,
                        extractor_name=self.backend_name,
                        confidence=candidate.score,
                    )
                )

        metadata = {
            **candidate.metadata,
            "bbox": candidate.bbox,
            "candidate_score": candidate.score,
        }
        return ExtractedTable(
            table_id=f"{Path(pdf_path).stem}-p{candidate.page_num}-t{candidate.table_index}",
            source_pdf=pdf_path,
            page_num=candidate.page_num,
            title=title,
            caption=caption,
            n_rows=len(candidate.raw_rows),
            n_cols=max((len(row) for row in candidate.raw_rows), default=0),
            cells=cells,
            extraction_backend=self.backend_name,
            metadata=metadata,
        )

    def _rescue_low_quality_page_candidates(
        self,
        *,
        page_num: int,
        page: Any,
        page_text: str,
        page_candidates: list[DetectedTableCandidate],
        paper_page_furniture: PaperPageFurniture | None = None,
        paper_table_mentions: Sequence[PaperTableMention] | None = None,
    ) -> list[DetectedTableCandidate]:
        """Replace suspicious explicit page candidates with better text-layout candidates."""
        if page is None or not any(
            candidate.score < self.heuristic_confidence_threshold
            and bool(candidate.metadata.get("signals", {}).get("caption_match", False))
            and (
                _column_count(candidate) <= 2
                or _first_column_fill_ratio(candidate) < 0.25
            )
            for candidate in page_candidates
        ):
            return page_candidates

        rescue_candidates = build_text_layout_candidates(
            page_num=page_num,
            page_text=page_text or extract_page_text(page),
            words=extract_page_words(page),
            chars=_extract_page_chars_with_page_num(page, page_num),
            rule_segments=extract_page_rule_segments(page, include_filled=False),
            layout_source="pymupdf_text_positions_rescue",
            paper_page_furniture=paper_page_furniture,
            paper_table_mentions=paper_table_mentions,
        )
        if not rescue_candidates:
            return page_candidates

        rescued: list[DetectedTableCandidate] = []
        for candidate in page_candidates:
            target_table_number = candidate.metadata.get("signals", {}).get("caption_table_number")
            matching = [
                rescue
                for rescue in rescue_candidates
                if rescue.metadata.get("signals", {}).get("caption_table_number") == target_table_number
            ]
            ranked = matching or rescue_candidates
            if not ranked:
                replacement = None
            else:
                best = sorted(
                    ranked,
                    key=lambda rescue: (-rescue.score, -_column_count(rescue), -len(rescue.raw_rows)),
                )[0]
                should_replace = (
                    best.score >= self.heuristic_confidence_threshold
                    and best.score > candidate.score
                    and (
                        _column_count(best) > _column_count(candidate)
                        or _first_column_fill_ratio(best) > _first_column_fill_ratio(candidate) + 0.4
                        or len(best.raw_rows) > len(candidate.raw_rows) + 5
                    )
                )
                replacement = best if should_replace else None
            if replacement is None:
                rescued.append(candidate)
                continue
            rescued.append(
                replacement.model_copy(
                    update={
                        "table_index": candidate.table_index,
                        "metadata": {
                            **replacement.metadata,
                            "extractor_used": self.backend_name,
                            "fallback_used": True,
                            **_infer_table_orientation_metadata(page, replacement.bbox),
                        },
                    }
                )
            )
        return rescued


def _build_rotated_block_candidate_from_mixed_table_box(
    *,
    page_num: int,
    table_index: int,
    page: Any,
    page_text: str,
    page_words: list[dict[str, object]],
    page_chars: list[dict[str, object]],
    page_rule_segments: list[tuple[float, float, float, float]],
    page_stroked_rule_segments: list[tuple[float, float, float, float]],
    source_bbox: tuple[float, float, float, float] | None,
    source_table: dict[str, Any],
    source_candidate: DetectedTableCandidate,
    caption: str | None,
    paper_page_furniture: PaperPageFurniture | None,
) -> DetectedTableCandidate | None:
    """Recover a rotated table block when PyMuPDF4LLM emits a mixed-orientation table box."""
    if page is None or source_bbox is None:
        return None
    if source_candidate.metadata.get("table_orientation") == "rotated":
        return None
    signals = source_candidate.metadata.get("signals", {})
    if not isinstance(signals, dict) or not signals.get("caption_match"):
        return None

    rotated_orientation = _find_rotated_text_block_in_bbox(page, source_bbox)
    rotated_bbox = _as_bbox(rotated_orientation.get("rotated_text_block_bbox")) if rotated_orientation else None
    if rotated_orientation is None or rotated_bbox is None:
        return None

    refinement = _refine_explicit_table_candidate_grid(
        raw_rows=[[""]],
        cell_bboxes=[],
        bbox=rotated_bbox,
        caption_bbox=None,
        page_words=page_words,
        page_chars=page_chars,
        page_rule_segments=page_rule_segments,
        full_width_rule_segments=page_stroked_rule_segments,
        orientation_metadata=rotated_orientation,
    )
    raw_rows = refinement["raw_rows"]
    if not isinstance(raw_rows, list) or not raw_rows:
        return None
    n_cols = max((len(row) for row in raw_rows), default=0)
    data_like_rows = sum(
        sum(bool(re.search(r"\d", cell)) for cell in row[1:] if cell.strip()) >= 2
        for row in raw_rows[1:]
    )
    if len(raw_rows) < 4 or n_cols < 3 or data_like_rows < 2:
        return None
    if str(refinement.get("geometry_coordinate_frame") or "") not in {
        "table_local_rotated_normalized",
        "table_local_rotated_transposed_normalized",
    }:
        return None

    table_bbox_cluster_ids = page_furniture_cluster_ids_for_bbox(
        paper_page_furniture,
        page_num=page_num,
        bbox=rotated_bbox,
        min_overlap_fraction=0.0,
    )
    return score_candidate(
        DetectedTableCandidate(
            page_num=page_num,
            table_index=table_index,
            bbox=rotated_bbox,
            raw_rows=raw_rows,
            caption=caption,
            page_text=page_text,
            metadata={
                "layout_source": "pymupdf4llm_json_rotated_block_repair",
                "caption_source": source_candidate.metadata.get("caption_source"),
                "primary_representation": "json",
                "extractor_used": "pymupdf4llm",
                "fallback_used": True,
                "orientation_strategy": "rotated_text_block_from_mixed_table_box",
                "rotated_block_candidate": True,
                "source_mixed_table_bbox": source_bbox,
                "row_count": source_table.get("row_count"),
                "col_count": source_table.get("col_count"),
                "explicit_grid_refined_from_words": True,
                "grid_refinement_source": refinement["grid_refinement_source"],
                "geometry_coordinate_frame": refinement["geometry_coordinate_frame"],
                "geometry_transform_source_bbox": refinement.get("geometry_transform_source_bbox"),
                "geometry_transform_transposed": refinement.get("geometry_transform_transposed"),
                "geometry_transform_applied": refinement.get("geometry_transform_applied"),
                "table_markdown": source_table.get("markdown"),
                "table_cells": refinement["table_cells"],
                "first_column_text_x0_by_row": {},
                "refined_table_cells": refinement["refined_table_cells"],
                "original_table_cells": source_table.get("cells"),
                "original_backend_rows": source_table.get("extract"),
                "row_bounds": refinement["row_bounds"],
                "horizontal_rules": refinement["horizontal_rules"],
                "full_width_horizontal_rules": refinement["full_width_horizontal_rules"],
                "page_furniture_overlap": {
                    "source_artifact": "paper_page_furniture.json",
                    "has_overlap": bool(table_bbox_cluster_ids),
                    "table_bbox_cluster_ids": table_bbox_cluster_ids,
                },
                **rotated_orientation,
            },
        )
    )


def _find_rotated_text_block_in_bbox(
    page: Any,
    bbox: tuple[float, float, float, float],
) -> dict[str, Any] | None:
    """Find a contiguous rotated text block inside a larger mixed-orientation bbox."""
    try:
        raw_blocks = (page.get_text("dict") or {}).get("blocks", [])
    except Exception:
        return None

    candidates_by_direction: dict[str, list[tuple[tuple[float, float, float, float], int, int]]] = {
        "vertical_text_up": [],
        "vertical_text_down": [],
    }
    for block in raw_blocks:
        if not isinstance(block, dict) or block.get("type", 0) != 0:
            continue
        block_bbox = _as_bbox(block.get("bbox"))
        if block_bbox is None:
            continue
        if (
            min(block_bbox[2], bbox[2]) <= max(block_bbox[0], bbox[0])
            or min(block_bbox[3], bbox[3]) <= max(block_bbox[1], bbox[1])
        ):
            continue
        horizontal_count = 0
        vertical_up_count = 0
        vertical_down_count = 0
        for line in block.get("lines", []):
            if not isinstance(line, dict):
                continue
            direction = line.get("dir")
            if not isinstance(direction, (list, tuple)) or len(direction) != 2:
                continue
            dx = float(direction[0])
            dy = float(direction[1])
            if abs(dx) >= 0.8 and abs(dy) <= 0.2:
                horizontal_count += 1
                continue
            if abs(dy) >= 0.8 and abs(dx) <= 0.35:
                if dy < 0:
                    vertical_up_count += 1
                else:
                    vertical_down_count += 1
        vertical_count = vertical_up_count + vertical_down_count
        directed_count = horizontal_count + vertical_count
        if directed_count == 0 or vertical_count / directed_count < 0.75:
            continue
        if vertical_up_count >= vertical_down_count:
            rotation_direction = "vertical_text_up"
            matching_count = vertical_up_count
        else:
            rotation_direction = "vertical_text_down"
            matching_count = vertical_down_count
        if matching_count < 2 or matching_count / directed_count < 0.75:
            continue
        candidates_by_direction[rotation_direction].append((block_bbox, matching_count, directed_count))

    ranked_directions = sorted(
        candidates_by_direction.items(),
        key=lambda item: sum(candidate[1] for candidate in item[1]),
        reverse=True,
    )
    if not ranked_directions or not ranked_directions[0][1]:
        return None
    rotation_direction, block_candidates = ranked_directions[0]
    matching_line_count = sum(candidate[1] for candidate in block_candidates)
    directed_line_count = sum(candidate[2] for candidate in block_candidates)
    if matching_line_count < 4 or directed_line_count == 0:
        return None
    block_bboxes = [candidate[0] for candidate in block_candidates]
    rotated_text_block_bbox = (
        min(block_bbox[0] for block_bbox in block_bboxes) - 2.0,
        min(block_bbox[1] for block_bbox in block_bboxes) - 2.0,
        max(block_bbox[2] for block_bbox in block_bboxes) + 2.0,
        max(block_bbox[3] for block_bbox in block_bboxes) + 2.0,
    )
    return {
        "table_orientation": "rotated",
        "rotation_source": "pymupdf_mixed_bbox_rotated_text_block",
        "rotation_direction": rotation_direction,
        "rotation_confidence": round(matching_line_count / directed_line_count, 4),
        "rotated_text_block_bbox": rotated_text_block_bbox,
        "rotated_text_region_source": "pymupdf_directional_text_blocks_in_mixed_table_box",
        "rotated_text_block_line_count": matching_line_count,
    }


def _infer_table_orientation_metadata(
    page: Any,
    bbox: tuple[float, float, float, float] | None,
) -> dict[str, Any]:
    """Infer table text orientation from PyMuPDF line-direction metadata."""
    directions = extract_clipped_line_directions(page, bbox)
    if not directions:
        return {
            "table_orientation": "unknown",
            "rotation_source": None,
            "rotation_direction": None,
            "rotation_confidence": 0.0,
        }

    horizontal_count = 0
    vertical_up_count = 0
    vertical_down_count = 0
    for dx, dy in directions:
        if abs(dx) >= 0.8 and abs(dy) <= 0.2:
            horizontal_count += 1
            continue
        if abs(dy) >= 0.8 and abs(dx) <= 0.2:
            if dy < 0:
                vertical_up_count += 1
            else:
                vertical_down_count += 1

    vertical_count = vertical_up_count + vertical_down_count
    considered_count = horizontal_count + vertical_count
    if considered_count == 0:
        return {
            "table_orientation": "unknown",
            "rotation_source": "pymupdf_line_direction",
            "rotation_direction": None,
            "rotation_confidence": 0.0,
        }
    if vertical_count > horizontal_count:
        rotation_direction = (
            "vertical_text_up"
            if vertical_up_count >= vertical_down_count
            else "vertical_text_down"
        )
        rotated_text_block_bboxes: list[tuple[float, float, float, float]] = []
        try:
            raw_blocks = (page.get_text("dict") or {}).get("blocks", [])
        except Exception:
            raw_blocks = []
        for block in raw_blocks:
            if not isinstance(block, dict):
                continue
            block_bbox = _as_bbox(block.get("bbox"))
            if block_bbox is None:
                continue
            if (
                min(block_bbox[2], bbox[2]) <= max(block_bbox[0], bbox[0])
                or min(block_bbox[3], bbox[3]) <= max(block_bbox[1], bbox[1])
            ):
                continue
            matching_line_count = 0
            directed_line_count = 0
            for line in block.get("lines", []):
                if not isinstance(line, dict):
                    continue
                direction = line.get("dir")
                if not isinstance(direction, (list, tuple)) or len(direction) != 2:
                    continue
                dx = float(direction[0])
                dy = float(direction[1])
                directed_line_count += 1
                if (
                    abs(dy) >= 0.8
                    and abs(dx) <= 0.35
                    and (
                        (rotation_direction == "vertical_text_up" and dy < 0)
                        or (rotation_direction == "vertical_text_down" and dy > 0)
                    )
                ):
                    matching_line_count += 1
            if (
                directed_line_count > 0
                and matching_line_count / directed_line_count >= 0.75
            ):
                rotated_text_block_bboxes.append(block_bbox)
        rotated_text_block_bbox = (
            (
                min(block_bbox[0] for block_bbox in rotated_text_block_bboxes) - 2.0,
                min(block_bbox[1] for block_bbox in rotated_text_block_bboxes) - 2.0,
                max(block_bbox[2] for block_bbox in rotated_text_block_bboxes) + 2.0,
                max(block_bbox[3] for block_bbox in rotated_text_block_bboxes) + 2.0,
            )
            if rotated_text_block_bboxes
            else None
        )
        return {
            "table_orientation": "rotated",
            "rotation_source": "pymupdf_line_direction",
            "rotation_direction": rotation_direction,
            "rotation_confidence": round(vertical_count / considered_count, 4),
            "rotated_text_block_bbox": rotated_text_block_bbox,
            "rotated_text_region_source": (
                "pymupdf_directional_text_blocks"
                if rotated_text_block_bbox is not None
                else None
            ),
        }
    return {
        "table_orientation": "upright",
        "rotation_source": "pymupdf_line_direction",
        "rotation_direction": "upright",
        "rotation_confidence": round(horizontal_count / considered_count, 4),
    }


def _infer_first_column_text_x0_by_row(
    *,
    raw_rows: list[list[str]],
    cell_bboxes: list[list[tuple[float, float, float, float] | None]],
    page_words: list[dict[str, object]],
) -> dict[int, float]:
    """Infer first visible text x-position inside first-column cells."""
    if not raw_rows or not cell_bboxes or not page_words:
        return {}
    x0_by_row: dict[int, float] = {}
    for row_idx, row in enumerate(raw_rows):
        if not row or not str(row[0]).strip() or row_idx >= len(cell_bboxes) or not cell_bboxes[row_idx]:
            continue
        cell_bbox = cell_bboxes[row_idx][0]
        if cell_bbox is None:
            continue
        left, top, right, bottom = cell_bbox
        matching_word_x0s: list[float] = []
        for word in page_words:
            text = str(word.get("text", "")).strip()
            if not text:
                continue
            word_x0 = float(word.get("x0", 0.0))
            word_x1 = float(word.get("x1", word_x0))
            word_top = float(word.get("top", 0.0))
            word_bottom = float(word.get("bottom", word_top))
            word_y_mid = (word_top + word_bottom) / 2.0
            horizontal_overlap = min(right, word_x1) - max(left, word_x0)
            if horizontal_overlap <= 0:
                continue
            if top - 1.0 <= word_y_mid <= bottom + 1.0:
                matching_word_x0s.append(word_x0)
        if matching_word_x0s:
            x0_by_row[row_idx] = round(min(matching_word_x0s), 4)
    return x0_by_row


def _looks_like_value_matrix_word(text: str) -> bool:
    """Return whether a positioned word is numeric enough to define a value column."""
    compact = re.sub(r"[\s,\u00a0\u2009\u202f]+", "", clean_text(text))
    if not compact or not re.search(r"\d", compact):
        return False
    if re.search(r"[A-Za-z]", compact):
        return False
    return bool(re.fullmatch(r"(?:[<>]=?)?[\d./%()\-+±*†‡§¶#]+", compact))


def _value_matrix_column_boundaries_from_lines(
    lines: list[dict[str, object]],
    horizontal_rules: list[float],
) -> tuple[list[float], list[float]] | None:
    """Infer label/value column boundaries from repeated numeric line anchors."""
    if not lines:
        return None

    first_table_rule = min(horizontal_rules or [float("-inf")])
    candidate_items: list[tuple[float, int]] = []
    first_value_boundaries: list[float] = []
    left_text_candidate_line_count = 0
    candidate_line_indices: set[int] = set()
    for line_index, line in enumerate(lines):
        line_words = [
            word
            for word in line["words"]
            if str(word.get("text", "")).strip()
        ]
        if not line_words or float(line["top"]) < first_table_rule - 2.0:
            continue
        numeric_words, first_value_boundary = _value_matrix_words_after_label_region(line_words)
        if len(numeric_words) < 3 or len(numeric_words) * 2 < len(line_words):
            continue
        candidate_line_indices.add(line_index)
        if first_value_boundary is not None:
            first_value_boundaries.append(first_value_boundary)
            if any(
                float(word.get("x1", word.get("x0", 0.0))) <= first_value_boundary + 1.0
                and re.search(r"[A-Za-z]", str(word.get("text", "")))
                for word in line_words
            ):
                left_text_candidate_line_count += 1
        candidate_items.extend((float(word["x0"]), line_index) for word in numeric_words)

    if len(candidate_line_indices) < 3 or not candidate_items:
        return None

    clusters: list[list[tuple[float, int]]] = []
    for item in sorted(candidate_items):
        if not clusters or abs(item[0] - clusters[-1][-1][0]) > 18.0:
            clusters.append([item])
            continue
        clusters[-1].append(item)

    minimum_line_support = (
        2
        if len(candidate_line_indices) <= 5
        else max(3, min(5, len(candidate_line_indices) // 4))
    )
    value_anchors = [
        sum(position for position, _line_index in cluster) / len(cluster)
        for cluster in clusters
        if len({_line_index for _position, _line_index in cluster}) >= minimum_line_support
    ]
    if len(value_anchors) < 4 or len(value_anchors) > 24:
        return None

    right_trailing_text_lines = 0
    rightmost_anchor = value_anchors[-1]
    for line_index in candidate_line_indices:
        line = lines[line_index]
        if any(
            float(word["x0"]) > rightmost_anchor + 18.0
            and re.search(r"[A-Za-z]", str(word.get("text", "")))
            for word in line["words"]
        ):
            right_trailing_text_lines += 1
    if right_trailing_text_lines >= max(2, len(candidate_line_indices) // 3):
        return None

    header_first_boundary: float | None = None
    if (
        len(value_anchors) >= 2
        and left_text_candidate_line_count >= max(2, len(candidate_line_indices) // 3)
    ):
        first_body_top = min(float(lines[line_index]["top"]) for line_index in candidate_line_indices)
        first_anchor = value_anchors[0]
        second_anchor = value_anchors[1]
        first_header_tolerance = max(18.0, min(34.0, (second_anchor - first_anchor) * 0.45))
        header_boundary_candidates: list[tuple[float, float]] = []
        for line_index, line in enumerate(lines):
            if line_index in candidate_line_indices:
                continue
            if float(line["top"]) < first_table_rule - 2.0:
                continue
            if float(line["bottom"]) > first_body_top - 0.5:
                continue
            header_words = sorted(
                [
                    word
                    for word in line["words"]
                    if str(word.get("text", "")).strip()
                ],
                key=lambda word: float(word["x0"]),
            )
            if len(header_words) < 2:
                continue
            for word_index, word in enumerate(header_words):
                word_x0 = float(word["x0"])
                if abs(word_x0 - first_anchor) > first_header_tolerance:
                    continue
                prior_words = [
                    prior_word
                    for prior_word in header_words[:word_index]
                    if float(prior_word.get("x1", prior_word.get("x0", 0.0))) <= word_x0 - 2.0
                ]
                if not prior_words:
                    continue
                prior_text = " ".join(str(prior_word.get("text", "")) for prior_word in prior_words)
                if re.search(r"[A-Za-z]", prior_text) is None:
                    continue
                prior_x1 = float(prior_words[-1].get("x1", prior_words[-1].get("x0", 0.0)))
                if word_x0 - prior_x1 < 8.0:
                    continue
                boundary = (prior_x1 + word_x0) / 2.0
                if first_anchor - boundary <= 4.0:
                    continue
                header_boundary_candidates.append((float(line["top"]), boundary))
                break
        if header_boundary_candidates:
            leaf_header_top = max(line_top for line_top, _boundary in header_boundary_candidates)
            leaf_header_boundaries = sorted(
                boundary
                for line_top, boundary in header_boundary_candidates
                if line_top >= leaf_header_top - 3.0
            )
            header_first_boundary = leaf_header_boundaries[len(leaf_header_boundaries) // 2]

    if header_first_boundary is not None:
        first_boundary = header_first_boundary
    elif first_value_boundaries:
        sorted_first_value_boundaries = sorted(first_value_boundaries)
        first_boundary = sorted_first_value_boundaries[len(sorted_first_value_boundaries) // 2]
    else:
        leftmost_text_x0 = min(float(word["x0"]) for line in lines for word in line["words"])
        first_boundary = (leftmost_text_x0 + value_anchors[0]) / 2.0
    if value_anchors[0] - first_boundary <= 4.0:
        return None
    boundaries = [
        first_boundary,
        *[
            (value_anchors[index] + value_anchors[index + 1]) / 2.0
            for index in range(len(value_anchors) - 1)
        ],
    ]
    return boundaries, value_anchors


def _value_matrix_words_after_label_region(
    line_words: list[dict[str, object]],
) -> tuple[list[dict[str, object]], float | None]:
    """Return numeric words after the line's left text-label region."""
    sorted_words = sorted(line_words, key=lambda word: float(word["x0"]))
    numeric_indices = [
        index
        for index, word in enumerate(sorted_words)
        if _looks_like_value_matrix_word(str(word.get("text", "")))
    ]
    if len(numeric_indices) < 3:
        return [], None
    best_start_index = numeric_indices[0]
    best_gap = float("-inf")
    for numeric_index in numeric_indices:
        trailing_numeric_count = sum(index >= numeric_index for index in numeric_indices)
        if trailing_numeric_count < 3:
            continue
        previous_x1 = (
            float(sorted_words[numeric_index - 1]["x1"])
            if numeric_index > 0
            else float(sorted_words[numeric_index]["x0"])
        )
        gap = float(sorted_words[numeric_index]["x0"]) - previous_x1
        if gap > best_gap:
            best_gap = gap
            best_start_index = numeric_index
    first_value_boundary = None
    if best_start_index > 0:
        first_value_boundary = (
            float(sorted_words[best_start_index - 1]["x1"])
            + float(sorted_words[best_start_index]["x0"])
        ) / 2.0
    return (
        [
            word
            for index, word in enumerate(sorted_words)
            if index >= best_start_index
            and _looks_like_value_matrix_word(str(word.get("text", "")))
        ],
        first_value_boundary,
    )


def _refine_grid_from_value_matrix_word_positions(
    *,
    raw_rows: list[list[str]],
    clipped_words: list[dict[str, object]],
    clipped_chars: list[dict[str, object]],
    horizontal_rules: list[float],
    full_width_rules: list[float],
) -> dict[str, object] | None:
    """Rebuild a grid from repeated numeric value-column anchors."""
    if len(raw_rows) < 4 or max((len(row) for row in raw_rows), default=0) < 4:
        return None
    if not clipped_words:
        return None

    lines = build_word_lines(clipped_words)
    if len(lines) < max(4, len(raw_rows) - 2):
        return None

    value_matrix_geometry = _value_matrix_column_boundaries_from_lines(
        lines,
        full_width_rules or horizontal_rules,
    )
    if value_matrix_geometry is None:
        return None
    boundaries, value_anchors = value_matrix_geometry
    refined_rows, refined_cell_bboxes = build_row_grid_from_lines(
        lines,
        page_chars=clipped_chars,
        column_start_boundaries=boundaries,
    )
    if not refined_rows:
        return None
    refined_col_count = max((len(row) for row in refined_rows), default=0)
    expected_col_count = len(value_anchors) + 1
    if refined_col_count != expected_col_count:
        return None
    if len(refined_rows) < len(raw_rows) - 2 or len(refined_rows) > len(raw_rows) + 4:
        return None

    refined_value_rows = 0
    for row in refined_rows:
        numeric_values = sum(_looks_like_value_matrix_word(cell) for cell in row[1:] if cell.strip())
        if numeric_values >= max(3, len(value_anchors) // 2):
            refined_value_rows += 1
    if refined_value_rows < 3:
        return None

    return {
        "raw_rows": refined_rows,
        "table_cells": refined_cell_bboxes,
        "refined_table_cells": refined_cell_bboxes,
        "row_bounds": [
            (float(line["top"]), float(line["bottom"]))
            for line in lines
        ],
        "horizontal_rules": horizontal_rules,
        "full_width_horizontal_rules": full_width_rules,
        "grid_refinement_source": "value_matrix_word_positions",
        "geometry_coordinate_frame": "page",
        "geometry_transform_source_bbox": None,
        "geometry_transform_transposed": False,
        "geometry_transform_applied": False,
        "value_matrix_column_anchors": [round(anchor, 4) for anchor in value_anchors],
    }


def _refine_grid_from_hline_word_positions(
    *,
    raw_rows: list[list[str]],
    clipped_words: list[dict[str, object]],
    clipped_chars: list[dict[str, object]],
    horizontal_rules: list[float],
    full_width_rules: list[float],
) -> dict[str, object] | None:
    """Rebuild a ruled table grid from positioned words, using hlines as primary structure."""
    rules = sorted({float(rule) for rule in full_width_rules})
    if len(rules) < 3 or not clipped_words:
        return None

    lines = [
        line
        for line in build_word_lines(clipped_words)
        if float(line["bottom"]) >= rules[0] - 2.0 and float(line["top"]) <= rules[-1] + 2.0
    ]
    if len(lines) <= len(raw_rows):
        return None

    separator_rule: float | None = None
    for rule in rules[1:-1]:
        header_count = sum(float(line["bottom"]) <= rule + 2.0 for line in lines)
        body_count = sum(float(line["top"]) >= rule - 2.0 for line in lines)
        if header_count >= 1 and body_count >= 1:
            separator_rule = rule
            break
    if separator_rule is None:
        return None

    header_lines = [line for line in lines if float(line["bottom"]) <= separator_rule + 2.0]
    body_lines = [line for line in lines if float(line["top"]) >= separator_rule - 2.0]
    if not header_lines or not body_lines:
        return None

    first_value_boundaries: list[float] = []
    value_anchor_items: list[tuple[float, int]] = []
    for body_line_index, line in enumerate(body_lines):
        words = [
            word
            for word in sorted(line["words"], key=lambda item: float(item["x0"]))
            if str(word.get("text", "")).strip()
        ]
        if len(words) < 2:
            continue
        value_like_indices = [
            index
            for index, word in enumerate(words)
            if _looks_like_hline_table_value_word(str(word.get("text", "")))
        ]
        if len(value_like_indices) < 2:
            continue
        best_start_index: int | None = None
        best_gap = float("-inf")
        for value_index in value_like_indices:
            if value_index == 0:
                continue
            trailing_value_count = sum(index >= value_index for index in value_like_indices)
            if trailing_value_count < 2:
                continue
            gap = float(words[value_index]["x0"]) - float(words[value_index - 1]["x1"])
            if gap > best_gap:
                best_gap = gap
                best_start_index = value_index
        if best_start_index is None:
            continue
        first_value_boundaries.append(
            (float(words[best_start_index - 1]["x1"]) + float(words[best_start_index]["x0"])) / 2.0
        )
        for word in words[best_start_index:]:
            if _looks_like_hline_table_value_word(str(word.get("text", ""))):
                value_anchor_items.append((float(word["x0"]), body_line_index))

    if not first_value_boundaries or not value_anchor_items:
        return None

    anchor_clusters: list[list[tuple[float, int]]] = []
    for item in sorted(value_anchor_items):
        if not anchor_clusters or abs(item[0] - anchor_clusters[-1][-1][0]) > 24.0:
            anchor_clusters.append([item])
            continue
        anchor_clusters[-1].append(item)
    minimum_line_support = 2 if len(body_lines) >= 2 else 1
    value_anchors = [
        sum(position for position, _line_index in cluster) / len(cluster)
        for cluster in anchor_clusters
        if len({_line_index for _position, _line_index in cluster}) >= minimum_line_support
    ]
    if len(value_anchors) < 2:
        return None

    first_boundary = sorted(first_value_boundaries)[len(first_value_boundaries) // 2]
    if value_anchors[0] - first_boundary <= 4.0:
        return None
    boundaries = [
        first_boundary,
        *[
            (value_anchors[index] + value_anchors[index + 1]) / 2.0
            for index in range(len(value_anchors) - 1)
        ],
    ]
    refined_rows, refined_cell_bboxes = build_row_grid_from_lines(
        lines,
        page_chars=clipped_chars,
        column_start_boundaries=boundaries,
    )
    if not refined_rows:
        return None
    refined_col_count = max((len(row) for row in refined_rows), default=0)
    if refined_col_count < 3:
        return None

    leaf_header_row_idx = max(0, len(header_lines) - 1)
    for row_idx in range(leaf_header_row_idx):
        row = refined_rows[row_idx]
        bbox_row = refined_cell_bboxes[row_idx]
        run_start: int | None = None
        for col_idx in range(1, refined_col_count + 1):
            is_populated = col_idx < refined_col_count and bool(row[col_idx].strip())
            if is_populated and run_start is None:
                run_start = col_idx
            if (not is_populated or col_idx == refined_col_count) and run_start is not None:
                run_end = col_idx - 1
                if run_end > run_start:
                    merged_text = clean_text(" ".join(row[index] for index in range(run_start, run_end + 1)))
                    merged_bbox = _merge_bboxes(bbox_row[run_start : run_end + 1])
                    row[run_start] = merged_text
                    bbox_row[run_start] = merged_bbox
                    for blank_idx in range(run_start + 1, run_end + 1):
                        row[blank_idx] = ""
                        bbox_row[blank_idx] = None
                run_start = None

    value_row_count = sum(
        sum(
            _looks_like_hline_table_value_word(cell)
            for cell in row[1:]
            if cell.strip()
        )
        >= 1
        for row in refined_rows[leaf_header_row_idx + 1 :]
    )
    if value_row_count < max(2, min(3, len(body_lines))):
        return None

    return {
        "raw_rows": refined_rows,
        "table_cells": refined_cell_bboxes,
        "refined_table_cells": refined_cell_bboxes,
        "row_bounds": [
            (float(line["top"]), float(line["bottom"]))
            for line in lines
        ],
        "horizontal_rules": horizontal_rules,
        "full_width_horizontal_rules": full_width_rules,
        "grid_refinement_source": "hline_word_positions",
        "geometry_coordinate_frame": "page",
        "geometry_transform_source_bbox": None,
        "geometry_transform_transposed": False,
        "geometry_transform_applied": False,
        "value_matrix_column_anchors": [round(anchor, 4) for anchor in value_anchors],
    }


def _looks_like_hline_table_value_word(text: str) -> bool:
    cleaned = clean_text(text)
    if not cleaned:
        return False
    if cleaned in {"-", "–", "—"}:
        return True
    return _looks_like_value_matrix_word(cleaned)


def _merge_bboxes(
    bboxes: list[tuple[float, float, float, float] | None],
) -> tuple[float, float, float, float] | None:
    populated = [bbox for bbox in bboxes if bbox is not None]
    if not populated:
        return None
    return (
        min(bbox[0] for bbox in populated),
        min(bbox[1] for bbox in populated),
        max(bbox[2] for bbox in populated),
        max(bbox[3] for bbox in populated),
    )


def _refine_explicit_table_candidate_grid(
    *,
    raw_rows: list[list[str]],
    cell_bboxes: list[list[tuple[float, float, float, float] | None]],
    bbox: tuple[float, float, float, float] | None,
    page_words: list[dict[str, object]],
    page_chars: list[dict[str, object]],
    page_rule_segments: list[tuple[float, float, float, float]],
    full_width_rule_segments: list[tuple[float, float, float, float]] | None = None,
    orientation_metadata: dict[str, Any],
    caption_bbox: tuple[float, float, float, float] | None = None,
) -> dict[str, object]:
    """Refine coarse explicit-table grids using positioned words and structural rules."""
    table_cells = cell_bboxes
    refined_table_cells: list[list[tuple[float, float, float, float] | None]] | None = None
    grid_refinement_source: str | None = None
    geometry_coordinate_frame = "page"

    row_bounds: list[tuple[float, float]] = []
    horizontal_rules_raw: list[float] = []
    table_width = max(1.0, bbox[2] - bbox[0]) if bbox is not None else None
    for row in cell_bboxes:
        populated = [cell_bbox for cell_bbox in row if cell_bbox is not None]
        if not populated:
            continue
        row_top = min(cell_bbox[1] for cell_bbox in populated)
        row_bottom = max(cell_bbox[3] for cell_bbox in populated)
        row_bounds.append((row_top, row_bottom))
        row_left = min(cell_bbox[0] for cell_bbox in populated)
        row_right = max(cell_bbox[2] for cell_bbox in populated)
        if table_width is None:
            coverage_ok = len(populated) >= max(2, len(row) // 2)
        else:
            coverage_ok = ((row_right - row_left) / table_width) >= 0.8
        if coverage_ok:
            horizontal_rules_raw.extend([row_top, row_bottom])
    horizontal_rules: list[float] = []
    for value in sorted(horizontal_rules_raw):
        if not horizontal_rules or abs(value - horizontal_rules[-1]) > 1.5:
            horizontal_rules.append(value)

    separator_rule_segments = full_width_rule_segments if full_width_rule_segments is not None else page_rule_segments
    full_width_rules = detect_horizontal_rules(separator_rule_segments, bbox) if bbox is not None else []
    if full_width_rules:
        for value in sorted(horizontal_rules + full_width_rules):
            if not horizontal_rules or abs(value - horizontal_rules[-1]) > 1.5:
                horizontal_rules.append(value)

    if bbox is None or not page_words:
        return {
            "raw_rows": raw_rows,
            "table_cells": table_cells,
            "refined_table_cells": refined_table_cells,
            "row_bounds": row_bounds,
            "horizontal_rules": horizontal_rules,
            "full_width_horizontal_rules": full_width_rules,
            "grid_refinement_source": grid_refinement_source,
            "geometry_coordinate_frame": geometry_coordinate_frame,
            "geometry_transform_source_bbox": None,
            "geometry_transform_transposed": False,
            "geometry_transform_applied": False,
        }

    word_clip_bbox = bbox
    if full_width_rules:
        sorted_full_width_rules = sorted(float(rule) for rule in full_width_rules)
        top_rule = sorted_full_width_rules[0]
        bottom_rule = sorted_full_width_rules[-1]
        clip_top = bbox[1]
        clip_bottom = bbox[3]
        if top_rule < bbox[1] and bbox[1] - top_rule <= 20.0:
            clip_top = top_rule
        if bottom_rule > bbox[3] and bottom_rule - bbox[3] <= 20.0:
            clip_bottom = bottom_rule
        word_clip_bbox = (bbox[0], clip_top, bbox[2], clip_bottom)

    clipped_words = [
        word
        for word in page_words
        if float(word["x0"]) >= word_clip_bbox[0] - 2.0
        and float(word["x1"]) <= word_clip_bbox[2] + 2.0
        and float(word["top"]) >= word_clip_bbox[1] - 2.0
        and float(word["bottom"]) <= word_clip_bbox[3] + 2.0
    ]
    if not clipped_words:
        return {
            "raw_rows": raw_rows,
            "table_cells": table_cells,
            "refined_table_cells": refined_table_cells,
            "row_bounds": row_bounds,
            "horizontal_rules": horizontal_rules,
            "full_width_horizontal_rules": full_width_rules,
            "grid_refinement_source": grid_refinement_source,
            "geometry_coordinate_frame": geometry_coordinate_frame,
            "geometry_transform_source_bbox": None,
            "geometry_transform_transposed": False,
            "geometry_transform_applied": False,
        }

    clipped_chars = [
        char
        for char in page_chars
        if float(char["x0"]) >= word_clip_bbox[0] - 2.0
        and float(char["x1"]) <= word_clip_bbox[2] + 2.0
        and float(char["top"]) >= word_clip_bbox[1] - 2.0
        and float(char["bottom"]) <= word_clip_bbox[3] + 2.0
    ]

    hline_refinement = _refine_grid_from_hline_word_positions(
        raw_rows=raw_rows,
        clipped_words=clipped_words,
        clipped_chars=clipped_chars,
        horizontal_rules=horizontal_rules,
        full_width_rules=full_width_rules,
    )
    if hline_refinement is not None:
        return hline_refinement

    rotation_direction = str(orientation_metadata.get("rotation_direction") or "")
    rotation_confidence = float(orientation_metadata.get("rotation_confidence") or 0.0)
    has_vertical_rotation_signal = (
        orientation_metadata.get("table_orientation") == "rotated"
        and rotation_direction in {"vertical_text_up", "vertical_text_down"}
    )
    is_rotated = has_vertical_rotation_signal and rotation_confidence >= 0.8
    max_raw_cols = max((len(row) for row in raw_rows), default=0)
    stacked_or_blob_cell_count = sum(
        1
        for row in raw_rows
        for cell in row
        if isinstance(cell, str) and (cell.count("\n") >= 2 or len(cell.split()) >= 12)
    )
    first_row_internally_stacked = False
    if raw_rows and len(row_bounds) == len(raw_rows) and max_raw_cols >= 4:
        first_row = raw_rows[0]
        first_row_stacked_cells = sum(
            isinstance(cell, str) and cell.count("\n") >= 2
            for cell in first_row
        )
        first_row_lines = [
            str(cell).splitlines()[0].strip()
            for cell in first_row
            if isinstance(cell, str) and str(cell).splitlines()
        ]
        first_line_alpha_cells = sum(
            bool(re.search(r"[A-Za-z]", cell)) for cell in first_row_lines if cell
        )
        row_heights = [
            bottom - top
            for top, bottom in row_bounds[1:]
            if bottom > top
        ]
        median_following_height = (
            sorted(row_heights)[len(row_heights) // 2]
            if row_heights
            else 0.0
        )
        first_row_height = row_bounds[0][1] - row_bounds[0][0]
        first_row_has_internal_rule = any(
            row_bounds[0][0] + 3.0 < float(rule) < row_bounds[0][1] - 3.0
            for rule in full_width_rules
        )
        first_row_internally_stacked = (
            not has_vertical_rotation_signal
            and len(raw_rows) >= 4
            and len(clipped_words) >= 12
            and first_row_stacked_cells >= max(3, max_raw_cols // 2)
            and first_line_alpha_cells >= max(3, max_raw_cols // 2)
            and first_row_height >= max(30.0, median_following_height * 3.0)
            and first_row_has_internal_rule
        )
    rotated_few_column_stacked_grid = (
        has_vertical_rotation_signal
        and rotation_confidence >= 0.5
        and len(raw_rows) >= 4
        and max_raw_cols <= 4
        and len(clipped_words) >= 12
        and stacked_or_blob_cell_count >= 2
    )
    collapsed_explicit_grid = (
        len(raw_rows) <= 1
        or (
            len(raw_rows) <= 3
            and max_raw_cols <= 4
            and len(clipped_words) >= 12
        )
        or rotated_few_column_stacked_grid
        or first_row_internally_stacked
    )

    if collapsed_explicit_grid:
        should_rotate_refinement = is_rotated or rotated_few_column_stacked_grid
        refinement_attempts: list[dict[str, object]] = []

        if should_rotate_refinement:
            rotated_refinement_bbox = bbox
            rotated_text_block_bbox = _as_bbox(
                orientation_metadata.get("rotated_text_block_bbox")
            )
            overlapping_rule_boxes: list[tuple[float, float, float, float]] = []
            for segment in page_rule_segments:
                segment_left = min(float(segment[0]), float(segment[2]))
                segment_right = max(float(segment[0]), float(segment[2]))
                segment_top = min(float(segment[1]), float(segment[3]))
                segment_bottom = max(float(segment[1]), float(segment[3]))
                if segment_right < bbox[0] - 12.0 or segment_left > bbox[2] + 12.0:
                    continue
                if segment_bottom < bbox[1] - 2.0:
                    continue
                overlapping_rule_boxes.append(
                    (segment_left, segment_top, segment_right, segment_bottom)
                )
            if overlapping_rule_boxes:
                rule_left = min(rule_box[0] for rule_box in overlapping_rule_boxes)
                rule_right = max(rule_box[2] for rule_box in overlapping_rule_boxes)
                rule_bottom = max(rule_box[3] for rule_box in overlapping_rule_boxes)
                if rule_bottom > bbox[3] + 20.0 or rule_left < bbox[0] - 2.0:
                    rotated_refinement_bbox = (
                        min(float(bbox[0]), rule_left),
                        float(bbox[1]),
                        max(float(bbox[2]), rule_right),
                        max(float(bbox[3]), rule_bottom),
                    )
            if caption_bbox is not None:
                caption_left_hint = min(float(caption_bbox[0]), float(caption_bbox[1]))
                if 0.0 < rotated_refinement_bbox[0] - caption_left_hint <= 24.0:
                    rotated_refinement_bbox = (
                        caption_left_hint - 2.0,
                        rotated_refinement_bbox[1],
                        rotated_refinement_bbox[2],
                        rotated_refinement_bbox[3],
                    )
            if rotated_text_block_bbox is not None:
                rotated_refinement_bbox = rotated_text_block_bbox
            rotated_words = [
                word
                for word in page_words
                if float(word["x0"]) >= rotated_refinement_bbox[0] - 2.0
                and float(word["x1"]) <= rotated_refinement_bbox[2] + 2.0
                and float(word["top"]) >= rotated_refinement_bbox[1] - 2.0
                and float(word["bottom"]) <= rotated_refinement_bbox[3] + 2.0
            ]
            rotated_chars = [
                char
                for char in page_chars
                if float(char["x0"]) >= rotated_refinement_bbox[0] - 2.0
                and float(char["x1"]) <= rotated_refinement_bbox[2] + 2.0
                and float(char["top"]) >= rotated_refinement_bbox[1] - 2.0
                and float(char["bottom"]) <= rotated_refinement_bbox[3] + 2.0
            ]
            clipped_rule_segments = [
                segment
                for segment in page_rule_segments
                if max(float(segment[0]), float(segment[2])) >= rotated_refinement_bbox[0] - 2.0
                and min(float(segment[0]), float(segment[2])) <= rotated_refinement_bbox[2] + 2.0
                and max(float(segment[1]), float(segment[3])) >= rotated_refinement_bbox[1] - 2.0
                and min(float(segment[1]), float(segment[3])) <= rotated_refinement_bbox[3] + 2.0
            ]
            (
                working_words,
                working_chars,
                transformed_rule_segments,
                transformed_bbox,
            ) = normalize_positioned_geometry_for_rotation(
                words=rotated_words or clipped_words,
                chars=rotated_chars or clipped_chars,
                rule_segments=clipped_rule_segments,
                bbox=rotated_refinement_bbox,
                rotation_direction=rotation_direction,
            )
            refinement_attempts.append(
                {
                    "words": working_words,
                    "chars": working_chars,
                    "horizontal_rules": detect_horizontal_rules(
                        transformed_rule_segments,
                        transformed_bbox,
                    ),
                    "full_width_horizontal_rules": detect_horizontal_rules(
                        transformed_rule_segments,
                        transformed_bbox,
                    ),
                    "refinement_source": "rotated_word_positions_with_rules",
                    "coordinate_frame": "table_local_rotated_normalized",
                    "geometry_transform_source_bbox": rotated_refinement_bbox,
                    "geometry_transform_transposed": False,
                    "geometry_transform_applied": True,
                    "minimum_row_gain": 3,
                }
            )

            bbox_width = float(bbox[2]) - float(bbox[0])
            bbox_height = float(bbox[3]) - float(bbox[1])
            if rotated_few_column_stacked_grid and bbox_width >= bbox_height * 3.0:
                compact_padding = max(8.0, min(12.0, bbox_height * 0.12))
                label_padding = max(20.0, min(32.0, bbox_height * 0.28))
                transposed_bbox = (
                    max(0.0, float(bbox[1]) - compact_padding),
                    max(0.0, float(bbox[0]) - compact_padding),
                    float(bbox[3]) + label_padding,
                    float(bbox[2]) + label_padding,
                )
                transposed_words = [
                    word
                    for word in page_words
                    if float(word["x0"]) >= transposed_bbox[0] - 2.0
                    and float(word["x1"]) <= transposed_bbox[2] + 2.0
                    and float(word["top"]) >= transposed_bbox[1] - 2.0
                    and float(word["bottom"]) <= transposed_bbox[3] + 2.0
                ]
                if transposed_words:
                    transposed_chars = [
                        char
                        for char in page_chars
                        if float(char["x0"]) >= transposed_bbox[0] - 2.0
                        and float(char["x1"]) <= transposed_bbox[2] + 2.0
                        and float(char["top"]) >= transposed_bbox[1] - 2.0
                        and float(char["bottom"]) <= transposed_bbox[3] + 2.0
                    ]
                    transposed_rule_segments = [
                        segment
                        for segment in page_rule_segments
                        if max(float(segment[0]), float(segment[2])) >= transposed_bbox[0] - 2.0
                        and min(float(segment[0]), float(segment[2])) <= transposed_bbox[2] + 2.0
                        and max(float(segment[1]), float(segment[3])) >= transposed_bbox[1] - 2.0
                        and min(float(segment[1]), float(segment[3])) <= transposed_bbox[3] + 2.0
                    ]
                    (
                        transposed_working_words,
                        transposed_working_chars,
                        transposed_transformed_rule_segments,
                        transposed_transformed_bbox,
                    ) = normalize_positioned_geometry_for_rotation(
                        words=transposed_words,
                        chars=transposed_chars,
                        rule_segments=transposed_rule_segments,
                        bbox=transposed_bbox,
                        rotation_direction=rotation_direction,
                    )
                    refinement_attempts.append(
                        {
                            "words": transposed_working_words,
                            "chars": transposed_working_chars,
                            "horizontal_rules": detect_horizontal_rules(
                                transposed_transformed_rule_segments,
                                transposed_transformed_bbox,
                            ),
                            "full_width_horizontal_rules": detect_horizontal_rules(
                                transposed_transformed_rule_segments,
                                transposed_transformed_bbox,
                            ),
                            "refinement_source": "rotated_transposed_word_positions_with_rules",
                            "coordinate_frame": "table_local_rotated_transposed_normalized",
                            "geometry_transform_source_bbox": transposed_bbox,
                            "geometry_transform_transposed": True,
                            "geometry_transform_applied": True,
                            "minimum_row_gain": 3,
                        }
                    )
        else:
            refinement_attempts.append(
                {
                    "words": clipped_words,
                    "chars": clipped_chars,
                    "horizontal_rules": horizontal_rules,
                    "full_width_horizontal_rules": full_width_rules,
                    "refinement_source": (
                        "stacked_row_word_positions"
                        if first_row_internally_stacked
                        else "collapsed_explicit_grid_word_positions"
                    ),
                    "coordinate_frame": "page",
                    "geometry_transform_source_bbox": None,
                    "geometry_transform_transposed": False,
                    "geometry_transform_applied": False,
                    "minimum_row_gain": 3 if first_row_internally_stacked else 4,
                    "allow_same_column_count": first_row_internally_stacked,
                    "use_top_header_boundaries": first_row_internally_stacked,
                }
            )

        for refinement_attempt in refinement_attempts:
            working_words = refinement_attempt["words"]
            working_chars = refinement_attempt["chars"]
            working_horizontal_rules = refinement_attempt["horizontal_rules"]
            working_full_width_rules = refinement_attempt.get("full_width_horizontal_rules")
            if not isinstance(working_words, list) or not isinstance(working_chars, list):
                continue
            if not isinstance(working_horizontal_rules, list):
                working_horizontal_rules = []
            if not isinstance(working_full_width_rules, list):
                working_full_width_rules = []
            refined_lines = build_word_lines(working_words)
            column_start_boundaries: list[float] | None = None
            value_matrix_column_anchors: list[float] = []
            value_matrix_geometry = _value_matrix_column_boundaries_from_lines(
                refined_lines,
                working_full_width_rules or working_horizontal_rules,
            )
            if value_matrix_geometry is not None:
                column_start_boundaries, value_matrix_column_anchors = value_matrix_geometry
            if (
                column_start_boundaries is None
                and bool(refinement_attempt.get("use_top_header_boundaries"))
                and refined_lines
            ):
                first_line = refined_lines[0]
                header_starts: list[float] = []
                previous_x1: float | None = None
                for word in sorted(first_line["words"], key=lambda item: float(item["x0"])):
                    text = str(word["text"]).strip()
                    if not text:
                        continue
                    word_x0 = float(word["x0"])
                    word_x1 = float(word["x1"])
                    if previous_x1 is None or word_x0 - previous_x1 > 10.0:
                        header_starts.append(word_x0)
                    previous_x1 = word_x1
                clustered_starts: list[float] = []
                for start in sorted(header_starts):
                    if not clustered_starts or abs(start - clustered_starts[-1]) > 8.0:
                        clustered_starts.append(start)
                    else:
                        clustered_starts[-1] = (clustered_starts[-1] + start) / 2.0
                if len(clustered_starts) >= max(4, max_raw_cols):
                    column_start_boundaries = [
                        (clustered_starts[index] + clustered_starts[index + 1]) / 2.0
                        for index in range(len(clustered_starts) - 1)
                    ]
            if (
                column_start_boundaries is None
                and bool(refinement_attempt["geometry_transform_applied"])
                and len(working_horizontal_rules) >= 3
            ):
                sorted_rules = sorted(float(rule) for rule in working_horizontal_rules)
                internal_rules = [
                    rule
                    for rule in sorted_rules[1:-1]
                    if rule > sorted_rules[0] + 3.0 and rule < sorted_rules[-1] - 3.0
                ]
                if internal_rules:
                    separator_rule = internal_rules[0]
                    header_lines = [
                        line
                        for line in refined_lines
                        if float(line["bottom"]) <= separator_rule + 1.5
                    ]
                    header_starts: list[float] = []
                    for line in header_lines:
                        previous_x1: float | None = None
                        for word in sorted(line["words"], key=lambda item: float(item["x0"])):
                            text = str(word["text"]).strip()
                            if not text:
                                continue
                            word_x0 = float(word["x0"])
                            word_x1 = float(word["x1"])
                            if previous_x1 is None or word_x0 - previous_x1 > 10.0:
                                header_starts.append(word_x0)
                            previous_x1 = word_x1
                    clustered_starts: list[float] = []
                    for start in sorted(header_starts):
                        if not clustered_starts or abs(start - clustered_starts[-1]) > 8.0:
                            clustered_starts.append(start)
                        else:
                            clustered_starts[-1] = (clustered_starts[-1] + start) / 2.0
                    if len(clustered_starts) >= max_raw_cols + 4:
                        column_start_boundaries = clustered_starts[1:]
            refined_rows, refined_cell_bboxes = build_row_grid_from_lines(
                refined_lines,
                page_chars=working_chars,
                column_start_boundaries=column_start_boundaries,
            )
            if refined_rows:
                keep_indices = [
                    col_idx
                    for col_idx in range(len(refined_rows[0]))
                    if any(col_idx < len(row) and row[col_idx].strip() for row in refined_rows)
                ]
                if keep_indices:
                    refined_rows = [
                        [row[col_idx] for col_idx in keep_indices]
                        for row in refined_rows
                    ]
                    refined_cell_bboxes = [
                        [row[col_idx] for col_idx in keep_indices]
                        for row in refined_cell_bboxes
                    ]
                refined_col_count = max((len(row) for row in refined_rows), default=0)
                column_gain_ok = refined_col_count > max_raw_cols
                row_gain_ok = len(refined_rows) >= len(raw_rows) + int(
                    refinement_attempt["minimum_row_gain"]
                )
                stacked_column_gain_ok = (
                    rotated_few_column_stacked_grid
                    and refined_col_count >= max_raw_cols + 4
                    and len(refined_rows) >= max(4, len(raw_rows) - 1)
                )
                wide_rotated_refinement = (
                    bool(refinement_attempt["geometry_transform_applied"])
                    and max_raw_cols <= 4
                    and refined_col_count > 12
                )
                has_rotated_rule_support = (
                    len(working_horizontal_rules) >= 3
                    or column_start_boundaries is not None
                )
                if wide_rotated_refinement and (
                    refined_col_count > 30 or not has_rotated_rule_support
                ):
                    continue
                same_column_stacked_row_ok = (
                    bool(refinement_attempt.get("allow_same_column_count"))
                    and refined_col_count >= max_raw_cols
                    and row_gain_ok
                )
                if (
                    column_gain_ok and (row_gain_ok or stacked_column_gain_ok)
                ) or same_column_stacked_row_ok:
                    return {
                        "raw_rows": refined_rows,
                        "table_cells": refined_cell_bboxes,
                        "refined_table_cells": refined_cell_bboxes,
                        "row_bounds": [
                            (float(line["top"]), float(line["bottom"]))
                            for line in refined_lines
                        ],
                        "horizontal_rules": working_horizontal_rules,
                        "full_width_horizontal_rules": working_full_width_rules,
                        "grid_refinement_source": str(refinement_attempt["refinement_source"]),
                        "geometry_coordinate_frame": str(refinement_attempt["coordinate_frame"]),
                        "geometry_transform_source_bbox": refinement_attempt[
                            "geometry_transform_source_bbox"
                        ],
                        "geometry_transform_transposed": bool(
                            refinement_attempt["geometry_transform_transposed"]
                        ),
                        "geometry_transform_applied": bool(
                            refinement_attempt["geometry_transform_applied"]
                        ),
                        "value_matrix_column_anchors": [
                            round(anchor, 4)
                            for anchor in value_matrix_column_anchors
                        ],
                    }

    value_matrix_refinement = _refine_grid_from_value_matrix_word_positions(
        raw_rows=raw_rows,
        clipped_words=clipped_words,
        clipped_chars=clipped_chars,
        horizontal_rules=horizontal_rules,
        full_width_rules=full_width_rules,
    )
    if value_matrix_refinement is not None:
        return value_matrix_refinement

    header_text = " ".join(
        cell
        for row in raw_rows[:2]
        for cell in row
        if isinstance(cell, str) and cell.strip()
    )
    if (
        len(horizontal_rules) >= 3
        and len(MODEL_HEADER_PATTERN.findall(header_text)) >= 2
        and ESTIMATE_HEADER_PATTERN.search(header_text)
    ):
        refined_lines = build_word_lines(clipped_words)
        header_boundary = horizontal_rules[1]
        header_line_count = sum(
            float(line["bottom"]) <= header_boundary + 2.0
            for line in refined_lines
        )
        if 1 <= header_line_count < len(refined_lines):
            refined_rows, refined_cell_bboxes = build_row_grid_from_lines(
                refined_lines,
                page_chars=clipped_chars,
            )
            if refined_rows:
                keep_indices = [
                    col_idx
                    for col_idx in range(len(refined_rows[0]))
                    if any(col_idx < len(row) and row[col_idx].strip() for row in refined_rows)
                ]
                if keep_indices:
                    refined_rows = [
                        [row[col_idx] for col_idx in keep_indices]
                        for row in refined_rows
                    ]
                    refined_cell_bboxes = [
                        [row[col_idx] for col_idx in keep_indices]
                        for row in refined_cell_bboxes
                    ]
                if (
                    len(refined_rows) >= len(raw_rows) + 2
                    and max((len(row) for row in refined_rows), default=0)
                    >= max((len(row) for row in raw_rows), default=0) + 2
                ):
                    return {
                        "raw_rows": refined_rows,
                        "table_cells": refined_cell_bboxes,
                        "refined_table_cells": refined_cell_bboxes,
                        "row_bounds": [
                            (float(line["top"]), float(line["bottom"]))
                            for line in refined_lines
                        ],
                        "horizontal_rules": horizontal_rules,
                        "full_width_horizontal_rules": full_width_rules,
                        "grid_refinement_source": "word_positions_with_horizontal_rules",
                        "geometry_coordinate_frame": "page",
                        "geometry_transform_source_bbox": None,
                        "geometry_transform_transposed": False,
                        "geometry_transform_applied": False,
                    }

    return {
        "raw_rows": raw_rows,
        "table_cells": table_cells,
        "refined_table_cells": refined_table_cells,
        "row_bounds": row_bounds,
        "horizontal_rules": horizontal_rules,
        "full_width_horizontal_rules": full_width_rules,
        "grid_refinement_source": grid_refinement_source,
        "geometry_coordinate_frame": geometry_coordinate_frame,
        "geometry_transform_source_bbox": None,
        "geometry_transform_transposed": False,
        "geometry_transform_applied": False,
    }


def _column_count(candidate: DetectedTableCandidate) -> int:
    """Return the candidate column count."""
    return max((len(row) for row in candidate.raw_rows), default=0)


def _front_matter_intervals_by_page(document: Any | None) -> dict[int, tuple[float, float]]:
    """Return page y-intervals between the abstract heading and introduction heading."""
    if document is None:
        return {}

    abstract_location: tuple[int, float] | None = None
    introduction_location: tuple[int, float] | None = None
    page_bottoms: dict[int, float] = {}

    page_count = int(getattr(document, "page_count", 0) or 0)
    for zero_based_page_num in range(page_count):
        try:
            page = document.load_page(zero_based_page_num)
        except Exception:
            continue
        page_num = zero_based_page_num + 1
        page_rect = getattr(page, "rect", None)
        page_bottoms[page_num] = float(getattr(page_rect, "height", 0.0) or 0.0)
        try:
            lines = build_word_lines(extract_page_words(page))
        except Exception:
            continue
        for line in lines:
            text = str(line.get("text", "")).strip()
            if not text:
                continue
            line_top = float(line.get("top", 0.0))
            if abstract_location is None and _is_abstract_heading(text):
                abstract_location = (page_num, line_top)
                continue
            if abstract_location is not None and _is_introduction_heading(text):
                introduction_location = (page_num, line_top)
                break
        if abstract_location is not None and introduction_location is not None:
            break

    if abstract_location is None or introduction_location is None:
        return {}
    abstract_page, abstract_top = abstract_location
    introduction_page, introduction_top = introduction_location
    if (introduction_page, introduction_top) <= (abstract_page, abstract_top):
        return {}

    intervals: dict[int, tuple[float, float]] = {}
    for page_num in range(abstract_page, introduction_page + 1):
        page_bottom = page_bottoms.get(page_num, 0.0)
        if page_num == abstract_page and page_num == introduction_page:
            intervals[page_num] = (abstract_top, introduction_top)
        elif page_num == abstract_page:
            intervals[page_num] = (abstract_top, page_bottom)
        elif page_num == introduction_page:
            intervals[page_num] = (0.0, introduction_top)
        else:
            intervals[page_num] = (0.0, page_bottom)
    return intervals


def _is_abstract_heading(text: str) -> bool:
    """Return whether a line is an abstract heading, including letter-spaced forms."""
    compact_alpha = re.sub(r"[^A-Za-z]+", "", text).casefold()
    return compact_alpha == "abstract" or (
        compact_alpha.endswith("abstract") and len(compact_alpha) <= 28
    )


def _is_introduction_heading(text: str) -> bool:
    """Return whether a line starts an introduction section."""
    return bool(INTRODUCTION_HEADING_PATTERN.match(clean_text(text)))


def _is_uncaptioned_front_matter_layout_candidate(
    candidate: DetectedTableCandidate,
    front_matter_interval: tuple[float, float] | None,
) -> bool:
    """Return whether an uncaptained candidate is a front-matter layout block."""
    if front_matter_interval is None or candidate.bbox is None:
        return False
    if candidate.caption or candidate.metadata.get("table_number") is not None:
        return False
    signals = candidate.metadata.get("signals")
    if isinstance(signals, dict) and bool(signals.get("caption_match")):
        return False

    candidate_top = float(candidate.bbox[1])
    candidate_bottom = float(candidate.bbox[3])
    candidate_height = max(1.0, candidate_bottom - candidate_top)
    interval_top, interval_bottom = front_matter_interval
    overlap = min(candidate_bottom, interval_bottom) - max(candidate_top, interval_top)
    if overlap <= 0 or overlap / candidate_height < 0.6:
        return False

    value_anchors = candidate.metadata.get("value_matrix_column_anchors")
    if isinstance(value_anchors, list) and len(value_anchors) >= 3:
        return False
    later_numeric_ratio = (
        float(signals.get("later_column_numeric_ratio", 0.0))
        if isinstance(signals, dict)
        else 0.0
    )
    if later_numeric_ratio >= 0.5 and len(candidate.raw_rows) >= 3:
        return False
    return True


def _looks_like_collapsed_grid_candidate(candidate: DetectedTableCandidate) -> bool:
    """Return whether a grid has collapsed several physical columns into wide cells."""
    return (
        _column_count(candidate) <= 4
        and len(candidate.raw_rows) >= 3
        and any(
            len(str(cell).split()) >= 20
            for row in candidate.raw_rows
            for cell in row
        )
    )


def _first_column_fill_ratio(candidate: DetectedTableCandidate) -> float:
    """Measure how often the first column is populated in the extracted grid."""
    if not candidate.raw_rows:
        return 0.0
    return round(
        sum(bool(row and row[0].strip()) for row in candidate.raw_rows) / len(candidate.raw_rows),
        4,
    )


def _collect_page_text(page_boxes: list[dict[str, Any]]) -> str:
    """Collect page text from non-table content boxes."""
    texts = []
    for box in page_boxes:
        if box.get("boxclass") == "table":
            continue
        text = _extract_box_text(box)
        if text:
            texts.append(text)
    return "\n".join(texts)


def _extract_page_chars_with_page_num(page: Any, page_num: int) -> list[dict[str, object]]:
    """Extract PyMuPDF chars and attach one-based page provenance."""
    chars = extract_page_chars(page)
    for char in chars:
        char.setdefault("page_num", page_num)
    return chars


def _extract_box_text(box: dict[str, Any]) -> str:
    """Read text from a PyMuPDF4LLM box."""
    textlines = box.get("textlines") or []
    lines: list[str] = []
    for line in textlines:
        line_text = join_pymupdf_line_spans(line.get("spans") or [])
        if line_text:
            lines.append(line_text)
    return " ".join(lines).strip()


def _as_bbox(value: Any) -> tuple[float, float, float, float] | None:
    """Convert a raw bbox-like value to a tuple."""
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    return tuple(float(part) for part in value)


def _box_bbox(box: dict[str, Any]) -> tuple[float, float, float, float] | None:
    """Read a PyMuPDF4LLM box bbox from either bbox or coordinate fields."""
    bbox = _as_bbox(box.get("bbox"))
    if bbox is not None:
        return bbox
    if not all(key in box for key in ("x0", "y0", "x1", "y1")):
        return None
    return (
        float(box["x0"]),
        float(box["y0"]),
        float(box["x1"]),
        float(box["y1"]),
    )


def _coerce_cell_bboxes(table_cells: list[Any]) -> list[list[tuple[float, float, float, float] | None]]:
    """Normalize PyMuPDF4LLM cell bbox arrays into row-major bbox lists."""
    rows: list[list[tuple[float, float, float, float] | None]] = []
    for row in table_cells:
        if not isinstance(row, list):
            continue
        bbox_row: list[tuple[float, float, float, float] | None] = []
        for cell in row:
            bbox_row.append(_as_bbox(cell))
        rows.append(bbox_row)
    return rows
