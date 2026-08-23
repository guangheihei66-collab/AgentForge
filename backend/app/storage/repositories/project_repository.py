"""Project persistence operations."""

from sqlalchemy.orm import Session

from ...projects.models import Project, ProjectStatus
from ..orm import ProjectRecord


def to_domain(record: ProjectRecord) -> Project:
    return Project(record.id, record.name, record.description, record.workspace_root,
                   record.environment, ProjectStatus(record.status),
                   tuple(record.allowed_capability_ids), record.config_version,
                   record.created_at, record.updated_at)


class ProjectRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, project: Project) -> Project:
        record = ProjectRecord(
            id=project.id, name=project.name, description=project.description,
            workspace_root=project.workspace_root, environment=project.environment,
            status=project.status.value,
            allowed_capability_ids=list(project.allowed_capability_ids),
            config_version=project.config_version, created_at=project.created_at,
            updated_at=project.updated_at,
        )
        self.session.add(record)
        self.session.flush()
        return to_domain(record)

    def get(self, project_id: str) -> Project | None:
        record = self.session.get(ProjectRecord, project_id)
        return to_domain(record) if record else None

    def list(self) -> list[Project]:
        return [to_domain(r) for r in self.session.query(ProjectRecord).order_by(ProjectRecord.created_at.desc()).all()]

    def update(self, project: Project) -> Project:
        record = self.session.get(ProjectRecord, project.id)
        if record is None:
            raise LookupError(f"Project not found: {project.id}")
        record.name = project.name
        record.description = project.description
        record.workspace_root = project.workspace_root
        record.environment = project.environment
        record.status = project.status.value
        record.allowed_capability_ids = list(project.allowed_capability_ids)
        record.config_version = project.config_version
        record.updated_at = project.updated_at
        self.session.flush()
        return to_domain(record)
