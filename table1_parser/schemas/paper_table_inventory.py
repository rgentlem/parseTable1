"""Schemas for paper-level table taxonomy predictions."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


TableCategory = Literal[
    "demographic_description",
    "analysis_outputs",
    "data_presentation",
    "general",
    "unknown",
    "non_table_artifact",
]


class PaperTableRecord(BaseModel):
    """One table-level taxonomy prediction within a paper."""

    table_id: str
    table_number: int | None = Field(default=None, ge=1)
    title: str | None = None
    caption: str | None = None
    table_category: TableCategory
    category_confidence: float = Field(ge=0.0, le=1.0)
    category_evidence: list[str] = Field(default_factory=list)
    continuation_of_table_number: int | None = Field(default=None, ge=1)
    table_family: str | None = None
    processing_status: str | None = None
    failure_reason: str | None = None


class PaperTableInventory(BaseModel):
    """Paper-level inventory of table taxonomy predictions."""

    paper_id: str
    tables: list[PaperTableRecord] = Field(default_factory=list)
