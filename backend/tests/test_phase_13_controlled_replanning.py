from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
import json

import pytest
from pydantic import ValidationError

from app.agent_runtime.observer import ObservationReason, RuntimeObserver
from app.agent_runtime.state import RuntimeDecision
from app.capabilities.models import ResolvedExecutionSnapshot
from app.capabilities.models import CapabilityRequest
from app.capabilities.registry import build_default_capability_registry
from app.capabilities.resolver import CapabilityResolver
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
from app.workspace.validator import WorkspaceValidator
from app.agents.providers import LLMRequest, MockLLMProvider
from app.agents.replanning.service import ReplanningService, ReplanOutcomeStatus
from app.approvals.service import ApprovalError, ApprovalService
from app.services.task_service import TaskService
from app.storage.orm import ApprovalRecord, PlanRecord, TaskRecord


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
    task = TaskService(session).create_task(
        title="Phase 13 release verification",
        goal="Check whether version 2.0 is ready for release.",
        workspace=REPO_ROOT,
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
        plan_json={"schema_version": 2, "summary": "verify", "steps": steps, "resolved_steps": []},
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
    service = ReplanningService(db_session, MockLLMProvider(), REPO_ROOT)

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
    service = ReplanningService(db_session, MockLLMProvider(), REPO_ROOT)

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
