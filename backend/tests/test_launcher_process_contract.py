from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

import pytest

from launcher.process_session import (
    CREATE_NO_WINDOW,
    STARTF_USESHOWWINDOW,
    AgentForgeProcessSession,
    hidden_popen_options,
)


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows launcher behavior")


def wait_until(predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    assert predicate()


def sleeper(seconds: int = 30) -> list[str]:
    return [sys.executable, "-c", f"import time; time.sleep({seconds})"]


def test_hidden_child_contract_uses_no_console_options():
    options = hidden_popen_options()

    assert options["creationflags"] & CREATE_NO_WINDOW
    assert options["stdin"] is subprocess.DEVNULL
    assert options["startupinfo"].dwFlags & STARTF_USESHOWWINDOW
    assert options["startupinfo"].wShowWindow == 0


def test_runtime_pid_metadata_is_external_and_removed_for_owned_process():
    runtime = Path(r"D:\AgentProjectData\AgentForge\test-runs") / (
        "launcher-process-" + uuid4().hex
    )
    session = AgentForgeProcessSession(runtime_dir=runtime)
    process = session.start(
        "backend",
        sleeper(),
        stdout_path=runtime / "logs" / "backend.log",
        stderr_path=runtime / "logs" / "backend-error.log",
    )
    pid_file = runtime / "launcher-backend.pid"

    try:
        assert process.poll() is None
        assert pid_file.read_text(encoding="ascii").strip() == str(process.pid)
        assert session.identity("backend").session_token == session.session_token
    finally:
        session.stop()

    wait_until(lambda: process.poll() is not None)
    assert not pid_file.exists()
