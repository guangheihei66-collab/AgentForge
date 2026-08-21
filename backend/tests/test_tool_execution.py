import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.domain.states.task_state import TaskStatus
from app.approvals.service import ApprovalService
from app.permissions.levels import PermissionLevel
from app.services.task_service import TaskService
from app.storage.orm import AuditEventRecord, EvidenceRecord, PlanRecord, ToolExecutionRecord
from app.tools.defaults import build_default_registry
from app.tools.gateway import ToolExecutionRequest, ToolGateway
from app.tools.models import ToolDefinition
from app.tools.registry import ToolRegistry
from app.workspace.validator import WorkspaceValidator


REPO_ROOT = r"D:\AgentProjects\AgentForge"
DATA_ROOT = r"D:\AgentProjectData\AgentForge"


def make_gateway(session):
    validator = WorkspaceValidator(REPO_ROOT)
    return ToolGateway(
        session=session,
        registry=build_default_registry(validator),
        workspace_validator=validator,
        artifact_root=Path(DATA_ROOT) / "test-runs" / "phase4-artifacts",
    )


def make_task(session):
    return TaskService(session).create_task(
        title="Tool gateway test",
        goal="Exercise a read-safe tool",
        workspace=REPO_ROOT,
    )


def approve_plan(session, task):
    TaskService(session).transition_task(task.id, TaskStatus.PLANNING)
    plan = PlanRecord(
        task_id=task.id,
        version=1,
        plan_json={"steps": []},
        validation_status="VALID",
        created_at=datetime.now(timezone.utc),
    )
    session.add(plan)
    session.flush()
    session.commit()
    approval = ApprovalService(session).create_request(
        task_id=task.id,
        plan_id=plan.id,
        plan_version=plan.version,
        requested_by="test",
    )
    ApprovalService(session).approve(approval.id, actor="tester")
    return plan


def test_git_read_success(db_session):
    task = make_task(db_session)
    result = make_gateway(db_session).execute(
        ToolExecutionRequest(
            task_id=task.id,
            tool_name="git_read",
            action="status",
            workspace=REPO_ROOT,
            parameters={},
            granted_permission=PermissionLevel.SAFE_READ,
        )
    )

    assert result.status == "SUCCESS"
    assert result.evidence_id is not None
    execution = db_session.get(ToolExecutionRecord, result.execution_id)
    assert execution is not None
    assert execution.status == "SUCCESS"
    assert Path(result.artifact_path).is_relative_to(Path(DATA_ROOT))


def test_test_profile_execution(db_session):
    task = make_task(db_session)
    plan = approve_plan(db_session, task)
    result = make_gateway(db_session).execute(
        ToolExecutionRequest(
            task_id=task.id,
            tool_name="test_run",
            action="run_profile",
            workspace=REPO_ROOT,
            parameters={"profile": "smoke"},
            granted_permission=PermissionLevel.APPROVED_EXEC,
            approved=True,
            plan_id=plan.id,
            plan_version=plan.version,
        )
    )

    assert result.status == "SUCCESS"
    assert "smoke" in result.summary


def test_missing_permission_rejected(db_session):
    task = make_task(db_session)

    with pytest.raises(PermissionError):
        make_gateway(db_session).execute(
            ToolExecutionRequest(
                task_id=task.id,
                tool_name="test_run",
                action="run_profile",
                workspace=REPO_ROOT,
                parameters={"profile": "smoke"},
            )
        )


def test_invalid_workspace_rejected(db_session):
    task = make_task(db_session)

    with pytest.raises(ValueError):
        make_gateway(db_session).execute(
            ToolExecutionRequest(
                task_id=task.id,
                tool_name="git_read",
                action="status",
                workspace=DATA_ROOT,
                parameters={},
                granted_permission=PermissionLevel.SAFE_READ,
            )
        )


def test_secret_file_access_rejected(db_session):
    task = make_task(db_session)

    with pytest.raises((PermissionError, ValueError)):
        make_gateway(db_session).execute(
            ToolExecutionRequest(
                task_id=task.id,
                tool_name="file_read",
                action="read_metadata",
                workspace=REPO_ROOT,
                parameters={"relative_path": ".env"},
                granted_permission=PermissionLevel.SAFE_READ,
            )
        )


def test_failed_execution_creates_audit(db_session):
    class FailingExecutor:
        def execute(self, action, parameters, workspace):
            raise RuntimeError("fixture execution failed")

    task = make_task(db_session)
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="failing_read",
            description="test failure",
            risk_level="low",
            permission_level=PermissionLevel.SAFE_READ,
            allowed_actions=("read",),
            executor=FailingExecutor(),
        )
    )
    validator = WorkspaceValidator(REPO_ROOT)
    result = ToolGateway(
        db_session,
        registry,
        validator,
        Path(DATA_ROOT) / "test-runs" / "phase4-artifacts",
    ).execute(
        ToolExecutionRequest(
            task_id=task.id,
            tool_name="failing_read",
            action="read",
            workspace=REPO_ROOT,
            parameters={},
            granted_permission=PermissionLevel.SAFE_READ,
        )
    )

    assert result.status == "FAILED"
    execution = db_session.get(ToolExecutionRecord, result.execution_id)
    assert execution is not None
    assert execution.status == "FAILED"
    events = (
        db_session.query(AuditEventRecord)
        .filter_by(task_id=task.id, event_type="TOOL_EXECUTION")
        .all()
    )
    payloads = [json.loads(event.payload_summary) for event in events]
    assert any(payload["tool_name"] == "failing_read" for payload in payloads)
