"""Schemas for explicit continuation column-compatibility diagnostics."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


HeaderSignatureStatus = Literal["match", "mismatch", "missing_base", "missing_continuation", "missing_both"]
ContinuationColumnOverallStatus = Literal["compatible", "possibly_compatible", "incompatible", "no_parent"]


class TableContinuationColumnCheck(BaseModel):
    """Schema-based column compatibility check for one continuation fragment."""

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
    overall_status: ContinuationColumnOverallStatus
    confidence: float = Field(ge=0.0, le=1.0)
    diagnostics: list[str] = Field(default_factory=list)
