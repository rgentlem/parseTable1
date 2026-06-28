"""Schemas for paper-level footnote anchors, definitions, and links."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


FootnoteSourceScope = Literal[
    "table_cell",
    "table_caption",
    "table_note",
    "figure_caption",
    "page_note",
    "body_text",
]
FootnoteGlyphKind = Literal["letter", "number", "symbol", "asterisk", "unknown"]
FootnoteLinkStatus = Literal["resolved", "ambiguous", "unresolved"]


class FootnoteAnchor(BaseModel):
    """One visual glyph anchor attached to a paper, table, or visual source."""

    anchor_id: str
    glyph_raw: str
    glyph_key: str
    glyph_kind: FootnoteGlyphKind
    glyph_codepoints: list[str]
    source_scope: FootnoteSourceScope
    source_id: str
    page_num: int = Field(ge=1)
    confidence: float = Field(ge=0.0, le=1.0)
    table_id: str | None = None
    visual_id: str | None = None
    row_idx: int | None = Field(default=None, ge=0)
    col_idx: int | None = Field(default=None, ge=0)
    source_role: str | None = None
    text_context: str | None = None
    attached_to_text: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    coordinate_frame: str | None = None
    source_artifact: str | None = None
    notes: list[str] = Field(default_factory=list)


class FootnoteDefinition(BaseModel):
    """One candidate footnote definition extracted from paper text."""

    definition_id: str
    glyph_raw: str
    glyph_key: str
    glyph_kind: FootnoteGlyphKind
    glyph_codepoints: list[str]
    source_scope: FootnoteSourceScope
    source_id: str
    page_num: int = Field(ge=1)
    raw_text: str
    clean_text: str
    confidence: float = Field(ge=0.0, le=1.0)
    definition_text: str | None = None
    table_id: str | None = None
    visual_id: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    line_index: int | None = Field(default=None, ge=0)
    source_artifact: str | None = None
    notes: list[str] = Field(default_factory=list)


class FootnoteDefinitionCandidateLine(BaseModel):
    """One positioned or contextual text line that may contain footnote definitions."""

    line_id: str
    page_num: int = Field(ge=1)
    raw_text: str
    source_scope: FootnoteSourceScope = "body_text"
    source_id: str | None = None
    table_id: str | None = None
    visual_id: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    page_height: float | None = Field(default=None, gt=0.0)
    line_index: int | None = Field(default=None, ge=0)
    source_artifact: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


class FootnoteLink(BaseModel):
    """One anchor-to-definition link decision."""

    link_id: str
    anchor_id: str
    glyph_key: str
    link_status: FootnoteLinkStatus
    candidate_definition_ids: list[str]
    link_basis: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    definition_id: str | None = None
    scope_distance: str | None = None
    notes: list[str] = Field(default_factory=list)


class PaperFootnotes(BaseModel):
    """Paper-level footnote artifact."""

    paper_id: str
    source_pdf: str
    anchors: list[FootnoteAnchor] = Field(default_factory=list)
    definitions: list[FootnoteDefinition] = Field(default_factory=list)
    links: list[FootnoteLink] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
