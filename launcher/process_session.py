"""Owned, windowless Windows process sessions for the AgentForge launcher."""

from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from pathlib import Path
import subprocess
import time
from typing import Any, Mapping, Sequence
from uuid import uuid4


CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
STARTF_USESHOWWINDOW = getattr(subprocess, "STARTF_USESHOWWINDOW", 0x00000001)
SW_HIDE = 0
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JobObjectExtendedLimitInformation = 9


def hidden_popen_options() -> dict[str, Any]:
    """Return the platform options used for a background AgentForge child."""

    options: dict[str, Any] = {
        "creationflags": CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = SW_HIDE
        options["creationflags"] |= CREATE_NO_WINDOW
        options["startupinfo"] = startupinfo
    return options


@dataclass(frozen=True)
class ProcessIdentity:
    """Bounded metadata used to explain and verify a launched child."""

    label: str
    pid: int
    command: tuple[str, ...]
    cwd: str | None
    started_at: float
    session_token: str


@dataclass(frozen=True)
class OwnedProcess:
    label: str
    process: subprocess.Popen[Any]
    identity: ProcessIdentity


if os.name == "nt":

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_ulonglong)
            for name in (
                "ReadOperationCount",
                "WriteOperationCount",
                "OtherOperationCount",
                "ReadTransferCount",
                "WriteTransferCount",
                "OtherTransferCount",
            )
        ]

    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]

    class _IOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]


class AgentForgeProcessSession:
    """Own only children launched through one launcher instance.

    The Windows Job Object is the authoritative ownership boundary. A PID file
    is only a bounded diagnostic aid and is never used to discover or terminate
    arbitrary Python/Node processes.
    """

    def __init__(
        self,
        *,
        runtime_dir: Path | None = None,
        session_token: str | None = None,
    ) -> None:
        self.runtime_dir = Path(runtime_dir).resolve() if runtime_dir else None
        self.session_token = session_token or uuid4().hex
        self._owned: dict[str, OwnedProcess] = {}
        self._job = None
        if os.name == "nt":
            self._job = self._create_job()

    @staticmethod
    def _create_job():
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = _IOBJECT_EXTENDED_LIMIT_INFORMATION()
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
            handle,
            JobObjectExtendedLimitInformation,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            kernel32.CloseHandle(handle)
            raise ctypes.WinError(ctypes.get_last_error())
        return handle

    def _ensure_job(self) -> None:
        if os.name == "nt" and self._job is None:
            self._job = self._create_job()

    def _pid_path(self, label: str) -> Path | None:
        if self.runtime_dir is None:
            return None
        return self.runtime_dir / f"launcher-{label}.pid"

    def _write_pid(self, label: str, pid: int) -> None:
        path = self._pid_path(label)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{pid}\n", encoding="ascii")

    def _remove_pid(self, identity: ProcessIdentity) -> None:
        path = self._pid_path(identity.label)
        if path is None or not path.exists():
            return
        try:
            recorded = path.read_text(encoding="ascii").strip()
        except OSError:
            return
        if recorded == str(identity.pid):
            try:
                path.unlink()
            except OSError:
                pass

    def start(
        self,
        label: str,
        command: Sequence[str],
        *,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
        stdout_path: Path | None = None,
        stderr_path: Path | None = None,
    ) -> subprocess.Popen[Any]:
        if label in self._owned:
            raise ValueError(f"process label already owned: {label}")
        self._ensure_job()

        normalized_command = tuple(str(part) for part in command)
        output_handles: list[Any] = []
        popen_options = hidden_popen_options()
        popen_options.update(
            {
                "cwd": cwd,
                "env": dict(env) if env is not None else None,
            }
        )
        try:
            if stdout_path is not None:
                stdout_path = Path(stdout_path)
                stdout_path.parent.mkdir(parents=True, exist_ok=True)
                handle = stdout_path.open("ab")
                output_handles.append(handle)
                popen_options["stdout"] = handle
            if stderr_path is not None:
                stderr_path = Path(stderr_path)
                stderr_path.parent.mkdir(parents=True, exist_ok=True)
                handle = stderr_path.open("ab")
                output_handles.append(handle)
                popen_options["stderr"] = handle

            process = subprocess.Popen(list(normalized_command), **popen_options)
        finally:
            for handle in output_handles:
                handle.close()

        identity = ProcessIdentity(
            label=label,
            pid=process.pid,
            command=normalized_command,
            cwd=cwd,
            started_at=time.time(),
            session_token=self.session_token,
        )
        try:
            if self._job is not None:
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                if not kernel32.AssignProcessToJobObject(self._job, process._handle):
                    raise ctypes.WinError(ctypes.get_last_error())
            self._owned[label] = OwnedProcess(label, process, identity)
            self._write_pid(label, process.pid)
            return process
        except BaseException:
            if process.poll() is None:
                process.kill()
            process.wait()
            raise

    def owned_labels(self) -> tuple[str, ...]:
        return tuple(self._owned)

    def owned_processes(self) -> tuple[OwnedProcess, ...]:
        return tuple(self._owned.values())

    def identity(self, label: str) -> ProcessIdentity | None:
        item = self._owned.get(label)
        return item.identity if item else None

    def stop(self, timeout: float = 5.0) -> None:
        owned = tuple(self._owned.values())
        self._owned.clear()
        for item in owned:
            if item.process.poll() is None:
                item.process.terminate()
        for item in owned:
            self._remove_pid(item.identity)
            if item.process.poll() is None:
                try:
                    item.process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    item.process.kill()
                    item.process.wait(timeout=timeout)
        self.close()

    def close(self) -> None:
        if self._job is not None:
            ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(self._job)
            self._job = None

    def __enter__(self) -> "AgentForgeProcessSession":
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()
