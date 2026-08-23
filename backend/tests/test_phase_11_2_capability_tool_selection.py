from dataclasses import replace
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from app.capabilities.models import CapabilityDefinition, CapabilityRequest
from app.capabilities.registry import (
    CapabilityNotFound,
    CapabilityRegistry,
    build_default_capability_registry,
)
from app.capabilities.resolver import CapabilityResolutionError, CapabilityResolver
from app.agents.planner.planner import PlannerAgent
from app.agents.planner.schemas import parse_plan_for_display
from app.agents.planner.validator import PlanValidationError, PlanValidator
from app.agents.providers.mock import MockLLMProvider
from app.agent_runtime.executor import RuntimeExecutor
from app.agent_runtime.runtime import AgentRuntime
from app.agent_runtime.state import RuntimeDecision, RuntimeState
from app.approvals.service import ApprovalError, ApprovalService
from app.main import app
from app.contracts.permissions import PermissionLevel
from app.domain.states.task_state import TaskStatus
from app.services.task_service import TaskService
from app.storage.database import Base
from app.storage.migrations import migrate_sqlite_schema
from app.storage.orm import (
    ApprovalRecord,
    AuditEventRecord,
    PlanRecord,
    TaskRecord,
    ToolExecutionRecord,
)
from app.tools.defaults import build_default_registry
from app.tools.gateway import ToolGateway
from app.tools.models import ToolDefinition
from app.tools.registry import ToolRegistry
from app.workspace.validator import WorkspaceValidator


REPO_ROOT = r"D:\AgentProjects\AgentForge"
DATA_ROOT = Path(r"D:\AgentProjectData\AgentForge")


def capability_resolver() -> CapabilityResolver:
    return CapabilityResolver(
        build_default_capability_registry(),
        build_default_registry(WorkspaceValidator(REPO_ROOT)),
    )


def test_default_registry_contains_only_the_three_mvp_capabilities():
    registry = build_default_capability_registry()

    assert registry.ids() == (
        "project_metadata",
        "repository_state",
        "test_verification",
    )
    assert registry.require("repository_state").candidate_tool_ids == ("git_read",)
    assert registry.require("project_metadata").candidate_tool_ids == ("file_read",)
    verification = registry.require("test_verification")
    assert verification.candidate_tool_ids == ("test_run",)
    assert verification.parameter_schema[0].name == "profile"
    assert verification.parameter_schema[0].allowed_values == ("smoke", "unit")


def test_capability_registry_rejects_unknown_and_duplicate_ids():
    registry = CapabilityRegistry()
    definition = build_default_capability_registry().require("repository_state")
    registry.register(definition)

    with pytest.raises(ValueError, match="already registered"):
        registry.register(definition)
    with pytest.raises(CapabilityNotFound, match="Unknown capability"):
        registry.require("missing")


@pytest.mark.parametrize(
    ("capability_id", "parameters", "tool_id", "action"),
    [
        ("repository_state", {}, "git_read", "status"),
        (
            "project_metadata",
            {"relative_path": "PROJECT_CONTEXT.md"},
            "file_read",
            "read_metadata",
        ),
        ("test_verification", {"profile": "smoke"}, "test_run", "run_profile"),
    ],
)
def test_resolver_selects_the_single_valid_mapped_tool(
    capability_id, parameters, tool_id, action
):
    resolver = capability_resolver()

    snapshot = resolver.resolve(
        task_id="task-1",
        plan_id="plan-1",
        plan_version=1,
        step_id="step-1",
        request=CapabilityRequest(capability_id, parameters),
    )

    assert snapshot.resolved_tool_id == tool_id
    assert snapshot.resolved_action == action
    assert snapshot.parameters_dict() == parameters
    assert len(snapshot.registry_fingerprint) == 64
    resolver.verify(snapshot)


@pytest.mark.parametrize(
    "capability_request",
    [
        CapabilityRequest("missing", {}),
        CapabilityRequest("test_verification", {}),
        CapabilityRequest("test_verification", {"profile": "arbitrary"}),
        CapabilityRequest(
            "test_verification", {"profile": "smoke", "command": "pytest"}
        ),
    ],
)
def test_resolver_rejects_unknown_capabilities_and_invalid_parameters(
    capability_request,
):
    with pytest.raises((CapabilityNotFound, CapabilityResolutionError)):
        capability_resolver().resolve(
            task_id="task-1",
            plan_id="plan-1",
            plan_version=1,
            step_id="step-1",
            request=capability_request,
        )


def test_resolver_fails_closed_for_zero_or_multiple_valid_candidates():
    capabilities = CapabilityRegistry()
    tools = ToolRegistry()
    base_tool = build_default_registry(WorkspaceValidator(REPO_ROOT)).require("git_read")
    tools.register(base_tool)
    tools.register(replace(base_tool, name="git_read_2"))
    capabilities.register(
        CapabilityDefinition(
            id="repository_state",
            description="Read repository state",
            risk_level="low",
            required_permission=PermissionLevel.SAFE_READ,
            candidate_tool_ids=("missing",),
            action="status",
            parameter_schema=(),
        )
    )

    with pytest.raises(CapabilityResolutionError, match="found 0"):
        CapabilityResolver(capabilities, tools).resolve(
            task_id="task-1",
            plan_id="plan-1",
            plan_version=1,
            step_id="step-1",
            request=CapabilityRequest("repository_state", {}),
        )

    multiple = CapabilityRegistry()
    multiple.register(
        replace(
            capabilities.require("repository_state"),
            candidate_tool_ids=("git_read", "git_read_2"),
        )
    )
    with pytest.raises(CapabilityResolutionError, match="found 2"):
        CapabilityResolver(multiple, tools).resolve(
            task_id="task-1",
            plan_id="plan-1",
            plan_version=1,
            step_id="step-1",
            request=CapabilityRequest("repository_state", {}),
        )


def test_fingerprint_is_stable_for_cosmetic_changes_and_detects_semantic_changes():
    resolver = capability_resolver()
    snapshot = resolver.resolve(
        task_id="task-1",
        plan_id="plan-1",
        plan_version=1,
        step_id="step-1",
        request=CapabilityRequest("repository_state", {}),
    )
    capabilities = build_default_capability_registry()
    tools = build_default_registry(WorkspaceValidator(REPO_ROOT))
    cosmetic_tools = ToolRegistry()
    cosmetic_tools.register(replace(tools.require("git_read"), description="New wording"))
    cosmetic = CapabilityResolver(capabilities, cosmetic_tools).resolve(
        task_id="task-1",
        plan_id="plan-1",
        plan_version=1,
        step_id="step-1",
        request=CapabilityRequest("repository_state", {}),
    )
    semantic_tools = ToolRegistry()
    semantic_tools.register(
        replace(tools.require("git_read"), execution_contract_version="2")
    )
    semantic = CapabilityResolver(capabilities, semantic_tools).resolve(
        task_id="task-1",
        plan_id="plan-1",
        plan_version=1,
        step_id="step-1",
        request=CapabilityRequest("repository_state", {}),
    )

    assert cosmetic.registry_fingerprint == snapshot.registry_fingerprint
    assert semantic.registry_fingerprint != snapshot.registry_fingerprint
    with pytest.raises(CapabilityResolutionError, match="fingerprint"):
        CapabilityResolver(capabilities, semantic_tools).verify(snapshot)


def test_planner_persists_capability_first_plan_and_resolved_snapshot(db_session):
    task = TaskService(db_session).create_task(
        title="Phase 11.2 planner",
        goal="Check repository state",
        workspace=REPO_ROOT,
    )

    plan = PlannerAgent(db_session, MockLLMProvider(), REPO_ROOT).create_plan(task.id)

    assert plan.plan_json["schema_version"] == 2
    assert plan.plan_json["steps"] == [
        {
            "step_id": "step-1",
            "capability_id": "repository_state",
            "parameters": {},
        }
    ]
    snapshot = plan.plan_json["resolved_steps"][0]
    assert snapshot["task_id"] == task.id
    assert snapshot["plan_id"] == plan.id
    assert snapshot["plan_version"] == 1
    assert snapshot["capability_id"] == "repository_state"
    assert snapshot["resolved_tool_id"] == "git_read"
    assert snapshot["normalized_parameters"] == {}
    events = db_session.query(AuditEventRecord).filter_by(task_id=task.id).all()
    event_types = [event.event_type for event in events]
    assert "CAPABILITY_REQUESTED" in event_types
    assert "CAPABILITY_RESOLVED" in event_types
    resolved_event = next(
        event for event in events if event.event_type == "CAPABILITY_RESOLVED"
    )
    assert json.loads(resolved_event.payload_summary)["resolved_tool_id"] == "git_read"
    assert db_session.get(TaskRecord, task.id).status == "WAITING_APPROVAL"


def test_new_planner_schema_rejects_concrete_tool_authority():
    validator = PlanValidator(WorkspaceValidator(REPO_ROOT))

    with pytest.raises(PlanValidationError):
        validator.validate(
            {
                "schema_version": 2,
                "steps": [
                    {
                        "step_id": "step-1",
                        "tool": "test_run",
                        "action": "run_profile",
                    }
                ],
            },
            REPO_ROOT,
        )


def test_legacy_concrete_tool_plan_is_readable_but_not_executable():
    legacy = parse_plan_for_display(
        {
            "steps": [
                {
                    "step_id": "step-1",
                    "tool": "git_read",
                    "action": "status",
                    "risk_level": "low",
                    "permission_level": "SAFE_READ",
                }
            ]
        }
    )

    assert legacy.schema_version == 1
    assert legacy.executable is False
    assert legacy.steps[0]["tool"] == "git_read"


def test_sqlite_migration_adds_snapshot_column_without_losing_legacy_rows():
    bind = create_engine("sqlite+pysqlite:///:memory:")
    with bind.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE approvals ("
            "id VARCHAR(36) PRIMARY KEY, task_id VARCHAR(36) NOT NULL, "
            "plan_id VARCHAR(36) NOT NULL, decision VARCHAR(32) NOT NULL, "
            "approver VARCHAR(200) NOT NULL, reason TEXT, created_at DATETIME)"
        )
        connection.exec_driver_sql(
            "INSERT INTO approvals (id, task_id, plan_id, decision, approver) "
            "VALUES ('a1', 't1', 'p1', 'PENDING', 'tester')"
        )

    migrate_sqlite_schema(bind)
    migrate_sqlite_schema(bind)

    columns = {column["name"] for column in inspect(bind).get_columns("approvals")}
    assert "resolved_snapshot" in columns
    with bind.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT COUNT(*) FROM approvals"
        ).scalar_one() == 1


def test_fresh_schema_contains_resolved_snapshot_column():
    bind = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind)

    columns = {column["name"] for column in inspect(bind).get_columns("approvals")}
    assert "resolved_snapshot" in columns


def make_resolved_plan(session):
    task = TaskService(session).create_task(
        title="Phase 11.2 approval",
        goal="Approve resolved repository state",
        workspace=REPO_ROOT,
    )
    TaskService(session).transition_task(task.id, TaskStatus.PLANNING)
    plan = PlanRecord(
        task_id=task.id,
        version=1,
        plan_json={
            "schema_version": 2,
            "steps": [
                {
                    "step_id": "step-1",
                    "capability_id": "repository_state",
                    "parameters": {},
                }
            ],
            "resolved_steps": [],
        },
        validation_status="VALID",
    )
    session.add(plan)
    session.flush()
    snapshot = capability_resolver().resolve(
        task_id=task.id,
        plan_id=plan.id,
        plan_version=1,
        step_id="step-1",
        request=CapabilityRequest("repository_state", {}),
    )
    plan.plan_json = {**plan.plan_json, "resolved_steps": [snapshot.to_dict()]}
    session.commit()
    return task, plan, snapshot


def test_approval_persists_and_authorizes_only_the_exact_resolved_snapshot(db_session):
    task, plan, snapshot = make_resolved_plan(db_session)
    service = ApprovalService(db_session)

    approval = service.create_request(
        task_id=task.id,
        plan_id=plan.id,
        plan_version=1,
        requested_by="phase-11-2-test",
    )
    assert approval.resolved_snapshot == {
        "schema_version": 1,
        "steps": [snapshot.to_dict()],
    }
    service.approve(approval.id, actor="reviewer")
    assert service.assert_snapshot_allowed(snapshot).id == approval.id

    drifted = [
        replace(snapshot, capability_id="project_metadata"),
        replace(snapshot, resolved_tool_id="file_read"),
        replace(snapshot, normalized_parameters=(("profile", "smoke"),)),
        replace(snapshot, registry_fingerprint="0" * 64),
        replace(snapshot, plan_version=2),
    ]
    for changed in drifted:
        with pytest.raises((ApprovalError, ValueError)):
            service.assert_snapshot_allowed(changed)


def test_legacy_plan_cannot_request_phase_11_2_approval(db_session):
    task = TaskService(db_session).create_task(
        title="Legacy approval",
        goal="Reject concrete tool authority",
        workspace=REPO_ROOT,
    )
    TaskService(db_session).transition_task(task.id, TaskStatus.PLANNING)
    plan = PlanRecord(
        task_id=task.id,
        version=1,
        plan_json={"steps": [{"step_id": "step-1", "tool": "git_read"}]},
        validation_status="VALID",
    )
    db_session.add(plan)
    db_session.commit()

    with pytest.raises(ApprovalError, match="resolved"):
        ApprovalService(db_session).create_request(
            task_id=task.id,
            plan_id=plan.id,
            plan_version=1,
        )

    assert db_session.query(ApprovalRecord).filter_by(plan_id=plan.id).count() == 0


def test_pending_approval_api_exposes_what_will_actually_execute():
    with TestClient(app) as client:
        task = client.post(
            "/tasks",
            json={
                "title": "Visible resolved approval",
                "goal": "Show resolved execution",
                "workspace": REPO_ROOT,
            },
        ).json()
        plan = client.post(f"/tasks/{task['id']}/plan", json={}).json()
        created = client.post(
            f"/tasks/{task['id']}/approval",
            json={"plan_id": plan["id"], "plan_version": 1},
        )
        pending = client.get("/approvals/pending")

    assert created.status_code == 201
    item = next(row for row in pending.json() if row["task_id"] == task["id"])
    snapshot = item["resolved_snapshot"]["steps"][0]
    assert snapshot["capability_id"] == "repository_state"
    assert snapshot["resolved_tool_id"] == "git_read"
    assert snapshot["normalized_parameters"] == {}
    assert len(snapshot["registry_fingerprint"]) == 64


def runtime_for(session, resolver=None):
    workspace_validator = WorkspaceValidator(REPO_ROOT)
    gateway = ToolGateway(
        session=session,
        registry=(resolver.tools if resolver else build_default_registry(workspace_validator)),
        workspace_validator=workspace_validator,
        artifact_root=DATA_ROOT / "test-runs" / "phase-11-2-artifacts",
    )
    active_resolver = resolver or CapabilityResolver(
        build_default_capability_registry(), gateway.registry
    )
    return AgentRuntime(session, RuntimeExecutor(gateway), active_resolver)


def approve_resolved_plan(session):
    task, plan, snapshot = make_resolved_plan(session)
    service = ApprovalService(session)
    approval = service.create_request(
        task_id=task.id,
        plan_id=plan.id,
        plan_version=plan.version,
        requested_by="runtime-test",
    )
    service.approve(approval.id, actor="reviewer")
    return task, plan, snapshot


def test_runtime_executes_only_the_approved_resolved_snapshot_through_gateway(
    db_session,
):
    task, plan, snapshot = approve_resolved_plan(db_session)

    result = runtime_for(db_session).run(
        task_id=task.id, plan_id=plan.id, plan_version=plan.version
    )

    assert result.state == RuntimeState.COMPLETED
    assert result.decision == RuntimeDecision.COMPLETE
    execution = db_session.query(ToolExecutionRecord).filter_by(task_id=task.id).one()
    assert execution.tool_name == snapshot.resolved_tool_id == "git_read"
    assert execution.action == snapshot.resolved_action == "status"
    event_types = {
        event.event_type
        for event in db_session.query(AuditEventRecord).filter_by(task_id=task.id).all()
    }
    assert "RUNTIME_EXECUTION" in event_types
    assert "TOOL_EXECUTION" in event_types
    assert "RUNTIME_OBSERVATION" in event_types


def test_runtime_rejects_unresolved_input_before_tool_execution(db_session):
    task, plan, _ = approve_resolved_plan(db_session)
    plan.plan_json = {
        "schema_version": 2,
        "steps": [
            {
                "step_id": "step-1",
                "capability_id": "repository_state",
                "parameters": {},
            }
        ],
        "resolved_steps": [],
    }
    db_session.commit()

    with pytest.raises(ValueError, match="resolved"):
        runtime_for(db_session).run(
            task_id=task.id, plan_id=plan.id, plan_version=plan.version
        )

    assert db_session.query(ToolExecutionRecord).filter_by(task_id=task.id).count() == 0


def test_runtime_rejects_registry_drift_before_tool_execution(db_session):
    task, plan, _ = approve_resolved_plan(db_session)
    workspace_validator = WorkspaceValidator(REPO_ROOT)
    changed_tools = ToolRegistry()
    changed_tools.register(
        replace(
            build_default_registry(workspace_validator).require("git_read"),
            execution_contract_version="2",
        )
    )
    changed_resolver = CapabilityResolver(
        build_default_capability_registry(), changed_tools
    )

    with pytest.raises(CapabilityResolutionError, match="fingerprint"):
        runtime_for(db_session, changed_resolver).run(
            task_id=task.id, plan_id=plan.id, plan_version=plan.version
        )

    assert db_session.query(ToolExecutionRecord).filter_by(task_id=task.id).count() == 0


def test_multi_step_capability_flow_is_auditable_end_to_end(db_session):
    class MultiStepProvider:
        def generate_plan(self, prompt, context):
            del prompt, context
            return {
                "schema_version": 2,
                "steps": [
                    {
                        "step_id": "step-1",
                        "capability_id": "repository_state",
                        "parameters": {},
                    },
                    {
                        "step_id": "step-2",
                        "capability_id": "project_metadata",
                        "parameters": {"relative_path": "PROJECT_CONTEXT.md"},
                    },
                    {
                        "step_id": "step-3",
                        "capability_id": "test_verification",
                        "parameters": {"profile": "smoke"},
                    },
                ],
            }

    task = TaskService(db_session).create_task(
        title="Phase 11.2 integration",
        goal="Verify release capabilities",
        workspace=REPO_ROOT,
    )
    plan = PlannerAgent(db_session, MultiStepProvider(), REPO_ROOT).create_plan(task.id)
    service = ApprovalService(db_session)
    approval = service.create_request(
        task_id=task.id,
        plan_id=plan.id,
        plan_version=plan.version,
        requested_by="integration-test",
    )
    service.approve(approval.id, actor="reviewer")

    result = runtime_for(db_session).run(
        task_id=task.id, plan_id=plan.id, plan_version=plan.version
    )

    assert result.state == RuntimeState.COMPLETED
    executions = (
        db_session.query(ToolExecutionRecord)
        .filter_by(task_id=task.id)
        .order_by(ToolExecutionRecord.started_at.asc())
        .all()
    )
    assert [execution.tool_name for execution in executions] == [
        "git_read",
        "file_read",
        "test_run",
    ]
    events = db_session.query(AuditEventRecord).filter_by(task_id=task.id).all()
    event_types = {event.event_type for event in events}
    assert {
        "CAPABILITY_REQUESTED",
        "CAPABILITY_RESOLVED",
        "EXECUTION_SNAPSHOT_APPROVED",
        "RUNTIME_EXECUTION",
        "TOOL_EXECUTION",
        "RUNTIME_OBSERVATION",
        "RUNTIME_DECISION",
    } <= event_types
    resolved_payload = json.loads(
        next(event for event in events if event.event_type == "CAPABILITY_RESOLVED").payload_summary
    )
    runtime_payload = json.loads(
        next(event for event in events if event.event_type == "RUNTIME_EXECUTION").payload_summary
    )
    assert runtime_payload["capability_id"] == resolved_payload["capability_id"]
    assert runtime_payload["resolved_tool_id"] == resolved_payload["resolved_tool_id"]
    assert runtime_payload["registry_fingerprint"] == resolved_payload["registry_fingerprint"]
