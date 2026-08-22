import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.agent_runtime.executor import RuntimeExecutor
from app.agent_runtime.runtime import AgentRuntime
from app.agent_runtime.state import RuntimeDecision, RuntimeState
from app.approvals.service import ApprovalError, ApprovalService
from app.domain.states.task_state import TaskStatus
from app.permissions.levels import PermissionLevel
from app.services.task_service import TaskService
from app.storage.orm import AuditEventRecord, PlanRecord, TaskRecord, ToolExecutionRecord
from app.tools.defaults import build_default_registry
from app.tools.gateway import ToolGateway
from app.tools.models import ToolDefinition
from app.tools.registry import ToolRegistry
from app.workspace.validator import WorkspaceValidator


REPO_ROOT = r"D:\AgentProjects\AgentForge"
DATA_ROOT = r"D:\AgentProjectData\AgentForge"


def make_task(session):
    return TaskService(session).create_task(
        title="Runtime test task",
        goal="Exercise deterministic runtime",
        workspace=REPO_ROOT,
    )


def make_plan(session, task, steps):
    TaskService(session).transition_task(task.id, TaskStatus.PLANNING)
    plan = PlanRecord(
        task_id=task.id,
        version=1,
        plan_json={"steps": steps},
        validation_status="VALID",
        created_at=datetime.now(timezone.utc),
    )
    session.add(plan)
    session.flush()
    session.commit()
    ApprovalService(session).create_request(
        task_id=task.id,
        plan_id=plan.id,
        plan_version=plan.version,
        requested_by="runtime-test",
    )
    ApprovalService(session).approve(plan_approval_id(session, plan), actor="reviewer")
    return plan


def plan_approval_id(session, plan):
    from app.storage.orm import ApprovalRecord

    return session.query(ApprovalRecord).filter_by(plan_id=plan.id).one().id


def make_gateway(session, registry=None):
    validator = WorkspaceValidator(REPO_ROOT)
    return ToolGateway(
        session=session,
        registry=registry or build_default_registry(validator),
        workspace_validator=validator,
        artifact_root=Path(DATA_ROOT) / "test-runs" / "runtime-artifacts",
    )


def runtime_steps(*tools):
    actions = {
        "git_read": ("check git status", "low", "SAFE_READ"),
        "test_run": ("run smoke tests", "medium", "APPROVED_EXEC"),
    }
    return [
        {
            "step_id": f"step-{index}",
            "tool": tool,
            "action": actions[tool][0],
            "risk_level": actions[tool][1],
            "permission_level": actions[tool][2],
        }
        for index, tool in enumerate(tools, start=1)
    ]


def test_runtime_successful_loop_and_completion(db_session):
    task = make_task(db_session)
    plan = make_plan(db_session, task, runtime_steps("git_read", "test_run"))
    runtime = AgentRuntime(db_session, RuntimeExecutor(make_gateway(db_session)))

    result = runtime.run(task_id=task.id, plan_id=plan.id, plan_version=1)

    assert result.state == RuntimeState.COMPLETED
    assert result.decision == RuntimeDecision.COMPLETE
    assert result.completed_steps == 2
    assert db_session.get(TaskRecord, task.id).status == TaskStatus.SUCCESS.value
    assert db_session.query(ToolExecutionRecord).filter_by(task_id=task.id).count() == 2
    decisions = db_session.query(AuditEventRecord).filter_by(
        task_id=task.id, event_type="RUNTIME_DECISION"
    ).all()
    assert json.loads(decisions[-1].payload_summary)["decision"] == "COMPLETE"


def test_runtime_handles_tool_failure(db_session):
    class FailingExecutor:
        def execute(self, action, parameters, workspace):
            raise RuntimeError("runtime fixture failure")

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="git_read",
            description="runtime failure fixture",
            risk_level="low",
            permission_level=PermissionLevel.SAFE_READ,
            allowed_actions=("status",),
            executor=FailingExecutor(),
        )
    )
    task = make_task(db_session)
    plan = make_plan(db_session, task, runtime_steps("git_read"))
    runtime = AgentRuntime(db_session, RuntimeExecutor(make_gateway(db_session, registry)))

    result = runtime.run(task_id=task.id, plan_id=plan.id, plan_version=1)

    assert result.state == RuntimeState.FAILED
    assert result.decision == RuntimeDecision.FAIL
    assert db_session.get(TaskRecord, task.id).status == TaskStatus.FAILED.value
    assert "runtime fixture failure" in result.observations[0].tool_result_summary


def test_runtime_requires_approval_before_tool_execution(db_session):
    task = make_task(db_session)
    TaskService(db_session).transition_task(task.id, TaskStatus.PLANNING)
    plan = PlanRecord(
        task_id=task.id,
        version=1,
        plan_json={"steps": runtime_steps("git_read")},
        validation_status="VALID",
    )
    db_session.add(plan)
    db_session.commit()
    runtime = AgentRuntime(db_session, RuntimeExecutor(make_gateway(db_session)))

    with pytest.raises(ApprovalError):
        runtime.run(task_id=task.id, plan_id=plan.id, plan_version=1)

    assert db_session.query(ToolExecutionRecord).filter_by(task_id=task.id).count() == 0
    assert db_session.get(TaskRecord, task.id).status == TaskStatus.PLANNING.value


def test_runtime_state_transitions_are_recorded(db_session):
    task = make_task(db_session)
    plan = make_plan(db_session, task, runtime_steps("git_read", "test_run"))
    runtime = AgentRuntime(db_session, RuntimeExecutor(make_gateway(db_session)))

    result = runtime.run(task_id=task.id, plan_id=plan.id, plan_version=1)

    transitions = db_session.query(AuditEventRecord).filter_by(
        task_id=task.id, event_type="RUNTIME_TRANSITION"
    ).all()
    payloads = [json.loads(event.payload_summary) for event in transitions]
    assert result.state == RuntimeState.COMPLETED
    assert payloads[0]["to"] == "RUNNING"
    assert any(payload["to"] == "OBSERVING" for payload in payloads)
    assert payloads[-1]["to"] == "COMPLETED"
