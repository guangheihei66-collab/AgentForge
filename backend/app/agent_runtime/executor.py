"""Adapter between validated plan steps and the existing Tool Gateway."""

from typing import Any, Mapping

from ..contracts.permissions import PermissionLevel
from ..tools.gateway import ToolExecutionRequest, ToolExecutionResult, ToolGateway


class RuntimeExecutor:
    """Translate human-readable plan actions into fixed Tool Gateway actions."""

    ACTIONS: dict[str, dict[str, tuple[str, dict[str, Any]]]] = {
        "git_read": {
            "status": ("status", {}),
            "check git status": ("status", {}),
            "log_summary": ("log_summary", {}),
            "check git log": ("log_summary", {}),
            "diff_summary": ("diff_summary", {}),
            "check git diff": ("diff_summary", {}),
        },
        "file_read": {
            "read_metadata": ("read_metadata", {"relative_path": "PROJECT_CONTEXT.md"}),
            "read project metadata": (
                "read_metadata",
                {"relative_path": "PROJECT_CONTEXT.md"},
            ),
        },
        "test_run": {
            "run_profile": ("run_profile", {"profile": "smoke"}),
            "run smoke tests": ("run_profile", {"profile": "smoke"}),
            "run unit tests": ("run_profile", {"profile": "unit"}),
        },
    }

    def __init__(self, gateway: ToolGateway):
        self.gateway = gateway

    def execute(
        self,
        *,
        task_id: str,
        plan_id: str,
        plan_version: int,
        workspace: str,
        step: Mapping[str, Any],
    ) -> ToolExecutionResult:
        tool_name = str(step["tool"])
        requested_action = str(step["action"])
        try:
            action, parameters = self.ACTIONS[tool_name][requested_action]
        except KeyError as exc:
            raise ValueError(
                f"Runtime cannot map plan action: {tool_name}/{requested_action}"
            ) from exc

        permission = PermissionLevel(str(step["permission_level"]).upper())
        return self.gateway.execute(
            ToolExecutionRequest(
                task_id=task_id,
                tool_name=tool_name,
                action=action,
                workspace=workspace,
                parameters=parameters,
                granted_permission=permission,
                approved=True,
                plan_id=plan_id,
                plan_version=plan_version,
            )
        )
