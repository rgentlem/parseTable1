"""Schemas for paper-level table and figure visual references."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from table1_parser.schemas.document_context import SectionRoleHint


VisualKind = Literal["table", "figure"]
VisualCaptionSource = Literal["extracted_table", "markdown_caption", "pdf_caption", "figure_image", "unknown"]
VisualReferenceResolutionStatus = Literal["resolved", "unresolved", "external_or_bibliographic", "ambiguous"]
VisualReferenceCheckStatus = Literal["referenced_in_text", "no_text_reference", "supplementary_exempt", "not_checked"]


class PaperVisual(BaseModel):
    """One table or figure that appears to exist in the paper."""

    visual_id: str
    visual_kind: VisualKind
    label: str
    number: str
    caption: str | None = None
    caption_source: VisualCaptionSource = "unknown"
    doi: str | None = None
    doi_source_line_id: str | None = None
    page_num: int | None = Field(default=None, ge=1)
    artifact_path: str | None = None
    source_table_id: str | None = None
    source: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    text_reference_ids: list[str] = Field(default_factory=list)
    reference_check_status: VisualReferenceCheckStatus = "not_checked"
    reference_check_notes: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class PaperVisualReference(BaseModel):
    """One prose reference to a table or figure in the paper text."""

    reference_id: str
    reference_kind: VisualKind
    reference_label: str
    reference_number: str
    matched_text: str
    section_id: str | None = None
    heading: str | None = None
    role_hint: SectionRoleHint = "other"
    paragraph_index: int = Field(ge=0)
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=0)
    anchor_text: str
    resolved_visual_id: str | None = None
    resolution_status: VisualReferenceResolutionStatus = "unresolved"
    resolution_notes: list[str] = Field(default_factory=list)
