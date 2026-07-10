"""Schemas for source-grid parsed cell value components."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from table1_parser.schemas.body_element_candidate import BodyElementSourceCell


ValueComponentKind = Literal[
    "count",
    "percent",
    "mean",
    "sd",
    "median",
    "q1",
    "q3",
    "min",
    "max",
    "estimate",
    "se",
    "p_value",
    "missing",
    "text",
    "unknown",
]
ValueRelation = Literal["=", "<", "<=", ">", ">="]


class ValueComponent(BaseModel):
    """One typed component parsed from a printed source cell value."""

    kind: ValueComponentKind
    value: float | str | None = None
    raw_fragment: str | None = None
    relation: ValueRelation | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


class ParsedCellValue(BaseModel):
    """Parsed value components keyed only by source table and grid indices."""

    source_table_index: int = Field(ge=0)
    source_table_id: str
    row_idx: int = Field(ge=0)
    col_idx: int = Field(ge=0)
    raw_value: str
    element_candidate_id: str | None = None
    raw_fragments: list[str] = Field(default_factory=list)
    source_cells: list[BodyElementSourceCell] = Field(default_factory=list)
    parse_pattern: str | None = None
    components: list[ValueComponent] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)
