"""Schemas for table-level rescue and failure tracking."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ProcessingStage = Literal["extraction", "normalization", "table_definition", "parsed_table"]
ProcessingStatusValue = Literal["ok", "rescued", "failed"]


class TableProcessingAttempt(BaseModel):
    """One rescue, repair, or primary-path attempt recorded for a table."""

    stage: ProcessingStage
    name: str
    considered: bool = False
    ran: bool = False
    succeeded: bool = False
    note: str | None = None


class SourceFragmentDiagnostic(BaseModel):
    """Diagnostic carried from one normalized source fragment into resolved-table status."""

    source_table_id: str
    source_table_index: int | None = Field(default=None, ge=0)
    source_role: str | None = None
    stage: str
    code: str
    severity: str | None = None
    row_idx: int | None = Field(default=None, ge=0)
    col_idx: int | None = Field(default=None, ge=0)


class TableProcessingStatus(BaseModel):
    """Per-table parse status with rescue attempts and terminal failure details."""

    table_id: str
    source_table_ids: list[str] = Field(default_factory=list)
    status: ProcessingStatusValue = "ok"
    failure_stage: ProcessingStage | None = None
    failure_reason: str | None = None
    attempts: list[TableProcessingAttempt] = Field(default_factory=list)
    source_fragment_diagnostics: list[SourceFragmentDiagnostic] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
