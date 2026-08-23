from pathlib import Path
import shutil
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect

from app.capabilities.registry import build_default_capability_registry
from app.projects.models import Project, ProjectStatus
from app.storage.database import Base
from app.storage.migrations import migrate_sqlite_schema
from app.storage.repositories.project_repository import ProjectRepository


@pytest.fixture()
def local_project_root():
    root = Path(r"D:\VSCodeData\AgentDev\Temp") / f"agentforge-phase14-{uuid4()}"
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        shutil.rmtree(root)


def test_project_persistence_defaults_to_empty_capability_policy(db_session, tmp_path):
    workspace = tmp_path / "project-a"
    workspace.mkdir()
    project = Project.new(
        name="Project A",
        description=None,
        workspace_root=str(workspace),
        environment="development",
        allowed_capability_ids=(),
    )

    created = ProjectRepository(db_session).create(project)

    assert created.status is ProjectStatus.ACTIVE
    assert created.allowed_capability_ids == ()
    assert created.config_version == 1
    persisted = ProjectRepository(db_session).get(created.id)
    assert persisted is not None
    assert persisted.id == created.id
    assert persisted.workspace_root == created.workspace_root


def test_sqlite_migration_adds_nullable_project_id_without_rewriting_task(tmp_path):
    database = tmp_path / "legacy.sqlite3"
    engine = create_engine(f"sqlite+pysqlite:///{database.as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE tasks (id VARCHAR(36) PRIMARY KEY, title VARCHAR(200) NOT NULL, "
            "goal TEXT NOT NULL, workspace VARCHAR(500) NOT NULL, status VARCHAR(32) NOT NULL, "
            "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, completed_at DATETIME)"
        )
        connection.exec_driver_sql(
            "INSERT INTO tasks (id,title,goal,workspace,status,created_at,updated_at) "
            "VALUES ('legacy-task','Legacy','Read history','D:/Legacy','SUCCESS',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
        )
    Base.metadata.create_all(engine)

    migrate_sqlite_schema(engine)
    migrate_sqlite_schema(engine)

    assert "projects" in inspect(engine).get_table_names()
    assert "project_id" in {c["name"] for c in inspect(engine).get_columns("tasks")}
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT id, project_id FROM tasks WHERE id='legacy-task'"
        ).one() == ("legacy-task", None)


def test_capability_subset_is_explicit_and_future_default_deny():
    registry = build_default_capability_registry()
    subset = registry.subset(("repository_state",))

    assert subset.ids() == ("repository_state",)
    assert "test_verification" not in subset.ids()


def test_workspace_validator_rejects_relative_unc_and_sibling(local_project_root):
    from app.workspace.validator import WorkspaceValidationError, WorkspaceValidator

    root = local_project_root / "App"
    sibling = local_project_root / "App-Other"
    root.mkdir(); sibling.mkdir()
    validator = WorkspaceValidator.for_project(root)
    with pytest.raises(WorkspaceValidationError):
        WorkspaceValidator.canonicalize_project_root("relative/path")
    with pytest.raises(WorkspaceValidationError):
        WorkspaceValidator.canonicalize_project_root(r"\\server\share")
    with pytest.raises(WorkspaceValidationError):
        validator.validate_target(root, sibling)


def test_project_authority_changes_only_for_execution_configuration(db_session, local_project_root):
    from app.projects.service import ProjectService

    workspace = local_project_root / "authority-project"
    workspace.mkdir()
    service = ProjectService(db_session)
    project = service.create(
        name="Authority", description=None, workspace_root=str(workspace),
        environment="development", allowed_capability_ids=("repository_state",),
    )
    before = service.execution_context(project.id)
    cosmetic = service.update(
        project.id, expected_config_version=1, name="Renamed",
        description="Cosmetic", environment="test",
    )
    after_cosmetic = service.execution_context(project.id)
    assert cosmetic.config_version == 1
    assert after_cosmetic.authority_fingerprint == before.authority_fingerprint

    changed = service.update(
        project.id, expected_config_version=1,
        allowed_capability_ids=("repository_state", "project_metadata"),
    )
    assert changed.config_version == 2
    assert service.execution_context(project.id).authority_fingerprint != before.authority_fingerprint


def test_project_policy_rejects_unknown_and_duplicate_capabilities(db_session, local_project_root):
    from app.projects.service import ProjectService

    workspace = local_project_root / "policy-project"
    workspace.mkdir()
    service = ProjectService(db_session)
    with pytest.raises(ValueError):
        service.create(name="Bad", description=None, workspace_root=str(workspace),
                       environment="development", allowed_capability_ids=("unknown",))
    with pytest.raises(ValueError):
        service.create(name="Bad", description=None, workspace_root=str(workspace),
                       environment="development",
                       allowed_capability_ids=("repository_state", "repository_state"))
