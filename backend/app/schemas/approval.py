"""Approval API contracts."""

from datetime import datetime

from pydantic import BaseModel, Field


class ApprovalCreate(BaseModel):
    plan_id: str = Field(min_length=1)
    plan_version: int = Field(ge=1)
    requested_by: str = Field(default="system", min_length=1, max_length=200)


class ApprovalDecision(BaseModel):
    actor: str = Field(min_length=1, max_length=200)
    reason: str = Field(default="", max_length=2_000)


class ApprovalRead(BaseModel):
    id: str
    task_id: str
    plan_id: str
    plan_version: int
    decision: str
    approver: str
    reason: str | None
    created_at: datetime


class CancelRequest(BaseModel):
    actor: str = Field(min_length=1, max_length=200)
    reason: str = Field(default="", max_length=2_000)
