"""Schemas for artifact-only Table 1 continuation merge inspection."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Table1ContinuationDecision = Literal["merge", "skip"]


class Table1ContinuationMember(BaseModel):
    """One source table participating in a Table 1 continuation decision."""

    table_index: int = Field(ge=0)
    table_id: str
    role: Literal["base", "continuation"]
    title: str | None = None
    caption: str | None = None
    n_rows: int = Field(ge=0)
    n_cols: int = Field(ge=0)
    header_rows: list[int] = Field(default_factory=list)
    body_rows: list[int] = Field(default_factory=list)


class Table1ContinuationGroup(BaseModel):
    """Decision record for one potential Table 1 continuation group."""

    group_id: str
    table_number: str = "1"
    source_table_indices: list[int] = Field(default_factory=list)
    source_table_ids: list[str] = Field(default_factory=list)
    merge_decision: Table1ContinuationDecision
    decision_reason: str
    confidence: float = Field(ge=0.0, le=1.0)
    column_headers_match: bool
    column_headers: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
    members: list[Table1ContinuationMember] = Field(default_factory=list)
