import pytest
from pathlib import Path

from app.agents.providers.mock import MockLLMProvider
from app.agent_runtime.executor import RuntimeExecutor
from app.agent_runtime.runtime import AgentRuntime
from app.analyst.models import AnalystSynthesisStatus
from app.analyst.service import AnalystService
from app.agent_runtime.state import RuntimeDecision, RuntimeState
from app.approvals.service import ApprovalError
from app.permissions.levels import PermissionLevel
from app.storage.orm import AuditEventRecord, ToolExecutionRecord
from app.tools.models import ToolDefinition
from app.tools.registry import ToolRegistry
from tests.test_agent_runtime import (
    make_gateway,
    make_plan,
    make_task,
    project_workspace,
    runtime_steps,
)
from tests.project_test_support import artifact_root


class RecordingAnalyst:
    def __init__(self, *, error: bool = False):
        self.calls: list[dict] = []
        self.error = error

    def synthesize(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise RuntimeError("analyst fixture failure must not change execution")
        return None


def test_runtime_invokes_analyst_after_terminal_success(db_session):
    task = make_task(db_session)
    plan = make_plan(db_session, task, runtime_steps("git_read"))
    analyst = RecordingAnalyst()
    runtime = AgentRuntime(
        db_session,
        RuntimeExecutor(make_gateway(db_session)),
        analyst_service=analyst,
    )

    result = runtime.run(task_id=task.id, plan_id=plan.id, plan_version=1)

    assert result.state is RuntimeState.COMPLETED
    assert result.decision is RuntimeDecision.COMPLETE
    assert analyst.calls == [
        {"task_id": task.id, "plan_id": plan.id, "plan_version": 1}
    ]


def test_runtime_persists_real_analyst_report_after_governed_execution(db_session):
    task = make_task(db_session)
    plan = make_plan(db_session, task, runtime_steps("git_read"))
    analyst = AnalystService(
        db_session,
        MockLLMProvider(),
        data_root=Path(artifact_root(db_session)),
    )
    runtime = AgentRuntime(
        db_session,
        RuntimeExecutor(make_gateway(db_session)),
        analyst_service=analyst,
    )

    result = runtime.run(task_id=task.id, plan_id=plan.id, plan_version=1)
    read_model = analyst.get_read_model(task.id)

    assert result.state is RuntimeState.COMPLETED
    assert read_model.status is AnalystSynthesisStatus.SUCCEEDED
    assert read_model.report is not None
    assert read_model.report.task_id == task.id
    assert read_model.report.plan_id == plan.id
    assert read_model.report.plan_version == 1
    assert read_model.artifact_path is not None
    assert Path(read_model.artifact_path).is_file()


def test_runtime_analyst_failure_does_not_change_terminal_execution(db_session):
    task = make_task(db_session)
    plan = make_plan(db_session, task, runtime_steps("git_read"))
    analyst = RecordingAnalyst(error=True)
    runtime = AgentRuntime(
        db_session,
        RuntimeExecutor(make_gateway(db_session)),
        analyst_service=analyst,
    )

    result = runtime.run(task_id=task.id, plan_id=plan.id, plan_version=1)

    assert result.state is RuntimeState.COMPLETED
    assert db_session.query(ToolExecutionRecord).filter_by(task_id=task.id).count() == 1
    failure_events = (
        db_session.query(AuditEventRecord)
        .filter_by(task_id=task.id, event_type="ANALYST_SYNTHESIS_FAILED")
        .all()
    )
    assert len(failure_events) == 1


def test_unapproved_runtime_cannot_reach_analyst(db_session):
    task = make_task(db_session)
    plan = make_plan(db_session, task, runtime_steps("git_read"), approve=False)
    analyst = RecordingAnalyst()
    runtime = AgentRuntime(
        db_session,
        RuntimeExecutor(make_gateway(db_session)),
        analyst_service=analyst,
    )

    with pytest.raises(ApprovalError):
        runtime.run(task_id=task.id, plan_id=plan.id, plan_version=1)

    assert analyst.calls == []
    assert db_session.query(ToolExecutionRecord).filter_by(task_id=task.id).count() == 0


def test_terminal_tool_failure_also_requests_analysis(db_session):
    class FailingExecutor:
        def execute(self, action, parameters, workspace):
            raise RuntimeError("bounded analyst runtime failure fixture")

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="git_read",
            description="failure fixture",
            risk_level="low",
            permission_level=PermissionLevel.SAFE_READ,
            allowed_actions=("status",),
            executor=FailingExecutor(),
        )
    )
    task = make_task(db_session)
    plan = make_plan(db_session, task, runtime_steps("git_read"), registry=registry)
    analyst = RecordingAnalyst()
    runtime = AgentRuntime(
        db_session,
        RuntimeExecutor(make_gateway(db_session, registry)),
        analyst_service=analyst,
    )

    result = runtime.run(task_id=task.id, plan_id=plan.id, plan_version=1)

    assert result.state is RuntimeState.FAILED
    assert result.decision is RuntimeDecision.FAIL
    assert analyst.calls == [
        {"task_id": task.id, "plan_id": plan.id, "plan_version": 1}
    ]
