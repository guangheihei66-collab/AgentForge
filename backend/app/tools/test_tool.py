"""Predefined test profiles; no arbitrary command input is accepted."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .models import ToolDefinition
from ..contracts.permissions import PermissionLevel


class TestTool:
    __test__ = False

    PROFILES = {
        "unit": (sys.executable, "-m", "pytest", "-q"),
        "smoke": (
            sys.executable,
            "-c",
            "print('AgentForge smoke profile passed')",
        ),
    }

    def __init__(self):
        self.definition = ToolDefinition(
            name="test_run",
            description="Run one predefined unit or smoke test profile.",
            risk_level="medium",
            permission_level=PermissionLevel.APPROVED_EXEC,
            allowed_actions=("run_profile",),
            executor=self,
            execution_contract_version="1",
        )

    def execute(self, action: str, parameters: dict[str, Any], workspace: str) -> dict[str, Any]:
        if action != "run_profile":
            raise ValueError(f"Unsupported test action: {action}")
        profile = parameters.get("profile")
        if not isinstance(profile, str) or profile not in self.PROFILES:
            raise ValueError("Only the predefined unit and smoke profiles are allowed")

        completed = subprocess.run(
            list(self.PROFILES[profile]),
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            shell=False,
            env=self._isolated_test_environment(workspace),
        )
        stdout = (completed.stdout or "")[-20_000:]
        stderr = (completed.stderr or "")[-20_000:]
        return {
            "profile": profile,
            "exit_code": completed.returncode,
            "success": completed.returncode == 0,
            "stdout": stdout,
            "stderr": stderr,
        }

    @staticmethod
    def _isolated_test_environment(workspace: str) -> dict[str, str]:
        """Run predefined profiles independently of the product process.

        The test child must use the source checkout it is verifying and the
        deterministic Mock provider.  In particular, a launcher-provided real
        provider or production database URL must never cross this boundary.
        Process-local TEMP/TMP and cache settings are intentionally preserved.
        """

        environment = dict(os.environ)
        for name in (
            "AGENTFORGE_LLM_BASE_URL",
            "AGENTFORGE_LLM_MODEL",
            "AGENTFORGE_LLM_API_KEY",
            "AGENTFORGE_LLM_STRUCTURED_OUTPUT_MODE",
            "AGENTFORGE_LLM_TIMEOUT_SECONDS",
            "AGENTFORGE_LLM_MAX_OUTPUT_TOKENS",
        ):
            environment.pop(name, None)
        environment["AGENTFORGE_LLM_PROVIDER"] = "mock"
        environment["AGENTFORGE_DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
        environment["PYTHONNOUSERSITE"] = "1"
        environment["PYTHONHASHSEED"] = "0"
        source_root = Path(workspace).expanduser().resolve()
        environment["PYTHONPATH"] = str(source_root / "backend")
        return environment

    @staticmethod
    def classify_result(result: dict[str, Any]) -> str:
        """Classify the predefined test profile's domain result."""
        return "SUCCESS" if result.get("exit_code") == 0 and result.get("success") is True else "FAILED"
