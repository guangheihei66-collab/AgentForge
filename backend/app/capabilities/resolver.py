"""Deterministic capability-to-tool resolution."""

import hashlib
import hmac
import json
from typing import Any, Mapping

from ..tools.models import ToolDefinition
from ..tools.registry import ToolRegistry
from .models import (
    CapabilityDefinition,
    CapabilityRequest,
    ResolvedExecutionSnapshot,
)
from .registry import CapabilityRegistry


class CapabilityResolutionError(ValueError):
    """Resolution failed without selecting an executable tool."""


def registry_fingerprint(
    capability: CapabilityDefinition, tool: ToolDefinition
) -> str:
    payload = {
        "capability_id": capability.id,
        "candidate_tool_ids": sorted(capability.candidate_tool_ids),
        "resolved_tool_id": tool.name,
        "resolved_action": capability.action,
        "enabled": tool.enabled,
        "permission_level": tool.permission_level.value,
        "risk_level": tool.risk_level,
        "allowed_actions": sorted(tool.allowed_actions),
        "parameter_schema": [
            {
                "name": field.name,
                "required": field.required,
                "allowed_values": sorted(field.allowed_values),
                "default": field.default,
            }
            for field in sorted(
                capability.parameter_schema, key=lambda item: item.name
            )
        ],
        "execution_contract_version": tool.execution_contract_version,
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class CapabilityResolver:
    def __init__(
        self, capabilities: CapabilityRegistry, tools: ToolRegistry
    ) -> None:
        self.capabilities = capabilities
        self.tools = tools

    def resolve(
        self,
        *,
        task_id: str,
        plan_id: str,
        plan_version: int,
        step_id: str,
        request: CapabilityRequest,
    ) -> ResolvedExecutionSnapshot:
        capability = self.capabilities.require(request.capability_id)
        normalized = self._normalize(capability, request.parameters)
        candidates = self._valid_candidates(capability)
        if len(candidates) != 1:
            raise CapabilityResolutionError(
                f"Capability {capability.id} requires exactly one valid candidate; "
                f"found {len(candidates)}"
            )
        tool = candidates[0]
        return ResolvedExecutionSnapshot(
            task_id=task_id,
            plan_id=plan_id,
            plan_version=plan_version,
            step_id=step_id,
            capability_id=capability.id,
            resolved_tool_id=tool.name,
            resolved_action=capability.action,
            normalized_parameters=normalized,
            registry_fingerprint=registry_fingerprint(capability, tool),
        )

    def normalize(
        self, request: CapabilityRequest
    ) -> tuple[tuple[str, str], ...]:
        """Return application-owned canonical parameters without selecting a tool."""
        capability = self.capabilities.require(request.capability_id)
        return self._normalize(capability, request.parameters)

    def verify(self, snapshot: ResolvedExecutionSnapshot) -> None:
        capability = self.capabilities.require(snapshot.capability_id)
        if snapshot.resolved_tool_id not in capability.candidate_tool_ids:
            raise CapabilityResolutionError("Resolved tool is not mapped to capability")
        tool = self.tools.get(snapshot.resolved_tool_id)
        if tool is None or not tool.enabled:
            raise CapabilityResolutionError("Resolved tool is unavailable")
        self._validate_selected_tool(capability, tool)
        if capability.action != snapshot.resolved_action:
            raise CapabilityResolutionError("Resolved action changed")
        normalized = self._normalize(capability, snapshot.parameters_dict())
        if normalized != snapshot.normalized_parameters:
            raise CapabilityResolutionError("Resolved parameters changed")
        actual = registry_fingerprint(capability, tool)
        if not hmac.compare_digest(actual, snapshot.registry_fingerprint):
            raise CapabilityResolutionError("Registry fingerprint changed")

    def _valid_candidates(
        self, capability: CapabilityDefinition
    ) -> list[ToolDefinition]:
        candidates: list[ToolDefinition] = []
        for tool_id in capability.candidate_tool_ids:
            tool = self.tools.get(tool_id)
            if tool is None or not tool.enabled:
                continue
            try:
                self._validate_selected_tool(capability, tool)
            except CapabilityResolutionError:
                continue
            candidates.append(tool)
        return candidates

    @staticmethod
    def _validate_selected_tool(
        capability: CapabilityDefinition, tool: ToolDefinition
    ) -> None:
        if tool.permission_level != capability.required_permission:
            raise CapabilityResolutionError("Tool permission is incompatible")
        if capability.action not in tool.allowed_actions:
            raise CapabilityResolutionError("Tool action is incompatible")

    @staticmethod
    def _normalize(
        capability: CapabilityDefinition, parameters: Mapping[str, Any]
    ) -> tuple[tuple[str, str], ...]:
        schema = {field.name: field for field in capability.parameter_schema}
        unknown = set(parameters) - set(schema)
        if unknown:
            raise CapabilityResolutionError("Capability parameters contain unknown keys")
        normalized: dict[str, str] = {}
        for name, field in schema.items():
            value = parameters.get(name, field.default)
            if value is None:
                if field.required:
                    raise CapabilityResolutionError(
                        f"Capability parameter is required: {name}"
                    )
                continue
            if not isinstance(value, str) or value not in field.allowed_values:
                raise CapabilityResolutionError(
                    f"Capability parameter is invalid: {name}"
                )
            normalized[name] = value
        return tuple(sorted(normalized.items()))
