"""Schemas for raw table extraction outputs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class TableCell(BaseModel):
    """A raw grid cell whose bbox is evidence, not its semantic column slot."""

    row_idx: int = Field(ge=0)
    col_idx: int = Field(ge=0)
    text: str
    page_num: int | None = Field(default=None, ge=1)
    bbox: tuple[float, float, float, float] | None = None
    extractor_name: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class PositionedSpanReference(BaseModel):
    """Reference to one span in the shared positioned-document artifact."""

    line_id: str
    span_index: int = Field(ge=0)


class TableCanonicalTransform(BaseModel):
    """Affine transform from page space into one canonical upright table frame."""

    source_coordinate_frame: Literal["page"] = "page"
    target_coordinate_frame: Literal["paper_text_orientation_group"] = (
        "paper_text_orientation_group"
    )
    source_bbox: tuple[float, float, float, float]
    affine_matrix: tuple[float, float, float, float, float, float]
    rotation_direction: Literal["upright", "vertical_text_up", "vertical_text_down"]


class TablePositionedEvidence(BaseModel):
    """Compact table-local source references and canonical physical geometry."""

    source_artifact: Literal["paper_positioned_document.json"] = "paper_positioned_document.json"
    page_num: int = Field(ge=1)
    bbox: tuple[float, float, float, float] | None = None
    candidate_bbox: tuple[float, float, float, float] | None = None
    caption_bbox: tuple[float, float, float, float] | None = None
    structural_scope_bbox: tuple[float, float, float, float] | None = None
    coordinate_frame: Literal["page"] = "page"
    canonical_coordinate_frame: Literal["paper_text_orientation_group"] = (
        "paper_text_orientation_group"
    )
    canonical_bbox: tuple[float, float, float, float] | None = None
    canonical_candidate_bbox: tuple[float, float, float, float] | None = None
    canonical_caption_bbox: tuple[float, float, float, float] | None = None
    canonical_structural_scope_bbox: tuple[float, float, float, float] | None = None
    canonical_grid_bbox: tuple[float, float, float, float] | None = None
    canonical_row_bounds: list[tuple[float, float]] = Field(default_factory=list)
    canonical_physical_column_bounds: list[tuple[float, float]] = Field(
        default_factory=list
    )
    canonical_transform: TableCanonicalTransform | None = None
    geometry_transform_applied: bool = False
    rotation_direction: Literal["vertical_text_up", "vertical_text_down"] | None = None
    orientation_group_id: str | None = None
    line_ids: list[str] = Field(default_factory=list)
    canonical_line_bboxes: list[tuple[float, float, float, float]] = Field(default_factory=list)
    span_references: list[PositionedSpanReference] = Field(default_factory=list)
    canonical_span_bboxes: list[tuple[float, float, float, float]] = Field(default_factory=list)
    word_indices: list[int] = Field(default_factory=list)
    canonical_word_bboxes: list[tuple[float, float, float, float]] = Field(default_factory=list)
    char_indices: list[int] = Field(default_factory=list)
    canonical_char_bboxes: list[tuple[float, float, float, float]] = Field(default_factory=list)
    rule_segment_indices: list[int] = Field(default_factory=list)
    canonical_rule_segments: list[tuple[float, float, float, float]] = Field(default_factory=list)
    stroked_rule_segment_indices: list[int] = Field(default_factory=list)
    canonical_stroked_rule_segments: list[tuple[float, float, float, float]] = Field(
        default_factory=list
    )
    text_filter_artifacts: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)


class TableCaptionRegion(BaseModel):
    """One complete table caption assembled from canonical document blocks."""

    source_artifact: Literal["paper_document.json"] = "paper_document.json"
    mention_id: str
    table_number: str
    mention_kind: Literal["caption_candidate", "continuation_label"]
    continuation_role: Literal[
        "from_previous_page",
        "to_next_page",
        "unspecified",
    ] | None = None
    page_num: int = Field(ge=1)
    label_line_id: str
    line_ids: list[str] = Field(min_length=1)
    text_lines: list[str] = Field(min_length=1)
    text: str
    bbox: tuple[float, float, float, float]
    canonical_bbox: tuple[float, float, float, float]
    orientation: Literal["upright", "vertical_text_up", "vertical_text_down"]
    orientation_group_id: str
    column_index: int = Field(ge=0)


class TableCaptionBinding(BaseModel):
    """Geometry binding between one caption region and one table candidate."""

    placement: Literal["above", "below"]
    distance: float = Field(ge=0.0)
    coordinate_frame: Literal["paper_text_orientation_group"] = (
        "paper_text_orientation_group"
    )
    mention_id: str
    orientation_group_id: str
    caption_bbox: tuple[float, float, float, float]
    caption_canonical_bbox: tuple[float, float, float, float]
    table_canonical_bbox: tuple[float, float, float, float]


class ExtractedTable(BaseModel):
    """Canonical representation of a table immediately after extraction."""

    table_id: str
    source_pdf: str
    page_num: int = Field(ge=1)
    title: str | None = None
    caption: str | None = None
    n_rows: int = Field(ge=0)
    n_cols: int = Field(ge=0)
    cells: list[TableCell] = Field(default_factory=list)
    positioned_evidence: TablePositionedEvidence
    extraction_backend: str
    metadata: dict[str, Any] = Field(default_factory=dict)
