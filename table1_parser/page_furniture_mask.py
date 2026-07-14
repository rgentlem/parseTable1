"""Geometry helpers for applying repeated page-furniture masks."""

from __future__ import annotations

from dataclasses import dataclass

from table1_parser.schemas import PaperPageFurniture

BBox = tuple[float, float, float, float]


@dataclass(slots=True)
class PageFurnitureRowFilterResult:
    """Rows and aligned geometry after page-furniture row masking."""

    raw_rows: list[list[str]]
    cell_bboxes: list[list[BBox | None]]
    row_bounds: list[tuple[float, float]]
    metadata: dict[str, object] | None


def bbox_overlap_fraction(bbox: BBox, other_bbox: BBox) -> float:
    """Return the fraction of `bbox` covered by `other_bbox`."""
    left, top, right, bottom = bbox
    other_left, other_top, other_right, other_bottom = other_bbox
    width = right - left
    height = bottom - top
    if width <= 0.0 or height <= 0.0:
        return 0.0
    overlap_width = min(right, other_right) - max(left, other_left)
    overlap_height = min(bottom, other_bottom) - max(top, other_top)
    if overlap_width <= 0.0 or overlap_height <= 0.0:
        return 0.0
    return (overlap_width * overlap_height) / (width * height)


def page_furniture_cluster_ids_for_bbox(
    paper_page_furniture: PaperPageFurniture | None,
    *,
    page_num: int | None,
    bbox: BBox | None,
    min_overlap_fraction: float = 0.0,
) -> list[str]:
    """Return repeated page-furniture clusters whose region overlaps `bbox`."""
    if paper_page_furniture is None or page_num is None or bbox is None:
        return []
    left, top, right, bottom = bbox
    if right <= left or bottom <= top:
        return []
    cluster_ids: set[str] = set()
    for region in paper_page_furniture.ignored_regions:
        if region.page_num != page_num:
            continue
        overlap_fraction = bbox_overlap_fraction(bbox, region.bbox)
        if overlap_fraction > 0.0 and overlap_fraction >= min_overlap_fraction:
            cluster_ids.add(region.cluster_id)
    return sorted(cluster_ids)


def filter_positioned_items_for_page_furniture(
    items: list[dict[str, object]],
    paper_page_furniture: PaperPageFurniture | None,
    *,
    page_num: int | None = None,
    min_overlap_fraction: float = 0.8,
) -> tuple[list[dict[str, object]], dict[str, object] | None]:
    """Remove positioned word/char records mostly inside ignored furniture regions."""
    if paper_page_furniture is None or not paper_page_furniture.ignored_regions or not items:
        return items, None

    filtered_items: list[dict[str, object]] = []
    removed_count = 0
    source_line_removed_count = 0
    bbox_removed_count = 0
    removed_cluster_ids: set[str] = set()
    observations_by_id = {
        observation.observation_id: observation
        for observation in paper_page_furniture.observations
    }
    source_line_clusters: dict[tuple[int, int, int], set[str]] = {}
    for region in paper_page_furniture.ignored_regions:
        for observation_id in region.source_observation_ids:
            observation = observations_by_id.get(observation_id)
            if (
                observation is None
                or observation.block_index is None
                or observation.line_index is None
            ):
                continue
            source_line_clusters.setdefault(
                (observation.page_num, observation.block_index, observation.line_index),
                set(),
            ).add(region.cluster_id)

    for item in items:
        item_page_num = page_num
        if item_page_num is None and isinstance(item.get("page_num"), int):
            item_page_num = int(item["page_num"])
        block_index = item.get("block_index")
        line_index = item.get("line_index")
        if (
            item_page_num is not None
            and isinstance(block_index, int)
            and isinstance(line_index, int)
        ):
            match_basis = "source_line"
            cluster_ids = sorted(
                source_line_clusters.get((item_page_num, block_index, line_index), set())
            )
        else:
            match_basis = "bbox"
            bbox = _bbox_from_positioned_item(item)
            cluster_ids = page_furniture_cluster_ids_for_bbox(
                paper_page_furniture,
                page_num=item_page_num,
                bbox=bbox,
                min_overlap_fraction=min_overlap_fraction,
            )
        if cluster_ids:
            removed_count += 1
            if match_basis == "source_line":
                source_line_removed_count += 1
            else:
                bbox_removed_count += 1
            removed_cluster_ids.update(cluster_ids)
            continue
        filtered_items.append(item)

    if removed_count == 0:
        return items, None
    return filtered_items, {
        "source_artifact": "paper_page_furniture.json",
        "removed_count": removed_count,
        "kept_count": len(filtered_items),
        "removed_cluster_ids": sorted(removed_cluster_ids),
        "source_line_removed_count": source_line_removed_count,
        "bbox_removed_count": bbox_removed_count,
        "bbox_min_overlap_fraction": min_overlap_fraction if bbox_removed_count else None,
    }


# This helper is intentionally separated from the extractor even though the
# current call site is narrow: row/geometry alignment is easy to get wrong and
# should stay isolated from table-candidate orchestration.
def filter_table_rows_for_page_furniture(
    raw_rows: list[list[str]],
    *,
    cell_bboxes: list[list[BBox | None]],
    row_bounds: list[tuple[float, float]],
    paper_page_furniture: PaperPageFurniture | None,
    page_num: int,
    min_overlap_fraction: float = 0.8,
) -> PageFurnitureRowFilterResult:
    """Remove explicit-grid rows whose populated cells are mostly furniture."""
    if paper_page_furniture is None or not paper_page_furniture.ignored_regions or not raw_rows:
        return PageFurnitureRowFilterResult(raw_rows, cell_bboxes, row_bounds, None)

    kept_rows: list[list[str]] = []
    kept_bboxes: list[list[BBox | None]] = []
    kept_bounds: list[tuple[float, float]] = []
    removed_rows: list[dict[str, object]] = []
    removed_cluster_ids: set[str] = set()
    for row_idx, row in enumerate(raw_rows):
        row_bboxes = cell_bboxes[row_idx] if row_idx < len(cell_bboxes) else []
        populated = [(col_idx, str(cell).strip()) for col_idx, cell in enumerate(row) if str(cell).strip()]
        populated_bboxes = [
            (col_idx, row_bboxes[col_idx])
            for col_idx, _text in populated
            if col_idx < len(row_bboxes) and row_bboxes[col_idx] is not None
        ]
        row_cluster_ids: set[str] = set()
        overlap_count = 0
        for _col_idx, bbox in populated_bboxes:
            cluster_ids = page_furniture_cluster_ids_for_bbox(
                paper_page_furniture,
                page_num=page_num,
                bbox=bbox,
                min_overlap_fraction=min_overlap_fraction,
            )
            if cluster_ids:
                overlap_count += 1
                row_cluster_ids.update(cluster_ids)
        bbox_coverage = len(populated_bboxes) / len(populated) if populated else 0.0
        remove_row = (
            bool(populated_bboxes)
            and bbox_coverage >= min_overlap_fraction
            and overlap_count / len(populated_bboxes) >= min_overlap_fraction
        )
        if remove_row:
            removed_cluster_ids.update(row_cluster_ids)
            removed_rows.append(
                {
                    "row_idx": row_idx,
                    "text": " ".join(text for _col_idx, text in populated),
                    "cluster_ids": sorted(row_cluster_ids),
                }
            )
            continue
        kept_rows.append(row)
        if cell_bboxes:
            kept_bboxes.append(row_bboxes)
        if row_bounds and row_idx < len(row_bounds):
            kept_bounds.append(row_bounds[row_idx])

    if not removed_rows:
        return PageFurnitureRowFilterResult(raw_rows, cell_bboxes, row_bounds, None)
    return PageFurnitureRowFilterResult(
        kept_rows,
        kept_bboxes if cell_bboxes else cell_bboxes,
        kept_bounds if row_bounds else row_bounds,
        {
            "source_artifact": "paper_page_furniture.json",
            "removed_row_count": len(removed_rows),
            "removed_rows": removed_rows,
            "removed_cluster_ids": sorted(removed_cluster_ids),
            "min_overlap_fraction": min_overlap_fraction,
        },
    )


def _bbox_from_positioned_item(item: dict[str, object]) -> BBox | None:
    """Return a page-coordinate bbox from a normalized word/char record."""
    try:
        return (
            float(item["x0"]),
            float(item["top"]),
            float(item["x1"]),
            float(item["bottom"]),
        )
    except (KeyError, TypeError, ValueError):
        return None
