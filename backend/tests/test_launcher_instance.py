from __future__ import annotations

import os
from pathlib import Path
import sys
import time
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from launcher.instance import InstanceCommand, InstanceOwnership


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows launcher behavior")


def unique_root() -> Path:
    return Path(r"D:\AgentProjectData\AgentForge\test-runs") / (
        "launcher-instance-" + uuid4().hex
    )


def wait_for(values: list[InstanceCommand], expected: InstanceCommand) -> None:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if expected in values:
            return
        time.sleep(0.025)
    raise AssertionError(f"did not receive {expected}; values={values!r}")


def test_first_instance_acquires_and_second_instance_activates_first():
    root = unique_root()
    received: list[InstanceCommand] = []
    first = InstanceOwnership(root, on_command=received.append)
    second = InstanceOwnership(root)

    try:
        assert first.acquire() is True
        assert second.acquire() is False
        wait_for(received, InstanceCommand.SHOW_OR_OPEN)
    finally:
        second.release()
        first.release()


def test_repeated_activation_does_not_create_another_owner():
    root = unique_root()
    received: list[InstanceCommand] = []
    first = InstanceOwnership(root, on_command=received.append)
    contenders = [InstanceOwnership(root) for _ in range(3)]

    try:
        assert first.acquire() is True
        assert all(contender.acquire() is False for contender in contenders)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and len(received) < 3:
            time.sleep(0.025)
        assert received.count(InstanceCommand.SHOW_OR_OPEN) == 3
    finally:
        for contender in contenders:
            contender.release()
        first.release()


def test_named_commands_reach_existing_instance():
    root = unique_root()
    received: list[InstanceCommand] = []
    first = InstanceOwnership(root, on_command=received.append)

    try:
        assert first.acquire() is True
        assert InstanceOwnership.signal(root, InstanceCommand.RESTART_SERVICES) is True
        wait_for(received, InstanceCommand.RESTART_SERVICES)
    finally:
        first.release()


def test_instance_ownership_recovers_after_owner_releases():
    root = unique_root()
    first = InstanceOwnership(root)
    second = InstanceOwnership(root)

    assert first.acquire() is True
    assert second.acquire() is False
    first.release()
    try:
        assert second.acquire() is True
    finally:
        second.release()


def test_installation_names_are_distinct_for_different_roots():
    left = InstanceOwnership(unique_root())
    right = InstanceOwnership(unique_root())

    try:
        assert left.mutex_name != right.mutex_name
        assert left.event_names != right.event_names
    finally:
        left.release()
        right.release()
