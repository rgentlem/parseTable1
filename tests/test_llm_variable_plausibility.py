"""Focused tests for TableDefinition variable-plausibility review safety."""

from __future__ import annotations

import json

import pytest

from table1_parser.llm.client import StaticStructuredLLMClient
from table1_parser.llm.variable_plausibility_parser import (
    LLMVariablePlausibilityReviewError,
    LLMVariablePlausibilityTableReviewParser,
)
from table1_parser.llm.variable_plausibility_prompts import build_variable_plausibility_input_payload
from table1_parser.schemas import ColumnDefinition, DefinedLevel, DefinedVariable, TableDefinition


def _build_definition() -> TableDefinition:
    return TableDefinition(
        table_id="tbl-plausibility",
        title="Table 1. Baseline characteristics",
        caption="Baseline characteristics by smoking status",
        variables=[
            DefinedVariable(
                variable_name="Age",
                variable_label="Age, years",
                variable_type="continuous",
                row_start=1,
                row_end=1,
                units_hint="years",
                summary_style_hint="mean_sd",
                confidence=0.9,
            ),
            DefinedVariable(
                variable_name="Sex",
                variable_label="Sex",
                variable_type="categorical",
                row_start=2,
                row_end=4,
                levels=[
                    DefinedLevel(level_name="Male", level_label="Male", row_idx=3),
                    DefinedLevel(level_name="Female", level_label="Female", row_idx=4),
                ],
                summary_style_hint="count_pct",
                confidence=0.92,
            ),
            DefinedVariable(
                variable_name="Current smoker",
                variable_label="Current smoker, n (%)",
                variable_type="binary",
                row_start=5,
                row_end=5,
                summary_style_hint="count_pct",
                confidence=0.95,
            ),
        ],
        column_definition=ColumnDefinition(columns=[]),
        notes=[],
        overall_confidence=0.92,
    )


def _safe_response() -> dict[str, object]:
    return {
        "table_id": "tbl-plausibility",
        "variables": [
            {
                "variable_name": "Age",
                "variable_label": "Age, years",
                "variable_type": "continuous",
                "row_start": 1,
                "row_end": 1,
                "levels": [],
                "units_hint": "years",
                "summary_style_hint": "mean_sd",
                "plausibility_score": 0.99,
            },
            {
                "variable_name": "Sex",
                "variable_label": "Sex",
                "variable_type": "categorical",
                "row_start": 2,
                "row_end": 4,
                "levels": [
                    {"level_name": "Male", "level_label": "Male", "row_idx": 3},
                    {"level_name": "Female", "level_label": "Female", "row_idx": 4},
                ],
                "units_hint": None,
                "summary_style_hint": "count_pct",
                "plausibility_score": 0.97,
            },
            {
                "variable_name": "Current smoker",
                "variable_label": "Current smoker, n (%)",
                "variable_type": "binary",
                "row_start": 5,
                "row_end": 5,
                "levels": [],
                "units_hint": None,
                "summary_style_hint": "count_pct",
                "plausibility_score": 0.9,
                "plausibility_note": "Single-row binary indicator is plausible.",
            },
        ],
        "notes": ["All variables look semantically coherent."],
        "overall_plausibility": 0.953,
    }


def test_variable_plausibility_payload_contains_only_variable_level_evidence() -> None:
    """The plausibility payload should not expose full table definitions."""
    payload = build_variable_plausibility_input_payload(_build_definition())

    dumped = payload.model_dump(mode="json", by_alias=True, exclude_none=True, exclude_defaults=True)
    dumped_json = json.dumps(dumped, sort_keys=True)

    assert payload.table_text == "Baseline characteristics by smoking status"
    assert dumped["vars"][0]["type"] == "continuous"
    assert dumped["vars"][1]["levels"][1]["level_label"] == "Female"
    assert '"column_definition"' not in dumped_json
    assert '"confidence"' not in dumped_json


def test_variable_plausibility_parser_writes_trace_for_safe_response(tmp_path) -> None:
    """The plausibility parser should accept identity-preserving responses and trace them."""
    response = _safe_response()
    client = StaticStructuredLLMClient(response=response)

    result = LLMVariablePlausibilityTableReviewParser(client).review(
        _build_definition(),
        table_index=0,
        table_family="descriptive_characteristics",
        trace_dir=tmp_path,
    )

    llm_output = json.loads((tmp_path / "variable_plausibility_llm_output.json").read_text())
    llm_metrics = json.loads((tmp_path / "variable_plausibility_llm_metrics.json").read_text())
    assert result.table_id == "tbl-plausibility"
    assert result.variables[1].levels[0].level_label == "Male"
    assert llm_output["response"] == response
    assert llm_metrics["status"] == "success"
    assert llm_metrics["prompt_char_count"] > 0
    assert (tmp_path / "variable_plausibility_llm_input.json").exists()
    assert (tmp_path / "variable_plausibility_llm_review.json").exists()


def test_variable_plausibility_parser_rejects_identity_changes() -> None:
    """The plausibility parser should fail if the review rewrites supplied variables."""
    response = _safe_response()
    variables = response["variables"]
    assert isinstance(variables, list)
    assert isinstance(variables[1], dict)
    variables[1]["variable_name"] = "Sex rewritten"
    client = StaticStructuredLLMClient(response=response)

    with pytest.raises(LLMVariablePlausibilityReviewError):
        LLMVariablePlausibilityTableReviewParser(client).review(
            _build_definition(),
            table_index=0,
            table_family="descriptive_characteristics",
        )
