"""Build the canonical paper document from positioned PDF text."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from table1_parser.context.paper_positioned_document import canonical_bbox_for_orientation
from table1_parser.page_furniture_mask import page_furniture_cluster_ids_for_bbox
from table1_parser.paper_bibliography import (
    bibliography_item_evidence_for_block,
    build_numbered_bibliography_entries_from_region,
    build_unnumbered_bibliography_entries_from_layout_lines,
)
from table1_parser.paper_page_furniture import normalize_page_furniture_text
from table1_parser.reference_sections import (
    INLINE_REFERENCE_START_PATTERN,
    REFERENCE_HEADING_LINE_PATTERN,
    reference_start_text,
)
from table1_parser.schemas import (
    BibliographyEntry,
    PaperPageFurniture,
    PaperPositionedDocument,
    PaperPositionedLine,
    PaperPositionedVisualComponent,
)
from table1_parser.text_cleaning import clean_text


BODY_TEXT_STYLE_MIN_FONT_SIZE = 5.0
BODY_TEXT_STYLE_MAX_FONT_SIZE = 18.0
TABLE_CAPTION_LINE_PATTERN = re.compile(r"^\s*table\s+[A-Za-z]?\d+[A-Za-z]?\b", re.IGNORECASE)
FIGURE_CAPTION_BLOCK_PATTERN = re.compile(
    r"^\s*(?P<label>(?:Fig\.|Figure)\s*[A-Za-z]?\d+[A-Za-z]?)\b",
    re.IGNORECASE,
)


def build_paper_document(
    pdf_path: str,
    *,
    paper_page_furniture: PaperPageFurniture | None = None,
    paper_positioned_document: PaperPositionedDocument | None = None,
    paper_id: str | None = None,
) -> tuple[dict[str, object], list[BibliographyEntry]]:
    """Build canonical block ownership from positioned layout evidence."""
    if paper_positioned_document is None:
        from table1_parser.context.paper_positioned_document import build_paper_positioned_document

        paper_positioned_document = build_paper_positioned_document(pdf_path, paper_id=paper_id)
    if paper_positioned_document.page_count <= 0:
        return {
            "paper_id": paper_id or Path(pdf_path).stem,
            "source_pdf": Path(pdf_path).name,
            "pages": [],
            "blocks": [],
            "structure": [],
            "prose": {"segments": []},
            "entities": [],
            "unassigned_block_ids": [],
            "bibliography_region_candidates": [],
            "figure_scope_rejections": [],
        }, []

    stream_lines: list[SimpleNamespace] = []
    stream_pages: list[SimpleNamespace] = []
    font_style_counts: Counter[tuple[str, float]] = Counter()
    removed_furniture_line_count = 0
    furniture_text_keys, furniture_text_patterns = _page_furniture_text_matchers(paper_page_furniture)
    for page in paper_positioned_document.pages:
        page_line_records: list[dict[str, object]] = []
        leading_digit_bboxes_by_line: dict[
            tuple[int, int], tuple[float, float, float, float]
        ] = {}
        for char in sorted(page.chars, key=lambda value: value.char_index):
            if (
                char.block_index is not None
                and char.line_index is not None
                and char.text.isdigit()
            ):
                leading_digit_bboxes_by_line.setdefault(
                    (char.block_index, char.line_index),
                    (char.x0, char.top, char.x1, char.bottom),
                )
        removed_on_page = 0
        for positioned_line in page.lines:
            line_record = _line_record_from_positioned_line(positioned_line)
            line_record["leading_digit_bbox"] = leading_digit_bboxes_by_line.get(
                (positioned_line.block_index, positioned_line.line_index)
                if positioned_line.block_index is not None
                and positioned_line.line_index is not None
                else (-1, -1)
            )
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
        orientation_groups: list[SimpleNamespace] = []
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
                leading_digit_bbox = record.get("leading_digit_bbox")
                canonical_leading_digit_bbox = (
                    canonical_bbox_for_orientation(
                        leading_digit_bbox,
                        orientation=orientation,
                        orientation_source_bbox=group_source_bbox,
                    )
                    if isinstance(leading_digit_bbox, tuple)
                    else None
                )
                oriented_records.append(
                    {
                        **record,
                        "source_bbox": record_source_bbox,
                        "bbox": canonical_bbox_for_orientation(
                            record_source_bbox,
                            orientation=orientation,
                            orientation_source_bbox=group_source_bbox,
                        ),
                        "leading_digit_width": (
                            canonical_leading_digit_bbox[2]
                            - canonical_leading_digit_bbox[0]
                            if canonical_leading_digit_bbox is not None
                            else None
                        ),
                        "orientation_group_id": group_id,
                    }
                )
            source_block_records: dict[int, list[dict[str, object]]] = {}
            source_block_orders: dict[int, int] = {}
            for record_order, record in enumerate(oriented_records):
                block_index = record.get("block_index")
                source_block_key = (
                    int(block_index)
                    if isinstance(block_index, int)
                    else -(record_order + 1)
                )
                source_block_records.setdefault(source_block_key, []).append(record)
                source_block_orders.setdefault(source_block_key, record_order)
            source_blocks: list[dict[str, object]] = []
            for source_block_key, block_records in source_block_records.items():
                source_ordered_records = sorted(
                    block_records,
                    key=lambda record: (
                        int(record["line_index"])
                        if isinstance(record.get("line_index"), int)
                        else 10**9
                    ),
                )
                source_blocks.append(
                    {
                        "block_index": source_block_key,
                        "source_block_index": source_ordered_records[0].get("block_index"),
                        "source_order": source_block_orders[source_block_key],
                        "page_num": page.page_num,
                        "orientation": orientation,
                        "orientation_group_id": group_id,
                        "source_bbox": (
                            min(float(record["source_bbox"][0]) for record in source_ordered_records),
                            min(float(record["source_bbox"][1]) for record in source_ordered_records),
                            max(float(record["source_bbox"][2]) for record in source_ordered_records),
                            max(float(record["source_bbox"][3]) for record in source_ordered_records),
                        ),
                        "bbox": (
                            min(float(record["bbox"][0]) for record in source_ordered_records),
                            min(float(record["bbox"][1]) for record in source_ordered_records),
                            max(float(record["bbox"][2]) for record in source_ordered_records),
                            max(float(record["bbox"][3]) for record in source_ordered_records),
                        ),
                        "line_ids": [
                            str(record["source_line_id"])
                            for record in source_ordered_records
                        ],
                        "text": "\n".join(
                            str(record["text"])
                            for record in source_ordered_records
                        ),
                        "records": source_ordered_records,
                    }
                )
            group_column_count, group_boundaries, group_bands, group_diagnostics = _detect_page_columns(
                oriented_records,
                canonical_width,
            )
            ordered_records = _order_page_blocks(source_blocks, group_boundaries, canonical_width)
            for record in ordered_records:
                record["group_column_count"] = group_column_count
            ordered_groups.append(((source_top, source_left), ordered_records))
            orientation_groups.append(
                SimpleNamespace(
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
                SimpleNamespace(
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
                    leading_digit_width=(
                        float(record["leading_digit_width"])
                        if isinstance(record.get("leading_digit_width"), (int, float))
                        else None
                    ),
                    spans=list(record.get("spans", [])) if isinstance(record.get("spans"), list) else [],
                    notes=line_notes,
                )
            )
        removed_furniture_line_count += removed_on_page
        stream_pages.append(
            SimpleNamespace(
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
    classified_stream_lines: list[SimpleNamespace] = []
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
                SimpleNamespace(
                    **{
                        **vars(line),
                        "role": "heading",
                        "confidence": 0.86,
                        "notes": [*line.notes, "layout_section_heading"],
                    }
                )
            )
            continue
        classified_stream_lines.append(line)

    text_blocks: list[SimpleNamespace] = []
    current_block_lines: list[SimpleNamespace] = []
    for line in [*classified_stream_lines, None]:
        if current_block_lines and (
            line is None
            or line.page_num != current_block_lines[-1].page_num
            or line.orientation_group_id != current_block_lines[-1].orientation_group_id
            or line.block_index != current_block_lines[-1].block_index
        ):
            block_roles = {block_line.role for block_line in current_block_lines}
            text_blocks.append(
                SimpleNamespace(
                    block_id=(
                        f"paper_text_block:page-{current_block_lines[0].page_num}:"
                        f"{current_block_lines[0].orientation}:"
                        f"{current_block_lines[0].block_index}"
                    ),
                    order=len(text_blocks),
                    page_num=current_block_lines[0].page_num,
                    source_block_index=current_block_lines[0].block_index,
                    orientation=current_block_lines[0].orientation,
                    orientation_group_id=current_block_lines[0].orientation_group_id,
                    bbox=(
                        min(block_line.bbox[0] for block_line in current_block_lines),
                        min(block_line.bbox[1] for block_line in current_block_lines),
                        max(block_line.bbox[2] for block_line in current_block_lines),
                        max(block_line.bbox[3] for block_line in current_block_lines),
                    ),
                    canonical_bbox=(
                        min(block_line.canonical_bbox[0] for block_line in current_block_lines if block_line.canonical_bbox is not None),
                        min(block_line.canonical_bbox[1] for block_line in current_block_lines if block_line.canonical_bbox is not None),
                        max(block_line.canonical_bbox[2] for block_line in current_block_lines if block_line.canonical_bbox is not None),
                        max(block_line.canonical_bbox[3] for block_line in current_block_lines if block_line.canonical_bbox is not None),
                    ),
                    column_index=current_block_lines[0].column_index,
                    column_count=current_block_lines[0].column_count,
                    line_ids=[block_line.line_id for block_line in current_block_lines],
                    role=next(iter(block_roles)) if len(block_roles) == 1 else "mixed",
                    text="\n".join(block_line.text for block_line in current_block_lines),
                )
            )
            current_block_lines = []
        if line is not None:
            current_block_lines.append(line)

    lines_by_id = {line.line_id: line for line in classified_stream_lines}
    blocks: list[SimpleNamespace] = []
    for block in text_blocks:
        block_lines = [lines_by_id[line_id] for line_id in block.line_ids]
        segments: list[list[SimpleNamespace]] = []
        segment: list[SimpleNamespace] = []
        for line in block_lines:
            if (
                segment
                and line.role != segment[-1].role
                and {line.role, segment[-1].role} == {"heading", "body"}
            ):
                segments.append(segment)
                segment = []
            segment.append(line)
        if segment:
            segments.append(segment)
        for segment_index, segment_lines in enumerate(segments):
            roles = {line.role for line in segment_lines}
            blocks.append(
                SimpleNamespace(
                    **{
                        **vars(block),
                        "block_id": (
                            block.block_id
                            if len(segments) == 1
                            else f"{block.block_id}:segment-{segment_index + 1}"
                        ),
                        "order": len(blocks),
                        "bbox": (
                            min(line.bbox[0] for line in segment_lines),
                            min(line.bbox[1] for line in segment_lines),
                            max(line.bbox[2] for line in segment_lines),
                            max(line.bbox[3] for line in segment_lines),
                        ),
                        "canonical_bbox": (
                            min(line.canonical_bbox[0] for line in segment_lines),
                            min(line.canonical_bbox[1] for line in segment_lines),
                            max(line.canonical_bbox[2] for line in segment_lines),
                            max(line.canonical_bbox[3] for line in segment_lines),
                        ),
                        "line_ids": [line.line_id for line in segment_lines],
                        "role": next(iter(roles)) if len(roles) == 1 else "mixed",
                        "text": "\n".join(line.text for line in segment_lines),
                    }
                )
            )

    figure_scope_candidates: list[dict[str, object]] = []
    source_ordered_blocks = sorted(
        blocks,
        key=lambda block: (
            block.page_num,
            block.source_block_index is None,
            block.source_block_index or 0,
            block.order,
        ),
    )
    for anchor_index, anchor in enumerate(source_ordered_blocks):
        caption_match = FIGURE_CAPTION_BLOCK_PATTERN.match(anchor.text)
        if caption_match is None:
            continue
        following_blocks: list[SimpleNamespace] = []
        for block in source_ordered_blocks[anchor_index + 1 :]:
            if (
                block.page_num != anchor.page_num
                or block.bbox[1] >= anchor.bbox[3]
                or block.bbox[3] <= anchor.bbox[1]
                or FIGURE_CAPTION_BLOCK_PATTERN.match(block.text)
            ):
                break
            following_blocks.append(block)
        ambiguous = len(following_blocks) > 1
        caption_blocks = [anchor] if ambiguous else [anchor, *following_blocks]
        figure_scope_candidates.append(
            {
                "candidate_id": f"figure-scope:{anchor.block_id}",
                "page_num": anchor.page_num,
                "figure_label": caption_match.group("label"),
                "caption_block_ids": [block.block_id for block in caption_blocks],
                "visual_component_ids": [],
                "internal_block_ids": [],
                "content_bbox": None,
                "composite_bbox": None,
                "structural_evidence": [
                    "block_leading_figure_label",
                    *(
                        ["consecutive_source_order", "positive_vertical_overlap"]
                        if len(caption_blocks) > 1
                        else []
                    ),
                ],
                "concerns": ["ambiguous_caption_assembly"] if ambiguous else [],
            }
        )

    blocks_by_id = {block.block_id: block for block in blocks}
    positioned_pages = {
        page.page_num: page for page in paper_positioned_document.pages
    }
    component_pages_by_signature: dict[
        tuple[str, tuple[float, float, float, float]], set[int]
    ] = {}
    for page_num, page in positioned_pages.items():
        for component in page.visual_components:
            component_pages_by_signature.setdefault(
                (component.component_kind, component.bbox), set()
            ).add(page_num)
    page_furniture_cluster_pages = (
        {
            cluster.cluster_id: set(cluster.page_nums)
            for cluster in paper_page_furniture.clusters
        }
        if paper_page_furniture is not None
        else {}
    )
    figure_eligible_components_by_page: dict[
        int, list[PaperPositionedVisualComponent]
    ] = {}
    for page_num, page in positioned_pages.items():
        page_furniture_regions = (
            [
                region
                for region in paper_page_furniture.ignored_regions
                if region.page_num == page_num
            ]
            if paper_page_furniture is not None
            else []
        )
        eligible_components: list[PaperPositionedVisualComponent] = []
        for component in page.visual_components:
            component_page_nums = component_pages_by_signature[
                (component.component_kind, component.bbox)
            ]
            represents_page_furniture = False
            for region in page_furniture_regions:
                cluster_page_nums = page_furniture_cluster_pages.get(
                    region.cluster_id, set()
                )
                recurs_with_cluster = bool(cluster_page_nums) and (
                    cluster_page_nums <= component_page_nums
                )
                overlaps_region = (
                    component.bbox[0] < region.bbox[2]
                    and component.bbox[2] > region.bbox[0]
                    and component.bbox[1] < region.bbox[3]
                    and component.bbox[3] > region.bbox[1]
                )
                if recurs_with_cluster and overlaps_region:
                    represents_page_furniture = True
                    break
            if not represents_page_furniture:
                eligible_components.append(component)
        figure_eligible_components_by_page[page_num] = eligible_components
    component_proposals: dict[str, list[PaperPositionedVisualComponent]] = {}
    caption_bboxes: dict[str, tuple[float, float, float, float]] = {}
    for candidate in figure_scope_candidates:
        caption_blocks = [
            blocks_by_id[block_id] for block_id in candidate["caption_block_ids"]
        ]
        caption_bbox = (
            min(block.bbox[0] for block in caption_blocks),
            min(block.bbox[1] for block in caption_blocks),
            max(block.bbox[2] for block in caption_blocks),
            max(block.bbox[3] for block in caption_blocks),
        )
        candidate_id = str(candidate["candidate_id"])
        caption_bboxes[candidate_id] = caption_bbox
        component_proposals[candidate_id] = (
            []
            if candidate["concerns"]
            else [
                component
                for component in figure_eligible_components_by_page[
                    int(candidate["page_num"])
                ]
                if component.bbox[3] <= caption_bbox[1]
                and component.bbox[0] < caption_bbox[2]
                and component.bbox[2] > caption_bbox[0]
            ]
        )
    component_claims = Counter(
        component.component_id
        for components in component_proposals.values()
        for component in components
    )
    for candidate in figure_scope_candidates:
        if candidate["concerns"]:
            continue
        candidate_id = str(candidate["candidate_id"])
        components = component_proposals[candidate_id]
        if not components:
            candidate["concerns"] = ["no_above_overlapping_visual_components"]
            continue
        if any(component_claims[component.component_id] > 1 for component in components):
            candidate["concerns"] = ["competing_caption_claim"]
            continue
        content_bbox = (
            min(component.bbox[0] for component in components),
            min(component.bbox[1] for component in components),
            max(component.bbox[2] for component in components),
            max(component.bbox[3] for component in components),
        )
        caption_bbox = caption_bboxes[candidate_id]
        candidate["visual_component_ids"] = [
            component.component_id for component in components
        ]
        candidate["content_bbox"] = content_bbox
        candidate["composite_bbox"] = (
            min(content_bbox[0], caption_bbox[0]),
            min(content_bbox[1], caption_bbox[1]),
            max(content_bbox[2], caption_bbox[2]),
            max(content_bbox[3], caption_bbox[3]),
        )
        candidate["structural_evidence"].extend(
            ["above_caption", "positive_horizontal_overlap"]
        )

    internal_block_proposals: dict[str, list[SimpleNamespace]] = {}
    for candidate in figure_scope_candidates:
        candidate_id = str(candidate["candidate_id"])
        if candidate["concerns"]:
            internal_block_proposals[candidate_id] = []
            continue
        caption_bbox = caption_bboxes[candidate_id]
        content_bbox = candidate["content_bbox"]
        composite_bbox = candidate["composite_bbox"]
        internal_block_proposals[candidate_id] = [
            block
            for block in blocks
            if block.page_num == candidate["page_num"]
            and block.block_id not in candidate["caption_block_ids"]
            and block.bbox[0] < composite_bbox[2]
            and block.bbox[2] > composite_bbox[0]
            and block.bbox[1] < caption_bbox[1]
            and block.bbox[3] > content_bbox[1]
        ]
    internal_block_claims = Counter(
        block.block_id
        for proposed_blocks in internal_block_proposals.values()
        for block in proposed_blocks
    )
    for candidate in figure_scope_candidates:
        if candidate["concerns"]:
            continue
        candidate_id = str(candidate["candidate_id"])
        internal_blocks = internal_block_proposals[candidate_id]
        if any(internal_block_claims[block.block_id] > 1 for block in internal_blocks):
            candidate["concerns"] = ["competing_internal_block_claim"]
            continue
        candidate["internal_block_ids"] = [block.block_id for block in internal_blocks]
        if internal_blocks:
            content_bbox = candidate["content_bbox"]
            candidate["content_bbox"] = (
                min(content_bbox[0], *(block.bbox[0] for block in internal_blocks)),
                min(content_bbox[1], *(block.bbox[1] for block in internal_blocks)),
                max(content_bbox[2], *(block.bbox[2] for block in internal_blocks)),
                max(content_bbox[3], *(block.bbox[3] for block in internal_blocks)),
            )
            caption_bbox = caption_bboxes[candidate_id]
            content_bbox = candidate["content_bbox"]
            candidate["composite_bbox"] = (
                min(content_bbox[0], caption_bbox[0]),
                min(content_bbox[1], caption_bbox[1]),
                max(content_bbox[2], caption_bbox[2]),
                max(content_bbox[3], caption_bbox[3]),
            )
            candidate["structural_evidence"].append("figure_envelope_overlap")

    for candidate in figure_scope_candidates:
        if candidate["concerns"]:
            continue
        member_block_ids = [
            *candidate["caption_block_ids"],
            *candidate["internal_block_ids"],
        ]
        composite_bbox = candidate["composite_bbox"]
        unclaimed_block_ids = [
            block.block_id
            for block in blocks
            if block.page_num == candidate["page_num"]
            and block.block_id not in member_block_ids
            and block.bbox[0] < composite_bbox[2]
            and block.bbox[2] > composite_bbox[0]
            and block.bbox[1] < composite_bbox[3]
            and block.bbox[3] > composite_bbox[1]
        ]
        if unclaimed_block_ids:
            candidate["concerns"] = [
                f"unclaimed_intersecting_block:{block_id}"
                for block_id in unclaimed_block_ids
            ]

    for page in stream_pages:
        for group in page.orientation_groups:
            group_blocks = [
                block
                for block in blocks
                if block.orientation_group_id == group.group_id
            ]
            (
                group.layout_kind,
                group.layout_regions,
                group.layout_diagnostics,
            ) = _build_block_layout_candidates(
                group.group_id,
                group_blocks,
            )

    groups = {
        group.group_id: group
        for page in stream_pages
        for group in page.orientation_groups
    }
    block_layouts: dict[str, tuple[int, str, str, int]] = {}
    block_styles: dict[str, tuple[str, float]] = {}
    eligible_body_ids: set[str] = set()
    eligible_heading_ids: set[str] = set()
    sentence_ids: set[str] = set()
    body_style_counts: dict[tuple[str, float], int] = {}
    for block in blocks:
        block_lines = [lines_by_id[line_id] for line_id in block.line_ids]
        line_indices = [line.line_index for line in block_lines]
        group = groups.get(block.orientation_group_id)
        spanning = bool(block_lines) and all(
            "full_width_line" in line.notes for line in block_lines
        )
        eligible = (
            block.orientation == "upright"
            and group is not None
            and (
                spanning
                or (
                    block.column_index < len(group.column_bands)
                    and group.column_bands[block.column_index][0]
                    <= block.canonical_bbox[0]
                    and block.canonical_bbox[2]
                    <= group.column_bands[block.column_index][1]
                )
            )
            and line_indices
            and all(line_index is not None for line_index in line_indices)
            and line_indices
            == list(range(line_indices[0], line_indices[0] + len(line_indices)))
            and all(
                line.page_num == block.page_num
                and line.block_index == block.source_block_index
                and line.orientation_group_id == block.orientation_group_id
                and line.column_index == block.column_index
                and line.column_count == block.column_count
                for line in block_lines
            )
        )
        if not eligible:
            continue
        block_layouts[block.block_id] = (
            block.page_num,
            block.orientation_group_id,
            "spanning" if spanning else "column",
            0 if spanning else block.column_index,
        )
        if block.role == "heading":
            eligible_heading_ids.add(block.block_id)
            continue
        if block.role != "body" or any(
            line.dominant_font is None or line.dominant_font_size is None
            for line in block_lines
        ):
            continue
        fonts = {line.dominant_font for line in block_lines}
        sizes = [line.dominant_font_size for line in block_lines]
        if len(fonts) != 1 or max(sizes) - min(sizes) >= 0.5:
            continue
        style = (next(iter(fonts)), max(sizes))
        block_styles[block.block_id] = style
        eligible_body_ids.add(block.block_id)
        if re.search(r"[.!?](?:[\"'’”)]*)?(?=\s|$)", block.text):
            sentence_ids.add(block.block_id)
            body_style_counts[style] = body_style_counts.get(style, 0) + sum(
                len(line.text) for line in block_lines
            )
    body_style = (
        max(body_style_counts, key=body_style_counts.__getitem__)
        if body_style_counts
        else None
    )
    paragraph_ids = {
        block.block_id
        for block in blocks
        if (
            block.block_id in eligible_body_ids
            and block_styles.get(block.block_id) == body_style
            and block_layouts[block.block_id][2] != "spanning"
            and any(
                "\n" in block.text[match.end() :]
                for match in re.finditer(
                    r"(?:[!?]|(?<!\d)\.)(?:[\"'’”)]*)?(?=\s|$)", block.text
                )
            )
        )
    }
    prose_ids = set(paragraph_ids)
    for block_index, block in enumerate(blocks[1:], start=1):
        previous = blocks[block_index - 1]
        if (
            previous.block_id in eligible_heading_ids
            and block.block_id in sentence_ids
            and block_styles.get(block.block_id) == body_style
            and block_layouts[previous.block_id][:2]
            == block_layouts[block.block_id][:2]
        ):
            prose_ids.add(block.block_id)
        continuation = previous
        crossed_spanning_residual = False
        if (
            previous.block_id not in prose_ids
            and block_layouts.get(previous.block_id, (None, None, None, None))[2]
            == "spanning"
            and block_index > 1
        ):
            continuation = blocks[block_index - 2]
            crossed_spanning_residual = True
        if (
            continuation.block_id in prose_ids
            and block.block_id in eligible_body_ids
            and block_styles.get(block.block_id) == body_style
            and block.block_id not in prose_ids
            and re.search(r"[.!?](?:[\"'’”)]*)\s*$", continuation.text) is None
            and (
                continuation.page_num != block.page_num
                or block_layouts.get(continuation.block_id)
                != block_layouts.get(block.block_id)
                or crossed_spanning_residual
            )
        ):
            prose_ids.add(block.block_id)
    for block_index, block in enumerate(blocks[:-1]):
        next_block = blocks[block_index + 1]
        if (
            block.block_id in eligible_heading_ids
            and next_block.block_id in prose_ids
            and block_layouts[block.block_id][:2]
            == block_layouts[next_block.block_id][:2]
        ):
            prose_ids.add(block.block_id)

    prose_segments: list[dict[str, object]] = []
    heading_block_ids: list[str] = []
    paragraphs: list[dict[str, object]] = []
    paragraph_count = 0
    for block in blocks:
        if block.block_id not in prose_ids:
            continue
        if block.role == "heading":
            if paragraphs:
                prose_segments.append(
                    {
                        "segment_id": f"paper-prose-segment-{len(prose_segments)}",
                        "heading_block_ids": heading_block_ids,
                        "paragraphs": paragraphs,
                    }
                )
                heading_block_ids = []
                paragraphs = []
            heading_block_ids.append(block.block_id)
            continue
        paragraphs.append(
            {
                "paragraph_id": f"paper-paragraph-{paragraph_count}",
                "block_ids": [block.block_id],
                "text": block.text,
            }
        )
        paragraph_count += 1
    if heading_block_ids or paragraphs:
        prose_segments.append(
            {
                "segment_id": f"paper-prose-segment-{len(prose_segments)}",
                "heading_block_ids": heading_block_ids,
                "paragraphs": paragraphs,
            }
        )

    blocks_by_line_id: dict[str, SimpleNamespace] = {
        line_id: block for block in blocks for line_id in block.line_ids
    }
    layout_block_ids_by_group: dict[str, list[str]] = {
        group.group_id: [
            str(placement["block_id"])
            for region in group.layout_regions
            for placement in region["block_placements"]
        ]
        for page in stream_pages
        for group in page.orientation_groups
    }
    bibliography_region_candidates: list[dict[str, object]] = []
    for line in classified_stream_lines:
        heading_text = reference_start_text(line.text)
        heading_match = REFERENCE_HEADING_LINE_PATTERN.match(heading_text)
        inline_match = INLINE_REFERENCE_START_PATTERN.match(heading_text)
        if heading_match is None and inline_match is None:
            continue
        heading_block = blocks_by_line_id.get(line.line_id)
        if heading_block is None:
            raise ValueError(
                f"Bibliography heading line {line.line_id} has no canonical block."
            )
        if not heading_block.line_ids or heading_block.line_ids[0] != line.line_id:
            continue
        heading_group_block_ids = layout_block_ids_by_group.get(
            heading_block.orientation_group_id,
            [],
        )
        if heading_block.block_id not in heading_group_block_ids:
            raise ValueError(
                f"Bibliography heading block {heading_block.block_id} has no layout placement."
            )
        candidate_block_ids = heading_group_block_ids[
            heading_group_block_ids.index(heading_block.block_id) :
        ]
        for page in stream_pages:
            if page.page_num <= heading_block.page_num:
                continue
            for group in page.orientation_groups:
                if group.orientation != heading_block.orientation:
                    continue
                candidate_block_ids.extend(
                    layout_block_ids_by_group.get(group.group_id, [])
                )
        bibliography_region_candidates.append(
            {
                "candidate_id": (
                    f"bibliography-region-candidate-"
                    f"{len(bibliography_region_candidates)}"
                ),
                "heading_line_id": line.line_id,
                "heading_block_id": heading_block.block_id,
                "block_ids": candidate_block_ids,
                "prose_conflict_block_ids": [
                    block_id
                    for block_id in candidate_block_ids
                    if block_id in prose_ids
                ],
                "structural_evidence": [
                    (
                        "explicit_inline_bibliography_heading"
                        if inline_match is not None
                        else "explicit_bibliography_heading_line"
                    ),
                    "forward_block_layout_order_from_heading",
                    "larger_pdf_pages_same_orientation",
                    "nonoperative_candidate",
                ],
            }
        )
    unnumbered_bibliography_entries = build_unnumbered_bibliography_entries_from_layout_lines(
        classified_stream_lines
    )
    item_region_candidates: list[dict[str, object]] = []
    unnumbered_line_ids = {
        line_id
        for entry in unnumbered_bibliography_entries
        for line_id in entry.source_line_ids
    }
    reference_heading_block_ids = {
        str(candidate["heading_block_id"])
        for candidate in bibliography_region_candidates
    }
    previous_heading_order: int | None = None
    previous_last_reference_number: int | None = None
    for region_candidate in bibliography_region_candidates:
        candidate_block_ids = [str(value) for value in region_candidate["block_ids"]]
        heading_block_id = str(region_candidate["heading_block_id"])
        heading_order = blocks_by_id[heading_block_id].order
        intervening_prose_block_ids = (
            [
                block.block_id
                for block in blocks
                if previous_heading_order < block.order < heading_order
                and block.block_id in prose_ids
            ]
            if previous_heading_order is not None
            else []
        )
        region_block_ids: list[str] = []
        region_numbered_starts: dict[str, int] = {}
        region_unnumbered_line_ids: list[str] = []
        region_continuation_line_ids: list[str] = []
        stop_block_id: str | None = None
        stop_reason: str | None = None
        expected_number: int | None = None
        first_reference_number: int | None = None
        continuation_start_x0: float | None = None
        numbering_style: str | None = None
        if previous_heading_order is not None and not intervening_prose_block_ids:
            stop_block_id = heading_block_id
            stop_reason = "no_intervening_prose"
        else:
            for block_id in candidate_block_ids:
                if block_id != heading_block_id and block_id in reference_heading_block_ids:
                    stop_block_id = block_id
                    stop_reason = "next_reference_heading"
                    break
                starts, unnumbered, continuation = bibliography_item_evidence_for_block(
                    blocks_by_id[block_id],
                    lines_by_id,
                    unnumbered_line_ids=unnumbered_line_ids,
                    continuation_start_x0=continuation_start_x0,
                )
                accepted_starts: list[tuple[int, str]] = []
                if numbering_style != "unnumbered" and starts:
                    remaining_start_index = 0
                    if expected_number is None:
                        seed_index = next(
                            (
                                index
                                for index, (number, _line_id) in enumerate(starts)
                                if previous_last_reference_number is not None
                                and number == previous_last_reference_number + 1
                            ),
                            0,
                        )
                        accepted_starts.append(starts[seed_index])
                        expected_number = starts[seed_index][0] + 1
                        first_reference_number = starts[seed_index][0]
                        remaining_start_index = seed_index + 1
                    for start in starts[remaining_start_index:]:
                        if start[0] == expected_number:
                            accepted_starts.append(start)
                            expected_number += 1
                if accepted_starts:
                    numbering_style = "numbered"
                    unnumbered = []
                    continuation_start_x0 = float(
                        lines_by_id[accepted_starts[-1][1]].canonical_bbox[0]
                    )
                elif numbering_style in (None, "unnumbered") and unnumbered:
                    numbering_style = "unnumbered"
                    continuation = []
                elif numbering_style != "numbered":
                    continuation = []
                if block_id == heading_block_id and not (
                    accepted_starts or unnumbered or continuation
                ):
                    continue
                if not (accepted_starts or unnumbered or continuation):
                    stop_block_id = block_id
                    stop_reason = "no_bibliography_item_evidence"
                    break
                region_block_ids.append(block_id)
                for number, line_id in accepted_starts:
                    region_numbered_starts[line_id] = number
                region_unnumbered_line_ids.extend(unnumbered)
                region_continuation_line_ids.extend(continuation)
        item_region_candidates.append(
            {
                "heading_line_id": region_candidate["heading_line_id"],
                "block_ids": region_block_ids,
                "numbered_item_starts": region_numbered_starts,
                "unnumbered_item_line_ids": region_unnumbered_line_ids,
                "continuation_line_ids": region_continuation_line_ids,
                "intervening_prose_block_ids": intervening_prose_block_ids,
                "previous_last_reference_number": previous_last_reference_number,
                "first_reference_number": first_reference_number,
                "stop_block_id": stop_block_id,
                "stop_reason": stop_reason,
            }
        )
        if region_block_ids:
            previous_heading_order = heading_order
            previous_last_reference_number = (
                max(region_numbered_starts.values())
                if region_numbered_starts
                else None
            )
    bibliography_entries: list[BibliographyEntry] = []
    bibliography_entities: list[dict[str, object]] = []
    bibliography_owned_block_ids: set[str] = set()
    seen_entry_ids: set[str] = set()
    for region_index, region in enumerate(item_region_candidates):
        region_block_ids = [str(value) for value in region["block_ids"]]
        if not region_block_ids:
            continue
        heading_line_id = str(region["heading_line_id"])
        heading_block_id = blocks_by_line_id[heading_line_id].block_id
        region_line_ids = [
            line_id
            for block_id in region_block_ids
            for line_id in blocks_by_id[block_id].line_ids
        ]
        region_numbered_starts = {
            str(line_id): int(number)
            for line_id, number in dict(region["numbered_item_starts"]).items()
        }
        if region_numbered_starts:
            region_entries = build_numbered_bibliography_entries_from_region(
                heading=lines_by_id[heading_line_id].text,
                line_ids=region_line_ids,
                item_starts=region_numbered_starts,
                lines_by_id=lines_by_id,
                seen_entry_ids=seen_entry_ids,
            )
            numbering_style = "numbered"
        else:
            accepted_line_ids = set(region_line_ids)
            region_entries = [
                entry
                for entry in unnumbered_bibliography_entries
                if any(line_id in accepted_line_ids for line_id in entry.source_line_ids)
            ]
            seen_entry_ids.update(entry.entry_id for entry in region_entries)
            numbering_style = "unnumbered"
        bibliography_entries.extend(region_entries)
        heading_component_block_ids = (
            [] if heading_block_id in region_block_ids else [heading_block_id]
        )
        components = [
            {
                "role": "content",
                "block_ids": region_block_ids,
                "content_refs": [
                    {
                        "artifact_kind": "paper_bibliography",
                        "artifact_id": entry.entry_id,
                    }
                    for entry in region_entries
                ],
            }
        ]
        if heading_component_block_ids:
            components.insert(
                0,
                {
                    "role": "heading",
                    "block_ids": heading_component_block_ids,
                    "content_refs": [],
                },
            )
        bibliography_owned_block_ids.update(heading_component_block_ids)
        bibliography_owned_block_ids.update(region_block_ids)
        bibliography_entities.append(
            {
                "entity_id": f"paper-bibliography-{region_index}",
                "kind": "bibliography",
                "scope": "main",
                "components": components,
                "evidence": {
                    "heading_line_id": heading_line_id,
                    "numbering_style": numbering_style,
                    "numbered_item_starts": region_numbered_starts,
                    "unnumbered_item_line_ids": region["unnumbered_item_line_ids"],
                    "continuation_line_ids": region["continuation_line_ids"],
                    "intervening_prose_block_ids": region["intervening_prose_block_ids"],
                    "previous_last_reference_number": region["previous_last_reference_number"],
                    "first_reference_number": region["first_reference_number"],
                    "stop_block_id": region["stop_block_id"],
                    "stop_reason": region["stop_reason"],
                },
            }
        )
    figure_entities: list[dict[str, object]] = []
    figure_owned_block_ids: set[str] = set()
    first_member_replacements: dict[str, str] = {}
    for candidate in figure_scope_candidates:
        if candidate["concerns"]:
            continue
        member_block_ids = [
            *candidate["caption_block_ids"],
            *candidate["internal_block_ids"],
        ]
        ownership_conflicts = bibliography_owned_block_ids.intersection(
            member_block_ids
        )
        if ownership_conflicts:
            candidate["concerns"] = [
                f"competing_bibliography_ownership:{block_id}"
                for block_id in sorted(ownership_conflicts)
            ]
            continue
        entity_id = f"figure-composite:{candidate['candidate_id']}"
        figure_entities.append(
            {
                "entity_id": entity_id,
                "kind": "figure",
                "scope": "main",
                "page_num": candidate["page_num"],
                "bbox": candidate["composite_bbox"],
                "components": [
                    {
                        "role": "caption",
                        "block_ids": candidate["caption_block_ids"],
                        "content_refs": [],
                    },
                    {
                        "role": "content",
                        "block_ids": candidate["internal_block_ids"],
                        "content_refs": [
                            {
                                "artifact_kind": "paper_positioned_visual_component",
                                "artifact_id": component_id,
                            }
                            for component_id in candidate["visual_component_ids"]
                        ],
                    },
                ],
                "evidence": {
                    "figure_scope_candidate_id": candidate["candidate_id"],
                    "figure_label": candidate["figure_label"],
                    "content_bbox": candidate["content_bbox"],
                    "structural_evidence": candidate["structural_evidence"],
                },
            }
        )
        first_member_replacements[
            min(member_block_ids, key=lambda block_id: blocks_by_id[block_id].order)
        ] = entity_id
        figure_owned_block_ids.update(member_block_ids)
    entity_owned_block_ids = bibliography_owned_block_ids | figure_owned_block_ids
    structure = [
        {
            "page_num": page.page_num,
            "structural_unit_ids": [
                first_member_replacements.get(block.block_id, block.block_id)
                for block in blocks
                if block.page_num == page.page_num
                and (
                    block.block_id not in figure_owned_block_ids
                    or block.block_id in first_member_replacements
                )
            ],
        }
        for page in stream_pages
    ]
    owned_prose_segments: list[dict[str, object]] = []
    for segment in prose_segments:
        heading_block_ids = [
            block_id
            for block_id in segment["heading_block_ids"]
            if block_id not in entity_owned_block_ids
        ]
        paragraphs = []
        for paragraph in segment["paragraphs"]:
            paragraph_block_ids = [
                block_id
                for block_id in paragraph["block_ids"]
                if block_id not in entity_owned_block_ids
            ]
            if paragraph_block_ids:
                paragraphs.append(
                    {
                        **paragraph,
                        "block_ids": paragraph_block_ids,
                        "text": "\n".join(
                            blocks_by_id[block_id].text
                            for block_id in paragraph_block_ids
                        ),
                    }
                )
        if heading_block_ids or paragraphs:
            owned_prose_segments.append(
                {
                    **segment,
                    "heading_block_ids": heading_block_ids,
                    "paragraphs": paragraphs,
                }
            )
    prose_segments = owned_prose_segments
    prose_ids = {
        block_id
        for segment in prose_segments
        for block_id in [
            *segment["heading_block_ids"],
            *[
                value
                for paragraph in segment["paragraphs"]
                for value in paragraph["block_ids"]
            ],
        ]
    }
    return {
        "paper_id": paper_id or Path(pdf_path).stem,
        "source_pdf": Path(pdf_path).name,
        "pages": [
            {
                "page_num": page.page_num,
                "width": page.page_width,
                "height": page.page_height,
                "orientation_groups": [
                    {
                        "group_id": group.group_id,
                        "orientation": group.orientation,
                        "source_bbox": group.source_bbox,
                        "canonical_width": group.canonical_width,
                        "canonical_height": group.canonical_height,
                        "column_boundaries": group.column_boundaries,
                        "column_bands": group.column_bands,
                        "layout_kind": group.layout_kind,
                        "layout_regions": group.layout_regions,
                        "layout_diagnostics": group.layout_diagnostics,
                    }
                    for group in page.orientation_groups
                ],
            }
            for page in stream_pages
        ],
        "blocks": [
            {
                "block_id": block.block_id,
                "page_num": block.page_num,
                "source_block_index": block.source_block_index,
                "role": block.role,
                "bbox": block.bbox,
                "canonical_bbox": block.canonical_bbox,
                "orientation": block.orientation,
                "orientation_group_id": block.orientation_group_id,
                "column_index": block.column_index,
                "column_count": block.column_count,
                "line_ids": block.line_ids,
                "text": block.text,
            }
            for block in blocks
        ],
        "structure": structure,
        "prose": {"segments": prose_segments},
        "entities": [*figure_entities, *bibliography_entities],
        "unassigned_block_ids": [
            block.block_id
            for block in blocks
            if block.block_id not in prose_ids
            and block.block_id not in entity_owned_block_ids
        ],
        "bibliography_region_candidates": bibliography_region_candidates,
        "figure_scope_rejections": [
            candidate for candidate in figure_scope_candidates if candidate["concerns"]
        ],
    }, bibliography_entries


def _build_block_layout_candidates(
    group_id: str,
    group_blocks: list[SimpleNamespace],
) -> tuple[str, list[dict[str, object]], list[str]]:
    """Build non-operative gutter tracks and block placements from exact topology."""
    if not group_blocks:
        raise ValueError(f"Block layout candidate has no blocks for orientation group {group_id}.")

    source_ordered_blocks = sorted(
        group_blocks,
        key=lambda block: (
            block.source_block_index is None,
            block.source_block_index or 0,
            block.order,
            block.block_id,
        ),
    )
    source_positions = {
        block.block_id: source_position
        for source_position, block in enumerate(source_ordered_blocks)
    }

    vertical_edges = sorted(
        {
            edge
            for block in group_blocks
            for edge in (block.canonical_bbox[1], block.canonical_bbox[3])
        }
    )
    region_candidates: list[
        tuple[list[SimpleNamespace], list[tuple[float, float]]]
    ] = []
    current_region_blocks: dict[str, SimpleNamespace] = {}
    current_gutters: list[tuple[float, float]] = []
    for interval_top, interval_bottom in zip(vertical_edges, vertical_edges[1:]):
        if interval_top >= interval_bottom:
            continue
        active_blocks = [
            block
            for block in group_blocks
            if (
                block.canonical_bbox[1] < interval_bottom
                and block.canonical_bbox[3] > interval_top
            )
        ]
        if not active_blocks:
            continue

        occupied_intervals: list[tuple[float, float]] = []
        for block in sorted(
            active_blocks,
            key=lambda candidate: (
                candidate.canonical_bbox[0],
                candidate.canonical_bbox[2],
                source_positions[candidate.block_id],
            ),
        ):
            block_left = block.canonical_bbox[0]
            block_right = block.canonical_bbox[2]
            if not occupied_intervals or occupied_intervals[-1][1] < block_left:
                occupied_intervals.append((block_left, block_right))
            else:
                occupied_intervals[-1] = (
                    occupied_intervals[-1][0],
                    max(occupied_intervals[-1][1], block_right),
                )
        interval_gutters = [
            (left_interval[1], right_interval[0])
            for left_interval, right_interval in zip(
                occupied_intervals,
                occupied_intervals[1:],
            )
            if left_interval[1] < right_interval[0]
        ]

        matched_gutter_indexes: set[int] = set()
        continued_gutters: dict[int, tuple[float, float]] = {}
        closed_gutter_indexes: set[int] = set()
        for gutter_index, gutter in enumerate(current_gutters):
            for interval_gutter_index, interval_gutter in enumerate(interval_gutters):
                if interval_gutter_index in matched_gutter_indexes:
                    continue
                intersection = (
                    max(gutter[0], interval_gutter[0]),
                    min(gutter[1], interval_gutter[1]),
                )
                if intersection[0] < intersection[1]:
                    continued_gutters[gutter_index] = intersection
                    matched_gutter_indexes.add(interval_gutter_index)
                    break
            if gutter_index in continued_gutters:
                continue
            crosses_gutter = any(
                block.canonical_bbox[0] < gutter[1]
                and block.canonical_bbox[2] > gutter[0]
                for block in active_blocks
            )
            occupies_left = any(
                block.canonical_bbox[2] <= gutter[0] for block in active_blocks
            )
            occupies_right = any(
                block.canonical_bbox[0] >= gutter[1] for block in active_blocks
            )
            if not crosses_gutter and occupies_left != occupies_right:
                continue
            closed_gutter_indexes.add(gutter_index)

        boundary_would_cut_block = any(
            block.canonical_bbox[1] < interval_top < block.canonical_bbox[3]
            for block in active_blocks
        )
        close_all_existing_gutters = bool(current_gutters) and len(
            closed_gutter_indexes
        ) == len(current_gutters)
        prior_phase_crosses_new_gutters = (
            not current_gutters
            and bool(current_region_blocks)
            and bool(interval_gutters)
            and all(
                any(
                    block.canonical_bbox[0] < gutter[1]
                    and block.canonical_bbox[2] > gutter[0]
                    for block in current_region_blocks.values()
                )
                for gutter in interval_gutters
            )
        )
        starts_new_region = (
            (close_all_existing_gutters or prior_phase_crosses_new_gutters)
            and not boundary_would_cut_block
        )
        if starts_new_region:
            region_candidates.append(
                (list(current_region_blocks.values()), current_gutters)
            )
            current_region_blocks = {
                block.block_id: block for block in active_blocks
            }
            current_gutters = interval_gutters
            continue

        current_region_blocks.update(
            {block.block_id: block for block in active_blocks}
        )
        if not current_gutters:
            current_gutters = interval_gutters
            continue
        current_gutters = [
            continued_gutters.get(gutter_index, gutter)
            for gutter_index, gutter in enumerate(current_gutters)
        ]
        current_gutters.extend(
            gutter
            for gutter_index, gutter in enumerate(interval_gutters)
            if gutter_index not in matched_gutter_indexes
        )
        current_gutters.sort()

    if current_region_blocks:
        region_candidates.append(
            (list(current_region_blocks.values()), current_gutters)
        )

    layout_regions: list[dict[str, object]] = []
    candidate_block_ids: list[str] = []
    spanning_placement_count = 0
    for region_index, (region_blocks, candidate_gutters) in enumerate(
        region_candidates
    ):
        candidate_gutters = sorted(candidate_gutters)
        region_bbox = (
            min(block.canonical_bbox[0] for block in region_blocks),
            min(block.canonical_bbox[1] for block in region_blocks),
            max(block.canonical_bbox[2] for block in region_blocks),
            max(block.canonical_bbox[3] for block in region_blocks),
        )
        region_id = f"{group_id}-region-{region_index}"
        for left_gutter, right_gutter in zip(
            candidate_gutters,
            candidate_gutters[1:],
        ):
            if left_gutter[1] >= right_gutter[0]:
                raise ValueError(
                    f"Block layout candidate has overlapping gutter tracks in {region_id}."
                )

        columns: list[dict[str, object]] = []
        column_count = len(candidate_gutters) + 1
        for column_index in range(column_count):
            column_left = (
                region_bbox[0]
                if column_index == 0
                else candidate_gutters[column_index - 1][1]
            )
            column_right = (
                region_bbox[2]
                if column_index == len(candidate_gutters)
                else candidate_gutters[column_index][0]
            )
            if column_left >= column_right:
                raise ValueError(
                    f"Block layout candidate has a non-positive column in {region_id}."
                )
            columns.append(
                {
                    "column_id": f"{region_id}-column-{column_index}",
                    "bbox": (
                        column_left,
                        region_bbox[1],
                        column_right,
                        region_bbox[3],
                    ),
                }
            )

        region_blocks_by_id = {block.block_id: block for block in region_blocks}
        block_placements: list[dict[str, object]] = []
        for block in region_blocks:
            start_column = sum(
                gutter[1] <= block.canonical_bbox[0]
                for gutter in candidate_gutters
            )
            end_column_exclusive = 1 + sum(
                gutter[0] < block.canonical_bbox[2]
                for gutter in candidate_gutters
            )
            if not (
                0 <= start_column < end_column_exclusive <= column_count
            ):
                raise ValueError(
                    f"Block layout candidate has an invalid placement for {block.block_id}."
                )
            if end_column_exclusive - start_column > 1:
                spanning_placement_count += 1
            block_placements.append(
                {
                    "block_id": block.block_id,
                    "start_column": start_column,
                    "end_column_exclusive": end_column_exclusive,
                }
            )
        block_placements.sort(
            key=lambda placement: (
                placement["start_column"],
                region_blocks_by_id[str(placement["block_id"])].canonical_bbox[1],
                source_positions[str(placement["block_id"])],
            )
        )
        candidate_block_ids.extend(
            str(placement["block_id"]) for placement in block_placements
        )
        layout_regions.append(
            {
                "region_id": region_id,
                "bbox": region_bbox,
                "candidate_gutters": candidate_gutters,
                "columns": columns,
                "block_placements": block_placements,
            }
        )

    expected_block_ids = {block.block_id for block in group_blocks}
    if (
        len(candidate_block_ids) != len(set(candidate_block_ids))
        or set(candidate_block_ids) != expected_block_ids
    ):
        raise ValueError(
            f"Block layout candidate does not cover orientation group {group_id} exactly once."
        )

    if len(layout_regions) > 1:
        layout_kind = "mixed"
    elif len(layout_regions[0]["columns"]) > 1:
        layout_kind = "multicolumn"
    else:
        layout_kind = "single"
    column_count = sum(len(region["columns"]) for region in layout_regions)
    gutter_count = sum(len(region["candidate_gutters"]) for region in layout_regions)
    return (
        layout_kind,
        layout_regions,
        [
            "nonoperative_region_column_layout_candidate",
            f"candidate_region_count:{len(layout_regions)}",
            f"candidate_column_count:{column_count}",
            f"candidate_gutter_count:{gutter_count}",
            f"candidate_spanning_placement_count:{spanning_placement_count}",
        ],
    )


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

    column_bands = [
        (
            min(float(record["bbox"][0]) for record in group),
            max(float(record["bbox"][2]) for record in group),
        )
        for group in column_groups
    ]

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
    source_blocks: list[dict[str, object]],
    column_boundaries: list[float],
    page_width: float,
) -> list[dict[str, object]]:
    ordered_blocks = list(source_blocks)

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
