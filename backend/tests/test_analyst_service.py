import json

from app.agents.providers.base import LLMResponse, ProviderError, ProviderErrorCategory
from app.agents.providers.mock import MockLLMProvider
from app.agents.planner.planner import PlannerAgent
from app.analyst.models import AnalystSynthesisStatus
from app.analyst.service import AnalystService
from app.storage.orm import AuditEventRecord, EvidenceRecord, TaskRecord, ToolExecutionRecord
from tests.project_test_support import create_project_task


def terminal_task_and_plan(session):
    task = create_project_task(
        session,
        title="Analyst service task",
        goal="Analyze persisted release evidence",
    )
    plan = PlannerAgent(session, MockLLMProvider()).create_plan(task.id)
    task_record = session.get(TaskRecord, task.id)
    task_record.status = "SUCCESS"
    session.add(
        EvidenceRecord(
            id="evidence-service-1",
            task_id=task.id,
            summary="The governed verification completed.",
            artifact_path="D:/AgentProjectData/AgentForge/artifacts/evidence.json",
            content_hash="b" * 64,
        )
    )
    session.add(
        ToolExecutionRecord(
            task_id=task.id,
            tool_name="git_read",
            action="status",
            status="SUCCESS",
            result_summary="Working tree is clean.",
        )
    )
    session.commit()
    return task, plan


class FailingProvider:
    provider_name = "failing"
    model_name = "failure-model"

    def generate_analyst(self, request):
        del request
        raise ProviderError(ProviderErrorCategory.TIMEOUT)


class MalformedProvider:
    provider_name = "malformed"
    model_name = "malformed-model"

    def generate_analyst(self, request):
        del request
        return LLMResponse(
            payload={"unexpected": "invalid"},
            provider=self.provider_name,
            model=self.model_name,
            duration_ms=0,
            attempt_count=1,
        )


class HallucinatingProvider:
    provider_name = "hallucinating"
    model_name = "unsafe-model"

    def generate_analyst(self, request):
        del request
        return LLMResponse(
            payload={
                "summary": "Unsupported claim.",
                "overall_status": "HEALTHY",
                "release_recommendation": "READY",
                "findings": [
                    {
                        "id": "finding-unsafe",
                        "title": "Unsupported",
                        "severity": "HIGH",
                        "category": "release",
                        "statement": "This is not grounded.",
                        "rationale": "The evidence id is fabricated.",
                        "evidence_refs": ["not-persisted"],
                        "recommended_action": "Ignore this claim.",
                    }
                ],
                "next_actions": [],
                "limitations": [],
                "evidence_coverage": {
                    "available_count": 1,
                    "referenced_count": 1,
                    "truncated": False,
                    "notes": [],
                },
            },
            provider=self.provider_name,
            model=self.model_name,
            duration_ms=0,
            attempt_count=1,
        )


def event_types(session, task_id):
    return [
        item.event_type
        for item in session.query(AuditEventRecord)
        .filter_by(task_id=task_id)
        .order_by(AuditEventRecord.created_at, AuditEventRecord.id)
        .all()
        if item.event_type.startswith("ANALYST_")
    ]


def test_successful_synthesis_persists_report_and_lifecycle_events(db_session):
    task, plan = terminal_task_and_plan(db_session)

    result = AnalystService(db_session, MockLLMProvider()).synthesize(
        task_id=task.id, plan_id=plan.id, plan_version=plan.version
    )

    assert result.status is AnalystSynthesisStatus.SUCCEEDED
    assert result.report is not None
    assert result.report.task_id == task.id
    assert result.report.plan_id == plan.id
    assert result.artifact_path is not None
    assert event_types(db_session, task.id) == [
        "ANALYST_SYNTHESIS_REQUESTED",
        "ANALYST_SYNTHESIS_STARTED",
        "ANALYST_SYNTHESIS_SUCCEEDED",
    ]
    audit_payloads = [
        json.loads(item.payload_summary)
        for item in db_session.query(AuditEventRecord)
        .filter_by(task_id=task.id)
        .all()
        if item.event_type.startswith("ANALYST_")
    ]
    serialized = json.dumps(audit_payloads)
    assert "reasoning" not in serialized.lower()
    assert "prompt" not in serialized.lower()


def test_provider_failure_preserves_execution_and_evidence_facts(db_session):
    task, plan = terminal_task_and_plan(db_session)
    before_execution = db_session.query(ToolExecutionRecord).filter_by(task_id=task.id).count()
    before_evidence = db_session.query(EvidenceRecord).filter_by(task_id=task.id).count()

    result = AnalystService(db_session, FailingProvider()).synthesize(
        task_id=task.id, plan_id=plan.id, plan_version=plan.version
    )

    assert result.status is AnalystSynthesisStatus.FAILED
    assert result.failure_category == "TIMEOUT"
    assert db_session.get(TaskRecord, task.id).status == "SUCCESS"
    assert db_session.query(ToolExecutionRecord).filter_by(task_id=task.id).count() == before_execution
    assert db_session.query(EvidenceRecord).filter_by(task_id=task.id).count() == before_evidence
    assert event_types(db_session, task.id)[-1] == "ANALYST_SYNTHESIS_FAILED"


def test_malformed_synthesis_is_failed_without_success_artifact(db_session):
    task, plan = terminal_task_and_plan(db_session)

    result = AnalystService(db_session, MalformedProvider()).synthesize(
        task_id=task.id, plan_id=plan.id, plan_version=plan.version
    )

    assert result.status is AnalystSynthesisStatus.FAILED
    assert result.failure_category == "MALFORMED_OUTPUT"
    assert result.report is None
    assert result.artifact_path is None


def test_hallucinated_evidence_reference_is_rejected(db_session):
    task, plan = terminal_task_and_plan(db_session)

    result = AnalystService(db_session, HallucinatingProvider()).synthesize(
        task_id=task.id, plan_id=plan.id, plan_version=plan.version
    )

    assert result.status is AnalystSynthesisStatus.FAILED
    assert result.failure_category == "INVALID_EVIDENCE_REFERENCE"
    assert result.report is None


def test_non_terminal_task_does_not_call_provider(db_session):
    task = create_project_task(
        db_session,
        title="Pending analyst task",
        goal="Do not synthesize before terminal execution",
    )
    plan = PlannerAgent(db_session, MockLLMProvider()).create_plan(task.id)
    result = AnalystService(db_session, FailingProvider()).synthesize(
        task_id=task.id, plan_id=plan.id, plan_version=plan.version
    )

    assert result.status is AnalystSynthesisStatus.FAILED
    assert result.failure_category == "TASK_NOT_TERMINAL"
    assert event_types(db_session, task.id) == []
