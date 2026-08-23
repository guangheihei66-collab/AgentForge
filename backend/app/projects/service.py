"""Project application service and authority derivation."""

from dataclasses import replace
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..capabilities.registry import CapabilityRegistry, build_default_capability_registry
from ..storage.orm import TaskRecord
from ..storage.repositories.project_repository import ProjectRepository
from ..workspace.validator import WorkspaceValidator
from .authority import ProjectAuthoritySnapshot, ProjectExecutionContext, authority_fingerprint
from .models import Project, ProjectStatus


class ProjectConflictError(ValueError):
    pass


class ProjectService:
    def __init__(self, session: Session, capability_registry: CapabilityRegistry | None = None):
        self.session = session
        self.registry = capability_registry or build_default_capability_registry()
        self.projects = ProjectRepository(session)

    def create(self, *, name: str, description: str | None, workspace_root: str,
               environment: str, allowed_capability_ids: tuple[str, ...] = ()) -> Project:
        root = str(WorkspaceValidator.canonicalize_project_root(workspace_root))
        policy = self._policy(allowed_capability_ids)
        self._assert_unique_active_root(root)
        project = self.projects.create(Project.new(
            name=name.strip(), description=description, workspace_root=root,
            environment=environment.strip(), allowed_capability_ids=policy,
        ))
        self.session.commit()
        return project

    def get(self, project_id: str) -> Project | None:
        return self.projects.get(project_id)

    def list(self) -> list[Project]:
        return self.projects.list()

    def update(self, project_id: str, *, expected_config_version: int,
               name: str | None = None, description: str | None = None,
               workspace_root: str | None = None, environment: str | None = None,
               allowed_capability_ids: tuple[str, ...] | None = None) -> Project:
        current = self.projects.get(project_id)
        if current is None:
            raise LookupError(f"Project not found: {project_id}")
        if current.config_version != expected_config_version:
            raise ProjectConflictError("Project config version is stale")
        root = current.workspace_root if workspace_root is None else str(WorkspaceValidator.canonicalize_project_root(workspace_root))
        self._assert_unique_active_root(root, exclude_project_id=current.id)
        policy = current.allowed_capability_ids if allowed_capability_ids is None else self._policy(allowed_capability_ids)
        security_changed = (WorkspaceValidator.authority_path_key(root) != WorkspaceValidator.authority_path_key(current.workspace_root) or policy != current.allowed_capability_ids)
        updated = replace(current, name=current.name if name is None else name.strip(),
                          description=current.description if description is None else description,
                          environment=current.environment if environment is None else environment.strip(),
                          workspace_root=root, allowed_capability_ids=policy,
                          config_version=current.config_version + int(security_changed),
                          updated_at=datetime.now(timezone.utc))
        result = self.projects.update(updated)
        self.session.commit()
        return result

    def archive(self, project_id: str, *, expected_config_version: int) -> Project:
        current = self.projects.get(project_id)
        if current is None:
            raise LookupError(f"Project not found: {project_id}")
        if current.config_version != expected_config_version:
            raise ProjectConflictError("Project config version is stale")
        if current.status is ProjectStatus.ARCHIVED:
            raise ProjectConflictError("Project is already archived")
        result = self.projects.update(replace(current, status=ProjectStatus.ARCHIVED,
            config_version=current.config_version + 1, updated_at=datetime.now(timezone.utc)))
        self.session.commit()
        return result

    def execution_context(self, project_id: str) -> ProjectExecutionContext:
        project = self.projects.get(project_id)
        if project is None:
            raise LookupError(f"Project not found: {project_id}")
        if project.status is not ProjectStatus.ACTIVE:
            raise PermissionError("Archived Project cannot execute")
        root = str(WorkspaceValidator.canonicalize_project_root(project.workspace_root))
        policy = self._policy(project.allowed_capability_ids)
        return ProjectExecutionContext(project.id, project.config_version, root,
            WorkspaceValidator.authority_path_key(root), policy, project.status,
            authority_fingerprint(project))

    def execution_context_for_task(self, task_id: str) -> ProjectExecutionContext:
        task = self.session.get(TaskRecord, task_id)
        if task is None:
            raise LookupError(f"Task not found: {task_id}")
        if not task.project_id:
            raise PermissionError("Legacy Task has no Project execution authority")
        return self.execution_context(task.project_id)

    def assert_authority(self, task_project_id: str | None, raw: dict) -> ProjectExecutionContext:
        if not task_project_id:
            raise PermissionError("Task has no Project execution authority")
        approved = ProjectAuthoritySnapshot.from_dict(raw)
        current = self.execution_context(task_project_id)
        if approved != current.authority_snapshot():
            raise PermissionError("Project execution authority has drifted")
        return current

    def _policy(self, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) > 64 or len(set(values)) != len(values):
            raise ValueError("Project capability policy is invalid")
        for value in values:
            if not isinstance(value, str) or len(value) > 128:
                raise ValueError("Project capability policy is invalid")
            try:
                self.registry.require(value)
            except LookupError as exc:
                raise ValueError(f"Unknown Project capability: {value}") from exc
        return tuple(sorted(values))

    def _assert_unique_active_root(
        self, root: str, *, exclude_project_id: str | None = None
    ) -> None:
        key = WorkspaceValidator.authority_path_key(root)
        for existing in self.projects.list():
            if (
                existing.id != exclude_project_id
                and existing.status is ProjectStatus.ACTIVE
                and WorkspaceValidator.authority_path_key(existing.workspace_root) == key
            ):
                raise ProjectConflictError(
                    "An active Project already uses this workspace"
                )
