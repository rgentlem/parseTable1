"""Schemas for paper-level markdown context and per-table retrieval artifacts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


SectionRoleHint = Literal[
    "abstract_like",
    "methods_like",
    "results_like",
    "discussion_like",
    "conclusion_like",
    "references_like",
    "other",
]
PassageMatchType = Literal["table_reference", "methods_term_match", "results_term_match"]


class PaperSection(BaseModel):
    """One block-derived section of the source paper."""

    section_id: str
    order: int = Field(ge=0)
    heading: str | None = None
    level: int = Field(default=0, ge=0, le=6)
    role_hint: SectionRoleHint = "other"
    content: str = ""
    heading_block_id: str | None = None
    body_block_ids: list[str] = Field(default_factory=list)


class RetrievedPassage(BaseModel):
    """One retrieved passage supporting table-level semantic interpretation."""

    passage_id: str
    section_id: str | None = None
    heading: str | None = None
    text: str
    match_type: PassageMatchType
    score: float | None = Field(default=None, ge=0.0)


class TableContext(BaseModel):
    """One per-table retrieval bundle derived from paper markdown."""

    table_id: str
    table_index: int = Field(ge=0)
    table_label: str | None = None
    title: str | None = None
    caption: str | None = None
    row_terms: list[str] = Field(default_factory=list)
    column_terms: list[str] = Field(default_factory=list)
    grouping_terms: list[str] = Field(default_factory=list)
    methods_like_section_ids: list[str] = Field(default_factory=list)
    results_like_section_ids: list[str] = Field(default_factory=list)
    passages: list[RetrievedPassage] = Field(default_factory=list)
    reference_ids: list[str] = Field(default_factory=list)
    resolved_visual_ids: list[str] = Field(default_factory=list)
