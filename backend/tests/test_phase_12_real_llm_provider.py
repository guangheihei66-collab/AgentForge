from __future__ import annotations

from dataclasses import FrozenInstanceError
import json

import httpx
import pytest

from app.agents.providers import (
    LLMRequest,
    MockLLMProvider,
    ProviderError,
    ProviderErrorCategory,
    build_provider,
    load_provider_config,
)
from app.agents.providers.openai_compatible import OpenAICompatibleProvider


SECRET = "PHASE12_TEST_SECRET_DO_NOT_LEAK"


def real_env(base_url: str = "https://llm.example.test/v1") -> dict[str, str]:
    return {
        "AGENTFORGE_LLM_PROVIDER": "openai-compatible",
        "AGENTFORGE_LLM_BASE_URL": base_url,
        "AGENTFORGE_LLM_MODEL": "example-model",
        "AGENTFORGE_LLM_API_KEY": SECRET,
        "AGENTFORGE_LLM_TIMEOUT_SECONDS": "30",
        "AGENTFORGE_LLM_MAX_OUTPUT_TOKENS": "1200",
    }


def test_default_configuration_selects_mock():
    config = load_provider_config({})

    assert config.provider == "mock"
    assert config.timeout_seconds == 30.0
    assert config.max_output_tokens == 1200
    assert config.configured is True
    assert config.credential_configured is False


def test_real_configuration_is_immutable_and_redacted():
    config = load_provider_config(real_env())

    assert config.configured is True
    assert config.credential_configured is True
    assert SECRET not in repr(config)
    with pytest.raises(FrozenInstanceError):
        config.model = "changed"


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:9000/v1",
        "http://127.0.0.1:9000/v1",
        "http://[::1]:9000/v1",
        "https://10.0.0.8/v1",
    ],
)
def test_approved_base_urls(url: str):
    assert load_provider_config(real_env(url)).configured is True


@pytest.mark.parametrize(
    "url",
    [
        "http://10.0.0.8/v1",
        "http://llm.example.test/v1",
        "https://user:password@llm.example.test/v1",
        "https://llm.example.test/v1?target=other",
        "https://llm.example.test/v1#fragment",
    ],
)
def test_rejected_base_urls_fail_closed_without_secret(url: str):
    config = load_provider_config(real_env(url))

    assert config.configured is False
    with pytest.raises(ProviderError) as exc:
        build_provider(config)
    assert exc.value.category == ProviderErrorCategory.NOT_CONFIGURED
    assert SECRET not in str(exc.value)
    assert SECRET not in repr(config)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("AGENTFORGE_LLM_TIMEOUT_SECONDS", "0"),
        ("AGENTFORGE_LLM_TIMEOUT_SECONDS", "121"),
        ("AGENTFORGE_LLM_TIMEOUT_SECONDS", "invalid"),
        ("AGENTFORGE_LLM_MAX_OUTPUT_TOKENS", "0"),
        ("AGENTFORGE_LLM_MAX_OUTPUT_TOKENS", "4097"),
        ("AGENTFORGE_LLM_MAX_OUTPUT_TOKENS", "invalid"),
    ],
)
def test_numeric_configuration_bounds_fail_closed(name: str, value: str):
    environ = real_env()
    environ[name] = value

    config = load_provider_config(environ)

    assert config.configured is False
    with pytest.raises(ProviderError) as exc:
        build_provider(config)
    assert exc.value.category == ProviderErrorCategory.NOT_CONFIGURED


@pytest.mark.parametrize(
    "missing",
    [
        "AGENTFORGE_LLM_BASE_URL",
        "AGENTFORGE_LLM_MODEL",
        "AGENTFORGE_LLM_API_KEY",
    ],
)
def test_missing_real_configuration_never_falls_back_to_mock(missing: str):
    environ = real_env()
    environ[missing] = ""

    config = load_provider_config(environ)

    assert config.provider == "openai-compatible"
    assert config.configured is False
    with pytest.raises(ProviderError) as exc:
        build_provider(config)
    assert exc.value.category == ProviderErrorCategory.NOT_CONFIGURED


def test_unknown_provider_is_rejected():
    with pytest.raises(ProviderError) as exc:
        load_provider_config({"AGENTFORGE_LLM_PROVIDER": "unexpected"})

    assert exc.value.category == ProviderErrorCategory.NOT_CONFIGURED


def test_mock_provider_is_deterministic_and_network_free():
    provider = MockLLMProvider()
    request = LLMRequest(prompt="bounded", context={}, output_schema={})

    first = provider.generate_plan(request)
    second = provider.generate_plan(request)

    assert first.payload == second.payload
    assert first.provider == "mock"
    assert provider.test_connection().payload == {"status": "ok"}
    assert SECRET not in json.dumps(dict(first.payload))


def valid_plan() -> dict:
    return {
        "schema_version": 2,
        "summary": "Inspect repository state.",
        "steps": [
            {
                "step_id": "step-1",
                "capability_id": "repository_state",
                "parameters": {},
            }
        ],
    }


def plan_request() -> LLMRequest:
    return LLMRequest(
        prompt="Return a bounded capability plan.",
        context={},
        output_schema={"type": "object"},
    )


def real_config():
    return load_provider_config(real_env())


def chat_response(content: dict, *, usage: dict | None = None) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": json.dumps(content)}}],
            "usage": usage or {},
        },
    )


def test_real_provider_sends_bounded_authenticated_structured_request():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return chat_response(valid_plan(), usage={"prompt_tokens": 12, "completion_tokens": 8})

    provider = OpenAICompatibleProvider(
        real_config(), transport=httpx.MockTransport(handler), sleeper=lambda _: None
    )

    response = provider.generate_plan(plan_request())

    request = captured["request"]
    body = json.loads(request.content)
    assert response.payload == valid_plan()
    assert response.input_tokens == 12
    assert response.output_tokens == 8
    assert str(request.url) == "https://llm.example.test/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {SECRET}"
    assert body["model"] == "example-model"
    assert body["max_tokens"] == 1200
    assert body["response_format"]["type"] == "json_schema"
    assert "temperature" not in body


@pytest.mark.parametrize(
    ("status", "category", "attempts"),
    [
        (400, ProviderErrorCategory.INVALID_RESPONSE, 1),
        (401, ProviderErrorCategory.AUTHENTICATION_FAILED, 1),
        (403, ProviderErrorCategory.AUTHENTICATION_FAILED, 1),
        (408, ProviderErrorCategory.TIMEOUT, 3),
        (429, ProviderErrorCategory.RATE_LIMITED, 3),
        (500, ProviderErrorCategory.UPSTREAM_SERVER_ERROR, 3),
    ],
)
def test_status_mapping_and_retry_bounds(status, category, attempts):
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status, text=SECRET, headers={"X-Debug": SECRET})

    provider = OpenAICompatibleProvider(
        real_config(), transport=httpx.MockTransport(handler), sleeper=lambda _: None
    )

    with pytest.raises(ProviderError) as exc:
        provider.generate_plan(plan_request())

    assert calls == attempts
    assert exc.value.category == category
    assert exc.value.attempt_count == attempts
    assert SECRET not in str(exc.value)


@pytest.mark.parametrize(
    ("exception", "category"),
    [
        (httpx.TimeoutException("unsafe", request=httpx.Request("POST", "https://x")), ProviderErrorCategory.TIMEOUT),
        (httpx.ConnectError("unsafe", request=httpx.Request("POST", "https://x")), ProviderErrorCategory.NETWORK_ERROR),
    ],
)
def test_transient_transport_errors_retry_three_times(exception, category):
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise exception

    provider = OpenAICompatibleProvider(
        real_config(), transport=httpx.MockTransport(handler), sleeper=lambda _: None
    )

    with pytest.raises(ProviderError) as exc:
        provider.generate_plan(plan_request())

    assert calls == 3
    assert exc.value.category == category
    assert "unsafe" not in str(exc.value)


def test_retry_delays_and_retry_after_are_bounded():
    delays = []
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "99"})
        if calls == 2:
            return httpx.Response(500)
        return chat_response(valid_plan())

    provider = OpenAICompatibleProvider(
        real_config(), transport=httpx.MockTransport(handler), sleeper=delays.append
    )

    assert provider.generate_plan(plan_request()).attempt_count == 3
    assert delays == [5.0, 1.5]


def test_response_body_over_64_kib_is_rejected_without_retry():
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=b"x" * 65_537)

    provider = OpenAICompatibleProvider(
        real_config(), transport=httpx.MockTransport(handler), sleeper=lambda _: None
    )

    with pytest.raises(ProviderError) as exc:
        provider.generate_plan(plan_request())

    assert calls == 1
    assert exc.value.category == ProviderErrorCategory.RESPONSE_TOO_LARGE


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{"message": {"content": "[]"}}]}),
    ],
)
def test_malformed_success_response_is_rejected_without_retry(response):
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return response

    provider = OpenAICompatibleProvider(
        real_config(), transport=httpx.MockTransport(handler), sleeper=lambda _: None
    )

    with pytest.raises(ProviderError) as exc:
        provider.generate_plan(plan_request())

    assert calls == 1
    assert exc.value.category == ProviderErrorCategory.INVALID_RESPONSE


def test_connection_check_uses_fixed_non_plan_payload_and_small_budget():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return chat_response({"status": "ok"})

    provider = OpenAICompatibleProvider(
        real_config(), transport=httpx.MockTransport(handler), sleeper=lambda _: None
    )

    response = provider.test_connection()

    assert response.payload == {"status": "ok"}
    assert captured["body"]["max_tokens"] <= 32
    serialized = json.dumps(captured["body"])
    assert "repository" not in serialized.lower()
    assert "business" not in serialized.lower()
