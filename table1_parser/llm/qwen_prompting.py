"""Qwen-specific prompt compaction helpers."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel


def json_only_prompt(prompt: str) -> str:
    """Add explicit instructions so text-only providers return one JSON object only."""
    return (
        f"{prompt}\n\n"
        "Return only one valid JSON object.\n"
        "Do not include markdown fences.\n"
        "Do not include any explanation before or after the JSON.\n"
    )


def compact_qwen_prompt(prompt: str, response_model: type[BaseModel] | None) -> str:
    """Replace verbose schema dumps with a compact output contract for Qwen."""
    prompt_without_schema, marker, _schema_block = prompt.partition("\n\nOutput schema:\n")
    compact_prompt = prompt_without_schema if marker else prompt
    if response_model is not None:
        compact_prompt += "\n\nOutput contract:\n"
        compact_prompt += _compact_contract_for_model(response_model)
        if response_model.__name__ == "LLMSemanticTableDefinition":
            compact_prompt += (
                "\n\nSemantic constraints:\n"
                '- Preserve every row_idx exactly as supplied.\n'
                '- Use only evidence_passage_ids that appear in passages.\n'
                '- If there is no supporting passage, use an empty evidence_passage_ids list.\n'
                '- Keep variable_name, variable_label, level_name, and level_label as strings.\n'
                '- Do not use alternate field names such as label, kind, rows, row_indices, or passages.\n'
            )
    return json_only_prompt(compact_prompt)


def _compact_contract_for_model(model: type[BaseModel]) -> str:
    """Return a compact, readable output contract derived from a Pydantic model."""
    if model.__name__ == "LLMSemanticTableDefinition":
        return (
            '{ "table_id": "string", '
            '"variables": [ { '
            '"variable_name": "string", '
            '"variable_label": "string", '
            '"variable_type": "continuous" | "categorical" | "binary" | "unknown", '
            '"row_start": integer, '
            '"row_end": integer, '
            '"levels": [ { '
            '"level_name": "string", '
            '"level_label": "string", '
            '"row_idx": integer, '
            '"evidence_passage_ids": [ "string" ], '
            '"confidence": number | null, '
            '"disagrees_with_deterministic": true | false } ], '
            '"evidence_passage_ids": [ "string" ], '
            '"confidence": number | null, '
            '"disagrees_with_deterministic": true | false } ], '
            '"notes": [ "string" ], '
            '"overall_confidence": number | null }'
        )

    schema = model.model_json_schema()
    defs = schema.get("$defs", {})
    contract = _schema_shape_to_text(schema, defs=defs, depth=0, seen=set())
    return contract if contract else '{"table_id":"string"}'


def _schema_shape_to_text(
    schema: dict[str, Any],
    *,
    defs: dict[str, Any],
    depth: int,
    seen: set[str],
) -> str:
    """Convert a JSON schema node into a concise pseudo-JSON contract."""
    if depth > 2:
        return "{...}"

    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        ref_name = ref.split("/")[-1]
        if ref_name in seen:
            return "{...}"
        target = defs.get(ref_name)
        if isinstance(target, dict):
            return _schema_shape_to_text(target, defs=defs, depth=depth + 1, seen={*seen, ref_name})
        return "{...}"

    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        return " | ".join(json.dumps(value) for value in enum_values[:6])

    any_of = schema.get("anyOf")
    if isinstance(any_of, list) and any_of:
        parts = [
            _schema_shape_to_text(item, defs=defs, depth=depth + 1, seen=seen)
            for item in any_of[:4]
            if isinstance(item, dict)
        ]
        return " | ".join(part for part in parts if part)

    schema_type = schema.get("type")
    if schema_type == "object" or isinstance(schema.get("properties"), dict):
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            return "{...}"
        required = set(schema.get("required", [])) if isinstance(schema.get("required"), list) else set()
        parts: list[str] = []
        for key in list(properties.keys())[:8]:
            value_schema = properties.get(key)
            if not isinstance(value_schema, dict):
                continue
            rendered = _schema_shape_to_text(value_schema, defs=defs, depth=depth + 1, seen=seen)
            suffix = "" if key in required else "?"
            parts.append(f'"{key}{suffix}": {rendered}')
        return "{ " + ", ".join(parts) + " }" if parts else "{...}"

    if schema_type == "array":
        items = schema.get("items")
        if isinstance(items, dict):
            return "[ " + _schema_shape_to_text(items, defs=defs, depth=depth + 1, seen=seen) + " ]"
        return "[ ... ]"

    if schema_type == "string":
        return '"string"'
    if schema_type == "integer":
        return "integer"
    if schema_type == "number":
        return "number"
    if schema_type == "boolean":
        return "true | false"
    if schema_type == "null":
        return "null"

    return '"value"'
