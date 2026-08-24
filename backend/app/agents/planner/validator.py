"""Security and schema validation for provider-generated capability plans."""

import json
from typing import Any

from pydantic import ValidationError

from ...workspace.validator import WorkspaceValidator
from .schemas import PlanContract


class PlanValidationError(ValueError):
    """Raised when a generated plan cannot be resolved or approved."""

    def __init__(self, message: str, *, diagnostics: dict[str, Any] | None = None):
        super().__init__(message)
        self.diagnostics = dict(diagnostics or {})


class PlanValidator:
    FORBIDDEN_TERMS = {
        "shell", "powershell", "cmd", "bash", "git push", "git commit",
        "git reset", "write", "delete", "remove", ".env", "secret",
        "credential", "password", "token",
    }

    def __init__(
        self,
        workspace_validator: WorkspaceValidator,
        metadata_manifest: tuple[str, ...] | None = None,
    ):
        self.workspace_validator = workspace_validator
        self.metadata_manifest = (
            None if metadata_manifest is None else frozenset(metadata_manifest)
        )

    def validate(self, raw: str | dict[str, Any], workspace: str) -> PlanContract:
        payload = self._parse_json(raw)
        try:
            plan = PlanContract.model_validate(payload)
        except ValidationError as exc:
            raise PlanValidationError(
                "Provider plan failed schema validation",
                diagnostics=self._validation_diagnostics(exc),
            ) from exc
        try:
            self.workspace_validator.validate_workspace(workspace)
        except ValueError as exc:
            raise PlanValidationError(
                str(exc),
                diagnostics=self._simple_diagnostics("workspace_validation"),
            ) from exc
        for step in plan.steps:
            lowered = json.dumps(step.parameters, ensure_ascii=False).lower()
            if any(term in lowered for term in self.FORBIDDEN_TERMS):
                raise PlanValidationError(
                    f"Forbidden parameter in capability: {step.capability_id}",
                    diagnostics=self._simple_diagnostics("forbidden_parameter"),
                )
            if step.capability_id == "project_metadata" and self.metadata_manifest is not None:
                relative_path = step.parameters.get("relative_path")
                if relative_path not in self.metadata_manifest:
                    raise PlanValidationError(
                        "project_metadata path is not present in the metadata manifest",
                        diagnostics=self._simple_diagnostics("metadata_not_grounded"),
                    )
        return plan

    @staticmethod
    def _parse_json(raw: str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise PlanValidationError(
                    "Provider returned invalid JSON",
                    diagnostics=PlanValidator._simple_diagnostics("invalid_json"),
                ) from exc
        if not isinstance(raw, dict):
            raise PlanValidationError(
                "Plan must be a JSON object",
                diagnostics=PlanValidator._simple_diagnostics("object_required"),
            )
        return raw

    @staticmethod
    def _simple_diagnostics(error_type: str) -> dict[str, Any]:
        return {
            "validation_error_count": 1,
            "validation_error_paths": [],
            "validation_error_types": [error_type[:80]],
            "validation_summary_truncated": False,
        }

    @staticmethod
    def _validation_diagnostics(exc: ValidationError) -> dict[str, Any]:
        errors = exc.errors()
        bounded = errors[:8]
        return {
            "validation_error_count": len(errors),
            "validation_error_paths": [
                ".".join(str(part) for part in error.get("loc", ()))[:120]
                for error in bounded
            ],
            "validation_error_types": [
                str(error.get("type", "validation_error"))[:80]
                for error in bounded
            ],
            "validation_summary_truncated": len(errors) > len(bounded),
        }
