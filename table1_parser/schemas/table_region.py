"""Schemas for table row-region ownership."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


TableRegionRowRole = Literal["caption", "preamble", "column_header", "body", "footer_note", "unknown"]


class TableRegionRow(BaseModel):
    """One extracted grid row assigned to a table-region role."""

    row_idx: int = Field(ge=0)
    role: TableRegionRowRole
    text: str = ""
    detection_basis: str


class TableRegion(BaseModel):
    """Geometry-derived row ownership for one extracted table."""

    region_id: str
    table_id: str
    source_pdf: str
    page_num: int = Field(ge=1)
    n_rows: int = Field(ge=0)
    n_cols: int = Field(ge=0)
    caption_rows: list[int] = Field(default_factory=list)
    preamble_rows: list[int] = Field(default_factory=list)
    column_header_rows: list[int] = Field(default_factory=list)
    body_rows: list[int] = Field(default_factory=list)
    footer_note_rows: list[int] = Field(default_factory=list)
    footer_line_ids: list[str] = Field(default_factory=list)
    row_regions: list[TableRegionRow] = Field(default_factory=list)
    horizontal_rules: list[float] = Field(default_factory=list)
    full_width_horizontal_rules: list[float] = Field(default_factory=list)
    start_rule_y: float | None = None
    header_body_rule_y: float | None = None
    body_footer_rule_y: float | None = None
    detection_basis: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    diagnostics: list[str] = Field(default_factory=list)
