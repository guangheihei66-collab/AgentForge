"""Shared test configuration using an in-memory SQLite database."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

os.environ.setdefault("AGENTFORGE_DATABASE_URL", "sqlite+pysqlite:///:memory:")

import pytest

from app.storage.database import Base, SessionLocal, engine, init_db


@pytest.fixture()
def db_session():
    init_db()
    with SessionLocal() as session:
        created_roots: list[Path] = []

        def project_factory():
            existing = session.info.get("phase14_test_project")
            if existing is not None:
                return existing
            temp_parent = Path(r"D:\VSCodeData\AgentDev\Temp")
            temp_parent.mkdir(parents=True, exist_ok=True)
            root = Path(tempfile.mkdtemp(prefix="agentforge-test-project-", dir=temp_parent))
            created_roots.append(root)
            artifact_parent = Path(r"D:\AgentProjectData\AgentForge\test-runs")
            artifact_parent.mkdir(parents=True, exist_ok=True)
            artifact_root = Path(tempfile.mkdtemp(prefix="phase14-regression-", dir=artifact_parent))
            created_roots.append(artifact_root)
            subprocess.run(
                ["git", "init", "--quiet", str(root)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            (root / "PROJECT_CONTEXT.md").write_text("# Tiny test Project\n", encoding="utf-8")
            from app.projects.service import ProjectService

            project = ProjectService(session).create(
                name="Isolated test Project",
                description="Tiny deterministic test workspace",
                workspace_root=str(root),
                environment="test",
                allowed_capability_ids=(
                    "project_metadata", "repository_state", "test_verification"
                ),
            )
            session.info["phase14_test_project"] = project
            session.info["phase14_test_workspace"] = str(root)
            session.info["phase14_test_artifacts"] = str(artifact_root)
            return project

        session.info["phase14_test_project_factory"] = project_factory
        yield session
        for root in created_roots:
            shutil.rmtree(root, ignore_errors=True)
    Base.metadata.drop_all(bind=engine)
