"""Schemas for provisional geometry-only table boundary evidence."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


TableBoundaryRole = Literal["table_start", "header_body", "body_footer", "table_end"]
TableRuleSource = Literal["rule_segment", "stroked_rule_segment"]


class TableBoundaryRuleReference(BaseModel):
    """Reference to one unmerged rule segment in positioned table evidence."""

    source: TableRuleSource
    source_index: int = Field(ge=0)
    canonical_segment: tuple[float, float, float, float]


class TableBoundaryCandidate(BaseModel):
    """One provisional boundary supported by individual horizontal segments."""

    canonical_y: float
    possible_roles: list[TableBoundaryRole] = Field(default_factory=list)
    row_before_idx: int | None = Field(default=None, ge=0)
    row_after_idx: int | None = Field(default=None, ge=0)
    rule_references: list[TableBoundaryRuleReference] = Field(default_factory=list)
    table_coverage_fraction: float = Field(ge=0.0, le=1.0)
    stub_coverage_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    value_coverage_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    immediate_font_style_change: bool | None = None
    following_text_line_ids: list[str] = Field(default_factory=list)
    following_text_bbox: tuple[float, float, float, float] | None = None
    following_text_styles: list[tuple[str, float]] = Field(default_factory=list)


class TableBoundaryProposal(BaseModel):
    """Geometry evidence and alternatives for later table-region ownership."""

    table_id: str
    page_num: int = Field(ge=1)
    coordinate_frame: Literal["paper_text_orientation_group"] = (
        "paper_text_orientation_group"
    )
    canonical_table_bbox: tuple[float, float, float, float] | None = None
    canonical_caption_bbox: tuple[float, float, float, float] | None = None
    canonical_stub_band: tuple[float, float] | None = None
    canonical_value_band: tuple[float, float] | None = None
    canonical_row_bounds: list[tuple[float, float]] = Field(default_factory=list)
    boundary_candidates: list[TableBoundaryCandidate] = Field(default_factory=list)
    credible_rule_geometry: bool = False
    coherent_positioned_grid: bool = False
    selected_header_body_rows: tuple[int, int] | None = None
    selected_body_footer_rows: tuple[int, int] | None = None
    review_required: bool = False
    concerns: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
