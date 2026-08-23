"""Small Project-bound helpers for pre-Phase-14 regression fixtures."""

from app.projects.service import ProjectService
from app.services.task_service import TaskService


def project_fixture(session):
    return session.info["phase14_test_project_factory"]()


def project_context(session):
    return ProjectService(session).execution_context(project_fixture(session).id)


def project_workspace(session) -> str:
    return project_context(session).workspace_root


def artifact_root(session) -> str:
    project_fixture(session)
    return session.info["phase14_test_artifacts"]


def create_project_task(session, *, title: str, goal: str):
    return TaskService(session).create_task(
        project_id=project_fixture(session).id,
        title=title,
        goal=goal,
    )


def with_project_authority(session, task, plan_json: dict) -> dict:
    context = ProjectService(session).execution_context_for_task(task.id)
    return {**plan_json, "project_authority": context.authority_snapshot().to_dict()}
