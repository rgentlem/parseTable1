"""PyMuPDF positioned-geometry extraction backend."""

from __future__ import annotations

import re
from pathlib import Path
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from table1_parser.config import Settings
from table1_parser.extract.base import BaseExtractor
from table1_parser.extract.layout_fallback import (
    build_text_layout_candidates,
    build_word_lines,
    normalize_bbox_for_rotation,
    normalize_positioned_geometry_for_rotation,
)
from table1_parser.extract.provisional_table import ProvisionalExtractedTable
from table1_parser.context.paper_positioned_document import build_paper_positioned_document
from table1_parser.extract.table_detector import (
    DetectedTableCandidate,
)
from table1_parser.extract.table_selector import select_top_candidates
from table1_parser.page_furniture_mask import (
    bbox_overlap_fraction,
    filter_positioned_items_for_page_furniture,
)
from table1_parser.schemas import (
    BibliographyEntry,
    PaperPageFurniture,
    PaperPositionedDocument,
    PaperPositionedPage,
    PaperTableMention,
    PaperTextLine,
    PaperTextOrientationGroup,
    PaperTextStream,
    PositionedSpanReference,
    TableCaptionBinding,
    TableCaptionRegion,
    TableCanonicalTransform,
    TableCell,
    TablePositionedEvidence,
)
from table1_parser.text_cleaning import clean_text


INTRODUCTION_HEADING_PATTERN = re.compile(
    r"^(?:\d+(?:\.\d+)*\.?\s+)?introduction\b",
    re.IGNORECASE,
)
CAPTION_LINK_MAX_DISTANCE = 120.0
CAPTION_BOUNDARY_TOLERANCE = 2.0


@dataclass(slots=True)
class BibliographyEvidenceMask:
    """Page-local bibliography-owned evidence used before table candidate construction."""

    page_num: int
    source_line_ids: set[str]
    source_line_keys: set[tuple[int, int]]
    line_regions: list[tuple[float, float, float, float]]
    entry_regions: list[tuple[float, float, float, float]]


def _caption_label_assignments(
    *,
    page_num: int,
    table_bboxes: Sequence[tuple[float, float, float, float] | None],
    orientation_metadata: Sequence[dict[str, Any]],
    paper_text_stream: PaperTextStream | None,
    paper_table_mentions: Sequence[PaperTableMention] | None,
) -> dict[int, tuple[TableCaptionRegion, TableCaptionBinding]]:
    """Bind PyMuPDF caption-label lines to table regions in canonical geometry."""
    if paper_text_stream is None or not paper_table_mentions:
        return {}
    page = next((item for item in paper_text_stream.pages if item.page_num == page_num), None)
    if page is None:
        return {}
    groups_by_id = {group.group_id: group for group in page.orientation_groups}
    lines_by_id = {
        line.line_id: line
        for line in paper_text_stream.lines
        if line.page_num == page_num
    }
    table_geometry: list[
        tuple[int, PaperTextOrientationGroup, tuple[float, float, float, float]]
    ] = []
    for table_index, table_bbox in enumerate(table_bboxes):
        if table_bbox is None or table_index >= len(orientation_metadata):
            continue
        metadata = orientation_metadata[table_index]
        rotation_direction = str(metadata.get("rotation_direction") or "upright")
        orientation = (
            rotation_direction
            if rotation_direction in {"vertical_text_up", "vertical_text_down"}
            else "upright"
        )
        for group in page.orientation_groups:
            if group.orientation == orientation:
                source_bbox = _as_bbox(metadata.get("rotated_text_block_bbox")) or table_bbox
            elif orientation == "upright" and group.orientation != "upright":
                source_bbox = (
                    max(table_bbox[0], group.source_bbox[0]),
                    max(table_bbox[1], group.source_bbox[1]),
                    min(table_bbox[2], group.source_bbox[2]),
                    min(table_bbox[3], group.source_bbox[3]),
                )
                if source_bbox[2] <= source_bbox[0] or source_bbox[3] <= source_bbox[1]:
                    continue
            else:
                continue
            canonical_table_bbox = (
                normalize_bbox_for_rotation(
                    source_bbox,
                    source_bbox=group.source_bbox,
                    rotation_direction=group.orientation,
                )
                if group.orientation != "upright"
                else source_bbox
            )
            table_geometry.append((table_index, group, canonical_table_bbox))

    caption_records: list[tuple[PaperTableMention, PaperTextLine, TableCaptionRegion]] = []
    for mention in paper_table_mentions:
        if (
            mention.page_num != page_num
            or not mention.is_caption_candidate
            or "line_starts_with_table_label" not in mention.notes
        ):
            continue
        line = lines_by_id.get(mention.source_line_id)
        if (
            line is None
            or line.canonical_bbox is None
            or line.orientation_group_id not in groups_by_id
        ):
            continue
        region = TableCaptionRegion(
            mention_id=mention.mention_id,
            table_number=mention.table_number,
            mention_kind=mention.mention_kind,
            page_num=page_num,
            label_line_id=line.line_id,
            line_ids=[line.line_id],
            text_lines=[line.text],
            text=line.text,
            bbox=line.bbox,
            canonical_bbox=line.canonical_bbox,
            orientation=line.orientation,
            orientation_group_id=line.orientation_group_id,
            column_index=line.column_index,
        )
        caption_records.append((mention, line, region))

    pair_candidates: list[tuple[float, float, int, int, str, int]] = []
    for caption_index, (_, line, _) in enumerate(caption_records):
        caption_bbox = line.canonical_bbox
        if caption_bbox is None:
            continue
        for geometry_index, (table_index, group, table_bbox) in enumerate(table_geometry):
            if line.orientation_group_id != group.group_id:
                continue
            horizontal_overlap = min(table_bbox[2], caption_bbox[2]) - max(
                table_bbox[0], caption_bbox[0]
            )
            if horizontal_overlap <= 0.0:
                continue
            if caption_bbox[3] <= table_bbox[1] + CAPTION_BOUNDARY_TOLERANCE:
                placement = "above"
                distance = max(0.0, table_bbox[1] - caption_bbox[3])
            elif caption_bbox[1] >= table_bbox[3] - CAPTION_BOUNDARY_TOLERANCE:
                placement = "below"
                distance = max(0.0, caption_bbox[1] - table_bbox[3])
            else:
                distance_to_top = abs(caption_bbox[1] - table_bbox[1])
                distance_to_bottom = abs(table_bbox[3] - caption_bbox[3])
                placement = "above" if distance_to_top <= distance_to_bottom else "below"
                distance = 0.0
            if distance <= CAPTION_LINK_MAX_DISTANCE:
                pair_candidates.append(
                    (
                        distance,
                        -horizontal_overlap,
                        caption_index,
                        table_index,
                        placement,
                        geometry_index,
                    )
                )

    assignments: dict[int, tuple[TableCaptionRegion, TableCaptionBinding]] = {}
    used_caption_indices: set[int] = set()
    for distance, _, caption_index, table_index, placement, geometry_index in sorted(
        pair_candidates
    ):
        if caption_index in used_caption_indices or table_index in assignments:
            continue
        _, _, region = caption_records[caption_index]
        _, _, table_bbox = table_geometry[geometry_index]
        binding = TableCaptionBinding(
            placement=placement,
            distance=round(distance, 3),
            mention_id=region.mention_id,
            orientation_group_id=region.orientation_group_id,
            caption_bbox=region.bbox,
            caption_canonical_bbox=region.canonical_bbox,
            table_canonical_bbox=table_bbox,
        )
        assignments[table_index] = (region, binding)
        used_caption_indices.add(caption_index)
    return assignments


def _complete_caption_region(
    *,
    region: TableCaptionRegion,
    binding: TableCaptionBinding,
    candidate_metadata: dict[str, Any],
    paper_text_stream: PaperTextStream,
    caption_label_line_ids: set[str],
) -> tuple[TableCaptionRegion, TableCaptionBinding]:
    """Extend one bound caption label through adjacent single-run text bands."""
    group_lines = [
        line
        for line in paper_text_stream.lines
        if line.page_num == region.page_num
        and line.orientation_group_id == region.orientation_group_id
        and line.column_index == region.column_index
    ]
    label_index = next(
        (index for index, line in enumerate(group_lines) if line.line_id == region.label_line_id),
        None,
    )
    if label_index is None:
        return region, binding
    page = next(
        (item for item in paper_text_stream.pages if item.page_num == region.page_num),
        None,
    )
    group = next(
        (
            item
            for item in page.orientation_groups
            if item.group_id == region.orientation_group_id
        ),
        None,
    ) if page is not None else None

    boundary_y: float | None = None
    if binding.placement == "above":
        rules = [
            float(rule)
            for rule in (
                candidate_metadata.get("horizontal_rules")
                or candidate_metadata.get("full_width_horizontal_rules")
                or []
            )
        ]
        if rules:
            transform_bbox = _as_bbox(
                candidate_metadata.get("geometry_transform_source_bbox")
            )
            rotation_direction = str(candidate_metadata.get("rotation_direction") or "")
            if transform_bbox is not None and group is not None:
                if rotation_direction == "vertical_text_up":
                    rules = [
                        rule + transform_bbox[0] - group.source_bbox[0]
                        for rule in rules
                    ]
                elif rotation_direction == "vertical_text_down":
                    rules = [
                        rule + group.source_bbox[2] - transform_bbox[2]
                        for rule in rules
                    ]
            rules_below_label = [
                rule
                for rule in rules
                if rule >= region.canonical_bbox[3] - CAPTION_BOUNDARY_TOLERANCE
            ]
            boundary_y = min(rules_below_label or rules)
        else:
            boundary_y = binding.table_canonical_bbox[1]

    selected_lines = [group_lines[label_index]]
    following_lines: list[PaperTextLine] = []
    for line in group_lines[label_index + 1 :]:
        if line.line_id in caption_label_line_ids:
            break
        line_bbox = line.canonical_bbox
        if line_bbox is None:
            break
        if boundary_y is not None and line_bbox[3] > boundary_y + CAPTION_BOUNDARY_TOLERANCE:
            break
        horizontal_overlap = min(binding.table_canonical_bbox[2], line_bbox[2]) - max(
            binding.table_canonical_bbox[0], line_bbox[0]
        )
        if horizontal_overlap <= 0.0:
            continue
        following_lines.append(line)

    line_bands: list[list[PaperTextLine]] = []
    for line in sorted(
        following_lines,
        key=lambda item: (
            item.canonical_bbox[1] if item.canonical_bbox is not None else 0.0,
            item.canonical_bbox[0] if item.canonical_bbox is not None else 0.0,
        ),
    ):
        line_bbox = line.canonical_bbox
        if line_bbox is None:
            continue
        if not line_bands:
            line_bands.append([line])
            continue
        prior_bboxes = [
            item.canonical_bbox
            for item in line_bands[-1]
            if item.canonical_bbox is not None
        ]
        prior_top = min(bbox[1] for bbox in prior_bboxes)
        prior_bottom = max(bbox[3] for bbox in prior_bboxes)
        band_height = max(1.0, prior_bottom - prior_top, line_bbox[3] - line_bbox[1])
        prior_center = (prior_top + prior_bottom) / 2.0
        line_center = (line_bbox[1] + line_bbox[3]) / 2.0
        if line_bbox[1] <= prior_bottom and abs(line_center - prior_center) <= 0.5 * band_height:
            line_bands[-1].append(line)
        else:
            line_bands.append([line])

    for band in line_bands:
        band_bboxes = sorted(
            (
                line.canonical_bbox
                for line in band
                if line.canonical_bbox is not None
            ),
            key=lambda bbox: (bbox[0], bbox[2]),
        )
        if not band_bboxes:
            continue
        band_top = min(bbox[1] for bbox in band_bboxes)
        band_bottom = max(bbox[3] for bbox in band_bboxes)
        band_height = max(1.0, band_bottom - band_top)
        horizontal_run_count = 1
        previous_right = band_bboxes[0][2]
        for bbox in band_bboxes[1:]:
            if bbox[0] - previous_right > band_height:
                horizontal_run_count += 1
            previous_right = max(previous_right, bbox[2])
        if horizontal_run_count > 1:
            break
        previous_bbox = selected_lines[-1].canonical_bbox
        if previous_bbox is None or band_top - previous_bbox[3] > 1.25 * max(
            band_height,
            previous_bbox[3] - previous_bbox[1],
        ):
            break
        selected_lines.extend(sorted(band, key=lambda line: line.canonical_bbox[0]))

    source_bbox = (
        min(line.bbox[0] for line in selected_lines),
        min(line.bbox[1] for line in selected_lines),
        max(line.bbox[2] for line in selected_lines),
        max(line.bbox[3] for line in selected_lines),
    )
    canonical_bboxes = [
        line.canonical_bbox
        for line in selected_lines
        if line.canonical_bbox is not None
    ]
    canonical_bbox = (
        min(bbox[0] for bbox in canonical_bboxes),
        min(bbox[1] for bbox in canonical_bboxes),
        max(bbox[2] for bbox in canonical_bboxes),
        max(bbox[3] for bbox in canonical_bboxes),
    )
    text_lines = [line.text for line in selected_lines]
    complete_region = region.model_copy(
        update={
            "line_ids": [line.line_id for line in selected_lines],
            "text_lines": text_lines,
            "text": "\n".join(text_lines),
            "bbox": source_bbox,
            "canonical_bbox": canonical_bbox,
        }
    )
    complete_binding = binding.model_copy(
        update={
            "caption_bbox": source_bbox,
            "caption_canonical_bbox": canonical_bbox,
        }
    )
    return complete_region, complete_binding


def _apply_complete_caption_bindings(
    candidates: Sequence[DetectedTableCandidate],
    *,
    paper_text_stream: PaperTextStream | None,
    paper_table_mentions: Sequence[PaperTableMention] | None,
) -> list[DetectedTableCandidate]:
    """Replace provisional captions with complete PyMuPDF caption regions."""
    if paper_text_stream is None or not paper_table_mentions:
        return [
            candidate.model_copy(
                update={
                    "caption": None,
                    "metadata": {
                        **candidate.metadata,
                        "caption_source": None,
                        "caption_region": None,
                        "caption_binding": None,
                        "caption_detection_space": None,
                    },
                }
            )
            for candidate in candidates
        ]
    caption_label_line_ids = {
        mention.source_line_id
        for mention in paper_table_mentions
        if mention.is_caption_candidate
    }
    result = list(candidates)
    candidate_indices_by_page: dict[int, list[int]] = {}
    for candidate_index, candidate in enumerate(candidates):
        candidate_indices_by_page.setdefault(candidate.page_num, []).append(candidate_index)
    for page_num, candidate_indices in candidate_indices_by_page.items():
        page_candidates = [candidates[index] for index in candidate_indices]
        assignments = _caption_label_assignments(
            page_num=page_num,
            table_bboxes=[candidate.bbox for candidate in page_candidates],
            orientation_metadata=[candidate.metadata for candidate in page_candidates],
            paper_text_stream=paper_text_stream,
            paper_table_mentions=paper_table_mentions,
        )
        for page_candidate_index, candidate in enumerate(page_candidates):
            result_index = candidate_indices[page_candidate_index]
            assignment = assignments.get(page_candidate_index)
            if assignment is None:
                result[result_index] = candidate.model_copy(
                    update={
                        "caption": None,
                        "metadata": {
                            **candidate.metadata,
                            "caption_source": None,
                            "caption_region": None,
                            "caption_binding": None,
                            "caption_detection_space": None,
                        },
                    }
                )
                continue
            region, binding = _complete_caption_region(
                region=assignment[0],
                binding=assignment[1],
                candidate_metadata=candidate.metadata,
                paper_text_stream=paper_text_stream,
                caption_label_line_ids=caption_label_line_ids,
            )
            numeric_table_number = (
                int(region.table_number)
                if region.table_number.isdigit()
                else candidate.metadata.get("table_number")
            )
            signals = candidate.metadata.get("signals")
            updated_signals = (
                {
                    **signals,
                    "caption_match": True,
                    "table_1_match": numeric_table_number == 1,
                    "caption_table_number": numeric_table_number,
                    "caption_is_continuation": region.mention_kind == "continuation_label",
                }
                if isinstance(signals, dict)
                else None
            )
            result[result_index] = candidate.model_copy(
                update={
                    "caption": region.text,
                    "metadata": {
                        **candidate.metadata,
                        "caption_source": "paper_text_stream_geometry",
                        "caption_region": region.model_dump(mode="json"),
                        "caption_binding": binding.model_dump(mode="json"),
                        "caption_detection_space": "paper_text_orientation_group",
                        "table_number": numeric_table_number,
                        "is_continuation": region.mention_kind == "continuation_label",
                        "continuation_of_table_number": (
                            numeric_table_number
                            if region.mention_kind == "continuation_label"
                            else None
                        ),
                        **({"signals": updated_signals} if updated_signals is not None else {}),
                    },
                }
            )
    return result


def _bibliography_evidence_masks_by_page(
    bibliography_entries: Sequence[BibliographyEntry] | None,
    paper_text_stream: PaperTextStream | None,
) -> dict[int, BibliographyEvidenceMask]:
    """Build page-local masks from bibliography-owned source lines and entry bboxes."""
    if not bibliography_entries:
        return {}
    line_by_id = {
        line.line_id: line
        for line in (paper_text_stream.lines if paper_text_stream is not None else [])
    }
    source_line_ids_by_page: dict[int, set[str]] = {}
    source_line_keys_by_page: dict[int, set[tuple[int, int]]] = {}
    line_regions_by_page: dict[int, list[tuple[float, float, float, float]]] = {}
    entry_regions_by_page: dict[int, list[tuple[float, float, float, float]]] = {}
    for entry in bibliography_entries:
        entry_pages = [int(page_num) for page_num in entry.page_nums if page_num is not None]
        entry_bbox = _as_bbox(entry.bbox)
        for source_line_id in entry.source_line_ids:
            line = line_by_id.get(source_line_id)
            if line is None:
                continue
            page_num = int(line.page_num)
            source_line_ids_by_page.setdefault(page_num, set()).add(source_line_id)
            line_regions_by_page.setdefault(page_num, []).append(line.bbox)
            if line.block_index is not None and line.line_index is not None:
                source_line_keys_by_page.setdefault(page_num, set()).add((line.block_index, line.line_index))
        if entry_bbox is not None:
            for page_num in entry_pages:
                entry_regions_by_page.setdefault(page_num, []).append(entry_bbox)

    page_nums = (
        set(source_line_ids_by_page)
        | set(source_line_keys_by_page)
        | set(line_regions_by_page)
        | set(entry_regions_by_page)
    )
    masks: dict[int, BibliographyEvidenceMask] = {}
    for page_num in sorted(page_nums):
        masks[page_num] = BibliographyEvidenceMask(
            page_num=page_num,
            source_line_ids=source_line_ids_by_page.get(page_num, set()),
            source_line_keys=source_line_keys_by_page.get(page_num, set()),
            line_regions=line_regions_by_page.get(page_num, []),
            entry_regions=entry_regions_by_page.get(page_num, []),
        )
    return masks


def _filter_positioned_items_for_bibliography(
    items: list[dict[str, object]],
    bibliography_mask: BibliographyEvidenceMask | None,
    *,
    item_kind: str,
) -> tuple[list[dict[str, object]], dict[str, object] | None]:
    """Remove positioned text items owned by the bibliography before table detection."""
    if bibliography_mask is None or not items:
        return items, None
    regions = bibliography_mask.line_regions or bibliography_mask.entry_regions
    if not regions and not bibliography_mask.source_line_keys:
        return items, None
    filtered_items: list[dict[str, object]] = []
    removed_by_line_key = 0
    removed_by_region_center = 0
    for item in items:
        remove_item = False
        if item_kind == "char":
            block_index = _optional_int(item.get("block_index"))
            line_index = _optional_int(item.get("line_index"))
            if (
                block_index is not None
                and line_index is not None
                and (block_index, line_index) in bibliography_mask.source_line_keys
            ):
                remove_item = True
                removed_by_line_key += 1
        if not remove_item:
            bbox = _positioned_item_bbox(item)
            if bbox is not None and _bbox_center_inside_any_region(bbox, regions):
                remove_item = True
                removed_by_region_center += 1
        if remove_item:
            continue
        filtered_items.append(item)

    removed_count = len(items) - len(filtered_items)
    if removed_count == 0:
        return items, None
    return filtered_items, {
        "source_artifact": "paper_bibliography.json",
        "page_num": bibliography_mask.page_num,
        "removed_count": removed_count,
        "kept_count": len(filtered_items),
        "source_line_id_count": len(bibliography_mask.source_line_ids),
        "line_region_count": len(bibliography_mask.line_regions),
        "entry_region_count": len(bibliography_mask.entry_regions),
        "removed_by_source_line_key": removed_by_line_key,
        "removed_by_region_center": removed_by_region_center,
    }


def _positioned_item_bbox(item: dict[str, object]) -> tuple[float, float, float, float] | None:
    try:
        return (
            float(item["x0"]),
            float(item["top"]),
            float(item["x1"]),
            float(item["bottom"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _bbox_center_inside_any_region(
    bbox: tuple[float, float, float, float],
    regions: Sequence[tuple[float, float, float, float]],
) -> bool:
    if not regions:
        return False
    center_x = (bbox[0] + bbox[2]) / 2.0
    center_y = (bbox[1] + bbox[3]) / 2.0
    return any(
        left <= center_x <= right and top <= center_y <= bottom
        for left, top, right, bottom in regions
    )


def _optional_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class PyMuPDFExtractor(BaseExtractor):
    """Extract raw table grids from shared PyMuPDF positioned evidence."""

    backend_name = "pymupdf"

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
        paper_positioned_document: PaperPositionedDocument | None = None,
        paper_table_mentions: Sequence[PaperTableMention] | None = None,
        paper_text_stream: PaperTextStream | None = None,
        bibliography_entries: Sequence[BibliographyEntry] | None = None,
    ) -> list[ProvisionalExtractedTable]:
        """Extract and rank raw table candidates from a PDF."""
        try:
            positioned_document = paper_positioned_document or build_paper_positioned_document(pdf_path)
            candidates = self._detect_table_candidates(
                pdf_path,
                paper_page_furniture=paper_page_furniture,
                paper_positioned_document=positioned_document,
                paper_table_mentions=paper_table_mentions,
                paper_text_stream=paper_text_stream,
                bibliography_entries=bibliography_entries,
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
        selected_candidates = _apply_complete_caption_bindings(
            selected_candidates,
            paper_text_stream=paper_text_stream,
            paper_table_mentions=paper_table_mentions,
        )

        pages_by_num = {page.page_num: page for page in positioned_document.pages}
        bibliography_masks_by_page = _bibliography_evidence_masks_by_page(
            bibliography_entries,
            paper_text_stream,
        )
        filtered_items_by_page: dict[int, tuple[list[dict[str, object]], list[dict[str, object]]]] = {}
        for page_num in {candidate.page_num for candidate in selected_candidates}:
            positioned_page = pages_by_num.get(page_num)
            if positioned_page is None:
                continue
            page_words, _ = filter_positioned_items_for_page_furniture(
                _positioned_page_words(positioned_page),
                paper_page_furniture,
                page_num=page_num,
            )
            page_chars, _ = filter_positioned_items_for_page_furniture(
                _positioned_page_chars(positioned_page),
                paper_page_furniture,
                page_num=page_num,
            )
            bibliography_mask = bibliography_masks_by_page.get(page_num)
            page_words, _ = _filter_positioned_items_for_bibliography(
                page_words,
                bibliography_mask,
                item_kind="word",
            )
            page_chars, _ = _filter_positioned_items_for_bibliography(
                page_chars,
                bibliography_mask,
                item_kind="char",
            )
            filtered_items_by_page[page_num] = (page_words, page_chars)

        text_pages_by_num = {
            page.page_num: page
            for page in (paper_text_stream.pages if paper_text_stream is not None else [])
        }
        candidates_with_positioned_evidence: list[DetectedTableCandidate] = []
        for candidate in selected_candidates:
            positioned_page = pages_by_num.get(candidate.page_num)
            text_page = text_pages_by_num.get(candidate.page_num)
            caption_region = candidate.metadata.get("caption_region")
            caption_region_values = caption_region if isinstance(caption_region, dict) else {}
            caption_bbox = _as_bbox(caption_region_values.get("bbox"))
            orientation_group_id = str(
                caption_region_values.get("orientation_group_id") or ""
            ) or None
            rotation_direction = str(candidate.metadata.get("rotation_direction") or "")
            if rotation_direction not in {"vertical_text_up", "vertical_text_down"}:
                rotation_direction = "upright"
            orientation_group = None
            if text_page is not None:
                orientation_group = next(
                    (
                        group
                        for group in text_page.orientation_groups
                        if (
                            orientation_group_id is not None
                            and group.group_id == orientation_group_id
                        )
                        or (
                            orientation_group_id is None
                            and group.orientation == rotation_direction
                        )
                    ),
                    None,
                )
            if orientation_group is not None:
                orientation_group_id = orientation_group.group_id
            transform_source_bbox = _as_bbox(
                candidate.metadata.get("geometry_transform_source_bbox")
            )
            evidence_bbox = (
                candidate.bbox
                if candidate.metadata.get("strong_ruled_geometry") is True
                and candidate.bbox is not None
                else transform_source_bbox or candidate.bbox
            )
            canonical_transform_source_bbox = (
                orientation_group.source_bbox
                if orientation_group is not None and rotation_direction != "upright"
                else (
                    (0.0, 0.0, positioned_page.page_width, positioned_page.page_height)
                    if positioned_page is not None
                    else evidence_bbox
                )
            )
            positioned_evidence = _table_local_positioned_evidence(
                positioned_page,
                candidate.page_num,
                evidence_bbox,
                *filtered_items_by_page.get(candidate.page_num, ([], [])),
                candidate_bbox=candidate.bbox,
                caption_bbox=caption_bbox,
                canonical_transform_source_bbox=canonical_transform_source_bbox,
                orientation_group_id=orientation_group_id,
                rotation_direction=rotation_direction,
                text_filter_artifacts=[
                    artifact
                    for artifact, was_applied in (
                        ("paper_page_furniture.json", paper_page_furniture is not None),
                        (
                            "paper_bibliography.json",
                            candidate.page_num in bibliography_masks_by_page,
                        ),
                    )
                    if was_applied
                ],
            )
            candidates_with_positioned_evidence.append(
                candidate.model_copy(
                    update={
                        "metadata": {
                            **candidate.metadata,
                            "table_positioned_evidence": positioned_evidence.model_dump(
                                mode="json"
                            ),
                        }
                    }
                )
            )
        selected_candidates = candidates_with_positioned_evidence

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
        paper_positioned_document: PaperPositionedDocument | None = None,
        paper_table_mentions: Sequence[PaperTableMention] | None = None,
        paper_text_stream: PaperTextStream | None = None,
        bibliography_entries: Sequence[BibliographyEntry] | None = None,
    ) -> list[DetectedTableCandidate]:
        positioned_document = paper_positioned_document or build_paper_positioned_document(pdf_path)
        positioned_pages_by_num = {
            page.page_num: page
            for page in positioned_document.pages
        }
        text_pages_by_num = {
            page.page_num: page
            for page in (paper_text_stream.pages if paper_text_stream is not None else [])
        }
        text_lines_by_page: dict[int, list[PaperTextLine]] = {}
        for line in paper_text_stream.lines if paper_text_stream is not None else []:
            text_lines_by_page.setdefault(line.page_num, []).append(line)
        candidates: list[DetectedTableCandidate] = []
        try:
            bibliography_masks_by_page = _bibliography_evidence_masks_by_page(
                bibliography_entries,
                paper_text_stream,
            )
            abstract_intervals = _abstract_intervals_by_page(positioned_document)
            for page_num in sorted(positioned_pages_by_num):
                positioned_page = positioned_pages_by_num[page_num]
                page_text = positioned_page.text
                page_words, page_word_mask_metadata = filter_positioned_items_for_page_furniture(
                    _positioned_page_words(positioned_page),
                    paper_page_furniture,
                    page_num=page_num,
                )
                page_chars, page_char_mask_metadata = filter_positioned_items_for_page_furniture(
                    _positioned_page_chars(positioned_page),
                    paper_page_furniture,
                    page_num=page_num,
                )
                bibliography_mask = bibliography_masks_by_page.get(page_num)
                page_words, page_word_bibliography_mask_metadata = _filter_positioned_items_for_bibliography(
                    page_words,
                    bibliography_mask,
                    item_kind="word",
                )
                page_chars, page_char_bibliography_mask_metadata = _filter_positioned_items_for_bibliography(
                    page_chars,
                    bibliography_mask,
                    item_kind="char",
                )
                page_rule_segments = list(positioned_page.rule_segments)
                removed_rule_segments = 0
                removed_rule_cluster_ids: set[str] = set()
                if paper_page_furniture is not None:
                    rule_regions = [
                        region
                        for region in paper_page_furniture.ignored_rule_regions
                        if region.page_num == page_num
                    ]
                    kept_rule_segments: list[tuple[float, float, float, float]] = []
                    for segment in page_rule_segments:
                        left = min(float(segment[0]), float(segment[2]))
                        right = max(float(segment[0]), float(segment[2]))
                        top = min(float(segment[1]), float(segment[3]))
                        bottom = max(float(segment[1]), float(segment[3]))
                        width = right - left
                        matched_region = None
                        if width > bottom - top:
                            center_y = (top + bottom) / 2.0
                            for region in rule_regions:
                                region_left, region_top, region_right, region_bottom = region.bbox
                                overlap = min(right, region_right) - max(left, region_left)
                                if (
                                    abs(center_y - (region_top + region_bottom) / 2.0) <= 2.0
                                    and overlap >= min(width, region_right - region_left) * 0.8
                                ):
                                    matched_region = region
                                    break
                        if matched_region is None:
                            kept_rule_segments.append(segment)
                            continue
                        removed_rule_segments += 1
                        removed_rule_cluster_ids.add(matched_region.rule_cluster_id)
                    page_rule_segments = kept_rule_segments
                text_page = text_pages_by_num.get(page_num)
                orientation_groups = list(text_page.orientation_groups) if text_page is not None else []
                if not orientation_groups:
                    orientation_groups = [
                        PaperTextOrientationGroup(
                            group_id=f"page-{page_num}-orientation-upright",
                            orientation="upright",
                            source_bbox=(
                                0.0,
                                0.0,
                                positioned_page.page_width,
                                positioned_page.page_height,
                            ),
                            canonical_width=positioned_page.page_width,
                            canonical_height=positioned_page.page_height,
                            line_count=max(1, len(positioned_page.lines)),
                            column_count=1,
                            column_bands=[(0.0, positioned_page.page_width)],
                        )
                    ]
                page_candidates: list[DetectedTableCandidate] = []
                page_lines = text_lines_by_page.get(page_num, [])
                line_by_id = {line.line_id: line for line in page_lines}
                for group in orientation_groups:
                    group_lines = [
                        line for line in page_lines if line.orientation_group_id == group.group_id
                    ]
                    group_line_keys = {
                        (line.block_index, line.line_index)
                        for line in group_lines
                        if line.block_index is not None and line.line_index is not None
                    }
                    group_words = [
                        word
                        for word in page_words
                        if not group_line_keys
                        or (word.get("block_index"), word.get("line_index")) in group_line_keys
                    ]
                    group_chars = [
                        char
                        for char in page_chars
                        if not group_line_keys
                        or (char.get("block_index"), char.get("line_index")) in group_line_keys
                    ]
                    if not group_words:
                        continue
                    transformed_words, transformed_chars, transformed_rules, _ = (
                        normalize_positioned_geometry_for_rotation(
                            words=group_words,
                            chars=group_chars,
                            rule_segments=page_rule_segments,
                            bbox=group.source_bbox,
                            rotation_direction=group.orientation,
                        )
                    )
                    group_line_ids = {line.line_id for line in group_lines}
                    transformed_mentions = [
                        mention.model_copy(
                            update={
                                "source_line_bbox": line_by_id[mention.source_line_id].canonical_bbox
                            }
                        )
                        for mention in paper_table_mentions or []
                        if mention.page_num == page_num
                        and mention.source_line_id in group_line_ids
                        and line_by_id[mention.source_line_id].canonical_bbox is not None
                    ]
                    group_text = "\n".join(line.text for line in group_lines) or page_text
                    if group.orientation == "upright":
                        text_layout_candidates = _build_upright_rule_span_candidates(
                            page_num=page_num,
                            page_text=group_text,
                            words=transformed_words,
                            chars=transformed_chars,
                            rule_segments=transformed_rules,
                            paper_table_mentions=transformed_mentions,
                        )
                        continuation_candidates = _build_cross_page_continuation_candidates(
                            page_num=page_num,
                            page_text=group_text,
                            words=transformed_words,
                            chars=transformed_chars,
                            rule_segments=transformed_rules,
                            prior_candidates=candidates,
                        )
                        for continuation_candidate in continuation_candidates:
                            if any(
                                candidate.bbox is not None
                                and continuation_candidate.bbox is not None
                                and (
                                    bbox_overlap_fraction(
                                        continuation_candidate.bbox,
                                        candidate.bbox,
                                    )
                                    >= 0.8
                                    or bbox_overlap_fraction(
                                        candidate.bbox,
                                        continuation_candidate.bbox,
                                    )
                                    >= 0.8
                                )
                                for candidate in text_layout_candidates
                            ):
                                continue
                            text_layout_candidates.append(continuation_candidate)
                    else:
                        text_layout_candidates = []
                    if not text_layout_candidates:
                        text_layout_candidates = build_text_layout_candidates(
                            page_num=page_num,
                            page_text=group_text,
                            words=transformed_words,
                            chars=transformed_chars,
                            rule_segments=transformed_rules,
                            layout_source="pymupdf_text_positions",
                            paper_page_furniture=None,
                            paper_table_mentions=transformed_mentions,
                            allow_uncaptioned_orientation_group=(
                                group.orientation != "upright"
                            ),
                        )
                    for candidate in text_layout_candidates:
                        source_candidate_bbox = candidate.bbox
                        if candidate.bbox is not None and group.orientation != "upright":
                            canonical_left, canonical_top, canonical_right, canonical_bottom = candidate.bbox
                            source_left, source_top, source_right, source_bottom = group.source_bbox
                            if group.orientation == "vertical_text_up":
                                source_candidate_bbox = (
                                    source_left + canonical_top,
                                    source_bottom - canonical_right,
                                    source_left + canonical_bottom,
                                    source_bottom - canonical_left,
                                )
                            else:
                                source_candidate_bbox = (
                                    source_right - canonical_bottom,
                                    source_top + canonical_left,
                                    source_right - canonical_top,
                                    source_top + canonical_right,
                                )
                        page_candidates.append(
                            candidate.model_copy(
                                update={
                                    "bbox": source_candidate_bbox,
                                    "metadata": {
                                        **candidate.metadata,
                                        "geometry_coordinate_frame": (
                                            "paper_text_orientation_group"
                                            if group.orientation != "upright"
                                            else "page"
                                        ),
                                        "geometry_transform_source_bbox": group.source_bbox,
                                        "geometry_transform_applied": group.orientation != "upright",
                                        "table_orientation": (
                                            "rotated" if group.orientation != "upright" else "upright"
                                        ),
                                        "rotation_direction": group.orientation,
                                        "orientation_group_id": group.group_id,
                                    },
                                }
                            )
                        )
                page_candidates = [
                    candidate.model_copy(update={"table_index": table_index})
                    for table_index, candidate in enumerate(
                        sorted(
                            page_candidates,
                            key=lambda candidate: (
                                float(candidate.bbox[1]) if candidate.bbox is not None else 0.0,
                                float(candidate.bbox[0]) if candidate.bbox is not None else 0.0,
                            ),
                        )
                    )
                ]
                for candidate in page_candidates:
                    if _is_abstract_owned_candidate(
                        candidate,
                        abstract_intervals.get(page_num),
                    ):
                        continue
                    bibliography_mask_metadata = {
                        key: value
                        for key, value in {
                            "word_items": page_word_bibliography_mask_metadata,
                            "char_items": page_char_bibliography_mask_metadata,
                        }.items()
                        if value is not None
                    }
                    candidates.append(
                        candidate.model_copy(
                            update={
                                "metadata": {
                                    **candidate.metadata,
                                    "primary_representation": "positioned_geometry",
                                    "extractor_used": self.backend_name,
                                    "fallback_used": False,
                                    "page_furniture_mask": {
                                        key: value
                                        for key, value in {
                                            "word_items": page_word_mask_metadata,
                                            "char_items": page_char_mask_metadata,
                                            "rule_segments": (
                                                {
                                                    "source_artifact": "paper_page_furniture.json",
                                                    "removed_count": removed_rule_segments,
                                                    "removed_rule_cluster_ids": sorted(
                                                        removed_rule_cluster_ids
                                                    ),
                                                }
                                                if removed_rule_segments
                                                else None
                                            ),
                                        }.items()
                                        if value is not None
                                    },
                                    "bibliography_evidence_mask": bibliography_mask_metadata or None,
                                }
                            }
                        )
                    )
        except Exception:
            return []
        return candidates

    def _build_extracted_table(
        self,
        pdf_path: str,
        candidate: DetectedTableCandidate,
    ) -> ProvisionalExtractedTable:
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
        return ProvisionalExtractedTable(
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

def _horizontal_rule_spans(
    rule_segments: list[tuple[float, float, float, float]],
) -> list[tuple[float, float, float]]:
    """Return continuous horizontal coverage spans without changing source rules."""
    horizontal_segments = sorted(
        (
            ((float(y0) + float(y1)) / 2.0, min(float(x0), float(x1)), max(float(x0), float(x1)))
            for x0, y0, x1, y1 in rule_segments
            if abs(float(y1) - float(y0)) <= 1.5 and abs(float(x1) - float(x0)) >= 4.0
        ),
        key=lambda item: (item[0], item[1]),
    )
    rule_buckets: list[list[tuple[float, float, float]]] = []
    for segment in horizontal_segments:
        if not rule_buckets or abs(segment[0] - rule_buckets[-1][0][0]) > 3.0:
            rule_buckets.append([segment])
        else:
            rule_buckets[-1].append(segment)

    rule_spans: list[tuple[float, float, float]] = []
    for bucket in rule_buckets:
        y = sum(segment[0] for segment in bucket) / len(bucket)
        continuous_spans: list[list[float]] = []
        for _, left, right in sorted(bucket, key=lambda item: item[1]):
            if not continuous_spans or left > continuous_spans[-1][1] + 0.51:
                continuous_spans.append([left, right])
            else:
                continuous_spans[-1][1] = max(continuous_spans[-1][1], right)
        rule_spans.extend(
            (y, left, right)
            for left, right in continuous_spans
            if right - left >= 40.0
        )
    return rule_spans


def _connected_rule_grid_regions(
    rule_segments: list[tuple[float, float, float, float]],
) -> list[tuple[float, float, float, float]]:
    """Return bboxes of rule components containing closed cell geometry."""
    normalized: dict[tuple[str, float, float, float], tuple[str, float, float, float]] = {}
    for x0, y0, x1, y1 in rule_segments:
        if abs(float(y1) - float(y0)) <= 1.5 and abs(float(x1) - float(x0)) >= 4.0:
            segment = (
                "h",
                min(float(x0), float(x1)),
                (float(y0) + float(y1)) / 2.0,
                max(float(x0), float(x1)),
            )
        elif abs(float(x1) - float(x0)) <= 1.5 and abs(float(y1) - float(y0)) >= 4.0:
            segment = (
                "v",
                (float(x0) + float(x1)) / 2.0,
                min(float(y0), float(y1)),
                max(float(y0), float(y1)),
            )
        else:
            continue
        key = (segment[0], round(segment[1], 1), round(segment[2], 1), round(segment[3], 1))
        normalized[key] = segment

    segments = list(normalized.values())
    parents = list(range(len(segments)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left_index: int, right_index: int) -> None:
        left_root = find(left_index)
        right_root = find(right_index)
        if left_root != right_root:
            parents[right_root] = left_root

    horizontal = [(index, segment) for index, segment in enumerate(segments) if segment[0] == "h"]
    vertical = [(index, segment) for index, segment in enumerate(segments) if segment[0] == "v"]
    for position, (left_index, left_segment) in enumerate(horizontal):
        for right_index, right_segment in horizontal[position + 1 :]:
            if (
                abs(left_segment[2] - right_segment[2]) <= 2.0
                and left_segment[1] <= right_segment[3] + 2.0
                and right_segment[1] <= left_segment[3] + 2.0
            ):
                union(left_index, right_index)
    for position, (left_index, left_segment) in enumerate(vertical):
        for right_index, right_segment in vertical[position + 1 :]:
            if (
                abs(left_segment[1] - right_segment[1]) <= 2.0
                and left_segment[2] <= right_segment[3] + 2.0
                and right_segment[2] <= left_segment[3] + 2.0
            ):
                union(left_index, right_index)
    for horizontal_index, horizontal_segment in horizontal:
        _, left, y, right = horizontal_segment
        for vertical_index, vertical_segment in vertical:
            _, x, top, bottom = vertical_segment
            if left - 2.0 <= x <= right + 2.0 and top - 2.0 <= y <= bottom + 2.0:
                union(horizontal_index, vertical_index)

    components: dict[int, list[tuple[str, float, float, float]]] = {}
    for index, segment in enumerate(segments):
        components.setdefault(find(index), []).append(segment)

    regions: list[tuple[float, float, float, float]] = []
    for component in components.values():
        horizontal_component = [segment for segment in component if segment[0] == "h"]
        vertical_component = [segment for segment in component if segment[0] == "v"]
        if len(horizontal_component) < 2 or len(vertical_component) < 2:
            continue
        left = min(
            [segment[1] for segment in horizontal_component]
            + [segment[1] for segment in vertical_component]
        )
        right = max(
            [segment[3] for segment in horizontal_component]
            + [segment[1] for segment in vertical_component]
        )
        top = min(
            [segment[2] for segment in horizontal_component]
            + [segment[2] for segment in vertical_component]
        )
        bottom = max(
            [segment[2] for segment in horizontal_component]
            + [segment[3] for segment in vertical_component]
        )
        edge_tolerance = 2.0
        top_edges = sorted(
            (segment[1], segment[3])
            for segment in horizontal_component
            if abs(segment[2] - top) <= edge_tolerance
        )
        bottom_edges = sorted(
            (segment[1], segment[3])
            for segment in horizontal_component
            if abs(segment[2] - bottom) <= edge_tolerance
        )
        left_edges = sorted(
            (segment[2], segment[3])
            for segment in vertical_component
            if abs(segment[1] - left) <= edge_tolerance
        )
        right_edges = sorted(
            (segment[2], segment[3])
            for segment in vertical_component
            if abs(segment[1] - right) <= edge_tolerance
        )
        enclosed = True
        for edges, start, end in (
            (top_edges, left, right),
            (bottom_edges, left, right),
            (left_edges, top, bottom),
            (right_edges, top, bottom),
        ):
            covered_to = start
            for edge_start, edge_end in edges:
                if edge_start > covered_to + edge_tolerance:
                    break
                covered_to = max(covered_to, edge_end)
            if covered_to < end - edge_tolerance:
                enclosed = False
                break
        if not enclosed:
            continue
        regions.append((left, top, right, bottom))
    return sorted(regions, key=lambda region: (region[1], region[0]))


def _build_upright_rule_span_candidates(
    *,
    page_num: int,
    page_text: str,
    words: list[dict[str, object]],
    chars: list[dict[str, object]],
    rule_segments: list[tuple[float, float, float, float]],
    paper_table_mentions: Sequence[PaperTableMention] | None,
) -> list[DetectedTableCandidate]:
    """Build upright candidates from captions or connected cell-rule geometry."""
    if not words or not rule_segments:
        return []
    rule_spans = _horizontal_rule_spans(rule_segments)

    caption_mentions = sorted(
        (
            mention
            for mention in paper_table_mentions
            if mention.page_num == page_num and mention.is_caption_candidate
        ),
        key=lambda mention: (mention.source_line_bbox[1], mention.source_line_bbox[0]),
    )

    candidates: list[DetectedTableCandidate] = []
    for mention in caption_mentions:
        caption_left, caption_top, caption_right, caption_bottom = (
            float(value) for value in mention.source_line_bbox
        )

        related_spans = [
            span
            for span in rule_spans
            if min(caption_right, span[2]) > max(caption_left, span[1])
            or span[1] - 8.0 <= caption_left <= span[2] + 8.0
        ]
        selected_region: tuple[float, float, float, float] | None = None
        for start_y, left, right in related_spans:
            overlapping_captions = [
                other
                for other in caption_mentions
                if other.mention_id != mention.mention_id
                and min(right, float(other.source_line_bbox[2]))
                > max(left, float(other.source_line_bbox[0]))
            ]
            next_caption_top = min(
                (
                    float(other.source_line_bbox[1])
                    for other in overlapping_captions
                    if float(other.source_line_bbox[1]) > caption_top + 2.0
                ),
                default=float("inf"),
            )
            if not caption_bottom - 2.0 <= start_y < next_caption_top - 2.0:
                continue
            edge_tolerance = max(3.0, min(8.0, (right - left) * 0.02))
            matching_rows = [
                span
                for span in rule_spans
                if start_y <= span[0] < next_caption_top - 2.0
                and abs(span[1] - left) <= edge_tolerance
                and abs(span[2] - right) <= edge_tolerance
            ]
            if len(matching_rows) >= 2:
                selected_region = (
                    left,
                    caption_top,
                    right,
                    max(span[0] for span in matching_rows),
                )
                break

        if selected_region is None:
            for end_y, left, right in reversed(related_spans):
                overlapping_captions = [
                    other
                    for other in caption_mentions
                    if other.mention_id != mention.mention_id
                    and min(right, float(other.source_line_bbox[2]))
                    > max(left, float(other.source_line_bbox[0]))
                ]
                previous_caption_bottom = max(
                    (
                        float(other.source_line_bbox[3])
                        for other in overlapping_captions
                        if float(other.source_line_bbox[1]) < caption_top - 2.0
                    ),
                    default=float("-inf"),
                )
                if not previous_caption_bottom + 2.0 < end_y <= caption_top + 2.0:
                    continue
                edge_tolerance = max(3.0, min(8.0, (right - left) * 0.02))
                matching_rows = [
                    span
                    for span in rule_spans
                    if previous_caption_bottom + 2.0 < span[0] <= end_y
                    and abs(span[1] - left) <= edge_tolerance
                    and abs(span[2] - right) <= edge_tolerance
                ]
                if len(matching_rows) >= 2:
                    selected_region = (
                        left,
                        min(span[0] for span in matching_rows),
                        right,
                        caption_bottom,
                    )
                    break

        if selected_region is None:
            continue
        left, top, right, bottom = selected_region
        region_words = [
            word
            for word in words
            if left - 2.0 <= (float(word["x0"]) + float(word["x1"])) / 2.0 <= right + 2.0
            and top - 2.0 <= (float(word["top"]) + float(word["bottom"])) / 2.0 <= bottom + 2.0
        ]
        if not region_words:
            continue
        region_chars = [
            char
            for char in chars
            if left - 2.0 <= (float(char["x0"]) + float(char["x1"])) / 2.0 <= right + 2.0
            and top - 2.0 <= (float(char["top"]) + float(char["bottom"])) / 2.0 <= bottom + 2.0
        ]
        region_rules = [
            segment
            for segment in rule_segments
            if min(float(segment[0]), float(segment[2])) < right + 2.0
            and max(float(segment[0]), float(segment[2])) > left - 2.0
            and (float(segment[1]) + float(segment[3])) / 2.0 >= top - 2.0
            and (float(segment[1]) + float(segment[3])) / 2.0 <= bottom + 2.0
        ]
        for candidate in build_text_layout_candidates(
            page_num=page_num,
            page_text=page_text,
            words=region_words,
            chars=region_chars,
            rule_segments=region_rules,
            layout_source="pymupdf_text_positions",
            paper_page_furniture=None,
            paper_table_mentions=[mention],
            candidate_region_bbox=selected_region,
        ):
            candidates.append(
                candidate.model_copy(
                    update={
                        "metadata": {
                            **candidate.metadata,
                            "candidate_region_source": "caption_and_rule_geometry",
                            "candidate_rule_span": [left, top, right, bottom],
                        }
                    }
                )
            )

    for left, top, right, bottom in _connected_rule_grid_regions(rule_segments):
        region_bbox = (left, top, right, bottom)
        if any(
            candidate.bbox is not None
            and (
                bbox_overlap_fraction(region_bbox, candidate.bbox) >= 0.8
                or bbox_overlap_fraction(candidate.bbox, region_bbox) >= 0.8
            )
            for candidate in candidates
        ):
            continue
        region_words = [
            word
            for word in words
            if left - 2.0 <= (float(word["x0"]) + float(word["x1"])) / 2.0 <= right + 2.0
            and top - 2.0 <= (float(word["top"]) + float(word["bottom"])) / 2.0 <= bottom + 2.0
        ]
        if not region_words:
            continue
        region_chars = [
            char
            for char in chars
            if left - 2.0 <= (float(char["x0"]) + float(char["x1"])) / 2.0 <= right + 2.0
            and top - 2.0 <= (float(char["top"]) + float(char["bottom"])) / 2.0 <= bottom + 2.0
        ]
        region_rules = [
            segment
            for segment in rule_segments
            if min(float(segment[0]), float(segment[2])) <= right + 2.0
            and max(float(segment[0]), float(segment[2])) >= left - 2.0
            and min(float(segment[1]), float(segment[3])) <= bottom + 2.0
            and max(float(segment[1]), float(segment[3])) >= top - 2.0
        ]
        for candidate in build_text_layout_candidates(
            page_num=page_num,
            page_text=page_text,
            words=region_words,
            chars=region_chars,
            rule_segments=region_rules,
            layout_source="pymupdf_text_positions",
            paper_page_furniture=None,
            paper_table_mentions=[],
            allow_uncaptioned_orientation_group=True,
        ):
            candidates.append(
                candidate.model_copy(
                    update={
                        "metadata": {
                            **candidate.metadata,
                            "candidate_region_source": "connected_rule_grid",
                            "candidate_rule_component_bbox": [left, top, right, bottom],
                        }
                    }
                )
            )
    return [
        candidate.model_copy(update={"table_index": index})
        for index, candidate in enumerate(
            sorted(
                candidates,
                key=lambda candidate: (
                    float(candidate.bbox[1]) if candidate.bbox is not None else 0.0,
                    float(candidate.bbox[0]) if candidate.bbox is not None else 0.0,
                    candidate.table_index,
                ),
            )
        )
    ]


def _build_cross_page_continuation_candidates(
    *,
    page_num: int,
    page_text: str,
    words: list[dict[str, object]],
    chars: list[dict[str, object]],
    rule_segments: list[tuple[float, float, float, float]],
    prior_candidates: Sequence[DetectedTableCandidate],
) -> list[DetectedTableCandidate]:
    """Build a top-of-page continuation from prior-page column geometry."""
    eligible_prior = [
        candidate
        for candidate in prior_candidates
        if candidate.page_num == page_num - 1
        and candidate.bbox is not None
        and candidate.metadata.get("table_orientation") != "rotated"
        and isinstance(candidate.metadata.get("value_matrix_column_anchors"), list)
        and len(candidate.metadata["value_matrix_column_anchors"]) >= 2
    ]
    if not eligible_prior or not words or not rule_segments:
        return []
    prior_candidate = max(
        eligible_prior,
        key=lambda candidate: float(candidate.bbox[3]) if candidate.bbox is not None else 0.0,
    )
    prior_bbox = prior_candidate.bbox
    if prior_bbox is None:
        return []
    anchors = sorted(float(value) for value in prior_candidate.metadata["value_matrix_column_anchors"])
    band_edges = [anchors[0] - (anchors[1] - anchors[0]) / 2.0]
    band_edges.extend((left + right) / 2.0 for left, right in zip(anchors, anchors[1:]))
    band_edges.append(anchors[-1] + (anchors[-1] - anchors[-2]) / 2.0)

    lines = build_word_lines(words)
    aligned_value_rows: list[tuple[dict[str, object], float]] = []
    for line in lines:
        supported_words = [
            [
                word
                for word in line["words"]
                if band_edges[index] <= float(word["x0"]) < band_edges[index + 1]
                and any(character.isdigit() for character in str(word["text"]))
            ]
            for index in range(len(anchors))
        ]
        if all(supported_words):
            aligned_value_rows.append(
                (
                    line,
                    max(
                        float(word["bottom"])
                        for band_words in supported_words
                        for word in band_words
                    ),
                )
            )
    if not aligned_value_rows:
        return []

    last_aligned_bottom = max(bottom for _, bottom in aligned_value_rows)
    covering_rules = [
        span
        for span in _horizontal_rule_spans(rule_segments)
        if span[0] >= last_aligned_bottom - 2.0
        and span[1] <= band_edges[0]
        and span[2] >= band_edges[-1]
    ]
    if not covering_rules:
        return []
    bottom = min(span[0] for span in covering_rules)
    left, right = float(prior_bbox[0]), float(prior_bbox[2])
    region_lines = [
        line
        for line in lines
        if float(line["top"]) <= bottom + 2.0
        and any(
            left - 2.0 <= (float(word["x0"]) + float(word["x1"])) / 2.0 <= right + 2.0
            for word in line["words"]
        )
    ]
    if not region_lines:
        return []
    top = min(float(line["top"]) for line in region_lines)
    region_words = [
        word
        for word in words
        if left - 2.0 <= (float(word["x0"]) + float(word["x1"])) / 2.0 <= right + 2.0
        and top - 2.0 <= (float(word["top"]) + float(word["bottom"])) / 2.0 <= bottom + 2.0
    ]
    region_chars = [
        char
        for char in chars
        if left - 2.0 <= (float(char["x0"]) + float(char["x1"])) / 2.0 <= right + 2.0
        and top - 2.0 <= (float(char["top"]) + float(char["bottom"])) / 2.0 <= bottom + 2.0
    ]
    region_rules = [
        segment
        for segment in rule_segments
        if min(float(segment[0]), float(segment[2])) <= right + 2.0
        and max(float(segment[0]), float(segment[2])) >= left - 2.0
        and min(float(segment[1]), float(segment[3])) <= bottom + 2.0
        and max(float(segment[1]), float(segment[3])) >= top - 2.0
    ]
    prior_table_number = prior_candidate.metadata.get("table_number")
    if (
        not isinstance(prior_table_number, int)
        or isinstance(prior_table_number, bool)
        or prior_table_number < 1
    ):
        prior_table_number = None
    return [
        candidate.model_copy(
            update={
                "metadata": {
                    **candidate.metadata,
                    "candidate_region_source": "cross_page_column_geometry",
                    "continuation_source_page": prior_candidate.page_num,
                    "continuation_anchor_count": len(anchors),
                    "continuation_region_bbox": [left, top, right, bottom],
                    "table_number": prior_table_number,
                    "is_continuation": prior_table_number is not None,
                    "continuation_of_table_number": prior_table_number,
                }
            }
        )
        for candidate in build_text_layout_candidates(
            page_num=page_num,
            page_text=page_text,
            words=region_words,
            chars=region_chars,
            rule_segments=region_rules,
            layout_source="pymupdf_text_positions",
            paper_page_furniture=None,
            paper_table_mentions=[],
            allow_uncaptioned_orientation_group=True,
        )
    ]


def _positioned_page_words(page: PaperPositionedPage) -> list[dict[str, object]]:
    """Project positioned-document words into the dict shape used by extraction heuristics."""
    return [
        {**word.model_dump(mode="json"), "source_word_index": word_index}
        for word_index, word in enumerate(page.words)
    ]


def _positioned_page_chars(page: PaperPositionedPage) -> list[dict[str, object]]:
    """Project positioned-document chars into the dict shape used by extraction heuristics."""
    return [char.model_dump(mode="json", exclude_none=True) for char in page.chars]


def _table_local_positioned_evidence(
    page: PaperPositionedPage | None,
    page_num: int,
    bbox: tuple[float, float, float, float] | None,
    filtered_words: list[dict[str, object]],
    filtered_chars: list[dict[str, object]],
    *,
    candidate_bbox: tuple[float, float, float, float] | None,
    caption_bbox: tuple[float, float, float, float] | None,
    canonical_transform_source_bbox: tuple[float, float, float, float] | None,
    orientation_group_id: str | None,
    rotation_direction: str,
    text_filter_artifacts: list[str],
) -> TablePositionedEvidence:
    """Project shared table-local PyMuPDF evidence into one canonical frame."""
    diagnostics: list[str] = []
    if page is None:
        diagnostics.append("missing_positioned_page")
    if bbox is None:
        diagnostics.append("missing_candidate_bbox")
    if canonical_transform_source_bbox is None:
        diagnostics.append("missing_canonical_transform_source_bbox")
    if page is None or bbox is None or canonical_transform_source_bbox is None:
        return TablePositionedEvidence(
            page_num=page_num,
            bbox=bbox,
            candidate_bbox=candidate_bbox,
            caption_bbox=caption_bbox,
            geometry_transform_applied=False,
            orientation_group_id=orientation_group_id,
            text_filter_artifacts=text_filter_artifacts,
            diagnostics=diagnostics,
        )

    geometry_transform_applied = rotation_direction in {
        "vertical_text_up",
        "vertical_text_down",
    }
    structural_scope_bbox = (
        (
            min(bbox[0], caption_bbox[0]),
            min(bbox[1], caption_bbox[1]),
            max(bbox[2], caption_bbox[2]),
            max(bbox[3], caption_bbox[3]),
        )
        if caption_bbox is not None
        else bbox
    )

    def intersects(
        item_bbox: tuple[float, float, float, float],
        scope_bbox: tuple[float, float, float, float] = bbox,
    ) -> bool:
        return not (
            item_bbox[2] < scope_bbox[0]
            or item_bbox[0] > scope_bbox[2]
            or item_bbox[3] < scope_bbox[1]
            or item_bbox[1] > scope_bbox[3]
        )

    table_words = sorted(
        (
            item
            for item in filtered_words
            if (item_bbox := _positioned_item_bbox(item)) is not None
            and intersects(item_bbox)
            and isinstance(item.get("source_word_index"), int)
        ),
        key=lambda item: int(item["source_word_index"]),
    )
    table_chars = sorted(
        (
            item
            for item in filtered_chars
            if (item_bbox := _positioned_item_bbox(item)) is not None
            and intersects(item_bbox)
            and isinstance(item.get("char_index"), int)
        ),
        key=lambda item: int(item["char_index"]),
    )
    retained_line_keys = {
        (int(item["block_index"]), int(item["line_index"]))
        for item in table_chars
        if isinstance(item.get("block_index"), int) and isinstance(item.get("line_index"), int)
    }
    line_ids: list[str] = []
    line_bboxes: list[tuple[float, float, float, float]] = []
    span_references: list[PositionedSpanReference] = []
    span_bboxes: list[tuple[float, float, float, float]] = []
    for line in page.lines:
        if not intersects(line.bbox):
            continue
        if (
            line.block_index is not None
            and line.line_index is not None
            and (line.block_index, line.line_index) not in retained_line_keys
        ):
            continue
        line_ids.append(line.line_id)
        line_bboxes.append(line.bbox)
        for span_index, span in enumerate(line.spans):
            if not intersects(span.bbox):
                continue
            span_references.append(
                PositionedSpanReference(line_id=line.line_id, span_index=span_index)
            )
            span_bboxes.append(span.bbox)

    def segment_intersects(segment: tuple[float, float, float, float]) -> bool:
        x0, y0, x1, y1 = segment
        return intersects(
            (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)),
            structural_scope_bbox,
        )

    rule_segment_indices = [
        index
        for index, segment in enumerate(page.rule_segments)
        if segment_intersects(segment)
    ]
    stroked_rule_segment_indices = [
        index
        for index, segment in enumerate(page.stroked_rule_segments)
        if segment_intersects(segment)
    ]
    source_rule_segments = [page.rule_segments[index] for index in rule_segment_indices]
    source_stroked_rule_segments = [
        page.stroked_rule_segments[index]
        for index in stroked_rule_segment_indices
    ]

    def canonical_bbox(
        source_bbox: tuple[float, float, float, float] | None,
    ) -> tuple[float, float, float, float] | None:
        if source_bbox is None:
            return None
        return normalize_bbox_for_rotation(
            source_bbox,
            source_bbox=canonical_transform_source_bbox,
            rotation_direction=rotation_direction,
        )

    _, _, canonical_rule_segments, _ = normalize_positioned_geometry_for_rotation(
        words=[],
        chars=[],
        rule_segments=source_rule_segments,
        bbox=canonical_transform_source_bbox,
        rotation_direction=rotation_direction,
    )
    _, _, canonical_stroked_rule_segments, _ = normalize_positioned_geometry_for_rotation(
        words=[],
        chars=[],
        rule_segments=source_stroked_rule_segments,
        bbox=canonical_transform_source_bbox,
        rotation_direction=rotation_direction,
    )
    if rotation_direction == "vertical_text_up":
        affine_matrix = (
            0.0,
            1.0,
            -1.0,
            0.0,
            canonical_transform_source_bbox[3],
            -canonical_transform_source_bbox[0],
        )
    elif rotation_direction == "vertical_text_down":
        affine_matrix = (
            0.0,
            -1.0,
            1.0,
            0.0,
            -canonical_transform_source_bbox[1],
            canonical_transform_source_bbox[2],
        )
    else:
        affine_matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    canonical_line_bboxes = [canonical_bbox(item) for item in line_bboxes]
    canonical_span_bboxes = [canonical_bbox(item) for item in span_bboxes]
    canonical_word_bboxes = [
        canonical_bbox(_positioned_item_bbox(item))
        for item in table_words
    ]
    canonical_char_bboxes = [
        canonical_bbox(_positioned_item_bbox(item))
        for item in table_chars
    ]
    if any(item is None for item in canonical_word_bboxes + canonical_char_bboxes):
        diagnostics.append("canonical_item_bbox_missing")

    return TablePositionedEvidence(
        page_num=page.page_num,
        bbox=bbox,
        candidate_bbox=candidate_bbox,
        caption_bbox=caption_bbox,
        structural_scope_bbox=structural_scope_bbox,
        canonical_bbox=canonical_bbox(bbox),
        canonical_candidate_bbox=canonical_bbox(candidate_bbox),
        canonical_caption_bbox=canonical_bbox(caption_bbox),
        canonical_structural_scope_bbox=canonical_bbox(structural_scope_bbox),
        canonical_transform=TableCanonicalTransform(
            source_bbox=canonical_transform_source_bbox,
            affine_matrix=affine_matrix,
            rotation_direction=(
                rotation_direction
                if rotation_direction in {"vertical_text_up", "vertical_text_down"}
                else "upright"
            ),
        ),
        geometry_transform_applied=geometry_transform_applied,
        rotation_direction=(rotation_direction if geometry_transform_applied else None),
        orientation_group_id=orientation_group_id,
        line_ids=line_ids,
        canonical_line_bboxes=[item for item in canonical_line_bboxes if item is not None],
        span_references=span_references,
        canonical_span_bboxes=[item for item in canonical_span_bboxes if item is not None],
        word_indices=[int(item["source_word_index"]) for item in table_words],
        canonical_word_bboxes=[item for item in canonical_word_bboxes if item is not None],
        char_indices=[int(item["char_index"]) for item in table_chars],
        canonical_char_bboxes=[item for item in canonical_char_bboxes if item is not None],
        rule_segment_indices=rule_segment_indices,
        canonical_rule_segments=canonical_rule_segments,
        stroked_rule_segment_indices=stroked_rule_segment_indices,
        canonical_stroked_rule_segments=canonical_stroked_rule_segments,
        text_filter_artifacts=text_filter_artifacts,
        diagnostics=diagnostics,
    )


def _abstract_intervals_by_page(
    positioned_document: PaperPositionedDocument | None,
) -> dict[int, tuple[float, float]]:
    """Return page y-intervals between the abstract heading and introduction heading."""
    if positioned_document is None:
        return {}

    abstract_location: tuple[int, float] | None = None
    introduction_location: tuple[int, float] | None = None
    page_bottoms = {
        page.page_num: page.page_height
        for page in positioned_document.pages
    }

    for page in positioned_document.pages:
        page_num = page.page_num
        try:
            lines = build_word_lines(_positioned_page_words(page))
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


def _is_abstract_owned_candidate(
    candidate: DetectedTableCandidate,
    abstract_interval: tuple[float, float] | None,
) -> bool:
    """Return whether candidate geometry overlaps the paper's abstract section."""
    if abstract_interval is None or candidate.bbox is None:
        return False
    candidate_top = float(candidate.bbox[1])
    candidate_bottom = float(candidate.bbox[3])
    interval_top, interval_bottom = abstract_interval
    overlap = min(candidate_bottom, interval_bottom) - max(candidate_top, interval_top)
    return overlap > 0.0


def _as_bbox(value: Any) -> tuple[float, float, float, float] | None:
    """Convert a raw bbox-like value to a tuple."""
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    return tuple(float(part) for part in value)


def _coerce_cell_bboxes(table_cells: list[Any]) -> list[list[tuple[float, float, float, float] | None]]:
    """Normalize positioned cell bbox arrays into row-major bbox lists."""
    rows: list[list[tuple[float, float, float, float] | None]] = []
    for row in table_cells:
        if not isinstance(row, list):
            continue
        bbox_row: list[tuple[float, float, float, float] | None] = []
        for cell in row:
            bbox_row.append(_as_bbox(cell))
        rows.append(bbox_row)
    return rows
