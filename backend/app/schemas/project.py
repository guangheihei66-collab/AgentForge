"""Project API contracts."""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    workspace_root: str = Field(min_length=1, max_length=1000)
    environment: str = Field(min_length=1, max_length=64)
    allowed_capability_ids: list[str] = Field(default_factory=list, max_length=64)


class ProjectPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_config_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    workspace_root: str | None = Field(default=None, min_length=1, max_length=1000)
    environment: str | None = Field(default=None, min_length=1, max_length=64)
    allowed_capability_ids: list[str] | None = Field(default=None, max_length=64)


class ArchiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_config_version: int = Field(ge=1)


class WorkspaceValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_root: str = Field(min_length=1, max_length=1000)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str | None
    workspace_root: str
    environment: str
    status: str
    allowed_capability_ids: list[str]
    config_version: int
    recent_task_count: int = 0
    created_at: datetime
    updated_at: datetime


class ProjectDetail(ProjectRead):
    recent_tasks: list[dict]
