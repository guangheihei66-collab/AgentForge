# Real LLM Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task in one bounded working stream. Do not use parallel subagents. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicitly configured OpenAI-compatible planning provider that produces locally validated capability-first plans without gaining execution authority.

**Architecture:** Extend the existing provider protocol with immutable request, response, configuration, and safe-error contracts. A small environment-owned composition boundary selects either the deterministic mock or an `httpx` OpenAI-compatible implementation; `PlannerAgent` still validates and resolves every model response before persistence, approval, Runtime, and ToolGateway. Provider status and connection testing remain minimal, secret-free, and process-local.

**Tech Stack:** Python 3.13, FastAPI, Pydantic 2, httpx, SQLAlchemy, pytest, React 19, TypeScript, Vitest.

**Spec:** `docs/superpowers/specs/2026-08-23-real-llm-provider-design.md`

## Global Constraints

- Read `AGENTS.md`, `PROJECT_CONTEXT.md`, and the approved spec before implementation.
- Work only in `D:\AgentProjects\AgentForge`; mutable test/runtime data belongs under `D:\AgentProjectData\AgentForge`.
- Use the existing `backend/.venv`, `frontend/node_modules`, and `httpx`; install no dependency.
- Do not call a real external API in implementation or automated tests. Use `httpx.MockTransport`.
- Keep `MockLLMProvider` deterministic and selected only when configuration says `mock`; never silently fall back from `openai-compatible`.
- The Base URL comes only from process environment. Require HTTPS except for exact loopback hosts `localhost`, `127.0.0.1`, and `::1`; reject URL credentials, queries, and fragments; disable redirects.
- Use 30 seconds and 1200 output tokens as defaults, 64 KiB as the response-body limit, and the existing 20-step plan limit. Do not add temperature.
- Retry at most three total attempts. Retry only transient network errors, timeout, HTTP 408, 429, and 5xx, using 0.5 and 1.5 seconds; cap valid `Retry-After` at 5 seconds.
- Never persist or expose API keys, Authorization headers, raw prompts, raw upstream bodies, hidden reasoning, or raw upstream exceptions.
- Preserve the authority chain: Provider -> `PlanContract` -> `PlanValidator` -> `CapabilityRegistry` -> `CapabilityResolver` -> approval -> Runtime -> ToolGateway.
- Do not modify ToolGateway, Runtime execution semantics, approval persistence, or the database schema.
- Add backend Phase 12 coverage only to `backend/tests/test_phase_12_real_llm_provider.py`; do not create per-task test modules.
- During normal iteration run only the focused Phase 12 file. Run full backend/frontend verification only at major integration or final completion.
- Keep command output bounded: quiet test summary on success; on failure report failing names and roughly the final 20-40 relevant lines.

---

### Task 1: Provider contracts and validated environment configuration

**Files:**
- Create: `backend/tests/test_phase_12_real_llm_provider.py`
- Create: `backend/app/agents/providers/config.py`
- Modify: `backend/app/agents/providers/base.py`
- Modify: `backend/app/agents/providers/mock.py`
- Modify: `backend/app/agents/providers/__init__.py`

**Interfaces:**
- Consumes: existing `PlanContract`, Python `Mapping`, and process environment.
- Produces: `ProviderErrorCategory`, `ProviderError`, `LLMRequest`, `LLMResponse`, `LLMProvider`, `ProviderConfig`, `load_provider_config(environ=None)`, `build_provider(config, *, transport=None, sleeper=time.sleep)`, and an updated `MockLLMProvider`.

- [ ] **Step 1: Add focused RED tests for contracts, mock defaults, and configuration**

Create the single Phase 12 test file with a deterministic sentinel and tests shaped as follows:

```python
from dataclasses import FrozenInstanceError

import pytest

from app.agents.providers import (
    LLMRequest,
    MockLLMProvider,
    ProviderError,
    ProviderErrorCategory,
    load_provider_config,
)

SECRET = "PHASE12_TEST_SECRET_DO_NOT_LEAK"


def test_default_configuration_selects_mock():
    config = load_provider_config({})
    assert config.provider == "mock"
    assert config.timeout_seconds == 30.0
    assert config.max_output_tokens == 1200
    assert config.credential_configured is False


def test_real_configuration_is_validated_without_exposing_secret():
    config = load_provider_config({
        "AGENTFORGE_LLM_PROVIDER": "openai-compatible",
        "AGENTFORGE_LLM_BASE_URL": "https://llm.example.test/v1",
        "AGENTFORGE_LLM_MODEL": "example-model",
        "AGENTFORGE_LLM_API_KEY": SECRET,
    })
    assert config.configured is True
    assert config.credential_configured is True
    assert SECRET not in repr(config)
    with pytest.raises(FrozenInstanceError):
        config.model = "changed"


@pytest.mark.parametrize("url", [
    "http://localhost:9000/v1",
    "http://127.0.0.1:9000/v1",
    "http://[::1]:9000/v1",
    "https://10.0.0.8/v1",
])
def test_approved_base_urls(url):
    assert load_provider_config(real_env(url)).configured is True


@pytest.mark.parametrize("url", [
    "http://10.0.0.8/v1",
    "http://llm.example.test/v1",
    "https://user:password@llm.example.test/v1",
    "https://llm.example.test/v1?target=other",
    "https://llm.example.test/v1#fragment",
])
def test_rejected_base_urls(url):
    config = load_provider_config(real_env(url))
    assert config.configured is False
    with pytest.raises(ProviderError) as exc:
        build_provider(config)
    assert exc.value.category == ProviderErrorCategory.NOT_CONFIGURED
    assert SECRET not in str(exc.value)


def test_mock_provider_is_deterministic_and_network_free():
    provider = MockLLMProvider()
    request = LLMRequest(prompt="bounded", context={}, output_schema={})
    assert provider.generate_plan(request).payload == provider.generate_plan(request).payload
    assert provider.test_connection().payload == {"status": "ok"}
```

Define `real_env(url)` in the same test file to return only the six approved environment variables with the sentinel key. Add parameterized cases for unknown provider, missing model/key/Base URL, timeout outside 1-120 seconds, and output-token values outside 1-4096. Unknown provider names raise `NOT_CONFIGURED`; an explicitly selected but incomplete/invalid `openai-compatible` configuration returns a redacted `ProviderConfig` with `configured=False`, and `build_provider` raises `NOT_CONFIGURED`. Assert every public exception and `repr` excludes `SECRET`.

- [ ] **Step 2: Run the focused test and confirm RED**

Run from `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_phase_12_real_llm_provider.py -q
```

Expected: collection fails because the new contracts/configuration do not exist. Output should remain under roughly 40 lines.

- [ ] **Step 3: Implement immutable provider contracts in `base.py`**

Implement the minimum contract shape:

```python
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
    def __init__(self, category, *, retryable=False, safe_message="LLM provider request failed", attempt_count=1, duration_ms=0):
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
    def generate_plan(self, request: LLMRequest) -> LLMResponse: ...
    def test_connection(self) -> LLMResponse: ...
```

Keep safe messages constant or category-derived. Do not retain request objects, raw exceptions, headers, or bodies on `ProviderError`.

- [ ] **Step 4: Implement `ProviderConfig` and the single loader in `config.py`**

Use an immutable dataclass with a custom redacted `repr`, plus computed `configured` and `credential_configured` properties and a bounded internal safe validation reason. Parse only these keys:

```python
PROVIDER_ENV_KEYS = (
    "AGENTFORGE_LLM_PROVIDER",
    "AGENTFORGE_LLM_BASE_URL",
    "AGENTFORGE_LLM_MODEL",
    "AGENTFORGE_LLM_API_KEY",
    "AGENTFORGE_LLM_TIMEOUT_SECONDS",
    "AGENTFORGE_LLM_MAX_OUTPUT_TOKENS",
)
```

Validate URLs with `urllib.parse.urlsplit`. Accept HTTPS, or HTTP only when `hostname` is exactly one of the three loopback names. Reject username, password, query, fragment, unsupported schemes, empty host, and insecure private-network HTTP. Normalize by removing only trailing `/`; never resolve or accept the URL from request content. Enforce `1 <= timeout_seconds <= 120` and `1 <= max_output_tokens <= 4096`.

For `openai-compatible`, return a redacted configuration object even when required fields are incomplete or invalid, setting `configured=False` and retaining only a constant safe validation reason. This lets the status API report the selected real provider without re-reading environment variables. Unknown provider names remain a loader error because they cannot satisfy the status schema. Never retain an invalid URL with embedded credentials.

Declare `build_provider` in this module as the one composition boundary, using local imports to avoid cycles:

```python
def build_provider(config: ProviderConfig, *, transport=None, sleeper=time.sleep) -> LLMProvider:
    if config.provider == "mock":
        return MockLLMProvider()
    if not config.configured:
        raise ProviderError(ProviderErrorCategory.NOT_CONFIGURED, safe_message="Real LLM provider is not configured")
    return OpenAICompatibleProvider(config, transport=transport, sleeper=sleeper)
```

- [ ] **Step 5: Adapt `MockLLMProvider` and exports**

Return `LLMResponse(provider="mock", model="deterministic-mock", ...)` from `generate_plan`; keep the existing one-step `repository_state` payload and add a deterministic `test_connection` response `{ "status": "ok" }`. Export only the approved public contracts, config loader/factory, and implementations from `providers/__init__.py`.

- [ ] **Step 6: Run focused GREEN verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_phase_12_real_llm_provider.py -q
```

Expected: all Task 1 cases pass, no network access, no warning containing the sentinel, exit code 0.

- [ ] **Step 7: Commit the coherent checkpoint**

```powershell
git add backend/app/agents/providers/base.py backend/app/agents/providers/config.py backend/app/agents/providers/mock.py backend/app/agents/providers/__init__.py backend/tests/test_phase_12_real_llm_provider.py
git commit -m "feat: define llm provider configuration boundary"
```

---

### Task 2: OpenAI-compatible bounded transport, safe errors, and retry

**Files:**
- Create: `backend/app/agents/providers/openai_compatible.py`
- Modify: `backend/app/agents/providers/config.py`
- Modify: `backend/app/agents/providers/__init__.py`
- Test: `backend/tests/test_phase_12_real_llm_provider.py`

**Interfaces:**
- Consumes: `ProviderConfig`, `LLMRequest`, `LLMResponse`, `ProviderError`, `ProviderErrorCategory`, injected `httpx.BaseTransport`, and injected `Callable[[float], None]` sleeper.
- Produces: `OpenAICompatibleProvider.generate_plan(request)`, `OpenAICompatibleProvider.test_connection()`, exact retry/error behavior, and a 64 KiB streaming response guard.

- [ ] **Step 1: Add RED transport tests to the same Phase 12 file**

Use `httpx.MockTransport` and captured requests:

```python
def chat_response(content: dict, *, usage: dict | None = None):
    return httpx.Response(200, json={
        "choices": [{"message": {"content": json.dumps(content)}}],
        "usage": usage or {},
    })


def test_real_provider_sends_bounded_authenticated_structured_request():
    captured = {}
    def handler(request):
        captured["request"] = request
        return chat_response(valid_plan())
    provider = OpenAICompatibleProvider(real_config(), transport=httpx.MockTransport(handler), sleeper=lambda _: None)
    response = provider.generate_plan(plan_request())
    assert response.payload == valid_plan()
    assert captured["request"].url == "https://llm.example.test/v1/chat/completions"
    assert captured["request"].headers["authorization"] == f"Bearer {SECRET}"
    body = json.loads(captured["request"].content)
    assert body["model"] == "example-model"
    assert body["max_tokens"] == 1200
    assert body["response_format"]["type"] == "json_schema"
    assert "temperature" not in body


@pytest.mark.parametrize("status,category,attempts", [
    (401, ProviderErrorCategory.AUTHENTICATION_FAILED, 1),
    (403, ProviderErrorCategory.AUTHENTICATION_FAILED, 1),
    (408, ProviderErrorCategory.TIMEOUT, 3),
    (429, ProviderErrorCategory.RATE_LIMITED, 3),
    (500, ProviderErrorCategory.UPSTREAM_SERVER_ERROR, 3),
])
def test_status_mapping_and_retry_bounds(status, category, attempts):
    calls = 0
    def handler(_):
        nonlocal calls
        calls += 1
        return httpx.Response(status, text=SECRET, headers={"X-Debug": SECRET})
    provider = provider_with(handler)
    with pytest.raises(ProviderError) as exc:
        provider.generate_plan(plan_request())
    assert calls == attempts
    assert exc.value.category == category
    assert SECRET not in str(exc.value)
```

Add deterministic cases for `httpx.TimeoutException`, `httpx.ConnectError`, a non-retryable 400, malformed chat envelope, malformed content JSON, a 65,537-byte streamed body, numeric `Retry-After`, HTTP-date `Retry-After`, cap at 5 seconds, delays `[0.5, 1.5]`, token usage extraction, and redirects returned as non-retryable invalid responses. Assert malformed/schema-invalid content receives no transport retry.

- [ ] **Step 2: Run the focused test and confirm RED**

Run the Phase 12 test file with `-q`. Expected: import failure for `OpenAICompatibleProvider` or behavior failures; no real network call.

- [ ] **Step 3: Implement the bounded HTTP request path**

In `openai_compatible.py`, construct one `httpx.Client` with configured timeout, injected transport, and `follow_redirects=False`. Use a fixed endpoint and headers:

```python
headers = {
    "Authorization": f"Bearer {config.api_key}",
    "Content-Type": "application/json",
}
payload = {
    "model": config.model,
    "messages": [
        {"role": "system", "content": SYSTEM_BOUNDARY},
        {"role": "user", "content": request.prompt},
    ],
    "max_tokens": config.max_output_tokens,
    "response_format": {
        "type": "json_schema",
        "json_schema": {"name": "agentforge_plan", "strict": True, "schema": dict(request.output_schema)},
    },
}
```

Read with `client.stream`, sum bytes while iterating, and raise `RESPONSE_TOO_LARGE` immediately above `65_536`. Decode only after the bound passes. Require exactly a JSON object from `choices[0].message.content`; reject missing/alternate envelopes as `INVALID_RESPONSE`. Extract only non-negative integer token counts.

- [ ] **Step 4: Implement safe status mapping and bounded retry**

Keep retry in one private `_request_json` method. Map 401/403 to non-retryable authentication failure; 408 to timeout; 429 to rate limit; 5xx to upstream server error; other non-2xx to invalid response. Map timeout/connect/transport exceptions without interpolating the original exception.

Use attempt indices to select `[0.5, 1.5]`; parse `Retry-After` as either non-negative delta seconds or an HTTP date, cap at 5, and inject `sleeper` so tests never sleep. After attempt 3, raise the last safe error with `attempt_count=3` and total bounded duration.

- [ ] **Step 5: Implement the non-plan connection check**

`test_connection()` uses the same bounded transport and error handling but a fixed prompt, a fixed `{status: "ok"}` JSON schema, and a small hard-coded token budget no larger than 32. It contains no task, repository, workspace, or business content and returns `LLMResponse` only.

- [ ] **Step 6: Run focused GREEN verification**

Run the single Phase 12 test file. Expected: all transport/error/retry/body-size tests pass with no real sleep, no real DNS, and no sentinel in captured safe outputs.

- [ ] **Step 7: Commit the transport checkpoint**

```powershell
git add backend/app/agents/providers/openai_compatible.py backend/app/agents/providers/config.py backend/app/agents/providers/__init__.py backend/tests/test_phase_12_real_llm_provider.py
git commit -m "feat: add bounded openai compatible transport"
```

---

### Task 3: Structured PlanContract, bounded prompt, and Planner validation pipeline

**Files:**
- Modify: `backend/app/agents/planner/schemas.py`
- Modify: `backend/app/agents/planner/prompts.py`
- Modify: `backend/app/agents/planner/planner.py`
- Modify: `backend/app/agents/providers/mock.py`
- Test: `backend/tests/test_phase_12_real_llm_provider.py`

**Interfaces:**
- Consumes: `CapabilityRegistry.ids()`, `CapabilityDefinition` descriptions/parameter schema, `PlanContract.model_json_schema()`, `LLMProvider.generate_plan(LLMRequest)`, existing `PlanValidator`, and `CapabilityResolver`.
- Produces: backward-compatible optional `PlanContract.summary`, `build_planning_prompt(goal, capability_registry, context)`, and Provider -> local validation -> deterministic resolution integration.

- [ ] **Step 1: Add RED schema, prompt, and authority-chain tests to the same file**

Add tests that assert:

```python
def test_summary_is_bounded_and_old_v2_plan_remains_readable():
    old = PlanContract.model_validate({"schema_version": 2, "steps": [repository_step()]})
    assert old.summary == ""
    with pytest.raises(ValidationError):
        PlanContract.model_validate({"schema_version": 2, "summary": "x" * 501, "steps": [repository_step()]})


def test_prompt_contains_capabilities_not_tools_or_secrets():
    prompt = build_planning_prompt("Check release", build_default_capability_registry(), {"release": "2.0"})
    assert "repository_state" in prompt
    assert "profile" in prompt and "smoke" in prompt
    assert "git_read" not in prompt and "test_run" not in prompt
    assert SECRET not in prompt


@pytest.mark.parametrize("extra", [
    {"tool_id": "git_read"},
    {"command": "git status"},
    {"permission": "SAFE_READ"},
    {"approval": "APPROVED"},
    {"workspace": "C:/"},
])
def test_model_cannot_add_execution_authority(extra):
    payload = valid_plan()
    payload["steps"][0].update(extra)
    with pytest.raises(PlanValidationError):
        validator().validate(payload, REPO_ROOT)
```

Also cover unknown capability, unknown parameter, invalid profile, arbitrary command in a parameter, empty steps, 21 steps, and a valid multi-step response resolving to snapshots. Assert no approval, Runtime, or ToolGateway call occurs inside planning tests.

- [ ] **Step 2: Run focused RED verification**

Run the Phase 12 test file. Expected: summary/prompt/request-contract assertions fail while existing Phase 11.2 behavior remains untouched.

- [ ] **Step 3: Extend the existing plan schema only**

Add `summary: str = Field(default="", max_length=500)` to `PlanContract`; retain `extra="forbid"`, schema version 2, literal capability IDs, strict step fields, and the 1-20 step bound. Do not create a second provider plan model. Update mock output to include a stable concise summary while ensuring persisted old plans without it still parse.

- [ ] **Step 4: Build the prompt from the capability registry**

Change the prompt function to receive the registry and serialize only a bounded catalog such as:

```python
catalog = [
    {
        "capability_id": definition.id,
        "description": definition.description,
        "parameters": [
            {"name": field.name, "required": field.required, "allowed_values": list(field.allowed_values)}
            for field in definition.parameter_schema
        ],
    }
    for definition in sorted_definitions
]
```

Set `MAX_PLANNING_CONTEXT_BYTES = 4096`, measure compact UTF-8 JSON, and reject oversized/non-serializable context before provider invocation. Do not include candidate tool IDs, actions, permissions, registry fingerprints, executor internals, raw files, audit, or evidence. Explicitly instruct JSON-only capability requirements and prohibit concrete tools, commands, approval, permission, and workspace changes.

- [ ] **Step 5: Pass typed request/response through `PlannerAgent`**

Build `LLMRequest(prompt=..., context=bounded_context, output_schema=PlanContract.model_json_schema())`; call the provider; pass `dict(response.payload)` to the existing `PlanValidator`; then use the existing resolver loop. Persist only `plan.model_dump(mode="json")` plus `resolved_steps`. HTTP 200 alone must not bypass any local stage.

- [ ] **Step 6: Run focused GREEN verification**

Run the single Phase 12 test file. Expected: valid Provider -> `PlanValidator` -> resolver integration passes; every concrete-tool/command/unknown/oversized case fails before approval or execution.

- [ ] **Step 7: Commit the structured-planning checkpoint**

```powershell
git add backend/app/agents/planner/schemas.py backend/app/agents/planner/prompts.py backend/app/agents/planner/planner.py backend/app/agents/providers/mock.py backend/tests/test_phase_12_real_llm_provider.py
git commit -m "feat: validate provider generated capability plans"
```

---

### Task 4: Provider composition, Planning API, task failure, and safe audit

**Files:**
- Modify: `backend/app/agents/providers/config.py`
- Modify: `backend/app/agents/planner/planner.py`
- Modify: `backend/app/api/routes/planning.py`
- Test: `backend/tests/test_phase_12_real_llm_provider.py`

**Interfaces:**
- Consumes: `load_provider_config`, `build_provider`, FastAPI dependency injection, `ProviderError`, `LLMResponse`, `TaskService.transition_task`, and existing `AuditEventRecord`.
- Produces: `get_llm_provider()` as the only route composition dependency, safe Planning API error mapping, `LLM_PLAN_REQUESTED/SUCCEEDED/FAILED`, and guaranteed `PLANNING -> FAILED` on planning failure.

- [ ] **Step 1: Add RED composition, API, audit, and state tests to the same file**

Use monkeypatched environment and FastAPI dependency overrides. Include:

```python
def test_planning_api_uses_selected_provider_without_silent_fallback(client, monkeypatch):
    set_real_environment(monkeypatch, api_key=SECRET)
    failing = FakeProvider(error=ProviderError(ProviderErrorCategory.NETWORK_ERROR, safe_message="Provider unavailable"))
    app.dependency_overrides[get_llm_provider] = lambda: failing
    task_id = create_task(client)
    response = client.post(f"/tasks/{task_id}/plan", json={})
    assert response.status_code == 502
    assert response.json()["detail"] == "LLM planning failed: NETWORK_ERROR"
    assert isinstance(failing, FakeProvider)
    assert SECRET not in response.text


def test_failed_provider_marks_task_failed_and_audits_safe_metadata(db_session):
    task = create_domain_task(db_session)
    provider = FakeProvider(error=ProviderError(ProviderErrorCategory.TIMEOUT, attempt_count=3, duration_ms=1234))
    with pytest.raises(ProviderError):
        PlannerAgent(db_session, provider, REPO_ROOT).create_plan(task.id)
    assert TaskService(db_session).get_task(task.id).status == TaskStatus.FAILED
    events = audit_payloads(db_session, task.id)
    assert "LLM_PLAN_REQUESTED" in events
    assert "LLM_PLAN_FAILED" in events
    assert SECRET not in json.dumps(events)
```

Add successful audit assertions for provider/model/duration/attempt/token usage/validation outcome, invalid PlanContract and resolver failures entering `FAILED`, zero approval/tool execution records, incomplete real config returning `NOT_CONFIGURED` with no mock call, and no API/audit/log/repr/traceback serialization containing the sentinel.

- [ ] **Step 2: Run focused RED verification**

Run the Phase 12 file. Expected: dependency and audit/state assertions fail; output is bounded.

- [ ] **Step 3: Add the single route composition dependency**

In `planning.py`, define and use exactly one dependency:

```python
def get_llm_provider() -> LLMProvider:
    return build_provider(load_provider_config())


def create_plan(..., provider: LLMProvider = Depends(get_llm_provider)):
    plan = PlannerAgent(db, provider, workspace_root).create_plan(...)
```

Do not put provider-selection `if` statements in route handlers. Map `NOT_CONFIGURED` to HTTP 503 and upstream provider failures to a bounded 502/504/429 policy chosen once in a small helper. Client detail contains only `LLM planning failed: <CATEGORY>`.

- [ ] **Step 4: Add safe Planner audit and one failure boundary**

Before provider invocation, add `LLM_PLAN_REQUESTED` with provider/model only. After provider return and all local validation/resolution succeeds, add `LLM_PLAN_SUCCEEDED` with duration, attempts, optional token integers, and `validation_outcome="VALID"`.

Wrap provider call, `PlanContract`, `PlanValidator`, and capability resolution in one planning failure boundary. On failure:

1. roll back any uncommitted partial plan/resolution records;
2. add bounded `LLM_PLAN_FAILED` metadata with safe provider category or `INVALID_RESPONSE` plus the local validation stage;
3. transition the existing task from `PLANNING` to `FAILED` using `TaskService`;
4. re-raise a safe typed error for the route;
5. create no approval, Runtime call, ToolGateway call, or valid plan.

Use existing `PlanRepository.flush` behavior so a failed resolution never commits a partial plan. Do not add a state or table.

- [ ] **Step 5: Run focused GREEN and one major integration regression**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_phase_12_real_llm_provider.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_api.py tests/test_planner.py tests/test_phase_11_2_capability_tool_selection.py -q
```

Expected: all focused Phase 12 and adjacent Planner/API/Phase 11.2 tests pass. Report only counts and failing names if any.

- [ ] **Step 6: Commit the planning-integration checkpoint**

```powershell
git add backend/app/agents/providers/config.py backend/app/agents/planner/planner.py backend/app/api/routes/planning.py backend/tests/test_phase_12_real_llm_provider.py
git commit -m "feat: compose governed llm planning"
```

---

### Task 5: Minimal provider status and explicit connection-test API

**Files:**
- Create: `backend/app/schemas/provider.py`
- Create: `backend/app/api/routes/providers.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_phase_12_real_llm_provider.py`

**Interfaces:**
- Consumes: `load_provider_config`, `build_provider`, `LLMProvider.test_connection()`, existing FastAPI router conventions, and the safe Provider error taxonomy.
- Produces: `GET /llm/provider`, `POST /llm/provider/test`, `ProviderStatusRead`, and process-local `ConnectionState` guarded by a lock.

- [ ] **Step 1: Add RED status and connection tests to the same backend file**

Add API tests with dependency override/mocked transport:

```python
def test_provider_status_exposes_no_credential_material(client, monkeypatch):
    set_real_environment(monkeypatch, api_key=SECRET)
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


def test_connection_test_is_explicit_bounded_and_non_executable(client):
    fake = FakeProvider(connection_response=LLMResponse(
        payload={"status": "ok"}, provider="openai-compatible", model="example-model",
        duration_ms=12, attempt_count=1,
    ))
    app.dependency_overrides[get_status_provider] = lambda: fake
    before = database_counts()
    response = client.post("/llm/provider/test")
    assert response.json()["connection_status"] == "success"
    assert fake.connection_calls == 1 and fake.plan_calls == 0
    assert database_counts() == before
```

Add failure-category, missing-config, repeated GET not triggering a connection, restart/reset semantics via store reset fixture, no key fragments, no Base URL field, no raw body, and no task/plan/approval/execution/audit writes.

- [ ] **Step 2: Run focused RED verification**

Run the Phase 12 file. Expected: route/schema imports or 404 assertions fail.

- [ ] **Step 3: Implement the read-only schema and process-local store**

Define:

```python
class ProviderStatusRead(BaseModel):
    provider: Literal["mock", "openai-compatible"]
    configured: bool
    model: str
    credential_configured: bool
    connection_status: Literal["not tested", "success", "failed"]
    failure_category: ProviderErrorCategory | None
```

Keep a module-local `ConnectionState` plus `threading.Lock`; it contains only status, safe category, duration, and timestamp internally. It resets at process import/start and never enters SQLite.

- [ ] **Step 4: Implement minimal routes with an injectable provider dependency**

`GET /llm/provider` uses the same redacted `ProviderConfig` produced by `load_provider_config` and never parses environment variables in the route. Invalid selected-real configuration returns HTTP 200 with `configured=false`, `credential_configured` based only on presence, `connection_status="failed"`, and `failure_category="NOT_CONFIGURED"`; it does not fall back. An unknown provider name remains a safe HTTP 503 configuration error rather than being mislabeled as mock.

`POST /llm/provider/test` explicitly calls `test_connection`, updates the process-local store, and returns the safe status. It maps typed errors without raw body/header/exception data. Register the router in `main.py`. Do not add CORS methods beyond existing GET/POST support or accept a request body containing Base URL/key/model.

- [ ] **Step 5: Run focused GREEN verification**

Run the Phase 12 file. Expected: status and mocked connection tests pass, database counts remain unchanged, and no network access occurs.

- [ ] **Step 6: Commit the operator API checkpoint**

```powershell
git add backend/app/schemas/provider.py backend/app/api/routes/providers.py backend/app/main.py backend/tests/test_phase_12_real_llm_provider.py
git commit -m "feat: expose safe llm provider status"
```

---

### Task 6: Minimal frontend provider-status surface

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/hooks/useOperations.ts`
- Modify: `frontend/src/pages/Dashboard.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/styles/app.css`

**Interfaces:**
- Consumes: backend `ProviderStatusRead`, existing `request<T>`, `useOperations`, Dashboard panel styles, and Vitest fetch stubs.
- Produces: `ProviderStatus` TypeScript type, `api.getProviderStatus()`, `api.testProviderConnection()`, provider state/actions in `useOperations`, and one small Dashboard status panel.

- [ ] **Step 1: Add RED frontend tests to the existing `App.test.tsx`**

Keep frontend coverage in the existing test structure:

```tsx
it('shows safe LLM provider status without a secret editor', async () => {
  mockBackend({ provider: {
    provider: 'openai-compatible', configured: true, model: 'example-model',
    credential_configured: true, connection_status: 'not tested', failure_category: null,
  } })
  render(<App />)
  expect(await screen.findByText('LLM Provider')).toBeInTheDocument()
  expect(screen.getByText('OpenAI-compatible')).toBeInTheDocument()
  expect(screen.getByText('example-model')).toBeInTheDocument()
  expect(screen.getByText('Credential configured')).toBeInTheDocument()
  expect(screen.queryByLabelText(/api key/i)).not.toBeInTheDocument()
})


it('tests provider connection only after an explicit click', async () => {
  const fetchMock = mockBackend({ provider: mockProviderStatus, connection: successProviderStatus })
  render(<App />)
  expect(fetchMock).not.toHaveBeenCalledWith(expect.stringContaining('/llm/provider/test'), expect.anything())
  fireEvent.click(await screen.findByRole('button', { name: 'Test Connection' }))
  expect(await screen.findByText('Connection success')).toBeInTheDocument()
})
```

Update the bounded fetch helper in the test file so existing task endpoints and provider endpoints receive deterministic responses. Assert no API key input, Base URL editor, CRUD controls, raw response view, chat UI, billing view, or prompt playground appears.

- [ ] **Step 2: Run frontend RED verification**

Run from `frontend`:

```powershell
npm test -- --run
```

Expected: only the new provider UI assertions fail; existing tests remain readable and output stays bounded.

- [ ] **Step 3: Add types, client calls, and hook state**

Add:

```typescript
export type ProviderStatus = {
  provider: 'mock' | 'openai-compatible'
  configured: boolean
  model: string
  credential_configured: boolean
  connection_status: 'not tested' | 'success' | 'failed'
  failure_category: string | null
}
```

Add `getProviderStatus` and POST-only `testProviderConnection` to the API client. In `useOperations`, fetch status with the existing refresh, retain a safe mock/not-tested preview when the backend is unavailable, and expose `providerStatus`, `testingProvider`, and `testProviderConnection`. Do not store a key, Base URL, headers, or raw errors in React state.

- [ ] **Step 4: Add one Dashboard panel**

Add a compact `LLM Provider` panel using existing `panel`, `PanelTitle`, button, and status styling. Show only provider display name, configured yes/no, model, credential configured/missing, connection state, and safe failure category. Disable the button while testing. Add only small responsive CSS rules; do not add navigation or a settings page.

- [ ] **Step 5: Run frontend GREEN verification and build**

Run:

```powershell
npm test -- --run
npm run build
```

Expected: all frontend tests pass and TypeScript/Vite production build exits 0. Report test count and build status only.

- [ ] **Step 6: Commit the frontend checkpoint**

```powershell
git add frontend/src/types/index.ts frontend/src/api/client.ts frontend/src/hooks/useOperations.ts frontend/src/pages/Dashboard.tsx frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/styles/app.css
git commit -m "feat: show llm provider status"
```

---

### Task 7: Security proof, final regression, documentation, and hygiene

**Files:**
- Modify: `backend/tests/test_phase_12_real_llm_provider.py`
- Modify: `.env.example`
- Modify: `PROJECT_CONTEXT.md`
- Modify: `README.md`
- Modify: `docs/deployment/README.md`
- Modify only if needed for a discovered defect: Phase 12 production files from Tasks 1-6

**Interfaces:**
- Consumes: the complete Phase 12 implementation, approved spec, existing launcher/deployment conventions, and all repository test/build commands.
- Produces: final cross-boundary security evidence, operator instructions, complete regression evidence, and a clean source tree.

- [ ] **Step 1: Add final RED security assertions to the same backend feature file**

Add one end-to-end mocked real-provider test with `SECRET` present in the configured key, upstream body, and upstream header. Serialize all bounded observable surfaces:

```python
observable = json.dumps({
    "api": planning_response.text,
    "status": status_response.text,
    "audit": [event.payload_summary for event in audit_events],
    "errors": captured_safe_errors,
    "logs": caplog.text,
    "provider_repr": repr(provider),
    "config_repr": repr(config),
})
assert SECRET not in observable
assert db_session.query(ApprovalRecord).filter_by(task_id=task.id).count() == 0
assert db_session.query(ToolExecutionRecord).filter_by(task_id=task.id).count() == 0
```

Add explicit assertions that a successful mocked real-provider plan reaches `WAITING_APPROVAL` with resolver-produced snapshots, while no Runtime or ToolGateway execution exists before approval. Inspect SQLite schema in the test and assert no provider/credential/configuration table was added.

- [ ] **Step 2: Run focused RED, make only evidence-driven fixes, then rerun GREEN**

Run the Phase 12 file. If a test fails, use `superpowers:systematic-debugging`, identify the leaking or bypassing boundary, make the minimum fix in the owning Phase 12 file, and rerun. Expected final result: all Phase 12 tests pass with no sentinel leakage and no network call.

- [ ] **Step 3: Document environment-only operation without secrets**

Update `.env.example` with blank values and safe comments for exactly the six approved variables. Update `README.md` and `docs/deployment/README.md` with:

```text
Mock:
  AGENTFORGE_LLM_PROVIDER=mock

Real provider:
  AGENTFORGE_LLM_PROVIDER=openai-compatible
  AGENTFORGE_LLM_BASE_URL=https://provider.example/v1
  AGENTFORGE_LLM_MODEL=<operator-selected-model>
  AGENTFORGE_LLM_API_KEY=<inject through service environment; never commit>
```

Explain HTTPS/non-local and loopback-HTTP rules, explicit connection testing, no silent fallback, how to explicitly return to mock, and that goals/capability catalogs are sent but keys, raw repository dumps, audit history, raw responses, and execution authority are not stored or sent. Do not include a plausible real key.

Update `PROJECT_CONTEXT.md` with Phase 12 architecture, completed scope, security decisions, test strategy, and remaining out-of-scope items. Do not claim completion until final verification passes.

- [ ] **Step 4: Run final bounded verification**

Run from `backend`, redirecting full output to a D-drive temporary log only if output becomes large:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_phase_12_real_llm_provider.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

Then from `frontend`:

```powershell
npm test -- --run
npm run build
```

Then from repository root:

```powershell
git diff --check
git status --short
```

Expected: Phase 12 tests pass; full backend regression passes; frontend tests and production build pass; diff check is clean; status contains only intentional Phase 12 source, test, frontend, and documentation changes. Report command, exit code, passed/failed count, failing names, and a short reason only.

- [ ] **Step 5: Perform final security and repository-hygiene review**

Use bounded searches:

```powershell
rg -n --hidden --glob '!backend/.venv/**' --glob '!frontend/node_modules/**' "PHASE12_TEST_SECRET_DO_NOT_LEAK|AGENTFORGE_LLM_API_KEY=.*[^=\s]" . | Select-Object -First 20
git diff --name-only
git status --short
```

Expected: the sentinel appears only as a test fixture/assertion, no populated key appears, no SQLite/runtime/log/temp/debug file is tracked, no dependency manifest changed, no ToolGateway/Runtime/approval persistence/database migration file changed, and no unnecessary top-level directory exists.

- [ ] **Step 6: Request one focused review near completion**

Use `superpowers:requesting-code-review` once for the complete Phase 12 diff. Review against the approved spec and this plan, emphasizing provider authority, SSRF controls, secret redaction, retry bounds, validation order, task failure state, no schema change, and no silent fallback. Apply review feedback only through `superpowers:receiving-code-review` with fresh verification.

- [ ] **Step 7: Commit final tests and operating documentation**

```powershell
git add .env.example PROJECT_CONTEXT.md README.md docs/deployment/README.md backend/tests/test_phase_12_real_llm_provider.py
git add backend/app/agents/providers/base.py backend/app/agents/providers/config.py backend/app/agents/providers/mock.py backend/app/agents/providers/openai_compatible.py backend/app/agents/providers/__init__.py
git add backend/app/agents/planner/schemas.py backend/app/agents/planner/prompts.py backend/app/agents/planner/planner.py backend/app/api/routes/planning.py backend/app/api/routes/providers.py backend/app/schemas/provider.py backend/app/main.py
git add frontend/src/types/index.ts frontend/src/api/client.ts frontend/src/hooks/useOperations.ts frontend/src/pages/Dashboard.tsx frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/styles/app.css
git status --short
git commit -m "docs: complete real llm provider phase"
```

Before committing, inspect the staged names and omit any unrelated file. Do not push. After commit, rerun `git status --short` and require a clean working tree before reporting Phase 12 complete.

## Execution Notes

- Preferred mode: `superpowers:executing-plans` in one active stream with a checkpoint after each task.
- No parallel subagents or per-task implementer/reviewer pairs.
- Use TDD in every task: add focused RED coverage to the same Phase 12 file, observe the expected failure, implement minimally, and rerun focused GREEN coverage.
- Use `superpowers:systematic-debugging` for any unexpected failure and `superpowers:verification-before-completion` before success claims or commits.
- Full regression frequency: at Task 4 major integration if necessary and once in Task 7 before completion; not after every task.
- No implementation step may use a real API key or real external endpoint. A separately authorized post-implementation operator smoke test would be a different task.
