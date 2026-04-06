"""Provider-agnostic LLM client abstractions."""

from __future__ import annotations

import json
import os
import re
import socket
from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from pydantic import BaseModel

from table1_parser.config import Settings
from table1_parser.llm.qwen_prompting import compact_qwen_prompt


class LLMConfigurationError(RuntimeError):
    """Raised when provider-backed LLM configuration is missing or invalid."""


class LLMProviderError(RuntimeError):
    """Raised when the configured LLM provider call fails."""


class LLMClient(ABC):
    """Abstract client for schema-constrained structured completions."""

    @property
    def embeds_output_schema_in_prompt(self) -> bool:
        """Return whether prompts should include the explicit output schema text."""
        return True

    @abstractmethod
    def structured_completion(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        response_model: type[BaseModel] | None = None,
    ) -> dict[str, Any]:
        """Return a structured JSON-like response that matches the requested schema."""


class StaticStructuredLLMClient(LLMClient):
    """Small test double that returns a preconfigured structured response."""

    def __init__(self, response: dict[str, Any]) -> None:
        self._response = deepcopy(response)
        self.calls: list[dict[str, Any]] = []

    def structured_completion(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        response_model: type[BaseModel] | None = None,
    ) -> dict[str, Any]:
        """Record the call and return the configured response."""
        self.calls.append({"prompt": prompt, "schema": schema, "response_model": response_model})
        return deepcopy(self._response)


class OpenAIClient(LLMClient):
    """OpenAI-backed structured-output client using environment-based configuration."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        temperature: float = 0.0,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        sdk_debug: bool = False,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.sdk_debug = sdk_debug
        if self.sdk_debug:
            os.environ.setdefault("OPENAI_LOG", "debug")

        try:
            from openai import OpenAI
        except ModuleNotFoundError as exc:
            raise LLMConfigurationError(
                "OpenAI SDK is not installed. Install the 'openai' package to enable LLM integration."
            ) from exc

        self._client = OpenAI(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )

    @property
    def embeds_output_schema_in_prompt(self) -> bool:
        """OpenAI uses native structured parsing, so prompt-level schema text is redundant."""
        return False

    def structured_completion(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        response_model: type[BaseModel] | None = None,
    ) -> dict[str, Any]:
        """Request a structured completion and return a JSON-like dict."""
        if response_model is None:
            raise LLMConfigurationError("OpenAIClient requires a Pydantic response_model for structured parsing.")
        try:
            response = self._client.responses.parse(
                model=self.model,
                input=prompt,
                temperature=self.temperature,
                text_format=response_model,
            )
        except Exception as exc:
            raise LLMProviderError(f"OpenAI structured completion failed: {exc}") from exc

        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            for output_item in getattr(response, "output", []) or []:
                for content_item in getattr(output_item, "content", []) or []:
                    parsed = getattr(content_item, "parsed", None)
                    if parsed is not None:
                        break
                if parsed is not None:
                    break
        if parsed is None:
            output_text = getattr(response, "output_text", None)
            if isinstance(output_text, str) and output_text.strip():
                try:
                    loaded = json.loads(output_text)
                except json.JSONDecodeError:
                    loaded = None
                if isinstance(loaded, dict):
                    parsed = loaded
        if parsed is None:
            raise LLMProviderError("OpenAI response did not contain a parsed structured payload.")
        if isinstance(parsed, BaseModel):
            return parsed.model_dump(mode="json")
        if isinstance(parsed, dict):
            return parsed
        raise LLMProviderError("OpenAI parsed structured payload had an unsupported type.")


class QwenClient(LLMClient):
    """Qwen-backed client that requests text JSON and validates it locally."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str | None = None,
        temperature: float = 0.0,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url or "https://dashscope.aliyuncs.com/api/v1"
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._endpoint = self.base_url.rstrip("/") + "/services/aigc/text-generation/generation"
        self._opener = urllib_request.build_opener(urllib_request.ProxyHandler({}))

    def structured_completion(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        response_model: type[BaseModel] | None = None,
    ) -> dict[str, Any]:
        """Request a text completion from Qwen and parse a JSON object from the response."""
        del schema
        strict_prompt = compact_qwen_prompt(prompt, response_model)
        request = urllib_request.Request(
            self._endpoint,
            data=json.dumps(
                {
                    "model": self.model,
                    "input": {"prompt": strict_prompt},
                    "parameters": {"temperature": self.temperature},
                }
            ).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                raw_payload = response.read().decode("utf-8")
        except urllib_error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise LLMProviderError(f"Qwen structured completion failed: HTTP {exc.code}: {error_body}") from exc
        except urllib_error.URLError as exc:
            raise LLMProviderError(f"Qwen structured completion failed: {exc}") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise LLMProviderError("Qwen structured completion failed: request timed out.") from exc

        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError as exc:
            raise LLMProviderError("Qwen structured completion failed: invalid JSON response.") from exc

        content = _extract_qwen_message_text(payload)
        if not content:
            raise LLMProviderError(f"Qwen response did not contain text output: {payload!r}")
        try:
            return _parse_json_object_from_text(content)
        except ValueError as exc:
            raise LLMProviderError(f"Qwen response was not valid JSON: {exc}") from exc


def _extract_qwen_message_text(response: Any) -> str:
    """Extract text from a DashScope-style response payload."""
    if response is None:
        return ""

    output = getattr(response, "output", None)
    if output is None and isinstance(response, dict):
        output = response.get("output")
    if output is None:
        return ""

    output_text = getattr(output, "text", None)
    if output_text is None and isinstance(output, dict):
        output_text = output.get("text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    choices = getattr(output, "choices", None)
    if choices is None and isinstance(output, dict):
        choices = output.get("choices")
    if not choices:
        return ""

    first_choice = choices[0]
    message = getattr(first_choice, "message", None)
    if message is None and isinstance(first_choice, dict):
        message = first_choice.get("message")
    if message is None:
        return ""

    content = getattr(message, "content", None)
    if content is None and isinstance(message, dict):
        content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text.strip())
        return "\n".join(texts).strip()
    return ""


def _parse_json_object_from_text(text: str) -> dict[str, Any]:
    """Parse a JSON object from raw model text, tolerating markdown fences."""
    candidate = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(.*?)```", candidate, flags=re.DOTALL | re.IGNORECASE)
    if fence_match is not None:
        candidate = fence_match.group(1).strip()

    try:
        loaded = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("no JSON object found in model response") from None
        loaded = json.loads(candidate[start : end + 1])
    if not isinstance(loaded, dict):
        raise ValueError("model response JSON was not an object")
    return loaded


def build_llm_client(settings: Settings | None = None) -> LLMClient:
    """Create a configured provider-backed LLM client from environment-driven settings."""
    settings = settings or Settings()
    provider = settings.llm_provider.lower().strip()
    if provider == "openai":
        api_key = settings.openai_api_key
        model = settings.openai_model or settings.llm_model
        if not api_key:
            raise LLMConfigurationError("OPENAI_API_KEY is required when LLM_PROVIDER=openai.")
        if not model:
            raise LLMConfigurationError("OPENAI_MODEL is required when LLM_PROVIDER=openai.")
        return OpenAIClient(
            api_key=api_key,
            model=model,
            temperature=settings.llm_temperature,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
            sdk_debug=settings.llm_sdk_debug,
        )

    if provider == "qwen":
        api_key = settings.qwen_api_key
        model = settings.qwen_model or settings.llm_model
        if not api_key:
            raise LLMConfigurationError("DASHSCOPE_API_KEY is required when LLM_PROVIDER=qwen.")
        if not model:
            raise LLMConfigurationError("QWEN_MODEL is required when LLM_PROVIDER=qwen.")
        return QwenClient(
            api_key=api_key,
            model=model,
            base_url=settings.qwen_base_url,
            temperature=settings.llm_temperature,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )

    raise LLMConfigurationError(f"Unsupported LLM provider: {settings.llm_provider}")
