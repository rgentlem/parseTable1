"""PyMuPDF positioned-geometry extraction backend."""

from __future__ import annotations

import re
from pathlib import Path
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import groupby
from typing import Any

from table1_parser.config import Settings
from table1_parser.extract.base import BaseExtractor
from table1_parser.extract.layout_fallback import (
    build_text_layout_candidates,
    build_word_lines,
    normalize_bbox_for_rotation,
    normalize_positioned_geometry_for_rotation,
    rotation_affine_matrix,
)
from table1_parser.extract.provisional_table import ProvisionalExtractedTable
from table1_parser.extract.pymupdf_page_adapter import open_pymupdf_document
from table1_parser.context.paper_positioned_document import build_paper_positioned_document
from table1_parser.context.paper_document import (
    iter_paper_discovery_lines,
)
from table1_parser.paper_discovery import PaperDiscoveryState
from table1_parser.extract.table_detector import (
    TABLE_IDENTIFIER_PATTERN,
    DetectedTableCandidate,
    score_candidate,
)
from table1_parser.extract.table_selector import select_top_candidates
from table1_parser.page_furniture_mask import (
    bbox_overlap_fraction,
    filter_positioned_items_for_page_furniture,
    page_furniture_rule_cluster_id,
    page_furniture_source_line_ids,
)
from table1_parser.schemas import (
    PaperPageFurniture,
    PaperPositionedDocument,
    PaperPositionedPage,
    PaperTableMention,
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


@dataclass(frozen=True, slots=True)
class TableCandidateBlockScope:
    """Canonical block scope for one accepted table caption."""

    page_num: int
    mention_id: str
    orientation_group_id: str
    canonical_bbox: tuple[float, float, float, float]
    block_ids: tuple[str, ...]
    source_block_indices: tuple[int, ...]
    line_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TableCandidateGridProposal:
    """Scoped native grid geometry awaiting one candidate decision."""

    page_num: int
    mention_id: str
    orientation_group_id: str
    detector_bbox: tuple[float, float, float, float]
    row_bboxes: tuple[tuple[float, float, float, float], ...]
    column_bboxes: tuple[tuple[float, float, float, float], ...]
    cell_bboxes: tuple[tuple[tuple[float, float, float, float] | None, ...], ...]
    supporting_drawing_items: tuple[tuple[str, int, int], ...]
    materialized_cells: tuple[tuple[TableCandidateGridCell, ...], ...]


@dataclass(frozen=True, slots=True)
class TableCandidateGridCell:
    """Shared positioned text and provenance assigned to one proposed cell."""

    bbox: tuple[float, float, float, float] | None
    text: str
    block_ids: tuple[str, ...]
    line_ids: tuple[str, ...]
    word_indices: tuple[int, ...]
    char_indices: tuple[int, ...]


def _caption_label_assignments(
    *,
    page_num: int,
    candidate_metadata: Sequence[dict[str, Any]],
    paper_discovery: PaperDiscoveryState | None,
    paper_document_lines: Sequence[object],
    paper_table_mentions: Sequence[PaperTableMention] | None,
) -> dict[int, tuple[TableCaptionRegion, TableCaptionBinding]]:
    """Bind PyMuPDF caption-label lines to table regions in canonical geometry."""
    if paper_discovery is None or not paper_table_mentions:
        return {}
    page = next(
        (
            item
            for item in paper_discovery.pages
            if item["page_num"] == page_num
        ),
        None,
    )
    if page is None:
        return {}
    groups_by_id = {
        group["group_id"]: group for group in page["orientation_groups"]
    }
    lines_by_id = {
        line.line_id: line
        for line in paper_document_lines
        if line.page_num == page_num
    }
    table_geometry: list[
        tuple[int, dict[str, object], tuple[float, float, float, float]]
    ] = []
    for table_index, metadata in enumerate(candidate_metadata):
        orientation_group_id = metadata.get("orientation_group_id")
        canonical_table_bbox = _as_bbox(metadata.get("canonical_candidate_bbox"))
        if not isinstance(orientation_group_id, str) or canonical_table_bbox is None:
            continue
        group = groups_by_id.get(orientation_group_id)
        if group is not None:
            table_geometry.append((table_index, group, canonical_table_bbox))

    caption_records: list[tuple[PaperTableMention, object, TableCaptionRegion]] = []
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
            continuation_role=mention.continuation_role,
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
            if line.orientation_group_id != group["group_id"]:
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
    paper_document_lines: Sequence[object],
    caption_label_line_ids: set[str],
) -> tuple[TableCaptionRegion, TableCaptionBinding]:
    """Extend one bound caption label through adjacent single-run text bands."""
    group_lines = [
        line
        for line in paper_document_lines
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
            rules_below_label = [
                rule
                for rule in rules
                if rule >= region.canonical_bbox[3] - CAPTION_BOUNDARY_TOLERANCE
            ]
            boundary_y = min(rules_below_label or rules)
        else:
            boundary_y = binding.table_canonical_bbox[1]

    selected_lines = [group_lines[label_index]]
    following_lines: list[object] = []
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

    line_bands: list[list[object]] = []
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
    paper_discovery: PaperDiscoveryState | None,
    paper_document_lines: Sequence[object],
    paper_table_mentions: Sequence[PaperTableMention] | None,
) -> list[DetectedTableCandidate]:
    """Replace provisional captions with complete PyMuPDF caption regions."""
    if paper_discovery is None or not paper_table_mentions:
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
            candidate_metadata=[candidate.metadata for candidate in page_candidates],
            paper_discovery=paper_discovery,
            paper_document_lines=paper_document_lines,
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
                paper_document_lines=paper_document_lines,
                caption_label_line_ids=caption_label_line_ids,
            )
            caption_table_number = region.table_number
            signals = candidate.metadata.get("signals")
            updated_signals = (
                {
                    **signals,
                    "caption_match": True,
                    "table_1_match": caption_table_number == "1",
                    "caption_table_number": caption_table_number,
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
                        "caption_source": "paper_document_geometry",
                        "caption_region": region.model_dump(mode="json"),
                        "caption_binding": binding.model_dump(mode="json"),
                        "caption_detection_space": "paper_document_orientation_group",
                        "table_number": caption_table_number,
                        "is_continuation": region.mention_kind == "continuation_label",
                        "continuation_of_table_number": (
                            caption_table_number
                            if region.mention_kind == "continuation_label"
                            else None
                        ),
                        **({"signals": updated_signals} if updated_signals is not None else {}),
                    },
                }
            )
    return result


def _bibliography_evidence_masks_by_page(
    paper_discovery: PaperDiscoveryState | None,
    paper_document_lines: Sequence[object],
) -> dict[int, BibliographyEvidenceMask]:
    """Build page-local masks from bibliography-owned canonical blocks."""
    if paper_discovery is None:
        return {}
    line_by_id = {
        line.line_id: line
        for line in paper_document_lines
    }
    blocks_by_id = {
        str(block["block_id"]): block for block in paper_discovery.blocks
    }
    bibliography_line_ids = {
        str(line_id)
        for block_id in paper_discovery.bibliography_block_ids
        for line_id in blocks_by_id[block_id]["line_ids"]
    }
    source_line_ids_by_page: dict[int, set[str]] = {}
    source_line_keys_by_page: dict[int, set[tuple[int, int]]] = {}
    line_regions_by_page: dict[int, list[tuple[float, float, float, float]]] = {}
    for source_line_id in bibliography_line_ids:
        line = line_by_id.get(source_line_id)
        if line is None:
            continue
        page_num = int(line.page_num)
        source_line_ids_by_page.setdefault(page_num, set()).add(source_line_id)
        line_regions_by_page.setdefault(page_num, []).append(line.bbox)
        if line.block_index is not None and line.line_index is not None:
            source_line_keys_by_page.setdefault(page_num, set()).add(
                (line.block_index, line.line_index)
            )

    page_nums = (
        set(source_line_ids_by_page)
        | set(source_line_keys_by_page)
        | set(line_regions_by_page)
    )
    masks: dict[int, BibliographyEvidenceMask] = {}
    for page_num in sorted(page_nums):
        masks[page_num] = BibliographyEvidenceMask(
            page_num=page_num,
            source_line_ids=source_line_ids_by_page.get(page_num, set()),
            source_line_keys=source_line_keys_by_page.get(page_num, set()),
            line_regions=line_regions_by_page.get(page_num, []),
            entry_regions=[],
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
        "source_artifact": "paper_document.json",
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
        paper_discovery: PaperDiscoveryState | None = None,
    ) -> list[ProvisionalExtractedTable]:
        """Extract and rank raw table candidates from a PDF."""
        try:
            positioned_document = paper_positioned_document or build_paper_positioned_document(pdf_path)
            document_lines = (
                list(iter_paper_discovery_lines(paper_discovery, positioned_document))
                if paper_discovery is not None
                else []
            )
            candidates = self._detect_table_candidates(
                pdf_path,
                paper_page_furniture=paper_page_furniture,
                paper_positioned_document=positioned_document,
                paper_table_mentions=paper_table_mentions,
                paper_discovery=paper_discovery,
                paper_document_lines=document_lines,
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
            paper_discovery=paper_discovery,
            paper_document_lines=document_lines,
            paper_table_mentions=paper_table_mentions,
        )

        pages_by_num = {page.page_num: page for page in positioned_document.pages}
        bibliography_masks_by_page = _bibliography_evidence_masks_by_page(
            paper_discovery,
            document_lines,
        )
        filtered_items_by_page: dict[int, tuple[list[dict[str, object]], list[dict[str, object]]]] = {}
        for page_num in {candidate.page_num for candidate in selected_candidates}:
            positioned_page = pages_by_num.get(page_num)
            if positioned_page is None:
                continue
            page_words, _ = filter_positioned_items_for_page_furniture(
                _positioned_page_words(positioned_page),
                paper_page_furniture,
            )
            page_chars, _ = filter_positioned_items_for_page_furniture(
                _positioned_page_chars(positioned_page),
                paper_page_furniture,
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

        document_pages_by_num = {
            page["page_num"]: page
            for page in (paper_discovery.pages if paper_discovery is not None else [])
        }
        candidates_with_positioned_evidence: list[
            tuple[DetectedTableCandidate, TablePositionedEvidence]
        ] = []
        for candidate in selected_candidates:
            positioned_page = pages_by_num.get(candidate.page_num)
            document_page = document_pages_by_num.get(candidate.page_num)
            caption_region = candidate.metadata.get("caption_region")
            caption_region_values = caption_region if isinstance(caption_region, dict) else {}
            caption_bbox = _as_bbox(caption_region_values.get("bbox"))
            orientation_group_id = str(
                candidate.metadata.get("orientation_group_id") or ""
            ) or None
            orientation_group = None
            if document_page is not None:
                orientation_group = next(
                    (
                        group
                        for group in document_page["orientation_groups"]
                        if orientation_group_id is not None
                        and group["group_id"] == orientation_group_id
                    ),
                    None,
                )
            evidence_bbox = (
                candidate.bbox
                if candidate.metadata.get("strong_ruled_geometry") is True
                and candidate.bbox is not None
                else (
                    orientation_group["source_bbox"]
                    if orientation_group is not None
                    else candidate.bbox
                )
            )
            canonical_transform_source_bbox = (
                orientation_group["source_bbox"]
                if orientation_group is not None
                and orientation_group["orientation"] != "upright"
                else (
                    (0.0, 0.0, positioned_page.page_width, positioned_page.page_height)
                    if positioned_page is not None
                    else evidence_bbox
                )
            )
            rotation_direction = (
                orientation_group["orientation"]
                if orientation_group is not None
                else "upright"
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
                paper_page_furniture=paper_page_furniture,
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
            native_grid = candidate.metadata.get("native_grid_proposal")
            if isinstance(native_grid, dict):
                row_bboxes = [
                    _as_bbox(item) for item in native_grid.get("row_bboxes", [])
                ]
                column_bboxes = [
                    _as_bbox(item) for item in native_grid.get("column_bboxes", [])
                ]
                native_cells = [
                    cell
                    for row in native_grid.get("cells", [])
                    if isinstance(row, list)
                    for cell in row
                    if isinstance(cell, dict)
                ]
                positioned_evidence = positioned_evidence.model_copy(
                    update={
                        "canonical_grid_bbox": _as_bbox(
                            native_grid.get("detector_bbox")
                        ),
                        "canonical_row_bounds": [
                            (item[1], item[3]) for item in row_bboxes if item
                        ],
                        "canonical_physical_column_bounds": [
                            (item[0], item[2]) for item in column_bboxes if item
                        ],
                        "canonical_grid_cell_bboxes": _coerce_cell_bboxes(
                            native_grid.get("cell_bboxes", [])
                        ),
                        "grid_source_block_ids": [
                            str(item) for item in native_grid.get("block_ids", [])
                        ],
                        "grid_source_line_ids": list(
                            dict.fromkeys(
                                str(item)
                                for cell in native_cells
                                for item in cell.get("line_ids", [])
                            )
                        ),
                        "grid_source_word_indices": list(
                            dict.fromkeys(
                                int(item)
                                for cell in native_cells
                                for item in cell.get("word_indices", [])
                            )
                        ),
                        "grid_source_char_indices": list(
                            dict.fromkeys(
                                int(item)
                                for cell in native_cells
                                for item in cell.get("char_indices", [])
                            )
                        ),
                        "grid_source_drawing_items": [
                            tuple(item)
                            for item in native_grid.get("drawing_items", [])
                        ],
                    }
                )
            candidates_with_positioned_evidence.append(
                (candidate, positioned_evidence)
            )

        tables = [
            self._build_extracted_table(
                pdf_path=pdf_path,
                candidate=candidate,
                positioned_evidence=positioned_evidence,
            )
            for candidate, positioned_evidence in candidates_with_positioned_evidence
        ]
        observed_table_numbers = sorted(
            {
                int(table_number)
                for table_number in (table.metadata.get("table_number") for table in tables)
                if isinstance(table_number, str) and table_number.isdecimal()
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
        paper_discovery: PaperDiscoveryState | None = None,
        paper_document_lines: Sequence[object] = (),
    ) -> list[DetectedTableCandidate]:
        positioned_document = paper_positioned_document or build_paper_positioned_document(pdf_path)
        positioned_pages_by_num = {
            page.page_num: page
            for page in positioned_document.pages
        }
        document_pages_by_num = {
            page["page_num"]: page
            for page in (paper_discovery.pages if paper_discovery is not None else [])
        }
        bibliography_block_ids = paper_discovery.bibliography_block_ids if paper_discovery else frozenset()
        document_blocks_by_page: dict[int, list[dict[str, object]]] = {}
        for block in paper_discovery.blocks if paper_discovery is not None else []:
            if str(block["block_id"]) not in bibliography_block_ids:
                document_blocks_by_page.setdefault(int(block["page_num"]), []).append(block)
        text_lines_by_page: dict[int, list[object]] = {}
        for line in paper_document_lines:
            text_lines_by_page.setdefault(line.page_num, []).append(line)
        candidates: list[DetectedTableCandidate] = []
        try:
            furniture_source_line_ids = page_furniture_source_line_ids(
                paper_page_furniture
            )
            bibliography_masks_by_page = _bibliography_evidence_masks_by_page(
                paper_discovery,
                paper_document_lines,
            )
            abstract_intervals = _abstract_intervals_by_page(positioned_document)
            for page_num in sorted(positioned_pages_by_num):
                positioned_page = positioned_pages_by_num[page_num]
                page_text = "\n".join(
                    line.raw_text
                    for line in positioned_page.lines
                    if line.line_id not in furniture_source_line_ids
                )
                page_words, page_word_mask_metadata = filter_positioned_items_for_page_furniture(
                    _positioned_page_words(positioned_page),
                    paper_page_furniture,
                )
                page_chars, page_char_mask_metadata = filter_positioned_items_for_page_furniture(
                    _positioned_page_chars(positioned_page),
                    paper_page_furniture,
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
                    kept_rule_segments: list[tuple[float, float, float, float]] = []
                    for segment in page_rule_segments:
                        rule_cluster_id = page_furniture_rule_cluster_id(
                            segment,
                            page_num,
                            paper_page_furniture,
                        )
                        if rule_cluster_id is None:
                            kept_rule_segments.append(segment)
                            continue
                        removed_rule_segments += 1
                        removed_rule_cluster_ids.add(rule_cluster_id)
                    page_rule_segments = kept_rule_segments
                document_page = document_pages_by_num.get(page_num)
                orientation_groups = (
                    list(document_page["orientation_groups"])
                    if document_page is not None
                    else []
                )
                if not orientation_groups:
                    orientation_groups = [
                        {
                            "group_id": f"page-{page_num}-orientation-upright",
                            "orientation": "upright",
                            "source_bbox": (
                                0.0,
                                0.0,
                                positioned_page.page_width,
                                positioned_page.page_height,
                            ),
                            "canonical_width": positioned_page.page_width,
                            "canonical_height": positioned_page.page_height,
                            "column_bands": [(0.0, positioned_page.page_width)],
                        }
                    ]
                page_candidates: list[DetectedTableCandidate] = []
                page_lines = text_lines_by_page.get(page_num, [])
                line_by_id = {line.line_id: line for line in page_lines}
                for group in orientation_groups:
                    group_lines = [
                        line
                        for line in page_lines
                        if line.orientation_group_id == group["group_id"]
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
                            bbox=group["source_bbox"],
                            rotation_direction=group["orientation"],
                        )
                    )
                    transformed_image_bboxes = [
                        normalize_bbox_for_rotation(
                            image_bbox,
                            source_bbox=group["source_bbox"],
                            rotation_direction=group["orientation"],
                        )
                        for image_bbox in positioned_page.image_bboxes
                        if min(image_bbox[2], group["source_bbox"][2])
                        > max(image_bbox[0], group["source_bbox"][0])
                        and min(image_bbox[3], group["source_bbox"][3])
                        > max(image_bbox[1], group["source_bbox"][1])
                    ]
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
                    group_blocks = [block for block in document_blocks_by_page.get(page_num, [])
                                    if block["orientation_group_id"] == group["group_id"]]
                    _block_scope_proposals = _build_block_scope_proposals(
                        page_num=page_num,
                        blocks=group_blocks,
                        rule_segments=transformed_rules,
                        paper_table_mentions=transformed_mentions,
                    )
                    _native_grid_proposals = _build_native_grid_proposals(
                        pdf_path=pdf_path,
                        positioned_page=positioned_page,
                        block_scopes=_block_scope_proposals,
                        words=transformed_words,
                        chars=transformed_chars,
                    ) if group["orientation"] == "upright" else []
                    group_text = "\n".join(line.text for line in group_lines) or page_text
                    text_layout_candidates = _build_rule_span_candidates(
                        page_num=page_num,
                        page_text=group_text,
                        words=transformed_words,
                        chars=transformed_chars,
                        rule_segments=transformed_rules,
                        image_bboxes=transformed_image_bboxes,
                        paper_table_mentions=transformed_mentions,
                    )
                    proposals_by_mention_id: dict[
                        str, list[TableCandidateGridProposal]
                    ] = {}
                    for proposal in _native_grid_proposals:
                        proposals_by_mention_id.setdefault(
                            proposal.mention_id, []
                        ).append(proposal)
                    scopes_by_mention_id: dict[str, list[TableCandidateBlockScope]] = {}
                    for scope in _block_scope_proposals:
                        scopes_by_mention_id.setdefault(scope.mention_id, []).append(scope)

                    native_replacements: dict[int, DetectedTableCandidate] = {}
                    native_insertions: list[DetectedTableCandidate] = []
                    for mention_id, proposals in proposals_by_mention_id.items():
                        scopes = scopes_by_mention_id.get(mention_id, [])
                        mention = next(
                            (
                                item
                                for item in transformed_mentions
                                if item.mention_id == mention_id
                            ),
                            None,
                        )
                        if len(proposals) != 1 or len(scopes) != 1 or mention is None:
                            continue
                        proposal = proposals[0]
                        scope = scopes[0]
                        row_count = len(proposal.row_bboxes)
                        column_count = len(proposal.column_bboxes)
                        if (
                            not mention.source_line_text.strip()
                            or not scope.block_ids
                            or not scope.line_ids
                            or not proposal.supporting_drawing_items
                            or row_count == 0
                            or column_count == 0
                            or len(proposal.cell_bboxes) != row_count
                            or len(proposal.materialized_cells) != row_count
                            or any(
                                len(row) != column_count
                                for row in proposal.cell_bboxes
                            )
                            or any(
                                len(row) != column_count
                                for row in proposal.materialized_cells
                            )
                            or not (
                                scope.canonical_bbox[0]
                                <= proposal.detector_bbox[0]
                                < proposal.detector_bbox[2]
                                <= scope.canonical_bbox[2]
                                and scope.canonical_bbox[1]
                                <= proposal.detector_bbox[1]
                                < proposal.detector_bbox[3]
                                <= scope.canonical_bbox[3]
                            )
                        ):
                            continue
                        matching_candidates = [
                            candidate
                            for candidate in text_layout_candidates
                            if candidate.metadata.get("caption_mention_id")
                            == mention_id
                            and candidate.metadata.get("candidate_region_source")
                            == "caption_and_rule_geometry"
                        ]
                        if len(matching_candidates) > 1:
                            continue
                        existing_candidate = (
                            matching_candidates[0] if matching_candidates else None
                        )
                        native_cells = [
                            [
                                {
                                    "bbox": cell.bbox,
                                    "block_ids": list(cell.block_ids),
                                    "line_ids": list(cell.line_ids),
                                    "word_indices": list(cell.word_indices),
                                    "char_indices": list(cell.char_indices),
                                }
                                for cell in row
                            ]
                            for row in proposal.materialized_cells
                        ]
                        native_metadata = {
                            **(
                                existing_candidate.metadata
                                if existing_candidate is not None
                                else {}
                            ),
                            "layout_source": "pymupdf_scoped_native_grid",
                            "candidate_region_source": (
                                "caption_block_scope_native_grid"
                            ),
                            "caption_mention_id": mention_id,
                            "caption_table_number": mention.table_number,
                            "caption_is_continuation": (
                                mention.mention_kind == "continuation_label"
                            ),
                            "is_rectangular": True,
                            "strong_ruled_geometry": True,
                            "table_cells": [
                                [cell for cell in row]
                                for row in proposal.cell_bboxes
                            ],
                            "row_bounds": [
                                (row[1], row[3]) for row in proposal.row_bboxes
                            ],
                            "native_grid_proposal": {
                                "detector_bbox": proposal.detector_bbox,
                                "row_bboxes": proposal.row_bboxes,
                                "column_bboxes": proposal.column_bboxes,
                                "cell_bboxes": [
                                    [cell for cell in row]
                                    for row in proposal.cell_bboxes
                                ],
                                "block_ids": scope.block_ids,
                                "source_block_indices": scope.source_block_indices,
                                "line_ids": scope.line_ids,
                                "drawing_items": proposal.supporting_drawing_items,
                                "cells": native_cells,
                            },
                        }
                        native_candidate = score_candidate(
                            DetectedTableCandidate(
                                page_num=page_num,
                                table_index=(
                                    existing_candidate.table_index
                                    if existing_candidate is not None
                                    else 0
                                ),
                                bbox=proposal.detector_bbox,
                                raw_rows=[
                                    [cell.text for cell in row]
                                    for row in proposal.materialized_cells
                                ],
                                caption=(
                                    existing_candidate.caption
                                    if existing_candidate is not None
                                    else mention.source_line_text
                                ),
                                page_text=(
                                    existing_candidate.page_text
                                    if existing_candidate is not None
                                    else group_text
                                ),
                                metadata=native_metadata,
                            )
                        )
                        if existing_candidate is None:
                            native_insertions.append(native_candidate)
                        else:
                            native_replacements[id(existing_candidate)] = (
                                native_candidate
                            )
                    if native_replacements or native_insertions:
                        text_layout_candidates = [
                            native_replacements.get(id(candidate), candidate)
                            for candidate in text_layout_candidates
                        ]
                        text_layout_candidates.extend(native_insertions)
                    if group["orientation"] == "upright":
                        continuation_candidates = (
                            _build_cross_page_continuation_candidates(
                                page_num=page_num,
                                page_text=group_text,
                                words=transformed_words,
                                chars=transformed_chars,
                                rule_segments=transformed_rules,
                                prior_candidates=candidates,
                            )
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
                    if not text_layout_candidates:
                        text_layout_candidates = build_text_layout_candidates(
                            page_num=page_num,
                            page_text=group_text,
                            words=transformed_words,
                            chars=transformed_chars,
                            rule_segments=transformed_rules,
                            layout_source="pymupdf_text_positions",
                            paper_table_mentions=transformed_mentions,
                            allow_uncaptioned_orientation_group=(
                                group["orientation"] != "upright"
                            ),
                        )
                    for candidate in text_layout_candidates:
                        canonical_candidate_bbox = candidate.bbox
                        source_candidate_bbox = canonical_candidate_bbox
                        if candidate.bbox is not None and group["orientation"] != "upright":
                            canonical_left, canonical_top, canonical_right, canonical_bottom = candidate.bbox
                            source_left, source_top, source_right, source_bottom = group["source_bbox"]
                            if group["orientation"] == "vertical_text_up":
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
                                        "geometry_coordinate_frame": "paper_document_orientation_group",
                                        "canonical_candidate_bbox": canonical_candidate_bbox,
                                        "source_candidate_bbox": source_candidate_bbox,
                                        "orientation_group_id": group["group_id"],
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
        *,
        positioned_evidence: TablePositionedEvidence,
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
            positioned_evidence=positioned_evidence,
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
            if abs(float(y1) - float(y0)) <= 1.5 and abs(float(x1) - float(x0)) > 0.0
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


def _build_block_scope_proposals(
    *,
    page_num: int,
    blocks: Sequence[dict[str, object]],
    rule_segments: Sequence[tuple[float, float, float, float]],
    paper_table_mentions: Sequence[PaperTableMention],
) -> list[TableCandidateBlockScope]:
    """Build exact outer scopes without assigning table or header structure."""
    horizontal_extents_by_y: dict[float, tuple[float, float]] = {}
    for x0, y0, x1, y1 in rule_segments:
        if y0 != y1 or x0 == x1:
            continue
        left, right = sorted((float(x0), float(x1)))
        current = horizontal_extents_by_y.get(float(y0))
        horizontal_extents_by_y[float(y0)] = (min(left, current[0]), max(right, current[1])) if current else (left, right)
    rule_rows_by_extent: dict[tuple[float, float], list[float]] = {}
    for rule_y, extent in horizontal_extents_by_y.items():
        rule_rows_by_extent.setdefault(extent, []).append(rule_y)

    captions = sorted(
        (mention for mention in paper_table_mentions
         if mention.page_num == page_num and mention.is_caption_candidate),
        key=lambda mention: mention.source_line_bbox[1],
    )
    proposals: list[TableCandidateBlockScope] = []
    for mention in captions:
        caption_block = next((block for block in blocks
                              if mention.source_line_id in block["line_ids"]), None)
        if caption_block is None:
            continue
        caption_left, caption_top, caption_right, caption_bottom = mention.source_line_bbox
        next_caption_top = min(
            (other.source_line_bbox[1] for other in captions
             if other.source_line_bbox[1] > caption_top),
            default=float("inf"),
        )
        related_rule_groups = [
            (rows[0], extent[0], extent[1], rows)
            for extent, source_rows in rule_rows_by_extent.items()
            if len(rows := sorted(y for y in source_rows if caption_bottom <= y < next_caption_top)) >= 2
            and min(caption_right, extent[1]) > max(caption_left, extent[0])
        ]
        if not related_rule_groups:
            continue
        _, left, right, rule_rows = min(related_rule_groups)
        top, bottom = rule_rows[0], rule_rows[-1]
        scoped_blocks = sorted(
            (
                block
                for block in blocks
                if len(block["canonical_bbox"]) == 4
                and top <= float(block["canonical_bbox"][1])
                and float(block["canonical_bbox"][3]) <= bottom
                and min(right, float(block["canonical_bbox"][2]))
                > max(left, float(block["canonical_bbox"][0]))
            ),
            key=lambda block: (int(block["source_block_index"]), str(block["block_id"])),
        )
        if not scoped_blocks:
            continue
        proposals.append(
            TableCandidateBlockScope(
                page_num=page_num,
                mention_id=mention.mention_id,
                orientation_group_id=str(caption_block["orientation_group_id"]),
                canonical_bbox=(left, top, right, bottom),
                block_ids=tuple(str(block["block_id"]) for block in scoped_blocks),
                source_block_indices=tuple(int(block["source_block_index"]) for block in scoped_blocks),
                line_ids=tuple(str(line_id) for block in scoped_blocks for line_id in block["line_ids"]),
            )
        )
    return proposals


def _build_native_grid_proposals(
    *,
    pdf_path: str,
    positioned_page: PaperPositionedPage,
    block_scopes: Sequence[TableCandidateBlockScope],
    words: Sequence[dict[str, object]],
    chars: Sequence[dict[str, object]],
) -> list[TableCandidateGridProposal]:
    """Build scoped native grid geometry without changing candidate selection."""
    if not block_scopes:
        return []
    document = open_pymupdf_document(pdf_path)
    proposals: list[TableCandidateGridProposal] = []
    try:
        page = document[positioned_page.page_num - 1]
        for scope in block_scopes:
            left, top, right, bottom = scope.canonical_bbox
            block_id_by_source_index = dict(
                zip(scope.source_block_indices, scope.block_ids, strict=True)
            )
            vertical_lines: list[float] = []
            drawing_items: list[tuple[str, int, int]] = []
            for rectangle in positioned_page.drawing_rectangles:
                rect_left, rect_top, rect_right, rect_bottom = rectangle.bbox
                if not (left <= rect_left and rect_right <= right
                        and top <= rect_top and rect_bottom <= bottom):
                    continue
                vertical_lines.extend((rect_left, rect_right))
                drawing_items.append(("rectangle", rectangle.source_drawing_index,
                                      rectangle.source_item_index))
            for line in positioned_page.drawing_lines:
                if line.start[1] != line.end[1] or line.start[0] == line.end[0]:
                    continue
                if not (left <= line.start[0] <= right and left <= line.end[0] <= right
                        and top <= line.start[1] <= bottom):
                    continue
                vertical_lines.extend((line.start[0], line.end[0]))
                drawing_items.append(("line", line.source_drawing_index,
                                      line.source_item_index))
            if not vertical_lines:
                continue
            finder = page.find_tables(
                clip=scope.canonical_bbox,
                vertical_lines=vertical_lines,
                horizontal_strategy="lines",
            )
            for table in finder.tables if finder is not None else []:
                cell_bboxes = tuple(
                    tuple(None if cell is None else tuple(float(value) for value in cell)
                          for cell in row.cells)
                    for row in table.rows
                )
                column_bboxes: list[tuple[float, float, float, float]] = []
                for col_idx in range(table.col_count):
                    cells = [row[col_idx] for row in cell_bboxes
                             if col_idx < len(row) and row[col_idx] is not None]
                    if cells:
                        column_bboxes.append((min(cell[0] for cell in cells),
                                              min(cell[1] for cell in cells),
                                              max(cell[2] for cell in cells),
                                              max(cell[3] for cell in cells)))
                materialized_rows: list[tuple[TableCandidateGridCell, ...]] = []
                for cell_row in cell_bboxes:
                    materialized_row: list[TableCandidateGridCell] = []
                    for cell in cell_row:
                        if cell is None:
                            materialized_row.append(TableCandidateGridCell(
                                bbox=None, text="", block_ids=(), line_ids=(),
                                word_indices=(), char_indices=()))
                            continue
                        cell_words = sorted(
                            (item for item in words
                             if isinstance(item.get("source_word_index"), int)
                             and cell[0] <= (float(item["x0"]) + float(item["x1"])) / 2 < cell[2]
                             and cell[1] <= (float(item["top"]) + float(item["bottom"])) / 2 < cell[3]),
                            key=lambda item: (int(item["block_index"]), int(item["line_index"]),
                                              int(item["source_word_index"])),
                        )
                        cell_chars = sorted(
                            (item for item in chars
                             if isinstance(item.get("char_index"), int)
                             and cell[0] <= (float(item["x0"]) + float(item["x1"])) / 2 < cell[2]
                             and cell[1] <= (float(item["top"]) + float(item["bottom"])) / 2 < cell[3]),
                            key=lambda item: (int(item["block_index"]), int(item["line_index"]),
                                              int(item["char_index"])),
                        )
                        source_items = [*cell_words, *cell_chars]
                        materialized_row.append(TableCandidateGridCell(
                            bbox=cell,
                            text="\n".join(
                                " ".join(str(item["text"]) for item in line_words)
                                for _, line_words in groupby(
                                    cell_words,
                                    key=lambda item: (item["block_index"], item["line_index"]),
                                )
                            ),
                            block_ids=tuple(dict.fromkeys(
                                block_id_by_source_index[int(item["block_index"])]
                                for item in source_items
                                if int(item["block_index"]) in block_id_by_source_index
                            )),
                            line_ids=tuple(dict.fromkeys(
                                str(item["source_line_id"])
                                for item in source_items if isinstance(item.get("source_line_id"), str)
                            )),
                            word_indices=tuple(int(item["source_word_index"]) for item in cell_words),
                            char_indices=tuple(int(item["char_index"]) for item in cell_chars),
                        ))
                    materialized_rows.append(tuple(materialized_row))
                proposals.append(
                    TableCandidateGridProposal(
                        page_num=scope.page_num,
                        mention_id=scope.mention_id,
                        orientation_group_id=scope.orientation_group_id,
                        detector_bbox=tuple(float(value) for value in table.bbox),
                        row_bboxes=tuple(tuple(float(value) for value in row.bbox)
                                         for row in table.rows),
                        column_bboxes=tuple(column_bboxes),
                        cell_bboxes=cell_bboxes,
                        supporting_drawing_items=tuple(drawing_items),
                        materialized_cells=tuple(materialized_rows),
                    )
                )
    finally:
        document.close()
    return proposals


def _build_rule_span_candidates(
    *,
    page_num: int,
    page_text: str,
    words: list[dict[str, object]],
    chars: list[dict[str, object]],
    rule_segments: list[tuple[float, float, float, float]],
    image_bboxes: list[tuple[float, float, float, float]],
    paper_table_mentions: Sequence[PaperTableMention] | None,
) -> list[DetectedTableCandidate]:
    """Build canonical candidates from captions or connected cell-rule geometry."""
    if not words or not rule_segments:
        return []
    rule_spans = _horizontal_rule_spans(rule_segments)
    connected_rule_spans: list[tuple[float, float, float]] = []
    for rule_y, span_left, span_right in rule_spans:
        component_left = span_left
        component_right = span_right
        component_expanded = True
        while component_expanded:
            component_expanded = False
            for x0, y0, x1, y1 in rule_segments:
                if not min(y0, y1) <= rule_y <= max(y0, y1):
                    continue
                segment_left = min(x0, x1)
                segment_right = max(x0, x1)
                if (
                    segment_right < component_left
                    or segment_left > component_right
                ):
                    continue
                if (
                    segment_left < component_left
                    or segment_right > component_right
                ):
                    component_left = min(component_left, segment_left)
                    component_right = max(component_right, segment_right)
                    component_expanded = True
        connected_rule_spans.append(
            (rule_y, component_left, component_right)
        )
    rule_spans = connected_rule_spans

    caption_mentions = sorted(
        (
            mention
            for mention in paper_table_mentions
            if mention.page_num == page_num
            and mention.is_caption_candidate
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
        selected_visual_object_bbox: tuple[float, float, float, float] | None = None
        for start_y, left, right in (
            related_spans
            if mention.continuation_role != "to_next_page"
            else []
        ):
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
            visual_object_bbox = min(
                (
                    image_bbox
                    for image_bbox in image_bboxes
                    if image_bbox[1] > start_y + 2.0
                    and min(right, image_bbox[2]) - max(left, image_bbox[0])
                    >= (right - left) * 0.25
                    and (
                        abs(image_bbox[0] - left) > edge_tolerance
                        or abs(image_bbox[2] - right) > edge_tolerance
                    )
                ),
                key=lambda image_bbox: image_bbox[1],
                default=None,
            )
            candidate_bottom_limit = min(
                next_caption_top - 2.0,
                visual_object_bbox[1]
                if visual_object_bbox is not None
                else float("inf"),
            )
            matching_rows = [
                span
                for span in rule_spans
                if start_y <= span[0] < candidate_bottom_limit
                and abs(span[1] - left) <= edge_tolerance
                and abs(span[2] - right) <= edge_tolerance
            ]
            if len(matching_rows) >= 2:
                scoped_word_bottoms = [
                    float(word["bottom"])
                    for word in words
                    if left
                    <= (float(word["x0"]) + float(word["x1"])) / 2.0
                    <= right
                    and start_y
                    <= (float(word["top"]) + float(word["bottom"])) / 2.0
                    < candidate_bottom_limit
                ]
                scoped_rule_rows = [
                    span[0]
                    for span in rule_spans
                    if start_y <= span[0] < candidate_bottom_limit
                    and min(right, span[2]) > max(left, span[1])
                ]
                if not scoped_word_bottoms:
                    continue
                selected_region = (
                    left,
                    caption_top,
                    right,
                    max(scoped_word_bottoms + scoped_rule_rows),
                )
                selected_visual_object_bbox = visual_object_bbox
                break

        if (
            selected_region is None
            and mention.continuation_role != "from_previous_page"
        ):
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
                visual_object_bbox = max(
                    (
                        image_bbox
                        for image_bbox in image_bboxes
                        if image_bbox[3] < end_y - 2.0
                        and min(right, image_bbox[2]) - max(left, image_bbox[0])
                        >= (right - left) * 0.25
                        and (
                            abs(image_bbox[0] - left) > edge_tolerance
                            or abs(image_bbox[2] - right) > edge_tolerance
                        )
                    ),
                    key=lambda image_bbox: image_bbox[3],
                    default=None,
                )
                candidate_top_limit = max(
                    previous_caption_bottom + 2.0,
                    visual_object_bbox[3]
                    if visual_object_bbox is not None
                    else float("-inf"),
                )
                matching_rows = [
                    span
                    for span in rule_spans
                    if candidate_top_limit < span[0] <= end_y
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
                    selected_visual_object_bbox = visual_object_bbox
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
            paper_table_mentions=[mention],
            candidate_region_bbox=selected_region,
        ):
            trailing_non_table_rows = candidate.metadata.get(
                "trailing_non_table_rows"
            )
            if mention.continuation_role == "to_next_page":
                existing_trailing_metadata = (
                    trailing_non_table_rows
                    if isinstance(trailing_non_table_rows, dict)
                    else {}
                )
                existing_reasons = existing_trailing_metadata.get("reasons")
                existing_note_texts = existing_trailing_metadata.get(
                    "continuation_note_texts"
                )
                trailing_non_table_rows = {
                    **existing_trailing_metadata,
                    "reasons": list(
                        dict.fromkeys(
                            [
                                *(
                                    [str(reason) for reason in existing_reasons]
                                    if isinstance(existing_reasons, list)
                                    else []
                                ),
                                "trailing_continuation_note",
                            ]
                        )
                    ),
                    "continuation_note_texts": list(
                        dict.fromkeys(
                            [
                                *(
                                    [str(text) for text in existing_note_texts]
                                    if isinstance(existing_note_texts, list)
                                    else []
                                ),
                                mention.source_line_text,
                            ]
                        )
                    ),
                    "continuation_table_number": mention.table_number,
                    "continuation_mention_provenance": {
                        "source_artifact": mention.source_artifact,
                        "mention_id": mention.mention_id,
                        "source_line_id": mention.source_line_id,
                        "source_line_bbox": list(mention.source_line_bbox),
                        "continuation_role": mention.continuation_role,
                        "candidate_region_source": "caption_and_rule_geometry",
                        "candidate_rule_span": [left, top, right, bottom],
                    },
                }
            candidates.append(
                candidate.model_copy(
                    update={
                        "metadata": {
                            **candidate.metadata,
                            "trailing_non_table_rows": trailing_non_table_rows,
                            "candidate_region_source": "caption_and_rule_geometry",
                            "caption_mention_id": mention.mention_id,
                            "candidate_rule_span": [left, top, right, bottom],
                            **(
                                {
                                    "candidate_visual_object_barrier_bbox": list(
                                        selected_visual_object_bbox
                                    )
                                }
                                if selected_visual_object_bbox is not None
                                else {}
                            ),
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
            paper_table_mentions=[],
            candidate_region_bbox=region_bbox,
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
        and isinstance(candidate.metadata.get("canonical_candidate_bbox"), (list, tuple))
        and len(candidate.metadata["canonical_candidate_bbox"]) == 4
        and isinstance(candidate.metadata.get("value_matrix_column_anchors"), list)
        and len(candidate.metadata["value_matrix_column_anchors"]) >= 2
    ]
    if not eligible_prior or not words or not rule_segments:
        return []
    prior_candidate = max(
        eligible_prior,
        key=lambda candidate: candidate.table_index,
    )
    prior_bbox = tuple(
        float(value)
        for value in prior_candidate.metadata["canonical_candidate_bbox"]
    )
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
        not isinstance(prior_table_number, str)
        or TABLE_IDENTIFIER_PATTERN.fullmatch(prior_table_number) is None
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
            paper_table_mentions=[],
            candidate_region_bbox=(left, top, right, bottom),
        )
    ]


def _positioned_page_words(page: PaperPositionedPage) -> list[dict[str, object]]:
    """Project positioned-document words into the dict shape used by extraction heuristics."""
    source_line_ids = {
        (line.block_index, line.line_index): line.line_id
        for line in page.lines
        if line.block_index is not None and line.line_index is not None
    }
    return [
        {
            **word.model_dump(mode="json"),
            "source_word_index": word_index,
            **(
                {"source_line_id": source_line_id}
                if (
                    source_line_id := source_line_ids.get(
                        (word.block_index, word.line_index)
                    )
                )
                is not None
                else {}
            ),
        }
        for word_index, word in enumerate(page.words)
    ]


def _positioned_page_chars(page: PaperPositionedPage) -> list[dict[str, object]]:
    """Project positioned-document chars into the dict shape used by extraction heuristics."""
    source_line_ids = {
        (line.block_index, line.line_index): line.line_id
        for line in page.lines
        if line.block_index is not None and line.line_index is not None
    }
    return [
        {
            **char.model_dump(mode="json", exclude_none=True),
            **(
                {"source_line_id": source_line_id}
                if (
                    source_line_id := source_line_ids.get(
                        (char.block_index, char.line_index)
                    )
                )
                is not None
                else {}
            ),
        }
        for char in page.chars
    ]


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
    paper_page_furniture: PaperPageFurniture | None,
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

    owned_line_ids = set(line_ids)
    owned_line_orientations = {
        (
            "vertical_text_up"
            if line.direction[1] < 0.0
            else "vertical_text_down"
        )
        if abs(line.direction[1]) > abs(line.direction[0])
        else "upright"
        for line in page.lines
        if line.line_id in owned_line_ids and line.direction is not None
    }
    if len(owned_line_orientations) == 1:
        owned_rotation_direction = next(iter(owned_line_orientations))
        if owned_rotation_direction != rotation_direction:
            diagnostics.append("table_owned_orientation_group_mismatch")
        rotation_direction = owned_rotation_direction
    elif not owned_line_orientations:
        diagnostics.append("table_owned_text_orientation_missing")
    else:
        diagnostics.append("table_owned_text_orientation_ambiguous")

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
        and page_furniture_rule_cluster_id(
            segment,
            page_num,
            paper_page_furniture,
        )
        is None
    ]
    stroked_rule_segment_indices = [
        index
        for index, segment in enumerate(page.stroked_rule_segments)
        if segment_intersects(segment)
        and page_furniture_rule_cluster_id(
            segment,
            page_num,
            paper_page_furniture,
        )
        is None
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

    (
        canonical_words,
        canonical_chars,
        canonical_rule_segments,
        _canonical_transform_bbox,
    ) = normalize_positioned_geometry_for_rotation(
        words=table_words,
        chars=table_chars,
        rule_segments=[*source_rule_segments, *source_stroked_rule_segments],
        bbox=canonical_transform_source_bbox,
        rotation_direction=rotation_direction,
    )
    canonical_stroked_rule_segments = canonical_rule_segments[
        len(source_rule_segments) :
    ]
    canonical_rule_segments = canonical_rule_segments[: len(source_rule_segments)]
    affine_matrix = rotation_affine_matrix(
        source_bbox=canonical_transform_source_bbox,
        rotation_direction=rotation_direction,
    )

    canonical_line_bboxes = [canonical_bbox(item) for item in line_bboxes]
    canonical_span_bboxes = [canonical_bbox(item) for item in span_bboxes]
    canonical_word_bboxes = [
        _positioned_item_bbox(item)
        for item in canonical_words
    ]
    canonical_char_bboxes = [
        _positioned_item_bbox(item)
        for item in canonical_chars
    ]
    if any(item is None for item in canonical_word_bboxes + canonical_char_bboxes):
        diagnostics.append("canonical_item_bbox_missing")

    canonical_lines = sorted(
        (
            (line_id, bbox)
            for line_id, bbox in zip(line_ids, canonical_line_bboxes, strict=True)
            if bbox is not None
        ),
        key=lambda item: (item[1][1], item[1][0], item[0]),
    )
    canonical_spans = sorted(
        (
            (reference, bbox)
            for reference, bbox in zip(
                span_references,
                canonical_span_bboxes,
                strict=True,
            )
            if bbox is not None
        ),
        key=lambda item: (
            item[1][1],
            item[1][0],
            item[0].line_id,
            item[0].span_index,
        ),
    )
    canonical_word_items = sorted(
        (
            (int(item["source_word_index"]), bbox)
            for item, bbox in zip(table_words, canonical_word_bboxes, strict=True)
            if bbox is not None
        ),
        key=lambda item: (item[1][1], item[1][0], item[0]),
    )
    canonical_char_items = sorted(
        (
            (int(item["char_index"]), bbox)
            for item, bbox in zip(table_chars, canonical_char_bboxes, strict=True)
            if bbox is not None
        ),
        key=lambda item: (item[1][1], item[1][0], item[0]),
    )

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
        line_ids=[item[0] for item in canonical_lines],
        canonical_line_bboxes=[item[1] for item in canonical_lines],
        span_references=[item[0] for item in canonical_spans],
        canonical_span_bboxes=[item[1] for item in canonical_spans],
        word_indices=[item[0] for item in canonical_word_items],
        canonical_word_bboxes=[item[1] for item in canonical_word_items],
        char_indices=[item[0] for item in canonical_char_items],
        canonical_char_bboxes=[item[1] for item in canonical_char_items],
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
