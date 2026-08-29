"""Bounded OpenAI-compatible Chat Completions planning transport."""

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import time
from typing import Any
from urllib.parse import urlsplit

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
MAX_ERROR_BODY_BYTES = 8 * 1024
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
            prompt='Return valid JSON only in exactly this shape: {"status":"ok"}.',
            output_schema={
                "type": "object",
                "properties": {"status": {"type": "string", "const": "ok"}},
                "required": ["status"],
                "additionalProperties": False,
            },
            schema_name="agentforge_connection",
            max_tokens=128,
            structured_output_mode=StructuredOutputMode.JSON_OBJECT,
        )
        if response.payload.get("status") != "ok":
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
        structured_output_mode: StructuredOutputMode | None = None,
    ) -> LLMResponse:
        del schema_name, output_schema, structured_output_mode
        output_mode = StructuredOutputMode.JSON_OBJECT
        response_format: dict[str, Any] = {"type": output_mode.value}
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
        request_facts = self._request_facts(
            request_payload,
            endpoint_path=urlsplit(f"{self.config.base_url}/chat/completions").path,
            prompt=prompt,
            output_mode=output_mode,
        )
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
                    diagnostics={"request_facts": request_facts, **diagnostics},
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
            except httpx.ConnectError:
                error = ProviderError(
                    ProviderErrorCategory.ENDPOINT_UNREACHABLE,
                    retryable=True,
                    safe_message="LLM provider endpoint is unreachable",
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
                    diagnostics={"request_facts": request_facts, **error.diagnostics},
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
                    error_body = OpenAICompatibleProvider._read_error_body(response)
                    raise self._status_error(
                        response.status_code,
                        response.headers.get("Retry-After"),
                        error_body,
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
    def _status_error(
        status: int,
        retry_after_value: str | None,
        body: bytes = b"",
    ) -> ProviderError:
        diagnostics = {
            "upstream_http_status": status,
            "failure_stage": "upstream_http",
            **OpenAICompatibleProvider._safe_upstream_error_facts(status, body),
        }
        if status in {401, 403}:
            return ProviderError(
                ProviderErrorCategory.AUTHENTICATION_FAILED,
                safe_message="LLM provider authentication failed",
                diagnostics=diagnostics,
            )
        if status == 402:
            return ProviderError(
                ProviderErrorCategory.INSUFFICIENT_BALANCE,
                safe_message="LLM provider balance is insufficient",
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
        elif status in {400, 404, 422}:
            category = OpenAICompatibleProvider._classify_error_body(status, body)
            return ProviderError(category, diagnostics=diagnostics)
        else:
            return ProviderError(
                ProviderErrorCategory.PROVIDER_ERROR,
                safe_message="LLM provider returned an unexpected HTTP response",
                diagnostics=diagnostics,
            )
        error.retry_after = OpenAICompatibleProvider._retry_after(retry_after_value)
        return error

    @staticmethod
    def _read_error_body(response: httpx.Response) -> bytes:
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes():
            remaining = MAX_ERROR_BODY_BYTES - total
            if remaining <= 0:
                break
            bounded = chunk[:remaining]
            chunks.append(bounded)
            total += len(bounded)
        return b"".join(chunks)

    @staticmethod
    def _classify_error_body(status: int, body: bytes) -> ProviderErrorCategory:
        default = ProviderErrorCategory.INVALID_CONFIGURATION
        text = OpenAICompatibleProvider._error_text(body)
        model_markers = ("model", "engine")
        unavailable_markers = (
            "not found",
            "does not exist",
            "unavailable",
            "invalid model",
            "unknown model",
        )
        if any(marker in text for marker in model_markers) and any(
            marker in text for marker in unavailable_markers
        ):
            return ProviderErrorCategory.MODEL_UNAVAILABLE
        return default

    @staticmethod
    def _error_text(body: bytes) -> str:
        """Return a transient classifier string; never place it in diagnostics."""

        try:
            envelope = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return ""
        if not isinstance(envelope, dict):
            return ""
        error = envelope.get("error")
        values: list[str] = []
        if isinstance(error, dict):
            values.extend(value for value in error.values() if isinstance(value, str))
        elif isinstance(error, str):
            values.append(error)
        values.extend(
            value
            for key, value in envelope.items()
            if key in {"code", "type", "message"} and isinstance(value, str)
        )
        return " ".join(values).casefold().replace("_", " ").replace("-", " ")

    @staticmethod
    def _safe_upstream_error_facts(status: int, body: bytes) -> dict[str, str]:
        """Map untrusted upstream text to fixed, non-sensitive diagnostics."""

        text = OpenAICompatibleProvider._error_text(body)
        if status in {401, 403}:
            return {
                "upstream_error_category": "authentication",
                "upstream_error_message": "Provider rejected authentication credentials",
            }
        if status == 402:
            return {
                "upstream_error_category": "insufficient_balance",
                "upstream_error_message": "Provider reported insufficient balance",
            }
        if status == 429:
            return {
                "upstream_error_category": "rate_limit",
                "upstream_error_message": "Provider rate-limited the request",
            }
        if status == 404 and "model" in text:
            return {
                "upstream_error_category": "model_unavailable",
                "upstream_error_message": "Provider rejected the configured model",
            }
        if status in {400, 422}:
            if "response format" in text or "json schema" in text:
                return {
                    "upstream_error_category": "unsupported_response_format",
                    "upstream_error_message": "Provider rejected the response_format parameter",
                }
            if "thinking" in text or "reasoning" in text:
                return {
                    "upstream_error_category": "unsupported_thinking_mode",
                    "upstream_error_message": "Provider rejected the thinking configuration",
                }
            if "max tokens" in text or "max completion tokens" in text:
                return {
                    "upstream_error_category": "invalid_token_parameter",
                    "upstream_error_message": "Provider rejected the token limit parameter",
                }
            return {
                "upstream_error_category": "invalid_request",
                "upstream_error_message": "Provider rejected request parameters",
            }
        return {}

    @staticmethod
    def _request_facts(
        payload: Mapping[str, Any],
        *,
        endpoint_path: str,
        prompt: str,
        output_mode: StructuredOutputMode,
    ) -> dict[str, Any]:
        messages = payload.get("messages", [])
        message_roles = [
            item.get("role")
            for item in messages
            if isinstance(item, Mapping) and isinstance(item.get("role"), str)
        ]
        message_text = " ".join(
            item.get("content", "")
            for item in messages
            if isinstance(item, Mapping) and isinstance(item.get("content"), str)
        )
        response_format = payload.get("response_format")
        response_format_type = (
            response_format.get("type")
            if isinstance(response_format, Mapping)
            else None
        )
        return {
            "http_method": "POST",
            "endpoint_path": endpoint_path or "/chat/completions",
            "model": payload.get("model"),
            "structured_output_mode": output_mode.value,
            "response_format_type": response_format_type,
            "thinking": (
                payload["thinking"].get("type")
                if isinstance(payload.get("thinking"), Mapping)
                else None
            ),
            "max_tokens": payload.get("max_tokens"),
            "temperature_present": "temperature" in payload,
            "tool_fields_present": any(
                field in payload for field in ("tools", "tool_choice")
            ),
            "top_level_fields": sorted(
                field for field in payload if not field.startswith("_")
            ),
            "message_roles": message_roles,
            "json_instruction_present": "json"
            in f"{prompt} {message_text}".casefold(),
        }

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
