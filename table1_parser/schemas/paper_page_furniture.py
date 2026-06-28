"""Schemas for repeated paper-level page furniture."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


PageFurnitureRecurrenceScope = Literal["all_pages", "odd_pages", "even_pages", "page_subset"]


class PageFurnitureTextObservation(BaseModel):
    """One positioned text observation used as page-furniture evidence."""

    observation_id: str
    page_num: int = Field(ge=1)
    raw_text: str
    normalized_text: str
    bbox: tuple[float, float, float, float]
    relative_bbox: tuple[float, float, float, float]
    page_width: float = Field(gt=0.0)
    page_height: float = Field(gt=0.0)
    orientation: str | None = None
    block_index: int | None = Field(default=None, ge=0)
    line_index: int | None = Field(default=None, ge=0)
    source_artifact: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


class PageFurnitureCluster(BaseModel):
    """Repeated text cluster with stable page-relative position."""

    cluster_id: str
    normalized_text_key: str
    representative_text: str
    observation_ids: list[str]
    page_nums: list[int]
    occurrence_count: int = Field(ge=1)
    page_fraction: float = Field(ge=0.0, le=1.0)
    recurrence_scope: PageFurnitureRecurrenceScope = "all_pages"
    scope_page_count: int | None = Field(default=None, ge=1)
    scope_page_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    representative_bbox: tuple[float, float, float, float]
    representative_relative_bbox: tuple[float, float, float, float]
    recurrence_basis: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


class PageFurnitureRegion(BaseModel):
    """One page-specific region that downstream stages may ignore."""

    region_id: str
    cluster_id: str
    page_num: int = Field(ge=1)
    bbox: tuple[float, float, float, float]
    relative_bbox: tuple[float, float, float, float]
    source_observation_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


class PaperPageFurniture(BaseModel):
    """Paper-level repeated page-furniture artifact."""

    paper_id: str
    source_pdf: str
    observations: list[PageFurnitureTextObservation] = Field(default_factory=list)
    clusters: list[PageFurnitureCluster] = Field(default_factory=list)
    ignored_regions: list[PageFurnitureRegion] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
