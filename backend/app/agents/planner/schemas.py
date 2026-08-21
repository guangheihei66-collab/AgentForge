"""Strict plan contract accepted from an LLM provider."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...permissions.levels import PermissionLevel


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1, max_length=64)
    tool: Literal["git_read", "file_read", "test_run"]
    action: str = Field(min_length=1, max_length=100)
    risk_level: Literal["low", "medium"]
    permission_level: PermissionLevel

    @field_validator("permission_level", mode="before")
    @classmethod
    def normalize_permission(cls, value: str | PermissionLevel) -> PermissionLevel:
        if isinstance(value, str):
            return PermissionLevel(value.upper())
        return value


class PlanContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: list[PlanStep] = Field(min_length=1, max_length=20)
