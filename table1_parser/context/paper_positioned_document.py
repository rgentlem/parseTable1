"""Build the shared positioned-text document artifact from a PDF."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from table1_parser.extract.pymupdf_page_adapter import (
    bbox_from_pymupdf_value,
    extract_page_chars,
    extract_page_rule_segments,
    extract_page_words,
    join_pymupdf_line_spans,
    open_pymupdf_document,
)
from table1_parser.schemas import (
    PaperPositionedChar,
    PaperPositionedDocument,
    PaperPositionedLine,
    PaperPositionedPage,
    PaperPositionedSpan,
    PaperPositionedVisualComponent,
    PaperPositionedWord,
)
from table1_parser.text_cleaning import clean_text


def canonical_bbox_for_orientation(
    bbox: object,
    *,
    orientation: str,
    orientation_source_bbox: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """Express one source bbox in its orientation group's canonical frame."""
    left, top, right, bottom = (float(value) for value in bbox)
    source_left, source_top, source_right, source_bottom = orientation_source_bbox
    if orientation == "vertical_text_up":
        return (source_bottom - bottom, left - source_left, source_bottom - top, right - source_left)
    if orientation == "vertical_text_down":
        return (top - source_top, source_right - right, bottom - source_top, source_right - left)
    return (left, top, right, bottom)


def build_paper_positioned_document(
    pdf_path: str,
    *,
    paper_id: str | None = None,
) -> PaperPositionedDocument:
    """Build the shared positioned-text evidence artifact for one paper."""
    try:
        document = open_pymupdf_document(pdf_path)
    except Exception:  # noqa: BLE001
        return PaperPositionedDocument(
            paper_id=paper_id or Path(pdf_path).stem,
            source_pdf=Path(pdf_path).name,
            page_count=0,
            metadata={
                "diagnostics": ["pymupdf_open_failed"],
                "source_artifacts": ["pymupdf_positioned_page_geometry"],
            },
        )

    pages: list[PaperPositionedPage] = []
    line_count = 0
    span_count = 0
    word_count = 0
    char_count = 0
    image_count = 0
    rule_segment_count = 0
    try:
        page_count = int(getattr(document, "page_count", 0))
        for page_index in range(page_count):
            page_num = page_index + 1
            try:
                import pymupdf

                page = document.load_page(page_index)
                page_dict = page.get_text("dict", clip=pymupdf.INFINITE_RECT()) or {}
            except Exception:  # noqa: BLE001
                pages.append(
                    PaperPositionedPage(
                        page_num=page_num,
                        page_width=1.0,
                        page_height=1.0,
                        diagnostics=["page_text_extraction_failed"],
                    )
                )
                continue

            page_width, page_height = page_size_from_pymupdf_page(page)
            page_bbox = (
                0.0,
                0.0,
                page_width,
                page_height,
            )
            try:
                page_drawings = [
                    drawing
                    for drawing in (page.get_drawings(extended=True) or [])
                    if isinstance(drawing, dict)
                ]
            except Exception:  # noqa: BLE001
                page_drawings = []
            try:
                page_rule_drawings = page.get_drawings() or []
            except Exception:  # noqa: BLE001
                page_rule_drawings = []

            page_lines: list[PaperPositionedLine] = []
            page_image_bboxes: list[tuple[float, float, float, float]] = []
            page_visual_components: list[PaperPositionedVisualComponent] = []
            page_line_index = 0
            for block_index, block in enumerate(page_dict.get("blocks", [])):
                if not isinstance(block, dict):
                    continue
                if block.get("type") == 1:
                    image_bbox = bbox_from_pymupdf_value(block.get("bbox"))
                    if image_bbox is not None:
                        page_image_bboxes.append(image_bbox)
                        page_visual_components.append(
                            PaperPositionedVisualComponent(
                                component_id=f"page-{page_num}-visual-raster-{block_index}",
                                component_kind="raster_image",
                                bbox=image_bbox,
                                source_index=block_index,
                            )
                        )
                for block_line_index, line in enumerate(block.get("lines", [])):
                    if not isinstance(line, dict):
                        continue
                    positioned_line = positioned_line_from_pymupdf_line(
                        line,
                        page_num=page_num,
                        block_index=block_index,
                        block_line_index=block_line_index,
                        page_line_index=page_line_index,
                    )
                    page_line_index += 1
                    if positioned_line is None:
                        continue
                    page_lines.append(positioned_line)
                    span_count += len(positioned_line.spans)
            for drawing_index, drawing in enumerate(page_drawings):
                drawing_type = drawing.get("type")
                if drawing_type not in {"clip", "group"}:
                    continue
                component_bbox = bbox_from_pymupdf_value(
                    drawing.get("scissor")
                    if drawing_type == "clip"
                    else drawing.get("rect")
                )
                if component_bbox is None:
                    continue
                if drawing_type == "clip" and component_bbox == page_bbox:
                    continue
                nesting_level = drawing.get("level")
                contained_sequences: list[int] = []
                if isinstance(nesting_level, int):
                    for following in page_drawings[drawing_index + 1 :]:
                        following_level = following.get("level")
                        if (
                            isinstance(following_level, int)
                            and following_level <= nesting_level
                        ):
                            break
                        following_sequence = following.get("seqno")
                        if isinstance(following_sequence, int):
                            contained_sequences.append(following_sequence)
                page_visual_components.append(
                    PaperPositionedVisualComponent(
                        component_id=f"page-{page_num}-visual-{drawing_type}-{drawing_index}",
                        component_kind=(
                            "vector_clip"
                            if drawing_type == "clip"
                            else "vector_group"
                        ),
                        bbox=component_bbox,
                        source_index=drawing_index,
                        nesting_level=(
                            int(nesting_level)
                            if isinstance(nesting_level, int)
                            else None
                        ),
                        drawing_sequence_range=(
                            (min(contained_sequences), max(contained_sequences))
                            if contained_sequences
                            else None
                        ),
                    )
                )
            page_chars = [PaperPositionedChar(**char) for char in extract_page_chars(page, page_num=page_num)]
            page_words = [
                PaperPositionedWord(**word)
                for word in extract_page_words(
                    page,
                    page_chars=[char.model_dump(mode="json", exclude_none=True) for char in page_chars],
                )
            ]
            page_rule_segments = extract_page_rule_segments(
                page,
                drawings=page_rule_drawings,
            )
            page_stroked_rule_segments = extract_page_rule_segments(
                page,
                include_filled=False,
                drawings=page_rule_drawings,
            )
            line_count += len(page_lines)
            word_count += len(page_words)
            char_count += len(page_chars)
            image_count += len(page_image_bboxes)
            rule_segment_count += len(page_rule_segments)
            pages.append(
                PaperPositionedPage(
                    page_num=page_num,
                    page_width=page_width,
                    page_height=page_height,
                    text="\n".join(line.raw_text for line in page_lines),
                    lines=page_lines,
                    words=page_words,
                    chars=page_chars,
                    image_bboxes=page_image_bboxes,
                    visual_components=page_visual_components,
                    rule_segments=page_rule_segments,
                    stroked_rule_segments=page_stroked_rule_segments,
                )
            )
    finally:
        close = getattr(document, "close", None)
        if callable(close):
            close()

    return PaperPositionedDocument(
        paper_id=paper_id or Path(pdf_path).stem,
        source_pdf=Path(pdf_path).name,
        page_count=len(pages),
        pages=pages,
        metadata={
            "source_artifacts": ["pymupdf_positioned_page_geometry"],
            "line_count": line_count,
            "span_count": span_count,
            "word_count": word_count,
            "char_count": char_count,
            "image_count": image_count,
            "rule_segment_count": rule_segment_count,
            "page_count": len(pages),
        },
    )


def positioned_line_from_pymupdf_line(
    line: dict[str, object],
    *,
    page_num: int,
    block_index: int,
    block_line_index: int,
    page_line_index: int,
) -> PaperPositionedLine | None:
    """Convert one PyMuPDF line dict into the shared line schema."""
    bbox_parts: list[tuple[float, float, float, float]] = []
    span_counts: Counter[tuple[str, float]] = Counter()
    span_records: list[PaperPositionedSpan] = []
    has_bold = False
    for span in line.get("spans", []):
        if not isinstance(span, dict):
            continue
        bbox = bbox_from_pymupdf_value(span.get("bbox"))
        if bbox is not None:
            bbox_parts.append(bbox)
        span_text = str(span.get("text", ""))
        visible_character_count = len("".join(span_text.split()))
        span_font = span.get("font")
        span_size = span.get("size")
        span_flags = span.get("flags")
        font = span_font if isinstance(span_font, str) and span_font.strip() else None
        font_size = float(span_size) if isinstance(span_size, (int, float)) else None
        if font is not None and font_size is not None and visible_character_count > 0:
            span_counts[(font, round(font_size, 1))] += visible_character_count
        if span_text and bbox is not None:
            span_records.append(
                PaperPositionedSpan(
                    text=span_text,
                    bbox=bbox,
                    font=font,
                    font_size=font_size,
                    flags=span_flags if isinstance(span_flags, int) else None,
                )
            )
        font_key = str(span.get("font", "")).lower()
        if "bold" in font_key or "semibold" in font_key or (isinstance(span_flags, int) and span_flags & 16):
            has_bold = True

    raw_text = join_pymupdf_line_spans(line.get("spans", []))
    text = clean_text(raw_text)
    if not text or not bbox_parts:
        return None

    dominant_font = None
    dominant_font_size = None
    dominant_style_character_count = 0
    if span_counts:
        (dominant_font, dominant_font_size), dominant_style_character_count = span_counts.most_common(1)[0]

    direction = None
    orientation = None
    raw_direction = line.get("dir")
    if isinstance(raw_direction, (list, tuple)) and len(raw_direction) == 2:
        direction = (float(raw_direction[0]), float(raw_direction[1]))
        orientation = f"{direction[0]:.3f},{direction[1]:.3f}"

    return PaperPositionedLine(
        line_id=f"page-{page_num}-line-{page_line_index}",
        page_num=page_num,
        block_index=block_index,
        line_index=block_line_index,
        page_line_index=page_line_index,
        raw_text=raw_text,
        text=text,
        bbox=(
            min(part[0] for part in bbox_parts),
            min(part[1] for part in bbox_parts),
            max(part[2] for part in bbox_parts),
            max(part[3] for part in bbox_parts),
        ),
        direction=direction,
        orientation=orientation,
        has_bold=has_bold,
        dominant_font=dominant_font,
        dominant_font_size=dominant_font_size,
        dominant_style_character_count=dominant_style_character_count,
        spans=span_records,
        font_style_counts=[
            {
                "font": font,
                "font_size": font_size,
                "character_count": character_count,
            }
            for (font, font_size), character_count in span_counts.most_common()
        ],
    )


def page_size_from_pymupdf_page(page: Any) -> tuple[float, float]:
    """Return dimensions in PyMuPDF's unrotated page-coordinate frame."""
    page_cropbox = getattr(page, "cropbox", None)
    if (
        page_cropbox is not None
        and hasattr(page_cropbox, "width")
        and hasattr(page_cropbox, "height")
    ):
        return float(page_cropbox.width), float(page_cropbox.height)
    if page_cropbox is not None and all(
        hasattr(page_cropbox, attr) for attr in ("x0", "y0", "x1", "y1")
    ):
        return (
            float(page_cropbox.x1) - float(page_cropbox.x0),
            float(page_cropbox.y1) - float(page_cropbox.y0),
        )
    if isinstance(page_cropbox, (list, tuple)) and len(page_cropbox) == 4:
        return (
            float(page_cropbox[2]) - float(page_cropbox[0]),
            float(page_cropbox[3]) - float(page_cropbox[1]),
        )
    page_rect = getattr(page, "rect", None)
    if page_rect is not None and hasattr(page_rect, "width") and hasattr(page_rect, "height"):
        return float(page_rect.width), float(page_rect.height)
    if page_rect is not None and all(hasattr(page_rect, attr) for attr in ("x0", "y0", "x1", "y1")):
        return float(page_rect.x1) - float(page_rect.x0), float(page_rect.y1) - float(page_rect.y0)
    if isinstance(page_rect, (list, tuple)) and len(page_rect) == 4:
        return float(page_rect[2]) - float(page_rect[0]), float(page_rect[3]) - float(page_rect[1])
    return 1.0, 1.0
