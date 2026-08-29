"""Regression coverage for deterministic unit profiles and failed replans."""

import json
from pathlib import Path

from app.agents.orchestration.service import AgentApprovalExecutionService
from app.agents.providers.mock import MockLLMProvider
from app.agent_runtime import AgentRuntime, RuntimeExecutor
from app.analyst.models import OverallStatus, ReleaseRecommendation
from app.analyst.service import AnalystService
from app.approvals.service import ApprovalService
from app.diagnostics.service import _command_provenance
from app.domain.states.task_state import TaskStatus
from app.storage.orm import (
    ApprovalRecord,
    AuditEventRecord,
    EvidenceRecord,
    PlanRecord,
    TaskRecord,
    ToolExecutionRecord,
)
from app.tools.models import ToolDefinition
from app.tools.registry import ToolRegistry
from app.permissions.levels import PermissionLevel

from tests.project_test_support import artifact_root
from tests.test_agent_runtime import make_gateway, make_plan, make_task


class SixStepVerificationExecutor:
    def __init__(self):
        self.calls = 0

    def execute(self, action, parameters, workspace):
        del action, parameters, workspace
        self.calls += 1
        status = "FAILED" if self.calls == 6 else "SUCCESS"
        return {"status": status, "summary": f"verification step {self.calls}"}

    @staticmethod
    def classify_result(result):
        return result["status"]


class ValidationFailingReplan:
    def create_successor(self, **kwargs):
        del kwargs
        raise ValueError("replan proposal failed validation in regression fixture")


class RecordingAnalyst:
    def __init__(self):
        self.calls = []

    def synthesize(self, **kwargs):
        self.calls.append(kwargs)
        return None


def _six_step_fixture(session):
    executor = SixStepVerificationExecutor()
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="test_run",
            description="six-step deterministic verification fixture",
            risk_level="medium",
            permission_level=PermissionLevel.APPROVED_EXEC,
            allowed_actions=("run_profile",),
            executor=executor,
        )
    )
    task = make_task(session)
    steps = [
        {
            "step_id": f"step-{index}",
            "capability_id": "test_verification",
            "parameters": {"profile": "smoke"},
        }
        for index in range(1, 7)
    ]
    plan = make_plan(session, task, steps, registry=registry)
    approval = session.query(ApprovalRecord).filter_by(plan_id=plan.id).one()
    return task, plan, approval, executor, registry


def _run_after_sixth_failure(session, *, analyst_service):
    task, plan, approval, executor, registry = _six_step_fixture(session)
    gateway = make_gateway(session, registry)
    runtime = AgentRuntime(
        session,
        RuntimeExecutor(gateway),
        replanning_service=ValidationFailingReplan(),
        analyst_service=analyst_service,
    )
    service = AgentApprovalExecutionService(
        session, runtime_factory=lambda current_task_id: runtime
    )
    result = service.approve_and_execute(
        task_id=task.id,
        approval_id=approval.id,
        plan_id=plan.id,
        plan_version=plan.version,
        actor="reviewer",
    )
    return result, task, plan, approval, executor


def test_failed_replan_after_execution_is_terminal_and_semantically_audited(db_session):
    analyst = RecordingAnalyst()
    result, task, plan, approval, executor = _run_after_sixth_failure(
        db_session, analyst_service=analyst
    )

    assert result.state.value == "FAILED"
    assert result.decision.value == "FAIL"
    assert executor.calls == 6
    assert db_session.get(TaskRecord, task.id).status == TaskStatus.FAILED.value
    assert db_session.query(PlanRecord).filter_by(task_id=task.id).count() == 1
    assert db_session.query(ApprovalRecord).filter_by(task_id=task.id).count() == 1
    assert db_session.get(ApprovalRecord, approval.id).decision == "APPROVED"
    assert db_session.query(ToolExecutionRecord).filter_by(task_id=task.id).count() == 6
    failed = (
        db_session.query(ToolExecutionRecord)
        .filter_by(task_id=task.id, status="FAILED")
        .one()
    )
    assert db_session.query(EvidenceRecord).filter_by(task_id=task.id).count() == 6
    assert failed.artifact_path
    assert len(analyst.calls) == 1

    events = (
        db_session.query(AuditEventRecord)
        .filter_by(task_id=task.id)
        .order_by(AuditEventRecord.created_at.asc(), AuditEventRecord.id.asc())
        .all()
    )
    event_types = [event.event_type for event in events]
    assert "EXECUTION_INITIATION_STARTED" in event_types
    assert "EXECUTION_INITIATION_FAILED" not in event_types
    assert "REPLAN_FAILED" in event_types
    assert any(
        event.event_type == "TASK_STATE_CHANGED"
        and "RUNNING -> FAILED" in event.payload_summary
        for event in events
    )
    observation = next(
        json.loads(event.payload_summary)
        for event in events
        if event.event_type == "RUNTIME_OBSERVATION"
        and json.loads(event.payload_summary).get("decision") == "REPLAN"
    )
    assert observation["status"] == "FAILED"
    failure = next(event for event in events if event.event_type == "REPLAN_FAILED")
    assert json.loads(failure.payload_summary)["error_category"] == (
        "RUNTIME_VALIDATION_FAILED"
    )
    provenance = _command_provenance(
        db_session, db_session.get(TaskRecord, task.id)
    )
    assert provenance.execution_initiation == "STARTED"
    assert provenance.failure_category == "RUNTIME_VALIDATION_FAILED"
    serialized = " ".join(event.payload_summary for event in events)
    assert "Chain of Thought" not in serialized


def test_failed_replan_synthesizes_negative_evidence_without_fabricated_success(
    db_session,
):
    analyst = AnalystService(
        db_session,
        MockLLMProvider(),
        data_root=Path(artifact_root(db_session)),
    )

    result, task, _, _, _ = _run_after_sixth_failure(
        db_session, analyst_service=analyst
    )

    read_model = analyst.get_read_model(task.id)
    assert result.state.value == "FAILED"
    assert read_model.report is not None
    assert read_model.report.overall_status is OverallStatus.BLOCKED
    assert (
        read_model.report.release_recommendation
        is ReleaseRecommendation.NOT_READY
    )
    assert read_model.report.evidence_coverage.referenced_count >= 1
    assert read_model.artifact_path is not None
