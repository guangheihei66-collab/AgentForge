from __future__ import annotations

from dataclasses import FrozenInstanceError
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agents.planner.planner import PlannerAgent
from app.agents.planner.prompts import build_planning_prompt
from app.agents.planner.schemas import PlanContract
from app.agents.planner.validator import PlanValidationError, PlanValidator
from app.agents.providers import (
    LLMRequest,
    LLMResponse,
    MockLLMProvider,
    ProviderError,
    ProviderErrorCategory,
    build_provider,
    load_provider_config,
)
from app.agents.providers.openai_compatible import OpenAICompatibleProvider
from app.api.routes.planning import get_llm_provider
from app.api.routes.providers import connection_state, get_status_provider
from app.capabilities.registry import build_default_capability_registry
from app.capabilities.resolver import CapabilityResolutionError
from app.domain.states.task_state import TaskStatus
from app.main import app
from app.services.task_service import TaskService
from app.storage.database import SessionLocal
from app.storage.orm import (
    ApprovalRecord,
    AuditEventRecord,
    PlanRecord,
    TaskRecord,
    ToolExecutionRecord,
)
from app.workspace.validator import WorkspaceValidator
from tests.project_test_support import create_project_task, project_fixture


SECRET = "PHASE12_TEST_SECRET_DO_NOT_LEAK"
REPO_ROOT = r"D:\AgentProjects\AgentForge"


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
        ("AGENTFORGE_LLM_MAX_OUTPUT_TOKENS", "1200.9"),
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
        httpx.Response(200, content=b"\xff\xfe"),
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


@pytest.mark.parametrize("acknowledgement", [{}, {"status": "error"}])
def test_connection_check_rejects_invalid_acknowledgement(acknowledgement):
    provider = OpenAICompatibleProvider(
        real_config(),
        transport=httpx.MockTransport(lambda _: chat_response(acknowledgement)),
        sleeper=lambda _: None,
    )

    with pytest.raises(ProviderError) as exc:
        provider.test_connection()

    assert exc.value.category == ProviderErrorCategory.INVALID_RESPONSE


class FakeProvider:
    provider_name = "openai-compatible"
    model_name = "fake-model"

    def __init__(self, *, payload: dict | None = None, error: ProviderError | None = None):
        self.payload = payload or valid_plan()
        self.error = error
        self.plan_calls = 0
        self.connection_calls = 0

    def generate_plan(self, request: LLMRequest) -> LLMResponse:
        self.plan_calls += 1
        if self.error:
            raise self.error
        return LLMResponse(
            payload=self.payload,
            provider=self.provider_name,
            model=self.model_name,
            duration_ms=12,
            attempt_count=1,
            input_tokens=10,
            output_tokens=7,
        )

    def test_connection(self) -> LLMResponse:
        self.connection_calls += 1
        if self.error:
            raise self.error
        return LLMResponse(
            payload={"status": "ok"}, provider=self.provider_name,
            model=self.model_name, duration_ms=4, attempt_count=1,
        )


def repository_step() -> dict:
    return {"step_id": "step-1", "capability_id": "repository_state", "parameters": {}}


def test_summary_is_bounded_and_old_v2_plan_remains_readable():
    old = PlanContract.model_validate({"schema_version": 2, "steps": [repository_step()]})

    assert old.summary == ""
    with pytest.raises(ValidationError):
        PlanContract.model_validate(
            {"schema_version": 2, "summary": "x" * 501, "steps": [repository_step()]}
        )


def test_prompt_contains_capabilities_not_concrete_tools_or_secrets():
    prompt = build_planning_prompt(
        "Check release", build_default_capability_registry(), {"release": "2.0"}
    )

    assert "repository_state" in prompt
    assert "profile" in prompt and "smoke" in prompt
    assert "git_read" not in prompt and "test_run" not in prompt
    assert SECRET not in prompt


def test_prompt_rejects_oversized_context():
    with pytest.raises(ValueError, match="context"):
        build_planning_prompt(
            "Check release", build_default_capability_registry(), {"summary": "x" * 4097}
        )


@pytest.mark.parametrize(
    "extra",
    [
        {"tool_id": "git_read"},
        {"command": "git status"},
        {"permission": "SAFE_READ"},
        {"approval": "APPROVED"},
        {"workspace": "C:/"},
    ],
)
def test_model_cannot_add_execution_authority(extra: dict):
    payload = valid_plan()
    payload["steps"][0].update(extra)
    validator = PlanValidator(WorkspaceValidator(REPO_ROOT))

    with pytest.raises(PlanValidationError):
        validator.validate(payload, REPO_ROOT)


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": 2, "summary": "empty", "steps": []},
        {"schema_version": 2, "summary": "unknown", "steps": [{"step_id": "1", "capability_id": "unknown", "parameters": {}}]},
        {"schema_version": 2, "summary": "command", "steps": [{"step_id": "1", "capability_id": "test_verification", "parameters": {"profile": "smoke", "command": "bash"}}]},
        {"schema_version": 2, "summary": "large", "steps": [repository_step() for _ in range(21)]},
    ],
)
def test_invalid_provider_plan_never_resolves(payload: dict):
    validator = PlanValidator(WorkspaceValidator(REPO_ROOT))
    with pytest.raises(PlanValidationError):
        validator.validate(payload, REPO_ROOT)


def test_invalid_capability_parameters_fail_during_resolution(db_session):
    task = create_project_task(db_session,
        title="Invalid capability", goal="Check release"
    )
    payload = {
        "schema_version": 2,
        "summary": "Invalid profile",
        "steps": [
            {
                "step_id": "step-1",
                "capability_id": "test_verification",
                "parameters": {"profile": "all"},
            }
        ],
    }

    with pytest.raises(CapabilityResolutionError):
        PlannerAgent(db_session, FakeProvider(payload=payload)).create_plan(task.id)

    assert TaskService(db_session).get_task(task.id).status == TaskStatus.FAILED
    assert db_session.query(PlanRecord).filter_by(task_id=task.id).count() == 0


def test_provider_plan_is_validated_resolved_and_safely_audited(db_session):
    task = create_project_task(db_session,
        title="Phase 12", goal="Check release"
    )

    plan = PlannerAgent(db_session, FakeProvider()).create_plan(task.id)

    refreshed = TaskService(db_session).get_task(task.id)
    assert refreshed.status == TaskStatus.WAITING_APPROVAL
    assert plan.plan_json["summary"] == "Inspect repository state."
    assert plan.plan_json["resolved_steps"][0]["resolved_tool_id"] == "git_read"
    events = db_session.query(AuditEventRecord).filter_by(task_id=task.id).all()
    event_types = {event.event_type for event in events}
    assert {"LLM_PLAN_REQUESTED", "LLM_PLAN_SUCCEEDED"}.issubset(event_types)
    serialized = json.dumps([event.payload_summary for event in events])
    assert SECRET not in serialized
    assert db_session.query(ApprovalRecord).filter_by(task_id=task.id).count() == 0
    assert db_session.query(ToolExecutionRecord).filter_by(task_id=task.id).count() == 0


def test_provider_failure_marks_task_failed_without_partial_plan(db_session):
    task = create_project_task(db_session,
        title="Phase 12 failure", goal="Check release"
    )
    provider = FakeProvider(
        error=ProviderError(
            ProviderErrorCategory.TIMEOUT,
            safe_message="Provider timed out",
            attempt_count=3,
            duration_ms=1234,
        )
    )

    with pytest.raises(ProviderError):
        PlannerAgent(db_session, provider).create_plan(task.id)

    assert TaskService(db_session).get_task(task.id).status == TaskStatus.FAILED
    assert db_session.query(PlanRecord).filter_by(task_id=task.id).count() == 0
    events = db_session.query(AuditEventRecord).filter_by(task_id=task.id).all()
    assert "LLM_PLAN_FAILED" in {event.event_type for event in events}
    assert SECRET not in json.dumps([event.payload_summary for event in events])


def test_planning_api_uses_injected_provider_without_silent_fallback(db_session):
    failing = FakeProvider(
        error=ProviderError(
            ProviderErrorCategory.NETWORK_ERROR,
            safe_message="Provider unavailable",
        )
    )
    app.dependency_overrides[get_llm_provider] = lambda: failing
    try:
        with TestClient(app) as client:
            project_id = project_fixture(db_session).id
            task = client.post(
                "/tasks",
                json={"title": "API Phase 12", "goal": "Check", "project_id": project_id},
            ).json()
            response = client.post(f"/tasks/{task['id']}/plan", json={})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert response.json()["detail"] == "LLM planning failed: NETWORK_ERROR"
    assert failing.plan_calls == 1
    with SessionLocal() as session:
        assert TaskService(session).get_task(task["id"]).status == TaskStatus.FAILED


def set_real_environment(monkeypatch, *, api_key: str = SECRET):
    for name, value in real_env().items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("AGENTFORGE_LLM_API_KEY", api_key)


def database_counts() -> dict[str, int]:
    with SessionLocal() as session:
        return {
            "tasks": session.query(TaskRecord).count(),
            "plans": session.query(PlanRecord).count(),
            "approvals": session.query(ApprovalRecord).count(),
            "executions": session.query(ToolExecutionRecord).count(),
            "audit": session.query(AuditEventRecord).count(),
        }


def test_provider_status_exposes_no_credential_material(monkeypatch):
    set_real_environment(monkeypatch)
    connection_state.reset()

    with TestClient(app) as client:
        response = client.get("/llm/provider")

    assert response.status_code == 200
    assert response.json() == {
        "provider": "openai-compatible",
        "configured": True,
        "model": "example-model",
        "credential_configured": True,
        "connection_status": "not tested",
        "failure_category": None,
    }
    assert SECRET not in response.text
    assert "base_url" not in response.text


def test_invalid_real_configuration_is_visible_without_mock_fallback(monkeypatch):
    set_real_environment(monkeypatch, api_key="")
    connection_state.reset()

    with TestClient(app) as client:
        response = client.get("/llm/provider")

    assert response.status_code == 200
    assert response.json()["provider"] == "openai-compatible"
    assert response.json()["configured"] is False
    assert response.json()["credential_configured"] is False
    assert response.json()["failure_category"] == "NOT_CONFIGURED"


def test_connection_test_is_explicit_and_writes_no_database_records(monkeypatch):
    set_real_environment(monkeypatch)
    connection_state.reset()
    fake = FakeProvider()
    app.dependency_overrides[get_status_provider] = lambda: fake
    try:
        with TestClient(app) as client:
            before = database_counts()
            status = client.get("/llm/provider")
            assert fake.connection_calls == 0
            response = client.post("/llm/provider/test")
            after = database_counts()
    finally:
        app.dependency_overrides.clear()

    assert status.json()["connection_status"] == "not tested"
    assert response.status_code == 200
    assert response.json()["connection_status"] == "success"
    assert fake.connection_calls == 1
    assert fake.plan_calls == 0
    assert before == after


def test_connection_failure_returns_only_safe_category(monkeypatch):
    set_real_environment(monkeypatch)
    connection_state.reset()
    fake = FakeProvider(
        error=ProviderError(
            ProviderErrorCategory.AUTHENTICATION_FAILED,
            safe_message=SECRET,
        )
    )
    app.dependency_overrides[get_status_provider] = lambda: fake
    try:
        with TestClient(app) as client:
            response = client.post("/llm/provider/test")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["connection_status"] == "failed"
    assert response.json()["failure_category"] == "AUTHENTICATION_FAILED"
    assert SECRET not in response.text


def test_provider_error_never_retains_caller_supplied_sensitive_text():
    error = ProviderError(
        ProviderErrorCategory.AUTHENTICATION_FAILED,
        safe_message=SECRET,
    )

    assert SECRET not in str(error)
    assert SECRET not in repr(error)
    assert SECRET not in error.safe_message
