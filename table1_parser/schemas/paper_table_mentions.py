"""Schemas for paper-level table mention evidence."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


TableMentionKind = Literal["caption_candidate", "prose_reference", "continuation_label"]


class PaperTableMention(BaseModel):
    """One mention of an in-paper table observed in the layout-aware text stream."""

    mention_id: str
    table_number: str
    table_label: str
    mention_kind: TableMentionKind
    page_num: int = Field(ge=1)
    line_ids: list[str] = Field(default_factory=list)
    source_line_id: str
    source_line_bbox: tuple[float, float, float, float]
    source_line_text: str
    context_text: str
    matched_text: str
    cue: str | None = None
    is_caption_candidate: bool = False
    source_line_role: str = "body"
    source_line_notes: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    source_artifact: str = "paper_text_stream.json"
    notes: list[str] = Field(default_factory=list)
