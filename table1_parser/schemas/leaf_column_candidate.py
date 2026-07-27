"""Schemas for provisional geometry-only physical-column candidates."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LeafColumnRuleEndpointEvidence(BaseModel):
    """One unmerged horizontal-rule endpoint inside an occupancy valley."""

    source: Literal["rule_segment", "stroked_rule_segment"]
    source_index: int = Field(ge=0)
    endpoint: Literal["left", "right"]
    canonical_x: float
    canonical_segment: tuple[float, float, float, float]


class LeafColumnSeparatorCandidate(BaseModel):
    """One exact font-qualified zero-occupancy gap between body bands."""

    separator_id: str
    canonical_x_bounds: tuple[float, float]
    canonical_x: float
    gap_width: float = Field(gt=0.0)
    minimum_gap_width: float = Field(gt=0.0)
    rule_endpoints: list[LeafColumnRuleEndpointEvidence] = Field(default_factory=list)


class PhysicalColumnBandCandidate(BaseModel):
    """One provisional physical column band bounded by occupancy valleys."""

    band_id: str
    canonical_x_bounds: tuple[float, float]
    left_separator_id: str | None = None
    right_separator_id: str | None = None
    minimum_occupied_line_count: int = Field(ge=1)
    maximum_occupied_line_count: int = Field(ge=1)


class LeafColumnCandidateTable(BaseModel):
    """Legacy-named provisional physical-band evidence for one table."""

    table_id: str
    page_num: int = Field(ge=1)
    coordinate_frame: Literal["paper_text_orientation_group"] = (
        "paper_text_orientation_group"
    )
    source_artifacts: list[str] = Field(default_factory=list)
    body_line_count: int = Field(ge=0)
    bin_width: float | None = Field(default=None, gt=0.0)
    separators: list[LeafColumnSeparatorCandidate] = Field(default_factory=list)
    bands: list[PhysicalColumnBandCandidate] = Field(default_factory=list)
    physical_band_ids: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
