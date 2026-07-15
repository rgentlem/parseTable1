"""Schemas for preliminary geometry-aligned header structure."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from table1_parser.schemas.table_boundary_proposal import TableBoundaryRuleReference


class HeaderTextEvidence(BaseModel):
    """One positioned header text run retained as source evidence."""

    evidence_id: str
    text: str
    header_row_indices: list[int] = Field(default_factory=list)
    source_line_ids: list[str] = Field(default_factory=list)
    source_word_indices: list[int] = Field(default_factory=list)
    canonical_bbox: tuple[float, float, float, float]


class HeaderLeafCandidate(BaseModel):
    """One preliminary leaf defined by a body-occupancy band."""

    leaf_id: str
    leaf_index: int = Field(ge=0)
    label: str
    raw_text: str = ""
    base_text: str = ""
    canonical_x_bounds: tuple[float, float]
    evidence_ids: list[str] = Field(default_factory=list)
    occupancy_band_ids: list[str] = Field(default_factory=list)
    occupancy_alignment: Literal["one_to_one"]
    marker_ids: list[str] = Field(default_factory=list)
    label_source: Literal["local_positioned_text", "inherited_continuation"] = (
        "local_positioned_text"
    )
    local_label: str | None = None
    inherited_from_table_id: str | None = None
    inherited_from_leaf_id: str | None = None
    inherited_from_page_num: int | None = Field(default=None, ge=1)
    inheritance_evidence: list[str] = Field(default_factory=list)


class HeaderGroupCandidate(BaseModel):
    """One preliminary multicolumn group over contiguous header leaves."""

    group_id: str
    label: str
    raw_text: str = ""
    base_text: str = ""
    canonical_x_bounds: tuple[float, float]
    leaf_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    rule_references: list[TableBoundaryRuleReference] = Field(default_factory=list)
    marker_ids: list[str] = Field(default_factory=list)


class HeaderStructureRelationship(BaseModel):
    """One explicit candidate group-to-leaf relationship."""

    relationship_id: str
    parent_group_id: str
    child_leaf_id: str


class HeaderMarkerAttachmentCandidate(BaseModel):
    """Candidate header nodes for one positioned marker occurrence."""

    attachment_id: str
    marker_id: str
    source_evidence_ids: list[str] = Field(default_factory=list)
    candidate_node_ids: list[str] = Field(default_factory=list)
    selected_node_id: str | None = None
    status: Literal["linked", "ambiguous", "unresolved"]


class HeaderStructureCandidate(BaseModel):
    """Preliminary LaTeX-like header aligned with body occupancy bands."""

    candidate_id: str
    table_id: str
    page_num: int = Field(ge=1)
    coordinate_frame: Literal["paper_text_orientation_group"] = (
        "paper_text_orientation_group"
    )
    source_artifacts: list[str] = Field(default_factory=list)
    header_row_indices: list[int] = Field(default_factory=list)
    body_row_indices: list[int] = Field(default_factory=list)
    occupancy_band_ids: list[str] = Field(default_factory=list)
    leaf_candidates: list[HeaderLeafCandidate] = Field(default_factory=list)
    group_candidates: list[HeaderGroupCandidate] = Field(default_factory=list)
    relationships: list[HeaderStructureRelationship] = Field(default_factory=list)
    marker_attachment_candidates: list[HeaderMarkerAttachmentCandidate] = Field(
        default_factory=list
    )
    evidence: list[HeaderTextEvidence] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
