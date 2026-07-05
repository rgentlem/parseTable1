"""Schemas for inferred paper-level style conventions."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PaperStyleEvidence(BaseModel):
    """One observed source item supporting a paper-style inference."""

    evidence_id: str
    style: str
    source_artifact: str
    source_id: str | None = None
    page_num: int | None = Field(default=None, ge=1)
    table_id: str | None = None
    text: str | None = None
    notes: list[str] = Field(default_factory=list)


class PaperStyleDimension(BaseModel):
    """A single inferred style dimension with counts and examples."""

    dimension: str
    likely_style: str
    confidence: float = Field(ge=0.0, le=1.0)
    count_by_style: dict[str, int] = Field(default_factory=dict)
    count_by_source: dict[str, int] = Field(default_factory=dict)
    secondary_counts: dict[str, dict[str, int]] = Field(default_factory=dict)
    evidence: list[PaperStyleEvidence] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class PaperStyleCheck(BaseModel):
    """One consistency check comparing inferred style with parsed evidence."""

    check_id: str
    check_type: str
    status: str
    message: str
    evidence: list[PaperStyleEvidence] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class PaperStyleProfile(BaseModel):
    """Paper-level summary of observed reference, footnote, and caption conventions."""

    paper_id: str
    source_pdf: str
    footnote_marker_style: PaperStyleDimension
    bibliography_reference_style: PaperStyleDimension
    table_caption_placement: PaperStyleDimension
    figure_caption_evidence: PaperStyleDimension
    visual_reference_style: PaperStyleDimension
    checks: list[PaperStyleCheck] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
