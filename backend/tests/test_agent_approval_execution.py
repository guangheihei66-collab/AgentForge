from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from app.agent_runtime import RuntimeResult, RuntimeState, RuntimeDecision
from app.agents.orchestration.service import (
    AgentApprovalExecutionService,
    AgentExecutionInitiationError,
)
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
