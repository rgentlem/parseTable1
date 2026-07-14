"""Schemas for visual text annotations attached to extracted table cells."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from table1_parser.schemas.extracted_table import PositionedSpanReference


CellTextAnnotationType = Literal["superscript", "subscript", "inline_marker", "unknown_marker"]


class CellTextAnnotation(BaseModel):
    """One visual text marker detected inside or near an extracted table cell."""

    annotation_id: str | None = None
    row_idx: int = Field(ge=0)
    col_idx: int = Field(ge=0)
    text: str
    glyph_key: str | None = None
    annotation_type: CellTextAnnotationType
    text_latex: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    attached_to_text: str | None = None
    source_cell_id: str | None = None
    source_char_indices: list[int] = Field(default_factory=list)
    source_span_references: list[PositionedSpanReference] = Field(default_factory=list)
    font_names: list[str] = Field(default_factory=list)
    font_sizes: list[float] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CellTextAnnotationTable(BaseModel):
    """Sparse annotation sidecar for one extracted table."""

    table_id: str
    page_num: int | None = Field(default=None, ge=1)
    n_rows: int = Field(ge=0)
    n_cols: int = Field(ge=0)
    annotations: list[CellTextAnnotation] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
