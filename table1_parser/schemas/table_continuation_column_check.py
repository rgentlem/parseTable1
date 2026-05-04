"""Schemas for explicit continuation column-compatibility diagnostics."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ColumnCoordinateEvidenceQuality = Literal["strong", "partial", "missing"]
ColumnCoordinateStatus = Literal["compatible", "possibly_compatible", "incompatible", "missing", "partial"]
HeaderSignatureStatus = Literal["match", "mismatch", "missing_base", "missing_continuation", "missing_both"]
ContinuationColumnOverallStatus = Literal["compatible", "possibly_compatible", "incompatible", "no_parent"]


class ColumnCoordinateProfile(BaseModel):
    """Normalized coordinate profile for one table's columns."""

    table_id: str
    normalized_n_cols: int = Field(ge=0)
    coordinate_n_cols: int = Field(ge=0)
    coordinate_source: Literal["extracted_cells", "metadata_table_cells", "none"]
    evidence_quality: ColumnCoordinateEvidenceQuality
    table_left: float | None = None
    table_right: float | None = None
    normalized_lefts: list[float | None] = Field(default_factory=list)
    normalized_centers: list[float | None] = Field(default_factory=list)
    normalized_rights: list[float | None] = Field(default_factory=list)
    normalized_widths: list[float | None] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ColumnCoordinateMapEntry(BaseModel):
    """Coordinate comparison for one aligned column position."""

    base_col_idx: int
    continuation_col_idx: int
    base_center: float | None = None
    continuation_center: float | None = None
    center_delta: float | None = None
    base_width: float | None = None
    continuation_width: float | None = None
    width_delta: float | None = None
    status: Literal["matched", "possibly_matched", "mismatched", "missing_evidence"]


class TableContinuationColumnCheck(BaseModel):
    """Column compatibility check for one explicit table continuation fragment."""

    check_id: str
    table_number: int
    base_table_index: int | None = None
    continuation_table_index: int = Field(ge=0)
    base_table_id: str | None = None
    continuation_table_id: str
    base_page_num: int | None = Field(default=None, ge=1)
    continuation_page_num: int | None = Field(default=None, ge=1)
    base_n_cols: int | None = Field(default=None, ge=0)
    continuation_n_cols: int = Field(ge=0)
    base_table_family: str | None = None
    continuation_table_family: str | None = None
    base_table_category: str | None = None
    continuation_table_category: str | None = None
    normalized_column_count_match: bool | None = None
    header_signature_status: HeaderSignatureStatus
    base_column_signature: list[str] = Field(default_factory=list)
    continuation_column_signature: list[str] = Field(default_factory=list)
    coordinate_status: ColumnCoordinateStatus
    overall_status: ContinuationColumnOverallStatus
    confidence: float = Field(ge=0.0, le=1.0)
    column_map: list[ColumnCoordinateMapEntry] = Field(default_factory=list)
    base_coordinate_profile: ColumnCoordinateProfile | None = None
    continuation_coordinate_profile: ColumnCoordinateProfile
    diagnostics: list[str] = Field(default_factory=list)
