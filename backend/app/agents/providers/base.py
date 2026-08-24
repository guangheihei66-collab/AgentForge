"""Typed, execution-free provider boundary for plan generation."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, Protocol


class StructuredOutputMode(StrEnum):
    JSON_SCHEMA = "json_schema"
    JSON_OBJECT = "json_object"


class ProviderErrorCategory(StrEnum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    UPSTREAM_SERVER_ERROR = "UPSTREAM_SERVER_ERROR"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    RESPONSE_TOO_LARGE = "RESPONSE_TOO_LARGE"


class ProviderError(RuntimeError):
    """Safe provider failure that never retains raw upstream details."""

    _SAFE_MESSAGES = {
        ProviderErrorCategory.NOT_CONFIGURED: "LLM provider is not configured",
        ProviderErrorCategory.AUTHENTICATION_FAILED: "LLM provider authentication failed",
        ProviderErrorCategory.RATE_LIMITED: "LLM provider rate limit reached",
        ProviderErrorCategory.TIMEOUT: "LLM provider request timed out",
        ProviderErrorCategory.NETWORK_ERROR: "LLM provider network request failed",
        ProviderErrorCategory.UPSTREAM_SERVER_ERROR: "LLM provider server request failed",
        ProviderErrorCategory.INVALID_RESPONSE: "LLM provider returned an invalid response",
        ProviderErrorCategory.RESPONSE_TOO_LARGE: "LLM provider response exceeded the size limit",
    }

    def __init__(
        self,
        category: ProviderErrorCategory,
        *,
        retryable: bool = False,
        safe_message: str = "LLM provider request failed",
        attempt_count: int = 1,
        duration_ms: int = 0,
        diagnostics: Mapping[str, Any] | None = None,
    ) -> None:
        del safe_message  # Caller or upstream text must never be retained.
        public_message = self._SAFE_MESSAGES[category]
        super().__init__(public_message)
        self.category = category
        self.retryable = retryable
        self.safe_message = public_message
        self.attempt_count = attempt_count
        self.duration_ms = duration_ms
        self.diagnostics = dict(diagnostics or {})


@dataclass(frozen=True, slots=True)
class LLMRequest:
    prompt: str
    context: Mapping[str, Any]
    output_schema: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class LLMResponse:
    payload: Mapping[str, Any]
    provider: str
    model: str
    duration_ms: int
    attempt_count: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


class LLMProvider(Protocol):
    provider_name: str
    model_name: str

    def generate_plan(self, request: LLMRequest) -> LLMResponse:
        """Return untrusted candidate planning data without executing tools."""

    def generate_replan(self, request: LLMRequest) -> LLMResponse:
        """Return untrusted capability-only remaining-plan data."""

    def test_connection(self) -> LLMResponse:
        """Perform one bounded, non-plan compatibility check."""
