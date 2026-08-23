"""Bounded capability-only prompt construction for replanning."""

import json
from dataclasses import asdict

from ...capabilities.registry import CapabilityRegistry
from .models import MAX_CONTEXT_BYTES, MAX_PROMPT_BYTES, ReplanContext


def build_replan_prompt(
    context: ReplanContext, capability_registry: CapabilityRegistry
) -> str:
    context_payload = asdict(context)
    context_json = json.dumps(
        context_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        default=str,
    )
    if len(context_json.encode("utf-8")) > MAX_CONTEXT_BYTES:
        raise ValueError("Replan context exceeds the size limit")
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
    prompt = (
        "Revise only the remaining capability plan. Return decision_summary and "
        "revised_remaining_steps containing only step_id, capability_id, and bounded "
        "parameters. Never return tools, commands, permissions, approvals, workspace "
        "overrides, execution instructions, or hidden reasoning.\n"
        f"Capability catalog: {catalog_json}\nReplan context: {context_json}"
    )
    if len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
        raise ValueError("Replan prompt exceeds the size limit")
    return prompt
