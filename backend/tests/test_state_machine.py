import pytest

from app.domain.states.task_state import (
    InvalidTransitionError,
    TaskStatus,
    transition_task,
)


def test_valid_state_transition():
    assert transition_task(TaskStatus.CREATED, TaskStatus.PLANNING) == TaskStatus.PLANNING
    assert (
        transition_task(TaskStatus.RUNNING, TaskStatus.SUCCESS) == TaskStatus.SUCCESS
    )


def test_invalid_transition_rejected():
    with pytest.raises(InvalidTransitionError):
        transition_task(TaskStatus.CREATED, TaskStatus.SUCCESS)


def test_cancellation_is_supported():
    assert transition_task(TaskStatus.WAITING_APPROVAL, TaskStatus.CANCELLED) == TaskStatus.CANCELLED


def test_failure_is_supported():
    assert transition_task(TaskStatus.RUNNING, TaskStatus.FAILED) == TaskStatus.FAILED
