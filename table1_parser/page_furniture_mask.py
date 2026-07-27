"""Apply the accepted repeated-page-furniture source-line mask."""

from __future__ import annotations

from table1_parser.schemas import PaperPageFurniture

BBox = tuple[float, float, float, float]


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


def page_furniture_rule_cluster_id(
    segment: BBox,
    page_num: int,
    paper_page_furniture: PaperPageFurniture | None,
) -> str | None:
    """Return the accepted furniture cluster that exactly contains a rule."""
    if paper_page_furniture is None:
        return None

    segment_left = min(float(segment[0]), float(segment[2]))
    segment_top = min(float(segment[1]), float(segment[3]))
    segment_right = max(float(segment[0]), float(segment[2]))
    segment_bottom = max(float(segment[1]), float(segment[3]))
    for region in paper_page_furniture.ignored_rule_regions:
        if region.page_num != page_num:
            continue
        region_left = min(float(region.bbox[0]), float(region.bbox[2]))
        region_top = min(float(region.bbox[1]), float(region.bbox[3]))
        region_right = max(float(region.bbox[0]), float(region.bbox[2]))
        region_bottom = max(float(region.bbox[1]), float(region.bbox[3]))
        if (
            region_left <= segment_left
            and region_top <= segment_top
            and segment_right <= region_right
            and segment_bottom <= region_bottom
        ):
            return region.rule_cluster_id
    return None


def page_furniture_source_line_ids(
    paper_page_furniture: PaperPageFurniture | None,
) -> frozenset[str]:
    """Return the exact source-line IDs accepted as repeated page furniture."""
    if paper_page_furniture is None:
        return frozenset()
    return frozenset(
        source_line_id
        for region in paper_page_furniture.ignored_regions
        for source_line_id in region.source_observation_ids
    )


def filter_positioned_items_for_page_furniture(
    items: list[dict[str, object]],
    paper_page_furniture: PaperPageFurniture | None,
) -> tuple[list[dict[str, object]], dict[str, object] | None]:
    """Remove word/char records owned by an accepted furniture source line."""
    source_line_ids = page_furniture_source_line_ids(paper_page_furniture)
    if not source_line_ids or not items:
        return items, None

    filtered_items: list[dict[str, object]] = []
    removed_count = 0
    for item in items:
        source_line_id = item.get("source_line_id")
        if isinstance(source_line_id, str) and source_line_id in source_line_ids:
            removed_count += 1
            continue
        filtered_items.append(item)

    if removed_count == 0:
        return items, None
    return filtered_items, {
        "source_artifact": "paper_page_furniture.json",
        "match_basis": "exact_source_line_id",
        "removed_count": removed_count,
        "kept_count": len(filtered_items),
        "masked_source_line_ids": sorted(
            {
                str(item["source_line_id"])
                for item in items
                if isinstance(item.get("source_line_id"), str)
                and str(item["source_line_id"]) in source_line_ids
            }
        ),
    }
