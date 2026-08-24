"""Canonical, secret-free runtime identity."""

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess


@dataclass(frozen=True, slots=True)
class RuntimeIdentity:
    product: str
    version: str
    revision: str | None
    environment: str


def _version() -> str:
    package = Path(__file__).resolve().parents[4] / "frontend" / "package.json"
    try:
        return str(json.loads(package.read_text(encoding="utf-8"))["version"])
    except (OSError, KeyError, TypeError, ValueError):
        return "UNKNOWN"


def _revision() -> str | None:
    root = Path(__file__).resolve().parents[4]
    try:
        value = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True,
            capture_output=True, text=True, timeout=2,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return value or None


def get_runtime_identity() -> RuntimeIdentity:
    return RuntimeIdentity("AgentForge", _version(), _revision(), "beta")
