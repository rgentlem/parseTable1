"""Build a layout-aware paper text stream from positioned PDF text."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from table1_parser.page_furniture_mask import page_furniture_cluster_ids_for_bbox
from table1_parser.paper_page_furniture import normalize_page_furniture_text
from table1_parser.schemas import (
    PaperPageFurniture,
    PaperPositionedDocument,
    PaperPositionedLine,
    PaperTextBlock,
    PaperTextLine,
    PaperTextOrientationGroup,
    PaperTextPage,
    PaperTextStream,
)
from table1_parser.text_cleaning import clean_text


BODY_TEXT_STYLE_MIN_FONT_SIZE = 5.0
BODY_TEXT_STYLE_MAX_FONT_SIZE = 18.0
TABLE_CAPTION_LINE_PATTERN = re.compile(r"^\s*table\s+[A-Za-z]?\d+[A-Za-z]?\b", re.IGNORECASE)


def build_paper_text_stream(
    pdf_path: str,
    *,
    paper_page_furniture: PaperPageFurniture | None = None,
    paper_positioned_document: PaperPositionedDocument | None = None,
    paper_id: str | None = None,
) -> PaperTextStream:
    """Build full-paper text ordered by page, orientation, source block, and column."""
    if paper_positioned_document is None:
        from table1_parser.context.paper_positioned_document import build_paper_positioned_document

        paper_positioned_document = build_paper_positioned_document(pdf_path, paper_id=paper_id)
    if paper_positioned_document.page_count <= 0:
        return PaperTextStream(
            paper_id=paper_id or Path(pdf_path).stem,
            source_pdf=Path(pdf_path).name,
            metadata={
                "diagnostics": ["positioned_document_unavailable"],
                "source_artifacts": ["paper_positioned_document.json"],
            },
        )

    stream_lines: list[PaperTextLine] = []
    stream_pages: list[PaperTextPage] = []
    font_style_counts: Counter[tuple[str, float]] = Counter()
    removed_furniture_line_count = 0
    furniture_text_keys, furniture_text_patterns = _page_furniture_text_matchers(paper_page_furniture)
    for page in paper_positioned_document.pages:
        page_line_records: list[dict[str, object]] = []
        removed_on_page = 0
        for positioned_line in page.lines:
            line_record = _line_record_from_positioned_line(positioned_line)
            if _is_page_furniture_text(line_record["text"], furniture_text_keys, furniture_text_patterns):
                removed_on_page += 1
                continue
            if page_furniture_cluster_ids_for_bbox(
                paper_page_furniture,
                page_num=page.page_num,
                bbox=line_record["bbox"],
                min_overlap_fraction=0.8,
            ):
                removed_on_page += 1
                continue
            page_line_records.append(line_record)

        records_by_orientation: dict[str, list[dict[str, object]]] = {
            "upright": [],
            "vertical_text_up": [],
            "vertical_text_down": [],
        }
        for record in page_line_records:
            orientation = _line_orientation(record.get("direction"))
            record["orientation"] = orientation
            records_by_orientation[orientation].append(record)

        ordered_groups: list[tuple[tuple[float, float], list[dict[str, object]]]] = []
        orientation_groups: list[PaperTextOrientationGroup] = []
        diagnostics = list(page.diagnostics)
        upright_columns: tuple[int, list[float], list[tuple[float, float]]] | None = None
        for orientation in ("upright", "vertical_text_up", "vertical_text_down"):
            source_records = records_by_orientation[orientation]
            if not source_records:
                continue
            group_id = f"page-{page.page_num}-orientation-{orientation}"
            source_left = min(float(record["bbox"][0]) for record in source_records)
            source_top = min(float(record["bbox"][1]) for record in source_records)
            source_right = max(float(record["bbox"][2]) for record in source_records)
            source_bottom = max(float(record["bbox"][3]) for record in source_records)
            group_source_bbox = (source_left, source_top, source_right, source_bottom)
            canonical_width = page.page_width if orientation == "upright" else source_bottom - source_top
            canonical_height = page.page_height if orientation == "upright" else source_right - source_left
            oriented_records: list[dict[str, object]] = []
            for record in source_records:
                record_source_bbox = record["bbox"]
                oriented_records.append(
                    {
                        **record,
                        "source_bbox": record_source_bbox,
                        "bbox": _canonical_bbox(
                            record_source_bbox,
                            orientation=orientation,
                            orientation_source_bbox=group_source_bbox,
                        ),
                        "orientation_group_id": group_id,
                    }
                )
            group_column_count, group_boundaries, group_bands, group_diagnostics = _detect_page_columns(
                oriented_records,
                canonical_width,
            )
            ordered_records = _order_page_blocks(oriented_records, group_boundaries, canonical_width)
            for record in ordered_records:
                record["group_column_count"] = group_column_count
            ordered_groups.append(((source_top, source_left), ordered_records))
            orientation_groups.append(
                PaperTextOrientationGroup(
                    group_id=group_id,
                    orientation=orientation,
                    source_bbox=group_source_bbox,
                    canonical_width=canonical_width,
                    canonical_height=canonical_height,
                    line_count=len(ordered_records),
                    column_count=group_column_count,
                    column_boundaries=group_boundaries,
                    column_bands=group_bands,
                )
            )
            diagnostics.extend(group_diagnostics)
            if orientation == "upright":
                upright_columns = (group_column_count, group_boundaries, group_bands)
            else:
                diagnostics.append(f"orientation_aware_ordering:{orientation}:lines={len(ordered_records)}")

        ordered_records = [
            record
            for _, group_records in sorted(ordered_groups, key=lambda item: item[0])
            for record in group_records
        ]
        if upright_columns is None:
            column_count, column_boundaries, column_bands = 1, [], [(0.0, page.page_width)]
        else:
            column_count, column_boundaries, column_bands = upright_columns
        for logical_index, record in enumerate(ordered_records):
            text = str(record["text"])
            column_index = int(record.get("column_index", 0))
            line_notes = list(record.get("notes", [])) if isinstance(record.get("notes"), list) else []
            if record.get("has_bold"):
                line_notes.append("has_bold_text")
            orientation = str(record.get("orientation") or "upright")
            if orientation != "upright":
                line_notes.append(f"orientation_group:{orientation}")
            for style_count in record.get("font_style_counts", []):
                if not isinstance(style_count, dict):
                    continue
                record_font = style_count.get("font")
                record_font_size = style_count.get("font_size")
                record_character_count = int(style_count.get("character_count", 0) or 0)
                if (
                    isinstance(record_font, str)
                    and isinstance(record_font_size, (int, float))
                    and record_character_count > 0
                    and BODY_TEXT_STYLE_MIN_FONT_SIZE <= float(record_font_size) <= BODY_TEXT_STYLE_MAX_FONT_SIZE
                ):
                    font_style_counts[(record_font, round(float(record_font_size), 1))] += record_character_count
            stream_lines.append(
                PaperTextLine(
                    line_id=str(record["source_line_id"]),
                    page_num=page.page_num,
                    block_index=int(record["block_index"]) if isinstance(record.get("block_index"), int) else None,
                    line_index=int(record["line_index"]) if isinstance(record.get("line_index"), int) else None,
                    raw_text=str(record["raw_text"]),
                    text=text,
                    bbox=record["source_bbox"],
                    canonical_bbox=record["bbox"],
                    direction=record.get("direction"),
                    orientation=orientation,
                    orientation_group_id=str(record["orientation_group_id"]),
                    column_index=column_index,
                    column_count=int(record["group_column_count"]),
                    role="body",
                    confidence=0.78,
                    dominant_font=str(record["dominant_font"]) if isinstance(record.get("dominant_font"), str) else None,
                    dominant_font_size=float(record["dominant_font_size"]) if isinstance(record.get("dominant_font_size"), (int, float)) else None,
                    spans=list(record.get("spans", [])) if isinstance(record.get("spans"), list) else [],
                    notes=line_notes,
                )
            )
        removed_furniture_line_count += removed_on_page
        stream_pages.append(
            PaperTextPage(
                page_num=page.page_num,
                page_width=page.page_width,
                page_height=page.page_height,
                column_count=column_count,
                column_boundaries=column_boundaries,
                column_bands=column_bands,
                line_count=len(ordered_records),
                removed_page_furniture_line_count=removed_on_page,
                orientation_groups=orientation_groups,
                diagnostics=list(dict.fromkeys(diagnostics)),
            )
        )

    total_style_characters = sum(font_style_counts.values())
    font_style_summary = [
        {
            "font": font,
            "font_size": font_size,
            "character_count": character_count,
            "character_fraction": character_count / total_style_characters if total_style_characters else 0.0,
        }
        for (font, font_size), character_count in font_style_counts.most_common()
    ]
    dominant_body_text_style = font_style_summary[0] if font_style_summary else None
    body_font_size = (
        dominant_body_text_style.get("font_size")
        if isinstance(dominant_body_text_style, dict)
        else None
    )
    classified_stream_lines: list[PaperTextLine] = []
    for line in stream_lines:
        visible_spans = [
            span
            for span in line.spans
            if isinstance(span, dict) and "".join(str(span.get("text", "")).split())
        ]
        is_heading = (
            visible_spans
            and all(
                "bold" in str(span.get("font") or "").lower()
                or "semibold" in str(span.get("font") or "").lower()
                or (isinstance(span.get("flags"), int) and bool(int(span["flags"]) & 16))
                for span in visible_spans
            )
            and isinstance(body_font_size, (int, float))
            and line.dominant_font_size is not None
            and line.block_index is not None
            and float(line.dominant_font_size) > float(body_font_size)
            and TABLE_CAPTION_LINE_PATTERN.match(line.text) is None
        )
        if is_heading:
            source_block_lines = [
                block_line
                for block_line in stream_lines
                if block_line.page_num == line.page_num
                and block_line.orientation_group_id == line.orientation_group_id
                and block_line.block_index == line.block_index
            ]
            source_block_visible_spans = [
                span
                for block_line in source_block_lines
                for span in block_line.spans
                if isinstance(span, dict) and "".join(str(span.get("text", "")).split())
            ]
            source_block_is_all_bold = bool(source_block_visible_spans) and all(
                "bold" in str(span.get("font") or "").lower()
                or "semibold" in str(span.get("font") or "").lower()
                or (isinstance(span.get("flags"), int) and bool(int(span["flags"]) & 16))
                for span in source_block_visible_spans
            )
            source_block_text = " ".join(block_line.text for block_line in source_block_lines)
            if source_block_is_all_bold and re.search(r"[.!?](?=\s|$)", source_block_text):
                is_heading = False
        if is_heading:
            classified_stream_lines.append(
                line.model_copy(
                    update={
                        "role": "heading",
                        "confidence": 0.86,
                        "notes": [*line.notes, "layout_section_heading"],
                    }
                )
            )
            continue
        classified_stream_lines.append(line)

    text_blocks: list[PaperTextBlock] = []
    current_block_lines: list[PaperTextLine] = []
    for line in [*classified_stream_lines, None]:
        if current_block_lines and (
            line is None
            or line.page_num != current_block_lines[-1].page_num
            or line.orientation_group_id != current_block_lines[-1].orientation_group_id
            or line.block_index != current_block_lines[-1].block_index
        ):
            block_roles = {block_line.role for block_line in current_block_lines}
            text_blocks.append(
                PaperTextBlock(
                    block_id=(
                        f"paper_text_block:page-{current_block_lines[0].page_num}:"
                        f"{current_block_lines[0].orientation}:"
                        f"{current_block_lines[0].block_index}"
                    ),
                    order=len(text_blocks),
                    page_num=current_block_lines[0].page_num,
                    source_block_index=current_block_lines[0].block_index,
                    orientation=current_block_lines[0].orientation,
                    bbox=(
                        min(block_line.bbox[0] for block_line in current_block_lines),
                        min(block_line.bbox[1] for block_line in current_block_lines),
                        max(block_line.bbox[2] for block_line in current_block_lines),
                        max(block_line.bbox[3] for block_line in current_block_lines),
                    ),
                    line_ids=[block_line.line_id for block_line in current_block_lines],
                    role=next(iter(block_roles)) if len(block_roles) == 1 else "mixed",
                    text="\n".join(block_line.text for block_line in current_block_lines),
                )
            )
            current_block_lines = []
        if line is not None:
            current_block_lines.append(line)

    return PaperTextStream(
        paper_id=paper_id or Path(pdf_path).stem,
        source_pdf=Path(pdf_path).name,
        lines=classified_stream_lines,
        blocks=text_blocks,
        pages=stream_pages,
        metadata={
            "source_artifacts": ["paper_positioned_document.json", "paper_page_furniture.json"],
            "line_count": len(stream_lines),
            "page_count": len(stream_pages),
            "removed_page_furniture_line_count": removed_furniture_line_count,
            "column_order": "page_then_orientation_group_then_source_block_column_then_block_top",
            "font_style_character_counts": font_style_summary,
            "dominant_body_text_style": dominant_body_text_style,
        },
    )


def paper_text_stream_to_markdown(blocks: list[PaperTextBlock]) -> str:
    """Render ordered paper text blocks as lightweight markdown."""
    markdown_lines: list[str] = []
    previous_page_num: int | None = None
    for block in blocks:
        if previous_page_num is not None and block.page_num != previous_page_num:
            markdown_lines.append("")
        previous_page_num = block.page_num
        if block.role == "heading":
            if markdown_lines and markdown_lines[-1] != "":
                markdown_lines.append("")
            markdown_lines.append(f"## {clean_text(block.text)}")
            markdown_lines.append("")
            continue
        markdown_lines.append(block.text)
    return "\n".join(markdown_lines).strip() + ("\n" if markdown_lines else "")


def _line_record_from_positioned_line(line: PaperPositionedLine) -> dict[str, object]:
    return {
        "source_line_id": line.line_id,
        "raw_text": line.raw_text,
        "text": line.text,
        "bbox": line.bbox,
        "direction": line.direction,
        "block_index": line.block_index,
        "line_index": line.line_index,
        "has_bold": line.has_bold,
        "dominant_font": line.dominant_font,
        "dominant_font_size": line.dominant_font_size,
        "dominant_style_character_count": line.dominant_style_character_count,
        "spans": [span.model_dump(mode="json") for span in line.spans],
        "font_style_counts": list(line.font_style_counts),
        "notes": list(line.notes),
    }


def _line_orientation(direction: object) -> str:
    if isinstance(direction, (list, tuple)) and len(direction) == 2:
        dx = float(direction[0])
        dy = float(direction[1])
        if abs(dy) > abs(dx):
            return "vertical_text_up" if dy < 0.0 else "vertical_text_down"
    return "upright"


def _canonical_bbox(
    bbox: object,
    *,
    orientation: str,
    orientation_source_bbox: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    left, top, right, bottom = (float(value) for value in bbox)
    source_left, source_top, source_right, source_bottom = orientation_source_bbox
    if orientation == "vertical_text_up":
        return (source_bottom - bottom, left - source_left, source_bottom - top, right - source_left)
    if orientation == "vertical_text_down":
        return (top - source_top, source_right - right, bottom - source_top, source_right - left)
    return (left, top, right, bottom)

def _page_furniture_text_matchers(
    paper_page_furniture: PaperPageFurniture | None,
) -> tuple[set[str], list[re.Pattern[str]]]:
    if paper_page_furniture is None:
        return set(), []
    exact_keys: set[str] = set()
    wildcard_patterns: list[re.Pattern[str]] = []
    for cluster in paper_page_furniture.clusters:
        key = " ".join(cluster.normalized_text_key.split())
        if not key:
            continue
        if "<page_num>" in key:
            continue
        exact_keys.add(key)
    return exact_keys, wildcard_patterns


def _is_page_furniture_text(
    text: object,
    exact_keys: set[str],
    wildcard_patterns: list[re.Pattern[str]],
) -> bool:
    if not exact_keys and not wildcard_patterns:
        return False
    normalized_text = normalize_page_furniture_text(clean_text(str(text)))
    return normalized_text in exact_keys or any(pattern.match(normalized_text) for pattern in wildcard_patterns)


def _detect_page_columns(
    line_records: list[dict[str, object]],
    page_width: float,
) -> tuple[int, list[float], list[tuple[float, float]], list[str]]:
    if len(line_records) < 8 or page_width <= 0.0:
        return 1, [], [(0.0, max(page_width, 1.0))], []
    caption_column_result = _detect_caption_aligned_columns(line_records, page_width)
    if caption_column_result is not None:
        return caption_column_result
    candidate_records = [
        record
        for record in line_records
        if (
            page_width * 0.15 <= _bbox_width(record["bbox"]) <= page_width * 0.68
            and not _is_full_width_record(record, page_width)
        )
    ]
    if len(candidate_records) < 8:
        return 1, [], [(0.0, page_width)], []

    x_starts = sorted(float(record["bbox"][0]) for record in candidate_records)
    gap_threshold = max(45.0, page_width * 0.07)
    x_start_groups: list[list[float]] = []
    active_group: list[float] = []
    for x_start in x_starts:
        if active_group and x_start - active_group[-1] >= gap_threshold:
            x_start_groups.append(active_group)
            active_group = []
        active_group.append(x_start)
    if active_group:
        x_start_groups.append(active_group)
    if len(x_start_groups) <= 1 or any(len(group) < 4 for group in x_start_groups):
        return 1, [], [(0.0, page_width)], []

    column_boundaries = [
        (max(left_group) + min(right_group)) / 2.0
        for left_group, right_group in zip(x_start_groups, x_start_groups[1:])
    ]
    column_groups: list[list[dict[str, object]]] = [[] for _ in x_start_groups]
    for record in candidate_records:
        column_index = sum(float(record["bbox"][0]) >= boundary for boundary in column_boundaries)
        column_groups[column_index].append(record)
    if any(len(group) < 4 for group in column_groups):
        return 1, [], [(0.0, page_width)], []

    column_bands: list[tuple[float, float]] = []
    band_left = 0.0
    for boundary in column_boundaries:
        column_bands.append((band_left, boundary))
        band_left = boundary
    column_bands.append((band_left, page_width))

    column_count = len(column_bands)
    diagnostics = [f"{column_count}_column_layout_detected"]
    return column_count, column_boundaries, column_bands, diagnostics


def _detect_caption_aligned_columns(
    line_records: list[dict[str, object]],
    page_width: float,
) -> tuple[int, list[float], list[tuple[float, float]], list[str]] | None:
    caption_records = [
        record
        for record in line_records
        if TABLE_CAPTION_LINE_PATTERN.match(str(record.get("text", "")))
        and not _is_full_width_record(record, page_width)
    ]
    if len(caption_records) < 2:
        return None
    caption_rows: list[list[dict[str, object]]] = []
    for record in sorted(caption_records, key=lambda item: (float(item["bbox"][1]), float(item["bbox"][0]))):
        top = float(record["bbox"][1])
        if not caption_rows or abs(top - float(caption_rows[-1][0]["bbox"][1])) > 18.0:
            caption_rows.append([record])
            continue
        caption_rows[-1].append(record)
    for caption_row in caption_rows:
        if len(caption_row) < 2:
            continue
        ordered = sorted(caption_row, key=lambda item: float(item["bbox"][0]))
        if float(ordered[-1]["bbox"][0]) - float(ordered[0]["bbox"][0]) < page_width * 0.25:
            continue
        boundaries = [
            (float(left_record["bbox"][2]) + float(right_record["bbox"][0])) / 2.0
            for left_record, right_record in zip(ordered, ordered[1:])
            if float(right_record["bbox"][0]) > float(left_record["bbox"][2])
        ]
        if len(boundaries) != len(ordered) - 1:
            continue
        column_bands: list[tuple[float, float]] = []
        band_left = 0.0
        for boundary in boundaries:
            column_bands.append((band_left, boundary))
            band_left = boundary
        column_bands.append((band_left, page_width))
        return (
            len(column_bands),
            boundaries,
            column_bands,
            [f"{len(column_bands)}_column_layout_detected", "caption_aligned_column_detection"],
        )
    return None


def _order_page_blocks(
    line_records: list[dict[str, object]],
    column_boundaries: list[float],
    page_width: float,
) -> list[dict[str, object]]:
    source_blocks: dict[int, list[dict[str, object]]] = {}
    for record_order, record in enumerate(line_records):
        block_index = record.get("block_index")
        source_blocks.setdefault(
            int(block_index) if isinstance(block_index, int) else -(record_order + 1),
            [],
        ).append(record)
    ordered_blocks: list[dict[str, object]] = []
    for block_index, block_records in source_blocks.items():
        source_ordered_records = sorted(
            block_records,
            key=lambda record: (
                int(record["line_index"])
                if isinstance(record.get("line_index"), int)
                else 10**9
            ),
        )
        ordered_blocks.append(
            {
                "block_index": block_index,
                "bbox": (
                    min(float(record["bbox"][0]) for record in source_ordered_records),
                    min(float(record["bbox"][1]) for record in source_ordered_records),
                    max(float(record["bbox"][2]) for record in source_ordered_records),
                    max(float(record["bbox"][3]) for record in source_ordered_records),
                ),
                "records": source_ordered_records,
            }
        )

    column_count = len(column_boundaries) + 1
    if column_count <= 1:
        output_records: list[dict[str, object]] = []
        for block in sorted(
            ordered_blocks,
            key=lambda item: (
                float(item["bbox"][1]),
                float(item["bbox"][0]),
                int(item["block_index"]),
            ),
        ):
            for record in block["records"]:
                record["column_index"] = 0
                output_records.append(record)
        return output_records

    top_full_width: list[dict[str, object]] = []
    bottom_full_width: list[dict[str, object]] = []
    column_blocks: list[dict[str, object]] = []
    non_full_blocks = [
        block
        for block in ordered_blocks
        if not _is_full_width_record(block, page_width)
    ]
    min_column_top = min((float(block["bbox"][1]) for block in non_full_blocks), default=0.0)
    max_column_bottom = max((float(block["bbox"][3]) for block in non_full_blocks), default=0.0)
    for block in ordered_blocks:
        if _is_full_width_record(block, page_width):
            for record in block["records"]:
                record["column_index"] = 0
                record.setdefault("notes", []).append("full_width_line")
            if float(block["bbox"][3]) <= min_column_top:
                top_full_width.append(block)
            elif float(block["bbox"][1]) >= max_column_bottom:
                bottom_full_width.append(block)
            else:
                column_blocks.append(block)
            continue
        column_index = sum(float(block["bbox"][0]) >= boundary for boundary in column_boundaries)
        for record in block["records"]:
            record["column_index"] = column_index
        block["column_index"] = column_index
        column_blocks.append(block)

    ordered_output_blocks: list[dict[str, object]] = []
    ordered_output_blocks.extend(
        sorted(
            top_full_width,
            key=lambda block: (float(block["bbox"][1]), float(block["bbox"][0])),
        )
    )
    for column_index in range(column_count):
        ordered_output_blocks.extend(
            sorted(
                [block for block in column_blocks if int(block.get("column_index", 0)) == column_index],
                key=lambda block: (float(block["bbox"][1]), float(block["bbox"][0])),
            )
        )
    ordered_output_blocks.extend(
        sorted(
            bottom_full_width,
            key=lambda block: (float(block["bbox"][1]), float(block["bbox"][0])),
        )
    )
    return [
        record
        for block in ordered_output_blocks
        for record in block["records"]
    ]

def _bbox_width(bbox: object) -> float:
    left, _top, right, _bottom = bbox
    return float(right) - float(left)


def _is_full_width_record(record: dict[str, object], page_width: float) -> bool:
    bbox = record["bbox"]
    width_fraction = _bbox_width(bbox) / page_width if page_width > 0.0 else 0.0
    return width_fraction >= 0.72 and float(bbox[0]) <= page_width * 0.22 and float(bbox[2]) >= page_width * 0.78
