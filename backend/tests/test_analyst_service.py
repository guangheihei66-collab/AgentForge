import json

from app.agents.providers.base import LLMResponse, ProviderError, ProviderErrorCategory
from app.agents.providers.mock import MockLLMProvider
from app.agents.planner.planner import PlannerAgent
from app.analyst.models import AnalystSynthesisStatus
from app.analyst.package import build_evidence_package
from app.analyst.prompts import build_analyst_prompt
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


def terminal_release_task_and_plan(session, *, failed_capability: str | None = None):
    task = create_project_task(
        session,
        title="Release readiness evidence task",
        goal="全面分析项目是否适合发布，找出主要风险并给出证据。",
    )
    plan = PlannerAgent(session, MockLLMProvider()).create_plan(
        task.id, context={"analysis_profile": "release_readiness"}
    )
    task_record = session.get(TaskRecord, task.id)
    task_record.status = "FAILED" if failed_capability else "SUCCESS"
    for index, snapshot in enumerate(plan.plan_json["resolved_steps"]):
        capability = snapshot["capability_id"]
        evidence_id = f"release-evidence-{index}"
        status = "FAILED" if capability == failed_capability else "SUCCESS"
        session.add(
            EvidenceRecord(
                id=evidence_id,
                task_id=task.id,
                summary=f"Persisted {capability} verification evidence.",
                artifact_path=(
                    f"D:/AgentProjectData/AgentForge/artifacts/{evidence_id}.json"
                ),
                content_hash=(str(index + 1) * 64)[:64],
            )
        )
        session.add(
            ToolExecutionRecord(
                task_id=task.id,
                tool_name=snapshot["resolved_tool_id"],
                action=snapshot["resolved_action"],
                status=status,
                result_summary=(
                    f"{capability} verification {status.lower()}."
                ),
            )
        )
        session.add(
            AuditEventRecord(
                task_id=task.id,
                event_type="RUNTIME_OBSERVATION",
                actor="agent_runtime",
                payload_summary=json.dumps(
                    {
                        "observation_id": f"observation-{index}",
                        "step_id": snapshot["step_id"],
                        "capability_id": capability,
                        "tool_id": snapshot["resolved_tool_id"],
                        "status": status,
                        "result_summary": f"{capability} verification {status.lower()}.",
                        "evidence_refs": [evidence_id],
                        "decision": "FAIL" if status == "FAILED" else "CONTINUE",
                    },
                    ensure_ascii=False,
                ),
                correlation_id=f"correlation-{index}",
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


def test_release_readiness_rejects_ready_from_only_repository_status(db_session):
    """Canonical blocker: clean git status is not full release evidence."""

    task, plan = terminal_task_and_plan(db_session)
    plan.plan_json = {**plan.plan_json, "analysis_profile": "release_readiness"}
    db_session.add(plan)
    db_session.commit()

    result = AnalystService(db_session, MockLLMProvider()).synthesize(
        task_id=task.id, plan_id=plan.id, plan_version=plan.version
    )

    assert result.status is AnalystSynthesisStatus.SUCCEEDED
    assert result.report is not None
    assert result.report.release_recommendation.value == "INSUFFICIENT_EVIDENCE"
    assert result.report.overall_status.value != "HEALTHY"
    assert any(
        "project_metadata" in limitation or "test_verification" in limitation
        for limitation in result.report.limitations
    )


def test_sufficient_release_evidence_can_preserve_ready_recommendation(db_session):
    task, plan = terminal_release_task_and_plan(db_session)

    result = AnalystService(db_session, MockLLMProvider()).synthesize(
        task_id=task.id, plan_id=plan.id, plan_version=plan.version
    )

    assert result.status is AnalystSynthesisStatus.SUCCEEDED
    assert result.report is not None
    assert result.report.release_recommendation.value == "READY"
    assert result.report.overall_status.value == "HEALTHY"
    assert result.report.evidence_coverage.sufficiency.value == "SUFFICIENT"
    assert result.report.evidence_coverage.available_count == 3


def test_failed_release_verification_cannot_produce_ready(db_session):
    task, plan = terminal_release_task_and_plan(
        db_session, failed_capability="test_verification"
    )

    result = AnalystService(db_session, MockLLMProvider()).synthesize(
        task_id=task.id, plan_id=plan.id, plan_version=plan.version
    )

    assert result.status is AnalystSynthesisStatus.SUCCEEDED
    assert result.report is not None
    assert result.report.release_recommendation.value == "NOT_READY"
    assert result.report.overall_status.value == "BLOCKED"
    assert result.report.evidence_coverage.sufficiency.value != "SUFFICIENT"
    assert any("test_verification" in limitation for limitation in result.report.limitations)


class CapturingAnalystProvider(MockLLMProvider):
    def __init__(self):
        self.request = None

    def generate_analyst(self, request):
        self.request = request
        return super().generate_analyst(request)


def test_analyst_prompt_requests_selected_language_and_persists_it(db_session):
    task, plan = terminal_task_and_plan(db_session)
    provider = CapturingAnalystProvider()
    package = build_evidence_package(
        db_session, task_id=task.id, plan_id=plan.id, plan_version=plan.version
    )

    assert "evidence-data" in build_analyst_prompt(package, language="en-US")
    assert "en-US" in build_analyst_prompt(package, language="en-US")
    result = AnalystService(db_session, provider).synthesize(
        task_id=task.id,
        plan_id=plan.id,
        plan_version=plan.version,
        language="zh-CN",
    )

    assert result.status is AnalystSynthesisStatus.SUCCEEDED
    assert provider.request is not None
    assert "zh-CN" in provider.request.system_instruction
    assert result.report is not None
    assert result.report.language == "zh-CN"
