import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.domain.states.task_state import TaskStatus
from app.approvals.service import ApprovalError, ApprovalService
from app.capabilities.models import CapabilityRequest
from app.capabilities.registry import build_default_capability_registry
from app.capabilities.resolver import CapabilityResolver
from app.permissions.levels import PermissionLevel
from app.services.task_service import TaskService
from app.storage.orm import AuditEventRecord, EvidenceRecord, PlanRecord, ToolExecutionRecord
from app.tools.defaults import build_default_registry
from app.tools.gateway import ToolExecutionRequest, ToolGateway
from app.tools.models import ToolDefinition
from app.tools.registry import ToolRegistry
from app.workspace.validator import WorkspaceValidator
from tests.project_test_support import (artifact_root, create_project_task,
                                        project_context, project_workspace,
                                        with_project_authority)


REPO_ROOT = r"D:\AgentProjects\AgentForge"
DATA_ROOT = r"D:\AgentProjectData\AgentForge"


def make_gateway(session):
    validator = WorkspaceValidator(project_workspace(session))
    return ToolGateway(
        session=session,
        registry=build_default_registry(validator),
        workspace_validator=validator,
        artifact_root=Path(artifact_root(session)),
    )


def make_task(session):
    return create_project_task(session,
        title="Tool gateway test",
        goal="Exercise a read-safe tool",
    )


def approve_plan(session, task):
    TaskService(session).transition_task(task.id, TaskStatus.PLANNING)
    plan = PlanRecord(
        task_id=task.id,
        version=1,
        plan_json=with_project_authority(session, task, {
            "schema_version": 2,
            "steps": [{
                "step_id": "step-1",
                "capability_id": "test_verification",
                "parameters": {"profile": "smoke"},
            }],
            "resolved_steps": [],
        }),
        validation_status="VALID",
        created_at=datetime.now(timezone.utc),
    )
    session.add(plan)
    session.flush()
    validator = WorkspaceValidator(project_workspace(session))
    snapshot = CapabilityResolver(
        build_default_capability_registry(), build_default_registry(validator)
    ).resolve(
        task_id=task.id,
        plan_id=plan.id,
        plan_version=plan.version,
        step_id="step-1",
        request=CapabilityRequest("test_verification", {"profile": "smoke"}),
    )
    plan.plan_json = {**plan.plan_json, "resolved_steps": [snapshot.to_dict()]}
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
    plan = approve_plan(db_session, task)
    result = make_gateway(db_session).execute(
        ToolExecutionRequest(
            task_id=task.id,
            tool_name="git_read",
            action="status",
            workspace=project_workspace(db_session),
            parameters={},
            granted_permission=PermissionLevel.SAFE_READ,
            plan_id=plan.id,
            plan_version=plan.version,
            project_authority_fingerprint=project_context(db_session).authority_fingerprint,
        )
    )

    assert result.status == "SUCCESS"
    assert result.evidence_id is not None
    execution = db_session.get(ToolExecutionRecord, result.execution_id)
    assert execution is not None
    assert execution.status == "SUCCESS"
    assert Path(result.artifact_path).is_relative_to(Path(artifact_root(db_session)))


def test_test_profile_execution(db_session):
    task = make_task(db_session)
    plan = approve_plan(db_session, task)
    result = make_gateway(db_session).execute(
        ToolExecutionRequest(
            task_id=task.id,
            tool_name="test_run",
            action="run_profile",
            workspace=project_workspace(db_session),
            parameters={"profile": "smoke"},
            granted_permission=PermissionLevel.APPROVED_EXEC,
            approved=True,
            plan_id=plan.id,
            plan_version=plan.version,
            project_authority_fingerprint=project_context(db_session).authority_fingerprint,
        )
    )

    assert result.status == "SUCCESS"
    assert "smoke" in result.summary


def test_missing_permission_rejected(db_session):
    task = make_task(db_session)
    plan = approve_plan(db_session, task)

    with pytest.raises(PermissionError):
        make_gateway(db_session).execute(
            ToolExecutionRequest(
                task_id=task.id,
                tool_name="test_run",
                action="run_profile",
                workspace=project_workspace(db_session),
                parameters={"profile": "smoke"},
                plan_id=plan.id,
                plan_version=plan.version,
                project_authority_fingerprint=project_context(db_session).authority_fingerprint,
            )
        )


def test_invalid_workspace_rejected(db_session):
    task = make_task(db_session)
    plan = approve_plan(db_session, task)

    with pytest.raises(ApprovalError):
        make_gateway(db_session).execute(
            ToolExecutionRequest(
                task_id=task.id,
                tool_name="git_read",
                action="status",
                workspace=DATA_ROOT,
                parameters={},
                granted_permission=PermissionLevel.SAFE_READ,
                plan_id=plan.id,
                plan_version=plan.version,
                project_authority_fingerprint=project_context(db_session).authority_fingerprint,
            )
        )


def test_secret_file_access_rejected(db_session):
    task = make_task(db_session)
    plan = approve_plan(db_session, task)

    with pytest.raises((PermissionError, ValueError)):
        make_gateway(db_session).execute(
            ToolExecutionRequest(
                task_id=task.id,
                tool_name="file_read",
                action="read_metadata",
                workspace=project_workspace(db_session),
                parameters={"relative_path": ".env"},
                granted_permission=PermissionLevel.SAFE_READ,
                plan_id=plan.id,
                plan_version=plan.version,
                project_authority_fingerprint=project_context(db_session).authority_fingerprint,
            )
        )


def test_failed_execution_creates_audit(db_session):
    class FailingExecutor:
        def execute(self, action, parameters, workspace):
            raise RuntimeError("fixture execution failed")

    task = make_task(db_session)
    plan = approve_plan(db_session, task)
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
    validator = WorkspaceValidator(project_workspace(db_session))
    result = ToolGateway(
        db_session,
        registry,
        validator,
        Path(artifact_root(db_session)),
    ).execute(
        ToolExecutionRequest(
            task_id=task.id,
            tool_name="failing_read",
            action="read",
            workspace=project_workspace(db_session),
            parameters={},
            granted_permission=PermissionLevel.SAFE_READ,
            plan_id=plan.id,
            plan_version=plan.version,
            project_authority_fingerprint=project_context(db_session).authority_fingerprint,
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
