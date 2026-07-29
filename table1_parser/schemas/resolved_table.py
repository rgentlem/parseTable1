"""Schemas for the resolved semantic table working set."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from table1_parser.schemas.normalized_table import NormalizedTable


ResolvedTableType = Literal["singleton", "integrated_continuation"]
ResolvedRowSourceRole = Literal["singleton", "base_fragment", "continuation_fragment", "rejected_continuation"]
ResolutionDecisionType = Literal["singleton", "integrated_continuation", "rejected_continuation"]
ResolutionDecisionStatus = Literal["accepted", "rejected", "not_applicable"]
SourceTableResolutionRole = Literal["singleton", "base_fragment", "continuation_fragment", "rejected_continuation"]
ColumnSchemaCompatibilityStatus = Literal["match", "rejected", "schema_missing"]


class DroppedSourceRow(BaseModel):
    """A source row omitted from an integrated resolved table."""

    source_table_id: str
    source_table_index: int = Field(ge=0)
    source_row_idx: int = Field(ge=0)
    source_page_num: int | None = Field(default=None, ge=1)
    reason: str


class ResolvedRowProvenance(BaseModel):
    """Source mapping for one retained row in a resolved table."""

    resolved_row_idx: int = Field(ge=0)
    source_table_id: str
    source_table_index: int = Field(ge=0)
    source_row_idx: int = Field(ge=0)
    source_page_num: int | None = Field(default=None, ge=1)
    source_role: ResolvedRowSourceRole


class IntegrationBoundary(BaseModel):
    """Boundary between source fragments inside one resolved table."""

    boundary_id: str
    previous_source_table_id: str
    next_source_table_id: str
    before_resolved_row_idx: int | None = Field(default=None, ge=0)
    after_resolved_row_idx: int | None = Field(default=None, ge=0)
    dropped_rows: list[DroppedSourceRow] = Field(default_factory=list)
    decision_id: str | None = None
    notes: list[str] = Field(default_factory=list)


class ColumnSchemaCompatibilityDecision(BaseModel):
    """Column-schema compatibility decision for a continuation candidate."""

    decision_id: str
    base_table_id: str
    continuation_table_id: str
    status: ColumnSchemaCompatibilityStatus
    base_column_headers: list[str] = Field(default_factory=list)
    continuation_column_headers: list[str] = Field(default_factory=list)
    normalized_column_count_match: bool | None = None
    decision_reason: str
    warnings: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class TableResolutionDecision(BaseModel):
    """Decision record explaining how source fragments entered the working set."""

    decision_id: str
    decision_type: ResolutionDecisionType
    status: ResolutionDecisionStatus
    base_table_id: str | None = None
    continuation_table_id: str | None = None
    resolved_table_id: str | None = None
    source_table_ids: list[str] = Field(default_factory=list)
    identity_evidence: list[str] = Field(default_factory=list)
    reason: str
    diagnostics: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class SourceTableResolution(BaseModel):
    """Index entry for one normalized source table."""

    source_table_id: str
    source_table_index: int = Field(ge=0)
    source_page_num: int | None = Field(default=None, ge=1)
    role: SourceTableResolutionRole
    resolved_table_id: str | None = None
    consumed_by: str | None = None
    decision_id: str | None = None
    notes: list[str] = Field(default_factory=list)


class ResolvedTable(BaseModel):
    """One table in the semantic working set."""

    table_id: str
    resolution_type: ResolvedTableType
    logical_table_number: str | None = None
    title: str | None = None
    caption: str | None = None
    table: NormalizedTable
    source_table_ids: list[str] = Field(default_factory=list)
    row_provenance: list[ResolvedRowProvenance] = Field(default_factory=list)
    integration_boundaries: list[IntegrationBoundary] = Field(default_factory=list)
    column_schema_decisions: list[ColumnSchemaCompatibilityDecision] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


class ResolvedTableSet(BaseModel):
    """Canonical working table set after continuation resolution."""

    source_artifact: str = "normalized_tables.json"
    working_artifact: str = "resolved_tables.json"
    resolved_tables: list[ResolvedTable] = Field(default_factory=list)
    decisions: list[TableResolutionDecision] = Field(default_factory=list)
    source_tables: list[SourceTableResolution] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
