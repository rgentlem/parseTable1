"""Row-focused LLM semantic interpreter for TableDefinition artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from pydantic import ValidationError

from table1_parser.llm.client import LLMClient, LLMProviderError
from table1_parser.llm.semantic_prompts import build_llm_semantic_input_payload, build_llm_semantic_prompt
from table1_parser.llm.semantic_schemas import LLMSemanticInputPayload, LLMSemanticTableDefinition
from table1_parser.schemas import (
    LLMSemanticCallRecord,
    NormalizedTable,
    TableContext,
    TableDefinition,
)
from table1_parser.validation import validate_llm_semantic_table_definition


class LLMSemanticInterpretationError(Exception):
    """Structured failure for invalid or unsafe LLM semantic interpretations."""

    def __init__(
        self,
        message: str,
        *,
        payload: LLMSemanticInputPayload | None = None,
        raw_response: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.payload = payload
        self.raw_response = raw_response


@dataclass(slots=True)
class LLMSemanticParseAttempt:
    """One semantic-LLM attempt together with monitoring metadata."""

    result: LLMSemanticTableDefinition | None
    monitoring: LLMSemanticCallRecord
    error: Exception | None = None


class LLMSemanticTableDefinitionParser:
    """Call an LLM for row-focused semantic interpretation and validate the result."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def parse(
        self,
        table: NormalizedTable,
        deterministic_table_definition: TableDefinition,
        retrieved_context: TableContext,
        *,
        trace_dir: str | Path | None = None,
    ) -> LLMSemanticTableDefinition:
        """Produce a validated row-focused LLM semantic interpretation for one normalized table."""
        attempt = self.parse_with_monitoring(
            table,
            deterministic_table_definition,
            retrieved_context,
            trace_dir=trace_dir,
        )
        if attempt.error is not None:
            raise attempt.error
        if attempt.result is None:
            raise LLMSemanticInterpretationError("Semantic LLM attempt did not return a result.")
        return attempt.result

    def parse_with_monitoring(
        self,
        table: NormalizedTable,
        deterministic_table_definition: TableDefinition,
        retrieved_context: TableContext,
        *,
        trace_dir: str | Path | None = None,
    ) -> LLMSemanticParseAttempt:
        """Produce a row-focused semantic interpretation together with timing and payload metrics."""
        payload = build_llm_semantic_input_payload(table, deterministic_table_definition, retrieved_context)
        schema = LLMSemanticTableDefinition.model_json_schema()
        prompt = build_llm_semantic_prompt(
            payload,
            schema if self.client.embeds_output_schema_in_prompt else {},
        )
        started_at = _utc_timestamp()
        started_perf = perf_counter()
        base_monitoring = LLMSemanticCallRecord(
            table_id=table.table_id,
            table_index=retrieved_context.table_index,
            should_run_llm_semantics=True,
            status="success",
            trace_dir=str(trace_dir) if trace_dir is not None else None,
            header_row_count=len(table.header_rows),
            body_row_count=len(table.body_rows),
            header_cell_count=table.n_cols * len(table.header_rows),
            body_cell_count=sum(len(row_view.raw_cells) for row_view in table.row_views),
            deterministic_variable_count=len(deterministic_table_definition.variables),
            deterministic_column_count=len(deterministic_table_definition.column_definition.columns),
            retrieved_passage_count=len(retrieved_context.passages),
            retrieved_context_char_count=sum(len(passage.text) for passage in retrieved_context.passages),
            prompt_char_count=len(prompt),
            prompt_line_count=prompt.count("\n") + 1 if prompt else 0,
        )
        try:
            raw_response = self.client.structured_completion(
                prompt,
                schema,
                response_model=LLMSemanticTableDefinition,
            )
        except LLMProviderError as exc:
            monitoring = _finalize_monitoring(
                base_monitoring,
                status="provider_error",
                started_at=started_at,
                started_perf=started_perf,
                error_message=str(exc),
            )
            if trace_dir is not None:
                _write_trace_artifacts(
                    trace_dir=trace_dir,
                    deterministic_table_definition=deterministic_table_definition,
                    payload=payload,
                    raw_response=None,
                    result=None,
                    monitoring=monitoring,
                )
            return LLMSemanticParseAttempt(result=None, monitoring=monitoring, error=exc)
        try:
            result = LLMSemanticTableDefinition.model_validate(raw_response)
            validated = validate_llm_semantic_table_definition(result, table, retrieved_context)
        except (ValidationError, ValueError) as exc:
            error = LLMSemanticInterpretationError(
                f"Invalid structured LLM semantic interpretation: {exc}",
                payload=payload,
                raw_response=raw_response,
            )
            monitoring = _finalize_monitoring(
                base_monitoring,
                status="validation_error",
                started_at=started_at,
                started_perf=started_perf,
                raw_response=raw_response,
                error_message=str(error),
            )
            if trace_dir is not None:
                _write_trace_artifacts(
                    trace_dir=trace_dir,
                    deterministic_table_definition=deterministic_table_definition,
                    payload=payload,
                    raw_response=raw_response,
                    result=None,
                    monitoring=monitoring,
                )
            return LLMSemanticParseAttempt(result=None, monitoring=monitoring, error=error)
        monitoring = _finalize_monitoring(
            base_monitoring,
            status="success",
            started_at=started_at,
            started_perf=started_perf,
            raw_response=raw_response,
            result=validated,
        )
        if trace_dir is not None:
            _write_trace_artifacts(
                trace_dir=trace_dir,
                deterministic_table_definition=deterministic_table_definition,
                payload=payload,
                raw_response=raw_response,
                result=validated,
                monitoring=monitoring,
            )
        return LLMSemanticParseAttempt(result=validated, monitoring=monitoring, error=None)


def _utc_timestamp() -> str:
    """Return a compact UTC ISO 8601 timestamp with trailing Z."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write a small JSON artifact with stable formatting."""
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_trace_artifacts(
    *,
    trace_dir: str | Path,
    deterministic_table_definition: TableDefinition,
    payload: LLMSemanticInputPayload,
    raw_response: dict[str, Any] | None,
    result: LLMSemanticTableDefinition | None,
    monitoring: LLMSemanticCallRecord,
) -> None:
    """Write compact trace artifacts for one row-focused semantic LLM interpretation."""
    trace_path = Path(trace_dir)
    trace_path.mkdir(parents=True, exist_ok=True)
    _write_json(
        trace_path / "table_definition_llm_input.json",
        {
            "report_timestamp": monitoring.completed_at or monitoring.started_at or _utc_timestamp(),
            "table_id": deterministic_table_definition.table_id,
            "payload": payload.model_dump(mode="json", exclude_none=True),
        },
    )
    _write_json(
        trace_path / "table_definition_llm_metrics.json",
        monitoring.model_dump(mode="json", exclude_none=True),
    )
    if raw_response is not None:
        _write_json(
            trace_path / "table_definition_llm_output.json",
            {
                "report_timestamp": monitoring.completed_at or monitoring.started_at or _utc_timestamp(),
                "table_id": deterministic_table_definition.table_id,
                "response": raw_response,
            },
        )
    if result is not None:
        _write_json(
            trace_path / "table_definition_llm_interpretation.json",
            {
                "report_timestamp": monitoring.completed_at or monitoring.started_at or _utc_timestamp(),
                "table_id": deterministic_table_definition.table_id,
                "interpretation": result.model_dump(mode="json", exclude_none=True),
            },
        )


def _finalize_monitoring(
    monitoring: LLMSemanticCallRecord,
    *,
    status: str,
    started_at: str,
    started_perf: float,
    raw_response: dict[str, Any] | None = None,
    result: LLMSemanticTableDefinition | None = None,
    error_message: str | None = None,
) -> LLMSemanticCallRecord:
    """Finish one monitoring record with elapsed time and output metrics."""
    return monitoring.model_copy(
        update={
            "status": status,
            "started_at": started_at,
            "completed_at": _utc_timestamp(),
            "elapsed_seconds": round(perf_counter() - started_perf, 4),
            "response_char_count": (
                len(json.dumps(raw_response, sort_keys=True)) if raw_response is not None else None
            ),
            "output_variable_count": len(result.variables) if result is not None else None,
            "output_column_count": None,
            "error_message": error_message,
        }
    )
