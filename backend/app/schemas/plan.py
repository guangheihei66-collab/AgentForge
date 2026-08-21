"""Planner API contracts."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PlanRequest(BaseModel):
    context: dict[str, Any] = Field(default_factory=dict)


class PlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    version: int
    plan_json: dict[str, Any]
    validation_status: str
