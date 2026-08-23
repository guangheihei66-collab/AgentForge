from pathlib import Path
import shutil
import subprocess
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect
from fastapi.testclient import TestClient

from app.capabilities.registry import build_default_capability_registry
from app.projects.models import Project, ProjectStatus
from app.storage.database import Base
from app.storage.migrations import migrate_sqlite_schema
from app.storage.orm import TaskRecord
from app.storage.repositories.project_repository import ProjectRepository
from app.services.task_service import TaskService
from app.agents.planner.planner import PlannerAgent
from app.agents.providers import MockLLMProvider
from app.main import app
from app.approvals.service import ApprovalError, ApprovalService
from app.agent_runtime.executor import RuntimeExecutor
from app.agent_runtime.runtime import AgentRuntime
from app.permissions.levels import PermissionLevel
from app.projects.service import ProjectConflictError, ProjectService
from app.tools.defaults import build_default_registry
from app.tools.gateway import ToolExecutionRequest, ToolGateway
from app.workspace.validator import WorkspaceValidationError, WorkspaceValidator


@pytest.fixture()
def local_project_root():
    root = Path(r"D:\VSCodeData\AgentDev\Temp") / f"agentforge-phase14-{uuid4()}"
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        shutil.rmtree(root)


@pytest.fixture()
def local_artifact_root():
    root = Path(r"D:\AgentProjectData\AgentForge\test-runs") / f"phase14-{uuid4()}"
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        shutil.rmtree(root)


def create_legacy_task(session, workspace: Path):
    record = TaskRecord(
        id=str(uuid4()), project_id=None, title="Legacy", goal="History",
        workspace=str(workspace), status="CREATED",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    session.add(record); session.commit()
    return TaskService(session).get_task(record.id)


def test_project_persistence_defaults_to_empty_capability_policy(db_session, local_project_root):
    workspace = local_project_root / "project-a"
    workspace.mkdir()
    project = Project.new(
        name="Project A",
        description=None,
        workspace_root=str(workspace),
        environment="development",
        allowed_capability_ids=(),
    )

    created = ProjectRepository(db_session).create(project)

    assert created.status is ProjectStatus.ACTIVE
    assert created.allowed_capability_ids == ()
    assert created.config_version == 1
    persisted = ProjectRepository(db_session).get(created.id)
    assert persisted is not None
    assert persisted.id == created.id
    assert persisted.workspace_root == created.workspace_root


def test_sqlite_migration_adds_nullable_project_id_without_rewriting_task(local_project_root):
    database = local_project_root / "legacy.sqlite3"
    engine = create_engine(f"sqlite+pysqlite:///{database.as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE tasks (id VARCHAR(36) PRIMARY KEY, title VARCHAR(200) NOT NULL, "
            "goal TEXT NOT NULL, workspace VARCHAR(500) NOT NULL, status VARCHAR(32) NOT NULL, "
            "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, completed_at DATETIME)"
        )
        connection.exec_driver_sql(
            "INSERT INTO tasks (id,title,goal,workspace,status,created_at,updated_at) "
            "VALUES ('legacy-task','Legacy','Read history','D:/Legacy','SUCCESS',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
        )
    Base.metadata.create_all(engine)

    migrate_sqlite_schema(engine)
    migrate_sqlite_schema(engine)

    assert "projects" in inspect(engine).get_table_names()
    assert "project_id" in {c["name"] for c in inspect(engine).get_columns("tasks")}
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT id, project_id FROM tasks WHERE id='legacy-task'"
        ).one() == ("legacy-task", None)
    engine.dispose()


def test_capability_subset_is_explicit_and_future_default_deny():
    registry = build_default_capability_registry()
    subset = registry.subset(("repository_state",))

    assert subset.ids() == ("repository_state",)
    assert "test_verification" not in subset.ids()


def test_workspace_validator_rejects_relative_unc_and_sibling(local_project_root):
    from app.workspace.validator import WorkspaceValidationError, WorkspaceValidator

    root = local_project_root / "App"
    sibling = local_project_root / "App-Other"
    root.mkdir(); sibling.mkdir()
    validator = WorkspaceValidator.for_project(root)
    with pytest.raises(WorkspaceValidationError):
        WorkspaceValidator.canonicalize_project_root("relative/path")
    with pytest.raises(WorkspaceValidationError):
        WorkspaceValidator.canonicalize_project_root(r"\\server\share")
    with pytest.raises(WorkspaceValidationError):
        validator.validate_target(root, sibling)


def test_workspace_validator_blocks_traversal_and_link_escape(local_project_root):
    workspace = local_project_root / "workspace"
    outside = local_project_root / "outside"
    workspace.mkdir(); outside.mkdir()
    (outside / "metadata.md").write_text("outside", encoding="utf-8")
    validator = WorkspaceValidator.for_project(workspace)

    with pytest.raises(WorkspaceValidationError, match="escapes"):
        validator.validate_relative_file(workspace, r"..\outside\metadata.md")

    link = workspace / "outside-link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        if completed.returncode != 0:
            pytest.fail("Test environment cannot create a symlink or junction")
    with pytest.raises(WorkspaceValidationError, match="escapes"):
        validator.validate_relative_file(workspace, r"outside-link\metadata.md")


def test_workspace_validator_rejects_remote_drive(local_project_root, monkeypatch):
    monkeypatch.setattr(
        WorkspaceValidator, "_windows_drive_type", staticmethod(lambda _path: 4),
        raising=False,
    )
    with pytest.raises(WorkspaceValidationError, match="remote"):
        WorkspaceValidator.canonicalize_project_root(local_project_root)


def test_project_authority_changes_only_for_execution_configuration(db_session, local_project_root):
    from app.projects.service import ProjectService

    workspace = local_project_root / "authority-project"
    workspace.mkdir()
    service = ProjectService(db_session)
    project = service.create(
        name="Authority", description=None, workspace_root=str(workspace),
        environment="development", allowed_capability_ids=("repository_state",),
    )
    before = service.execution_context(project.id)
    cosmetic = service.update(
        project.id, expected_config_version=1, name="Renamed",
        description="Cosmetic", environment="test",
    )
    after_cosmetic = service.execution_context(project.id)
    assert cosmetic.config_version == 1
    assert after_cosmetic.authority_fingerprint == before.authority_fingerprint

    changed = service.update(
        project.id, expected_config_version=1,
        allowed_capability_ids=("repository_state", "project_metadata"),
    )
    assert changed.config_version == 2
    assert service.execution_context(project.id).authority_fingerprint != before.authority_fingerprint


def test_project_policy_rejects_unknown_and_duplicate_capabilities(db_session, local_project_root):
    from app.projects.service import ProjectService

    workspace = local_project_root / "policy-project"
    workspace.mkdir()
    service = ProjectService(db_session)
    with pytest.raises(ValueError):
        service.create(name="Bad", description=None, workspace_root=str(workspace),
                       environment="development", allowed_capability_ids=("unknown",))
    with pytest.raises(ValueError):
        service.create(name="Bad", description=None, workspace_root=str(workspace),
                       environment="development",
                       allowed_capability_ids=("repository_state", "repository_state"))


def test_missing_stored_workspace_does_not_break_project_creation(db_session, local_project_root):
    from app.projects.service import ProjectService

    stale_root = local_project_root / "stale-project"
    fresh_root = local_project_root / "fresh-project"
    stale_root.mkdir(); fresh_root.mkdir()
    service = ProjectService(db_session)
    service.create(name="Stale", description=None, workspace_root=str(stale_root),
                   environment="test", allowed_capability_ids=())
    shutil.rmtree(stale_root)

    created = service.create(name="Fresh", description=None, workspace_root=str(fresh_root),
                             environment="test", allowed_capability_ids=())

    assert created.workspace_root == str(fresh_root.resolve())


def test_project_workspace_update_cannot_collide_with_an_active_project(db_session, local_project_root):
    first_root = local_project_root / "first"
    second_root = local_project_root / "second"
    first_root.mkdir(); second_root.mkdir()
    service = ProjectService(db_session)
    first = service.create(name="First", description=None, workspace_root=str(first_root),
                           environment="test", allowed_capability_ids=())
    second = service.create(name="Second", description=None, workspace_root=str(second_root),
                            environment="test", allowed_capability_ids=())

    with pytest.raises(ProjectConflictError, match="already uses"):
        service.update(second.id, expected_config_version=1,
                       workspace_root=first.workspace_root)


def test_new_task_derives_workspace_from_project(db_session, local_project_root):
    from app.projects.service import ProjectService

    workspace = local_project_root / "task-project"
    workspace.mkdir()
    project = ProjectService(db_session).create(
        name="Tasks", description=None, workspace_root=str(workspace),
        environment="development", allowed_capability_ids=("repository_state",),
    )

    task = TaskService(db_session).create_task(
        title="Check", goal="Check repository", project_id=project.id
    )

    assert task.project_id == project.id
    assert Path(task.workspace).resolve() == workspace.resolve()


def test_legacy_task_is_readable_but_has_no_execution_context(db_session, local_project_root):
    from app.projects.service import ProjectService

    legacy = create_legacy_task(db_session, local_project_root)
    assert TaskService(db_session).get_task(legacy.id).project_id is None
    with pytest.raises(PermissionError, match="Legacy Task"):
        ProjectService(db_session).execution_context_for_task(legacy.id)


class CapturingMockProvider(MockLLMProvider):
    def __init__(self):
        self.requests = []

    def generate_plan(self, request):
        self.requests.append(request)
        return super().generate_plan(request)


def test_planner_uses_only_project_capabilities_and_hides_workspace(db_session, local_project_root):
    from app.projects.service import ProjectService

    workspace = local_project_root / "planner-project"
    workspace.mkdir()
    project = ProjectService(db_session).create(
        name="Planner", description="Bounded", workspace_root=str(workspace),
        environment="development", allowed_capability_ids=("repository_state",),
    )
    task = TaskService(db_session).create_task(
        title="Plan", goal="Inspect repository", project_id=project.id
    )
    provider = CapturingMockProvider()

    plan = PlannerAgent(db_session, provider).create_plan(task.id)

    assert plan.plan_json["project_authority"]["project_id"] == project.id
    prompt = provider.requests[0].prompt
    assert "repository_state" in prompt
    assert "test_verification" not in prompt
    assert str(workspace) not in prompt


def test_legacy_task_cannot_start_planning(db_session, local_project_root):
    legacy = create_legacy_task(db_session, local_project_root)
    with pytest.raises(PermissionError, match="Legacy Task"):
        PlannerAgent(db_session, MockLLMProvider()).create_plan(legacy.id)


def create_project_plan(db_session, local_project_root):
    from app.projects.service import ProjectService

    workspace = local_project_root / "approved-project"
    workspace.mkdir()
    project = ProjectService(db_session).create(
        name="Approved", description=None, workspace_root=str(workspace),
        environment="development", allowed_capability_ids=("repository_state",),
    )
    task = TaskService(db_session).create_task(
        title="Approve", goal="Inspect", project_id=project.id
    )
    plan = PlannerAgent(db_session, MockLLMProvider()).create_plan(task.id)
    return project, task, plan


def test_approval_snapshot_contains_project_authority(db_session, local_project_root):
    project, task, plan = create_project_plan(db_session, local_project_root)
    approval = ApprovalService(db_session).create_request(
        task_id=task.id, plan_id=plan.id, plan_version=plan.version
    )

    assert approval.resolved_snapshot["schema_version"] == 2
    authority = approval.resolved_snapshot["project_authority"]
    assert authority["project_id"] == project.id
    assert authority["config_version"] == 1
    assert len(authority["authority_fingerprint"]) == 64


def test_project_policy_drift_invalidates_approved_snapshot(db_session, local_project_root):
    from app.projects.service import ProjectService

    project, task, plan = create_project_plan(db_session, local_project_root)
    approval = ApprovalService(db_session).create_request(
        task_id=task.id, plan_id=plan.id, plan_version=plan.version
    )
    ApprovalService(db_session).approve(approval.id, actor="operator")
    ProjectService(db_session).update(
        project.id, expected_config_version=1,
        allowed_capability_ids=("repository_state", "project_metadata"),
    )

    snapshot = plan.plan_json["resolved_steps"][0]
    from app.capabilities.models import ResolvedExecutionSnapshot
    with pytest.raises((ApprovalError, PermissionError), match="authority|drift"):
        ApprovalService(db_session).assert_snapshot_allowed(
            ResolvedExecutionSnapshot.from_dict(snapshot)
        )


def test_archived_project_blocks_pending_approval_and_runtime(
    db_session, local_project_root, local_artifact_root
):
    project, task, plan = create_project_plan(db_session, local_project_root)
    approval = ApprovalService(db_session).create_request(
        task_id=task.id, plan_id=plan.id, plan_version=plan.version
    )
    ProjectService(db_session).archive(project.id, expected_config_version=1)

    pending = TestClient(app).get("/approvals/pending")
    assert all(item["id"] != approval.id for item in pending.json())

    with pytest.raises(ApprovalError, match="Archived|authority"):
        ApprovalService(db_session).approve(approval.id, actor="operator")

    approval.decision = "APPROVED"
    task_record = db_session.get(TaskRecord, task.id)
    task_record.status = "RUNNING"
    db_session.commit()
    validator = WorkspaceValidator(project.workspace_root)
    runtime = AgentRuntime(db_session, RuntimeExecutor(ToolGateway(
        db_session, build_default_registry(validator), validator, local_artifact_root
    )))
    with pytest.raises(PermissionError, match="Archived"):
        runtime.run(task_id=task.id, plan_id=plan.id, plan_version=plan.version)


def test_tool_gateway_rejects_cross_project_workspace(
    db_session, local_project_root, local_artifact_root
):
    project, task, plan = create_project_plan(db_session, local_project_root)
    approval = ApprovalService(db_session).create_request(
        task_id=task.id, plan_id=plan.id, plan_version=plan.version
    )
    ApprovalService(db_session).approve(approval.id, actor="operator")
    other_root = local_project_root / "other-project"
    other_root.mkdir()
    ProjectService(db_session).create(
        name="Other", description=None, workspace_root=str(other_root),
        environment="test", allowed_capability_ids=("repository_state",),
    )
    context = ProjectService(db_session).execution_context(project.id)
    validator = WorkspaceValidator(project.workspace_root)
    gateway = ToolGateway(db_session, build_default_registry(validator), validator,
                          local_artifact_root)

    with pytest.raises(ApprovalError, match="workspace authority"):
        gateway.execute(ToolExecutionRequest(
            task_id=task.id, tool_name="git_read", action="status",
            workspace=str(other_root), parameters={},
            project_authority_fingerprint=context.authority_fingerprint,
            granted_permission=PermissionLevel.SAFE_READ,
            plan_id=plan.id, plan_version=plan.version,
        ))
    from app.storage.orm import ToolExecutionRecord
    assert db_session.query(ToolExecutionRecord).filter_by(
        task_id=task.id, status="SUCCESS"
    ).count() == 0


def test_project_api_and_task_payload_are_strict(db_session, local_project_root):
    workspace = local_project_root / "api-project"
    workspace.mkdir()
    client = TestClient(app)
    response = client.post("/projects", json={
        "name": "API Project", "description": "Local",
        "workspace_root": str(workspace), "environment": "development",
        "allowed_capability_ids": ["repository_state"],
    })
    assert response.status_code == 201
    project = response.json()
    assert project["allowed_capability_ids"] == ["repository_state"]

    injected = client.post("/tasks", json={
        "project_id": project["id"], "title": "Task", "goal": "Goal",
        "workspace": str(local_project_root), "tool_id": "git_read",
    })
    assert injected.status_code == 422
    created = client.post("/tasks", json={
        "project_id": project["id"], "title": "Task", "goal": "Goal",
    })
    assert created.status_code == 201
    assert created.json()["project_id"] == project["id"]


def test_archived_project_blocks_new_tasks(db_session, local_project_root):
    workspace = local_project_root / "archive-project"
    workspace.mkdir()
    client = TestClient(app)
    project = client.post("/projects", json={
        "name": "Archive", "workspace_root": str(workspace),
        "environment": "development", "allowed_capability_ids": [],
    }).json()
    archived = client.post(f"/projects/{project['id']}/archive", json={
        "expected_config_version": 1
    })
    assert archived.status_code == 200
    assert archived.json()["status"] == "ARCHIVED"
    assert client.post("/tasks", json={
        "project_id": project["id"], "title": "Blocked", "goal": "Goal",
    }).status_code == 400
