"""Persistence-independent domain entities for the backend foundation."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..states.task_state import TaskStatus


@dataclass(slots=True)
class Task:
    id: str
    project_id: str | None
    title: str
    goal: str
    workspace: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


@dataclass(slots=True)
class Plan:
    id: str
    task_id: str
    version: int
    plan_json: dict[str, Any]
    validation_status: str
    created_at: datetime


@dataclass(slots=True)
class Approval:
    id: str
    task_id: str
    plan_id: str
    plan_version: int
    decision: str
    approver: str
    reason: str | None
    created_at: datetime


@dataclass(slots=True)
class AuditEvent:
    id: str
    task_id: str
    event_type: str
    actor: str
    payload_summary: str
    correlation_id: str
    created_at: datetime


@dataclass(slots=True)
class Evidence:
    id: str
    task_id: str
    summary: str
    artifact_path: str | None
    content_hash: str | None
    created_at: datetime


@dataclass(slots=True)
class ToolExecution:
    id: str
    task_id: str
    tool_name: str
    action: str
    status: str
    result_summary: str | None
    artifact_path: str | None
    content_hash: str | None
    started_at: datetime
    finished_at: datetime | None
