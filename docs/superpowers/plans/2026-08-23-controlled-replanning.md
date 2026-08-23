# Controlled Re-planning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bounded, application-authorized re-planning that creates an immutable capability-first successor plan, requires a fresh approval, and resumes only through the existing Runtime and ToolGateway boundaries.

**Architecture:** Extend the existing structured observation and runtime-decision vocabulary, then add a focused `agents/replanning` package for deterministic policy, bounded prompt/proposal contracts, canonical loop guards, and successor-plan orchestration. Reuse the Phase 12 provider transport, PlanValidator, CapabilityResolver, PlanRecord versioning, ApprovalService snapshots, audit infrastructure, and AgentRuntime; do not add a database schema, persistent `REPLANNING` state, provider subsystem, or frontend feature.

**Tech Stack:** Python 3, FastAPI application services, Pydantic v2, SQLAlchemy, SQLite, existing `httpx` provider transport, pytest.

**Spec:** `docs/superpowers/specs/2026-08-23-controlled-replanning-design.md`

## Global Constraints

- Every newly created replanned Plan Version requires a fresh human approval; no Plan v1 approval may authorize Plan v2, including safe-read-only revisions.
- Runtime decisions are exactly `CONTINUE`, `COMPLETE`, `FAIL`, and `REPLAN`.
- The application owns replan authorization, budgets, validation, canonical comparison, capability resolution, approval, and execution permission.
- The LLM proposes only a summary and capability-first remaining steps; extra fields, concrete tools, commands, permissions, approvals, and workspace overrides are rejected.
- Maximum replans per task is 2; maximum total attempted/proposed steps across versions is 12; one proposal has at most `min(10, remaining_budget)` steps.
- Replan context is at most 8 KiB; the complete prompt is at most 12 KiB; one accepted REPLAN decision causes one provider call, using the existing maximum of 3 transient attempts.
- Observation summaries are at most 2,000 characters; at most 5 evidence references/summaries are included; each prompt-facing step/evidence summary is at most 500 characters; replan audit payloads are at most 8 KiB.
- A configured real-provider failure never falls back to Mock. Automated tests make no real network calls.
- No database schema change, migration, new persistent task status, dependency, ToolGateway change, or large frontend expansion.
- Keep all Phase 13 coverage in `backend/tests/test_phase_13_controlled_replanning.py` where practical. Use focused tests during development and one full regression near completion.

## File and Interface Map

**Create:**

- `backend/app/agents/replanning/__init__.py` — public exports only.
- `backend/app/agents/replanning/models.py` — immutable context, proposal, policy input/result, lineage, outcome, and bounded summary types.
- `backend/app/agents/replanning/policy.py` — deterministic authorization, canonical plan fingerprinting, progress fingerprinting, and loop limits.
- `backend/app/agents/replanning/prompts.py` — capability-only replan prompt and byte guards.
- `backend/app/agents/replanning/service.py` — provider call, untrusted validation, stale/budget checks, resolution, immutable persistence, fresh approval, recovery query, and bounded audit.
- `backend/tests/test_phase_13_controlled_replanning.py` — the single coherent Phase 13 feature suite.

**Modify:**

- `backend/app/agent_runtime/state.py` — add `REPLAN` and successor identifiers in the runtime result path only where needed.
- `backend/app/agent_runtime/observer.py` — evolve the existing observation contract and deterministic reason mapping.
- `backend/app/agent_runtime/runtime.py` — stop old-plan iteration on REPLAN and delegate to `ReplanningService`.
- `backend/app/agent_runtime/__init__.py` — export the evolved contracts.
- `backend/app/agents/providers/base.py` — add `generate_replan(request: LLMRequest) -> LLMResponse` to the protocol.
- `backend/app/agents/providers/mock.py` — deterministic capability-only replan response.
- `backend/app/agents/providers/openai_compatible.py` — route replan requests through the existing bounded `_complete()` transport.
- `backend/app/capabilities/resolver.py` — expose canonical normalized request data without exposing tool selection to the LLM.
- `backend/app/services/plan_repository.py` — explicit current/highest-version lookup used by stale checks.
- `backend/app/approvals/service.py` — permit a RUNNING task to request approval for a validated successor while preserving exact snapshot binding.
- `backend/app/domain/states/task_state.py` — allow only `RUNNING -> WAITING_APPROVAL`; add no new status.
- `PROJECT_CONTEXT.md`, `README.md`, and `docs/deployment/README.md` — document Phase 13 operation and bounds after implementation passes.

No frontend, storage ORM, migration, ToolGateway, package manifest, or lockfile change is planned.

---

### Task 1: Structured Observation and Runtime Decision Contracts

**Files:**

- Create: `backend/tests/test_phase_13_controlled_replanning.py`
- Modify: `backend/app/agent_runtime/state.py`
- Modify: `backend/app/agent_runtime/observer.py`
- Modify: `backend/app/agent_runtime/__init__.py`

**Interfaces:**

- Consumes: `ResolvedExecutionSnapshot`, `ToolExecutionResult`, existing `RuntimeState`.
- Produces: `RuntimeDecision.REPLAN`; `ObservationReason`; immutable `RuntimeObservation`; `RuntimeObserver.observe(*, snapshot, result, remaining_steps) -> RuntimeObservation`.

- [ ] **Step 1: Add RED contract and semantic tests to the single Phase 13 file**

Add tests with these exact assertions:

```python
from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest

from app.agent_runtime.observer import ObservationReason, RuntimeObserver
from app.agent_runtime.state import RuntimeDecision


def test_runtime_decision_vocabulary_is_exact():
    assert {item.value for item in RuntimeDecision} == {
        "CONTINUE", "COMPLETE", "FAIL", "REPLAN"
    }


def test_failed_test_with_evidence_is_replan_candidate(resolved_test_snapshot):
    result = tool_result(
        status="FAILED",
        summary="unit profile failed",
        evidence_id="evidence-test-failure",
    )
    observation = RuntimeObserver().observe(
        snapshot=resolved_test_snapshot, result=result, remaining_steps=0
    )
    assert observation.reason_code == ObservationReason.TEST_FAILED_DIAGNOSTIC_AVAILABLE
    assert observation.replan_recommended is True
    assert observation.decision == RuntimeDecision.REPLAN
    assert observation.evidence_refs == ("evidence-test-failure",)
    assert len(observation.result_summary) <= 2_000
    assert isinstance(observation.created_at, datetime)
    with pytest.raises(FrozenInstanceError):
        observation.status = "SUCCESS"


def test_failure_without_diagnostic_evidence_is_fail(resolved_test_snapshot):
    observation = RuntimeObserver().observe(
        snapshot=resolved_test_snapshot,
        result=tool_result(status="FAILED", summary="failed", evidence_id=None),
        remaining_steps=0,
    )
    assert observation.decision == RuntimeDecision.FAIL
    assert observation.reason_code == ObservationReason.NON_REPLANNABLE_TOOL_FAILURE
    assert observation.replan_recommended is False


def test_success_semantics_remain_continue_then_complete(resolved_repo_snapshot):
    result = tool_result(status="SUCCESS", summary="clean")
    continuing = RuntimeObserver().observe(
        snapshot=resolved_repo_snapshot, result=result, remaining_steps=1
    )
    complete = RuntimeObserver().observe(
        snapshot=resolved_repo_snapshot, result=result, remaining_steps=0
    )
    assert continuing.decision == RuntimeDecision.CONTINUE
    assert complete.decision == RuntimeDecision.COMPLETE
```

Define local helpers and fixtures in this same file using existing Phase 11.2 test patterns; do not create shared Phase 13 fixture modules.

- [ ] **Step 2: Run the focused RED slice**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase_13_controlled_replanning.py -q
```

Expected bounded output: 4 failures caused by missing `REPLAN`, `ObservationReason`, and evolved fields; no traceback beyond the relevant final 20–40 lines.

- [ ] **Step 3: Implement the minimum immutable observation evolution**

Use these names and bounds:

```python
class RuntimeDecision(StrEnum):
    CONTINUE = "CONTINUE"
    COMPLETE = "COMPLETE"
    FAIL = "FAIL"
    REPLAN = "REPLAN"


class ObservationReason(StrEnum):
    STEP_SUCCEEDED = "STEP_SUCCEEDED"
    TEST_FAILED_DIAGNOSTIC_AVAILABLE = "TEST_FAILED_DIAGNOSTIC_AVAILABLE"
    NON_REPLANNABLE_TOOL_FAILURE = "NON_REPLANNABLE_TOOL_FAILURE"
    POLICY_DENIED = "POLICY_DENIED"
    INVALID_RESULT = "INVALID_RESULT"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


@dataclass(frozen=True, slots=True)
class RuntimeObservation:
    observation_id: str
    step_id: str
    execution_id: str
    capability_id: str
    tool_id: str
    status: str
    result_summary: str
    evidence_refs: tuple[str, ...]
    reason_code: ObservationReason
    retryable: bool
    replan_recommended: bool
    created_at: datetime
    decision: RuntimeDecision
```

Map only failed `test_verification` results with a non-empty `evidence_id` to `REPLAN`. All other failed results remain `FAIL`. Preserve current success behavior. Truncate summaries to 2,000 characters and evidence IDs to the first five non-empty values.

- [ ] **Step 4: Run the Phase 13 file and adjacent runtime tests**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase_13_controlled_replanning.py backend/tests/test_agent_runtime.py -q
```

Expected: all selected tests pass using the existing `backend/tests/test_agent_runtime.py`; do not create a replacement package.

- [ ] **Step 5: Keep this task uncommitted until Task 2**

Task 1 and Task 2 form the first coherent commit: observation plus the application-owned authorization policy.

---

### Task 2: ReplanPolicy, Canonical Fingerprints, and Loop Safety

**Files:**

- Create: `backend/app/agents/replanning/__init__.py`
- Create: `backend/app/agents/replanning/models.py`
- Create: `backend/app/agents/replanning/policy.py`
- Modify: `backend/app/capabilities/resolver.py`
- Test: `backend/tests/test_phase_13_controlled_replanning.py`

**Interfaces:**

- Consumes: `RuntimeObservation`, `TaskStatus`, `CapabilityRequest`, resolver-normalized parameters.
- Produces: `StepSummary`; `ReplanPolicyInput`; `ReplanPolicyResult`; `ReplanPolicy.evaluate(value: ReplanPolicyInput) -> ReplanPolicyResult`; `canonical_plan_fingerprint(requests: Sequence[CapabilityRequest], resolver: CapabilityResolver) -> str`; `progress_fingerprint(completed_steps: Sequence[StepSummary], reason_code: ObservationReason, evidence_keys: Sequence[str], current_plan_fingerprint: str) -> str`; public `CapabilityResolver.normalize(request: CapabilityRequest) -> tuple[tuple[str, str], ...]`.

- [ ] **Step 1: Add RED tests for policy authority and exact budgets**

Add parameterized tests that construct `ReplanPolicyInput` directly:

```python
@pytest.mark.parametrize(
    ("override", "expected_reason"),
    [
        ({"task_status": TaskStatus.CANCELLED}, ObservationReason.POLICY_DENIED),
        ({"replan_count": 2}, ObservationReason.BUDGET_EXHAUSTED),
        ({"total_steps": 12}, ObservationReason.BUDGET_EXHAUSTED),
        ({"observation": malformed_observation()}, ObservationReason.INVALID_RESULT),
    ],
)
def test_replan_policy_fails_closed(policy_input, override, expected_reason):
    result = ReplanPolicy().evaluate(replace(policy_input, **override))
    assert result.decision == RuntimeDecision.FAIL
    assert result.reason_code == expected_reason


def test_replan_policy_authorizes_only_bounded_diagnostic_case(policy_input):
    result = ReplanPolicy().evaluate(policy_input)
    assert result.decision == RuntimeDecision.REPLAN
    assert result.remaining_replans == 1
    assert result.remaining_steps == 10
```

Add canonical tests proving generated step IDs and mapping key order do not affect SHA-256, while capability, normalized parameter, or step order changes do. Assert exactly 64 lowercase hexadecimal characters.

Add no-progress tests for:

- proposal fingerprint equal to current remaining plan;
- proposal fingerprint already in prior replan fingerprints;
- unchanged progress fingerprint;
- the same canonical capability request plus reason failed twice.

Each returns `FAIL` with `POLICY_DENIED` or `BUDGET_EXHAUSTED`; none invokes a provider.

- [ ] **Step 2: Run the new RED policy slice**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase_13_controlled_replanning.py -q -k "policy or fingerprint or progress or budget"
```

Expected: failures for missing replanning models/policy and public resolver normalization.

- [ ] **Step 3: Implement immutable policy models and bounds**

Define the exact core types in `models.py`:

```python
MAX_REPLANS = 2
MAX_TOTAL_STEPS = 12
MAX_PROPOSAL_STEPS = 10
MAX_CONTEXT_BYTES = 8 * 1024
MAX_PROMPT_BYTES = 12 * 1024


@dataclass(frozen=True, slots=True)
class StepSummary:
    capability_id: str
    parameters: Mapping[str, str]
    status: str
    reason_code: str
    summary: str
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReplanPolicyInput:
    task_status: TaskStatus
    observation: RuntimeObservation
    current_plan_id: str
    current_plan_version: int
    replan_count: int
    total_steps: int
    current_plan_fingerprint: str
    previous_plan_fingerprints: tuple[str, ...]
    current_progress_fingerprint: str
    previous_progress_fingerprint: str | None
    repeated_failure_count: int


@dataclass(frozen=True, slots=True)
class ReplanPolicyResult:
    decision: RuntimeDecision
    reason_code: ObservationReason
    summary: str
    remaining_replans: int
    remaining_steps: int
```

`ReplanPolicy.evaluate()` checks cancellation/malformed input first, then the closed reason/evidence requirement, then budgets and repeated progress. It never reads provider output and never calls an LLM.

- [ ] **Step 4: Implement deterministic canonicalization without exposing tools**

Add public resolver normalization:

```python
def normalize(self, request: CapabilityRequest) -> tuple[tuple[str, str], ...]:
    capability = self.capabilities.require(request.capability_id)
    return self._normalize(capability, request.parameters)
```

In `policy.py`, canonicalize ordered capability IDs and normalized parameters with:

```python
payload = [
    {"capability_id": request.capability_id, "parameters": dict(resolver.normalize(request))}
    for request in requests
]
encoded = json.dumps(
    payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
).encode("utf-8")
return hashlib.sha256(encoded).hexdigest()
```

Exclude step IDs and prose. Build `progress_fingerprint()` from bounded completed summaries, reason code, stable evidence IDs/content hashes, and current-plan fingerprint using the same canonical JSON rule.

- [ ] **Step 5: Run focused and adjacent resolver tests**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase_13_controlled_replanning.py backend/tests/test_phase_11_2_capability_tool_selection.py -q
```

Expected: all selected tests pass; no network and no database schema activity.

- [ ] **Step 6: Commit observation and policy safety**

```powershell
git add backend/app/agent_runtime/state.py backend/app/agent_runtime/observer.py backend/app/agent_runtime/__init__.py backend/app/agents/replanning/__init__.py backend/app/agents/replanning/models.py backend/app/agents/replanning/policy.py backend/app/capabilities/resolver.py backend/tests/test_phase_13_controlled_replanning.py
git commit -m "feat: add bounded replan policy"
```

---

### Task 3: Replanner Contract and Existing Provider Integration

**Files:**

- Create: `backend/app/agents/replanning/prompts.py`
- Modify: `backend/app/agents/replanning/models.py`
- Modify: `backend/app/agents/providers/base.py`
- Modify: `backend/app/agents/providers/mock.py`
- Modify: `backend/app/agents/providers/openai_compatible.py`
- Test: `backend/tests/test_phase_13_controlled_replanning.py`

**Interfaces:**

- Consumes: existing `LLMRequest`, `LLMResponse`, `CapabilityPlanStep`, `CapabilityRegistry`, provider transport bounds.
- Produces: Pydantic `ReplanProposal`; immutable `ReplanContext`; `build_replan_prompt(context, registry) -> str`; `LLMProvider.generate_replan(request) -> LLMResponse`.

- [ ] **Step 1: Add RED schema, authority, and byte-bound tests**

Define tests that validate the exact accepted payload:

```python
proposal = ReplanProposal.model_validate({
    "decision_summary": "Inspect bounded project metadata after test failure.",
    "revised_remaining_steps": [{
        "step_id": "replan-1-step-1",
        "capability_id": "project_metadata",
        "parameters": {"relative_path": "PROJECT_CONTEXT.md"},
    }],
})
assert proposal.revised_remaining_steps[0].capability_id == "project_metadata"
```

Parameterize rejected fields at both proposal and step levels: `tool_id`, `tool`, `action`, `command`, `permission`, `approval`, `workspace`, and unknown capability. Assert Pydantic validation fails before resolution.

Add tests proving:

- context JSON at 8,192 bytes is accepted and 8,193 bytes fails before provider invocation;
- complete prompt never exceeds 12,288 bytes and an oversize generated prompt fails;
- no prompt contains a sentinel API key, Authorization header, raw audit history, ToolGateway internals, or concrete tool IDs;
- only 12 step summaries and 5 evidence summaries survive context construction, each truncated to 500 characters.

- [ ] **Step 2: Add RED provider-contract tests with mocked transport only**

Test deterministic Mock output and capture the OpenAI-compatible request with `httpx.MockTransport`:

```python
response = MockLLMProvider().generate_replan(replan_request())
assert response.payload["revised_remaining_steps"][0]["capability_id"] == "project_metadata"
assert "tool_id" not in json.dumps(response.payload)

real = OpenAICompatibleProvider(
    real_config(), transport=httpx.MockTransport(handler), sleeper=lambda _: None
)
assert real.generate_replan(replan_request()).payload == valid_replan_payload()
```

Reuse Phase 12 helpers locally or import only stable production interfaces. Add timeout/auth/malformed response tests asserting safe `ProviderError` categories and exactly no Mock call/fallback.

- [ ] **Step 3: Run the Task 3 RED slice**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase_13_controlled_replanning.py -q -k "proposal or context or prompt or provider or mock"
```

Expected: failures for missing context/proposal/prompt and `generate_replan`.

- [ ] **Step 4: Implement strict context and proposal models**

Use Pydantic for untrusted output and immutable dataclasses for trusted context:

```python
class ReplanProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision_summary: str = Field(min_length=1, max_length=500)
    revised_remaining_steps: list[CapabilityPlanStep] = Field(min_length=1, max_length=10)


@dataclass(frozen=True, slots=True)
class ReplanContext:
    user_goal: str
    original_plan_id: str
    current_plan_id: str
    current_plan_version: int
    remaining_plan_summary: tuple[StepSummary, ...]
    completed_step_summaries: tuple[StepSummary, ...]
    latest_observation: RuntimeObservation
    evidence_summaries: tuple[EvidenceSummary, ...]
    remaining_step_budget: int
    remaining_replan_budget: int
```

Add `EvidenceSummary(evidence_id: str, summary: str, content_hash: str | None)` and a `bounded()` constructor that applies count/character limits before serialization.

- [ ] **Step 5: Implement prompt bounds and provider extension**

`build_replan_prompt()` serializes a capability catalog equivalent to Phase 12 planning but never includes `candidate_tool_ids`. Check context bytes before assembly and complete prompt bytes after assembly. Raise `ValueError` before the provider call when either limit is exceeded.

Extend the protocol and providers with:

```python
def generate_replan(self, request: LLMRequest) -> LLMResponse:
    """Return untrusted capability-only remaining-plan data."""
```

Mock returns one deterministic `project_metadata` request for `PROJECT_CONTEXT.md`. OpenAI-compatible calls existing `_complete()` with schema name `agentforge_replan` and the configured output-token limit. Do not copy retry/HTTP code.

- [ ] **Step 6: Run Phase 13 and Phase 12 provider suites**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase_13_controlled_replanning.py backend/tests/test_phase_12_real_llm_provider.py -q
```

Expected: all selected tests pass; all real-provider paths use mocked transport.

- [ ] **Step 7: Keep this task uncommitted until Task 4**

Provider contracts and successor persistence are one coherent boundary and commit together after approval binding is proven.

---

### Task 4: Immutable Plan Versioning, Validation, Resolution, and Fresh Approval

**Files:**

- Create: `backend/app/agents/replanning/service.py`
- Modify: `backend/app/agents/replanning/models.py`
- Modify: `backend/app/agents/replanning/__init__.py`
- Modify: `backend/app/services/plan_repository.py`
- Modify: `backend/app/approvals/service.py`
- Modify: `backend/app/domain/states/task_state.py`
- Test: `backend/tests/test_phase_13_controlled_replanning.py`

**Interfaces:**

- Consumes: `ReplanPolicy`, `LLMProvider.generate_replan`, `PlanValidator`, `CapabilityResolver`, `PlanRepository`, `ApprovalService`.
- Produces: `ReplanningService.create_successor(*, task_id: str, current_plan_id: str, current_plan_version: int, observation: RuntimeObservation, completed_steps: tuple[StepSummary, ...], attempted_steps: int) -> ReplanOutcome`; `ReplanningService.authoritative_plan(task_id: str) -> AuthoritativePlan`; fresh `ApprovalRecord` bound to the new plan/version/snapshots.

- [ ] **Step 1: Add RED tests for immutable lineage and exact fresh approval**

Build a task with approved Plan v1, then call the service using a valid diagnostic observation. Assert:

```python
outcome = service.create_successor(
    task_id=task.id,
    current_plan_id=plan_v1.id,
    current_plan_version=1,
    observation=replan_observation(),
    completed_steps=(repository_summary(), test_failure_summary()),
    attempted_steps=2,
)
plan_v2 = session.get(PlanRecord, outcome.plan_id)
assert outcome.status == ReplanOutcomeStatus.WAITING_APPROVAL
assert plan_v2.version == 2
assert session.get(PlanRecord, plan_v1.id).plan_json == original_v1_json
assert plan_v2.plan_json["replan_lineage"]["previous_plan_id"] == plan_v1.id
assert plan_v2.plan_json["replan_lineage"]["previous_plan_version"] == 1
assert plan_v2.plan_json["replan_lineage"]["triggering_execution_id"] == "execution-test"
assert plan_v2.plan_json["replan_lineage"]["triggering_observation_id"] == observation.observation_id
assert plan_v2.plan_json["replan_lineage"]["reason_code"] == "TEST_FAILED_DIAGNOSTIC_AVAILABLE"
assert plan_v2.plan_json["replan_lineage"]["created_at"]
approval_v2 = latest_approval(session, plan_v2.id)
assert approval_v2.decision == "PENDING"
assert approval_v2.plan_id == plan_v2.id
assert approval_v2.resolved_snapshot["steps"][0]["plan_version"] == 2
assert task_record(session, task.id).status == TaskStatus.WAITING_APPROVAL.value
```

Assert the approved v1 row remains approved but `ApprovalService.assert_snapshot_allowed(v2_snapshot)` fails until v2 approval is explicitly approved. Even a `SAFE_READ`-only v2 must have a new pending approval.

- [ ] **Step 2: Add RED fail-closed matrix to the same file**

Parameterize service cases for invalid proposal, unknown capability, invalid parameters, concrete-tool/command fields, zero resolver candidate, multiple resolver candidates, stale current version, duplicate plan fingerprint, unchanged progress, max replans, max total steps, provider timeout/auth/malformed output, missing evidence, malformed observation, and cancellation before/after provider response.

For each case assert:

- no executable successor remains committed;
- no approved v2 exists;
- the old plan is not resumed;
- a bounded `REPLAN_REJECTED` event contains only a safe category/reason;
- secret sentinel is absent from serialized plans, approvals, audit, and exception strings.

- [ ] **Step 3: Run the Task 4 RED slice**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase_13_controlled_replanning.py -q -k "lineage or approval or stale or candidate or rejected or cancelled"
```

Expected: failures for missing service/outcome, missing `RUNNING -> WAITING_APPROVAL`, and no fresh successor approval path.

- [ ] **Step 4: Implement repository lookups and state transition**

Add:

```python
def highest_for_task(self, task_id: str) -> PlanRecord | None:
    return (
        self.session.query(PlanRecord)
        .filter_by(task_id=task_id)
        .order_by(PlanRecord.version.desc(), PlanRecord.created_at.desc())
        .first()
    )

def count_replans(self, task_id: str) -> int:
    return sum(
        1 for plan in self.session.query(PlanRecord).filter_by(task_id=task_id)
        if isinstance(plan.plan_json.get("replan_lineage"), dict)
    )
```

Add only `TaskStatus.WAITING_APPROVAL` to allowed targets from `RUNNING`. Update `ApprovalService.create_request()` to transition either `PLANNING` or `RUNNING` to `WAITING_APPROVAL` after validating the exact new plan and snapshot. Do not allow arbitrary WAITING requests or cross-version snapshot reuse.

- [ ] **Step 5: Implement service contracts and orchestration**

Use these result types:

```python
class ReplanOutcomeStatus(StrEnum):
    WAITING_APPROVAL = "WAITING_APPROVAL"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class ReplanOutcome:
    status: ReplanOutcomeStatus
    task_id: str
    plan_id: str | None
    plan_version: int | None
    approval_id: str | None
    reason_code: str
    summary: str


@dataclass(frozen=True, slots=True)
class AuthoritativePlan:
    plan_id: str
    plan_version: int
    approval_id: str | None
    approval_decision: str | None
    executable: bool
```

`create_successor()` performs, in order:

1. reload task/current/highest plan and reject stale or cancelled state;
2. derive persisted replan/step/failure history and call `ReplanPolicy`;
3. build bounded context and audit `REPLAN_REQUESTED`;
4. call exactly one `provider.generate_replan()`;
5. parse `ReplanProposal`, adapt it to a normal schema-v2 `PlanContract`, and call existing `PlanValidator`;
6. reject old/prior fingerprints and no-progress conditions;
7. under a process-local per-task lock, recheck highest plan/version, create and flush vN+1, resolve every step, and bind snapshots to vN+1;
8. persist server-owned lineage and bounded safe provider metadata;
9. create a fresh approval request for vN+1, which moves task to `WAITING_APPROVAL`;
10. commit `PLAN_VERSION_CREATED` and `REPLAN_APPROVAL_REQUIRED` audit data without prompts/raw responses.

Rollback any partial plan/snapshot work on errors. Convert safe failures to `ReplanOutcomeStatus.FAILED`, transition active tasks to `FAILED`, and never resume v1 after policy declared it insufficient.

- [ ] **Step 6: Implement authoritative recovery query**

`authoritative_plan(task_id)` loads the unique highest valid plan. It returns executable only when the task is `RUNNING`, a fresh `APPROVED` approval exists for that exact plan ID, and its snapshot document parses and binds exactly. A pending v2 returns `WAITING_APPROVAL`/not executable. `REPLAN_REQUESTED` without a successor, competing same-parent successors, stale approvals, or cancelled tasks fail closed with `ApprovalError`/`ValueError` and do not choose v1.

- [ ] **Step 7: Run feature and adjacent approval/planner tests**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase_13_controlled_replanning.py backend/tests/test_planner.py backend/tests/test_phase_11_2_capability_tool_selection.py -q
```

Expected: all selected tests pass; SQLite schema remains unchanged.

- [ ] **Step 8: Commit replanner and successor approval boundary**

```powershell
git add backend/app/agents/replanning backend/app/agents/providers/base.py backend/app/agents/providers/mock.py backend/app/agents/providers/openai_compatible.py backend/app/services/plan_repository.py backend/app/approvals/service.py backend/app/domain/states/task_state.py backend/tests/test_phase_13_controlled_replanning.py
git commit -m "feat: create governed replan versions"
```

---

### Task 5: AgentRuntime REPLAN Orchestration and Resume

**Files:**

- Modify: `backend/app/agent_runtime/runtime.py`
- Modify: `backend/app/agent_runtime/state.py`
- Modify: `backend/app/agent_runtime/__init__.py`
- Modify: `backend/app/agents/replanning/service.py`
- Test: `backend/tests/test_phase_13_controlled_replanning.py`

**Interfaces:**

- Consumes: `RuntimeObservation.decision`, `ReplanningService.create_successor()`, existing exact-version approval and resolver verification.
- Produces: `RuntimeResult` with optional successor identifiers; old-plan pause on REPLAN; explicit post-approval run of Plan v2 through existing executor/ToolGateway.

- [ ] **Step 1: Add RED runtime transition tests**

Inject a fake/real test `ReplanningService` and deterministic executor. Assert that a failed test observation:

- executes v1 steps only through `RuntimeExecutor`;
- records one `REPLAN` decision;
- calls `create_successor()` exactly once;
- stops iterating any remaining v1 steps;
- returns `RuntimeResult.decision == REPLAN` with v2 identifiers;
- leaves task `WAITING_APPROVAL`, not `FAILED` or `SUCCESS`;
- executes no v2 tool before fresh approval.

After explicitly approving v2, call `AgentRuntime.run(task_id, plan_v2.id, 2)` and assert only the exact v2 snapshot reaches the existing ToolGateway. Add stale v1 approval and stale registry fingerprint cases that fail before gateway execution.

For a lineage reason of `TEST_FAILED_DIAGNOSTIC_AVAILABLE`, assert that successful completion of the v2 diagnostic step produces the application-owned terminal decision `FAIL` with bounded summary `NOT READY: test failure confirmed by project metadata`; tool success means the diagnostic ran correctly, not that the release goal passed.

- [ ] **Step 2: Add RED restart and cancellation tests**

Create persisted states for:

- pending v2 after restart -> authoritative v2, not executable;
- approved v2 after restart -> authoritative v2 and executable;
- `REPLAN_REQUESTED` without successor -> fail closed, never v1;
- cancellation between observation and service call -> no provider call;
- cancellation after proposal but before persistence -> rollback and no approval;
- multiple successors from one parent -> integrity failure.

- [ ] **Step 3: Run the Task 5 RED slice**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase_13_controlled_replanning.py -q -k "runtime or resume or restart or authoritative or cancellation"
```

Expected: failures because Runtime currently treats REPLAN as terminal FAIL and has no successor fields/service delegation.

- [ ] **Step 4: Implement minimal runtime delegation**

Extend `RuntimeResult` with:

```python
successor_plan_id: str | None = None
successor_plan_version: int | None = None
approval_id: str | None = None
```

Inject `replanning_service: ReplanningService | None = None` into `AgentRuntime.__init__`. In the decision branch:

```python
if observation.decision == RuntimeDecision.REPLAN:
    if self.replanning_service is None:
        summary = "Replanning is unavailable"
        TaskService(self.session).transition_task(
            task_id, TaskStatus.FAILED, actor="agent_runtime", reason=summary
        )
        self._transition(runtime_snapshot, task_id, RuntimeState.FAILED, summary)
        return RuntimeResult(
            task_id=task_id, plan_id=plan_id, plan_version=plan_version,
            state=RuntimeState.FAILED, decision=RuntimeDecision.FAIL,
            completed_steps=runtime_snapshot.completed_steps,
            observations=tuple(observations),
        )
    outcome = self.replanning_service.create_successor(
        task_id=task_id,
        current_plan_id=plan_id,
        current_plan_version=plan_version,
        observation=observation,
        completed_steps=self._step_summaries(observations),
        attempted_steps=index + 1,
    )
    if outcome.status != ReplanOutcomeStatus.WAITING_APPROVAL:
        self._transition(runtime_snapshot, task_id, RuntimeState.FAILED, outcome.summary)
        return RuntimeResult(
            task_id=task_id, plan_id=plan_id, plan_version=plan_version,
            state=RuntimeState.FAILED, decision=RuntimeDecision.FAIL,
            completed_steps=runtime_snapshot.completed_steps,
            observations=tuple(observations),
        )
    return RuntimeResult(
        task_id=task_id,
        plan_id=plan_id,
        plan_version=plan_version,
        state=RuntimeState.OBSERVING,
        decision=RuntimeDecision.REPLAN,
        completed_steps=runtime_snapshot.completed_steps,
        observations=tuple(observations),
        successor_plan_id=outcome.plan_id,
        successor_plan_version=outcome.plan_version,
        approval_id=outcome.approval_id,
    )
```

Add `_step_summaries(observations: Sequence[RuntimeObservation]) -> tuple[StepSummary, ...]`; it copies only capability ID, normalized parameters from the matching resolved snapshot, status, reason code, a 500-character summary, and at most five evidence IDs. It never reads raw artifacts or audit history.

Do not recursively call `run()` and do not execute v2 in the same invocation. Human approval is an explicit pause. The existing later call to `run()` remains the resume mechanism and re-verifies approval, snapshots, resolver fingerprint, and ToolGateway input.

When an approved lineage-bearing v2 reaches its final successful diagnostic step, derive the task conclusion from the server-owned lineage reason. `TEST_FAILED_DIAGNOSTIC_AVAILABLE` maps deterministically to task `FAILED` and the bounded `NOT READY` summary. The provider cannot set this mapping or terminal task status.

- [ ] **Step 5: Bound and align runtime audit**

Serialize the evolved structured observation, reason code, decision, and successor IDs. Keep summaries at 2,000 characters and full replan audit payloads at 8 KiB. Use the existing runtime events plus `REPLAN_RESUMED` when a lineage-bearing approved plan starts; do not duplicate every event name from the design for symmetry.

- [ ] **Step 6: Run Phase 13 and all adjacent runtime/approval tests**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase_13_controlled_replanning.py backend/tests/test_agent_runtime.py backend/tests/test_approval_workflow.py -q
```

Expected: all selected tests pass using the existing runtime and approval workflow suites.

- [ ] **Step 7: Commit Runtime and approval integration**

```powershell
git add backend/app/agent_runtime backend/app/agents/replanning/service.py backend/tests/test_phase_13_controlled_replanning.py
git commit -m "feat: pause runtime for governed replanning"
```

---

### Task 6: Audit Reconstruction and Deterministic Release Verification Flow

**Files:**

- Modify: `backend/app/agents/replanning/service.py`
- Modify: `backend/app/agent_runtime/runtime.py`
- Test: `backend/tests/test_phase_13_controlled_replanning.py`

**Interfaces:**

- Consumes: all Phase 13 production boundaries from Tasks 1–5.
- Produces: reconstructable bounded audit sequence and one fully offline v1 -> observation -> v2 -> fresh approval -> resume -> NOT READY scenario.

- [ ] **Step 1: Add RED end-to-end deterministic scenario**

Build exactly one release-verification flow in the Phase 13 file:

1. create goal “Check whether version 2.0 is ready for release.”;
2. persist/approve Plan v1 with `repository_state` and `test_verification`;
3. deterministic gateway returns repository success, then test failure plus `evidence-test-failure`;
4. policy returns REPLAN and Mock proposes `project_metadata`;
5. service creates Plan v2 and fresh pending approval;
6. assert no metadata execution before approval;
7. approve v2 and run it through ToolGateway;
8. deterministic metadata result identifies a version/configuration problem and creates `evidence-version-config`;
9. final report/result is NOT READY and references both evidence IDs.

Do not add a second demo scenario or real-provider call.

- [ ] **Step 2: Add RED audit reconstruction and secrecy assertions**

Query audit in timestamp/ID order and assert the sequence contains the repository-consistent events needed to reconstruct:

```text
RUNTIME_EXECUTION
RUNTIME_OBSERVATION
RUNTIME_DECISION(REPLAN)
REPLAN_REQUESTED
REPLAN_PROPOSED
PLAN_VERSION_CREATED
REPLAN_APPROVAL_REQUIRED
APPROVED / EXECUTION_SNAPSHOT_APPROVED
REPLAN_RESUMED
RUNTIME_EXECUTION
RUNTIME_OBSERVATION
RUNTIME_DECISION(COMPLETE or FAIL with NOT READY summary)
```

Assert IDs, versions, triggering reason, proposed capability IDs, provider/model and safe timing metadata are present. Assert sentinel secret, full prompt, raw provider body, raw tool output, Authorization, and Chain of Thought are absent. Assert every replan event payload is at most 8 KiB encoded UTF-8.

- [ ] **Step 3: Run the Task 6 RED slice**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase_13_controlled_replanning.py -q -k "release_verification or audit or secret"
```

Expected: focused failures for missing/incorrect audit metadata or final deterministic outcome only.

- [ ] **Step 4: Implement only missing audit and demo-facing behavior**

Use one service `_audit(event_type, payload)` helper that JSON-serializes approved fields, truncates summaries before serialization, enforces 8 KiB, and rejects rather than truncating invalid structural JSON. Reuse existing evidence/execution records; do not persist a second observation table. Ensure provider metadata is safe and outcome summaries contain no raw exception/body.

For the deterministic final outcome, implement only the application-owned lineage-reason mapping specified in Task 5: the v1 test-failure reason plus successful v2 diagnostic evidence yields task `FAILED` and the bounded `NOT READY` summary. Do not add a model judgment, frontend, or generic evaluation engine.

- [ ] **Step 5: Run the complete Phase 13 feature file**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase_13_controlled_replanning.py -q
```

Expected bounded output: all Phase 13 tests pass, zero real network calls, no verbose logs.

- [ ] **Step 6: Keep this task uncommitted until Task 7**

Audit/demo completion, docs, and final security verification form the final coherent commit.

---

### Task 7: Security Review, Documentation, Final Regression, and Hygiene

**Files:**

- Modify: `PROJECT_CONTEXT.md`
- Modify: `README.md`
- Modify: `docs/deployment/README.md`
- Test: `backend/tests/test_phase_13_controlled_replanning.py`

**Interfaces:**

- Consumes: completed Phase 13 implementation and approved spec.
- Produces: operational documentation, confirmed security invariants, clean regression evidence, and final coherent commit.

- [ ] **Step 1: Perform one focused whole-feature review without parallel agents**

Review the diff from `7a1a557` for exactly these risks: model-controlled tool/command/approval/workspace; Resolver or ToolGateway bypass; old approval authorizing v2; missing stale version/fingerprint check; duplicate/no-progress loop; budget off-by-one; context/audit overflow; raw prompt/response/tool output or secret persistence; silent real-to-Mock fallback; real network in tests; schema/status/dependency/frontend scope creep; and unnecessary files.

Fix only confirmed findings and add their regression coverage to the same Phase 13 test file. Do not create a review artifact or another test package.

- [ ] **Step 2: Verify database and dependency boundaries**

Run bounded read-only checks:

```powershell
git diff 7a1a557 --name-only
git diff 7a1a557 -- backend/app/storage backend/requirements.txt frontend/package.json frontend/package-lock.json
```

Expected: no ORM/migration/database schema, dependency, lockfile, ToolGateway, or frontend changes. If a schema change appears necessary, stop and report instead of implementing it.

- [ ] **Step 3: Update only required operational documentation**

Document:

- the four runtime decisions and controlled hybrid flow;
- `max_replans=2`, `max_total_steps=12`, 8 KiB context, and 12 KiB prompt;
- every replan version requires fresh approval, including safe-read-only versions;
- Plan v1 remains immutable and cannot authorize v2;
- no Chain of Thought/raw output/provider credentials are stored;
- Mock is deterministic/offline and real provider never silently falls back;
- no DB migration or frontend setup is required.

Do not add implementation-plan status to unrelated portfolio documents.

- [ ] **Step 4: Run fresh Phase 13 verification**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase_13_controlled_replanning.py -q
```

Expected: all Phase 13 tests pass.

- [ ] **Step 5: Run one final backend regression**

Redirect the complete log to the approved D-drive temporary directory and print only the summary/final 40 lines:

```powershell
$log='D:\VSCodeData\AgentDev\Temp\agentforge-phase13-final-backend.log'
backend\.venv\Scripts\python.exe -m pytest backend/tests -q *> $log
$code=$LASTEXITCODE
Get-Content $log -Tail 40
exit $code
```

Expected: all backend tests pass. Do not run frontend tests/build because this plan does not modify frontend; run them only if review finds a genuinely required frontend change.

- [ ] **Step 6: Run final hygiene and secret checks**

Run:

```powershell
git diff --check
git status --short
git diff 7a1a557 --stat
git diff 7a1a557 --name-only
```

Confirm only intentional source/docs/tests changed; no `.env`, SQLite, runtime data, logs, caches, temporary/debug files, dependency environments, or extra Phase 13 test packages appear. Confirm disk growth remains below approximately 500 MiB.

- [ ] **Step 7: Commit final audit/demo/docs completion**

```powershell
git add PROJECT_CONTEXT.md README.md docs/deployment/README.md backend/app backend/tests/test_phase_13_controlled_replanning.py
git commit -m "docs: complete controlled replanning phase"
```

- [ ] **Step 8: Verify the committed branch and stop before integration**

Run:

```powershell
git status --short
git log -5 --oneline
```

Expected: clean worktree with a few coherent Phase 13 commits. Do not merge, push, deploy, delete the worktree, or touch runtime/live database data without explicit user approval.
