"""Security and schema validation for provider-generated plans."""

import json
from typing import Any

from pydantic import ValidationError

from ...permissions.levels import PermissionLevel
from ...tools.defaults import build_default_registry
from ...workspace.validator import WorkspaceValidator
from .schemas import PlanContract


class PlanValidationError(ValueError):
    """Raised when a generated plan cannot be approved for execution."""


class PlanValidator:
    ACTIONS = {
        "git_read": {
            "status", "log_summary", "diff_summary",
            "check git status", "check git log", "check git diff",
        },
        "file_read": {"read_metadata", "read project metadata"},
        "test_run": {"run_profile", "run unit tests", "run smoke tests"},
    }
    FORBIDDEN_TERMS = {
        "shell", "powershell", "cmd", "bash", "git push", "git commit",
        "git reset", "write", "delete", "remove", ".env", "secret",
        "credential", "password", "token",
    }

    def __init__(self, workspace_validator: WorkspaceValidator):
        self.workspace_validator = workspace_validator
        self.registry = build_default_registry(workspace_validator)

    def validate(self, raw: str | dict[str, Any], workspace: str) -> PlanContract:
        payload = self._parse_json(raw)
        try:
            plan = PlanContract.model_validate(payload)
        except ValidationError as exc:
            raise PlanValidationError(str(exc)) from exc

        try:
            self.workspace_validator.validate_workspace(workspace)
        except ValueError as exc:
            raise PlanValidationError(str(exc)) from exc

        for step in plan.steps:
            self._validate_step(step)
        return plan

    def _parse_json(self, raw: str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise PlanValidationError("Provider returned invalid JSON") from exc
        if not isinstance(raw, dict):
            raise PlanValidationError("Plan must be a JSON object")
        return raw

    def _validate_step(self, step) -> None:
        definition = self.registry.get(step.tool)
        if definition is None or not definition.enabled:
            raise PlanValidationError(f"Unknown or disabled tool: {step.tool}")
        if step.permission_level not in {
            PermissionLevel.SAFE_READ,
            PermissionLevel.APPROVED_EXEC,
        }:
            raise PlanValidationError("Denied permission is not valid in a plan")
        if step.permission_level != definition.permission_level:
            raise PlanValidationError(
                f"Permission does not match tool policy: {step.tool}"
            )
        if step.action not in self.ACTIONS[step.tool]:
            raise PlanValidationError(f"Unsupported action for tool: {step.action}")
        lowered = f"{step.tool} {step.action}".lower()
        if any(term in lowered for term in self.FORBIDDEN_TERMS):
            raise PlanValidationError(f"Forbidden operation in plan: {step.action}")
