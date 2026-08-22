"""Deterministic observation and completion decisions."""

from dataclasses import dataclass
from typing import Any, Mapping

from ..tools.gateway import ToolExecutionResult
from .state import RuntimeDecision


@dataclass(frozen=True, slots=True)
class RuntimeObservation:
    decision: RuntimeDecision
    decision_summary: str
    tool_result_summary: str
    execution_metadata: dict[str, Any]


class RuntimeObserver:
    """Convert one bounded tool result into the next runtime decision."""

    def observe(
        self,
        *,
        step: Mapping[str, Any],
        result: ToolExecutionResult,
        remaining_steps: int,
    ) -> RuntimeObservation:
        tool_summary = (result.summary or "No tool result summary")[:2_000]
        metadata = {
            "step_id": str(step["step_id"]),
            "tool_name": str(step["tool"]),
            "execution_id": result.execution_id,
            "status": result.status,
            "artifact_path": result.artifact_path,
            "evidence_id": result.evidence_id,
        }
        if result.status != "SUCCESS":
            return RuntimeObservation(
                decision=RuntimeDecision.FAIL,
                decision_summary=f"Tool execution failed: {tool_summary}"[:2_000],
                tool_result_summary=tool_summary,
                execution_metadata=metadata,
            )
        if remaining_steps == 0:
            return RuntimeObservation(
                decision=RuntimeDecision.COMPLETE,
                decision_summary="All approved plan steps completed successfully.",
                tool_result_summary=tool_summary,
                execution_metadata=metadata,
            )
        return RuntimeObservation(
            decision=RuntimeDecision.CONTINUE,
            decision_summary=f"Step {step['step_id']} succeeded; continue with the next approved step.",
            tool_result_summary=tool_summary,
            execution_metadata=metadata,
        )
