"""Approval API contracts."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ApprovalCreate(BaseModel):
    plan_id: str = Field(min_length=1)
    plan_version: int = Field(ge=1)
    requested_by: str = Field(default="system", min_length=1, max_length=200)


class ApprovalDecision(BaseModel):
    actor: str = Field(min_length=1, max_length=200)
    reason: str = Field(default="", max_length=2_000)


class ApproveAndExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_id: str = Field(min_length=36, max_length=36)
    plan_id: str = Field(min_length=36, max_length=36)
    plan_version: int = Field(ge=1)
    actor: str = Field(min_length=1, max_length=200)
    language: Literal["en-US", "zh-CN"] = "en-US"


class ApprovalRead(BaseModel):
    id: str
    task_id: str
    plan_id: str
    plan_version: int
    decision: str
    approver: str
    reason: str | None
    resolved_snapshot: dict[str, Any] | None
    created_at: datetime


class CancelRequest(BaseModel):
    actor: str = Field(min_length=1, max_length=200)
    reason: str = Field(default="", max_length=2_000)
