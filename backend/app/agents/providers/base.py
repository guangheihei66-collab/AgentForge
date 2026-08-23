"""Typed, execution-free provider boundary for plan generation."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, Protocol


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

    def __init__(
        self,
        category: ProviderErrorCategory,
        *,
        retryable: bool = False,
        safe_message: str = "LLM provider request failed",
        attempt_count: int = 1,
        duration_ms: int = 0,
    ) -> None:
        super().__init__(safe_message)
        self.category = category
        self.retryable = retryable
        self.safe_message = safe_message
        self.attempt_count = attempt_count
        self.duration_ms = duration_ms


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


class LLMProvider(Protocol):
    def generate_plan(self, request: LLMRequest) -> LLMResponse:
        """Return untrusted candidate planning data without executing tools."""

    def test_connection(self) -> LLMResponse:
        """Perform one bounded, non-plan compatibility check."""
