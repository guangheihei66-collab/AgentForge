"""Deterministic Project execution authority."""

from dataclasses import dataclass
import hashlib
import json

from .models import Project, ProjectStatus
from ..workspace.validator import WorkspaceValidator


@dataclass(frozen=True, slots=True)
class ProjectAuthoritySnapshot:
    project_id: str
    config_version: int
    authority_fingerprint: str
    canonical_workspace_root: str

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "config_version": self.config_version,
            "authority_fingerprint": self.authority_fingerprint,
            "canonical_workspace_root": self.canonical_workspace_root,
        }

    @classmethod
    def from_dict(cls, value: dict) -> "ProjectAuthoritySnapshot":
        if set(value) != {"project_id", "config_version", "authority_fingerprint", "canonical_workspace_root"}:
            raise ValueError("Project authority fields are invalid")
        return cls(**value)


@dataclass(frozen=True, slots=True)
class ProjectExecutionContext:
    project_id: str
    config_version: int
    workspace_root: str
    workspace_authority_key: str
    allowed_capability_ids: tuple[str, ...]
    status: ProjectStatus
    authority_fingerprint: str

    def authority_snapshot(self) -> ProjectAuthoritySnapshot:
        return ProjectAuthoritySnapshot(self.project_id, self.config_version,
                                        self.authority_fingerprint,
                                        self.workspace_authority_key)


def authority_fingerprint(project: Project) -> str:
    document = {
        "authority_schema_version": 1,
        "project_id": project.id,
        "config_version": project.config_version,
        "workspace_root": WorkspaceValidator.authority_path_key(project.workspace_root),
        "allowed_capability_ids": sorted(project.allowed_capability_ids),
        "status": project.status.value,
    }
    payload = json.dumps(document, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
