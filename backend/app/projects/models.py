"""Local Project domain contracts."""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4


class ProjectStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


@dataclass(slots=True)
class Project:
    id: str
    name: str
    description: str | None
    workspace_root: str
    environment: str
    status: ProjectStatus
    allowed_capability_ids: tuple[str, ...]
    config_version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def new(cls, *, name: str, description: str | None, workspace_root: str,
            environment: str, allowed_capability_ids: tuple[str, ...] = ()) -> "Project":
        now = datetime.now(timezone.utc)
        return cls(str(uuid4()), name, description, workspace_root, environment,
                   ProjectStatus.ACTIVE, tuple(sorted(allowed_capability_ids)), 1, now, now)
