"""Small PyMuPDF adapter for fallback page geometry extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Any


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
    words: list[dict[str, object]] = []
    for word in raw_words:
        if not isinstance(word, (list, tuple)) or len(word) < 5:
            continue
        x0, top, x1, bottom, text = word[:5]
        words.append(
            {
                "text": str(text).strip(),
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
                    if bbox_value is None:
                        bbox = None
                    elif all(hasattr(bbox_value, attr) for attr in ("x0", "y0", "x1", "y1")):
                        bbox = (float(bbox_value.x0), float(bbox_value.y0), float(bbox_value.x1), float(bbox_value.y1))
                    elif isinstance(bbox_value, (list, tuple)) and len(bbox_value) == 4:
                        bbox = tuple(float(part) for part in bbox_value)
                    else:
                        bbox = None
                    if bbox is None:
                        continue
                    char_record: dict[str, object] = {
                        "text": str(char.get("c", "")),
                        "x0": bbox[0],
                        "x1": bbox[2],
                        "top": bbox[1],
                        "bottom": bbox[3],
                        "char_height": bbox[3] - bbox[1],
                    }
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


def extract_page_rule_segments(page: Any) -> list[tuple[float, float, float, float]]:
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
        if rect is not None:
            segments.append(rect)
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
