from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
import json

import pytest
from pydantic import ValidationError

from app.agent_runtime.observer import ObservationReason, RuntimeObserver
from app.agent_runtime.state import RuntimeDecision
from app.agent_runtime.runtime import AgentRuntime
from app.agent_runtime.state import RuntimeState
from app.capabilities.models import CapabilityRequest, ResolvedExecutionSnapshot
from app.capabilities.registry import build_default_capability_registry
from app.capabilities.resolver import CapabilityResolver
from app.contracts.permissions import PermissionLevel
from app.domain.states.task_state import TaskStatus
from app.agents.replanning.models import (
    EvidenceSummary,
    ReplanContext,
    ReplanPolicyInput,
    ReplanProposal,
    StepSummary,
)
from app.agents.replanning.prompts import build_replan_prompt
from app.agents.replanning.policy import (
    ReplanPolicy,
    canonical_plan_fingerprint,
    progress_fingerprint,
)
from app.tools.defaults import build_default_registry
from app.tools.gateway import ToolExecutionResult
from app.tools.models import ToolDefinition
from app.tools.registry import ToolRegistry
from app.workspace.validator import WorkspaceValidator
from tests.project_test_support import (create_project_task, project_workspace,
                                        with_project_authority)
from app.agents.providers import (
    LLMRequest,
    LLMResponse,
    MockLLMProvider,
    ProviderError,
    ProviderErrorCategory,
)
from app.agents.replanning.service import ReplanningService, ReplanOutcomeStatus
from app.approvals.service import ApprovalError, ApprovalService
from app.services.task_service import TaskService
from app.storage.orm import ApprovalRecord, AuditEventRecord, PlanRecord, TaskRecord


REPO_ROOT = r"D:\AgentProjects\AgentForge"


def snapshot(capability_id: str) -> ResolvedExecutionSnapshot:
    if capability_id == "test_verification":
        tool_id, action, parameters = "test_run", "run_profile", (("profile", "smoke"),)
    else:
        tool_id, action, parameters = "git_read", "status", ()
    return ResolvedExecutionSnapshot(
        task_id="task-phase13",
        plan_id="plan-v1",
        plan_version=1,
        step_id=f"step-{capability_id}",
        capability_id=capability_id,
        resolved_tool_id=tool_id,
        resolved_action=action,
        normalized_parameters=parameters,
        registry_fingerprint="a" * 64,
    )


def tool_result(
    *, status: str, summary: str, evidence_id: str | None = None
) -> ToolExecutionResult:
    return ToolExecutionResult(
        execution_id="execution-phase13",
        status=status,
        summary=summary,
        evidence_id=evidence_id,
    )


def test_runtime_decision_vocabulary_is_exact():
    assert {item.value for item in RuntimeDecision} == {
        "CONTINUE",
        "COMPLETE",
        "FAIL",
        "REPLAN",
    }


def test_failed_test_with_evidence_is_replan_candidate():
    observation = RuntimeObserver().observe(
        snapshot=snapshot("test_verification"),
        result=tool_result(
            status="FAILED",
            summary="unit profile failed",
            evidence_id="evidence-test-failure",
        ),
        remaining_steps=0,
    )

    assert observation.reason_code == ObservationReason.TEST_FAILED_DIAGNOSTIC_AVAILABLE
    assert observation.replan_recommended is True
    assert observation.decision == RuntimeDecision.REPLAN
    assert observation.evidence_refs == ("evidence-test-failure",)
    assert observation.execution_metadata["normalized_parameters"] == {
        "profile": "smoke"
    }
    assert len(observation.result_summary) <= 2_000
    assert isinstance(observation.created_at, datetime)
    with pytest.raises(FrozenInstanceError):
        observation.status = "SUCCESS"


def test_failure_without_diagnostic_evidence_is_fail():
    observation = RuntimeObserver().observe(
        snapshot=snapshot("test_verification"),
        result=tool_result(status="FAILED", summary="failed"),
        remaining_steps=0,
    )

    assert observation.decision == RuntimeDecision.FAIL
    assert observation.reason_code == ObservationReason.NON_REPLANNABLE_TOOL_FAILURE
    assert observation.replan_recommended is False


def test_success_semantics_remain_continue_then_complete():
    result = tool_result(status="SUCCESS", summary="clean")
    continuing = RuntimeObserver().observe(
        snapshot=snapshot("repository_state"), result=result, remaining_steps=1
    )
    complete = RuntimeObserver().observe(
        snapshot=snapshot("repository_state"), result=result, remaining_steps=0
    )

    assert continuing.decision == RuntimeDecision.CONTINUE
    assert complete.decision == RuntimeDecision.COMPLETE


def resolver() -> CapabilityResolver:
    validator = WorkspaceValidator(REPO_ROOT)
    return CapabilityResolver(
        build_default_capability_registry(), build_default_registry(validator)
    )


def replan_observation():
    return RuntimeObserver().observe(
        snapshot=snapshot("test_verification"),
        result=tool_result(
            status="FAILED", summary="unit profile failed", evidence_id="evidence-1"
        ),
        remaining_steps=0,
    )


def policy_input() -> ReplanPolicyInput:
    return ReplanPolicyInput(
        task_status=TaskStatus.RUNNING,
        observation=replan_observation(),
        current_plan_id="plan-v1",
        current_plan_version=1,
        replan_count=1,
        total_steps=2,
        current_plan_fingerprint="1" * 64,
        previous_plan_fingerprints=(),
        current_progress_fingerprint="2" * 64,
        previous_progress_fingerprint=None,
        repeated_failure_count=1,
    )


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"task_status": TaskStatus.CANCELLED}, ObservationReason.POLICY_DENIED),
        ({"replan_count": 2}, ObservationReason.BUDGET_EXHAUSTED),
        ({"total_steps": 12}, ObservationReason.BUDGET_EXHAUSTED),
        ({"repeated_failure_count": 2}, ObservationReason.POLICY_DENIED),
    ],
)
def test_replan_policy_fails_closed(overrides, reason):
    decision = ReplanPolicy().evaluate(replace(policy_input(), **overrides))

    assert decision.decision == RuntimeDecision.FAIL
    assert decision.reason_code == reason


def test_replan_policy_authorizes_only_bounded_diagnostic_case():
    decision = ReplanPolicy().evaluate(policy_input())

    assert decision.decision == RuntimeDecision.REPLAN
    assert decision.remaining_replans == 1
    assert decision.remaining_steps == 10


def test_canonical_plan_fingerprint_uses_normalized_capability_requests():
    first = [
        CapabilityRequest("repository_state", {}),
        CapabilityRequest("test_verification", {"profile": "smoke"}),
    ]
    equivalent = [
        CapabilityRequest("repository_state", {}),
        CapabilityRequest("test_verification", dict(profile="smoke")),
    ]
    changed = list(reversed(first))

    fingerprint = canonical_plan_fingerprint(first, resolver())

    assert fingerprint == canonical_plan_fingerprint(equivalent, resolver())
    assert fingerprint != canonical_plan_fingerprint(changed, resolver())
    assert len(fingerprint) == 64
    assert set(fingerprint) <= set("0123456789abcdef")


def test_progress_fingerprint_changes_with_evidence():
    completed = (
        StepSummary(
            capability_id="test_verification",
            parameters={"profile": "smoke"},
            status="FAILED",
            reason_code="TEST_FAILED_DIAGNOSTIC_AVAILABLE",
            summary="tests failed",
            evidence_refs=("evidence-1",),
        ),
    )
    first = progress_fingerprint(
        completed,
        ObservationReason.TEST_FAILED_DIAGNOSTIC_AVAILABLE,
        ("evidence-1",),
        "1" * 64,
    )
    second = progress_fingerprint(
        completed,
        ObservationReason.TEST_FAILED_DIAGNOSTIC_AVAILABLE,
        ("evidence-2",),
        "1" * 64,
    )

    assert first != second


def test_replan_policy_rejects_unchanged_progress():
    value = policy_input()
    decision = ReplanPolicy().evaluate(
        replace(value, previous_progress_fingerprint=value.current_progress_fingerprint)
    )

    assert decision.decision == RuntimeDecision.FAIL
    assert decision.reason_code == ObservationReason.POLICY_DENIED


def valid_replan_payload():
    return {
        "decision_summary": "Inspect bounded project metadata.",
        "revised_remaining_steps": [
            {
                "step_id": "replan-1-step-1",
                "capability_id": "project_metadata",
                "parameters": {"relative_path": "PROJECT_CONTEXT.md"},
            }
        ],
    }


def replan_context(summary: str = "tests failed") -> ReplanContext:
    failed = StepSummary(
        capability_id="test_verification",
        parameters={"profile": "smoke"},
        status="FAILED",
        reason_code="TEST_FAILED_DIAGNOSTIC_AVAILABLE",
        summary=summary,
        evidence_refs=("evidence-1",),
    )
    return ReplanContext.bounded(
        user_goal="Check whether version 2.0 is ready for release.",
        original_plan_id="plan-v1",
        current_plan_id="plan-v1",
        current_plan_version=1,
        remaining_plan_summary=(),
        completed_step_summaries=(failed,),
        latest_observation=replan_observation(),
        evidence_summaries=(EvidenceSummary("evidence-1", summary, "b" * 64),),
        remaining_step_budget=10,
        remaining_replan_budget=1,
    )


def test_replan_proposal_accepts_only_capability_first_steps():
    proposal = ReplanProposal.model_validate(valid_replan_payload())

    assert proposal.revised_remaining_steps[0].capability_id == "project_metadata"


@pytest.mark.parametrize(
    "forbidden",
    ["tool_id", "tool", "action", "command", "permission", "approval", "workspace"],
)
def test_replan_proposal_rejects_model_controlled_authority(forbidden):
    payload = valid_replan_payload()
    payload["revised_remaining_steps"][0][forbidden] = "forbidden"

    with pytest.raises(ValidationError):
        ReplanProposal.model_validate(payload)


def test_replan_context_truncates_counts_and_summaries():
    item = StepSummary("repository_state", {}, "SUCCESS", "STEP_SUCCEEDED", "x" * 900)
    evidence = EvidenceSummary("e", "y" * 900, None)
    context = ReplanContext.bounded(
        user_goal="goal",
        original_plan_id="p1",
        current_plan_id="p1",
        current_plan_version=1,
        remaining_plan_summary=tuple(item for _ in range(20)),
        completed_step_summaries=tuple(item for _ in range(20)),
        latest_observation=replan_observation(),
        evidence_summaries=tuple(evidence for _ in range(10)),
        remaining_step_budget=10,
        remaining_replan_budget=1,
    )

    assert len(context.completed_step_summaries) == 12
    assert len(context.evidence_summaries) == 5
    assert len(context.completed_step_summaries[0].summary) == 500
    assert len(context.evidence_summaries[0].summary) == 500


def test_replan_prompt_is_bounded_and_excludes_concrete_tools():
    prompt = build_replan_prompt(replan_context(), build_default_capability_registry())

    assert len(prompt.encode("utf-8")) <= 12 * 1024
    assert "project_metadata" in prompt
    assert "file_read" not in prompt
    assert "ToolGateway" not in prompt
    assert "Authorization" not in prompt


def test_replan_context_over_8_kib_fails_before_prompt():
    large_step = StepSummary(
        "test_verification",
        {"profile": "smoke"},
        "FAILED",
        "TEST_FAILED_DIAGNOSTIC_AVAILABLE",
        "界" * 500,
        ("evidence-1",),
    )
    large_evidence = EvidenceSummary("evidence-1", "界" * 500, "b" * 64)
    context = ReplanContext.bounded(
        user_goal="goal",
        original_plan_id="p1",
        current_plan_id="p1",
        current_plan_version=1,
        remaining_plan_summary=(),
        completed_step_summaries=tuple(large_step for _ in range(12)),
        latest_observation=replan_observation(),
        evidence_summaries=tuple(large_evidence for _ in range(5)),
        remaining_step_budget=10,
        remaining_replan_budget=1,
    )

    with pytest.raises(ValueError, match="context exceeds"):
        build_replan_prompt(context, build_default_capability_registry())


def test_mock_replanner_is_deterministic_and_capability_only():
    request = LLMRequest(
        prompt="bounded",
        context={},
        output_schema=ReplanProposal.model_json_schema(),
    )

    first = MockLLMProvider().generate_replan(request)
    second = MockLLMProvider().generate_replan(request)

    assert first.payload == second.payload == valid_replan_payload()
    assert "tool" not in json.dumps(first.payload).lower()


def create_approved_v1(session):
    task = create_project_task(session,
        title="Phase 13 release verification",
        goal="Check whether version 2.0 is ready for release.",
    )
    TaskService(session).transition_task(task.id, TaskStatus.PLANNING)
    steps = [
        {"step_id": "step-1", "capability_id": "repository_state", "parameters": {}},
        {
            "step_id": "step-2",
            "capability_id": "test_verification",
            "parameters": {"profile": "smoke"},
        },
    ]
    plan = PlanRecord(
        task_id=task.id,
        version=1,
        plan_json=with_project_authority(session, task, {"schema_version": 2, "summary": "verify", "steps": steps, "resolved_steps": []}),
        validation_status="VALID",
        created_at=datetime.now(timezone.utc),
    )
    session.add(plan)
    session.flush()
    resolved = []
    active_resolver = resolver()
    for step in steps:
        resolved.append(
            active_resolver.resolve(
                task_id=task.id,
                plan_id=plan.id,
                plan_version=1,
                step_id=step["step_id"],
                request=CapabilityRequest(step["capability_id"], step["parameters"]),
            ).to_dict()
        )
    plan.plan_json = {**plan.plan_json, "resolved_steps": resolved}
    session.commit()
    approval = ApprovalService(session).create_request(
        task_id=task.id, plan_id=plan.id, plan_version=1, requested_by="phase13-test"
    )
    ApprovalService(session).approve(approval.id, actor="reviewer")
    return task, plan, approval


def failed_step_summary():
    return StepSummary(
        capability_id="test_verification",
        parameters={"profile": "smoke"},
        status="FAILED",
        reason_code="TEST_FAILED_DIAGNOSTIC_AVAILABLE",
        summary="unit profile failed",
        evidence_refs=("evidence-test-failure",),
    )


def test_replanning_service_creates_immutable_v2_with_fresh_approval(db_session):
    task, plan_v1, approval_v1 = create_approved_v1(db_session)
    original_v1 = json.loads(json.dumps(plan_v1.plan_json))
    observation = replan_observation()
    service = ReplanningService(db_session, MockLLMProvider())

    outcome = service.create_successor(
        task_id=task.id,
        current_plan_id=plan_v1.id,
        current_plan_version=1,
        observation=observation,
        completed_steps=(failed_step_summary(),),
        attempted_steps=2,
    )

    plan_v2 = db_session.get(PlanRecord, outcome.plan_id)
    approval_v2 = db_session.get(ApprovalRecord, outcome.approval_id)
    assert outcome.status == ReplanOutcomeStatus.WAITING_APPROVAL
    assert plan_v2.version == 2
    assert db_session.get(PlanRecord, plan_v1.id).plan_json == original_v1
    lineage = plan_v2.plan_json["replan_lineage"]
    assert lineage["original_plan_id"] == plan_v1.id
    assert lineage["previous_plan_id"] == plan_v1.id
    assert lineage["previous_plan_version"] == 1
    assert lineage["triggering_observation_id"] == observation.observation_id
    assert lineage["reason_code"] == "TEST_FAILED_DIAGNOSTIC_AVAILABLE"
    assert lineage["created_at"]
    assert approval_v1.decision == "APPROVED"
    assert approval_v2.decision == "PENDING"
    assert approval_v2.plan_id == plan_v2.id
    assert approval_v2.resolved_snapshot["steps"][0]["plan_version"] == 2
    assert db_session.get(TaskRecord, task.id).status == TaskStatus.WAITING_APPROVAL.value
    v2_snapshot = ResolvedExecutionSnapshot.from_dict(
        plan_v2.plan_json["resolved_steps"][0]
    )
    with pytest.raises(ApprovalError):
        ApprovalService(db_session).assert_snapshot_allowed(v2_snapshot)


def test_replanning_service_rejects_stale_plan_version(db_session):
    task, plan_v1, _ = create_approved_v1(db_session)
    service = ReplanningService(db_session, MockLLMProvider())

    with pytest.raises(ValueError, match="stale"):
        service.create_successor(
            task_id=task.id,
            current_plan_id=plan_v1.id,
            current_plan_version=0,
            observation=replan_observation(),
            completed_steps=(failed_step_summary(),),
            attempted_steps=2,
        )

    assert db_session.query(PlanRecord).filter_by(task_id=task.id).count() == 1


class DeterministicReplanExecutor:
    def __init__(self):
        self.capabilities = []

    def execute(self, **values):
        capability = values["snapshot"].capability_id
        self.capabilities.append(capability)
        if capability == "test_verification":
            return tool_result(
                status="FAILED",
                summary="unit profile failed",
                evidence_id="evidence-test-failure",
            )
        if capability == "project_metadata":
            return ToolExecutionResult(
                execution_id="execution-metadata",
                status="SUCCESS",
                summary="version configuration does not match release 2.0",
                evidence_id="evidence-version-config",
            )
        return ToolExecutionResult(
            execution_id="execution-repository",
            status="SUCCESS",
            summary="repository state captured",
            evidence_id="evidence-repository",
        )


def test_runtime_pauses_v1_on_replan_and_requires_v2_approval(db_session):
    task, plan_v1, _ = create_approved_v1(db_session)
    service = ReplanningService(db_session, MockLLMProvider())
    executor = DeterministicReplanExecutor()
    runtime = AgentRuntime(
        db_session,
        executor,
        resolver=resolver(),
        replanning_service=service,
    )

    result = runtime.run(task_id=task.id, plan_id=plan_v1.id, plan_version=1)

    assert result.decision == RuntimeDecision.REPLAN
    assert result.state == RuntimeState.OBSERVING
    assert result.successor_plan_version == 2
    assert result.approval_id
    assert executor.capabilities == ["repository_state", "test_verification"]
    assert db_session.get(TaskRecord, task.id).status == TaskStatus.WAITING_APPROVAL.value
    assert service.authoritative_plan(task.id).plan_id == result.successor_plan_id
    assert service.authoritative_plan(task.id).executable is False


def test_approved_v2_resumes_through_snapshot_and_finishes_not_ready(db_session):
    task, plan_v1, _ = create_approved_v1(db_session)
    service = ReplanningService(db_session, MockLLMProvider())
    executor = DeterministicReplanExecutor()
    runtime = AgentRuntime(
        db_session,
        executor,
        resolver=resolver(),
        replanning_service=service,
    )
    paused = runtime.run(task_id=task.id, plan_id=plan_v1.id, plan_version=1)
    ApprovalService(db_session).approve(paused.approval_id, actor="reviewer-v2")

    result = runtime.run(
        task_id=task.id,
        plan_id=paused.successor_plan_id,
        plan_version=paused.successor_plan_version,
    )

    assert service.authoritative_plan(task.id).executable is False
    assert result.decision == RuntimeDecision.FAIL
    assert result.state == RuntimeState.FAILED
    assert result.observations[-1].evidence_refs == ("evidence-version-config",)
    assert db_session.get(TaskRecord, task.id).status == TaskStatus.FAILED.value
    assert executor.capabilities[-1] == "project_metadata"


def test_release_verification_replan_audit_is_reconstructable_and_bounded(db_session):
    task, plan_v1, _ = create_approved_v1(db_session)
    service = ReplanningService(db_session, MockLLMProvider())
    executor = DeterministicReplanExecutor()
    runtime = AgentRuntime(
        db_session, executor, resolver=resolver(), replanning_service=service
    )
    paused = runtime.run(task_id=task.id, plan_id=plan_v1.id, plan_version=1)
    ApprovalService(db_session).approve(paused.approval_id, actor="reviewer-v2")
    finished = runtime.run(
        task_id=task.id,
        plan_id=paused.successor_plan_id,
        plan_version=paused.successor_plan_version,
    )

    events = (
        db_session.query(AuditEventRecord)
        .filter_by(task_id=task.id)
        .order_by(AuditEventRecord.created_at.asc(), AuditEventRecord.id.asc())
        .all()
    )
    event_types = [event.event_type for event in events]
    for required in (
        "RUNTIME_EXECUTION",
        "RUNTIME_OBSERVATION",
        "RUNTIME_DECISION",
        "REPLAN_REQUESTED",
        "REPLAN_PROPOSED",
        "PLAN_VERSION_CREATED",
        "REPLAN_APPROVAL_REQUIRED",
        "EXECUTION_SNAPSHOT_APPROVED",
        "REPLAN_RESUMED",
    ):
        assert required in event_types
    observations = [
        json.loads(event.payload_summary)
        for event in events
        if event.event_type == "RUNTIME_OBSERVATION"
    ]
    assert any(item["reason_code"] == "TEST_FAILED_DIAGNOSTIC_AVAILABLE" for item in observations)
    assert any(item["evidence_refs"] == ["evidence-version-config"] for item in observations)
    assert finished.decision == RuntimeDecision.FAIL
    serialized = json.dumps([event.payload_summary for event in events])
    for forbidden in (
        "PHASE13_TEST_SECRET_DO_NOT_LEAK",
        "Authorization",
        "Chain of Thought",
        "full prompt",
    ):
        assert forbidden not in serialized
    for event in events:
        if event.event_type.startswith("REPLAN") or event.event_type == "PLAN_VERSION_CREATED":
            assert len(event.payload_summary.encode("utf-8")) <= 8 * 1024


def test_authoritative_plan_rejects_tampered_v2_snapshot(db_session):
    task, plan_v1, _ = create_approved_v1(db_session)
    service = ReplanningService(db_session, MockLLMProvider())
    outcome = service.create_successor(
        task_id=task.id,
        current_plan_id=plan_v1.id,
        current_plan_version=1,
        observation=replan_observation(),
        completed_steps=(failed_step_summary(),),
        attempted_steps=2,
    )
    ApprovalService(db_session).approve(outcome.approval_id, actor="reviewer-v2")
    plan_v2 = db_session.get(PlanRecord, outcome.plan_id)
    payload = dict(plan_v2.plan_json)
    resolved = [dict(payload["resolved_steps"][0])]
    resolved[0]["registry_fingerprint"] = "0" * 64
    plan_v2.plan_json = {**payload, "resolved_steps": resolved}
    db_session.commit()

    with pytest.raises((ApprovalError, ValueError)):
        service.authoritative_plan(task.id)


def test_authoritative_plan_never_resumes_v1_after_incomplete_replan_request(db_session):
    task, plan_v1, _ = create_approved_v1(db_session)
    db_session.add(
        AuditEventRecord(
            task_id=task.id,
            event_type="REPLAN_REQUESTED",
            actor="replanning_service",
            payload_summary=json.dumps({"plan_id": plan_v1.id, "plan_version": 1}),
            correlation_id="phase13-incomplete-replan",
        )
    )
    db_session.commit()

    with pytest.raises(ValueError, match="incomplete"):
        ReplanningService(
            db_session, MockLLMProvider()
        ).authoritative_plan(task.id)


class FailingReplanProvider(MockLLMProvider):
    category = ProviderErrorCategory.TIMEOUT

    def generate_replan(self, request):
        del request
        raise ProviderError(self.category)


def test_provider_failure_fails_task_and_records_safe_rejection(db_session):
    task, plan_v1, _ = create_approved_v1(db_session)
    service = ReplanningService(db_session, FailingReplanProvider())

    outcome = service.create_successor(
        task_id=task.id,
        current_plan_id=plan_v1.id,
        current_plan_version=1,
        observation=replan_observation(),
        completed_steps=(failed_step_summary(),),
        attempted_steps=2,
    )

    assert outcome.status == ReplanOutcomeStatus.FAILED
    assert db_session.get(TaskRecord, task.id).status == TaskStatus.FAILED.value
    rejection = (
        db_session.query(AuditEventRecord)
        .filter_by(task_id=task.id, event_type="REPLAN_REJECTED")
        .one()
    )
    assert "TIMEOUT" in rejection.payload_summary
    events = {
        event.event_type
        for event in db_session.query(AuditEventRecord).filter_by(task_id=task.id)
    }
    assert {"REPLAN_REQUESTED", "REPLAN_REJECTED"} <= events
    assert db_session.query(PlanRecord).filter_by(task_id=task.id).count() == 1


def test_provider_authentication_failure_fails_closed(db_session):
    class AuthenticationFailureProvider(FailingReplanProvider):
        category = ProviderErrorCategory.AUTHENTICATION_FAILED

    task, plan_v1, _ = create_approved_v1(db_session)
    outcome = ReplanningService(
        db_session, AuthenticationFailureProvider()
    ).create_successor(
        task_id=task.id,
        current_plan_id=plan_v1.id,
        current_plan_version=1,
        observation=replan_observation(),
        completed_steps=(failed_step_summary(),),
        attempted_steps=2,
    )

    assert outcome.status == ReplanOutcomeStatus.FAILED
    assert outcome.reason_code == ProviderErrorCategory.AUTHENTICATION_FAILED.value
    assert db_session.get(TaskRecord, task.id).status == TaskStatus.FAILED.value


class CancellingReplanProvider(MockLLMProvider):
    def __init__(self, session, task_id):
        self.session = session
        self.task_id = task_id

    def generate_replan(self, request):
        del request
        ApprovalService(self.session).cancel_task(
            self.task_id, actor="operator", reason="cancel during replan"
        )
        return LLMResponse(
            payload=valid_replan_payload(),
            provider="mock",
            model="deterministic-mock",
            duration_ms=0,
            attempt_count=1,
        )


def test_cancellation_after_provider_response_prevents_v2_persistence(db_session):
    task, plan_v1, _ = create_approved_v1(db_session)
    provider = CancellingReplanProvider(db_session, task.id)
    service = ReplanningService(db_session, provider)

    outcome = service.create_successor(
        task_id=task.id,
        current_plan_id=plan_v1.id,
        current_plan_version=1,
        observation=replan_observation(),
        completed_steps=(failed_step_summary(),),
        attempted_steps=2,
    )

    assert outcome.status == ReplanOutcomeStatus.FAILED
    assert db_session.get(TaskRecord, task.id).status == TaskStatus.CANCELLED.value
    assert db_session.query(PlanRecord).filter_by(task_id=task.id).count() == 1


class PayloadReplanProvider(MockLLMProvider):
    def __init__(self, payload):
        self.payload = payload

    def generate_replan(self, request):
        del request
        return LLMResponse(
            payload=self.payload,
            provider="mock",
            model="deterministic-mock",
            duration_ms=0,
            attempt_count=1,
        )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {
            "decision_summary": "forbidden",
            "revised_remaining_steps": [
                {
                    "step_id": "bad",
                    "capability_id": "project_metadata",
                    "parameters": {"relative_path": "PROJECT_CONTEXT.md"},
                    "command": "shell",
                }
            ],
        },
        {
            "decision_summary": "unknown",
            "revised_remaining_steps": [
                {"step_id": "bad", "capability_id": "unknown", "parameters": {}}
            ],
        },
    ],
)
def test_invalid_replan_proposal_fails_closed(payload, db_session):
    task, plan_v1, _ = create_approved_v1(db_session)
    service = ReplanningService(
        db_session, PayloadReplanProvider(payload)
    )

    outcome = service.create_successor(
        task_id=task.id,
        current_plan_id=plan_v1.id,
        current_plan_version=1,
        observation=replan_observation(),
        completed_steps=(failed_step_summary(),),
        attempted_steps=2,
    )

    assert outcome.status == ReplanOutcomeStatus.FAILED
    assert db_session.get(TaskRecord, task.id).status == TaskStatus.FAILED.value
    assert db_session.query(PlanRecord).filter_by(task_id=task.id).count() == 1


def test_duplicate_replan_proposal_fails_closed(db_session):
    task, plan_v1, _ = create_approved_v1(db_session)
    duplicate = {
        "decision_summary": "repeat current plan",
        "revised_remaining_steps": plan_v1.plan_json["steps"],
    }
    service = ReplanningService(
        db_session, PayloadReplanProvider(duplicate)
    )

    outcome = service.create_successor(
        task_id=task.id,
        current_plan_id=plan_v1.id,
        current_plan_version=1,
        observation=replan_observation(),
        completed_steps=(failed_step_summary(),),
        attempted_steps=2,
    )

    assert outcome.status == ReplanOutcomeStatus.FAILED
    assert outcome.reason_code == "INVALID_RESPONSE"
    assert db_session.query(PlanRecord).filter_by(task_id=task.id).count() == 1


def test_zero_resolver_candidate_rolls_back_successor(db_session):
    task, plan_v1, _ = create_approved_v1(db_session)
    service = ReplanningService(db_session, MockLLMProvider())
    capabilities = build_default_capability_registry()
    capabilities._capabilities["project_metadata"] = replace(
        capabilities.require("project_metadata"), candidate_tool_ids=("missing",)
    )
    service.capability_registry = capabilities

    outcome = service.create_successor(
        task_id=task.id,
        current_plan_id=plan_v1.id,
        current_plan_version=1,
        observation=replan_observation(),
        completed_steps=(failed_step_summary(),),
        attempted_steps=2,
    )

    assert outcome.status == ReplanOutcomeStatus.FAILED
    assert db_session.query(PlanRecord).filter_by(task_id=task.id).count() == 1
    assert db_session.get(TaskRecord, task.id).status == TaskStatus.FAILED.value


def test_multiple_resolver_candidates_fail_closed(db_session):
    class NoopExecutor:
        def execute(self, action, parameters, workspace):
            del action, parameters, workspace
            return {"status": "SUCCESS"}

    capabilities = build_default_capability_registry()
    project_metadata = capabilities.require("project_metadata")
    capabilities._capabilities["project_metadata"] = replace(
        project_metadata, candidate_tool_ids=("file_a", "file_b")
    )
    tools = ToolRegistry()
    for name in ("file_a", "file_b"):
        tools.register(
            ToolDefinition(
                name=name,
                description="test tool",
                risk_level="medium",
                permission_level=PermissionLevel.SAFE_READ,
                allowed_actions=("read_metadata",),
                executor=NoopExecutor(),
            )
        )

    task, plan_v1, _ = create_approved_v1(db_session)
    service = ReplanningService(db_session, MockLLMProvider())
    service.capability_registry = capabilities
    service.resolver = CapabilityResolver(capabilities, tools)
    outcome = service.create_successor(
        task_id=task.id,
        current_plan_id=plan_v1.id,
        current_plan_version=1,
        observation=replan_observation(),
        completed_steps=(failed_step_summary(),),
        attempted_steps=2,
    )

    assert outcome.status == ReplanOutcomeStatus.FAILED
    assert db_session.query(PlanRecord).filter_by(task_id=task.id).count() == 1
    assert db_session.get(TaskRecord, task.id).status == TaskStatus.FAILED.value


def test_service_policy_budget_denial_fails_closed(db_session):
    task, plan_v1, _ = create_approved_v1(db_session)
    outcome = ReplanningService(
        db_session, MockLLMProvider()
    ).create_successor(
        task_id=task.id,
        current_plan_id=plan_v1.id,
        current_plan_version=1,
        observation=replan_observation(),
        completed_steps=(failed_step_summary(),),
        attempted_steps=12,
    )

    assert outcome.status == ReplanOutcomeStatus.FAILED
    assert outcome.reason_code == ObservationReason.BUDGET_EXHAUSTED.value
    assert db_session.get(TaskRecord, task.id).status == TaskStatus.FAILED.value
