"""Bounded immutable contracts for controlled re-planning."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping, Any

from pydantic import BaseModel, ConfigDict, Field

from ...agent_runtime.observer import ObservationReason, RuntimeObservation
from ...agent_runtime.state import RuntimeDecision
from ...domain.states.task_state import TaskStatus
from ..planner.schemas import CapabilityPlanStep


MAX_REPLANS = 2
MAX_TOTAL_STEPS = 12
MAX_PROPOSAL_STEPS = 10
MAX_CONTEXT_BYTES = 8 * 1024
MAX_PROMPT_BYTES = 12 * 1024


@dataclass(frozen=True, slots=True)
class StepSummary:
    capability_id: str
    parameters: Mapping[str, str]
    status: str
    reason_code: str
    summary: str
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EvidenceSummary:
    evidence_id: str
    summary: str
    content_hash: str | None


@dataclass(frozen=True, slots=True)
class ReplanContext:
    user_goal: str
    original_plan_id: str
    current_plan_id: str
    current_plan_version: int
    remaining_plan_summary: tuple[StepSummary, ...]
    completed_step_summaries: tuple[StepSummary, ...]
    latest_observation: RuntimeObservation
    evidence_summaries: tuple[EvidenceSummary, ...]
    remaining_step_budget: int
    remaining_replan_budget: int

    @classmethod
    def bounded(cls, **values: Any) -> "ReplanContext":
        def bounded_step(step: StepSummary) -> StepSummary:
            return StepSummary(
                capability_id=step.capability_id,
                parameters=dict(step.parameters),
                status=step.status,
                reason_code=step.reason_code,
                summary=step.summary[:500],
                evidence_refs=tuple(step.evidence_refs[:5]),
            )

        return cls(
            user_goal=str(values["user_goal"])[:2_000],
            original_plan_id=str(values["original_plan_id"]),
            current_plan_id=str(values["current_plan_id"]),
            current_plan_version=int(values["current_plan_version"]),
            remaining_plan_summary=tuple(
                bounded_step(item)
                for item in tuple(values["remaining_plan_summary"])[:12]
            ),
            completed_step_summaries=tuple(
                bounded_step(item)
                for item in tuple(values["completed_step_summaries"])[:12]
            ),
            latest_observation=values["latest_observation"],
            evidence_summaries=tuple(
                EvidenceSummary(item.evidence_id, item.summary[:500], item.content_hash)
                for item in tuple(values["evidence_summaries"])[:5]
            ),
            remaining_step_budget=max(0, int(values["remaining_step_budget"])),
            remaining_replan_budget=max(0, int(values["remaining_replan_budget"])),
        )


class ReplanProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_summary: str = Field(min_length=1, max_length=500)
    revised_remaining_steps: list[CapabilityPlanStep] = Field(
        min_length=1, max_length=MAX_PROPOSAL_STEPS
    )


@dataclass(frozen=True, slots=True)
class ReplanPolicyInput:
    task_status: TaskStatus
    observation: RuntimeObservation
    current_plan_id: str
    current_plan_version: int
    replan_count: int
    total_steps: int
    current_plan_fingerprint: str
    previous_plan_fingerprints: tuple[str, ...]
    current_progress_fingerprint: str
    previous_progress_fingerprint: str | None
    repeated_failure_count: int


@dataclass(frozen=True, slots=True)
class ReplanPolicyResult:
    decision: RuntimeDecision
    reason_code: ObservationReason
    summary: str
    remaining_replans: int
    remaining_steps: int


class ReplanOutcomeStatus(StrEnum):
    WAITING_APPROVAL = "WAITING_APPROVAL"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class ReplanOutcome:
    status: ReplanOutcomeStatus
    task_id: str
    plan_id: str | None
    plan_version: int | None
    approval_id: str | None
    reason_code: str
    summary: str


@dataclass(frozen=True, slots=True)
class AuthoritativePlan:
    plan_id: str
    plan_version: int
    approval_id: str | None
    approval_decision: str | None
    executable: bool
