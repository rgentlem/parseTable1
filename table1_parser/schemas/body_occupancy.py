"""Schemas for raw canonical body-character occupancy evidence."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BodyOccupancyLine(BaseModel):
    """One physical body line represented in the occupancy matrix."""

    line_id: str
    source_line_ids: list[str] = Field(default_factory=list)
    source_row_indices: list[int] = Field(default_factory=list)
    canonical_bbox: tuple[float, float, float, float]
    ordinary_character_count: int = Field(ge=0)
    excluded_marker_ids: list[str] = Field(default_factory=list)
    excluded_marker_char_indices: list[int] = Field(default_factory=list)


class BodyOccupancyGap(BaseModel):
    """One exact internal zero-occupancy interval wide enough to separate columns."""

    canonical_x_bounds: tuple[float, float]
    width: float = Field(gt=0.0)


class BodyOccupancyTable(BaseModel):
    """Raw physical-line by x-bin occupancy for one extracted table body."""

    table_id: str
    page_num: int = Field(ge=1)
    coordinate_frame: Literal["paper_text_orientation_group"] = (
        "paper_text_orientation_group"
    )
    source_artifacts: list[str] = Field(default_factory=list)
    body_row_indices: list[int] = Field(default_factory=list)
    x_min: float | None = None
    x_max: float | None = None
    bin_width: float | None = Field(default=None, gt=0.0)
    bin_count: int = Field(default=0, ge=0)
    lines: list[BodyOccupancyLine] = Field(default_factory=list)
    occupancy_matrix: list[list[Literal[0, 1]]] = Field(default_factory=list)
    occupied_line_counts: list[int] = Field(default_factory=list)
    occupied_line_proportions: list[float] = Field(default_factory=list)
    dominant_body_font: str | None = None
    dominant_body_font_size: float | None = Field(default=None, gt=0.0)
    median_body_space_width: float | None = Field(default=None, gt=0.0)
    space_width_source: Literal["table_evidence", "paper_font_style"] | None = None
    minimum_separator_gap_width: float | None = Field(default=None, gt=0.0)
    qualified_zero_gaps: list[BodyOccupancyGap] = Field(default_factory=list)
    excluded_marker_ids: list[str] = Field(default_factory=list)
    unlinked_marker_ids: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
