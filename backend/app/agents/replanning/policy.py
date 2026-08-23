"""Application-owned replan authorization and deterministic loop guards."""

import hashlib
import json
from collections.abc import Sequence

from ...agent_runtime.observer import ObservationReason
from ...agent_runtime.state import RuntimeDecision
from ...capabilities.models import CapabilityRequest
from ...capabilities.resolver import CapabilityResolver
from ...domain.states.task_state import TaskStatus
from .models import (
    MAX_REPLANS,
    MAX_TOTAL_STEPS,
    ReplanPolicyInput,
    ReplanPolicyResult,
    StepSummary,
)


class ReplanPolicy:
    def evaluate(self, value: ReplanPolicyInput) -> ReplanPolicyResult:
        remaining_replans = max(0, MAX_REPLANS - value.replan_count)
        remaining_steps = max(0, MAX_TOTAL_STEPS - value.total_steps)
        if value.task_status != TaskStatus.RUNNING:
            return self._fail(ObservationReason.POLICY_DENIED, "Task cannot replan", remaining_replans, remaining_steps)
        observation = value.observation
        if (
            observation.reason_code
            != ObservationReason.TEST_FAILED_DIAGNOSTIC_AVAILABLE
            or not observation.replan_recommended
            or not observation.evidence_refs
            or observation.decision != RuntimeDecision.REPLAN
        ):
            return self._fail(ObservationReason.INVALID_RESULT, "Observation cannot authorize replanning", remaining_replans, remaining_steps)
        if remaining_replans == 0 or remaining_steps == 0:
            return self._fail(ObservationReason.BUDGET_EXHAUSTED, "Replan budget exhausted", remaining_replans, remaining_steps)
        if value.repeated_failure_count >= 2:
            return self._fail(ObservationReason.POLICY_DENIED, "Repeated failure made no progress", remaining_replans, remaining_steps)
        if (
            value.previous_progress_fingerprint is not None
            and value.previous_progress_fingerprint == value.current_progress_fingerprint
        ):
            return self._fail(ObservationReason.POLICY_DENIED, "Progress fingerprint did not change", remaining_replans, remaining_steps)
        return ReplanPolicyResult(
            decision=RuntimeDecision.REPLAN,
            reason_code=ObservationReason.TEST_FAILED_DIAGNOSTIC_AVAILABLE,
            summary="Bounded diagnostic replanning is authorized",
            remaining_replans=remaining_replans,
            remaining_steps=remaining_steps,
        )

    @staticmethod
    def _fail(reason_code: ObservationReason, summary: str, remaining_replans: int, remaining_steps: int) -> ReplanPolicyResult:
        return ReplanPolicyResult(RuntimeDecision.FAIL, reason_code, summary, remaining_replans, remaining_steps)


def canonical_plan_fingerprint(
    requests: Sequence[CapabilityRequest], resolver: CapabilityResolver
) -> str:
    payload = [
        {
            "capability_id": request.capability_id,
            "parameters": dict(resolver.normalize(request)),
        }
        for request in requests
    ]
    return _fingerprint(payload)


def progress_fingerprint(
    completed_steps: Sequence[StepSummary],
    reason_code: ObservationReason,
    evidence_keys: Sequence[str],
    current_plan_fingerprint: str,
) -> str:
    payload = {
        "completed_steps": [
            {
                "capability_id": step.capability_id,
                "parameters": dict(sorted(step.parameters.items())),
                "status": step.status,
                "reason_code": step.reason_code,
                "evidence_refs": list(step.evidence_refs[:5]),
            }
            for step in completed_steps[:12]
        ],
        "reason_code": reason_code.value,
        "evidence_keys": list(evidence_keys[:5]),
        "current_plan_fingerprint": current_plan_fingerprint,
    }
    return _fingerprint(payload)


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
