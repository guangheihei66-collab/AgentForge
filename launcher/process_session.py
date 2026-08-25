"""Owned Windows process session for the AgentForge controller."""

from __future__ import annotations

import ctypes
import os
import subprocess
from dataclasses import dataclass
from typing import Mapping, Sequence


CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JobObjectExtendedLimitInformation = 9


@dataclass(frozen=True)
class OwnedProcess:
    label: str
    process: subprocess.Popen[bytes]


if os.name == "nt":
    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]

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
    """Own only processes launched through this controller session."""

    def __init__(self) -> None:
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
            handle, JobObjectExtendedLimitInformation, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            kernel32.CloseHandle(handle)
            raise ctypes.WinError(ctypes.get_last_error())
        return handle

    def start(
        self,
        label: str,
        command: Sequence[str],
        *,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> subprocess.Popen[bytes]:
        if label in self._owned:
            raise ValueError(f"process label already owned: {label}")
        process = subprocess.Popen(
            list(command),
            cwd=cwd,
            env=dict(env) if env is not None else None,
            creationflags=CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
        try:
            if self._job is not None:
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                if not kernel32.AssignProcessToJobObject(self._job, process._handle):
                    raise ctypes.WinError(ctypes.get_last_error())
            self._owned[label] = OwnedProcess(label, process)
            return process
        except BaseException:
            process.kill()
            process.wait()
            raise

    def owned_labels(self) -> tuple[str, ...]:
        return tuple(self._owned)

    def stop(self, timeout: float = 5.0) -> None:
        owned = tuple(self._owned.values())
        self._owned.clear()
        for item in owned:
            if item.process.poll() is None:
                item.process.terminate()
        for item in owned:
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
