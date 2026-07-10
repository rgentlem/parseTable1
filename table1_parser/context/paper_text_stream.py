"""Build a layout-aware paper text stream from positioned PDF text."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from table1_parser.extract.pymupdf_page_adapter import (
    bbox_from_pymupdf_value,
    join_pymupdf_line_spans,
    open_pymupdf_document,
)
from table1_parser.page_furniture_mask import page_furniture_cluster_ids_for_bbox
from table1_parser.paper_page_furniture import normalize_page_furniture_text
from table1_parser.reference_sections import INLINE_REFERENCE_START_PATTERN
from table1_parser.schemas import PaperPageFurniture, PaperTextLine, PaperTextPage, PaperTextStream
from table1_parser.text_cleaning import clean_text


BODY_TEXT_STYLE_MIN_FONT_SIZE = 5.0
BODY_TEXT_STYLE_MAX_FONT_SIZE = 18.0
SECTION_HEADING_TEXTS = {
    "abstract",
    "introduction",
    "methods",
    "materials and methods",
    "patients and methods",
    "study population",
    "healthy lifestyle score",
    "covariates",
    "assessment of the outcomes",
    "statistical analysis",
    "results",
    "discussion",
    "conclusion",
    "conclusions",
    "supplementary information",
    "acknowledgements",
    "acknowledgments",
    "author contributions",
    "funding",
    "availability of data and materials",
    "declarations",
    "ethics approval and consent to participate",
    "consent for publication",
    "competing interests",
    "author details",
    "references",
    "bibliography",
    "works cited",
    "literature cited",
    "abbreviations",
    "publisher's note",
    "publisher’s note",
}
TABLE_CAPTION_LINE_PATTERN = re.compile(r"^\s*table\s+[A-Za-z]?\d+[A-Za-z]?\b", re.IGNORECASE)


def build_paper_text_stream(
    pdf_path: str,
    *,
    paper_page_furniture: PaperPageFurniture | None = None,
    paper_id: str | None = None,
) -> PaperTextStream:
    """Build layout-aware full-paper text ordered by page, column, then y-position."""
    try:
        document = open_pymupdf_document(pdf_path)
    except Exception:  # noqa: BLE001
        return PaperTextStream(
            paper_id=paper_id or Path(pdf_path).stem,
            source_pdf=Path(pdf_path).name,
            metadata={"diagnostics": ["pymupdf_open_failed"], "source_artifacts": ["pymupdf_page_text_lines"]},
        )

    stream_lines: list[PaperTextLine] = []
    stream_pages: list[PaperTextPage] = []
    font_style_counts: Counter[tuple[str, float]] = Counter()
    removed_furniture_line_count = 0
    furniture_text_keys, furniture_text_patterns = _page_furniture_text_matchers(paper_page_furniture)
    try:
        page_count = int(getattr(document, "page_count", 0))
        for page_index in range(page_count):
            page_num = page_index + 1
            try:
                page = document.load_page(page_index)
                page_dict = page.get_text("dict") or {}
            except Exception:  # noqa: BLE001
                stream_pages.append(
                    PaperTextPage(
                        page_num=page_num,
                        page_width=1.0,
                        page_height=1.0,
                        column_count=1,
                        column_boundaries=[],
                        column_bands=[(0.0, 1.0)],
                        line_count=0,
                        removed_page_furniture_line_count=0,
                        diagnostics=["page_text_extraction_failed"],
                    )
                )
                continue

            page_width, page_height = _page_size(page)
            page_line_records: list[dict[str, object]] = []
            removed_on_page = 0
            for block_index, block in enumerate(page_dict.get("blocks", [])):
                for line_index, line in enumerate(block.get("lines", [])):
                    line_record = _line_record_from_pymupdf_line(line, block_index, line_index)
                    if line_record is None:
                        continue
                    if _is_page_furniture_text(line_record["text"], furniture_text_keys, furniture_text_patterns):
                        removed_on_page += 1
                        continue
                    if page_furniture_cluster_ids_for_bbox(
                        paper_page_furniture,
                        page_num=page_num,
                        bbox=line_record["bbox"],
                        min_overlap_fraction=0.8,
                    ):
                        removed_on_page += 1
                        continue
                    page_line_records.append(line_record)

            column_count, column_boundaries, column_bands, diagnostics = _detect_page_columns(
                page_line_records,
                page_width,
            )
            ordered_records = _order_page_lines(page_line_records, column_boundaries, page_width)
            for logical_index, record in enumerate(ordered_records):
                text = str(record["text"])
                role = "heading" if _looks_like_section_heading(text, bool(record.get("bold_like"))) else "body"
                column_index = int(record.get("column_index", 0))
                line_notes = list(record.get("notes", [])) if isinstance(record.get("notes"), list) else []
                if record.get("bold_like"):
                    line_notes.append("bold_like_text")
                if role == "heading":
                    line_notes.append("layout_section_heading")
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
                        line_id=f"page-{page_num}-line-{logical_index}",
                        page_num=page_num,
                        block_index=int(record["block_index"]) if isinstance(record.get("block_index"), int) else None,
                        line_index=int(record["line_index"]) if isinstance(record.get("line_index"), int) else None,
                        raw_text=str(record["raw_text"]),
                        text=text,
                        bbox=record["bbox"],
                        column_index=column_index,
                        column_count=column_count,
                        role=role,
                        confidence=0.86 if role == "heading" else 0.78,
                        dominant_font=str(record["dominant_font"]) if isinstance(record.get("dominant_font"), str) else None,
                        dominant_font_size=float(record["dominant_font_size"]) if isinstance(record.get("dominant_font_size"), (int, float)) else None,
                        spans=list(record.get("spans", [])) if isinstance(record.get("spans"), list) else [],
                        notes=line_notes,
                    )
                )
            removed_furniture_line_count += removed_on_page
            stream_pages.append(
                PaperTextPage(
                    page_num=page_num,
                    page_width=page_width,
                    page_height=page_height,
                    column_count=column_count,
                    column_boundaries=column_boundaries,
                    column_bands=column_bands,
                    line_count=len(ordered_records),
                    removed_page_furniture_line_count=removed_on_page,
                    diagnostics=diagnostics,
                )
            )
    finally:
        close = getattr(document, "close", None)
        if callable(close):
            close()

    markdown = paper_text_stream_to_markdown(stream_lines)
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
    return PaperTextStream(
        paper_id=paper_id or Path(pdf_path).stem,
        source_pdf=Path(pdf_path).name,
        markdown=markdown,
        lines=stream_lines,
        pages=stream_pages,
        metadata={
            "source_artifacts": ["pymupdf_page_text_lines", "paper_page_furniture.json"],
            "line_count": len(stream_lines),
            "page_count": len(stream_pages),
            "removed_page_furniture_line_count": removed_furniture_line_count,
            "column_order": "page_then_column_then_y",
            "font_style_character_counts": font_style_summary,
            "dominant_body_text_style": font_style_summary[0] if font_style_summary else None,
        },
    )


def paper_text_stream_to_markdown(lines: list[PaperTextLine]) -> str:
    """Render layout-ordered paper text lines as lightweight markdown for section parsing."""
    markdown_lines: list[str] = []
    previous_page_num: int | None = None
    for line in lines:
        if previous_page_num is not None and line.page_num != previous_page_num:
            markdown_lines.append("")
        previous_page_num = line.page_num
        inline_match = INLINE_REFERENCE_START_PATTERN.match(line.text)
        if inline_match is not None:
            markdown_lines.append(f"## {inline_match.group('heading')}")
            markdown_lines.append(inline_match.group("body"))
            continue
        if line.role == "heading":
            if markdown_lines and markdown_lines[-1] != "":
                markdown_lines.append("")
            markdown_lines.append(f"## {line.text}")
            markdown_lines.append("")
            continue
        markdown_lines.append(line.text)
    return "\n".join(markdown_lines).strip() + ("\n" if markdown_lines else "")

def _line_record_from_pymupdf_line(
    line: dict[str, object],
    block_index: int,
    line_index: int,
) -> dict[str, object] | None:
    bbox_parts: list[tuple[float, float, float, float]] = []
    span_counts: Counter[tuple[str, float]] = Counter()
    span_records: list[dict[str, object]] = []
    bold_like = False
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
                {
                    "text": span_text,
                    "bbox": bbox,
                    "font": font,
                    "font_size": font_size,
                    "flags": span_flags if isinstance(span_flags, int) else None,
                }
            )
        font = str(span.get("font", "")).lower()
        flags = span.get("flags")
        if "bold" in font or "semibold" in font or (isinstance(flags, int) and flags & 16):
            bold_like = True
    raw_text = join_pymupdf_line_spans(line.get("spans", []))
    text = clean_text(raw_text)
    if not text or not bbox_parts:
        return None
    dominant_font = None
    dominant_font_size = None
    dominant_style_character_count = 0
    if span_counts:
        (dominant_font, dominant_font_size), dominant_style_character_count = span_counts.most_common(1)[0]
    return {
        "raw_text": raw_text,
        "text": text,
        "bbox": (
            min(part[0] for part in bbox_parts),
            min(part[1] for part in bbox_parts),
            max(part[2] for part in bbox_parts),
            max(part[3] for part in bbox_parts),
        ),
        "block_index": block_index,
        "line_index": line_index,
        "bold_like": bold_like,
        "dominant_font": dominant_font,
        "dominant_font_size": dominant_font_size,
        "dominant_style_character_count": dominant_style_character_count,
        "spans": span_records,
        "font_style_counts": [
            {
                "font": font,
                "font_size": font_size,
                "character_count": character_count,
            }
            for (font, font_size), character_count in span_counts.most_common()
        ],
        "notes": [],
    }

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


def _order_page_lines(
    line_records: list[dict[str, object]],
    column_boundaries: list[float],
    page_width: float,
) -> list[dict[str, object]]:
    column_count = len(column_boundaries) + 1
    if column_count <= 1:
        ordered = sorted(line_records, key=lambda record: (float(record["bbox"][1]), float(record["bbox"][0])))
        for record in ordered:
            record["column_index"] = 0
        return ordered

    top_full_width: list[dict[str, object]] = []
    bottom_full_width: list[dict[str, object]] = []
    column_records: list[dict[str, object]] = []
    non_full_records = [
        record
        for record in line_records
        if not _is_full_width_record(record, page_width)
    ]
    min_column_top = min((float(record["bbox"][1]) for record in non_full_records), default=0.0)
    max_column_bottom = max((float(record["bbox"][3]) for record in non_full_records), default=0.0)
    for record in line_records:
        if _is_full_width_record(record, page_width):
            record["column_index"] = 0
            record.setdefault("notes", []).append("full_width_line")
            if float(record["bbox"][3]) <= min_column_top + 4.0:
                top_full_width.append(record)
            elif float(record["bbox"][1]) >= max_column_bottom - 4.0:
                bottom_full_width.append(record)
            else:
                column_records.append(record)
            continue
        record["column_index"] = sum(float(record["bbox"][0]) >= boundary for boundary in column_boundaries)
        column_records.append(record)

    ordered_columns: list[dict[str, object]] = []
    for column_index in range(column_count):
        ordered_columns.extend(
            sorted(
                [record for record in column_records if int(record.get("column_index", 0)) == column_index],
                key=lambda record: (float(record["bbox"][1]), float(record["bbox"][0])),
            )
        )
    return [
        *sorted(top_full_width, key=lambda record: (float(record["bbox"][1]), float(record["bbox"][0]))),
        *ordered_columns,
        *sorted(bottom_full_width, key=lambda record: (float(record["bbox"][1]), float(record["bbox"][0]))),
    ]


def _looks_like_section_heading(text: str, bold_like: bool) -> bool:
    normalized = clean_text(text).strip(" :").lower()
    if not normalized or len(normalized) > 120:
        return False
    if normalized in SECTION_HEADING_TEXTS:
        return True
    if bold_like and len(normalized.split()) <= 8 and not re.search(r"[.;,]\s", normalized):
        return True
    return False


def _page_size(page: Any) -> tuple[float, float]:
    page_rect = getattr(page, "rect", None)
    if page_rect is not None and hasattr(page_rect, "width") and hasattr(page_rect, "height"):
        return float(page_rect.width), float(page_rect.height)
    if page_rect is not None and all(hasattr(page_rect, attr) for attr in ("x0", "y0", "x1", "y1")):
        return float(page_rect.x1) - float(page_rect.x0), float(page_rect.y1) - float(page_rect.y0)
    if isinstance(page_rect, (list, tuple)) and len(page_rect) == 4:
        return float(page_rect[2]) - float(page_rect[0]), float(page_rect[3]) - float(page_rect[1])
    return 1.0, 1.0


def _bbox_width(bbox: object) -> float:
    left, _top, right, _bottom = bbox
    return float(right) - float(left)


def _is_full_width_record(record: dict[str, object], page_width: float) -> bool:
    bbox = record["bbox"]
    width_fraction = _bbox_width(bbox) / page_width if page_width > 0.0 else 0.0
    return width_fraction >= 0.72 and float(bbox[0]) <= page_width * 0.22 and float(bbox[2]) >= page_width * 0.78
