"""Schemas for one shared positioned-text pass over a paper PDF."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PaperPositionedSpan(BaseModel):
    """One PyMuPDF text span with geometry and font evidence."""

    text: str
    bbox: tuple[float, float, float, float]
    font: str | None = None
    font_size: float | None = None
    flags: int | None = None


class PaperPositionedWord(BaseModel):
    """One positioned word from PyMuPDF word extraction."""

    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    block_index: int | None = Field(default=None, ge=0)
    line_index: int | None = Field(default=None, ge=0)


class PaperPositionedChar(BaseModel):
    """One positioned character from PyMuPDF raw character extraction."""

    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    char_height: float
    char_index: int = Field(ge=0)
    block_index: int | None = Field(default=None, ge=0)
    line_index: int | None = Field(default=None, ge=0)
    span_index: int | None = Field(default=None, ge=0)
    char_in_span_index: int | None = Field(default=None, ge=0)
    page_num: int | None = Field(default=None, ge=1)
    font_size: float | None = None
    font: str | None = None
    span_flags: int | None = None
    raw_text: str | None = None
    text_normalization: str | None = None


class PaperPositionedLine(BaseModel):
    """One visual PDF text line from the shared positioned-document pass."""

    line_id: str
    page_num: int = Field(ge=1)
    block_index: int | None = Field(default=None, ge=0)
    line_index: int | None = Field(default=None, ge=0)
    page_line_index: int = Field(ge=0)
    raw_text: str
    text: str
    bbox: tuple[float, float, float, float]
    direction: tuple[float, float] | None = None
    orientation: str | None = None
    bold_like: bool = False
    dominant_font: str | None = None
    dominant_font_size: float | None = None
    dominant_style_character_count: int = Field(default=0, ge=0)
    spans: list[PaperPositionedSpan] = Field(default_factory=list)
    font_style_counts: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class PaperPositionedPage(BaseModel):
    """Positioned text extracted from one PDF page."""

    page_num: int = Field(ge=1)
    page_width: float = Field(gt=0.0)
    page_height: float = Field(gt=0.0)
    text: str = ""
    lines: list[PaperPositionedLine] = Field(default_factory=list)
    words: list[PaperPositionedWord] = Field(default_factory=list)
    chars: list[PaperPositionedChar] = Field(default_factory=list)
    image_bboxes: list[tuple[float, float, float, float]] = Field(
        default_factory=list
    )
    rule_segments: list[tuple[float, float, float, float]] = Field(default_factory=list)
    stroked_rule_segments: list[tuple[float, float, float, float]] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)


class PaperPositionedDocument(BaseModel):
    """Shared positioned-text artifact used by paper-level parser stages."""

    paper_id: str
    source_pdf: str
    page_count: int = Field(ge=0)
    pages: list[PaperPositionedPage] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
