"""LLM runner for TableDefinition variable-plausibility review."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from pydantic import ValidationError

from table1_parser.llm.client import LLMClient, LLMProviderError
from table1_parser.llm.variable_plausibility_prompts import (
    build_variable_plausibility_input_payload,
    build_variable_plausibility_prompt,
)
from table1_parser.llm.variable_plausibility_schemas import (
    LLMVariablePlausibilityInputPayload,
    LLMVariablePlausibilityTableReview,
)
from table1_parser.schemas import LLMVariablePlausibilityCallRecord, TableDefinition
from table1_parser.validation.llm_variable_plausibility import validate_llm_variable_plausibility_review


class LLMVariablePlausibilityReviewError(Exception):
    """Structured failure for invalid or unsafe variable-plausibility reviews."""

    def __init__(
        self,
        message: str,
        *,
        payload: LLMVariablePlausibilityInputPayload | None = None,
        raw_response: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.payload = payload
        self.raw_response = raw_response


@dataclass(slots=True)
class LLMVariablePlausibilityReviewAttempt:
    """One variable-plausibility review attempt with monitoring metadata."""

    result: LLMVariablePlausibilityTableReview | None
    monitoring: LLMVariablePlausibilityCallRecord
    error: Exception | None = None


class LLMVariablePlausibilityTableReviewParser:
    """Call an LLM for variable-plausibility review and validate the result."""

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def review(
        self,
        deterministic_table_definition: TableDefinition,
        *,
        table_index: int,
        table_family: str | None = None,
        trace_dir: str | Path | None = None,
    ) -> LLMVariablePlausibilityTableReview:
        """Produce a validated variable-plausibility review for one deterministic table definition."""
        attempt = self.review_with_monitoring(
            deterministic_table_definition,
            table_index=table_index,
            table_family=table_family,
            trace_dir=trace_dir,
        )
        if attempt.error is not None:
            raise attempt.error
        if attempt.result is None:
            raise LLMVariablePlausibilityReviewError("Variable-plausibility review attempt did not return a result.")
        return attempt.result

    def review_with_monitoring(
        self,
        deterministic_table_definition: TableDefinition,
        *,
        table_index: int,
        table_family: str | None = None,
        trace_dir: str | Path | None = None,
    ) -> LLMVariablePlausibilityReviewAttempt:
        """Produce one variable-plausibility review together with timing and payload metrics."""
        payload = build_variable_plausibility_input_payload(deterministic_table_definition)
        schema = LLMVariablePlausibilityTableReview.model_json_schema()
        prompt = build_variable_plausibility_prompt(
            payload,
            schema if self.client.embeds_output_schema_in_prompt else {},
        )
        started_at = _utc_timestamp()
        started_perf = perf_counter()
        variable_counts = _variable_type_counts(deterministic_table_definition)
        base_monitoring = LLMVariablePlausibilityCallRecord(
            table_id=deterministic_table_definition.table_id,
            table_index=table_index,
            table_family=table_family,
            eligible_for_review=True,
            status="success",
            trace_dir=str(trace_dir) if trace_dir is not None else None,
            deterministic_variable_count=len(deterministic_table_definition.variables),
            continuous_variable_count=variable_counts["continuous"],
            categorical_variable_count=variable_counts["categorical"],
            binary_variable_count=variable_counts["binary"],
            attached_level_count=sum(len(variable.levels) for variable in deterministic_table_definition.variables),
            prompt_char_count=len(prompt),
            prompt_line_count=prompt.count("\n") + 1 if prompt else 0,
        )
        try:
            raw_response = self.client.structured_completion(
                prompt,
                schema,
                response_model=LLMVariablePlausibilityTableReview,
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
            return LLMVariablePlausibilityReviewAttempt(result=None, monitoring=monitoring, error=exc)
        try:
            result = LLMVariablePlausibilityTableReview.model_validate(raw_response)
            validated = validate_llm_variable_plausibility_review(result, payload)
        except (ValidationError, ValueError):
            error = LLMVariablePlausibilityReviewError(
                "Invalid structured LLM variable-plausibility review.",
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
            return LLMVariablePlausibilityReviewAttempt(result=None, monitoring=monitoring, error=error)
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
        return LLMVariablePlausibilityReviewAttempt(result=validated, monitoring=monitoring, error=None)


def _variable_type_counts(definition: TableDefinition) -> dict[str, int]:
    """Count the main deterministic variable types for monitoring."""
    counts = {"continuous": 0, "categorical": 0, "binary": 0}
    for variable in definition.variables:
        if variable.variable_type in counts:
            counts[variable.variable_type] += 1
    return counts


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
    payload: LLMVariablePlausibilityInputPayload,
    raw_response: dict[str, Any] | None,
    result: LLMVariablePlausibilityTableReview | None,
    monitoring: LLMVariablePlausibilityCallRecord,
) -> None:
    """Write compact trace artifacts for one variable-plausibility review."""
    trace_path = Path(trace_dir)
    trace_path.mkdir(parents=True, exist_ok=True)
    _write_json(
        trace_path / "variable_plausibility_llm_input.json",
        {
            "report_timestamp": monitoring.completed_at or monitoring.started_at or _utc_timestamp(),
            "table_id": deterministic_table_definition.table_id,
            "payload": payload.model_dump(mode="json", exclude_none=True),
        },
    )
    _write_json(
        trace_path / "variable_plausibility_llm_metrics.json",
        monitoring.model_dump(mode="json", exclude_none=True),
    )
    if raw_response is not None:
        _write_json(
            trace_path / "variable_plausibility_llm_output.json",
            {
                "report_timestamp": monitoring.completed_at or monitoring.started_at or _utc_timestamp(),
                "table_id": deterministic_table_definition.table_id,
                "response": raw_response,
            },
        )
    if result is not None:
        _write_json(
            trace_path / "variable_plausibility_llm_review.json",
            {
                "report_timestamp": monitoring.completed_at or monitoring.started_at or _utc_timestamp(),
                "table_id": deterministic_table_definition.table_id,
                "review": result.model_dump(mode="json", exclude_none=True),
            },
        )


def _finalize_monitoring(
    monitoring: LLMVariablePlausibilityCallRecord,
    *,
    status: str,
    started_at: str,
    started_perf: float,
    raw_response: dict[str, Any] | None = None,
    result: LLMVariablePlausibilityTableReview | None = None,
    error_message: str | None = None,
) -> LLMVariablePlausibilityCallRecord:
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
            "error_message": error_message,
        }
    )
