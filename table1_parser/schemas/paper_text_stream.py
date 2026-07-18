"""Schemas for layout-aware paper text streams."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


PaperTextLineRole = Literal["body", "heading", "full_width"]
PaperTextBlockRole = Literal["body", "heading", "full_width", "mixed"]
PaperTextOrientation = Literal["upright", "vertical_text_up", "vertical_text_down"]


class PaperTextLine(BaseModel):
    """One layout-ordered text line used for paper context parsing."""

    line_id: str
    page_num: int = Field(ge=1)
    block_index: int | None = Field(default=None, ge=0)
    line_index: int | None = Field(default=None, ge=0)
    raw_text: str
    text: str
    bbox: tuple[float, float, float, float]
    canonical_bbox: tuple[float, float, float, float] | None = None
    direction: tuple[float, float] | None = None
    orientation: PaperTextOrientation = "upright"
    orientation_group_id: str | None = None
    column_index: int = Field(ge=0)
    column_count: int = Field(ge=1)
    role: PaperTextLineRole = "body"
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    dominant_font: str | None = None
    dominant_font_size: float | None = None
    spans: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class PaperTextBlock(BaseModel):
    """One positioned source block in document reading order."""

    block_id: str
    order: int = Field(ge=0)
    page_num: int = Field(ge=1)
    source_block_index: int | None = Field(default=None, ge=0)
    orientation: PaperTextOrientation = "upright"
    orientation_group_id: str
    bbox: tuple[float, float, float, float]
    canonical_bbox: tuple[float, float, float, float]
    column_index: int = Field(ge=0)
    column_count: int = Field(ge=1)
    line_ids: list[str] = Field(min_length=1)
    role: PaperTextBlockRole = "body"
    prose_candidate: bool = False
    text: str = ""


class PaperTextOrientationGroup(BaseModel):
    """One page-local writing-direction group ordered in an upright frame."""

    group_id: str
    orientation: PaperTextOrientation
    source_bbox: tuple[float, float, float, float]
    canonical_width: float = Field(gt=0.0)
    canonical_height: float = Field(gt=0.0)
    line_count: int = Field(ge=1)
    column_count: int = Field(ge=1)
    column_boundaries: list[float] = Field(default_factory=list)
    column_bands: list[tuple[float, float]] = Field(default_factory=list)


class PaperTextPage(BaseModel):
    """Per-page column-detection metadata for paper context parsing."""

    page_num: int = Field(ge=1)
    page_width: float = Field(gt=0.0)
    page_height: float = Field(gt=0.0)
    column_count: int = Field(ge=1)
    column_boundaries: list[float] = Field(default_factory=list)
    column_bands: list[tuple[float, float]] = Field(default_factory=list)
    line_count: int = Field(ge=0)
    removed_page_furniture_line_count: int = Field(ge=0)
    orientation_groups: list[PaperTextOrientationGroup] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)


class PaperTextStream(BaseModel):
    """Layout-aware paper text stream used by paper-level context artifacts."""

    paper_id: str
    source_pdf: str
    markdown: str = ""
    lines: list[PaperTextLine] = Field(default_factory=list)
    blocks: list[PaperTextBlock] = Field(default_factory=list)
    pages: list[PaperTextPage] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
