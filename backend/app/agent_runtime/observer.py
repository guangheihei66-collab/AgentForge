"""Deterministic observation and completion decisions."""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from ..capabilities.models import ResolvedExecutionSnapshot
from ..tools.gateway import ToolExecutionResult
from .state import RuntimeDecision


class ObservationReason(StrEnum):
    STEP_SUCCEEDED = "STEP_SUCCEEDED"
    TEST_FAILED_DIAGNOSTIC_AVAILABLE = "TEST_FAILED_DIAGNOSTIC_AVAILABLE"
    NON_REPLANNABLE_TOOL_FAILURE = "NON_REPLANNABLE_TOOL_FAILURE"
    POLICY_DENIED = "POLICY_DENIED"
    INVALID_RESULT = "INVALID_RESULT"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


@dataclass(frozen=True, slots=True)
class RuntimeObservation:
    observation_id: str
    step_id: str
    execution_id: str
    capability_id: str
    tool_id: str
    status: str
    result_summary: str
    evidence_refs: tuple[str, ...]
    reason_code: ObservationReason
    retryable: bool
    replan_recommended: bool
    created_at: datetime
    decision: RuntimeDecision
    decision_summary: str
    execution_metadata: dict[str, Any]

    @property
    def tool_result_summary(self) -> str:
        """Backward-compatible bounded summary used by existing audit code."""
        return self.result_summary


class RuntimeObserver:
    """Convert one bounded tool result into the next runtime decision."""

    def observe(
        self,
        *,
        snapshot: ResolvedExecutionSnapshot,
        result: ToolExecutionResult,
        remaining_steps: int,
    ) -> RuntimeObservation:
        tool_summary = (result.summary or "No tool result summary")[:2_000]
        metadata = {
            "step_id": snapshot.step_id,
            "capability_id": snapshot.capability_id,
            "tool_name": snapshot.resolved_tool_id,
            "execution_id": result.execution_id,
            "status": result.status,
            "artifact_path": result.artifact_path,
            "evidence_id": result.evidence_id,
            "normalized_parameters": snapshot.parameters_dict(),
        }
        if result.status != "SUCCESS":
            can_replan = (
                snapshot.capability_id == "test_verification"
                and bool(result.evidence_id)
            )
            return RuntimeObservation(
                observation_id=str(uuid4()),
                step_id=snapshot.step_id,
                execution_id=result.execution_id,
                capability_id=snapshot.capability_id,
                tool_id=snapshot.resolved_tool_id,
                status=result.status,
                result_summary=tool_summary,
                evidence_refs=(result.evidence_id,) if result.evidence_id else (),
                reason_code=(
                    ObservationReason.TEST_FAILED_DIAGNOSTIC_AVAILABLE
                    if can_replan
                    else ObservationReason.NON_REPLANNABLE_TOOL_FAILURE
                ),
                retryable=False,
                replan_recommended=can_replan,
                created_at=datetime.now(timezone.utc),
                decision=(RuntimeDecision.REPLAN if can_replan else RuntimeDecision.FAIL),
                decision_summary=f"Tool execution failed: {tool_summary}"[:2_000],
                execution_metadata=metadata,
            )
        if remaining_steps == 0:
            return RuntimeObservation(
                observation_id=str(uuid4()),
                step_id=snapshot.step_id,
                execution_id=result.execution_id,
                capability_id=snapshot.capability_id,
                tool_id=snapshot.resolved_tool_id,
                status=result.status,
                result_summary=tool_summary,
                evidence_refs=(result.evidence_id,) if result.evidence_id else (),
                reason_code=ObservationReason.STEP_SUCCEEDED,
                retryable=False,
                replan_recommended=False,
                created_at=datetime.now(timezone.utc),
                decision=RuntimeDecision.COMPLETE,
                decision_summary="All approved plan steps completed successfully.",
                execution_metadata=metadata,
            )
        return RuntimeObservation(
            observation_id=str(uuid4()),
            step_id=snapshot.step_id,
            execution_id=result.execution_id,
            capability_id=snapshot.capability_id,
            tool_id=snapshot.resolved_tool_id,
            status=result.status,
            result_summary=tool_summary,
            evidence_refs=(result.evidence_id,) if result.evidence_id else (),
            reason_code=ObservationReason.STEP_SUCCEEDED,
            retryable=False,
            replan_recommended=False,
            created_at=datetime.now(timezone.utc),
            decision=RuntimeDecision.CONTINUE,
            decision_summary=f"Step {snapshot.step_id} succeeded; continue with the next approved step.",
            execution_metadata=metadata,
        )
