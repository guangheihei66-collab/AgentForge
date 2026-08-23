"""In-memory state and decision vocabulary for the runtime loop."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RuntimeState(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    OBSERVING = "OBSERVING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RuntimeDecision(StrEnum):
    CONTINUE = "CONTINUE"
    COMPLETE = "COMPLETE"
    FAIL = "FAIL"
    REPLAN = "REPLAN"


@dataclass(slots=True)
class RuntimeSnapshot:
    """Bounded runtime state; never contains hidden model reasoning."""

    state: RuntimeState = RuntimeState.CREATED
    current_step_id: str | None = None
    completed_steps: int = 0
    decision_summary: str = "Runtime created"
    history: list[RuntimeState] = field(default_factory=lambda: [RuntimeState.CREATED])
    metadata: dict[str, Any] = field(default_factory=dict)

    def transition(self, target: RuntimeState, summary: str) -> None:
        self.state = target
        self.decision_summary = summary[:2_000]
        self.history.append(target)
