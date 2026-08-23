"""Strict capability-first plan contracts accepted from an LLM provider."""

from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field


class CapabilityPlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1, max_length=64)
    capability_id: Literal[
        "repository_state", "project_metadata", "test_verification"
    ]
    parameters: dict[str, str] = Field(default_factory=dict)


class PlanContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2]
    summary: str = Field(default="", max_length=500)
    steps: list[CapabilityPlanStep] = Field(min_length=1, max_length=20)


class LegacyPlanContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    executable: Literal[False] = False
    steps: list[dict[str, Any]]


def parse_plan_for_display(
    payload: Mapping[str, Any],
) -> PlanContract | LegacyPlanContract:
    """Read new or legacy plans without granting legacy execution authority."""

    if payload.get("schema_version") == 2:
        return PlanContract.model_validate(payload)
    steps = payload.get("steps")
    if not isinstance(steps, list):
        raise ValueError("Persisted plan has no readable steps")
    return LegacyPlanContract(steps=steps)
