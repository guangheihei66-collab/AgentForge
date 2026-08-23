"""Bounded immutable contracts for controlled re-planning."""

from dataclasses import dataclass
from typing import Mapping

from ...agent_runtime.observer import ObservationReason, RuntimeObservation
from ...agent_runtime.state import RuntimeDecision
from ...domain.states.task_state import TaskStatus


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
