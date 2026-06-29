"""Schemas for parsed Table 1 outputs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from table1_parser.schemas.parsed_cell_value import ValueComponent


VariableType = Literal["continuous", "categorical", "binary", "unknown"]
ColumnRole = Literal["group", "overall", "p_value", "statistic", "unknown"]


class ParsedLevel(BaseModel):
    """A categorical level attached to a parsed variable."""

    label: str
    row_idx: int = Field(ge=0)


class ParsedVariable(BaseModel):
    """A parsed variable spanning one or more rows in the table body."""

    variable_name: str
    variable_label: str
    variable_type: VariableType = "unknown"
    row_start: int = Field(ge=0)
    row_end: int = Field(ge=0)
    levels: list[ParsedLevel] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class ParsedColumn(BaseModel):
    """A parsed semantic interpretation of a table column."""

    col_idx: int = Field(ge=0)
    column_name: str
    column_label: str
    header_leaf_id: str | None = None
    header_leaf_label: str | None = None
    header_group_ids: list[str] = Field(default_factory=list)
    header_group_labels: list[str] = Field(default_factory=list)
    header_path: list[str] = Field(default_factory=list)
    inferred_role: ColumnRole = "unknown"
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class ValueRecord(BaseModel):
    """A semantic value record joined to row/column meaning and source components."""

    source_table_index: int | None = Field(default=None, ge=0)
    source_table_id: str | None = None
    row_idx: int = Field(ge=0)
    col_idx: int = Field(ge=0)
    variable_name: str
    variable_label: str | None = None
    level_label: str | None = None
    column_name: str
    column_label: str | None = None
    header_leaf_id: str | None = None
    header_leaf_label: str | None = None
    header_group_ids: list[str] = Field(default_factory=list)
    header_group_labels: list[str] = Field(default_factory=list)
    header_path: list[str] = Field(default_factory=list)
    raw_value: str
    parse_pattern: str | None = None
    components: list[ValueComponent] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


class ParsedTable(BaseModel):
    """Final parsed representation of a Table 1-style table."""

    table_id: str
    title: str | None = None
    caption: str | None = None
    variables: list[ParsedVariable] = Field(default_factory=list)
    columns: list[ParsedColumn] = Field(default_factory=list)
    values: list[ValueRecord] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    overall_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
