"""Security and schema validation for provider-generated capability plans."""

import json
from typing import Any

from pydantic import ValidationError

from ...workspace.validator import WorkspaceValidator
from .schemas import PlanContract


class PlanValidationError(ValueError):
    """Raised when a generated plan cannot be resolved or approved."""


class PlanValidator:
    FORBIDDEN_TERMS = {
        "shell", "powershell", "cmd", "bash", "git push", "git commit",
        "git reset", "write", "delete", "remove", ".env", "secret",
        "credential", "password", "token",
    }

    def __init__(self, workspace_validator: WorkspaceValidator):
        self.workspace_validator = workspace_validator

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
            lowered = json.dumps(step.parameters, ensure_ascii=False).lower()
            if any(term in lowered for term in self.FORBIDDEN_TERMS):
                raise PlanValidationError(
                    f"Forbidden parameter in capability: {step.capability_id}"
                )
        return plan

    @staticmethod
    def _parse_json(raw: str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise PlanValidationError("Provider returned invalid JSON") from exc
        if not isinstance(raw, dict):
            raise PlanValidationError("Plan must be a JSON object")
        return raw
