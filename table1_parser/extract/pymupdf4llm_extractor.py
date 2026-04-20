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
        candidates: list[DetectedTableCandidate] = []
        explicit_page_nums: set[int] = set()
        try:
            document = open_pymupdf_document(pdf_path)
        except Exception:
            document = None
        try:
            for page_num, payload_page in sorted(pages.items()):
                page = None
                if document is not None and 0 <= page_num - 1 < getattr(document, "page_count", 0):
                    page = document.load_page(page_num - 1)
                page_boxes = payload_page.get("boxes", []) or []
                page_text = _collect_page_text(page_boxes)
                if page is None:
                    page_words = []
                    page_chars = []
                    page_rule_segments = []
                else:
                    page_words = extract_page_words(page)
                    page_chars = extract_page_chars(page)
                    page_rule_segments = extract_page_rule_segments(page)
                page_candidates: list[DetectedTableCandidate] = []
                table_boxes = [box for box in page_boxes if isinstance(box, dict) and box.get("table")]
                table_count = len(table_boxes)
                for table_index, box in enumerate(table_boxes):
                    table = box.get("table") or {}
                    original_raw_rows = _normalize_rows(table.get("extract") or [])
                    raw_rows = original_raw_rows
                    if not original_raw_rows:
                        continue
                    bbox = _as_bbox(table.get("bbox")) or _as_bbox(box.get("bbox"))
                    cell_bboxes = _coerce_cell_bboxes(table.get("cells") or [])
                    orientation_metadata = _infer_table_orientation_metadata(page, bbox)
                    refinement = _refine_explicit_table_candidate_grid(
                        raw_rows=raw_rows,
                        cell_bboxes=cell_bboxes,
                        bbox=bbox,
                        page_words=page_words,
                        page_chars=page_chars,
                        page_rule_segments=page_rule_segments,
                        orientation_metadata=orientation_metadata,
                    )
                    raw_rows = refinement["raw_rows"]
                    cell_bboxes = refinement["table_cells"]
                    row_bounds = refinement["row_bounds"]
                    horizontal_rules = refinement["horizontal_rules"]
                    nearby_caption_candidates: list[tuple[float, str]] = []
                    table_top = bbox[1] if bbox else float("inf")
                    for candidate_box in page_boxes:
                        if candidate_box.get("boxclass") == "table":
                            continue
                        candidate_bbox = _as_bbox(candidate_box.get("bbox"))
                        if candidate_bbox is None or candidate_bbox[3] > table_top + 2.0:
                            continue
                        caption_lines = _find_table_caption_lines(_extract_box_text(candidate_box))
                        if not caption_lines:
                            continue
                        nearby_caption_candidates.append((table_top - candidate_bbox[3], caption_lines[-1]))
                    nearby_caption = (
                        min(nearby_caption_candidates, key=lambda item: item[0])[1]
                        if nearby_caption_candidates
                        else None
                    )
                    caption = _caption_for_index(
                        nearby_caption,
                        page_text,
                        table_index,
                        table_count,
                    )
                    page_candidates.append(
                        score_candidate(
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
                                    "geometry_coordinate_frame": refinement["geometry_coordinate_frame"],
                                    "table_markdown": table.get("markdown"),
                                    "table_cells": cell_bboxes,
                                    "refined_table_cells": refinement["refined_table_cells"],
                                    "original_table_cells": table.get("cells") if raw_rows != original_raw_rows else None,
                                    "original_backend_rows": table.get("extract") if raw_rows != original_raw_rows else None,
                                    "row_bounds": row_bounds,
                                    "horizontal_rules": horizontal_rules,
                                    **orientation_metadata,
                                },
                            )
                        )
                    )
                page_candidates = self._rescue_low_quality_page_candidates(
                    page_num=page_num,
                    page=page,
                    page_text=page_text,
                    page_candidates=page_candidates,
                )
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
                page_text = _collect_page_text(page_boxes) or extract_page_text(page)
                for candidate in build_text_layout_candidates(
                    page_num=page_num,
                    page_text=page_text,
                    words=extract_page_words(page),
                    chars=extract_page_chars(page),
                    rule_segments=extract_page_rule_segments(page),
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
            chars=extract_page_chars(page),
            rule_segments=extract_page_rule_segments(page),
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


def _refine_explicit_table_candidate_grid(
    *,
    raw_rows: list[list[str]],
    cell_bboxes: list[list[tuple[float, float, float, float] | None]],
    bbox: tuple[float, float, float, float] | None,
    page_words: list[dict[str, object]],
    page_chars: list[dict[str, object]],
    page_rule_segments: list[tuple[float, float, float, float]],
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

    full_width_rules = detect_horizontal_rules(page_rule_segments, bbox) if bbox is not None else []
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
            "grid_refinement_source": grid_refinement_source,
            "geometry_coordinate_frame": geometry_coordinate_frame,
        }

    clipped_words = [
        word
        for word in page_words
        if float(word["x0"]) >= bbox[0] - 2.0
        and float(word["x1"]) <= bbox[2] + 2.0
        and float(word["top"]) >= bbox[1] - 2.0
        and float(word["bottom"]) <= bbox[3] + 2.0
    ]
    if not clipped_words:
        return {
            "raw_rows": raw_rows,
            "table_cells": table_cells,
            "refined_table_cells": refined_table_cells,
            "row_bounds": row_bounds,
            "horizontal_rules": horizontal_rules,
            "grid_refinement_source": grid_refinement_source,
            "geometry_coordinate_frame": geometry_coordinate_frame,
        }

    clipped_chars = [
        char
        for char in page_chars
        if float(char["x0"]) >= bbox[0] - 2.0
        and float(char["x1"]) <= bbox[2] + 2.0
        and float(char["top"]) >= bbox[1] - 2.0
        and float(char["bottom"]) <= bbox[3] + 2.0
    ]

    is_rotated = (
        orientation_metadata.get("table_orientation") == "rotated"
        and float(orientation_metadata.get("rotation_confidence") or 0.0) >= 0.8
    )
    collapsed_explicit_grid = (
        len(raw_rows) <= 1
        or (
            len(raw_rows) <= 3
            and max((len(row) for row in raw_rows), default=0) <= 4
            and len(clipped_words) >= 12
        )
    )

    if is_rotated and collapsed_explicit_grid:
        clipped_rule_segments = [
            segment
            for segment in page_rule_segments
            if max(float(segment[0]), float(segment[2])) >= bbox[0] - 2.0
            and min(float(segment[0]), float(segment[2])) <= bbox[2] + 2.0
            and max(float(segment[1]), float(segment[3])) >= bbox[1] - 2.0
            and min(float(segment[1]), float(segment[3])) <= bbox[3] + 2.0
        ]
        transformed_words, transformed_chars, transformed_rule_segments, transformed_bbox = (
            normalize_positioned_geometry_for_rotation(
                words=clipped_words,
                chars=clipped_chars,
                rule_segments=clipped_rule_segments,
                bbox=bbox,
                rotation_direction=str(orientation_metadata.get("rotation_direction") or ""),
            )
        )
        refined_lines = build_word_lines(transformed_words)
        transformed_horizontal_rules = detect_horizontal_rules(
            transformed_rule_segments,
            transformed_bbox,
        )
        if len(transformed_horizontal_rules) >= 3:
            footer_boundary = sorted(transformed_horizontal_rules)[-1]
            refined_lines = [
                line
                for line in refined_lines
                if float(line["bottom"]) <= footer_boundary + 1.5
            ]
        refined_rows, transformed_cell_bboxes = build_row_grid_from_lines(
            refined_lines,
            page_chars=transformed_chars,
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
                transformed_cell_bboxes = [
                    [row[col_idx] for col_idx in keep_indices]
                    for row in transformed_cell_bboxes
                ]
            if (
                len(refined_rows) >= len(raw_rows) + 3
                and max((len(row) for row in refined_rows), default=0)
                > max((len(row) for row in raw_rows), default=0)
            ):
                return {
                    "raw_rows": refined_rows,
                    "table_cells": [],
                    "refined_table_cells": transformed_cell_bboxes,
                    "row_bounds": [
                        (float(line["top"]), float(line["bottom"]))
                        for line in refined_lines
                    ],
                    "horizontal_rules": transformed_horizontal_rules,
                    "grid_refinement_source": "rotated_word_positions_with_rules",
                    "geometry_coordinate_frame": "table_local_rotated_normalized",
                }

    if collapsed_explicit_grid:
        refined_lines = build_word_lines(clipped_words)
        if len(horizontal_rules) >= 3:
            footer_boundary = sorted(horizontal_rules)[-1]
            refined_lines = [
                line
                for line in refined_lines
                if float(line["bottom"]) <= footer_boundary + 1.5
            ]
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
                len(refined_rows) >= len(raw_rows) + 4
                and max((len(row) for row in refined_rows), default=0)
                > max((len(row) for row in raw_rows), default=0)
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
                    "grid_refinement_source": "collapsed_explicit_grid_word_positions",
                    "geometry_coordinate_frame": "page",
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
                        "grid_refinement_source": "word_positions_with_horizontal_rules",
                        "geometry_coordinate_frame": "page",
                    }

    return {
        "raw_rows": raw_rows,
        "table_cells": table_cells,
        "refined_table_cells": refined_table_cells,
        "row_bounds": row_bounds,
        "horizontal_rules": horizontal_rules,
        "grid_refinement_source": grid_refinement_source,
        "geometry_coordinate_frame": geometry_coordinate_frame,
    }


def _column_count(candidate: DetectedTableCandidate) -> int:
    """Return the candidate column count."""
    return max((len(row) for row in candidate.raw_rows), default=0)


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
