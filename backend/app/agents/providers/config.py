"""Single environment-owned configuration and provider composition boundary."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import os
import time
from typing import Any
from urllib.parse import urlsplit

from .base import (
    LLMProvider,
    ProviderError,
    ProviderErrorCategory,
    StructuredOutputMode,
)


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    provider: str
    base_url: str = ""
    model: str = ""
    api_key: str = field(default="", repr=False)
    timeout_seconds: float = 30.0
    max_output_tokens: int = 1200
    structured_output_mode: StructuredOutputMode = StructuredOutputMode.JSON_SCHEMA
    validation_error: str | None = field(default=None, repr=False)

    @property
    def configured(self) -> bool:
        return self.validation_error is None

    @property
    def credential_configured(self) -> bool:
        return bool(self.api_key)


def _number(
    environ: Mapping[str, str], name: str, default: str, minimum: float, maximum: float
) -> tuple[float, str | None]:
    try:
        value = float(environ.get(name, default))
    except (TypeError, ValueError):
        return float(default), f"{name} is invalid"
    if not minimum <= value <= maximum:
        return value, f"{name} is outside the allowed range"
    return value, None


def _integer(
    environ: Mapping[str, str], name: str, default: str, minimum: int, maximum: int
) -> tuple[int, str | None]:
    raw = environ.get(name, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return int(default), f"{name} is invalid"
    if str(value) != str(raw).strip() or not minimum <= value <= maximum:
        return value, f"{name} is outside the allowed range"
    return value, None


def _validated_base_url(value: str) -> tuple[str, str | None]:
    if not value:
        return "", "Base URL is required"
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
    except ValueError:
        return "", "Base URL is invalid"
    if not hostname or parsed.username is not None or parsed.password is not None:
        return "", "Base URL is invalid"
    if parsed.query or parsed.fragment:
        return "", "Base URL is invalid"
    if parsed.scheme == "https":
        return value.rstrip("/"), None
    if parsed.scheme == "http" and hostname.lower() in {"localhost", "127.0.0.1", "::1"}:
        return value.rstrip("/"), None
    return "", "Base URL must use HTTPS except on loopback"


def load_provider_config(environ: Mapping[str, str] | None = None) -> ProviderConfig:
    values = os.environ if environ is None else environ
    provider = values.get("AGENTFORGE_LLM_PROVIDER", "mock").strip().lower()
    if provider not in {"mock", "openai-compatible"}:
        raise ProviderError(
            ProviderErrorCategory.NOT_CONFIGURED,
            safe_message="Unknown LLM provider configuration",
        )
    timeout, timeout_error = _number(
        values, "AGENTFORGE_LLM_TIMEOUT_SECONDS", "30", 1, 120
    )
    tokens, token_error = _integer(
        values, "AGENTFORGE_LLM_MAX_OUTPUT_TOKENS", "1200", 1, 4096
    )
    raw_mode = values.get("AGENTFORGE_LLM_STRUCTURED_OUTPUT_MODE", "json_schema").strip().lower()
    try:
        structured_output_mode = StructuredOutputMode(raw_mode or "json_schema")
        mode_error = None
    except ValueError:
        structured_output_mode = StructuredOutputMode.JSON_SCHEMA
        mode_error = "Structured output mode is invalid"
    if provider == "mock":
        error = timeout_error or token_error or mode_error
        return ProviderConfig(
            provider=provider,
            timeout_seconds=timeout,
            max_output_tokens=tokens,
            structured_output_mode=structured_output_mode,
            validation_error=error,
        )
    raw_url = values.get("AGENTFORGE_LLM_BASE_URL", "").strip()
    base_url, url_error = _validated_base_url(raw_url)
    model = values.get("AGENTFORGE_LLM_MODEL", "").strip()
    api_key = values.get("AGENTFORGE_LLM_API_KEY", "")
    error = (
        timeout_error
        or token_error
        or mode_error
        or url_error
        or ("Model is required" if not model else None)
        or ("API key is required" if not api_key else None)
    )
    return ProviderConfig(
        provider=provider,
        base_url=base_url,
        model=model,
        api_key=api_key,
        timeout_seconds=timeout,
        max_output_tokens=tokens,
        structured_output_mode=structured_output_mode,
        validation_error=error,
    )


def build_provider(
    config: ProviderConfig,
    *,
    transport: Any = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> LLMProvider:
    if not config.configured:
        raise ProviderError(
            ProviderErrorCategory.NOT_CONFIGURED,
            safe_message="Real LLM provider is not configured",
        )
    if config.provider == "mock":
        from .mock import MockLLMProvider

        return MockLLMProvider()
    from .openai_compatible import OpenAICompatibleProvider

    return OpenAICompatibleProvider(config, transport=transport, sleeper=sleeper)
