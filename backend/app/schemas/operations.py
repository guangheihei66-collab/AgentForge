"""Read models for the frontend operations console."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from ..analyst.models import AnalystReport


class TaskSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None
    title: str
    goal: str
    workspace: str
    status: str
    created_at: datetime
    updated_at: datetime


class ApprovalQueueRead(BaseModel):
    id: str
    approval_id: str | None = None
    task_id: str
    task_title: str
    plan_id: str
    plan_version: int
    decision: str
    requested_by: str
    created_at: datetime
    plan_json: dict[str, Any]
    resolved_snapshot: dict[str, Any] | None


class TaskDetailRead(BaseModel):
    task: TaskSummaryRead
    plans: list[dict[str, Any]]
    approvals: list[dict[str, Any]]
    executions: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    audit: list[dict[str, Any]]


class AnalystSynthesisRead(BaseModel):
    status: str
    report: AnalystReport | None = None
    failure_category: str | None = None
    provider: str | None = None
    model: str | None = None
    plan_id: str | None = None
    plan_version: int | None = None
    artifact_path: str | None = None
    content_hash: str | None = None
    generated_at: datetime | None = None


class ReportRead(BaseModel):
    task: TaskSummaryRead
    readiness: str
    summary: str
    completed_steps: int
    failed_steps: int
    rejected_steps: int
    evidence: list[dict[str, Any]]
    audit_count: int
    execution_count: int
    analyst: AnalystSynthesisRead


class ReconciliationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str


class ReconciliationEligibilityRead(BaseModel):
    task_id: str
    eligible: bool
    reason_code: str


class ReconciliationResultRead(BaseModel):
    task_id: str
    previous_state: str
    final_state: str
    reconciled: bool
    eligible: bool
    reason_code: str
