"""Schemas for diagnostic body token-left-edge evidence."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


TokenStartEvaluationReason = Literal[
    "grid_count_disagreement",
    "cross_band_header_run",
    "non_stub_band_without_header_text",
    "ambiguous_header_attachment",
    "leaf_candidate_concern_or_diagnostic",
    "header_candidate_diagnostic",
]


class TokenStartObservation(BaseModel):
    """One exact ordinary-token left edge on a physical body line."""

    observation_id: str
    source_word_index: int = Field(ge=0)
    source_char_index: int = Field(ge=0)
    source_line_id: str
    source_row_idx: int = Field(ge=0)
    canonical_x: float
    canonical_bbox: tuple[float, float, float, float]
    occupancy_band_id: str | None = None


class TokenStartLineEvidence(BaseModel):
    """Exact token starts observed on one positioned physical body line."""

    line_id: str
    source_line_ids: list[str] = Field(default_factory=list)
    source_row_indices: list[int] = Field(default_factory=list)
    observations: list[TokenStartObservation] = Field(default_factory=list)


class TokenStartEvidenceTable(BaseModel):
    """Non-operative token-start distribution for one extracted table."""

    table_id: str
    page_num: int = Field(ge=1)
    coordinate_frame: Literal["paper_text_orientation_group"] = (
        "paper_text_orientation_group"
    )
    source_artifacts: list[str] = Field(default_factory=list)
    evaluated: bool = False
    evaluation_reasons: list[TokenStartEvaluationReason] = Field(default_factory=list)
    body_line_count: int = Field(default=0, ge=0)
    observed_line_count: int = Field(default=0, ge=0)
    observation_count: int = Field(default=0, ge=0)
    x_min: float | None = None
    bin_width: float | None = Field(default=None, gt=0.0)
    bin_count: int = Field(default=0, ge=0)
    token_start_counts: list[int] = Field(default_factory=list)
    token_start_line_counts: list[int] = Field(default_factory=list)
    lines: list[TokenStartLineEvidence] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
