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
    StructuredOutputMode,
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

    def generate_replan(self, request: LLMRequest) -> LLMResponse:
        return self._complete(
            prompt=request.prompt,
            output_schema=request.output_schema,
            schema_name="agentforge_replan",
            max_tokens=self.config.max_output_tokens,
        )

    def generate_analyst(self, request: LLMRequest) -> LLMResponse:
        return self._complete(
            prompt=request.prompt,
            output_schema=request.output_schema,
            schema_name="agentforge_analyst_report",
            max_tokens=self.config.max_output_tokens,
            system_instruction=request.system_instruction,
        )

    def test_connection(self) -> LLMResponse:
        response = self._complete(
            prompt="Return a JSON object with status set to ok.",
            output_schema={
                "type": "object",
                "properties": {"status": {"type": "string", "const": "ok"}},
                "required": ["status"],
                "additionalProperties": False,
            },
            schema_name="agentforge_connection",
            max_tokens=128,
        )
        if response.payload != {"status": "ok"}:
            raise ProviderError(ProviderErrorCategory.INVALID_RESPONSE)
        return response

    def _complete(
        self,
        *,
        prompt: str,
        output_schema: Mapping[str, Any],
        schema_name: str,
        max_tokens: int,
        system_instruction: str = "",
    ) -> LLMResponse:
        response_format: dict[str, Any] = {"type": "json_object"}
        if self.config.structured_output_mode.value == StructuredOutputMode.JSON_SCHEMA.value:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": dict(output_schema),
                },
            }
        request_payload = {
            "model": self.config.model,
            "messages": [
                {
                    "role": "system",
                    "content": system_instruction or SYSTEM_BOUNDARY,
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "response_format": response_format,
            "thinking": {"type": "disabled"},
        }
        started = time.perf_counter()
        for attempt in range(1, 4):
            try:
                body, retry_after = self._send_once(request_payload)
                payload, input_tokens, output_tokens, diagnostics = self._extract(body)
                return LLMResponse(
                    payload=payload,
                    provider="openai-compatible",
                    model=self.config.model,
                    duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
                    attempt_count=attempt,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    diagnostics=diagnostics,
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
                    diagnostics=error.diagnostics,
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
        diagnostics = {
            "upstream_http_status": status,
            "failure_stage": "upstream_http",
        }
        if status in {401, 403}:
            return ProviderError(
                ProviderErrorCategory.AUTHENTICATION_FAILED,
                safe_message="LLM provider authentication failed",
                diagnostics=diagnostics,
            )
        if status == 408:
            error = ProviderError(
                ProviderErrorCategory.TIMEOUT,
                retryable=True,
                safe_message="LLM provider timed out",
                diagnostics=diagnostics,
            )
        elif status == 429:
            error = ProviderError(
                ProviderErrorCategory.RATE_LIMITED,
                retryable=True,
                safe_message="LLM provider rate limited the request",
                diagnostics=diagnostics,
            )
        elif 500 <= status < 600:
            error = ProviderError(
                ProviderErrorCategory.UPSTREAM_SERVER_ERROR,
                retryable=True,
                safe_message="LLM provider server failed",
                diagnostics=diagnostics,
            )
        else:
            return ProviderError(
                ProviderErrorCategory.INVALID_RESPONSE,
                safe_message="LLM provider returned an invalid HTTP response",
                diagnostics=diagnostics,
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
    def _extract(
        body: bytes, *, upstream_http_status: int = 200
    ) -> tuple[dict[str, Any], int | None, int | None, dict[str, Any]]:
        diagnostics: dict[str, Any] = {
            "upstream_http_status": upstream_http_status,
            "finish_reason": None,
            "content_present": False,
            "content_length": 0,
            "envelope_json_valid": False,
            "choices_present": False,
            "message_present": False,
            "content_json_valid": False,
            "content_json_object": False,
            "reasoning_content_present": False,
            "failure_stage": "envelope_json_parse",
        }
        try:
            envelope = json.loads(body)
            diagnostics["envelope_json_valid"] = True
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ProviderError(ProviderErrorCategory.INVALID_RESPONSE, diagnostics=diagnostics) from None
        if not isinstance(envelope, dict):
            diagnostics["failure_stage"] = "response_envelope"
            raise ProviderError(ProviderErrorCategory.INVALID_RESPONSE, diagnostics=diagnostics) from None
        choices = envelope.get("choices")
        if not isinstance(choices, list) or not choices:
            diagnostics["failure_stage"] = "choices"
            raise ProviderError(ProviderErrorCategory.INVALID_RESPONSE, diagnostics=diagnostics) from None
        diagnostics["choices_present"] = True
        choice = choices[0]
        if not isinstance(choice, dict):
            diagnostics["failure_stage"] = "choices"
            raise ProviderError(ProviderErrorCategory.INVALID_RESPONSE, diagnostics=diagnostics) from None
        finish_reason = choice.get("finish_reason")
        if isinstance(finish_reason, str):
            diagnostics["finish_reason"] = finish_reason
        message = choice.get("message")
        if not isinstance(message, dict):
            diagnostics["failure_stage"] = "message"
            raise ProviderError(ProviderErrorCategory.INVALID_RESPONSE, diagnostics=diagnostics) from None
        diagnostics["message_present"] = True
        diagnostics["reasoning_content_present"] = "reasoning_content" in message
        if "content" not in message:
            diagnostics["failure_stage"] = "content"
            raise ProviderError(ProviderErrorCategory.INVALID_RESPONSE, diagnostics=diagnostics) from None
        content = message["content"]
        if isinstance(content, str):
            diagnostics["content_present"] = bool(content)
            diagnostics["content_length"] = len(content)
        else:
            diagnostics["content_present"] = content is not None
        if not diagnostics["content_present"]:
            diagnostics["failure_stage"] = "content_empty"
            raise ProviderError(ProviderErrorCategory.INVALID_RESPONSE, diagnostics=diagnostics) from None
        if not isinstance(content, str):
            diagnostics["failure_stage"] = "content_type"
            raise ProviderError(ProviderErrorCategory.INVALID_RESPONSE, diagnostics=diagnostics) from None
        try:
            payload = json.loads(content)
            diagnostics["content_json_valid"] = True
        except json.JSONDecodeError:
            diagnostics["failure_stage"] = "content_json_parse"
            raise ProviderError(ProviderErrorCategory.INVALID_RESPONSE, diagnostics=diagnostics) from None
        if not isinstance(payload, dict):
            diagnostics["failure_stage"] = "content_not_object"
            raise ProviderError(ProviderErrorCategory.INVALID_RESPONSE, diagnostics=diagnostics) from None
        diagnostics["content_json_object"] = True
        diagnostics["failure_stage"] = None
        usage = envelope.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        return (
            payload,
            OpenAICompatibleProvider._token_count(usage.get("prompt_tokens")),
            OpenAICompatibleProvider._token_count(usage.get("completion_tokens")),
            diagnostics,
        )

    @staticmethod
    def _token_count(value: Any) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
