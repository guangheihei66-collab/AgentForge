from dataclasses import FrozenInstanceError, replace
from datetime import datetime

import pytest

from app.agent_runtime.observer import ObservationReason, RuntimeObserver
from app.agent_runtime.state import RuntimeDecision
from app.capabilities.models import ResolvedExecutionSnapshot
from app.capabilities.models import CapabilityRequest
from app.capabilities.registry import build_default_capability_registry
from app.capabilities.resolver import CapabilityResolver
from app.domain.states.task_state import TaskStatus
from app.agents.replanning.models import ReplanPolicyInput, StepSummary
from app.agents.replanning.policy import (
    ReplanPolicy,
    canonical_plan_fingerprint,
    progress_fingerprint,
)
from app.tools.defaults import build_default_registry
from app.tools.gateway import ToolExecutionResult
from app.workspace.validator import WorkspaceValidator


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
