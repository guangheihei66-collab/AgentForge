from typing import Literal

from pydantic import BaseModel


HealthState = Literal["HEALTHY", "DEGRADED", "UNHEALTHY", "UNKNOWN"]


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


class DiagnosticsRead(BaseModel):
    identity: RuntimeIdentityRead
    health: HealthRead
    provider: dict[str, object]
    recent_task: RecentTaskRead | None
    command_provenance: CommandProvenanceRead | None = None
    recent_errors: list[str]
