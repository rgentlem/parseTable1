"""Schemas for row-focused LLM semantic TableDefinition interpretation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from table1_parser.schemas.table_definition import DefinedVariableType


class _CompactPayloadModel(BaseModel):
    """Base model for compact LLM input payload objects with short serialized keys."""

    model_config = ConfigDict(populate_by_name=True)


class LLMIndexedRowPayload(_CompactPayloadModel):
    """One compact row hint supplied to the semantic LLM."""

    row_idx: int = Field(alias="i", ge=0)
    label: str
    has_trailing_values: bool = Field(default=False, alias="vals")
    numeric_cell_count: int = Field(default=0, alias="num", ge=0)
    indent_level: int = Field(default=0, alias="indent", ge=0)


class LLMIndexedLevelPayload(_CompactPayloadModel):
    """One compact deterministic level row supplied as row-structure evidence."""

    row_idx: int = Field(alias="i", ge=0)
    label: str


class LLMDeterministicVariablePayload(_CompactPayloadModel):
    """One compact deterministic variable span supplied to the semantic LLM."""

    label: str
    variable_type: DefinedVariableType = Field(alias="type")
    row_start: int = Field(alias="r0", ge=0)
    row_end: int = Field(alias="r1", ge=0)
    levels: list[LLMIndexedLevelPayload] = Field(default_factory=list)


class LLMRetrievedPassagePayload(_CompactPayloadModel):
    """One compact retrieved passage supplied to the semantic LLM."""

    passage_id: str = Field(alias="id")
    heading: str | None = Field(default=None, alias="h")
    text: str = Field(alias="t")


class LLMSemanticInputPayload(_CompactPayloadModel):
    """Structured compact payload for row-focused LLM semantic interpretation."""

    table_id: str = Field(alias="id")
    table_text: str | None = Field(default=None, alias="table")
    body_rows: list[LLMIndexedRowPayload] = Field(default_factory=list, alias="rows")
    deterministic_variables: list[LLMDeterministicVariablePayload] = Field(default_factory=list, alias="vars")
    retrieved_passages: list[LLMRetrievedPassagePayload] = Field(default_factory=list, alias="passages")


class LLMSemanticLevelInterpretation(BaseModel):
    """LLM semantic interpretation of one categorical level row."""

    level_name: str
    level_label: str
    row_idx: int = Field(ge=0)
    evidence_passage_ids: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    disagrees_with_deterministic: bool = False


class LLMSemanticVariableInterpretation(BaseModel):
    """LLM semantic interpretation of one row variable."""

    variable_name: str
    variable_label: str
    variable_type: DefinedVariableType = "unknown"
    row_start: int = Field(ge=0)
    row_end: int = Field(ge=0)
    levels: list[LLMSemanticLevelInterpretation] = Field(default_factory=list)
    evidence_passage_ids: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    disagrees_with_deterministic: bool = False


class LLMSemanticTableDefinition(BaseModel):
    """Row-focused LLM semantic interpretation linked to deterministic table structure."""

    table_id: str
    variables: list[LLMSemanticVariableInterpretation] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    overall_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
