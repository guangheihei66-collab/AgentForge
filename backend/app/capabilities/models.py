"""Immutable contracts for capability requirements and resolved execution."""

from dataclasses import dataclass
import re
from typing import Any, Mapping

from ..contracts.permissions import PermissionLevel


@dataclass(frozen=True, slots=True)
class ParameterFieldDefinition:
    name: str
    required: bool
    allowed_values: tuple[str, ...]
    default: str | None = None


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    id: str
    description: str
    risk_level: str
    required_permission: PermissionLevel
    candidate_tool_ids: tuple[str, ...]
    action: str
    parameter_schema: tuple[ParameterFieldDefinition, ...]


@dataclass(frozen=True, slots=True)
class CapabilityRequest:
    capability_id: str
    parameters: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ResolvedExecutionSnapshot:
    task_id: str
    plan_id: str
    plan_version: int
    step_id: str
    capability_id: str
    resolved_tool_id: str
    resolved_action: str
    normalized_parameters: tuple[tuple[str, str], ...]
    registry_fingerprint: str

    def parameters_dict(self) -> dict[str, str]:
        return dict(self.normalized_parameters)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "step_id": self.step_id,
            "capability_id": self.capability_id,
            "resolved_tool_id": self.resolved_tool_id,
            "resolved_action": self.resolved_action,
            "normalized_parameters": self.parameters_dict(),
            "registry_fingerprint": self.registry_fingerprint,
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> "ResolvedExecutionSnapshot":
        expected = {
            "task_id",
            "plan_id",
            "plan_version",
            "step_id",
            "capability_id",
            "resolved_tool_id",
            "resolved_action",
            "normalized_parameters",
            "registry_fingerprint",
        }
        if set(payload) != expected:
            raise ValueError("Resolved snapshot fields are invalid")
        parameters = payload["normalized_parameters"]
        if not isinstance(parameters, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in parameters.items()
        ):
            raise ValueError("Resolved snapshot parameters are invalid")
        version = payload["plan_version"]
        fingerprint = payload["registry_fingerprint"]
        if not isinstance(version, int) or version < 1:
            raise ValueError("Resolved snapshot plan version is invalid")
        if not isinstance(fingerprint, str) or not re.fullmatch(
            r"[0-9a-f]{64}", fingerprint
        ):
            raise ValueError("Resolved snapshot fingerprint is invalid")
        string_fields = expected - {
            "plan_version",
            "normalized_parameters",
            "registry_fingerprint",
        }
        if any(
            not isinstance(payload[field], str) or not payload[field]
            for field in string_fields
        ):
            raise ValueError("Resolved snapshot identifiers are invalid")
        return cls(
            task_id=payload["task_id"],
            plan_id=payload["plan_id"],
            plan_version=version,
            step_id=payload["step_id"],
            capability_id=payload["capability_id"],
            resolved_tool_id=payload["resolved_tool_id"],
            resolved_action=payload["resolved_action"],
            normalized_parameters=tuple(sorted(parameters.items())),
            registry_fingerprint=fingerprint,
        )
