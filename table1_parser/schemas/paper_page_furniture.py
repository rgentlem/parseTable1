"""Schemas for repeated paper-level page furniture."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field


PageFurnitureRecurrenceScope = Literal["all_pages", "odd_pages", "even_pages", "page_subset"]
PaperPageScopeDetectionStatus = Literal["unknown", "detected"]


@dataclass(frozen=True)
class PaperPageScope:
    """Authoritative paper boundary within the physical PDF."""

    physical_page_count: int
    detection_status: PaperPageScopeDetectionStatus
    reported_paper_page_total: int | None
    terminal_pdf_page_num: int | None
    included_page_nums: list[int] = field(default_factory=list)
    excluded_trailing_page_nums: list[int] = field(default_factory=list)
    printed_page_offset: int | None = None
    source_observation_ids: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)


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
    """Repeated text cluster with intersecting page-relative position and orientation."""

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


class PageFurnitureRuleRegion(BaseModel):
    """One recurrent page rule excluded from table geometry."""

    region_id: str
    rule_cluster_id: str
    page_num: int = Field(ge=1)
    bbox: tuple[float, float, float, float]
    relative_bbox: tuple[float, float, float, float]
    recurrence_page_nums: list[int]
    page_fraction: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    source_artifact: str = "paper_positioned_document.json"
    recurrence_basis: list[str] = Field(default_factory=list)


class PaperPageFurniture(BaseModel):
    """Paper-level repeated page-furniture artifact."""

    paper_id: str
    source_pdf: str
    page_scope: PaperPageScope
    observations: list[PageFurnitureTextObservation] = Field(default_factory=list)
    clusters: list[PageFurnitureCluster] = Field(default_factory=list)
    ignored_regions: list[PageFurnitureRegion] = Field(default_factory=list)
    ignored_rule_regions: list[PageFurnitureRuleRegion] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
