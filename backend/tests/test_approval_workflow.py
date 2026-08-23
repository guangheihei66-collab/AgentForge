import json
from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path

import pytest

from app.approvals.service import ApprovalError, ApprovalService
from app.capabilities.models import CapabilityRequest
from app.capabilities.registry import build_default_capability_registry
from app.capabilities.resolver import CapabilityResolver
from app.domain.states.task_state import TaskStatus
from app.permissions.levels import PermissionLevel
from app.services.task_service import TaskService
from app.storage.orm import ApprovalRecord, AuditEventRecord, PlanRecord, TaskRecord
from app.tools.defaults import build_default_registry
from app.tools.gateway import ToolExecutionRequest, ToolGateway
from app.workspace.validator import WorkspaceValidator


REPO_ROOT = r"D:\AgentProjects\AgentForge"
ARTIFACT_ROOT = Path(r"D:\AgentProjectData\AgentForge") / "test-runs" / "phase5-artifacts"


def make_task(session):
    return TaskService(session).create_task(
        title="Approval test",
        goal="Exercise approval governance",
        workspace=REPO_ROOT,
    )


def make_plan(session, task, version=1):
    task_record = session.get(TaskRecord, task.id)
    if task_record.status == TaskStatus.CREATED.value:
        TaskService(session).transition_task(task.id, TaskStatus.PLANNING)
    plan = PlanRecord(
        task_id=task.id,
        version=version,
        plan_json={
            "schema_version": 2,
            "steps": [{
                "step_id": "step-1",
                "capability_id": "test_verification",
                "parameters": {"profile": "smoke"},
            }],
            "resolved_steps": [],
        },
        validation_status="VALID",
        created_at=datetime.now(timezone.utc),
    )
    session.add(plan)
    session.flush()
    validator = WorkspaceValidator(REPO_ROOT)
    snapshot = CapabilityResolver(
        build_default_capability_registry(), build_default_registry(validator)
    ).resolve(
        task_id=task.id,
        plan_id=plan.id,
        plan_version=version,
        step_id="step-1",
        request=CapabilityRequest("test_verification", {"profile": "smoke"}),
    )
    plan.plan_json = {**plan.plan_json, "resolved_steps": [snapshot.to_dict()]}
    session.commit()
    return plan


def make_gateway(session):
    validator = WorkspaceValidator(REPO_ROOT)
    return ToolGateway(session, build_default_registry(validator), validator, ARTIFACT_ROOT)


def test_create_approve_and_audit(db_session):
    task = make_task(db_session)
    plan = make_plan(db_session, task)
    service = ApprovalService(db_session)

    approval = service.create_request(
        task_id=task.id, plan_id=plan.id, plan_version=1, requested_by="requester"
    )
    assert approval.decision == "PENDING"
    assert db_session.get(ApprovalRecord, approval.id) is not None

    approval = service.approve(approval.id, actor="approver", reason="Looks good")
    assert approval.decision == "APPROVED"
    assert db_session.get(TaskRecord, task.id).status == TaskStatus.RUNNING.value

    events = db_session.query(AuditEventRecord).filter_by(task_id=task.id).all()
    event_types = [event.event_type for event in events]
    assert "APPROVAL_CREATED" in event_types
    assert "APPROVED" in event_types
    approved_event = next(event for event in events if event.event_type == "APPROVED")
    assert json.loads(approved_event.payload_summary)["plan_version"] == 1


def test_reject_and_cancel(db_session):
    task = make_task(db_session)
    plan = make_plan(db_session, task)
    service = ApprovalService(db_session)
    approval = service.create_request(
        task_id=task.id, plan_id=plan.id, plan_version=1, requested_by="requester"
    )

    rejected = service.reject(approval.id, actor="approver", reason="Needs revision")
    assert rejected.decision == "REJECTED"

    second_plan = make_plan(db_session, task, version=2)
    second = service.create_request(
        task_id=task.id,
        plan_id=second_plan.id,
        plan_version=2,
        requested_by="requester",
    )
    cancelled = service.cancel_task(task.id, actor="owner", reason="User cancelled")
    assert cancelled.status == TaskStatus.CANCELLED.value
    assert db_session.get(ApprovalRecord, second.id).decision == "CANCELLED"
    event_types = [
        event.event_type
        for event in db_session.query(AuditEventRecord).filter_by(task_id=task.id).all()
    ]
    assert "REJECTED" in event_types
    assert "CANCELLED" in event_types


def test_protected_tool_requires_current_approved_plan(db_session):
    task = make_task(db_session)
    plan = make_plan(db_session, task)
    request = ToolExecutionRequest(
        task_id=task.id,
        tool_name="test_run",
        action="run_profile",
        workspace=REPO_ROOT,
        parameters={"profile": "smoke"},
        granted_permission=PermissionLevel.APPROVED_EXEC,
        approved=True,
        plan_id=plan.id,
        plan_version=1,
    )
    with pytest.raises(ApprovalError):
        make_gateway(db_session).execute(request)

    approval = ApprovalService(db_session).create_request(
        task_id=task.id, plan_id=plan.id, plan_version=1, requested_by="requester"
    )
    ApprovalService(db_session).approve(approval.id, actor="approver")
    with pytest.raises(ApprovalError):
        make_gateway(db_session).execute(
            replace(request, plan_version=2)
        )

    ApprovalService(db_session).cancel_task(task.id, actor="owner")
    with pytest.raises(ApprovalError):
        make_gateway(db_session).execute(request)
