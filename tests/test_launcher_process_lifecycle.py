import os
import subprocess
import sys
import time

import pytest

from launcher.process_session import AgentForgeProcessSession


def wait_until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    assert predicate()


def sleeper(seconds=30):
    return [sys.executable, "-c", f"import time; time.sleep({seconds})"]


@pytest.mark.skipif(os.name != "nt", reason="owned process implementation is Windows-specific")
def test_session_owns_and_stops_launched_process():
    session = AgentForgeProcessSession()
    process = session.start("backend", sleeper())
    assert process.poll() is None
    assert session.owned_labels() == ("backend",)

    session.stop()

    wait_until(lambda: process.poll() is not None)
    assert session.owned_labels() == ()


@pytest.mark.skipif(os.name != "nt", reason="owned process implementation is Windows-specific")
def test_session_stop_is_idempotent_and_does_not_touch_unrelated_process():
    unrelated = subprocess.Popen(sleeper())
    session = AgentForgeProcessSession()
    session.start("frontend", sleeper())
    try:
        session.stop()
        session.stop()
        assert unrelated.poll() is None
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=5)
