import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.agent_runtime.executor import RuntimeExecutor
from app.agent_runtime.runtime import AgentRuntime
from app.agent_runtime.state import RuntimeDecision, RuntimeState
from app.approvals.service import ApprovalError, ApprovalService
from app.capabilities.models import CapabilityRequest
from app.capabilities.registry import build_default_capability_registry
from app.capabilities.resolver import CapabilityResolver
from app.domain.states.task_state import TaskStatus
from app.permissions.levels import PermissionLevel
from app.services.task_service import TaskService
from app.storage.orm import AuditEventRecord, PlanRecord, TaskRecord, ToolExecutionRecord
from app.tools.defaults import build_default_registry
from app.tools.gateway import ToolGateway
from app.tools.models import ToolDefinition
from app.tools.registry import ToolRegistry
from app.workspace.validator import WorkspaceValidator
from tests.project_test_support import (artifact_root, create_project_task,
                                        project_workspace, with_project_authority)


REPO_ROOT = r"D:\AgentProjects\AgentForge"
DATA_ROOT = r"D:\AgentProjectData\AgentForge"


def make_task(session):
    return create_project_task(session,
        title="Runtime test task",
        goal="Exercise deterministic runtime",
    )


def make_plan(session, task, steps, registry=None, approve=True):
    TaskService(session).transition_task(task.id, TaskStatus.PLANNING)
    plan = PlanRecord(
        task_id=task.id,
        version=1,
        plan_json=with_project_authority(session, task, {"schema_version": 2, "steps": steps, "resolved_steps": []}),
        validation_status="VALID",
        created_at=datetime.now(timezone.utc),
    )
    session.add(plan)
    session.flush()
    tool_registry = registry or build_default_registry(WorkspaceValidator(project_workspace(session)))
    resolver = CapabilityResolver(build_default_capability_registry(), tool_registry)
    resolved = [
        resolver.resolve(
            task_id=task.id,
            plan_id=plan.id,
            plan_version=plan.version,
            step_id=step["step_id"],
            request=CapabilityRequest(step["capability_id"], step["parameters"]),
        ).to_dict()
        for step in steps
    ]
    plan.plan_json = {**plan.plan_json, "resolved_steps": resolved}
    session.commit()
    if approve:
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
    validator = WorkspaceValidator(project_workspace(session))
    return ToolGateway(
        session=session,
        registry=registry or build_default_registry(validator),
        workspace_validator=validator,
        artifact_root=Path(artifact_root(session)),
    )


def runtime_steps(*tools):
    capabilities = {
        "git_read": ("repository_state", {}),
        "test_run": ("test_verification", {"profile": "smoke"}),
    }
    return [
        {
            "step_id": f"step-{index}",
            "capability_id": capabilities[tool][0],
            "parameters": capabilities[tool][1],
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
    plan = make_plan(db_session, task, runtime_steps("git_read"), registry=registry)
    runtime = AgentRuntime(db_session, RuntimeExecutor(make_gateway(db_session, registry)))

    result = runtime.run(task_id=task.id, plan_id=plan.id, plan_version=1)

    assert result.state == RuntimeState.FAILED
    assert result.decision == RuntimeDecision.FAIL
    assert db_session.get(TaskRecord, task.id).status == TaskStatus.FAILED.value
    assert "runtime fixture failure" in result.observations[0].tool_result_summary


def test_runtime_requires_approval_before_tool_execution(db_session):
    task = make_task(db_session)
    plan = make_plan(db_session, task, runtime_steps("git_read"), approve=False)
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
