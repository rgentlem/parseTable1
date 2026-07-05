"""Schemas for layout-aware paper text streams."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


PaperTextLineRole = Literal["body", "heading", "full_width"]


class PaperTextLine(BaseModel):
    """One layout-ordered text line used for paper context parsing."""

    line_id: str
    page_num: int = Field(ge=1)
    block_index: int | None = Field(default=None, ge=0)
    line_index: int | None = Field(default=None, ge=0)
    raw_text: str
    text: str
    bbox: tuple[float, float, float, float]
    column_index: int = Field(ge=0)
    column_count: int = Field(ge=1)
    role: PaperTextLineRole = "body"
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


class PaperTextPage(BaseModel):
    """Per-page column-detection metadata for paper context parsing."""

    page_num: int = Field(ge=1)
    page_width: float = Field(gt=0.0)
    page_height: float = Field(gt=0.0)
    column_count: int = Field(ge=1)
    split_x: float | None = None
    line_count: int = Field(ge=0)
    removed_page_furniture_line_count: int = Field(ge=0)
    diagnostics: list[str] = Field(default_factory=list)


class PaperTextStream(BaseModel):
    """Layout-aware paper text stream used by paper-level context artifacts."""

    paper_id: str
    source_pdf: str
    markdown: str = ""
    lines: list[PaperTextLine] = Field(default_factory=list)
    pages: list[PaperTextPage] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
