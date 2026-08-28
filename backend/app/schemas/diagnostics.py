from datetime import datetime
from typing import Literal

from pydantic import BaseModel


HealthState = Literal["HEALTHY", "DEGRADED", "UNHEALTHY", "UNKNOWN"]
AnalystStatus = Literal["NOT_REQUESTED", "PENDING", "GENERATING", "SUCCEEDED", "FAILED"]
AnalystSynthesisMode = Literal["REAL", "MOCK", "FAILED", "NOT_REQUESTED"]


class RuntimeIdentityRead(BaseModel):
    product: str
    version: str
    revision: str | None
    environment: str


class HealthRead(BaseModel):
    overall: HealthState
    backend: HealthState
    database: HealthState
    provider: HealthState


class ExecutionCountsRead(BaseModel):
    total: int
    success: int
    failed: int
    rejected: int


class RecentTaskRead(BaseModel):
    id: str
    state: str
    plan_version: int | None
    approval: str | None
    executions: ExecutionCountsRead
    evidence_count: int
    observation_count: int
    replan_count: int


class CommandProvenanceRead(BaseModel):
    command_kind: str
    task_id: str
    task_state: str
    plan_id: str | None
    plan_version: int | None
    approval_id: str | None
    approval_state: str | None
    authority_validation: str | None
    approval_persistence: str | None
    execution_initiation: Literal["NOT_REQUESTED", "REQUESTED", "STARTED", "FAILED"]
    last_checkpoint: str
    correlation_id: str
    failure_category: str | None


class AnalystDiagnosticsRead(BaseModel):
    status: AnalystStatus
    synthesis_mode: AnalystSynthesisMode = "NOT_REQUESTED"
    task_id: str | None = None
    plan_id: str | None = None
    plan_version: int | None = None
    provider: str | None = None
    model: str | None = None
    artifact_path: str | None = None
    content_hash: str | None = None
    generated_at: datetime | None = None
    failure_category: str | None = None


class DiagnosticsRead(BaseModel):
    identity: RuntimeIdentityRead
    health: HealthRead
    provider: dict[str, object]
    recent_task: RecentTaskRead | None
    analyst: AnalystDiagnosticsRead
    planner_provider: str | None = None
    planner_model: str | None = None
    analyst_provider: str | None = None
    analyst_model: str | None = None
    analyst_synthesis_mode: AnalystSynthesisMode = "NOT_REQUESTED"
    command_provenance: CommandProvenanceRead | None = None
    recent_errors: list[str]
