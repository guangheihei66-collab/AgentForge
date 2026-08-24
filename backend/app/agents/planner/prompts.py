"""Bounded prompt construction kept separate from planning orchestration."""

import json
from typing import Any

from ...capabilities.registry import CapabilityRegistry


MAX_PLANNING_CONTEXT_BYTES = 4096


def build_planning_prompt(
    goal: str,
    capability_registry: CapabilityRegistry,
    context: dict[str, Any] | None = None,
) -> str:
    try:
        context_json = json.dumps(
            context or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Planning context is not JSON serializable") from exc
    if len(context_json.encode("utf-8")) > MAX_PLANNING_CONTEXT_BYTES:
        raise ValueError("Planning context exceeds the size limit")
    catalog = []
    for capability_id in capability_registry.ids():
        definition = capability_registry.require(capability_id)
        catalog.append(
            {
                "capability_id": definition.id,
                "description": definition.description,
                "parameters": [
                    {
                        "name": field.name,
                        "required": field.required,
                        "allowed_values": list(field.allowed_values),
                    }
                    for field in definition.parameter_schema
                ],
            }
        )
    catalog_json = json.dumps(
        catalog, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return (
        "Create a minimal JSON capability plan for the user goal. Return only "
        "schema_version, a concise summary, and 1-20 steps containing only "
        "step_id, capability_id, and bounded parameters from the catalog. "
        "schema_version must be the integer 2. steps must contain 1-20 objects. "
        "step_id must be a non-empty string. "
        "Never select a concrete tool, command, permission, approval, workspace, "
        "executable path, or filesystem path. Do not provide hidden reasoning.\n"
        "For project_metadata steps, relative_path must be one of the paths in "
        "the application-owned metadata_manifest. Never invent a metadata path.\n"
        f"Capability catalog: {catalog_json}\n"
        f"Goal: {goal}\nContext: {context_json}"
    )
