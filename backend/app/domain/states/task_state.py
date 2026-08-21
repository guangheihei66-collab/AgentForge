"""Explicit task state machine independent from HTTP and persistence."""

from enum import StrEnum


class TaskStatus(StrEnum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class InvalidTransitionError(ValueError):
    """Raised when a task state transition is not allowed."""


ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.CREATED: frozenset({TaskStatus.PLANNING, TaskStatus.CANCELLED}),
    TaskStatus.PLANNING: frozenset(
        {TaskStatus.WAITING_APPROVAL, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.WAITING_APPROVAL: frozenset(
        {TaskStatus.RUNNING, TaskStatus.CANCELLED}
    ),
    TaskStatus.RUNNING: frozenset(
        {TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.SUCCESS: frozenset(),
    TaskStatus.FAILED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}


def transition_task(current: TaskStatus, target: TaskStatus) -> TaskStatus:
    """Validate and return a legal target state."""

    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidTransitionError(
            f"Invalid task transition: {current.value} -> {target.value}"
        )
    return target
