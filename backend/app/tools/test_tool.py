"""Predefined test profiles; no arbitrary command input is accepted."""

import subprocess
import sys
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
    def classify_result(result: dict[str, Any]) -> str:
        """Classify the predefined test profile's domain result."""
        return "SUCCESS" if result.get("exit_code") == 0 and result.get("success") is True else "FAILED"
