"""Application configuration for the Table 1 parser."""

from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict, Field, model_validator

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ModuleNotFoundError:
    class SettingsConfigDict(dict):
        """Fallback settings config when pydantic-settings is unavailable."""

    class BaseSettings(BaseModel):
        """Minimal BaseSettings-compatible fallback for local development."""

        model_config = ConfigDict(extra="ignore")

        def __init__(self, **data: object) -> None:
            merged_data = self._load_environment_defaults()
            merged_data.update(data)
            super().__init__(**merged_data)

        @classmethod
        def _load_environment_defaults(cls) -> dict[str, object]:
            prefix = ""
            config = getattr(cls, "model_config", None)
            if isinstance(config, dict):
                prefix = str(config.get("env_prefix", ""))

            values: dict[str, object] = {}
            for field_name, field in cls.model_fields.items():
                candidate_names: list[str] = []
                validation_alias = getattr(field, "validation_alias", None)
                if isinstance(validation_alias, str):
                    candidate_names.append(validation_alias)
                elif validation_alias is not None:
                    candidate_names.extend(
                        str(choice)
                        for choice in getattr(validation_alias, "choices", [])
                        if isinstance(choice, str)
                    )
                alias = getattr(field, "alias", None)
                if isinstance(alias, str):
                    candidate_names.append(alias)
                candidate_names.append(f"{prefix}{field_name}".upper())
                for env_name in candidate_names:
                    if env_name in os.environ:
                        values[field_name] = os.environ[env_name]
                        break
            return values


class Settings(BaseSettings):
    """Runtime configuration for the Table 1 parser."""

    default_extraction_backend: str = Field(default="pymupdf")
    llm_provider: str = Field(default="openai", validation_alias="LLM_PROVIDER")
    llm_model: str | None = Field(default=None, validation_alias="LLM_MODEL")
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY", repr=False)
    openai_model: str | None = Field(default=None, validation_alias="OPENAI_MODEL")
    qwen_api_key: str | None = Field(default=None, validation_alias="DASHSCOPE_API_KEY", repr=False)
    qwen_model: str | None = Field(default=None, validation_alias="QWEN_MODEL")
    qwen_base_url: str | None = Field(default=None, validation_alias="QWEN_BASE_URL")
    llm_temperature: float = Field(default=0.0, validation_alias="LLM_TEMPERATURE")
    llm_timeout_seconds: float = Field(default=60.0, validation_alias="LLM_TIMEOUT_SECONDS", gt=0.0)
    llm_max_retries: int = Field(default=2, validation_alias="LLM_MAX_RETRIES", ge=0)
    llm_debug: bool = Field(default=False, validation_alias="LLM_DEBUG")
    llm_sdk_debug: bool = Field(default=False, validation_alias="LLM_SDK_DEBUG")
    max_table_candidates: int = Field(default=10, ge=1)
    heuristic_confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)

    model_config = SettingsConfigDict(
        env_prefix="TABLE1_PARSER_",
        extra="ignore",
        populate_by_name=True,
    )

    @model_validator(mode="after")
    def _sync_provider_defaults(self) -> "Settings":
        """Backfill generic provider settings from the active provider-specific values."""
        provider = self.llm_provider.strip().lower()
        if self.llm_model is None:
            self.llm_model = self.active_llm_model
        if provider == "openai" and self.openai_model is None and self.llm_model is not None:
            self.openai_model = self.llm_model
        if provider == "qwen" and self.qwen_model is None and self.llm_model is not None:
            self.qwen_model = self.llm_model
        return self

    @property
    def active_llm_model(self) -> str | None:
        """Return the active provider's configured model, falling back to the generic model."""
        provider = self.llm_provider.strip().lower()
        if provider == "qwen":
            return self.qwen_model or self.llm_model
        return self.openai_model or self.llm_model
