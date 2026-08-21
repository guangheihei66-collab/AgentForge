"""Read-only Git tool with a fixed action allowlist."""

import subprocess
from typing import Any

from .models import ToolDefinition
from ..permissions.levels import PermissionLevel


class GitReadTool:
    ACTIONS = {
        "status": ("status", "--short"),
        "log_summary": ("log", "-5", "--oneline"),
        "diff_summary": ("diff", "--stat"),
    }

    definition: ToolDefinition

    def __init__(self):
        self.definition = ToolDefinition(
            name="git_read",
            description="Read-only Git status, log, and diff summaries.",
            risk_level="low",
            permission_level=PermissionLevel.SAFE_READ,
            allowed_actions=tuple(self.ACTIONS),
            executor=self,
        )

    def execute(self, action: str, parameters: dict[str, Any], workspace: str) -> dict[str, Any]:
        if parameters:
            raise ValueError("git_read does not accept arbitrary parameters")
        try:
            args = self.ACTIONS[action]
        except KeyError as exc:
            raise ValueError(f"Unsupported git action: {action}") from exc

        completed = subprocess.run(
            ["git", *args],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            shell=False,
        )
        output = (completed.stdout or completed.stderr).strip()[:20_000]
        if completed.returncode != 0:
            raise RuntimeError(f"Git action failed ({completed.returncode}): {output}")
        return {"action": action, "exit_code": completed.returncode, "summary": output}
