"""Build the canonical paper document from positioned PDF text."""

from __future__ import annotations

import re
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from table1_parser.context.paper_positioned_document import canonical_bbox_for_orientation
from table1_parser.context.visual_references import VISUAL_OBJECT_DOI_PATTERN
from table1_parser.paper_discovery import PaperDiscoveryState
from table1_parser.page_furniture_mask import page_furniture_source_line_ids
from table1_parser.paper_bibliography import (
    bibliography_item_evidence_for_block,
    build_numbered_bibliography_entries_from_region,
    build_unnumbered_bibliography_entries_from_layout_lines,
)
from table1_parser.reference_sections import (
    INLINE_REFERENCE_START_PATTERN,
    REFERENCE_HEADING_LINE_PATTERN,
    reference_start_text,
)
from table1_parser.schemas import (
    BibliographyEntry,
    ExtractedTable,
    PaperPageFurniture,
    PaperPositionedDocument,
    PaperPositionedLine,
    PaperPositionedVisualComponent,
    ResolvedTableSet,
    TableRegion,
)
from table1_parser.text_cleaning import clean_text


BODY_TEXT_STYLE_MIN_FONT_SIZE = 5.0
BODY_TEXT_STYLE_MAX_FONT_SIZE = 18.0
TABLE_CAPTION_LINE_PATTERN = re.compile(r"^\s*table\s+[A-Za-z]?\d+[A-Za-z]?\b", re.IGNORECASE)
FIGURE_CAPTION_BLOCK_PATTERN = re.compile(
    r"^\s*(?P<label>(?:Fig\.|Figure)\s*[A-Za-z]?\d+[A-Za-z]?)\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class PaperDocumentBuildState:
    """Private in-memory state awaiting final PaperDocument materialization."""

    paper_id: str
    source_pdf: str
    discovery: PaperDiscoveryState
    structure: list[dict[str, object]]
    layout_ordered_block_ids: list[str]
    candidate_prose_block_ids: frozenset[str]
    entity_owned_block_ids: frozenset[str]
    entities: list[dict[str, object]]
    bibliography_region_candidates: list[dict[str, object]]
    figure_scope_rejections: list[dict[str, object]]
    bibliography_entries: list[BibliographyEntry]


def build_paper_document_state(
    pdf_path: str,
    *,
    paper_page_furniture: PaperPageFurniture | None = None,
    paper_positioned_document: PaperPositionedDocument | None = None,
    paper_id: str | None = None,
) -> PaperDocumentBuildState:
    """Build filtered canonical blocks and pre-final discovery evidence."""
    if paper_positioned_document is None:
        from table1_parser.context.paper_positioned_document import build_paper_positioned_document

        paper_positioned_document = build_paper_positioned_document(pdf_path, paper_id=paper_id)
    if paper_positioned_document.page_count <= 0:
        return PaperDocumentBuildState(
            paper_id=paper_id or Path(pdf_path).stem,
            source_pdf=Path(pdf_path).name,
            discovery=PaperDiscoveryState(
                pages=[],
                blocks=[],
                prose_line_ids=frozenset(),
                bibliography_block_ids=frozenset(),
            ),
            structure=[],
            layout_ordered_block_ids=[],
            candidate_prose_block_ids=frozenset(),
            entity_owned_block_ids=frozenset(),
            entities=[],
            bibliography_region_candidates=[],
            figure_scope_rejections=[],
            bibliography_entries=[],
        )

    stream_lines: list[SimpleNamespace] = []
    stream_pages: list[SimpleNamespace] = []
    font_style_counts: Counter[tuple[str, float]] = Counter()
    removed_furniture_line_count = 0
    furniture_source_line_ids = page_furniture_source_line_ids(
        paper_page_furniture
    )
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
            if positioned_line.line_id in furniture_source_line_ids:
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
    figure_eligible_components_by_page: dict[
        int, list[PaperPositionedVisualComponent]
    ] = {
        page_num: list(page.visual_components)
        for page_num, page in positioned_pages.items()
    }
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

    groups = {
        group.group_id: group
        for page in stream_pages
        for group in page.orientation_groups
    }
    figure_entities: list[dict[str, object]] = []
    figure_owned_block_ids: set[str] = set()
    figure_layout_units_by_group: dict[str, list[SimpleNamespace]] = {}
    for candidate in figure_scope_candidates:
        if candidate["concerns"]:
            continue
        member_block_ids = [
            *candidate["caption_block_ids"],
            *candidate["internal_block_ids"],
        ]
        first_member_block_id = min(
            member_block_ids,
            key=lambda block_id: blocks_by_id[block_id].order,
        )
        caption_block = blocks_by_id[str(candidate["caption_block_ids"][0])]
        caption_group = groups[caption_block.orientation_group_id]
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
        figure_owned_block_ids.update(member_block_ids)
        figure_layout_units_by_group.setdefault(
            caption_block.orientation_group_id, []
        ).append(
            SimpleNamespace(
                block_id=entity_id,
                page_num=candidate["page_num"],
                source_block_index=caption_block.source_block_index,
                order=blocks_by_id[first_member_block_id].order,
                bbox=candidate["composite_bbox"],
                canonical_bbox=canonical_bbox_for_orientation(
                    candidate["composite_bbox"],
                    orientation=caption_block.orientation,
                    orientation_source_bbox=caption_group.source_bbox,
                ),
                orientation=caption_block.orientation,
                orientation_group_id=caption_block.orientation_group_id,
            )
        )

    for page in stream_pages:
        for group in page.orientation_groups:
            group_layout_units = [
                block
                for block in blocks
                if block.orientation_group_id == group.group_id
                and block.block_id not in figure_owned_block_ids
            ]
            group_layout_units.extend(
                figure_layout_units_by_group.get(group.group_id, [])
            )
            if not group_layout_units:
                group.layout_kind = "empty"
                group.layout_regions = []
                group.layout_diagnostics = [
                    "figure_member_only_orientation_group"
                ]
                continue
            (
                group.layout_kind,
                group.layout_regions,
                group.layout_diagnostics,
            ) = _build_block_layout_candidates(
                group.group_id,
                group_layout_units,
            )

    layout_ordered_blocks = [
        blocks_by_id[str(placement["block_id"])]
        for page in stream_pages
        for group in page.orientation_groups
        for region in group.layout_regions
        for placement in region["block_placements"]
        if str(placement["block_id"]) in blocks_by_id
    ]
    expected_layout_block_ids = set(blocks_by_id) - figure_owned_block_ids
    if (
        len(layout_ordered_blocks)
        != len({block.block_id for block in layout_ordered_blocks})
        or {block.block_id for block in layout_ordered_blocks}
        != expected_layout_block_ids
    ):
        raise ValueError(
            "Prose layout traversal does not cover ordinary blocks exactly once."
        )

    block_layouts: dict[str, tuple[int, str, str, int]] = {}
    block_styles: dict[str, tuple[str, float]] = {}
    eligible_body_ids: set[str] = set()
    eligible_heading_ids: set[str] = set()
    sentence_ids: set[str] = set()
    body_style_counts: dict[tuple[str, float], int] = {}
    for block in layout_ordered_blocks:
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
        for block in layout_ordered_blocks
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
    for block_index, block in enumerate(layout_ordered_blocks[1:], start=1):
        previous = layout_ordered_blocks[block_index - 1]
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
            continuation = layout_ordered_blocks[block_index - 2]
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
    for block_index, block in enumerate(layout_ordered_blocks[:-1]):
        next_block = layout_ordered_blocks[block_index + 1]
        if (
            block.block_id in eligible_heading_ids
            and next_block.block_id in prose_ids
            and block_layouts[block.block_id][:2]
            == block_layouts[next_block.block_id][:2]
        ):
            prose_ids.add(block.block_id)

    blocks_by_line_id: dict[str, SimpleNamespace] = {
        line_id: block
        for block in layout_ordered_blocks
        for line_id in block.line_ids
    }
    layout_ordered_lines = [
        lines_by_id[line_id]
        for block in layout_ordered_blocks
        for line_id in block.line_ids
    ]
    layout_order_by_block_id = {
        block.block_id: block_index
        for block_index, block in enumerate(layout_ordered_blocks)
    }
    bibliography_region_candidates: list[dict[str, object]] = []
    for heading_layout_index, heading_block in enumerate(layout_ordered_blocks):
        if not heading_block.line_ids:
            continue
        line = lines_by_id[heading_block.line_ids[0]]
        heading_text = reference_start_text(line.text)
        heading_match = REFERENCE_HEADING_LINE_PATTERN.match(heading_text)
        inline_match = INLINE_REFERENCE_START_PATTERN.match(heading_text)
        if heading_match is None and inline_match is None:
            continue
        candidate_block_ids = [
            block.block_id
            for block in layout_ordered_blocks[heading_layout_index:]
            if block.orientation == heading_block.orientation
        ]
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
        layout_ordered_lines
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
    previous_heading_layout_index: int | None = None
    previous_last_reference_number: int | None = None
    for region_candidate in bibliography_region_candidates:
        candidate_block_ids = [str(value) for value in region_candidate["block_ids"]]
        heading_block_id = str(region_candidate["heading_block_id"])
        heading_layout_index = layout_order_by_block_id[heading_block_id]
        intervening_prose_block_ids = (
            [
                block.block_id
                for block in layout_ordered_blocks[
                    previous_heading_layout_index + 1 : heading_layout_index
                ]
                if block.block_id in prose_ids
            ]
            if previous_heading_layout_index is not None
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
        if previous_heading_layout_index is not None and not intervening_prose_block_ids:
            stop_block_id = heading_block_id
            stop_reason = "no_intervening_prose"
        else:
            candidate_block_iter = iter(candidate_block_ids)
            for block_id in candidate_block_iter:
                if block_id != heading_block_id and block_id in reference_heading_block_ids:
                    stop_block_id = block_id
                    stop_reason = "next_reference_heading"
                    break
                block = blocks_by_id[block_id]
                starts, unnumbered, continuation = bibliography_item_evidence_for_block(
                    block,
                    lines_by_id,
                    unnumbered_line_ids=unnumbered_line_ids,
                    continuation_start_x0=continuation_start_x0,
                )
                if numbering_style in ("numbered", "unnumbered") and region_block_ids:
                    previous_block = blocks_by_id[region_block_ids[-1]]
                    next_column = (previous_block.page_num, previous_block.orientation_group_id, previous_block.column_index + 1)
                    same_next_column = (block.page_num, block.orientation_group_id, block.column_index) == next_column
                    top_has_bibliography_evidence = (
                        any(number == expected_number for number, _ in starts)
                        if numbering_style == "numbered" and expected_number is not None
                        else bool(unnumbered)
                    )
                    if same_next_column and not top_has_bibliography_evidence:
                        first_next_column_block_id = block_id
                        if block.page_num != blocks_by_id[heading_block_id].page_num:
                            stop_block_id = first_next_column_block_id
                            stop_reason = "no_cross_column_bibliography_continuation"
                            break
                        first_bibliography_block = blocks_by_id[region_block_ids[0]]
                        for block_id in candidate_block_iter:
                            block = blocks_by_id[block_id]
                            same_next_column = (block.page_num, block.orientation_group_id, block.column_index) == next_column
                            vertically_aligned = (
                                block.canonical_bbox[1] < first_bibliography_block.canonical_bbox[3]
                                and first_bibliography_block.canonical_bbox[1] < block.canonical_bbox[3]
                            )
                            if not (same_next_column and vertically_aligned):
                                continue
                            starts, unnumbered, continuation = (
                                bibliography_item_evidence_for_block(
                                    block,
                                    lines_by_id,
                                    unnumbered_line_ids=unnumbered_line_ids,
                                    continuation_start_x0=continuation_start_x0,
                                )
                            )
                            aligned_has_bibliography_evidence = (
                                any(number == expected_number for number, _ in starts)
                                if numbering_style == "numbered" and expected_number is not None
                                else bool(unnumbered)
                            )
                            if aligned_has_bibliography_evidence:
                                break
                        else:
                            stop_block_id = first_next_column_block_id
                            stop_reason = "no_cross_column_bibliography_continuation"
                            break
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
            previous_heading_layout_index = heading_layout_index
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
    entity_owned_block_ids = bibliography_owned_block_ids | figure_owned_block_ids
    figure_entities_by_id = {
        str(entity["entity_id"]): entity for entity in figure_entities
    }
    structure: list[dict[str, object]] = []
    placed_structural_unit_ids: list[str] = []
    for page in stream_pages:
        structural_unit_ids = [
            str(placement["block_id"])
            for group in page.orientation_groups
            for region in group.layout_regions
            for placement in region["block_placements"]
        ]
        for structural_unit_id in structural_unit_ids:
            block = blocks_by_id.get(structural_unit_id)
            if block is not None:
                if block.page_num != page.page_num:
                    raise ValueError(
                        f"Structural block {structural_unit_id} is placed on the wrong page."
                    )
                continue
            entity = figure_entities_by_id.get(structural_unit_id)
            if entity is None:
                raise ValueError(
                    f"Unknown structural unit in layout: {structural_unit_id}."
                )
            if entity["page_num"] != page.page_num:
                raise ValueError(
                    f"Structural figure {structural_unit_id} is placed on the wrong page."
                )
        structure.append(
            {
                "page_num": page.page_num,
                "structural_unit_ids": structural_unit_ids,
            }
        )
        placed_structural_unit_ids.extend(structural_unit_ids)
    expected_structural_unit_ids = (
        set(blocks_by_id) - figure_owned_block_ids
    ) | set(figure_entities_by_id)
    if (
        len(placed_structural_unit_ids) != len(set(placed_structural_unit_ids))
        or set(placed_structural_unit_ids) != expected_structural_unit_ids
    ):
        raise ValueError(
            "PaperDocument.structure does not cover structural layout units exactly once."
        )
    final_prose_ids = prose_ids - entity_owned_block_ids
    pages = [
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
        ]
    block_payloads = [
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
        ]
    return PaperDocumentBuildState(
        paper_id=paper_id or Path(pdf_path).stem,
        source_pdf=Path(pdf_path).name,
        discovery=PaperDiscoveryState(
            pages=pages,
            blocks=block_payloads,
            prose_line_ids=frozenset(
                line_id
                for block in blocks
                if block.block_id in final_prose_ids
                for line_id in block.line_ids
            ),
            bibliography_block_ids=frozenset(bibliography_owned_block_ids),
        ),
        structure=structure,
        layout_ordered_block_ids=[
            block.block_id for block in layout_ordered_blocks
        ],
        candidate_prose_block_ids=frozenset(prose_ids),
        entity_owned_block_ids=frozenset(entity_owned_block_ids),
        entities=[*figure_entities, *bibliography_entities],
        bibliography_region_candidates=bibliography_region_candidates,
        figure_scope_rejections=[
            candidate
            for candidate in figure_scope_candidates
            if candidate["concerns"]
        ],
        bibliography_entries=bibliography_entries,
    )


def finalize_paper_document(
    state: PaperDocumentBuildState,
    *,
    extracted_tables: list[ExtractedTable],
    resolved_table_set: ResolvedTableSet,
    table_regions: list[TableRegion],
    paper_positioned_document: PaperPositionedDocument,
) -> tuple[dict[str, object], list[BibliographyEntry]]:
    """Materialize final ownership after table discovery and resolution finish."""
    original_blocks = [dict(block) for block in state.discovery.blocks]
    original_blocks_by_id = {
        str(block["block_id"]): block for block in original_blocks
    }
    line_to_block_id: dict[str, str] = {}
    for block in original_blocks:
        for line_id in block["line_ids"]:
            if line_id in line_to_block_id:
                raise ValueError(f"Canonical line occurs in multiple blocks: {line_id}.")
            line_to_block_id[str(line_id)] = str(block["block_id"])
    source_lines_by_id = {
        line.line_id: line
        for page in paper_positioned_document.pages
        for line in page.lines
    }
    orientation_groups_by_id = {
        str(group["group_id"]): group
        for page in state.discovery.pages
        for group in page["orientation_groups"]
    }
    extracted_by_id = {table.table_id: table for table in extracted_tables}
    region_by_table_id = {region.table_id: region for region in table_regions}
    existing_entity_owned_block_ids = {
        str(block_id)
        for entity in state.entities
        for component in entity.get("components", [])
        for block_id in component.get("block_ids", [])
    }
    table_entity_records: list[dict[str, object]] = []
    claimed_line_entity_ids: dict[str, str] = {}
    for resolved_table in resolved_table_set.resolved_tables:
        source_tables = [
            extracted_by_id[source_table_id]
            for source_table_id in resolved_table.source_table_ids
            if source_table_id in extracted_by_id
        ]
        if len(source_tables) != len(resolved_table.source_table_ids):
            continue
        line_roles: dict[str, str] = {}
        eligible = bool(source_tables)
        caption_placements: list[str] = []
        table_numbers: list[str] = []
        for table in source_tables:
            region = region_by_table_id.get(table.table_id)
            selection = table.metadata.get("canonical_grid_selection") or {}
            if (
                region is None
                or selection.get("status") != "accepted"
                or any(row.role == "unknown" for row in region.row_regions)
            ):
                eligible = False
                continue
            caption_region = table.metadata.get("caption_region") or {}
            caption_line_ids = set(caption_region.get("line_ids") or [])
            footer_line_ids = set(region.footer_line_ids)
            content_line_ids = (
                set(table.positioned_evidence.line_ids)
                - caption_line_ids
                - footer_line_ids
            )
            binding = table.metadata.get("caption_binding") or {}
            if binding.get("placement"):
                caption_placements.append(str(binding["placement"]))
            table_number = caption_region.get("table_number") or table.metadata.get(
                "table_number"
            )
            if table_number is not None:
                table_numbers.append(str(table_number))
            for role, line_ids in (
                ("caption", caption_line_ids),
                ("content", content_line_ids),
                ("footer", footer_line_ids),
            ):
                for line_id in line_ids:
                    if line_id in line_roles and line_roles[line_id] != role:
                        raise ValueError(
                            f"Table component line has competing roles: {line_id}."
                        )
                    line_roles[line_id] = role
        if not eligible or "caption" not in set(line_roles.values()):
            continue
        if any(line_id not in line_to_block_id for line_id in line_roles):
            continue
        touched_block_ids = {
            line_to_block_id[line_id] for line_id in line_roles
        }
        if touched_block_ids & existing_entity_owned_block_ids:
            raise ValueError(
                f"Table ownership conflicts with an existing entity: {resolved_table.table_id}."
            )
        for block_id in touched_block_ids:
            block = original_blocks_by_id[block_id]
            unselected_line_ids = [
                line_id for line_id in block["line_ids"] if line_id not in line_roles
            ]
            if not unselected_line_ids:
                continue
            block_text_by_line_id = dict(
                zip(block["line_ids"], str(block["text"]).split("\n"), strict=True)
            )
            selected_roles = {
                line_roles[line_id]
                for line_id in block["line_ids"]
                if line_id in line_roles
            }
            if selected_roles == {"footer"} and all(
                VISUAL_OBJECT_DOI_PATTERN.fullmatch(
                    clean_text(block_text_by_line_id[line_id])
                )
                is not None
                for line_id in unselected_line_ids
            ):
                for line_id in unselected_line_ids:
                    line_roles[line_id] = "footer"
                continue
            eligible = False
            break
        if not eligible:
            continue
        entity_id = f"paper-table:{resolved_table.table_id}"
        for line_id in line_roles:
            existing_entity_id = claimed_line_entity_ids.get(line_id)
            if existing_entity_id is not None and existing_entity_id != entity_id:
                raise ValueError(f"Table entities compete for line {line_id}.")
            claimed_line_entity_ids[line_id] = entity_id
        table_entity_records.append(
            {
                "entity_id": entity_id,
                "resolved_table_id": resolved_table.table_id,
                "resolution_type": resolved_table.resolution_type,
                "logical_table_number": resolved_table.logical_table_number,
                "source_table_ids": list(resolved_table.source_table_ids),
                "line_roles": line_roles,
                "scope": (
                    "supplementary"
                    if any(number.upper().startswith("S") for number in table_numbers)
                    else "main"
                ),
                "caption_placements": list(dict.fromkeys(caption_placements)),
            }
        )

    claims_by_block_id: dict[str, tuple[str, dict[str, str]]] = {}
    for record in table_entity_records:
        entity_id = str(record["entity_id"])
        line_roles = record["line_roles"]
        for line_id, role in line_roles.items():
            block_id = line_to_block_id[line_id]
            if block_id not in claims_by_block_id:
                claims_by_block_id[block_id] = (entity_id, {})
            block_entity_id, block_roles = claims_by_block_id[block_id]
            if block_entity_id != entity_id:
                raise ValueError(f"Table entities compete for block {block_id}.")
            block_roles[line_id] = role

    component_block_ids: dict[str, dict[str, list[str]]] = {
        str(record["entity_id"]): {"caption": [], "content": [], "footer": []}
        for record in table_entity_records
    }
    original_block_to_table_entity: dict[str, str] = {}
    refined_blocks: list[dict[str, object]] = []
    for block in original_blocks:
        block_id = str(block["block_id"])
        claim = claims_by_block_id.get(block_id)
        if claim is None:
            refined_blocks.append(block)
            continue
        entity_id, roles_by_line_id = claim
        line_ids = list(block["line_ids"])
        line_texts = str(block["text"]).split("\n")
        if len(line_ids) != len(line_texts) or set(line_ids) != set(roles_by_line_id):
            raise ValueError(f"Table block refinement is not line-exact: {block_id}.")
        original_block_to_table_entity[block_id] = entity_id
        part_start = 0
        part_index = 0
        while part_start < len(line_ids):
            role = roles_by_line_id[line_ids[part_start]]
            part_end = part_start + 1
            while (
                part_end < len(line_ids)
                and roles_by_line_id[line_ids[part_end]] == role
            ):
                part_end += 1
            part_line_ids = line_ids[part_start:part_end]
            part_id = (
                block_id
                if part_start == 0 and part_end == len(line_ids)
                else f"{block_id}:table-part-{part_index}"
            )
            page_bboxes = [source_lines_by_id[line_id].bbox for line_id in part_line_ids]
            group = orientation_groups_by_id[str(block["orientation_group_id"])]
            canonical_bboxes = [
                canonical_bbox_for_orientation(
                    bbox,
                    orientation=str(block["orientation"]),
                    orientation_source_bbox=group["source_bbox"],
                )
                for bbox in page_bboxes
            ]
            refined_blocks.append(
                {
                    **block,
                    "block_id": part_id,
                    "bbox": (
                        min(bbox[0] for bbox in page_bboxes),
                        min(bbox[1] for bbox in page_bboxes),
                        max(bbox[2] for bbox in page_bboxes),
                        max(bbox[3] for bbox in page_bboxes),
                    ),
                    "canonical_bbox": (
                        min(bbox[0] for bbox in canonical_bboxes),
                        min(bbox[1] for bbox in canonical_bboxes),
                        max(bbox[2] for bbox in canonical_bboxes),
                        max(bbox[3] for bbox in canonical_bboxes),
                    ),
                    "line_ids": part_line_ids,
                    "text": "\n".join(line_texts[part_start:part_end]),
                }
            )
            component_block_ids[entity_id][role].append(part_id)
            part_start = part_end
            part_index += 1

    table_entities: list[dict[str, object]] = []
    for record in table_entity_records:
        entity_id = str(record["entity_id"])
        components = [
            {
                "role": role,
                "block_ids": component_block_ids[entity_id][role],
                "content_refs": (
                    [
                        {
                            "artifact_kind": "resolved_table",
                            "artifact_id": record["resolved_table_id"],
                        },
                        *[
                            {
                                "artifact_kind": "extracted_table",
                                "artifact_id": source_table_id,
                            }
                            for source_table_id in record["source_table_ids"]
                        ],
                    ]
                    if role == "content"
                    else []
                ),
            }
            for role in ("caption", "content", "footer")
            if component_block_ids[entity_id][role]
        ]
        table_entities.append(
            {
                "entity_id": entity_id,
                "kind": "table",
                "scope": record["scope"],
                "components": components,
                "evidence": {
                    "resolved_table_id": record["resolved_table_id"],
                    "resolution_type": record["resolution_type"],
                    "logical_table_number": record["logical_table_number"],
                    "source_table_ids": record["source_table_ids"],
                    "caption_placements": record["caption_placements"],
                },
            }
        )

    pages = deepcopy(state.discovery.pages)
    placed_table_entity_ids: set[str] = set()
    for page in pages:
        for group in page["orientation_groups"]:
            for region in group["layout_regions"]:
                placements = region["block_placements"]
                table_placements: dict[str, list[dict[str, object]]] = {}
                for placement in placements:
                    entity_id = original_block_to_table_entity.get(
                        str(placement["block_id"])
                    )
                    if entity_id is not None:
                        table_placements.setdefault(entity_id, []).append(placement)
                final_placements: list[dict[str, object]] = []
                emitted_here: set[str] = set()
                for placement in placements:
                    entity_id = original_block_to_table_entity.get(
                        str(placement["block_id"])
                    )
                    if entity_id is None:
                        final_placements.append(placement)
                        continue
                    if (
                        entity_id in placed_table_entity_ids
                        or entity_id in emitted_here
                    ):
                        continue
                    related = table_placements[entity_id]
                    final_placements.append(
                        {
                            **placement,
                            "block_id": entity_id,
                            "start_column": min(
                                int(item["start_column"]) for item in related
                            ),
                            "end_column_exclusive": max(
                                int(item["end_column_exclusive"]) for item in related
                            ),
                        }
                    )
                    emitted_here.add(entity_id)
                region["block_placements"] = final_placements
                placed_table_entity_ids.update(emitted_here)

    structure: list[dict[str, object]] = []
    placed_table_entity_ids = set()
    for page in state.structure:
        structural_unit_ids: list[str] = []
        for structural_unit_id in page["structural_unit_ids"]:
            entity_id = original_block_to_table_entity.get(str(structural_unit_id))
            if entity_id is None:
                structural_unit_ids.append(str(structural_unit_id))
            elif entity_id not in placed_table_entity_ids:
                structural_unit_ids.append(entity_id)
                placed_table_entity_ids.add(entity_id)
        structure.append(
            {"page_num": page["page_num"], "structural_unit_ids": structural_unit_ids}
        )

    blocks_by_id = {str(block["block_id"]): block for block in refined_blocks}
    all_entities = [*state.entities, *table_entities]
    entity_owned_block_ids = {
        str(block_id)
        for entity in all_entities
        for component in entity.get("components", [])
        for block_id in component.get("block_ids", [])
    }
    prose_segments: list[dict[str, object]] = []
    heading_block_ids: list[str] = []
    paragraphs: list[dict[str, object]] = []
    paragraph_count = 0
    for block_id in [
        structural_unit_id
        for page in structure
        for structural_unit_id in page["structural_unit_ids"]
    ]:
        if (
            block_id not in state.candidate_prose_block_ids
            or block_id in entity_owned_block_ids
        ):
            continue
        block = blocks_by_id[block_id]
        if block["role"] == "heading":
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
            heading_block_ids.append(block_id)
            continue
        paragraphs.append(
            {
                "paragraph_id": f"paper-paragraph-{paragraph_count}",
                "block_ids": [block_id],
                "text": block["text"],
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

    final_prose_ids = {
        str(block_id)
        for segment in prose_segments
        for block_id in segment["heading_block_ids"]
    } | {
        str(block_id)
        for segment in prose_segments
        for paragraph in segment["paragraphs"]
        for block_id in paragraph["block_ids"]
    }
    unassigned_block_ids = [
        str(block["block_id"])
        for block in refined_blocks
        if block["block_id"] not in final_prose_ids
        and block["block_id"] not in entity_owned_block_ids
    ]
    if (
        final_prose_ids & entity_owned_block_ids
        or final_prose_ids & set(unassigned_block_ids)
        or entity_owned_block_ids & set(unassigned_block_ids)
        or final_prose_ids | entity_owned_block_ids | set(unassigned_block_ids)
        != set(blocks_by_id)
    ):
        raise ValueError("PaperDocument ownership is not pairwise disjoint and complete.")
    original_line_counts = Counter(
        str(line_id) for block in original_blocks for line_id in block["line_ids"]
    )
    refined_line_counts = Counter(
        str(line_id) for block in refined_blocks for line_id in block["line_ids"]
    )
    if (
        original_line_counts != refined_line_counts
        or any(count != 1 for count in refined_line_counts.values())
    ):
        raise ValueError("PaperDocument block refinement changed retained-line coverage.")
    opaque_entity_ids = {
        str(entity["entity_id"])
        for entity in all_entities
        if entity.get("kind") in {"figure", "table"}
    }
    opaque_owned_block_ids = {
        str(block_id)
        for entity in all_entities
        if entity.get("kind") in {"figure", "table"}
        for component in entity.get("components", [])
        for block_id in component.get("block_ids", [])
    }
    structure_ids = [
        str(structural_unit_id)
        for page in structure
        for structural_unit_id in page["structural_unit_ids"]
    ]
    page_placement_ids = [
        str(placement["block_id"])
        for page in pages
        for group in page["orientation_groups"]
        for region in group["layout_regions"]
        for placement in region["block_placements"]
    ]
    expected_structure_ids = (
        set(blocks_by_id) - opaque_owned_block_ids
    ) | opaque_entity_ids
    if (
        len(structure_ids) != len(set(structure_ids))
        or set(structure_ids) != expected_structure_ids
        or page_placement_ids != structure_ids
    ):
        raise ValueError("Final PaperDocument structure does not cover opaque entities once.")
    paper_document = {
        "paper_id": state.paper_id,
        "source_pdf": state.source_pdf,
        "pages": pages,
        "blocks": refined_blocks,
        "structure": structure,
        "prose": {"segments": prose_segments},
        "entities": all_entities,
        "unassigned_block_ids": unassigned_block_ids,
        "bibliography_region_candidates": state.bibliography_region_candidates,
        "figure_scope_rejections": state.figure_scope_rejections,
    }
    return paper_document, list(state.bibliography_entries)


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
            spans_gutter = any(
                block.canonical_bbox[0] < gutter[0]
                and block.canonical_bbox[2] > gutter[1]
                for block in active_blocks
            )
            if spans_gutter:
                closed_gutter_indexes.add(gutter_index)

        if not current_gutters and current_region_blocks and interval_gutters:
            spanning_prior_blocks = [
                block
                for block in current_region_blocks.values()
                if all(
                    block.canonical_bbox[0] < gutter[0]
                    and block.canonical_bbox[2] > gutter[1]
                    for gutter in interval_gutters
                )
            ]
            if spanning_prior_blocks:
                barrier_bottom = max(
                    block.canonical_bbox[3] for block in spanning_prior_blocks
                )
                boundary_would_cut_block = any(
                    block.canonical_bbox[1]
                    < barrier_bottom
                    < block.canonical_bbox[3]
                    for block in current_region_blocks.values()
                )
                if not boundary_would_cut_block:
                    preceding_blocks = [
                        block
                        for block in current_region_blocks.values()
                        if block.canonical_bbox[3] <= barrier_bottom
                    ]
                    following_blocks = [
                        block
                        for block in current_region_blocks.values()
                        if block.canonical_bbox[1] >= barrier_bottom
                    ]
                    region_candidates.append((preceding_blocks, []))
                    current_region_blocks = {
                        block.block_id: block
                        for block in [*following_blocks, *active_blocks]
                    }
                    current_gutters = interval_gutters
                    continue

        boundary_would_cut_block = any(
            block.canonical_bbox[1] < interval_top < block.canonical_bbox[3]
            for block in active_blocks
        )
        close_all_existing_gutters = bool(current_gutters) and len(
            closed_gutter_indexes
        ) == len(current_gutters)
        starts_new_region = (
            close_all_existing_gutters and not boundary_would_cut_block
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
