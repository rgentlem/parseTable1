"""Schemas for paper-level bibliography entries and reference mentions."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


BibliographyMentionSourceScope = Literal["table_cell", "body_text", "table_caption"]
BibliographyMentionLinkStatus = Literal["resolved", "unresolved", "ambiguous"]


class BibliographyEntry(BaseModel):
    """One parsed entry from a paper bibliography or reference list."""

    entry_id: str
    label_raw: str
    label_key: str
    reference_number: int | None = Field(default=None, ge=1)
    raw_text: str
    clean_text: str
    source_section_id: str | None = None
    heading: str | None = None
    role_hint: str | None = None
    source_artifact: str = "paper_sections.json"
    source_line_ids: list[str] = Field(default_factory=list)
    page_nums: list[int] = Field(default_factory=list)
    bbox: tuple[float, float, float, float] | None = None
    visual_line_count: int = Field(default=0, ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


class BibliographyReferenceMention(BaseModel):
    """One bibliography reference marker observed in a table or paper text source."""

    mention_id: str
    label_raw: str
    label_key: str
    source_scope: BibliographyMentionSourceScope
    source_id: str
    source_artifact: str
    page_num: int | None = Field(default=None, ge=1)
    table_id: str | None = None
    row_idx: int | None = Field(default=None, ge=0)
    col_idx: int | None = Field(default=None, ge=0)
    source_role: str | None = None
    attached_to_text: str | None = None
    text_context: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    link_status: BibliographyMentionLinkStatus = "unresolved"
    entry_id: str | None = None
    candidate_entry_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


class PaperBibliography(BaseModel):
    """Paper-level bibliography and reference-marker link artifact."""

    paper_id: str
    source_pdf: str
    entries: list[BibliographyEntry] = Field(default_factory=list)
    reference_mentions: list[BibliographyReferenceMention] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
