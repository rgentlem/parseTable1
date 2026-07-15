"""Schemas for parser-native column header structure."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ColumnHeaderEvidenceSource = Literal[
    "extracted_cell",
    "metadata_table_cells",
    "normalized_cleaned_row",
    "header_structure_candidate",
]
ColumnHeaderGroupInferenceRule = Literal[
    "repeated_label_span",
    "single_cell_blank_span",
    "single_leaf_group",
    "explicit_cell_span",
]


class ColumnHeaderCellEvidence(BaseModel):
    """One cell-level evidence record supporting a column-header schema."""

    evidence_id: str
    table_id: str
    row_idx: int = Field(ge=0)
    col_idx: int = Field(ge=0)
    original_row_idx: int | None = Field(default=None, ge=0)
    original_col_idx: int | None = Field(default=None, ge=0)
    raw_text: str | None = None
    cleaned_text: str
    bbox: tuple[float, float, float, float] | None = None
    page_num: int | None = Field(default=None, ge=1)
    source: ColumnHeaderEvidenceSource


class ColumnHeaderLeaf(BaseModel):
    """One parser-facing leaf column in a normalized table."""

    leaf_id: str
    table_id: str
    col_idx: int = Field(ge=0)
    original_col_idx: int | None = Field(default=None, ge=0)
    is_row_label_column: bool = False
    is_value_column: bool = True
    leaf_header_row_idx: int | None = Field(default=None, ge=0)
    leaf_label: str
    leaf_name: str
    body_nonempty_row_indices: list[int] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    coordinate_left: float | None = None
    coordinate_center: float | None = None
    coordinate_right: float | None = None


class ColumnHeaderGroup(BaseModel):
    """A higher header label spanning one or more leaf columns."""

    group_id: str
    table_id: str
    row_idx: int = Field(ge=0)
    label: str
    name: str
    col_start: int = Field(ge=0)
    col_end: int = Field(ge=0)
    leaf_col_indices: list[int] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    inference_rule: ColumnHeaderGroupInferenceRule
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class ColumnHeaderRelationship(BaseModel):
    """One inferred attachment between a header group and a leaf column."""

    relationship_id: str
    table_id: str
    parent_group_id: str
    child_leaf_id: str
    leaf_col_idx: int = Field(ge=0)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class ColumnHeaderDescriptor(BaseModel):
    """One canonical parser-facing column descriptor derived from a header schema."""

    leaf_id: str
    col_idx: int = Field(ge=0)
    original_col_idx: int | None = Field(default=None, ge=0)
    column_label: str
    column_name: str
    leaf_label: str
    leaf_name: str
    header_group_ids: list[str] = Field(default_factory=list)
    header_group_labels: list[str] = Field(default_factory=list)
    header_path: list[str] = Field(default_factory=list)
    shared_context_label: str | None = None
    is_row_label_column: bool = False
    is_value_column: bool = True


class ColumnHeaderSchema(BaseModel):
    """Parser-native column header tree represented as flat records."""

    schema_id: str
    table_id: str
    n_cols: int = Field(ge=0)
    label_col_idx: int | None = Field(default=0, ge=0)
    header_rows_considered: list[int] = Field(default_factory=list)
    body_rows_considered: list[int] = Field(default_factory=list)
    leaf_header_row_idx: int | None = Field(default=None, ge=0)
    leaves: list[ColumnHeaderLeaf] = Field(default_factory=list)
    groups: list[ColumnHeaderGroup] = Field(default_factory=list)
    relationships: list[ColumnHeaderRelationship] = Field(default_factory=list)
    evidence: list[ColumnHeaderCellEvidence] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
