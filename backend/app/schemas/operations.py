"""Read models for the frontend operations console."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class TaskSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    goal: str
    workspace: str
    status: str
    created_at: datetime
    updated_at: datetime


class ApprovalQueueRead(BaseModel):
    id: str
    task_id: str
    task_title: str
    plan_id: str
    plan_version: int
    decision: str
    requested_by: str
    created_at: datetime
    plan_json: dict[str, Any]


class TaskDetailRead(BaseModel):
    task: TaskSummaryRead
    plans: list[dict[str, Any]]
    approvals: list[dict[str, Any]]
    executions: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    audit: list[dict[str, Any]]


class ReportRead(BaseModel):
    task: TaskSummaryRead
    readiness: str
    summary: str
    completed_steps: int
    failed_steps: int
    evidence: list[dict[str, Any]]
    audit_count: int
    execution_count: int
