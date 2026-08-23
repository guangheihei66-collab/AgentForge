# Local Project Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. The user has prohibited parallel subagents for Phase 14.

**Goal:** Add local Projects as execution-security boundaries so every new Task plans, receives approval, and executes only within one validated local workspace and explicit semantic Capability allow-list.

**Architecture:** Add one `projects` aggregate and nullable legacy `tasks.project_id`, then derive an immutable application-owned `ProjectExecutionContext` for Planner, Replanner, ApprovalService, Runtime, and ToolGateway. Store deterministic Project authority in existing Plan JSON and `ApprovalRecord.resolved_snapshot`; revalidate it before every step while preserving the existing CapabilityResolver and ToolGateway.

**Tech Stack:** Python 3, FastAPI, Pydantic, SQLAlchemy, SQLite, pytest, React 19, TypeScript, Vitest, existing AgentForge ToolGateway and WorkspaceValidator.

**Spec:** `docs/superpowers/specs/2026-08-23-local-project-workspace-design.md`

## Global Constraints

- Work only in the existing `feature/phase-12-real-llm-provider` worktree; do not create a branch/worktree, merge, push, or use parallel subagents.
- Production source stays under `D:\AgentProjects\AgentForge`; mutable/runtime data stays under `D:\AgentProjectData\AgentForge`.
- Do not touch the live database `D:\AgentProjectData\AgentForge\database\agentforge.sqlite3`; migration tests use isolated temporary SQLite files only. Live migration and its required timestamped D-drive backup are a later separately approved operation.
- Add no dependency, `.venv`, `node_modules`, Docker asset, model, external API call, large fixture repository, or unbounded log.
- Use one primary backend feature file only: `backend/tests/test_phase_14_local_project_workspace.py`.
- Project Capability policy is a JSON list of semantic Capability IDs, default `[]`; future registry additions remain disabled.
- Project status is exactly `ACTIVE` or `ARCHIVED`; no hard delete or reactivation API.
- Workspace roots are existing canonical local directories; UNC, network, device, relative, file, traversal, junction/reparse, symlink, and cross-project escapes fail closed.
- `environment` remains descriptive in Phase 14: it is excluded from authority fingerprinting and does not increment `config_version`.
- The authority fingerprint is SHA-256 of compact, sorted-key UTF-8 JSON containing exactly `authority_schema_version`, `project_id`, `config_version`, the `ntpath.normcase(ntpath.normpath(strictly_resolved_root))` workspace authority key, sorted `allowed_capability_ids`, and `status`.
- Name, description, environment, UI labels, and timestamps are excluded from execution authority.
- New API Tasks require Project binding; null-Project legacy Tasks stay readable/reportable but cannot plan, approve, execute, or Replan.
- The model never receives or controls absolute workspace, cwd, Project ID, config version, fingerprint, Tool ID, or approval authority.
- Run Phase 14 tests primarily. Run one final backend regression, frontend tests, and frontend production build near completion; keep complete logs under `D:\VSCodeData\AgentDev\Temp` and print bounded tails.

## Preflight

- [ ] Verify the exact development line before edits.

```powershell
git rev-parse --show-toplevel
git branch --show-current
git status --short
git log -5 --oneline
```

Expected: linked worktree root, branch `feature/phase-12-real-llm-provider`, clean status, and starting HEAD `5522e26`.

- [ ] Record bounded disk headroom without scanning drives.

```powershell
"C_FREE=$((Get-PSDrive C).Free)"
"D_FREE=$((Get-PSDrive D).Free)"
```

Stop if an operation would exceed 1 GiB or unexpected growth exceeds about 500 MiB.

---

### Task 1: Project Persistence and Isolated Migration Foundation

**Files:**
- Create: `backend/app/projects/__init__.py`
- Create: `backend/app/projects/models.py`
- Create: `backend/app/storage/repositories/project_repository.py`
- Modify: `backend/app/storage/repositories/__init__.py`
- Modify: `backend/app/storage/orm.py`
- Modify: `backend/app/storage/migrations.py`
- Modify: `backend/app/domain/models/entities.py`
- Modify: `backend/app/storage/repositories/task_repository.py`
- Test: `backend/tests/test_phase_14_local_project_workspace.py`

**Interfaces:**
- Produces `ProjectStatus`, `Project`, `ProjectRecord`, `ProjectRepository`, and nullable `Task.project_id`.
- Migration keeps all existing Task rows with `project_id IS NULL`; it does not alter Approval, Evidence, or Audit schemas.

- [ ] **Step 1: Write persistence and migration tests first**

Create the one Phase 14 test file with an isolated Project fixture and tests equivalent to:

```python
def test_project_record_uses_uuid_dates_empty_policy_and_active_status(db_session, tmp_path):
    workspace = tmp_path / "project-a"
    workspace.mkdir()
    project = ProjectRepository(db_session).create(Project.new(
        name="Project A", description=None, workspace_root=str(workspace),
        environment="development", allowed_capability_ids=(),
    ))
    assert project.status is ProjectStatus.ACTIVE
    assert project.allowed_capability_ids == ()
    assert project.config_version == 1


def test_sqlite_migration_adds_nullable_project_binding_without_rewriting_history(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'legacy.sqlite3'}")
    create_phase_13_schema_fixture(engine, task_id="legacy-task")
    Base.metadata.create_all(engine)
    migrate_sqlite_schema(engine)
    migrate_sqlite_schema(engine)
    columns = {item["name"] for item in inspect(engine).get_columns("tasks")}
    assert "project_id" in columns
    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT id, project_id FROM tasks WHERE id='legacy-task'"
        ).one()
    assert row == ("legacy-task", None)
    assert "projects" in inspect(engine).get_table_names()
```

The helper creates only the minimum old `tasks`, `plans`, `approvals`, `audit_events`, and `evidence` rows needed to prove counts and IDs remain unchanged. It must never use the configured live database URL.

- [ ] **Step 2: Run the focused tests and verify RED**

```powershell
D:\AgentProjects\AgentForge\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase_14_local_project_workspace.py -q
```

Expected: collection/import failures for missing Project types or assertions showing `tasks.project_id` absent.

- [ ] **Step 3: Add the minimal domain and ORM records**

Define exact contracts:

```python
class ProjectStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


@dataclass(slots=True)
class Project:
    id: str
    name: str
    description: str | None
    workspace_root: str
    environment: str
    status: ProjectStatus
    allowed_capability_ids: tuple[str, ...]
    config_version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def new(cls, *, name: str, description: str | None, workspace_root: str,
            environment: str, allowed_capability_ids: tuple[str, ...]) -> "Project":
        now = datetime.now(timezone.utc)
        return cls(str(uuid4()), name, description, workspace_root, environment,
                   ProjectStatus.ACTIVE, allowed_capability_ids, 1, now, now)
```

`ProjectRecord` mirrors the approved field lengths and stores `allowed_capability_ids` in `JSON`. Add `TaskRecord.project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)` and carry it through `Task` and `TaskRepository` without changing `tasks.workspace` yet.

- [ ] **Step 4: Extend the idempotent SQLite migration**

Keep the existing approval migration and add bounded inspection:

```python
task_columns = {column["name"] for column in inspect(bind).get_columns("tasks")}
if "project_id" not in task_columns:
    with bind.begin() as connection:
        connection.exec_driver_sql(
            "ALTER TABLE tasks ADD COLUMN project_id VARCHAR(36) REFERENCES projects(id)"
        )
```

Verify the column after alteration. `Base.metadata.create_all()` creates `projects`; migration must not issue DROP, DELETE, UPDATE, reset, or recreate statements.

- [ ] **Step 5: Run Phase 14 tests GREEN and inspect only isolated DB metadata**

```powershell
D:\AgentProjects\AgentForge\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase_14_local_project_workspace.py -q
```

Expected: persistence/migration tests pass; no file appears under `D:\AgentProjectData\AgentForge`.

- [ ] **Step 6: Keep Task 1 uncommitted until Task 2**

Task 2 completes the coherent `Project persistence + workspace authority` commit.

---

### Task 2: Workspace Canonicalization and Project Authority

**Files:**
- Create: `backend/app/projects/authority.py`
- Create: `backend/app/projects/service.py`
- Modify: `backend/app/projects/__init__.py`
- Modify: `backend/app/workspace/validator.py`
- Modify: `backend/app/capabilities/registry.py`
- Test: `backend/tests/test_phase_14_local_project_workspace.py`

**Interfaces:**
- Produces immutable `ProjectExecutionContext` and `ProjectAuthoritySnapshot`.
- Produces `ProjectService.create`, `update`, `archive`, `execution_context`, and `assert_authority`.
- Produces `CapabilityRegistry.subset(allowed_ids)` for exact global/project intersection.

- [ ] **Step 1: Add RED tests for root validation and canonical descendants**

Cover absolute existing directories, ordinary files, missing and relative roots, UNC/device syntax, mixed separators, case-equivalent roots, `..`, sibling-prefix (`App` versus `App-Other`), absolute target injection, cross-drive/root, and symlink/junction escape. Representative assertions:

```python
def test_canonical_descendant_rejects_sibling_prefix(tmp_path):
    root = tmp_path / "App"
    sibling = tmp_path / "App-Other"
    root.mkdir(); sibling.mkdir()
    validator = WorkspaceValidator.for_project(root)
    with pytest.raises(WorkspaceValidationError):
        validator.validate_target(root, sibling.resolve())


@pytest.mark.parametrize("value", [r"\\server\share", r"\\?\UNC\server\share"])
def test_project_workspace_rejects_unc(value):
    with pytest.raises(WorkspaceValidationError):
        WorkspaceValidator.canonicalize_project_root(value)
```

Use platform-safe skips only for junction/symlink creation permission; never weaken production assertions because a fixture cannot create a link.

- [ ] **Step 2: Run the targeted path tests RED**

```powershell
D:\AgentProjects\AgentForge\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase_14_local_project_workspace.py -q -k "workspace or descendant or symlink or junction"
```

Expected: missing canonicalization/scoped-validator APIs.

- [ ] **Step 3: Extend the existing WorkspaceValidator**

Add, rather than duplicate, these interfaces:

```python
@classmethod
def canonicalize_project_root(cls, value: str | Path) -> Path:
    raw = str(value).strip()
    if not raw or raw.startswith(("\\\\", "\\\\?\\", "\\\\.\\")):
        raise WorkspaceValidationError("Workspace must be a local path")
    candidate = Path(raw)
    if not candidate.is_absolute():
        raise WorkspaceValidationError("Workspace must be an absolute path")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_dir():
        raise WorkspaceValidationError("Workspace must be a directory")
    cls._reject_system_or_user_root_static(resolved)
    cls._reject_remote_drive(resolved)
    return resolved

@classmethod
def for_project(cls, root: str | Path) -> "WorkspaceValidator":
    return cls(cls.canonicalize_project_root(root))

@staticmethod
def authority_path_key(path: str | Path) -> str:
    return ntpath.normcase(ntpath.normpath(str(Path(path).resolve(strict=True))))

def validate_target(self, workspace: str | Path, target: str | Path) -> Path:
    root = self.validate_workspace(workspace)
    resolved = Path(target).resolve(strict=True)
    root_key = self.authority_path_key(root)
    target_key = self.authority_path_key(resolved)
    if os.path.commonpath((root_key, target_key)) != root_key:
        raise WorkspaceValidationError("Target escapes the Project workspace")
    return resolved
```

Use `Path.resolve(strict=True)` and `os.path.commonpath` on authority keys; equality with the root is allowed and sibling string prefixes are not. Reject UNC/device prefixes before `Path` resolution and reject remote drives with bounded Windows drive-type inspection where available. `validate_relative_file` delegates to the shared descendant rule after rejecting absolute input and secrets.

- [ ] **Step 4: Add RED authority/version/policy tests**

Test empty default, unknown/duplicate/over-64 policies, deterministic sorting, future registry default deny, ACTIVE-root uniqueness, optimistic version conflict, cosmetic edits preserving version/fingerprint, workspace/policy/archive changes incrementing and changing fingerprint, and environment edits preserving authority.

```python
def test_project_authority_fingerprint_excludes_cosmetic_fields(project_service, project):
    before = project_service.execution_context(project.id)
    project_service.update(project.id, expected_config_version=1,
                           name="Renamed", description="Cosmetic", environment="test")
    after = project_service.execution_context(project.id)
    assert after.config_version == before.config_version
    assert after.authority_fingerprint == before.authority_fingerprint
```

- [ ] **Step 5: Implement Project authority and service minimally**

Use frozen dataclasses. The fingerprint document must be exactly:

```python
document = {
    "authority_schema_version": 1,
    "project_id": project.id,
    "config_version": project.config_version,
    "workspace_root": WorkspaceValidator.authority_path_key(project.workspace_root),
    "allowed_capability_ids": sorted(project.allowed_capability_ids),
    "status": project.status.value,
}
digest = hashlib.sha256(json.dumps(
    document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
).encode("utf-8")).hexdigest()
```

Define:

```python
@dataclass(frozen=True, slots=True)
class ProjectExecutionContext:
    project_id: str
    config_version: int
    workspace_root: str
    workspace_authority_key: str
    allowed_capability_ids: tuple[str, ...]
    status: ProjectStatus
    authority_fingerprint: str

    def authority_snapshot(self) -> "ProjectAuthoritySnapshot":
        return ProjectAuthoritySnapshot(
            project_id=self.project_id,
            config_version=self.config_version,
            authority_fingerprint=self.authority_fingerprint,
            canonical_workspace_root=self.workspace_authority_key,
        )
```

`ProjectAuthoritySnapshot.to_dict/from_dict` uses exact fields `project_id`, `config_version`, `authority_fingerprint`, and `canonical_workspace_root`. `ProjectService.execution_context(project_id)` freshly canonicalizes the root, validates all policy IDs against the global registry, requires ACTIVE, and returns the context. `assert_authority(task_project_id, snapshot)` compares every field and recomputed fingerprint.

- [ ] **Step 6: Add and test exact capability intersection**

Implement `CapabilityRegistry.subset(allowed_ids: Iterable[str]) -> CapabilityRegistry`; require every ID and register only sorted explicitly allowed definitions. Empty input returns an empty registry. It never reads Tool IDs or mutates the global registry.

```powershell
D:\AgentProjects\AgentForge\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase_14_local_project_workspace.py -q
```

Expected: Task 1-2 tests pass.

- [ ] **Step 7: Commit persistence and workspace authority**

```powershell
git add backend/app/projects backend/app/storage backend/app/domain/models/entities.py backend/app/workspace/validator.py backend/app/capabilities/registry.py backend/tests/test_phase_14_local_project_workspace.py
git diff --cached --check
git commit -m "feat: add project workspace authority"
```

---

### Task 3: Task-to-Project Binding and Legacy Compatibility

**Files:**
- Modify: `backend/app/services/task_service.py`
- Modify: `backend/app/storage/repositories/task_repository.py`
- Modify: `backend/app/schemas/task.py`
- Modify: `backend/app/schemas/operations.py`
- Modify: `backend/app/api/routes/tasks.py`
- Modify: `backend/app/api/routes/operations.py`
- Modify existing fixture setup in: `backend/tests/conftest.py`
- Modify adjacent tests only as required for the new service contract: `backend/tests/test_repository.py`, `backend/tests/test_planner.py`, `backend/tests/test_agent_runtime.py`, `backend/tests/test_approval_workflow.py`, `backend/tests/test_tool_execution.py`, `backend/tests/test_phase_11_2_capability_tool_selection.py`, `backend/tests/test_phase_12_real_llm_provider.py`, `backend/tests/test_phase_13_controlled_replanning.py`
- Test: `backend/tests/test_phase_14_local_project_workspace.py`

**Interfaces:**
- `TaskService.create_task(*, title: str, goal: str, project_id: str) -> Task` derives workspace from Project.
- Normal Task API uses strict Pydantic input and cannot create null-Project Tasks.
- A test-only fixture helper may insert historical null-Project rows directly through `TaskRepository`; production service exposes no legacy creation path.

- [ ] **Step 1: Write RED Task binding and API-injection tests**

```python
def test_new_task_requires_active_project_and_derives_workspace(client, project):
    response = client.post("/tasks", json={
        "project_id": project.id, "title": "Check", "goal": "Verify release"
    })
    assert response.status_code == 201
    assert response.json()["project_id"] == project.id
    assert response.json()["workspace"] == project.workspace_root


@pytest.mark.parametrize("field,value", [
    ("workspace", r"D:\Other"), ("workspace_root", r"D:\Other"),
    ("tool_id", "git_read"), ("config_version", 999),
    ("authority_fingerprint", "0" * 64),
])
def test_task_payload_rejects_authority_injection(client, project, field, value):
    payload = {"project_id": project.id, "title": "Check", "goal": "Goal", field: value}
    assert client.post("/tasks", json=payload).status_code == 422
```

Also test nonexistent/ARCHIVED Project rejection, `project_id` immutability, legacy Task detail/report readability, and all planning/approval/runtime/replan entry points rejecting `project_id = NULL`.

- [ ] **Step 2: Run Task/legacy tests RED**

```powershell
D:\AgentProjects\AgentForge\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase_14_local_project_workspace.py -q -k "task or legacy or payload or archived"
```

- [ ] **Step 3: Make Task creation server-owned**

Use strict schemas:

```python
class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str = Field(min_length=36, max_length=36)
    title: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, max_length=5000)
```

`TaskService` loads `ProjectService.execution_context(project_id)`, writes `project_id`, and copies `context.workspace_root` only into the legacy display column. There is no Task project PATCH. Add `project_id: str | None` to Task read/operations models so historical rows remain serializable.

- [ ] **Step 4: Add a deliberate historical fixture helper and migrate adjacent tests**

In `conftest.py`, provide `create_test_project(session, tmp_path, capabilities)` for executable tests and `create_legacy_task_record(session, workspace)` only for explicit legacy-read tests. Update existing Planner/Runtime/Approval/Phase 11-13 helpers to create tiny `tmp_path` Project records and pass `project_id`; do not point automated tests at the real AgentForge tree. Preserve old behavior assertions while adding Project authority.

- [ ] **Step 5: Run focused Task and adjacent repository/API tests**

```powershell
D:\AgentProjects\AgentForge\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase_14_local_project_workspace.py backend/tests/test_repository.py backend/tests/test_api.py -q
```

- [ ] **Step 6: Keep Task 3 uncommitted until Task 4**

Task 4 completes the coherent `Task/Capability/Planner integration` commit.

---

### Task 4: Effective Capability Policy in Planner and Replanner

**Files:**
- Modify: `backend/app/agents/planner/planner.py`
- Modify: `backend/app/agents/planner/prompts.py`
- Modify: `backend/app/agents/planner/validator.py`
- Modify: `backend/app/agents/replanning/service.py`
- Modify: `backend/app/agents/replanning/prompts.py`
- Modify: `backend/app/api/routes/planning.py`
- Modify adjacent existing tests listed in Task 3 as required
- Test: `backend/tests/test_phase_14_local_project_workspace.py`

**Interfaces:**
- Planner and Replanner load `ProjectExecutionContext` from Task binding and use `global_registry.subset(context.allowed_capability_ids)`.
- Every new Plan JSON has `project_authority = context.authority_snapshot().to_dict()`.
- Prompt builders receive only the filtered registry and bounded cosmetic Project summary; absolute workspace is absent.

- [ ] **Step 1: Add RED Planner/Replanner policy tests**

Cover empty policy failure, allowed-only prompt catalog, model-proposed disallowed capability failure, newly registered future capability remaining absent, Project/workspace fields forbidden in provider payload, Project drift during provider response, and successor Plans retaining the same Task Project.

```python
def test_planner_prompt_contains_only_effective_capabilities(
    db_session, project_task, capturing_provider
):
    PlannerAgent(db_session, capturing_provider).create_plan(project_task.id)
    prompt = capturing_provider.requests[0].prompt
    assert "repository_state" in prompt
    assert "test_verification" not in prompt
    assert project_task.workspace not in prompt


def test_replanner_cannot_expand_project_capabilities(
    db_session, project_task, plan_v1
):
    provider = PayloadReplanProvider({
        "decision_summary": "expand",
        "revised_remaining_steps": [{
            "step_id": "forbidden", "capability_id": "test_verification",
            "parameters": {"profile": "smoke"},
        }],
    })
    outcome = ReplanningService(db_session, provider).create_successor(
        task_id=project_task.id,
        current_plan_id=plan_v1.id,
        current_plan_version=plan_v1.version,
        observation=replan_observation(),
        completed_steps=(failed_step_summary(),),
        attempted_steps=2,
    )
    assert outcome.status is ReplanOutcomeStatus.FAILED
    assert db_session.query(PlanRecord).filter_by(task_id=project_task.id).count() == 1
```

- [ ] **Step 2: Run Planner/Replanner tests RED**

```powershell
D:\AgentProjects\AgentForge\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase_14_local_project_workspace.py -q -k "planner or replanner or effective or future_capability"
```

- [ ] **Step 3: Integrate ProjectExecutionContext into planning**

At the start of planning:

```python
context = self.projects.execution_context_for_task(task_id)
effective_registry = self.capability_registry.subset(context.allowed_capability_ids)
project_summary = {"name": project.name, "environment": project.environment,
                   "description": (project.description or "")[:500]}
```

Build prompts from `effective_registry`; never add `workspace_root`, authority key, fingerprint, config version, Tool IDs, or approval data. Validate and resolve against the same registry and a `WorkspaceValidator.for_project(context.workspace_root)`. Persist `project_authority` beside `resolved_steps` before committing the Plan.

Change constructors to the exact application-owned forms `PlannerAgent(session: Session, provider: LLMProvider)` and `ReplanningService(session: Session, provider: LLMProvider)`. Each constructs `ProjectService(session, build_default_capability_registry())`; tests may replace the service/registry attributes with isolated deterministic fixtures. Remove `AGENTFORGE_WORKSPACE_ROOT` reads from the planning route because persisted Project configuration is now the authority.

- [ ] **Step 4: Integrate the same authority into Replanning**

Before policy/provider calls, reload context, assert current Plan authority, and build the Replan prompt from the effective registry. After provider response, reload and assert authority again before creating v2. Successor Plan copies the current authority snapshot; it cannot accept Project/workspace fields from `ReplanProposal`.

- [ ] **Step 5: Run Phase 14 plus focused Phase 11.2-13 integration tests**

```powershell
D:\AgentProjects\AgentForge\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase_14_local_project_workspace.py backend/tests/test_phase_11_2_capability_tool_selection.py backend/tests/test_phase_12_real_llm_provider.py backend/tests/test_phase_13_controlled_replanning.py -q
```

Expected: Project policy tests and prior capability/provider/replanning behavior pass offline.

- [ ] **Step 6: Commit Task/Capability/Planner integration**

```powershell
git add backend/app/services backend/app/schemas backend/app/api/routes/tasks.py backend/app/api/routes/operations.py backend/app/api/routes/planning.py backend/app/agents backend/app/storage/repositories/task_repository.py backend/tests
git diff --cached --check
git commit -m "feat: bind tasks and planning to projects"
```

Verify the staged list contains no new Phase 14 test module besides `test_phase_14_local_project_workspace.py`.

---

### Task 5: Approval Snapshot and Runtime/ToolGateway Drift Enforcement

**Files:**
- Modify: `backend/app/approvals/service.py`
- Modify: `backend/app/agent_runtime/runtime.py`
- Modify: `backend/app/agent_runtime/executor.py`
- Modify: `backend/app/tools/gateway.py`
- Modify: `backend/app/agents/replanning/service.py`
- Test: `backend/tests/test_phase_14_local_project_workspace.py`
- Modify adjacent tests: `backend/tests/test_approval_workflow.py`, `backend/tests/test_agent_runtime.py`, `backend/tests/test_tool_execution.py`, `backend/tests/test_phase_13_controlled_replanning.py`

**Interfaces:**
- Approval JSON schema version 2 contains one top-level `project_authority` and existing resolved `steps`.
- `ApprovalService.assert_project_execution_allowed(*, task_id: str, plan_id: str | None, plan_version: int | None, workspace: str, authority_fingerprint: str | None) -> ApprovalRecord` verifies Task/Project/Plan/Approval/workspace authority for all permissions, including SAFE_READ.
- ToolGateway remains the only executor boundary and receives application-owned authority from RuntimeExecutor.

- [ ] **Step 1: Add RED approval snapshot tests**

```python
def test_approval_snapshot_binds_project_authority(approved_project_plan):
    document = approved_project_plan.approval.resolved_snapshot
    assert document["schema_version"] == 2
    assert document["project_authority"] == {
        "project_id": approved_project_plan.project.id,
        "config_version": 1,
        "authority_fingerprint": approved_project_plan.fingerprint,
        "canonical_workspace_root": approved_project_plan.authority_key,
    }
    assert document["steps"][0]["task_id"] == approved_project_plan.task.id
```

Also assert schema-version-1 legacy approvals remain readable in API/audit but cannot execute.

- [ ] **Step 2: Add RED drift and cross-project security matrix**

Parameterize old Approval rejection after workspace change, capability removal, capability addition, archive, stale version, stale fingerprint, Project B snapshot, Task project substitution, Project B policy reuse, and Project B absolute/traversal/link target. Prove name/description/environment-only edits leave existing approval executable.

For every rejection, assert no successful ToolExecution/Evidence is created and ToolGateway records only a bounded rejection where its current behavior does so.

- [ ] **Step 3: Run approval/runtime security tests RED**

```powershell
D:\AgentProjects\AgentForge\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase_14_local_project_workspace.py -q -k "approval or drift or cross_project or archived or gateway"
```

- [ ] **Step 4: Version the existing approval document**

Update `_snapshot_document` to require Plan `project_authority`, call `ProjectService.assert_authority`, and return:

```python
{
    "schema_version": 2,
    "project_authority": authority.to_dict(),
    "steps": ordered_existing_snapshots,
}
```

Do not add `ApprovalRecord` fields or a second approval service. Parse schema 2 strictly for execution. Preserve schema 1 only for read serialization.

- [ ] **Step 5: Revalidate fresh authority before every Runtime step**

Runtime loads context from `task.project_id`, compares Plan and Approval authority, confirms the Capability remains allowed, then calls `resolver.verify`. It passes `context.workspace_root` and `context.authority_fingerprint`, never `task.workspace`, to RuntimeExecutor. Reload context inside the loop before each step so archive/config changes between steps fail closed.

- [ ] **Step 6: Add the small ToolGateway enforcement extension**

Extend `ToolExecutionRequest` with application-owned `project_authority_fingerprint: str | None`. For every Project-bound Task, before permission policy or executor invocation, ToolGateway calls:

```python
ApprovalService(self.session).assert_project_execution_allowed(
    task_id=request.task_id,
    plan_id=request.plan_id,
    plan_version=request.plan_version,
    workspace=request.workspace,
    authority_fingerprint=request.project_authority_fingerprint,
)
```

This check applies to SAFE_READ and APPROVED_EXEC. Null-Project Tasks fail before execution. Keep existing permission and `APPROVED_EXEC` checks as defense in depth; do not duplicate ToolGateway or let direct callers select a Project root.

- [ ] **Step 7: Run focused security and adjacent suites**

```powershell
D:\AgentProjects\AgentForge\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase_14_local_project_workspace.py backend/tests/test_approval_workflow.py backend/tests/test_agent_runtime.py backend/tests/test_tool_execution.py backend/tests/test_phase_13_controlled_replanning.py -q
```

- [ ] **Step 8: Commit approval/runtime security enforcement**

```powershell
git add backend/app/approvals backend/app/agent_runtime backend/app/tools backend/app/agents/replanning backend/app/schemas/approval.py backend/tests
git diff --cached --check
git commit -m "feat: enforce project authority at runtime"
```

---

### Task 6: Project API and Minimal Frontend Experience

**Files:**
- Create: `backend/app/schemas/project.py`
- Create: `backend/app/api/routes/projects.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/projects/service.py`
- Modify: `backend/app/storage/repositories/project_repository.py`
- Modify: `backend/app/schemas/operations.py`
- Modify: `backend/app/api/routes/operations.py`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/hooks/useOperations.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Shell.tsx`
- Create: `frontend/src/pages/Projects.tsx`
- Create: `frontend/src/pages/ProjectDetail.tsx`
- Modify: `frontend/src/styles/app.css`
- Modify: `frontend/src/App.test.tsx`
- Test: `backend/tests/test_phase_14_local_project_workspace.py`

**Interfaces:**
- Backend routes: `GET/POST /projects`, `GET/PATCH /projects/{id}`, `POST /projects/{id}/archive`, `POST /projects/validate-workspace`.
- Frontend sends Project configuration only to Project endpoints and `{project_id,title,goal}` to Task creation.
- No DELETE, unarchive, filesystem listing, Organization, user, team, RBAC, or analytics route/page.

- [ ] **Step 1: Add RED API tests**

Test strict create/update schemas, canonical server response, empty default policy, unknown Capability rejection, duplicate ACTIVE root conflict, optimistic version conflict, cosmetic PATCH, security PATCH version increment, archive behavior, bounded recent Tasks, validation-only response without directory contents, missing DELETE route, and explicit CORS PATCH allowance.

Use response status conventions: 201 create, 200 reads/patch/archive, 404 missing, 409 duplicate/stale version, 422 malformed request, and 400 unsafe workspace/policy.

- [ ] **Step 2: Implement strict Project API schemas and routes**

All write schemas use `ConfigDict(extra="forbid")`. Representative contracts:

```python
class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    workspace_root: str = Field(min_length=1, max_length=1000)
    environment: str = Field(min_length=1, max_length=64)
    allowed_capability_ids: list[str] = Field(default_factory=list, max_length=64)


class ProjectPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_config_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    workspace_root: str | None = Field(default=None, min_length=1, max_length=1000)
    environment: str | None = Field(default=None, min_length=1, max_length=64)
    allowed_capability_ids: list[str] | None = Field(default=None, max_length=64)
```

Archive has its own `{expected_config_version}` body. Validate-workspace returns only `{valid, canonical_workspace_root}` or a bounded error; never list files.

- [ ] **Step 3: Register routes and adjust CORS minimally**

Include `projects_router` in `main.py` and change `allow_methods` from `GET, POST, OPTIONS` to `GET, POST, PATCH, OPTIONS`. Do not permit DELETE.

- [ ] **Step 4: Add RED frontend tests in the existing file**

Mock API responses and cover Projects navigation/list, explicit empty capability selection, create validation state, Project detail, Create Task sending no workspace/tool authority, and archived actions disabled.

```typescript
expect(JSON.parse(String(taskCall?.[1]?.body))).toEqual({
  project_id: 'project-a', title: 'Release check', goal: 'Check readiness',
})
expect(String(taskCall?.[1]?.body)).not.toContain('workspace')
```

- [ ] **Step 5: Run frontend tests RED**

```powershell
Set-Location frontend
npm test
```

Expected: missing Project pages/types/API behavior. Do not install packages; use existing `node_modules`.

- [ ] **Step 6: Implement the minimal Projects experience**

Add `projects` and `project-detail` page states to the existing local App navigation. Use one Projects page for list/create and one detail page for status, workspace, environment, allowed Capabilities, recent Tasks, Create Task, and Archive. Capability checkboxes start unchecked and display semantic IDs plus permission labels; no Tool IDs are sent or used as policy.

- [ ] **Step 7: Run focused backend and frontend tests GREEN**

```powershell
Set-Location ..
D:\AgentProjects\AgentForge\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase_14_local_project_workspace.py -q -k "api or project or task_payload"
Set-Location frontend
npm test
```

- [ ] **Step 8: Commit API and frontend**

```powershell
Set-Location ..
git add backend/app/api backend/app/main.py backend/app/projects backend/app/schemas backend/tests/test_phase_14_local_project_workspace.py frontend/src
git diff --cached --check
git commit -m "feat: add local project workspace console"
```

---

### Task 7: Security Review, Documentation, Final Regression, and Hygiene

**Files:**
- Modify: `PROJECT_CONTEXT.md`
- Modify: `README.md`
- Modify: `docs/architecture/README.md`
- Modify: `docs/deployment/README.md`
- Modify: `.env.example`
- Test: `backend/tests/test_phase_14_local_project_workspace.py`

**Interfaces:**
- Produces final security evidence, operational documentation, isolated migration proof, and a clean branch.
- Does not migrate or smoke-test the live database; that is a separate later operation.

- [ ] **Step 1: Perform one focused whole-feature review without subagents**

Review `git diff 5522e26` for exactly: LLM/task-controlled workspace, concrete Tool IDs in Project policy, future capability auto-enable, null-Project execution, Project substitution, Plan/Approval authority mismatch, stale config/fingerprint/workspace, SAFE_READ Gateway bypass, string-prefix descendant checks, UNC/device/network paths, junction/symlink escape, archive bypass, cosmetic version churn, hard-delete/unarchive, approval schema creep, Organization/RBAC scope creep, real-project test paths, real provider/network use, dependency changes, and live data references.

Fix only confirmed Phase 14 findings and add regression coverage to the same Phase 14 backend file or existing `App.test.tsx`.

- [ ] **Step 2: Complete the explicit security matrix**

Ensure Phase 14 tests prove: Project A cannot use Project B traversal/absolute/link path, project ID, approval snapshot, fingerprint, or policy; both capability removal and addition invalidate old approval; archive blocks pending/new execution and Replanning; name/description/environment edits preserve authority; empty/future capability policy remains deny; Task payload extra authority is rejected; no ToolGateway bypass succeeds.

- [ ] **Step 3: Run fresh Phase 14 backend and isolated migration tests**

```powershell
D:\AgentProjects\AgentForge\backend\.venv\Scripts\python.exe -m pytest backend/tests/test_phase_14_local_project_workspace.py -q
```

Expected: all Phase 14 tests pass using in-memory or temporary SQLite and tiny temporary workspaces only.

- [ ] **Step 4: Update only required operational documentation**

Document Project as execution authority, local-only canonical workspace rules, empty explicit Capability allow-list, ACTIVE/ARCHIVED behavior, nullable read-only legacy Tasks, config version/fingerprint drift invalidation, approval JSON schema version 2, non-destructive migration shape, and the later manual AgentForge dogfood setup. State that live migration requires separate backup/approval and has not run.

- [ ] **Step 5: Run one final backend regression with bounded output**

```powershell
$log='D:\VSCodeData\AgentDev\Temp\agentforge-phase14-final-backend.log'
D:\AgentProjects\AgentForge\backend\.venv\Scripts\python.exe -m pytest backend/tests -q *> $log
$code=$LASTEXITCODE
Get-Content $log -Tail 60
exit $code
```

- [ ] **Step 6: Run final frontend tests and production build**

```powershell
Set-Location frontend
npm test *> 'D:\VSCodeData\AgentDev\Temp\agentforge-phase14-final-frontend-test.log'
$testCode=$LASTEXITCODE
Get-Content 'D:\VSCodeData\AgentDev\Temp\agentforge-phase14-final-frontend-test.log' -Tail 60
if ($testCode -ne 0) { exit $testCode }
npm run build *> 'D:\VSCodeData\AgentDev\Temp\agentforge-phase14-final-frontend-build.log'
$buildCode=$LASTEXITCODE
Get-Content 'D:\VSCodeData\AgentDev\Temp\agentforge-phase14-final-frontend-build.log' -Tail 60
exit $buildCode
```

- [ ] **Step 7: Verify schema, dependency, storage, secret, and workspace boundaries**

```powershell
Set-Location ..
git diff --check
git status --short
git diff 5522e26 --stat
git diff 5522e26 --name-only
git diff 5522e26 -- backend/requirements.txt frontend/package.json frontend/package-lock.json backend/app/storage/orm.py backend/app/storage/migrations.py
"C_FREE=$((Get-PSDrive C).Free)"
"D_FREE=$((Get-PSDrive D).Free)"
```

Expected: intentional Project schema/migration changes only; no Approval column, dependency/lock change, `.env`, SQLite file, runtime data, logs, caches, extra Phase 14 test packages, duplicate environments, or unexpected ~500 MiB growth. Search changed text for credential assignments without printing values.

- [ ] **Step 8: Commit Phase completion documentation and final fixes**

```powershell
git add PROJECT_CONTEXT.md README.md docs/architecture/README.md docs/deployment/README.md .env.example backend/app backend/tests/test_phase_14_local_project_workspace.py frontend/src
git diff --cached --check
git commit -m "docs: complete local project workspace phase"
```

Remove the obsolete `AGENTFORGE_WORKSPACE_ROOT` template entry because persisted Project configuration replaces the fixed process workspace authority; do not add a replacement secret or client-controlled root. Confirm no other test file named `test_phase14_*`, `test_phase_14_*`, or equivalent was added.

- [ ] **Step 9: Verify committed branch and stop before integration/live migration**

```powershell
git status --short
git log -7 --oneline
```

Expected: clean `feature/phase-12-real-llm-provider` with a few coherent Phase 14 commits. Do not merge, push, deploy, delete the worktree, start the live launcher, or migrate `D:\AgentProjectData\AgentForge\database\agentforge.sqlite3`.

## Final Acceptance Checklist

- [ ] Project is enforced as execution authority, not cosmetic CRUD.
- [ ] Workspace authority comes only from validated Project configuration, never Task or LLM input.
- [ ] Project policy contains Capability IDs only and defaults to empty.
- [ ] Future registry Capabilities remain disabled until explicitly selected.
- [ ] Task Project binding is immutable and successor Plans cannot switch it.
- [ ] Legacy null-Project Tasks remain readable/reportable and cannot execute.
- [ ] `config_version` changes only for workspace, policy, or ACTIVE-to-ARCHIVED authority changes.
- [ ] SHA-256 authority fingerprint uses the exact canonical document from the spec.
- [ ] Existing approval JSON, not a new DB column/system, binds Project authority.
- [ ] Stale Project version, fingerprint, workspace, status, or capability policy invalidates approval.
- [ ] SAFE_READ and APPROVED_EXEC both pass through Project authority and ToolGateway checks.
- [ ] Canonical descendant checks block traversal, prefix siblings, absolute injection, UNC/network, junction/reparse/symlink, and cross-project escapes.
- [ ] Project API has no hard-delete/unarchive and UI has no Organization/RBAC/file-browser scope.
- [ ] Migration is idempotent/non-destructive in isolated SQLite and live migration is deferred.
- [ ] One primary Phase 14 backend test file is used; automated tests touch only tiny temporary Projects.
- [ ] Final backend, frontend test/build, hygiene, secret, and disk checks have fresh bounded evidence.

## Execution Handoff

Execute this plan only after explicit approval, using `superpowers:executing-plans` inline in the same current worktree. Parallel subagents are prohibited for Phase 14. Use focused Phase 14 tests during development, one major-integration regression only if genuinely required, and one final full regression near completion.
