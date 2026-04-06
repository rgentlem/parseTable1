"""Tests for provider-backed LLM client wiring."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from urllib import error as urllib_error
import json

import pytest

from table1_parser.config import Settings
from table1_parser.llm.client import LLMConfigurationError, LLMProviderError, build_llm_client
from table1_parser.llm.semantic_schemas import LLMSemanticTableDefinition


class _FakeResponsesAPI:
    def __init__(self, response: object) -> None:
        self._response = response
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self._response


class _FakeOpenAI:
    def __init__(self, *, api_key: str, timeout: float, max_retries: int) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.responses = _FakeResponsesAPI(
            SimpleNamespace(
                output_parsed=LLMSemanticTableDefinition(
                    table_id="tbl-llm",
                    variables=[],
                    notes=["from fake openai"],
                )
            )
        )


class _FakeHTTPResponse:
    def __init__(self, payload: str) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload.encode("utf-8")

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeURLOpener:
    def __init__(self, payload: str | None = None, exc: Exception | None = None) -> None:
        self.payload = payload
        self.exc = exc
        self.calls: list[object] = []

    def open(self, request: object, timeout: float | None = None) -> _FakeHTTPResponse:
        self.calls.append({"request": request, "timeout": timeout})
        if self.exc is not None:
            raise self.exc
        if self.payload is None:
            raise AssertionError("Fake opener requires either payload or exc.")
        return _FakeHTTPResponse(self.payload)


def test_settings_reads_llm_environment_variables(monkeypatch) -> None:
    """Settings should read the documented LLM environment variables directly."""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.1")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("LLM_MAX_RETRIES", "4")
    monkeypatch.setenv("LLM_DEBUG", "true")
    monkeypatch.setenv("LLM_SDK_DEBUG", "true")

    settings = Settings()

    assert settings.llm_provider == "openai"
    assert settings.openai_api_key == "test-key"
    assert settings.openai_model == "gpt-4.1-mini"
    assert settings.llm_model == "gpt-4.1-mini"
    assert settings.llm_temperature == 0.1
    assert settings.llm_timeout_seconds == 30
    assert settings.llm_max_retries == 4
    assert settings.llm_debug is True
    assert settings.llm_sdk_debug is True


def test_settings_reads_qwen_environment_variables(monkeypatch) -> None:
    """Settings should read the documented Qwen environment variables directly."""
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dash-key")
    monkeypatch.setenv("QWEN_MODEL", "qwen-plus")
    monkeypatch.setenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/api/v1")

    settings = Settings()

    assert settings.llm_provider == "qwen"
    assert settings.qwen_api_key == "dash-key"
    assert settings.qwen_model == "qwen-plus"
    assert settings.llm_model == "qwen-plus"
    assert settings.qwen_base_url == "https://dashscope.aliyuncs.com/api/v1"


def test_build_llm_client_requires_openai_configuration(monkeypatch) -> None:
    """Missing required OpenAI settings should fail with a clear configuration error."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    settings = Settings(llm_provider="openai", openai_model="gpt-4.1-mini")

    with pytest.raises(LLMConfigurationError) as exc_info:
        build_llm_client(settings=settings)

    assert "OPENAI_API_KEY" in str(exc_info.value)


def test_build_llm_client_requires_qwen_configuration(monkeypatch) -> None:
    """Missing required Qwen settings should fail with a clear configuration error."""
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    settings = Settings(llm_provider="qwen", qwen_model="qwen-plus")

    with pytest.raises(LLMConfigurationError) as exc_info:
        build_llm_client(settings=settings)

    assert "DASHSCOPE_API_KEY" in str(exc_info.value)


def test_build_llm_client_returns_openai_client_with_fake_sdk(monkeypatch) -> None:
    """The provider builder should construct an OpenAI-backed client from configured settings."""
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_FakeOpenAI))
    settings = Settings(
        llm_provider="openai",
        openai_api_key="test-key",
        openai_model="gpt-4.1-mini",
        llm_temperature=0.2,
        llm_timeout_seconds=15,
        llm_max_retries=3,
    )

    client = build_llm_client(settings=settings)
    response = client.structured_completion(
        "prompt text",
        LLMSemanticTableDefinition.model_json_schema(),
        response_model=LLMSemanticTableDefinition,
    )

    assert response["table_id"] == "tbl-llm"
    assert response["notes"] == ["from fake openai"]
    assert client._client.api_key == "test-key"  # type: ignore[attr-defined]
    assert client._client.timeout == 15  # type: ignore[attr-defined]
    assert client._client.max_retries == 3  # type: ignore[attr-defined]
    assert client._client.responses.calls[0]["model"] == "gpt-4.1-mini"  # type: ignore[attr-defined]
    assert client.sdk_debug is False
    assert client.embeds_output_schema_in_prompt is False


def test_build_llm_client_returns_qwen_client_and_parses_json_response() -> None:
    """The provider builder should construct a Qwen client and parse JSON text output."""
    client = build_llm_client(
        settings=Settings(
            llm_provider="qwen",
            qwen_api_key="dash-key",
            qwen_model="qwen-plus",
            qwen_base_url="https://dashscope.aliyuncs.com/api/v1",
            llm_temperature=0.2,
            llm_timeout_seconds=15,
            llm_max_retries=3,
        )
    )
    fake_opener = _FakeURLOpener(
        payload=json.dumps(
            {
                "output": {
                    "choices": [
                        {
                            "message": {
                                "content": [
                                    {
                                        "text": (
                                            "```json\n"
                                            '{"table_id":"tbl-llm","variables":[],'
                                            '"notes":["from fake qwen"]}'
                                            "\n```"
                                        )
                                    }
                                ]
                            }
                        }
                    ]
                }
            }
        )
    )
    client._opener = fake_opener  # type: ignore[attr-defined]

    response = client.structured_completion(
        "prompt text\n\nOutput schema:\n{...}",
        LLMSemanticTableDefinition.model_json_schema(),
        response_model=LLMSemanticTableDefinition,
    )

    request = fake_opener.calls[0]["request"]
    body = request.data.decode("utf-8")  # type: ignore[attr-defined]
    assert response["table_id"] == "tbl-llm"
    assert response["notes"] == ["from fake qwen"]
    assert fake_opener.calls[0]["timeout"] == 15
    assert '"model": "qwen-plus"' in body
    assert "Output contract:" in body
    assert "Output schema:" not in body
    assert client.embeds_output_schema_in_prompt is True


def test_build_llm_client_separates_sdk_debug_from_artifact_debug(monkeypatch) -> None:
    """SDK logging should only activate from LLM_SDK_DEBUG, not from LLM_DEBUG."""
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_FakeOpenAI))
    monkeypatch.delenv("OPENAI_LOG", raising=False)
    client = build_llm_client(
        settings=Settings(
            llm_provider="openai",
            openai_api_key="test-key",
            openai_model="gpt-4.1-mini",
            llm_debug=True,
            llm_sdk_debug=False,
        )
    )

    assert client.sdk_debug is False
    assert "OPENAI_LOG" not in os.environ

    build_llm_client(
        settings=Settings(
            llm_provider="openai",
            openai_api_key="test-key",
            openai_model="gpt-4.1-mini",
            llm_debug=False,
            llm_sdk_debug=True,
        )
    )

    assert os.environ["OPENAI_LOG"] == "debug"


def test_openai_client_raises_provider_error_when_no_parsed_payload(monkeypatch) -> None:
    """A provider response without structured parsed content should fail clearly."""
    broken_openai = SimpleNamespace(
        OpenAI=lambda **kwargs: SimpleNamespace(
            responses=_FakeResponsesAPI(SimpleNamespace(output_parsed=None, output_text="not json"))
        )
    )
    monkeypatch.setitem(sys.modules, "openai", broken_openai)
    client = build_llm_client(
        settings=Settings(
            llm_provider="openai",
            openai_api_key="test-key",
            openai_model="gpt-4.1-mini",
        )
    )

    with pytest.raises(LLMProviderError):
        client.structured_completion(
            "prompt text",
            LLMSemanticTableDefinition.model_json_schema(),
            response_model=LLMSemanticTableDefinition,
        )


def test_qwen_client_raises_provider_error_for_invalid_json_response() -> None:
    """Malformed Qwen text output should fail clearly before model validation."""
    client = build_llm_client(
        settings=Settings(
            llm_provider="qwen",
            qwen_api_key="dash-key",
            qwen_model="qwen-plus",
        )
    )
    client._opener = _FakeURLOpener(  # type: ignore[attr-defined]
        payload='{"output":{"choices":[{"message":{"content":[{"text":"not json"}]}}]}}'
    )

    with pytest.raises(LLMProviderError):
        client.structured_completion(
            "prompt text",
            LLMSemanticTableDefinition.model_json_schema(),
            response_model=LLMSemanticTableDefinition,
        )


def test_qwen_client_raises_provider_error_for_http_failures() -> None:
    """HTTP-layer Qwen failures should be wrapped as provider errors."""
    client = build_llm_client(
        settings=Settings(
            llm_provider="qwen",
            qwen_api_key="dash-key",
            qwen_model="qwen-plus",
        )
    )
    client._opener = _FakeURLOpener(  # type: ignore[attr-defined]
        exc=urllib_error.URLError("network down")
    )

    with pytest.raises(LLMProviderError) as exc_info:
        client.structured_completion(
            "prompt text",
            LLMSemanticTableDefinition.model_json_schema(),
            response_model=LLMSemanticTableDefinition,
        )

    assert "network down" in str(exc_info.value)
