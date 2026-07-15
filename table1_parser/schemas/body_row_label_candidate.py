"""Schemas for logical body row-label candidates built over physical rows."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


BodyRowLabelCandidateKind = Literal["vertical_label_continuation"]


class BodyRowLabelSourceCell(BaseModel):
    """One physical source cell contributing to a logical row label."""

    source_table_index: int = Field(ge=0)
    source_table_id: str
    row_idx: int = Field(ge=0)
    col_idx: int = Field(ge=0)
    original_row_idx: int | None = Field(default=None, ge=0)
    original_col_idx: int | None = Field(default=None, ge=0)
    text: str
    cleaned_text: str
    bbox: tuple[float, float, float, float] | None = None
    page_num: int | None = Field(default=None, ge=1)


class BodyRowLabelCandidate(BaseModel):
    """A candidate logical row label assembled from one or more source cells."""

    candidate_id: str
    source_table_index: int = Field(ge=0)
    source_table_id: str
    anchor_row_idx: int = Field(ge=0)
    anchor_col_idx: int = Field(ge=0)
    kind: BodyRowLabelCandidateKind
    candidate_label: str
    raw_text: str = ""
    base_text: str = ""
    marker_ids: list[str] = Field(default_factory=list)
    raw_fragments: list[str] = Field(default_factory=list)
    source_cells: list[BodyRowLabelSourceCell] = Field(default_factory=list)
    continuation_row_indices: list[int] = Field(default_factory=list)
    reason: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)
