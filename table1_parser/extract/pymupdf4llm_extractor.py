"""PyMuPDF4LLM-based extraction backend."""

from __future__ import annotations

import contextlib
import io
import json
import re
from pathlib import Path
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
from table1_parser.schemas import ExtractedTable, TableCell


MODEL_HEADER_PATTERN = re.compile(r"\bmodel[_\s]*\d+\b", re.IGNORECASE)
ESTIMATE_HEADER_PATTERN = re.compile(r"\b(?:or\b|95%\s*ci|p(?:-value)?\b)\b", re.IGNORECASE)
REFERENCES_HEADING_PATTERN = re.compile(
    r"(?m)^\s*(?:#{1,6}\s*)?(?:[*_`]+)?(?:references|bibliography)(?:[*_`]+)?\s*$",
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

    def extract(self, pdf_path: str) -> list[ExtractedTable]:
        """Extract and rank raw table candidates from a PDF."""
        try:
            candidates = self._detect_table_candidates(pdf_path)
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

    def _detect_table_candidates(self, pdf_path: str) -> list[DetectedTableCandidate]:
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
                if REFERENCES_HEADING_PATTERN.search(page_text):
                    in_references_section = True
                    if references_start_page_num is None:
                        references_start_page_num = page_num
                if in_references_section:
                    continue
                if page is None:
                    page_words = []
                    page_chars = []
                    page_rule_segments = []
                    page_stroked_rule_segments = []
                else:
                    page_words = extract_page_words(page)
                    page_chars = _extract_page_chars_with_page_num(page, page_num)
                    page_rule_segments = extract_page_rule_segments(page)
                    page_stroked_rule_segments = extract_page_rule_segments(page, include_filled=False)
                page_candidates: list[DetectedTableCandidate] = []
                table_boxes = [
                    box
                    for box in page_boxes
                    if isinstance(box, dict) and box.get("table")
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
                    cell_bboxes = _coerce_cell_bboxes(table.get("cells") or [])
                    orientation_metadata = _infer_table_orientation_metadata(page, bbox)
                    refinement = _refine_explicit_table_candidate_grid(
                        raw_rows=raw_rows,
                        cell_bboxes=cell_bboxes,
                        bbox=bbox,
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
                    trimmed = trim_trailing_non_table_rows(
                        raw_rows,
                        cell_bboxes=cell_bboxes,
                        row_bounds=row_bounds,
                    )
                    raw_rows = trimmed.raw_rows
                    cell_bboxes = trimmed.cell_bboxes
                    row_bounds = trimmed.row_bounds
                    if trimmed.metadata is not None and row_bounds:
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
                    nearby_caption_candidates: list[tuple[float, str]] = []
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
                            (table_top - candidate_bbox[3], caption_line)
                        )
                    nearby_caption = (
                        min(nearby_caption_candidates, key=lambda item: item[0])[1]
                        if nearby_caption_candidates
                        else None
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
                                "trailing_non_table_rows": trimmed.metadata,
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
                    page_candidates.append(scored_candidate)
                page_candidates = self._rescue_low_quality_page_candidates(
                    page_num=page_num,
                    page=page,
                    page_text=page_text,
                    page_candidates=page_candidates,
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
                if REFERENCES_HEADING_PATTERN.search(page_text):
                    references_start_page_num = page_num
                    continue
                for candidate in build_text_layout_candidates(
                    page_num=page_num,
                    page_text=page_text,
                    words=extract_page_words(page),
                    chars=_extract_page_chars_with_page_num(page, page_num),
                    rule_segments=extract_page_rule_segments(page, include_filled=False),
                    layout_source="pymupdf_text_positions",
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
        return {
            "table_orientation": "rotated",
            "rotation_source": "pymupdf_line_direction",
            "rotation_direction": "vertical_text_up" if vertical_up_count >= vertical_down_count else "vertical_text_down",
            "rotation_confidence": round(vertical_count / considered_count, 4),
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
        if top_rule < bbox[1] and bbox[1] - top_rule <= 20.0:
            word_clip_bbox = (bbox[0], top_rule, bbox[2], bbox[3])

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
    )

    if collapsed_explicit_grid:
        should_rotate_refinement = is_rotated or rotated_few_column_stacked_grid
        refinement_attempts: list[dict[str, object]] = []

        if should_rotate_refinement:
            rotated_refinement_bbox = bbox
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
                    "refinement_source": "collapsed_explicit_grid_word_positions",
                    "coordinate_frame": "page",
                    "geometry_transform_source_bbox": None,
                    "geometry_transform_transposed": False,
                    "geometry_transform_applied": False,
                    "minimum_row_gain": 4,
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
            if (
                bool(refinement_attempt["geometry_transform_applied"])
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
                if column_gain_ok and (row_gain_ok or stacked_column_gain_ok):
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
                    }

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
        spans = line.get("spans") or []
        pieces: list[str] = []
        for part in (str(span.get("text", "")) for span in spans):
            if not part:
                continue
            if pieces:
                previous = pieces[-1]
                if (
                    previous
                    and not previous[-1].isspace()
                    and not part[0].isspace()
                    and (
                        (previous[-1].isalnum() and part[0].isalnum())
                        or (previous[-1].isalnum() and part[0] == "(")
                        or (previous[-1] in {")", "]"} and part[0].isalnum())
                    )
                ):
                    pieces.append(" ")
            pieces.append(part)
        line_text = "".join(pieces).strip()
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
