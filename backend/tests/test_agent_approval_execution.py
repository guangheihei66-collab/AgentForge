from dataclasses import dataclass
from datetime import datetime, timezone
import json

import pytest

from app.agent_runtime import RuntimeResult, RuntimeState, RuntimeDecision
from app.agents.orchestration.service import (
    AgentApprovalExecutionService,
    AgentExecutionInitiationError,
)
from app.audit.provenance import persist_provenance_event
from app.approvals.service import ApprovalError, ApprovalService
from app.capabilities.models import CapabilityRequest
from app.capabilities.registry import build_default_capability_registry
from app.capabilities.resolver import CapabilityResolver
from app.domain.states.task_state import TaskStatus
from app.services.task_service import TaskService
from app.storage.orm import ApprovalRecord, AuditEventRecord, PlanRecord, TaskRecord, ToolExecutionRecord
from app.tools.defaults import build_default_registry
from app.workspace.validator import WorkspaceValidator
from tests.project_test_support import project_fixture, project_workspace, with_project_authority


@dataclass
class RecordingRuntime:
    result: RuntimeResult | None = None
    error: Exception | None = None

    def __post_init__(self):
        self.calls: list[dict] = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        assert self.result is not None
        return self.result


def make_task(session, title="Agent command test"):
    project = project_fixture(session)
    return TaskService(session).create_task(
        project_id=project.id,
        title=title,
        goal="Verify the approved Agent command",
    )


def make_plan(session, task: TaskRecord, version=1):
    persisted_task = session.get(TaskRecord, task.id)
    if persisted_task is not None and persisted_task.status == TaskStatus.CREATED.value:
        TaskService(session).transition_task(task.id, TaskStatus.PLANNING)
    steps = [{"step_id": f"step-{version}", "capability_id": "repository_state", "parameters": {}}]
    plan = PlanRecord(
        task_id=task.id,
        version=version,
        plan_json=with_project_authority(
            session,
            task,
            {"schema_version": 2, "steps": steps, "resolved_steps": []},
        ),
        validation_status="VALID",
        created_at=datetime.now(timezone.utc),
    )
    session.add(plan)
    session.flush()
    registry = build_default_registry(WorkspaceValidator(project_workspace(session)))
    resolved = CapabilityResolver(
        build_default_capability_registry(), registry
    ).resolve(
        task_id=task.id,
        plan_id=plan.id,
        plan_version=version,
        step_id=steps[0]["step_id"],
        request=CapabilityRequest("repository_state", {}),
    )
    plan.plan_json = {**plan.plan_json, "resolved_steps": [resolved.to_dict()]}
    session.commit()
    return plan


def make_pending(session, task, version=1):
    plan = make_plan(session, task, version)
    approval = ApprovalService(session).create_request(
        task_id=task.id,
        plan_id=plan.id,
        plan_version=version,
        requested_by="operator",
    )
    return plan, approval


def make_result(task_id, plan_id, plan_version=1):
    return RuntimeResult(
        task_id=task_id,
        plan_id=plan_id,
        plan_version=plan_version,
        state=RuntimeState.COMPLETED,
        decision=RuntimeDecision.COMPLETE,
        completed_steps=1,
        observations=(),
    )


def audit_payloads(session, task_id):
    return [
        (event.event_type, event.correlation_id, json.loads(event.payload_summary))
        for event in session.query(AuditEventRecord)
        .filter_by(task_id=task_id)
        .filter(AuditEventRecord.event_type.in_({
            "AGENT_APPROVE_AND_EXECUTE_COMMAND_RECEIVED",
            "APPROVAL_COMMAND_SUCCEEDED",
            "APPROVAL_COMMAND_FAILED",
            "EXECUTION_INITIATION_REQUESTED",
            "EXECUTION_INITIATION_STARTED",
            "EXECUTION_INITIATION_FAILED",
        }))
        .order_by(AuditEventRecord.created_at.asc(), AuditEventRecord.id.asc())
        .all()
    ]


def command(session, runtime, *, task_id, approval_id, plan_id, plan_version=1):
    return AgentApprovalExecutionService(
        session, runtime_factory=lambda _task_id: runtime
    ).approve_and_execute(
        task_id=task_id,
        approval_id=approval_id,
        plan_id=plan_id,
        plan_version=plan_version,
        actor="operator",
    )


def test_valid_pending_approval_is_persisted_then_runtime_invoked_once(db_session):
    task = make_task(db_session)
    plan, approval = make_pending(db_session, task)
    runtime = RecordingRuntime(make_result(task.id, plan.id))

    result = command(
        db_session,
        runtime,
        task_id=task.id,
        approval_id=approval.id,
        plan_id=plan.id,
    )

    refreshed = db_session.get(ApprovalRecord, approval.id)
    assert result is runtime.result
    assert refreshed.decision == "APPROVED"
    assert db_session.get(TaskRecord, task.id).status == TaskStatus.RUNNING.value
    assert len(runtime.calls) == 1
    assert runtime.calls[0] == {
        "task_id": task.id,
        "plan_id": plan.id,
        "plan_version": 1,
    }
    provenance = audit_payloads(db_session, task.id)
    received = next(item for item in provenance if item[0] == "AGENT_APPROVE_AND_EXECUTE_COMMAND_RECEIVED")
    succeeded = next(item for item in provenance if item[0] == "APPROVAL_COMMAND_SUCCEEDED")
    requested = next(item for item in provenance if item[0] == "EXECUTION_INITIATION_REQUESTED")
    started = next(item for item in provenance if item[0] == "EXECUTION_INITIATION_STARTED")
    assert received[1] == succeeded[1] == requested[1] == started[1]
    assert received[2] == {
        "approval_id": approval.id,
        "command_kind": "AGENT_APPROVE_AND_EXECUTE",
        "outcome": "RECEIVED",
        "plan_id": plan.id,
        "plan_version": 1,
        "task_id": task.id,
        "task_state": "WAITING_APPROVAL",
    }
    assert succeeded[2]["authority_validation"] == "PASSED"
    assert succeeded[2]["approval_persistence"] == "APPROVED"
    assert succeeded[2]["task_state"] == "RUNNING"
    assert requested[2]["execution_initiation"] == "REQUESTED"
    assert started[2]["execution_initiation"] == "STARTED"


def test_already_approved_plan_can_resume_once_through_composite_command(db_session):
    task = make_task(db_session)
    plan, approval = make_pending(db_session, task)
    ApprovalService(db_session).approve(approval.id, actor="operator")
    runtime = RecordingRuntime(make_result(task.id, plan.id))

    result = command(
        db_session,
        runtime,
        task_id=task.id,
        approval_id=approval.id,
        plan_id=plan.id,
    )

    assert result is runtime.result
    assert db_session.get(ApprovalRecord, approval.id).decision == "APPROVED"
    assert db_session.get(TaskRecord, task.id).status == TaskStatus.RUNNING.value
    assert len(runtime.calls) == 1
    provenance = audit_payloads(db_session, task.id)
    received = next(item for item in provenance if item[0] == "AGENT_APPROVE_AND_EXECUTE_COMMAND_RECEIVED")
    succeeded = next(item for item in provenance if item[0] == "APPROVAL_COMMAND_SUCCEEDED")
    requested = next(item for item in provenance if item[0] == "EXECUTION_INITIATION_REQUESTED")
    started = next(item for item in provenance if item[0] == "EXECUTION_INITIATION_STARTED")
    assert received[1] == succeeded[1] == requested[1] == started[1]
    assert succeeded[2]["approval_state"] == "APPROVED"
    assert succeeded[2]["approval_persistence"] == "ALREADY_APPROVED"
    assert succeeded[2]["outcome"] == "APPROVAL_REUSED"
    assert requested[2]["execution_initiation"] == "REQUESTED"
    assert started[2]["execution_initiation"] == "STARTED"


def test_approval_bound_to_another_task_is_rejected_without_runtime(db_session):
    first = make_task(db_session, "First Agent command test")
    second = make_task(db_session, "Second Agent command test")
    first_plan, approval = make_pending(db_session, first)
    second_plan = make_plan(db_session, second)
    runtime = RecordingRuntime(make_result(second.id, second_plan.id))

    with pytest.raises(ApprovalError, match="Approval is not bound"):
        command(
            db_session,
            runtime,
            task_id=second.id,
            approval_id=approval.id,
            plan_id=second_plan.id,
        )

    assert runtime.calls == []
    assert db_session.get(ApprovalRecord, approval.id).decision == "PENDING"
    provenance = audit_payloads(db_session, second.id)
    failure = next(item for item in provenance if item[0] == "APPROVAL_COMMAND_FAILED")
    assert failure[2]["approval_id"] == approval.id
    assert failure[2]["authority_validation"] == "FAILED"
    assert failure[2]["execution_initiation"] == "NOT_REQUESTED"
    assert failure[2]["error_category"] == "AUTHORITY_REJECTED"


def test_older_plan_approval_cannot_execute_current_successor(db_session):
    task = make_task(db_session)
    old_plan, approval = make_pending(db_session, task)
    current_plan = make_plan(db_session, task, version=2)
    runtime = RecordingRuntime(make_result(task.id, current_plan.id, 2))

    with pytest.raises(ApprovalError, match="current Plan"):
        command(
            db_session,
            runtime,
            task_id=task.id,
            approval_id=approval.id,
            plan_id=old_plan.id,
        )

    assert runtime.calls == []
    assert db_session.get(ApprovalRecord, approval.id).decision == "PENDING"
    failure = next(item for item in audit_payloads(db_session, task.id) if item[0] == "APPROVAL_COMMAND_FAILED")
    assert failure[2]["error_category"] == "AUTHORITY_REJECTED"
    assert failure[2]["execution_initiation"] == "NOT_REQUESTED"


def test_plan_id_mismatch_is_rejected(db_session):
    task = make_task(db_session)
    plan, approval = make_pending(db_session, task)
    other_plan = make_plan(db_session, task, version=2)
    runtime = RecordingRuntime(make_result(task.id, plan.id))

    with pytest.raises(ApprovalError, match="current Plan"):
        command(
            db_session,
            runtime,
            task_id=task.id,
            approval_id=approval.id,
            plan_id=other_plan.id,
        )

    assert runtime.calls == []
    failure = next(item for item in audit_payloads(db_session, task.id) if item[0] == "APPROVAL_COMMAND_FAILED")
    assert failure[2]["error_category"] == "AUTHORITY_REJECTED"


def test_plan_version_mismatch_is_rejected(db_session):
    task = make_task(db_session)
    plan, approval = make_pending(db_session, task)
    runtime = RecordingRuntime(make_result(task.id, plan.id))

    with pytest.raises(ApprovalError, match="current Plan"):
        command(
            db_session,
            runtime,
            task_id=task.id,
            approval_id=approval.id,
            plan_id=plan.id,
            plan_version=2,
        )

    assert runtime.calls == []
    failure = next(item for item in audit_payloads(db_session, task.id) if item[0] == "APPROVAL_COMMAND_FAILED")
    assert failure[2]["error_category"] == "AUTHORITY_REJECTED"


def test_rejected_approval_is_not_executable(db_session):
    task = make_task(db_session)
    plan, approval = make_pending(db_session, task)
    ApprovalService(db_session).reject(approval.id, actor="operator", reason="needs changes")
    runtime = RecordingRuntime(make_result(task.id, plan.id))

    with pytest.raises(ApprovalError, match="already decided"):
        command(
            db_session,
            runtime,
            task_id=task.id,
            approval_id=approval.id,
            plan_id=plan.id,
        )

    assert runtime.calls == []


def test_duplicate_command_cannot_invoke_runtime_twice(db_session):
    task = make_task(db_session)
    plan, approval = make_pending(db_session, task)
    runtime = RecordingRuntime(make_result(task.id, plan.id))
    service = AgentApprovalExecutionService(
        db_session, runtime_factory=lambda _task_id: runtime
    )

    service.approve_and_execute(
        task_id=task.id,
        approval_id=approval.id,
        plan_id=plan.id,
        plan_version=1,
        actor="operator",
    )
    with pytest.raises(ApprovalError, match="already decided"):
        service.approve_and_execute(
            task_id=task.id,
            approval_id=approval.id,
            plan_id=plan.id,
            plan_version=1,
            actor="operator",
        )

    assert len(runtime.calls) == 1
    failures = [item for item in audit_payloads(db_session, task.id) if item[0] == "APPROVAL_COMMAND_FAILED"]
    assert len(failures) == 1
    assert failures[0][2]["error_category"] == "AUTHORITY_REJECTED"


def test_runtime_initiation_failure_is_explicit_and_terminal(db_session):
    task = make_task(db_session)
    plan, approval = make_pending(db_session, task)
    runtime = RecordingRuntime(error=RuntimeError("do not persist this detail"))

    with pytest.raises(AgentExecutionInitiationError, match="Execution initiation failed"):
        command(
            db_session,
            runtime,
            task_id=task.id,
            approval_id=approval.id,
            plan_id=plan.id,
        )

    assert db_session.get(TaskRecord, task.id).status == TaskStatus.FAILED.value
    assert db_session.query(ToolExecutionRecord).filter_by(task_id=task.id).count() == 0
    audit = db_session.query(AuditEventRecord).filter_by(task_id=task.id).all()
    failure = [event for event in audit if event.event_type == "EXECUTION_INITIATION_FAILED"]
    assert len(failure) == 1
    assert "do not persist this detail" not in failure[0].payload_summary
    provenance = audit_payloads(db_session, task.id)
    assert any(item[0] == "AGENT_APPROVE_AND_EXECUTE_COMMAND_RECEIVED" for item in provenance)
    assert any(item[0] == "APPROVAL_COMMAND_SUCCEEDED" for item in provenance)
    assert any(item[0] == "EXECUTION_INITIATION_REQUESTED" for item in provenance)
    assert any(item[0] == "EXECUTION_INITIATION_STARTED" for item in provenance)
    initiation_failure = next(item for item in provenance if item[0] == "EXECUTION_INITIATION_FAILED")
    assert initiation_failure[2]["execution_initiation"] == "FAILED"
    assert initiation_failure[2]["error_category"] == "RUNTIME_START_FAILED"
    assert "do not persist this detail" not in initiation_failure[2].values()


def test_missing_current_plan_is_rejected_without_runtime(db_session):
    task = make_task(db_session)
    runtime = RecordingRuntime()

    with pytest.raises(LookupError, match="No valid current Plan"):
        command(
            db_session,
            runtime,
            task_id=task.id,
            approval_id="missing-approval",
            plan_id="missing-plan",
        )

    assert runtime.calls == []


def test_command_provenance_allowlists_metadata_and_never_persists_hidden_content(db_session):
    task = make_task(db_session)

    event = persist_provenance_event(
        db_session,
        task_id=task.id,
        event_type="APPROVAL_COMMAND_FAILED",
        actor="operator",
        correlation_id="1e0a5e0b-4fbd-4d36-a3bd-16dd0e6c11af",
        fields={
            "command_kind": "AGENT_APPROVE_AND_EXECUTE",
            "outcome": "REJECTED",
            "secret": "DO_NOT_PERSIST_SECRET",
            "raw_stack_trace": "DO_NOT_PERSIST_STACK",
            "chain_of_thought": "DO_NOT_PERSIST_REASONING",
        },
    )

    assert "DO_NOT_PERSIST_SECRET" not in event.payload_summary
    assert "DO_NOT_PERSIST_STACK" not in event.payload_summary
    assert "DO_NOT_PERSIST_REASONING" not in event.payload_summary
    assert json.loads(event.payload_summary) == {
        "command_kind": "AGENT_APPROVE_AND_EXECUTE",
        "outcome": "REJECTED",
        "task_id": task.id,
    }
