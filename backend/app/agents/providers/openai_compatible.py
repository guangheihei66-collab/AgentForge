"""Bounded OpenAI-compatible Chat Completions planning transport."""

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import time
from typing import Any

import httpx

from .base import (
    LLMRequest,
    LLMResponse,
    ProviderError,
    ProviderErrorCategory,
)
from .config import ProviderConfig


MAX_RESPONSE_BYTES = 64 * 1024
RETRY_DELAYS = (0.5, 1.5)
SYSTEM_BOUNDARY = (
    "Return only the requested JSON object. You may propose capability "
    "requirements, but never tools, commands, permissions, approvals, or execution."
)


class OpenAICompatibleProvider:
    def __init__(
        self,
        config: ProviderConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not config.configured or config.provider != "openai-compatible":
            raise ProviderError(
                ProviderErrorCategory.NOT_CONFIGURED,
                safe_message="Real LLM provider is not configured",
            )
        self.config = config
        self.transport = transport
        self.sleeper = sleeper

    @property
    def provider_name(self) -> str:
        return "openai-compatible"

    @property
    def model_name(self) -> str:
        return self.config.model

    def generate_plan(self, request: LLMRequest) -> LLMResponse:
        return self._complete(
            prompt=request.prompt,
            output_schema=request.output_schema,
            schema_name="agentforge_plan",
            max_tokens=self.config.max_output_tokens,
        )

    def test_connection(self) -> LLMResponse:
        return self._complete(
            prompt="Return a JSON object with status set to ok.",
            output_schema={
                "type": "object",
                "properties": {"status": {"type": "string", "const": "ok"}},
                "required": ["status"],
                "additionalProperties": False,
            },
            schema_name="agentforge_connection",
            max_tokens=32,
        )

    def _complete(
        self,
        *,
        prompt: str,
        output_schema: Mapping[str, Any],
        schema_name: str,
        max_tokens: int,
    ) -> LLMResponse:
        request_payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": SYSTEM_BOUNDARY},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": dict(output_schema),
                },
            },
        }
        started = time.perf_counter()
        for attempt in range(1, 4):
            try:
                body, retry_after = self._send_once(request_payload)
                payload, input_tokens, output_tokens = self._extract(body)
                return LLMResponse(
                    payload=payload,
                    provider="openai-compatible",
                    model=self.config.model,
                    duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                    attempt_count=attempt,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
            except ProviderError as exc:
                error = exc
                retry_after = getattr(exc, "retry_after", None)
            except httpx.TimeoutException:
                error = ProviderError(
                    ProviderErrorCategory.TIMEOUT,
                    retryable=True,
                    safe_message="LLM provider timed out",
                )
                retry_after = None
            except (httpx.NetworkError, httpx.RemoteProtocolError):
                error = ProviderError(
                    ProviderErrorCategory.NETWORK_ERROR,
                    retryable=True,
                    safe_message="LLM provider network request failed",
                )
                retry_after = None
            if not error.retryable or attempt == 3:
                raise ProviderError(
                    error.category,
                    retryable=error.retryable,
                    safe_message=error.safe_message,
                    attempt_count=attempt,
                    duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                ) from None
            delay = retry_after if retry_after is not None else RETRY_DELAYS[attempt - 1]
            self.sleeper(delay)
        raise AssertionError("bounded retry loop exhausted")

    def _send_once(self, payload: Mapping[str, Any]) -> tuple[bytes, float | None]:
        endpoint = f"{self.config.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        timeout = httpx.Timeout(self.config.timeout_seconds)
        with httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            transport=self.transport,
        ) as client:
            with client.stream(
                "POST", endpoint, headers=headers, json=dict(payload)
            ) as response:
                if not 200 <= response.status_code < 300:
                    raise self._status_error(
                        response.status_code, response.headers.get("Retry-After")
                    )
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > MAX_RESPONSE_BYTES:
                        raise ProviderError(
                            ProviderErrorCategory.RESPONSE_TOO_LARGE,
                            safe_message="LLM provider response exceeded the size limit",
                        )
                    chunks.append(chunk)
                return b"".join(chunks), None

    @staticmethod
    def _status_error(status: int, retry_after_value: str | None) -> ProviderError:
        if status in {401, 403}:
            return ProviderError(
                ProviderErrorCategory.AUTHENTICATION_FAILED,
                safe_message="LLM provider authentication failed",
            )
        if status == 408:
            error = ProviderError(
                ProviderErrorCategory.TIMEOUT,
                retryable=True,
                safe_message="LLM provider timed out",
            )
        elif status == 429:
            error = ProviderError(
                ProviderErrorCategory.RATE_LIMITED,
                retryable=True,
                safe_message="LLM provider rate limited the request",
            )
        elif 500 <= status < 600:
            error = ProviderError(
                ProviderErrorCategory.UPSTREAM_SERVER_ERROR,
                retryable=True,
                safe_message="LLM provider server failed",
            )
        else:
            return ProviderError(
                ProviderErrorCategory.INVALID_RESPONSE,
                safe_message="LLM provider returned an invalid HTTP response",
            )
        error.retry_after = OpenAICompatibleProvider._retry_after(retry_after_value)
        return error

    @staticmethod
    def _retry_after(value: str | None) -> float | None:
        if not value:
            return None
        try:
            seconds = float(value)
        except ValueError:
            try:
                target = parsedate_to_datetime(value)
                if target.tzinfo is None:
                    target = target.replace(tzinfo=timezone.utc)
                seconds = (target - datetime.now(timezone.utc)).total_seconds()
            except (TypeError, ValueError, OverflowError):
                return None
        if seconds < 0:
            return None
        return min(seconds, 5.0)

    @staticmethod
    def _extract(body: bytes) -> tuple[dict[str, Any], int | None, int | None]:
        try:
            envelope = json.loads(body)
            choices = envelope["choices"]
            content = choices[0]["message"]["content"]
            payload = json.loads(content) if isinstance(content, str) else content
            if not isinstance(payload, dict):
                raise TypeError
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            raise ProviderError(
                ProviderErrorCategory.INVALID_RESPONSE,
                safe_message="LLM provider returned invalid structured data",
            ) from None
        usage = envelope.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        return (
            payload,
            OpenAICompatibleProvider._token_count(usage.get("prompt_tokens")),
            OpenAICompatibleProvider._token_count(usage.get("completion_tokens")),
        )

    @staticmethod
    def _token_count(value: Any) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
