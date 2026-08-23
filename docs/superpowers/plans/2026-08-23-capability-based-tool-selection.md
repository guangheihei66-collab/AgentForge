# Capability-Based Tool Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Phase 11.2 capability-first planning, deterministic concrete-tool resolution, immutable approval binding, and resolved runtime execution without bypassing the existing ToolGateway.

**Architecture:** Planner output uses schema version 2 and contains semantic `capability_id` plus bounded parameters. An application-owned `CapabilityResolver` validates exactly one mapped ToolRegistry candidate and produces immutable per-step snapshots before approval; Approval stores the complete structured snapshot document, and AgentRuntime verifies and consumes it through RuntimeExecutor and the existing ToolGateway. Legacy concrete-tool plans remain readable but are rejected by the new approval/runtime path.

**Tech Stack:** Python 3, FastAPI, Pydantic 2, SQLAlchemy 2, SQLite, pytest, React 19, TypeScript, Vite, Vitest.

**Spec:** `docs/superpowers/specs/2026-08-23-capability-based-tool-selection-design.md`

## Global Constraints

- Source changes stay under `D:\AgentProjects\AgentForge`; mutable runtime/test data stays under `D:\AgentProjectData\AgentForge`.
- Implement only `repository_state`, `project_metadata`, and `test_verification`.
- Planner and Runtime must not directly accept concrete tool IDs as authority.
- `CapabilityRegistry` and `ToolRegistry` remain independent.
- Resolution succeeds only with exactly one valid candidate; zero or multiple valid candidates fail closed.
- No priority, implicit tie-break, LLM selection, arbitrary shell, hidden reasoning persistence, or fallback to a legacy tool field.
- Runtime consumes and verifies already-resolved snapshots; it does not select candidates or invent parameters.
- Existing `ToolGateway`, `PermissionPolicy`, and `WorkspaceValidator` remain the final execution boundary and are not modified in this phase.
- Approval binds task ID, plan ID, plan version, capability ID, resolved tool ID, resolved action, normalized parameters, and registry fingerprint.
- Existing SQLite data is migrated non-destructively; no database recreation or deletion is permitted.
- No new dependencies, database tables, Docker, model downloads, or operations expected to exceed 1 GiB.
- Each task starts with a failing test, implements the minimum behavior, runs focused and relevant regression tests, checks repository hygiene, and commits only its coherent files.

## File Structure

New backend files:

- `backend/app/capabilities/__init__.py`: public capability package exports.
- `backend/app/capabilities/models.py`: immutable capability, parameter, and resolved snapshot contracts plus JSON serialization.
- `backend/app/capabilities/registry.py`: independent capability registry and three default definitions.
- `backend/app/capabilities/resolver.py`: deterministic candidate filtering, parameter normalization, canonical fingerprinting, and snapshot verification.
- `backend/app/storage/migrations.py`: idempotent SQLite schema migration for `approvals.resolved_snapshot`.
- `backend/tests/test_capability_registry.py`: capability model and registry tests.
- `backend/tests/test_capability_resolver.py`: resolution and fingerprint tests.
- `backend/tests/test_storage_migrations.py`: fresh and legacy SQLite schema tests.

Existing files modified:

- `backend/app/agents/planner/schemas.py`, `validator.py`, `prompts.py`, `planner.py`: capability-first schema, validation, resolution, persistence, and audit.
- `backend/app/agents/providers/mock.py`: deterministic schema-v2 mock plan.
- `backend/app/tools/models.py` and the three tool files: stable execution contract version metadata used by fingerprints.
- `backend/app/storage/database.py`, `orm.py`: migration invocation and nullable structured approval snapshot column.
- `backend/app/approvals/service.py`, `backend/app/schemas/approval.py`, `backend/app/api/routes/approvals.py`: snapshot persistence, approval response, and exact runtime binding checks.
- `backend/app/agent_runtime/runtime.py`, `executor.py`, `observer.py`: snapshot-only runtime input and ToolGateway adapter.
- `backend/app/schemas/operations.py`, `backend/app/api/routes/operations.py`: expose resolved snapshots for operator review.
- `backend/tests/test_planner.py`, `test_approval_workflow.py`, `test_agent_runtime.py`, `test_api.py`: schema, binding, runtime, API, audit, and end-to-end coverage.
- `scripts/seed_demo.py`: capability-first demo plan and approval snapshots.
- `frontend/src/types/index.ts`, `hooks/useOperations.ts`, `pages/Approvals.tsx`, `pages/TaskDetail.tsx`, `App.test.tsx`: display capability, resolved concrete tool, and normalized parameters.
- `PROJECT_CONTEXT.md` and `README.md`: Phase 11.2 architecture/status after all tests pass.

---

### Task 1: Capability contracts and independent registry

**Files:**

- Create: `backend/app/capabilities/__init__.py`
- Create: `backend/app/capabilities/models.py`
- Create: `backend/app/capabilities/registry.py`
- Create: `backend/tests/test_capability_registry.py`

**Interfaces:**

- Consumes: `app.contracts.permissions.PermissionLevel`.
- Produces: `ParameterFieldDefinition`, `CapabilityDefinition`, `CapabilityRequest`, `ResolvedExecutionSnapshot`, `CapabilityRegistry`, `CapabilityNotFound`, and `build_default_capability_registry()`.
- `ResolvedExecutionSnapshot.normalized_parameters` uses a sorted tuple of `(str, str)` pairs for deep immutability; `to_dict()` emits a JSON object and `from_dict()` validates persisted JSON.

- [ ] **Step 1: Write registry tests that define the exact three-capability contract**

```python
# backend/tests/test_capability_registry.py
import pytest

from app.capabilities.models import CapabilityDefinition, ParameterFieldDefinition
from app.capabilities.registry import (
    CapabilityNotFound,
    CapabilityRegistry,
    build_default_capability_registry,
)
from app.contracts.permissions import PermissionLevel


def test_default_registry_contains_only_three_mvp_capabilities():
    registry = build_default_capability_registry()

    assert registry.ids() == (
        "project_metadata",
        "repository_state",
        "test_verification",
    )
    assert registry.require("repository_state").candidate_tool_ids == ("git_read",)
    assert registry.require("project_metadata").candidate_tool_ids == ("file_read",)
    test_definition = registry.require("test_verification")
    assert test_definition.candidate_tool_ids == ("test_run",)
    assert test_definition.parameter_schema == (
        ParameterFieldDefinition(
            name="profile", required=True, allowed_values=("smoke", "unit")
        ),
    )


def test_unknown_and_duplicate_capabilities_are_rejected():
    registry = CapabilityRegistry()
    definition = CapabilityDefinition(
        id="repository_state",
        description="Read repository state",
        risk_level="low",
        required_permission=PermissionLevel.SAFE_READ,
        candidate_tool_ids=("git_read",),
        action="status",
        parameter_schema=(),
    )
    registry.register(definition)

    with pytest.raises(ValueError, match="already registered"):
        registry.register(definition)
    with pytest.raises(CapabilityNotFound, match="Unknown capability"):
        registry.require("missing")
```

- [ ] **Step 2: Run the focused tests and confirm the package is absent**

Run from `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_capability_registry.py -q
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'app.capabilities'`.

- [ ] **Step 3: Implement immutable models and the registry**

Implement these signatures in `models.py`:

```python
@dataclass(frozen=True, slots=True)
class ParameterFieldDefinition:
    name: str
    required: bool
    allowed_values: tuple[str, ...]
    default: str | None = None

@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    id: str
    description: str
    risk_level: str
    required_permission: PermissionLevel
    candidate_tool_ids: tuple[str, ...]
    action: str
    parameter_schema: tuple[ParameterFieldDefinition, ...]

@dataclass(frozen=True, slots=True)
class CapabilityRequest:
    capability_id: str
    parameters: Mapping[str, Any]

@dataclass(frozen=True, slots=True)
class ResolvedExecutionSnapshot:
    task_id: str
    plan_id: str
    plan_version: int
    step_id: str
    capability_id: str
    resolved_tool_id: str
    resolved_action: str
    normalized_parameters: tuple[tuple[str, str], ...]
    registry_fingerprint: str

    def parameters_dict(self) -> dict[str, str]:
        return dict(self.normalized_parameters)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "step_id": self.step_id,
            "capability_id": self.capability_id,
            "resolved_tool_id": self.resolved_tool_id,
            "resolved_action": self.resolved_action,
            "normalized_parameters": self.parameters_dict(),
            "registry_fingerprint": self.registry_fingerprint,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ResolvedExecutionSnapshot":
        expected = {
            "task_id", "plan_id", "plan_version", "step_id", "capability_id",
            "resolved_tool_id", "resolved_action", "normalized_parameters",
            "registry_fingerprint",
        }
        if set(payload) != expected:
            raise ValueError("Resolved snapshot fields are invalid")
        parameters = payload["normalized_parameters"]
        if not isinstance(parameters, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in parameters.items()
        ):
            raise ValueError("Resolved snapshot parameters are invalid")
        version = payload["plan_version"]
        fingerprint = payload["registry_fingerprint"]
        if not isinstance(version, int) or version < 1:
            raise ValueError("Resolved snapshot plan version is invalid")
        if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            raise ValueError("Resolved snapshot fingerprint is invalid")
        string_fields = expected - {
            "plan_version", "normalized_parameters", "registry_fingerprint"
        }
        if any(not isinstance(payload[field], str) or not payload[field] for field in string_fields):
            raise ValueError("Resolved snapshot identifiers are invalid")
        return cls(
            task_id=payload["task_id"],
            plan_id=payload["plan_id"],
            plan_version=version,
            step_id=payload["step_id"],
            capability_id=payload["capability_id"],
            resolved_tool_id=payload["resolved_tool_id"],
            resolved_action=payload["resolved_action"],
            normalized_parameters=tuple(sorted(parameters.items())),
            registry_fingerprint=fingerprint,
        )
```

`from_dict()` must reject missing/extra fields, non-string parameter values,
non-positive plan versions, and non-64-character lowercase hex fingerprints.
It must sort parameter pairs by key before constructing the frozen value.

Implement `CapabilityRegistry.register()`, `.get()`, `.require()`, and `.ids()`
with duplicate rejection and sorted IDs. Implement exactly these defaults:

```python
repository_state: git_read / status / SAFE_READ / no parameters
project_metadata: file_read / read_metadata / SAFE_READ /
  relative_path required and restricted to AGENTS.md, PROJECT_CONTEXT.md,
  README.md, package-lock.json, package.json, pyproject.toml,
  requirements.txt, tsconfig.json
test_verification: test_run / run_profile / APPROVED_EXEC /
  profile required and restricted to smoke, unit
```

- [ ] **Step 4: Export the public contracts and rerun focused tests**

Export all Task 1 public names from `backend/app/capabilities/__init__.py`.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_capability_registry.py -q
```

Expected: PASS.

- [ ] **Step 5: Run nearby permission and registry regression tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_tool_registry.py tests/test_capability_registry.py -q
git status --short
```

Expected: tests PASS; only Task 1 files are changed; no cache, database, log,
or temporary file appears in the repository.

- [ ] **Step 6: Commit the capability domain**

```powershell
git add backend/app/capabilities backend/tests/test_capability_registry.py
git commit -m "feat: add capability registry contracts"
```

### Task 2: Deterministic resolver and registry fingerprint

**Files:**

- Create: `backend/app/capabilities/resolver.py`
- Create: `backend/tests/test_capability_resolver.py`
- Modify: `backend/app/tools/models.py`
- Modify: `backend/app/tools/git_read.py`
- Modify: `backend/app/tools/file_read.py`
- Modify: `backend/app/tools/test_tool.py`

**Interfaces:**

- Consumes: Task 1 contracts, `CapabilityRegistry`, and existing `ToolRegistry`.
- Produces: `CapabilityResolutionError`, `CapabilityResolver.resolve()`, `CapabilityResolver.verify()`, and `registry_fingerprint()`.
- Extends `ToolDefinition` with `execution_contract_version: str = "1"`; no executor behavior changes.

- [ ] **Step 1: Write resolver success, failure, normalization, and fingerprint tests**

Create tests with these exact calls:

```python
resolver.resolve(
    task_id="task-1",
    plan_id="plan-1",
    plan_version=1,
    step_id="step-1",
    request=CapabilityRequest("test_verification", {"profile": "smoke"}),
)
resolver.verify(snapshot)
```

Cover:

```python
@pytest.mark.parametrize(
    ("capability_id", "parameters", "tool_id", "action"),
    [
        ("repository_state", {}, "git_read", "status"),
        ("project_metadata", {"relative_path": "PROJECT_CONTEXT.md"}, "file_read", "read_metadata"),
        ("test_verification", {"profile": "smoke"}, "test_run", "run_profile"),
    ],
)
def test_resolves_each_mvp_capability(
    capability_id, parameters, tool_id, action, resolver
):
    snapshot = resolver.resolve(
        task_id="task-1",
        plan_id="plan-1",
        plan_version=1,
        step_id="step-1",
        request=CapabilityRequest(capability_id, parameters),
    )
    assert snapshot.resolved_tool_id == tool_id
    assert snapshot.resolved_action == action
    resolver.verify(snapshot)
```

Add separate tests named
`test_unknown_zero_multiple_unregistered_disabled_and_permission_mismatch_fail_closed`,
`test_invalid_extra_or_missing_parameters_are_rejected`,
`test_parameter_order_is_normalized`,
`test_fingerprint_is_deterministic_and_ignores_description`,
`test_fingerprint_changes_for_permission_action_schema_enabled_or_contract_version`,
and `test_verify_rejects_removed_tool_and_modified_fingerprint`. Each must assert
the exact success or `CapabilityResolutionError` outcome described below.

Build fixture registries with `dataclasses.replace()` so each rejection has a
single cause. For the multiple-candidate case, register two enabled
permission-compatible tools and map both IDs in one test capability. Assert
`CapabilityResolutionError` messages name the capability and reason without
including unrestricted model output.

- [ ] **Step 2: Run resolver tests and confirm the resolver is absent**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_capability_resolver.py -q
```

Expected: FAIL during collection because `app.capabilities.resolver` does not exist.

- [ ] **Step 3: Add stable execution contract metadata to ToolDefinition**

Append this field after `enabled`:

```python
execution_contract_version: str = "1"
```

Set it explicitly to `"1"` in `GitReadTool`, `FileReadTool`, and `TestTool`.
Do not alter their actions, subprocess behavior, workspace validation, or
permission levels.

- [ ] **Step 4: Implement candidate validation and parameter normalization**

Implement:

```python
class CapabilityResolutionError(ValueError):
    """Resolution failed without selecting an executable tool."""

class CapabilityResolver:
    def __init__(
        self,
        capabilities: CapabilityRegistry,
        tools: ToolRegistry,
    ) -> None:
        self.capabilities = capabilities
        self.tools = tools

    def resolve(
        self,
        *,
        task_id: str,
        plan_id: str,
        plan_version: int,
        step_id: str,
        request: CapabilityRequest,
    ) -> ResolvedExecutionSnapshot:
        capability = self.capabilities.require(request.capability_id)
        normalized = self._normalize(capability, request.parameters)
        candidates = self._valid_candidates(capability)
        if len(candidates) != 1:
            raise CapabilityResolutionError(
                f"Capability {capability.id} requires exactly one valid candidate; "
                f"found {len(candidates)}"
            )
        tool = candidates[0]
        return ResolvedExecutionSnapshot(
            task_id=task_id,
            plan_id=plan_id,
            plan_version=plan_version,
            step_id=step_id,
            capability_id=capability.id,
            resolved_tool_id=tool.name,
            resolved_action=capability.action,
            normalized_parameters=normalized,
            registry_fingerprint=registry_fingerprint(capability, tool),
        )

    def verify(self, snapshot: ResolvedExecutionSnapshot) -> None:
        capability = self.capabilities.require(snapshot.capability_id)
        tool = self.tools.get(snapshot.resolved_tool_id)
        if tool is None or not tool.enabled:
            raise CapabilityResolutionError("Resolved tool is unavailable")
        if capability.action != snapshot.resolved_action:
            raise CapabilityResolutionError("Resolved action changed")
        self._validate_selected_tool(capability, tool)
        self._normalize(capability, snapshot.parameters_dict())
        actual = registry_fingerprint(capability, tool)
        if not hmac.compare_digest(actual, snapshot.registry_fingerprint):
            raise CapabilityResolutionError("Registry fingerprint changed")
```

Add private `_normalize()`, `_valid_candidates()`, and
`_validate_selected_tool()` methods implementing the exact checks in Step 4;
their tests must call only the public resolver interface.

Parameter normalization must:

- reject unknown keys;
- apply a declared default only when one exists;
- reject missing required keys;
- require string values;
- reject values outside `allowed_values`;
- return sorted `(key, value)` tuples.

Candidate filtering must use only `candidate_tool_ids`, `ToolRegistry.get()`,
`enabled`, exact permission equality, and membership of the capability action
in `allowed_actions`. It must collect all valid candidates and require length
exactly one. It must not call `ToolRegistry.require()` until after uniqueness
is established, because disabled/missing candidates are validation outcomes,
not implicit fallback selection.

- [ ] **Step 5: Implement canonical fingerprinting and verification**

Implement:

```python
def registry_fingerprint(
    capability: CapabilityDefinition,
    tool: ToolDefinition,
) -> str:
    payload = {
        "capability_id": capability.id,
        "candidate_tool_ids": sorted(capability.candidate_tool_ids),
        "resolved_tool_id": tool.name,
        "resolved_action": capability.action,
        "enabled": tool.enabled,
        "permission_level": tool.permission_level.value,
        "risk_level": tool.risk_level,
        "allowed_actions": sorted(tool.allowed_actions),
        "parameter_schema": [
            {
                "name": field.name,
                "required": field.required,
                "allowed_values": sorted(field.allowed_values),
                "default": field.default,
            }
            for field in sorted(capability.parameter_schema, key=lambda item: item.name)
        ],
        "execution_contract_version": tool.execution_contract_version,
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
```

Description is deliberately excluded. `verify()` must require the same
capability and selected tool to still exist and be enabled, recheck permission,
action, and normalized parameters, recompute the fingerprint, and compare with
`hmac.compare_digest()`. It must never choose another candidate.

- [ ] **Step 6: Run focused and tool regression tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_capability_resolver.py tests/test_tool_registry.py tests/test_tool_execution.py -q
git diff --check
git status --short
```

Expected: PASS; only Task 2 files are changed.

- [ ] **Step 7: Commit deterministic resolution**

```powershell
git add backend/app/capabilities/resolver.py backend/app/tools/models.py backend/app/tools/git_read.py backend/app/tools/file_read.py backend/app/tools/test_tool.py backend/tests/test_capability_resolver.py
git commit -m "feat: add deterministic capability resolver"
```

### Task 3: Capability-first planner schema and resolved plan persistence

**Files:**

- Modify: `backend/app/agents/planner/schemas.py`
- Modify: `backend/app/agents/planner/validator.py`
- Modify: `backend/app/agents/planner/prompts.py`
- Modify: `backend/app/agents/planner/planner.py`
- Modify: `backend/app/agents/providers/mock.py`
- Modify: `backend/app/services/plan_repository.py`
- Modify: `backend/tests/test_planner.py`
- Modify: `backend/tests/test_api.py`

**Interfaces:**

- Consumes: `CapabilityRequest`, `CapabilityResolver`, default capability and tool registries.
- Produces: schema-v2 `PlanContract`, `CapabilityPlanStep`, persisted `plan_json["resolved_steps"]`, and `CAPABILITY_REQUESTED` / `CAPABILITY_RESOLVED` events.
- Legacy parsing is exposed as `parse_plan_for_display(payload) -> PlanContract | LegacyPlanContract`; only `PlanValidator.validate()` returns executable schema-v2 plans.

- [ ] **Step 1: Replace planner expectations with capability-first failing tests**

Update `test_planner.py` so the valid payload is:

```python
{
    "schema_version": 2,
    "steps": [
        {
            "step_id": "step-1",
            "capability_id": "repository_state",
            "parameters": {},
        }
    ],
}
```

Add tests asserting:

```python
assert plan.plan_json["schema_version"] == 2
assert plan.plan_json["steps"][0]["capability_id"] == "repository_state"
assert plan.plan_json["resolved_steps"][0]["resolved_tool_id"] == "git_read"

with pytest.raises(PlanValidationError):
    validator().validate({"steps": [{"step_id": "1", "tool": "test_run"}]}, REPO_ROOT)

legacy = parse_plan_for_display({"steps": [legacy_concrete_tool_step]})
assert legacy.schema_version == 1
assert legacy.executable is False
```

Also assert the planner writes one `CAPABILITY_REQUESTED` and one
`CAPABILITY_RESOLVED` event per step, with structured JSON containing no prompt
or hidden reasoning.

- [ ] **Step 2: Run planner and planning API tests to observe schema failures**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_planner.py tests/test_api.py::test_create_plan_endpoint -q
```

Expected: FAIL because current schemas require `tool`, `action`, risk, and permission.

- [ ] **Step 3: Implement strict schema version 2 plus display-only legacy schema**

Define:

```python
class CapabilityPlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_id: str = Field(min_length=1, max_length=64)
    capability_id: Literal[
        "repository_state", "project_metadata", "test_verification"
    ]
    parameters: dict[str, str] = Field(default_factory=dict)

class PlanContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[2] = 2
    steps: list[CapabilityPlanStep] = Field(min_length=1, max_length=20)

class LegacyPlanContract(BaseModel):
    schema_version: Literal[1] = 1
    executable: Literal[False] = False
    steps: list[dict[str, Any]]

def parse_plan_for_display(
    payload: Mapping[str, Any],
) -> PlanContract | LegacyPlanContract:
    if payload.get("schema_version") == 2:
        return PlanContract.model_validate(payload)
    steps = payload.get("steps")
    if not isinstance(steps, list):
        raise ValueError("Persisted plan has no readable steps")
    return LegacyPlanContract(steps=steps)
```

`PlanValidator.validate()` must accept only `PlanContract`; any payload without
`schema_version: 2`, any `tool`/`action` field, forbidden parameter key/value,
or invalid workspace raises `PlanValidationError`. Legacy parsing must never be
called by approval or Runtime.

- [ ] **Step 4: Update prompt and mock provider to emit only capability intent**

Update the prompt contract and `MockLLMProvider` to emit:

```python
{
    "schema_version": 2,
    "steps": [
        {
            "step_id": "step-1",
            "capability_id": "repository_state",
            "parameters": {},
        }
    ],
}
```

The prompt must explicitly forbid concrete tool IDs and arbitrary commands.

- [ ] **Step 5: Resolve after PlanRecord identity exists and persist snapshots**

Keep `PlanRepository.create()` as the identity/version boundary. In
`PlannerAgent.create_plan()`:

1. validate schema-v2 capability intent;
2. create and flush `PlanRecord` with `schema_version`, `steps`, and an empty
   `resolved_steps` list;
3. resolve every step using the record ID and version;
4. replace `plan_json` with a newly assigned JSON object containing serialized
   snapshots (do not mutate nested SQLAlchemy JSON in place);
5. emit bounded structured `CAPABILITY_REQUESTED`, `CAPABILITY_RESOLVED`, and
   existing `PLAN_CREATED` audit events;
6. commit and transition to `WAITING_APPROVAL`.

If any step fails resolution, roll back the plan transaction and transition
the task to `FAILED` using the existing TaskService failure path; no approval
request may exist.

- [ ] **Step 6: Run planner, API, and repository regressions**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_planner.py tests/test_api.py::test_create_plan_endpoint tests/test_repository.py -q
git diff --check
git status --short
```

Expected: PASS and only Task 3 files changed.

- [ ] **Step 7: Commit capability-first planning**

```powershell
git add backend/app/agents/planner backend/app/agents/providers/mock.py backend/app/services/plan_repository.py backend/tests/test_planner.py backend/tests/test_api.py
git commit -m "feat: generate and resolve capability plans"
```

### Task 4: Non-destructive SQLite approval snapshot migration

**Files:**

- Create: `backend/app/storage/migrations.py`
- Create: `backend/tests/test_storage_migrations.py`
- Modify: `backend/app/storage/database.py`
- Modify: `backend/app/storage/orm.py`

**Interfaces:**

- Consumes: SQLAlchemy `Engine` and current `Base.metadata.create_all()` startup.
- Produces: nullable `ApprovalRecord.resolved_snapshot: Mapped[dict | None]` and `migrate_sqlite_schema(bind: Engine) -> None`.
- Migration strategy: idempotent startup migration that only adds the missing nullable JSON column; no table/data deletion or database recreation.

- [ ] **Step 1: Write fresh-schema and legacy-schema migration tests**

Use isolated in-memory SQLite engines so no runtime database is touched:

```python
def test_fresh_schema_contains_resolved_snapshot_column():
    bind = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind)
    assert "resolved_snapshot" in column_names(bind, "approvals")


def test_legacy_approval_table_is_migrated_without_losing_rows():
    bind = create_engine("sqlite+pysqlite:///:memory:")
    with bind.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE approvals (id VARCHAR(36) PRIMARY KEY, task_id VARCHAR(36) NOT NULL, "
            "plan_id VARCHAR(36) NOT NULL, decision VARCHAR(32) NOT NULL, "
            "approver VARCHAR(200) NOT NULL, reason TEXT, created_at DATETIME)"
        )
        connection.exec_driver_sql(
            "INSERT INTO approvals (id, task_id, plan_id, decision, approver) "
            "VALUES ('a1', 't1', 'p1', 'PENDING', 'tester')"
        )

    migrate_sqlite_schema(bind)
    migrate_sqlite_schema(bind)

    assert "resolved_snapshot" in column_names(bind, "approvals")
    with bind.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM approvals").scalar_one() == 1
```

- [ ] **Step 2: Run migration tests and confirm the column/function are absent**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_storage_migrations.py -q
```

Expected: FAIL because the migration module and ORM column do not exist.

- [ ] **Step 3: Add the nullable structured JSON column**

Add to `ApprovalRecord`:

```python
resolved_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

Nullable is required so existing legacy approvals remain readable after the
column is added; null means legacy/unresolved and is not executable by the new
runtime.

- [ ] **Step 4: Implement and invoke the idempotent startup migration**

Implement `migrate_sqlite_schema(bind)` using `sqlalchemy.inspect(bind)`:

- return unchanged for non-SQLite engines;
- return if `approvals` does not exist (fresh `create_all` handles it);
- inspect exact column names;
- if missing, execute exactly
  `ALTER TABLE approvals ADD COLUMN resolved_snapshot JSON` inside `bind.begin()`;
- inspect again and raise `RuntimeError` if the column still does not exist.

In `init_db()`, call `Base.metadata.create_all(bind=engine)` first and then
`migrate_sqlite_schema(engine)`. This supports fresh databases, existing demo
databases, and in-memory tests. It never drops, renames, rewrites, or recreates
the database. Document that any migration failure prevents startup and leaves
the existing database for operator recovery.

- [ ] **Step 5: Run migration and repository tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_storage_migrations.py tests/test_repository.py tests/test_approval_workflow.py -q
git diff --check
git status --short
```

Expected: PASS. Do not run the launcher or point tests at
`D:\AgentProjectData\AgentForge\database\agentforge.sqlite3` in this task.

- [ ] **Step 6: Commit the safe schema migration**

```powershell
git add backend/app/storage/database.py backend/app/storage/migrations.py backend/app/storage/orm.py backend/tests/test_storage_migrations.py
git commit -m "feat: persist resolved approval snapshots"
```

### Task 5: Approval snapshot binding and operator read models

**Files:**

- Modify: `backend/app/approvals/service.py`
- Modify: `backend/app/schemas/approval.py`
- Modify: `backend/app/api/routes/approvals.py`
- Modify: `backend/app/schemas/operations.py`
- Modify: `backend/app/api/routes/operations.py`
- Modify: `backend/tests/test_approval_workflow.py`
- Modify: `backend/tests/test_api.py`

**Interfaces:**

- Consumes: serialized `ResolvedExecutionSnapshot` list in `PlanRecord.plan_json["resolved_steps"]`.
- Produces: `ApprovalService.assert_snapshot_allowed(snapshot)`, persisted approval document with `schema_version: 1` and an ordered `steps` list, and API/read-model exposure.
- Existing `assert_execution_allowed(task_id, plan_id, plan_version)` remains for ToolGateway compatibility; Runtime must additionally call `assert_snapshot_allowed()`.

- [ ] **Step 1: Write approval binding and drift rejection tests**

Update the plan helper to create schema-v2 plans with two serialized resolved
steps. Add tests that assert:

```python
approval = service.create_request(
    task_id=task.id,
    plan_id=plan.id,
    plan_version=plan.version,
    requested_by="requester",
)
assert approval.resolved_snapshot == {
    "schema_version": 1,
    "steps": [snapshot.to_dict(), second_snapshot.to_dict()],
}

service.approve(approval.id, actor="approver")
service.assert_snapshot_allowed(snapshot)
```

Parameterize modified snapshots with `dataclasses.replace()` to reject:

- task ID mismatch;
- plan ID mismatch;
- plan version mismatch;
- capability ID mismatch;
- resolved tool ID mismatch;
- normalized parameter mismatch;
- registry fingerprint mismatch.

Add explicit tests that a legacy approval with `resolved_snapshot=None` cannot
pass `assert_snapshot_allowed()` and a newer PlanRecord version invalidates the
old approval.

- [ ] **Step 2: Run approval tests and confirm snapshot arguments are unsupported**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_approval_workflow.py -q
```

Expected: FAIL because `ApprovalRecord` is not populated and
`assert_snapshot_allowed()` does not exist.

- [ ] **Step 3: Persist exact plan snapshots when requesting approval**

In `create_request()`:

- require `plan.plan_json["schema_version"] == 2`;
- parse every `resolved_steps` item with `ResolvedExecutionSnapshot.from_dict()`;
- require non-empty snapshots and one snapshot per plan step;
- require unique matching `step_id` sets;
- require every snapshot task/plan/version to match the request;
- serialize a fresh approval document with `schema_version: 1` and ordered
  steps matching plan step order;
- assign it to `ApprovalRecord.resolved_snapshot` before flush;
- reject legacy/unresolved plans with `ApprovalError`.

This copies approval semantics; it must not store a mutable reference to the
PlanRecord JSON object.

- [ ] **Step 4: Implement exact snapshot authorization**

Implement:

```python
def assert_snapshot_allowed(
    self,
    snapshot: ResolvedExecutionSnapshot,
) -> ApprovalRecord:
    task, plan = self._validate_binding(
        snapshot.task_id, snapshot.plan_id, snapshot.plan_version
    )
    approval = self._latest_approved(plan.id)
    if task.status != TaskStatus.RUNNING.value or approval is None:
        raise ApprovalError("Resolved execution is not approved")
    approved = self._parse_approved_snapshots(approval)
    matches = [item for item in approved if item.step_id == snapshot.step_id]
    if len(matches) != 1 or matches[0] != snapshot:
        raise ApprovalError("Resolved execution snapshot does not match approval")
    return approval
```

Implement `_latest_approved()` and `_parse_approved_snapshots()` as focused
private helpers using the existing approval query ordering and
`ResolvedExecutionSnapshot.from_dict()`.

It must reuse `_validate_binding()`, require RUNNING state and an APPROVED
approval, parse the approval's structured snapshot, find exactly one matching
step ID, and compare the entire `ResolvedExecutionSnapshot` value. Return the
approval only on exact equality. Missing, duplicate, malformed, legacy, or
drifted data raises `ApprovalError`.

On `approve()`, emit `EXECUTION_SNAPSHOT_APPROVED` with bounded structured JSON
containing approval ID and all resolved steps; preserve the existing `APPROVED`
event for compatibility.

- [ ] **Step 5: Expose resolved snapshots to approval and operations responses**

Add `resolved_snapshot: dict[str, Any] | None` to `ApprovalRead` and
`ApprovalQueueRead`; include it in `_approval_read()`, pending approvals, and
task-detail approval dictionaries. Add API assertions that pending approval
responses show capability, resolved tool, parameters, and fingerprint.

- [ ] **Step 6: Run approval and API regressions**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_approval_workflow.py tests/test_api.py -q
git diff --check
git status --short
```

Expected: PASS; ToolGateway source remains unchanged.

- [ ] **Step 7: Commit approval binding**

```powershell
git add backend/app/approvals/service.py backend/app/schemas/approval.py backend/app/api/routes/approvals.py backend/app/schemas/operations.py backend/app/api/routes/operations.py backend/tests/test_approval_workflow.py backend/tests/test_api.py
git commit -m "feat: bind approvals to resolved execution"
```

### Task 6: Snapshot-only AgentRuntime and executor adapter

**Files:**

- Modify: `backend/app/agent_runtime/runtime.py`
- Modify: `backend/app/agent_runtime/executor.py`
- Modify: `backend/app/agent_runtime/observer.py`
- Modify: `backend/tests/test_agent_runtime.py`

**Interfaces:**

- Consumes: persisted `ResolvedExecutionSnapshot`, `ApprovalService.assert_snapshot_allowed()`, and `CapabilityResolver.verify()`.
- Produces: `RuntimeExecutor.execute()` with a required `snapshot: ResolvedExecutionSnapshot` argument, creating the existing `ToolExecutionRequest` and calling only `ToolGateway.execute()`.
- `AgentRuntime` constructor receives a `CapabilityResolver` verifier; it does not call `resolve()`.

- [ ] **Step 1: Rewrite runtime fixtures to resolved schema and add bypass tests**

Replace `runtime_steps(*tools)` with a helper that builds schema-v2 plan steps
and resolver-produced snapshots. Update `make_plan()` to persist
`resolved_steps` before creating approval.

Add tests named `test_runtime_rejects_unresolved_or_legacy_plan`,
`test_runtime_rejects_snapshot_tool_parameter_and_fingerprint_drift`,
`test_runtime_rejects_tool_removed_after_approval`,
`test_executor_always_calls_tool_gateway_with_snapshot_values`, and
`test_runtime_multi_step_success_and_phase_11_1_failure_behavior`. The first
four must assert rejection before a ToolExecutionRecord exists; the final test
must assert the existing COMPLETE and FAIL state transitions and observations.

Use a recording gateway stub only in the adapter unit test; integration tests
must use the real ToolGateway. Assert no ToolExecutionRecord exists after any
pre-execution rejection.

- [ ] **Step 2: Run runtime tests and observe concrete-tool assumptions fail**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_agent_runtime.py -q
```

Expected: FAIL because Runtime currently reads `step["tool"]` and the adapter
maps human-readable actions.

- [ ] **Step 3: Change RuntimeExecutor into a thin snapshot adapter**

Replace `ACTIONS` and the `step` mapping argument with:

```python
def execute(
    self,
    *,
    task_id: str,
    plan_id: str,
    plan_version: int,
    workspace: str,
    snapshot: ResolvedExecutionSnapshot,
    granted_permission: PermissionLevel,
) -> ToolExecutionResult:
    return self.gateway.execute(
        ToolExecutionRequest(
            task_id=task_id,
            tool_name=snapshot.resolved_tool_id,
            action=snapshot.resolved_action,
            workspace=workspace,
            parameters=snapshot.parameters_dict(),
            granted_permission=granted_permission,
            approved=True,
            plan_id=plan_id,
            plan_version=plan_version,
        )
    )
```

RuntimeExecutor must not contain tool maps, candidate logic, defaults, or
direct executor calls.

- [ ] **Step 4: Make AgentRuntime load, authorize, verify, and consume snapshots**

At run start:

- require `plan_json.schema_version == 2`;
- parse `steps` and `resolved_steps` and require equal non-zero lengths;
- match exactly one snapshot to each step ID;
- reject `tool` or `action` fields in capability steps;
- require capability ID and normalized requested parameters to match the
  snapshot;
- call `ApprovalService.assert_snapshot_allowed(snapshot)`;
- call `self.resolver.verify(snapshot)` to detect removed/disabled tools and
  execution-semantic fingerprint changes;
- derive granted permission from the immutable capability definition returned
  by `CapabilityRegistry.require(snapshot.capability_id)`, without selecting a
  tool;
- call RuntimeExecutor with that snapshot.

Keep existing state transitions and observation decisions. Update observation
audit payloads to use `capability_id`, `resolved_tool_id`, parameters, and
fingerprint. Emit bounded `RUNTIME_EXECUTION` after ToolGateway returns. Do not
persist provider reasoning.

- [ ] **Step 5: Run runtime, approval, and ToolGateway regressions**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_agent_runtime.py tests/test_approval_workflow.py tests/test_tool_execution.py -q
git diff --check
git status --short
```

Expected: PASS; `backend/app/tools/gateway.py` has no diff.

- [ ] **Step 6: Commit runtime integration**

```powershell
git add backend/app/agent_runtime backend/tests/test_agent_runtime.py
git commit -m "feat: execute approved capability snapshots"
```

### Task 7: End-to-end audit, demo data, and operator visibility

**Files:**

- Modify: `scripts/seed_demo.py`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/hooks/useOperations.ts`
- Modify: `frontend/src/pages/Approvals.tsx`
- Modify: `frontend/src/pages/TaskDetail.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `backend/tests/test_api.py`

**Interfaces:**

- Consumes: schema-v2 plan JSON and approval `resolved_snapshot` API fields.
- Produces: a synthetic capability-first demo and UI that displays semantic
  capability, concrete resolved tool, normalized parameters, and fingerprint.
- No new API endpoint is introduced.

- [ ] **Step 1: Add failing backend integration assertions for the full audit chain**

Extend the operations API test to create a plan, request and grant approval,
run AgentRuntime with the real resolver/gateway, then assert the ordered event
set includes:

```python
{
    "CAPABILITY_REQUESTED",
    "CAPABILITY_RESOLVED",
    "EXECUTION_SNAPSHOT_APPROVED",
    "RUNTIME_EXECUTION",
    "TOOL_EXECUTION",
    "RUNTIME_OBSERVATION",
    "RUNTIME_DECISION",
}
```

Parse event JSON and verify the same capability, concrete tool, normalized
parameters, and fingerprint can be followed from resolution through runtime.
Add a multi-step integration case resolving `repository_state` and
`test_verification` to different tools.

- [ ] **Step 2: Add failing frontend tests for actual execution visibility**

Update `App.test.tsx` fixtures and assertions:

```typescript
expect(await screen.findByText('test_verification')).toBeInTheDocument()
expect(screen.getByText('test_run')).toBeInTheDocument()
expect(screen.getByText(/profile: smoke/i)).toBeInTheDocument()
expect(screen.getByText(/Registry fingerprint/i)).toBeInTheDocument()
```

Run:

```powershell
npm test -- --run
```

Expected: FAIL because current types and pages display only `tool` and `action`.

- [ ] **Step 3: Update frontend contracts and demo fallback data**

Define:

```typescript
export type CapabilityPlanStep = {
  step_id: string
  capability_id: 'repository_state' | 'project_metadata' | 'test_verification'
  parameters: Record<string, string>
}

export type ResolvedExecutionSnapshot = {
  task_id: string
  plan_id: string
  plan_version: number
  step_id: string
  capability_id: string
  resolved_tool_id: string
  resolved_action: string
  normalized_parameters: Record<string, string>
  registry_fingerprint: string
}
```

Update Plan, Approval, and ApprovalQueue types with `schema_version: 2`,
`resolved_steps`, and `resolved_snapshot`. Convert local fallback demo data to
the same shape.

- [ ] **Step 4: Display the approved execution snapshot**

In Approval Center and Task Detail, render each step as:

```text
Capability: test_verification
Resolved tool: test_run · run_profile
Parameters: profile: smoke
Registry fingerprint: <first 12 hex characters>
Permission: APPROVED_EXEC
```

Use existing pills and layout classes where possible. Do not add a new page or
design system. The UI must not imply that the model selected the tool.

- [ ] **Step 5: Convert seed_demo.py without touching existing runtime data**

Update `build_plan()` to produce schema-v2 steps and deterministic serialized
resolved snapshots. Set `ApprovalRecord.resolved_snapshot` for newly seeded
pending and approved records. Add the four capability/audit event types using
bounded JSON. Preserve idempotency: if demo data already exists, the script
still reports no change. Do not run `seed_demo.py` during implementation tests,
because this task must not mutate the existing external demo database.

- [ ] **Step 6: Run integration and frontend tests**

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_api.py tests/test_agent_runtime.py -q
cd ..\frontend
npm test -- --run
npm run build
cd ..
git diff --check
git status --short
```

Expected: all commands PASS; no `dist`, database, logs, cache, or temporary
files are tracked or newly left in the repository.

- [ ] **Step 7: Commit integration and operator visibility**

```powershell
git add scripts/seed_demo.py frontend/src/types/index.ts frontend/src/hooks/useOperations.ts frontend/src/pages/Approvals.tsx frontend/src/pages/TaskDetail.tsx frontend/src/App.test.tsx backend/tests/test_api.py
git commit -m "feat: expose resolved capability approvals"
```

### Task 8: Full regression, documentation, and Phase 11.2 hygiene

**Files:**

- Modify: `PROJECT_CONTEXT.md`
- Modify: `README.md`
- Test: all `backend/tests/`
- Test: frontend Vitest suite and production build

**Interfaces:**

- Consumes: completed Tasks 1-7.
- Produces: verified Phase 11.2 status and accurate architecture documentation.

- [ ] **Step 1: Run the complete backend suite with bounded logging**

Run from repository root, storing the full log outside source:

```powershell
$phaseLog = 'D:\AgentProjectData\AgentForge\test-runs\phase-11-2-backend.log'
New-Item -ItemType Directory -Force (Split-Path $phaseLog) | Out-Null
Push-Location backend
.\.venv\Scripts\python.exe -m pytest -q *> $phaseLog
$backendExit = $LASTEXITCODE
Pop-Location
Get-Content $phaseLog -Tail 80
if ($backendExit -ne 0) { exit $backendExit }
```

Expected: all backend tests PASS. The known Starlette/httpx deprecation warning
may remain; no new warning is accepted without investigation.

- [ ] **Step 2: Run frontend tests and build with bounded logs**

```powershell
$frontendTestLog = 'D:\AgentProjectData\AgentForge\test-runs\phase-11-2-frontend-test.log'
$frontendBuildLog = 'D:\AgentProjectData\AgentForge\test-runs\phase-11-2-frontend-build.log'
Push-Location frontend
npm test -- --run *> $frontendTestLog
$testExit = $LASTEXITCODE
npm run build *> $frontendBuildLog
$buildExit = $LASTEXITCODE
Pop-Location
Get-Content $frontendTestLog -Tail 50
Get-Content $frontendBuildLog -Tail 50
if ($testExit -ne 0) { exit $testExit }
if ($buildExit -ne 0) { exit $buildExit }
```

Expected: frontend tests and TypeScript/Vite build PASS.

- [ ] **Step 3: Update project context and README only after verification passes**

Add Phase 11.2 to `PROJECT_CONTEXT.md` with:

- capability-first planner schema;
- deterministic resolver with exactly-one-candidate semantics;
- approval-bound resolved snapshots and registry fingerprints;
- non-destructive SQLite migration;
- Runtime consumption through existing ToolGateway;
- the three MVP capability mappings.

Update README architecture/status and security bullets to match implemented
behavior. Preserve the statement that real external LLM, Docker, PostgreSQL,
RBAC, and write-capable tools have not started.

- [ ] **Step 4: Perform spec coverage and security invariant review**

Verify with exact searches:

```powershell
rg -n 'tool\s*[:=]|\["tool"\]|\.tool' backend/app/agents/planner backend/app/agent_runtime
rg -n 'gateway\.execute|\.executor\.execute' backend/app
rg -n 'NotImplementedError|shell=True|pass\s*(#.*)?$' backend/app backend/tests frontend/src scripts PROJECT_CONTEXT.md README.md
```

Expected:

- no new-plan or Runtime path consumes a concrete `tool` field;
- RuntimeExecutor calls `gateway.execute()` and no parallel direct executor path exists;
- `shell=True` is absent;
- no unfinished markers are present;
- any remaining concrete tool references belong only to ToolRegistry,
  ToolGateway requests, execution records, or display-only legacy parsing.

- [ ] **Step 5: Run final diff and repository hygiene checks**

```powershell
git diff --check
git status --short
git diff --stat
git ls-files | rg '(^|/)(dist|logs|cache|temp|uploads|artifacts|traces)/|\.sqlite3$|\.env$'
```

Expected: only intentional source, tests, docs, and demo source changes; no
runtime database, generated build output, secrets, temporary/debug files, or
new top-level directory. `backend/app/tools/gateway.py` must be unchanged.

- [ ] **Step 6: Commit documentation and verified completion**

```powershell
git add PROJECT_CONTEXT.md README.md
git commit -m "docs: record capability selection phase"
git status --short --branch
```

Expected: clean working tree on the implementation branch. Do not push unless
the user explicitly asks.

## Execution Notes

- Execute this plan in an isolated worktree created by
  `superpowers:using-git-worktrees` before Task 1.
- Recommended execution mode is `superpowers:subagent-driven-development`,
  with one fresh implementer per task and review after every commit.
- If multi-agent tools are unavailable, use `superpowers:executing-plans` in
  the same isolated worktree and preserve each task's test and commit gate.
- Do not initialize or migrate the user's live demo database as part of the
  test run. The migration is exercised against isolated in-memory SQLite and
  will apply to the live database only when the user later launches the updated
  backend.
