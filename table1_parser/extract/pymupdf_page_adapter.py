"""Small PyMuPDF adapter for fallback page geometry extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from table1_parser.text_cleaning import repair_extractor_glyph_failures


SYMBOL_FONT_CHAR_MAPS: dict[str, dict[str, str]] = {
    "AdvPS586B": {
        ",": "<",
        "2": "−",
        "3": "×",
        "6": "±",
    },
}


def open_pymupdf_document(pdf_path: str) -> Any:
    """Open a PDF with PyMuPDF."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    try:
        import pymupdf
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError("pymupdf is required for PyMuPDF geometry extraction.") from exc
    return pymupdf.open(path)


def bbox_from_pymupdf_value(value: Any) -> tuple[float, float, float, float] | None:
    """Convert a PyMuPDF bbox-like value to a plain tuple."""
    if all(hasattr(value, attr) for attr in ("x0", "y0", "x1", "y1")):
        return (float(value.x0), float(value.y0), float(value.x1), float(value.y1))
    if isinstance(value, (list, tuple)) and len(value) == 4:
        return (float(value[0]), float(value[1]), float(value[2]), float(value[3]))
    return None


def join_pymupdf_line_spans(spans: Any, *, gap_tolerance: float = 1.0) -> str:
    """Join same-line PyMuPDF spans without adding spaces inside split words."""
    if not isinstance(spans, list):
        return ""
    positioned_parts: list[tuple[float, float, str]] = []
    raw_parts: list[str] = []
    for span in spans:
        if not isinstance(span, dict):
            continue
        span_text = repair_extractor_glyph_failures(str(span.get("text", "")))
        if not span_text:
            continue
        raw_parts.append(span_text)
        bbox = bbox_from_pymupdf_value(span.get("bbox"))
        if bbox is not None:
            positioned_parts.append((bbox[0], bbox[2], span_text))
    if not positioned_parts or len(positioned_parts) != len(raw_parts):
        text_parts: list[str] = []
        for span_text in raw_parts:
            if text_parts and not text_parts[-1][-1].isspace() and not span_text[0].isspace():
                text_parts.append(" ")
            text_parts.append(span_text)
        return "".join(text_parts).strip()

    text_parts: list[str] = []
    previous_x1: float | None = None
    for x0, x1, span_text in sorted(positioned_parts, key=lambda part: part[0]):
        if (
            previous_x1 is not None
            and x0 - previous_x1 > gap_tolerance
            and text_parts
            and not text_parts[-1][-1].isspace()
            and not span_text[0].isspace()
        ):
            text_parts.append(" ")
        text_parts.append(span_text)
        previous_x1 = x1 if previous_x1 is None else max(previous_x1, x1)
    return "".join(text_parts).strip()


def extract_page_text(page: Any) -> str:
    """Extract plain page text while tolerating backend quirks."""
    try:
        return (page.get_text("text") or "").strip()
    except Exception:
        return ""


def extract_page_words(page: Any) -> list[dict[str, object]]:
    """Extract normalized positioned words from a PyMuPDF page."""
    try:
        raw_words = page.get_text("words") or []
    except Exception:
        return []
    page_chars = extract_page_chars(page)
    words: list[dict[str, object]] = []
    for word in raw_words:
        if not isinstance(word, (list, tuple)) or len(word) < 5:
            continue
        x0, top, x1, bottom, text = word[:5]
        word_text = str(text).strip()
        chars_in_word = [
            char
            for char in page_chars
            if float(char["x0"]) >= float(x0) - 0.5
            and float(char["x1"]) <= float(x1) + 0.5
            and float(char["top"]) >= float(top) - 0.5
            and float(char["bottom"]) <= float(bottom) + 0.5
        ]
        if chars_in_word:
            rebuilt_text = "".join(
                str(char.get("text", ""))
                for char in sorted(chars_in_word, key=lambda char: int(char.get("char_index", 0)))
            ).strip()
            if rebuilt_text:
                word_text = rebuilt_text
        words.append(
            {
                "text": word_text,
                "x0": float(x0),
                "x1": float(x1),
                "top": float(top),
                "bottom": float(bottom),
            }
        )
    return words


def extract_page_chars(page: Any, page_num: int | None = None) -> list[dict[str, object]]:
    """Extract normalized positioned chars from a PyMuPDF page."""
    try:
        raw = page.get_text("rawdict") or {}
    except Exception:
        return []
    chars: list[dict[str, object]] = []
    for block in raw.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                span_font_size = span.get("size")
                span_font = span.get("font")
                span_flags = span.get("flags")
                for char in span.get("chars", []):
                    bbox_value = char.get("bbox")
                    bbox = bbox_from_pymupdf_value(bbox_value)
                    if bbox is None:
                        continue
                    raw_text = str(char.get("c", ""))
                    normalized_text = _normalize_symbol_font_char(raw_text, span_font)
                    char_record: dict[str, object] = {
                        "text": normalized_text,
                        "x0": bbox[0],
                        "x1": bbox[2],
                        "top": bbox[1],
                        "bottom": bbox[3],
                        "char_height": bbox[3] - bbox[1],
                        "char_index": len(chars),
                    }
                    if normalized_text != raw_text:
                        char_record["raw_text"] = raw_text
                        char_record["text_normalization"] = "symbol_font_char_map"
                    if page_num is not None:
                        char_record["page_num"] = page_num
                    if isinstance(span_font_size, (int, float)):
                        char_record["font_size"] = float(span_font_size)
                    if isinstance(span_font, str):
                        char_record["font"] = span_font
                    if isinstance(span_flags, int):
                        char_record["span_flags"] = span_flags
                    chars.append(char_record)
    return chars


def _normalize_symbol_font_char(text: str, font: object) -> str:
    """Map known embedded-symbol font codes to their Unicode text equivalents."""
    if not isinstance(font, str):
        return text
    return SYMBOL_FONT_CHAR_MAPS.get(font, {}).get(text, text)


def extract_page_rule_segments(
    page: Any,
    *,
    include_filled: bool = True,
) -> list[tuple[float, float, float, float]]:
    """Extract candidate horizontal drawing segments from a PyMuPDF page."""
    try:
        drawings = page.get_drawings() or []
    except Exception:
        return []
    segments: list[tuple[float, float, float, float]] = []
    for drawing in drawings:
        rect_value = drawing.get("rect")
        if rect_value is None:
            rect = None
        elif all(hasattr(rect_value, attr) for attr in ("x0", "y0", "x1", "y1")):
            rect = (float(rect_value.x0), float(rect_value.y0), float(rect_value.x1), float(rect_value.y1))
        elif isinstance(rect_value, (list, tuple)) and len(rect_value) == 4:
            rect = (float(rect_value[0]), float(rect_value[1]), float(rect_value[2]), float(rect_value[3]))
        else:
            rect = None
        if rect is not None and (include_filled or abs(rect[3] - rect[1]) <= 1.5):
            segments.append(rect)
        if not include_filled and drawing.get("fill") is not None and drawing.get("color") is None:
            continue
        for item in drawing.get("items", []):
            if not isinstance(item, tuple) or len(item) < 3 or item[0] != "l":
                segment = None
            else:
                start = _coerce_point(item[1])
                end = _coerce_point(item[2])
                segment = None if start is None or end is None else (start[0], start[1], end[0], end[1])
            if segment is not None:
                segments.append(segment)
    return segments


def extract_clipped_line_directions(
    page: Any,
    clip_bbox: tuple[float, float, float, float] | None,
) -> list[tuple[float, float]]:
    """Extract line direction vectors from a clipped PyMuPDF page region."""
    if clip_bbox is None:
        return []
    try:
        raw = page.get_text("dict", clip=clip_bbox) or {}
    except Exception:
        return []
    directions: list[tuple[float, float]] = []
    for block in raw.get("blocks", []):
        for line in block.get("lines", []):
            direction = line.get("dir")
            if not isinstance(direction, (list, tuple)) or len(direction) != 2:
                continue
            directions.append((float(direction[0]), float(direction[1])))
    return directions


def _coerce_point(value: Any) -> tuple[float, float] | None:
    """Convert a point-like object to a numeric pair."""
    if value is None:
        return None
    if all(hasattr(value, attr) for attr in ("x", "y")):
        return (float(value.x), float(value.y))
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return (float(value[0]), float(value[1]))
    return None
