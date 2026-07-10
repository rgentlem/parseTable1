"""Collect positioned page text for page-furniture detection."""

from __future__ import annotations

import re
from pathlib import Path

from table1_parser.schemas import (
    PageFurnitureCluster,
    PageFurnitureRegion,
    PageFurnitureTextObservation,
    PaperPageFurniture,
    PaperPositionedDocument,
)


_PAGE_NUMBER_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9.])\d+(?![A-Za-z0-9.])")


def normalize_page_furniture_text(raw_text: str, *, page_num: int | None = None) -> str:
    """Normalize page text only for page-furniture matching."""
    normalized_text = " ".join(raw_text.split())
    if page_num is None or not normalized_text:
        return normalized_text

    return _PAGE_NUMBER_TOKEN_RE.sub(
        lambda match: "<page_num>" if int(match.group(0)) == page_num else match.group(0),
        normalized_text,
    )


def collect_page_furniture_text_observations(
    pdf_path: str,
    *,
    paper_positioned_document: PaperPositionedDocument | None = None,
) -> tuple[list[PageFurnitureTextObservation], int]:
    """Collect positioned page text lines as page-furniture observations plus PDF page count."""
    from table1_parser.context.paper_positioned_document import build_paper_positioned_document

    positioned_document = paper_positioned_document or build_paper_positioned_document(pdf_path)

    observations: list[PageFurnitureTextObservation] = []
    for page in positioned_document.pages:
        if page.page_width <= 0.0 or page.page_height <= 0.0:
            continue
        for line in page.lines:
            normalized_text = normalize_page_furniture_text(line.raw_text, page_num=page.page_num)
            if not normalized_text:
                continue
            observations.append(
                PageFurnitureTextObservation(
                    observation_id=line.line_id,
                    page_num=page.page_num,
                    raw_text=line.raw_text,
                    normalized_text=normalized_text,
                    bbox=line.bbox,
                    relative_bbox=(
                        line.bbox[0] / page.page_width,
                        line.bbox[1] / page.page_height,
                        line.bbox[2] / page.page_width,
                        line.bbox[3] / page.page_height,
                    ),
                    page_width=page.page_width,
                    page_height=page.page_height,
                    orientation=line.orientation,
                    block_index=line.block_index,
                    line_index=line.page_line_index,
                    source_artifact="paper_positioned_document.json",
                )
            )
    return observations, positioned_document.page_count


def build_paper_page_furniture(
    pdf_path: str,
    *,
    paper_id: str | None = None,
    paper_positioned_document: PaperPositionedDocument | None = None,
    min_pages: int = 3,
    min_page_fraction: float = 0.5,
    relative_position_tolerance: float = 0.02,
    relative_edge_margin: float = 0.06,
) -> PaperPageFurniture:
    """Build the paper-level page-furniture artifact."""
    observations, page_count = collect_page_furniture_text_observations(
        pdf_path,
        paper_positioned_document=paper_positioned_document,
    )
    clusters, ignored_regions = cluster_page_furniture_observations(
        observations,
        page_count=page_count or None,
        min_pages=min_pages,
        min_page_fraction=min_page_fraction,
        relative_position_tolerance=relative_position_tolerance,
        relative_edge_margin=relative_edge_margin,
    )
    diagnostics = []
    if not observations:
        diagnostics.append("no_page_text_observations")
    elif not clusters:
        diagnostics.append("no_repeated_page_furniture")

    return PaperPageFurniture(
        paper_id=paper_id or Path(pdf_path).stem,
        source_pdf=pdf_path,
        observations=observations,
        clusters=clusters,
        ignored_regions=ignored_regions,
        metadata={
            "source_artifacts": ["paper_positioned_document.json"],
            "observation_count": len(observations),
            "cluster_count": len(clusters),
            "ignored_region_count": len(ignored_regions),
            "page_count": page_count,
            "thresholds": {
                "min_pages": min_pages,
                "min_page_fraction": min_page_fraction,
                "relative_position_tolerance": relative_position_tolerance,
                "relative_edge_margin": relative_edge_margin,
            },
            "diagnostics": diagnostics,
        },
    )


def cluster_page_furniture_observations(
    observations: list[PageFurnitureTextObservation],
    *,
    page_count: int | None = None,
    min_pages: int = 3,
    min_page_fraction: float = 0.5,
    relative_position_tolerance: float = 0.02,
    relative_edge_margin: float = 0.06,
) -> tuple[list[PageFurnitureCluster], list[PageFurnitureRegion]]:
    """Cluster repeated page text by normalized content and stable relative position."""
    if not observations:
        return [], []

    observed_page_count = max(observation.page_num for observation in observations)
    total_pages = max(page_count or observed_page_count, observed_page_count)
    if total_pages <= 0:
        return [], []

    location_groups: dict[tuple[str, str | None], list[list[PageFurnitureTextObservation]]] = {}
    for observation in observations:
        if not observation.normalized_text:
            continue
        center_x = (observation.relative_bbox[0] + observation.relative_bbox[2]) / 2.0
        center_y = (observation.relative_bbox[1] + observation.relative_bbox[3]) / 2.0
        text_groups = location_groups.setdefault((observation.normalized_text, observation.orientation), [])
        for text_group in text_groups:
            group_center_x = sum((item.relative_bbox[0] + item.relative_bbox[2]) / 2.0 for item in text_group) / len(
                text_group
            )
            group_center_y = sum((item.relative_bbox[1] + item.relative_bbox[3]) / 2.0 for item in text_group) / len(
                text_group
            )
            if (
                abs(center_x - group_center_x) <= relative_position_tolerance
                and abs(center_y - group_center_y) <= relative_position_tolerance
            ):
                text_group.append(observation)
                break
        else:
            text_groups.append([observation])

    clusters: list[PageFurnitureCluster] = []
    regions: list[PageFurnitureRegion] = []
    odd_scope_count = sum(1 for page_num in range(1, total_pages + 1) if page_num % 2 == 1)
    even_scope_count = total_pages - odd_scope_count

    for (normalized_text, orientation), text_groups in sorted(location_groups.items(), key=lambda item: (item[0][0], item[0][1] or "")):
        for text_group in text_groups:
            page_nums = sorted({observation.page_num for observation in text_group})
            page_fraction = len(page_nums) / total_pages
            odd_pages = [page_num for page_num in page_nums if page_num % 2 == 1]
            even_pages = [page_num for page_num in page_nums if page_num % 2 == 0]
            odd_fraction = len(odd_pages) / odd_scope_count if odd_scope_count else 0.0
            even_fraction = len(even_pages) / even_scope_count if even_scope_count else 0.0

            recurrence_scope = None
            scope_page_count = total_pages
            scope_page_fraction = page_fraction
            broad_all_match = page_fraction >= min_page_fraction
            min_page_match = len(page_nums) >= min_pages
            odd_match = bool(odd_pages) and (len(odd_pages) >= min_pages or odd_fraction >= min_page_fraction)
            even_match = bool(even_pages) and (len(even_pages) >= min_pages or even_fraction >= min_page_fraction)

            if broad_all_match and odd_pages and even_pages:
                recurrence_scope = "all_pages"
            elif odd_match and (not even_match or odd_fraction >= even_fraction):
                recurrence_scope = "odd_pages"
                scope_page_count = odd_scope_count
                scope_page_fraction = odd_fraction
            elif even_match:
                recurrence_scope = "even_pages"
                scope_page_count = even_scope_count
                scope_page_fraction = even_fraction
            elif broad_all_match:
                recurrence_scope = "all_pages"
            elif min_page_match:
                recurrence_scope = "page_subset"

            if recurrence_scope is None:
                continue

            cluster_id = f"page-furniture-cluster-{len(clusters) + 1}"
            representative_bbox = tuple(
                sum(observation.bbox[index] for observation in text_group) / len(text_group) for index in range(4)
            )
            representative_relative_bbox = tuple(
                sum(observation.relative_bbox[index] for observation in text_group) / len(text_group) for index in range(4)
            )
            if not (
                representative_relative_bbox[0] <= relative_edge_margin
                or representative_relative_bbox[1] <= relative_edge_margin
                or representative_relative_bbox[2] >= 1.0 - relative_edge_margin
                or representative_relative_bbox[3] >= 1.0 - relative_edge_margin
            ):
                continue
            confidence = round(min(0.99, 0.5 + (scope_page_fraction * 0.5)), 3)
            recurrence_basis = [
                "normalized_text",
                "relative_position",
                "page_edge_band",
                f"min_pages={min_pages}",
                f"min_page_fraction={min_page_fraction:.2f}",
                f"relative_edge_margin={relative_edge_margin:.2f}",
            ]
            if orientation is not None:
                recurrence_basis.append(f"orientation={orientation}")
            clusters.append(
                PageFurnitureCluster(
                    cluster_id=cluster_id,
                    normalized_text_key=normalized_text,
                    representative_text=text_group[0].raw_text,
                    observation_ids=[observation.observation_id for observation in text_group],
                    page_nums=page_nums,
                    occurrence_count=len(text_group),
                    page_fraction=round(page_fraction, 3),
                    recurrence_scope=recurrence_scope,
                    scope_page_count=scope_page_count,
                    scope_page_fraction=round(scope_page_fraction, 3),
                    representative_bbox=representative_bbox,
                    representative_relative_bbox=representative_relative_bbox,
                    recurrence_basis=recurrence_basis,
                    confidence=confidence,
                )
            )

            for page_num in page_nums:
                page_observations = [observation for observation in text_group if observation.page_num == page_num]
                regions.append(
                    PageFurnitureRegion(
                        region_id=f"{cluster_id}-page-{page_num}",
                        cluster_id=cluster_id,
                        page_num=page_num,
                        bbox=(
                            min(observation.bbox[0] for observation in page_observations),
                            min(observation.bbox[1] for observation in page_observations),
                            max(observation.bbox[2] for observation in page_observations),
                            max(observation.bbox[3] for observation in page_observations),
                        ),
                        relative_bbox=(
                            min(observation.relative_bbox[0] for observation in page_observations),
                            min(observation.relative_bbox[1] for observation in page_observations),
                            max(observation.relative_bbox[2] for observation in page_observations),
                            max(observation.relative_bbox[3] for observation in page_observations),
                        ),
                        source_observation_ids=[observation.observation_id for observation in page_observations],
                        confidence=confidence,
                    )
                )

    return clusters, regions


def paper_page_furniture_to_payload(furniture: PaperPageFurniture) -> dict[str, object]:
    """Serialize paper page furniture as a JSON-friendly record."""
    return furniture.model_dump(mode="json")
