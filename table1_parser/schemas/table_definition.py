"""Schemas for value-free semantic table definitions."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


DefinedVariableType = Literal["continuous", "categorical", "binary", "unknown"]
DefinedColumnRole = Literal["overall", "group", "comparison_group", "p_value", "smd", "unknown"]


class DefinedLevel(BaseModel):
    """One categorical level attached to a defined variable."""

    level_name: str
    level_label: str
    row_idx: int = Field(ge=0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class DefinedVariable(BaseModel):
    """A value-free semantic definition of one row variable."""

    variable_name: str
    variable_label: str
    variable_type: DefinedVariableType = "unknown"
    row_start: int = Field(ge=0)
    row_end: int = Field(ge=0)
    levels: list[DefinedLevel] = Field(default_factory=list)
    units_hint: str | None = None
    summary_style_hint: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class DefinedColumn(BaseModel):
    """A value-free semantic definition of one table column."""

    col_idx: int = Field(ge=0)
    column_name: str
    column_label: str
    inferred_role: DefinedColumnRole = "unknown"
    grouping_variable_hint: str | None = None
    group_level_label: str | None = None
    group_level_name: str | None = None
    group_order: int | None = Field(default=None, ge=1)
    statistic_subtype: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class ColumnDefinition(BaseModel):
    """Overall semantic definition of the table columns."""

    grouping_label: str | None = None
    grouping_name: str | None = None
    group_count: int | None = Field(default=None, ge=0)
    columns: list[DefinedColumn] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class TableDefinition(BaseModel):
    """A value-free semantic definition of a table."""

    table_id: str
    title: str | None = None
    caption: str | None = None
    variables: list[DefinedVariable] = Field(default_factory=list)
    column_definition: ColumnDefinition
    metadata: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    overall_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
