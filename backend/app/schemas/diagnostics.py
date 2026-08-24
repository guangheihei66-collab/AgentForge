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


class DiagnosticsRead(BaseModel):
    identity: RuntimeIdentityRead
    health: HealthRead
    provider: dict[str, object]
    recent_task: RecentTaskRead | None
    recent_errors: list[str]
