from pathlib import Path
import shutil
import subprocess
import tempfile

import pytest
from fastapi.testclient import TestClient

from app.agents.providers.mock import MockLLMProvider
from app.analyst.service import AnalystService
from app.main import app
from app.storage.database import SessionLocal
from app.storage.orm import EvidenceRecord, TaskRecord


@pytest.fixture()
def api_project_path():
    parent = Path(r"D:\VSCodeData\AgentDev\Temp")
    parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="agentforge-analyst-api-", dir=parent))
    subprocess.run(
        ["git", "init", "--quiet", str(root)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def create_project(client: TestClient, root: Path) -> str:
    response = client.post(
        "/projects",
        json={
            "name": f"Analyst API Project {root.name}",
            "workspace_root": str(root),
            "environment": "test",
            "allowed_capability_ids": [
                "project_metadata",
                "repository_state",
                "test_verification",
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def create_terminal_task(client: TestClient, root: Path) -> tuple[str, str]:
    project_id = create_project(client, root)
    task = client.post(
        "/tasks",
        json={
            "title": "Analyst report API task",
            "goal": "Assess report projection",
            "project_id": project_id,
        },
    ).json()
    plan = client.post(f"/tasks/{task['id']}/plan", json={}).json()
    with SessionLocal() as session:
        record = session.get(TaskRecord, task["id"])
        record.status = "SUCCESS"
        session.add(
            EvidenceRecord(
                id="analyst-api-evidence",
                task_id=task["id"],
                summary="API test evidence is persisted.",
                artifact_path="D:/AgentProjectData/AgentForge/test-runs/api-evidence.json",
                content_hash="c" * 64,
            )
        )
        session.commit()
        result = AnalystService(session, MockLLMProvider()).synthesize(
            task_id=task["id"], plan_id=plan["id"], plan_version=plan["version"]
        )
        assert result.report is not None
    return task["id"], plan["id"]


def test_report_api_returns_validated_analyst_report_additively(api_project_path, db_session):
    with TestClient(app) as client:
        task_id, plan_id = create_terminal_task(client, api_project_path)
        response = client.get(f"/tasks/{task_id}/report")

    assert response.status_code == 200
    body = response.json()
    assert body["readiness"] == "PASS"
    assert body["execution_count"] == 0
    assert body["analyst"]["status"] == "SUCCEEDED"
    assert body["analyst"]["report"]["task_id"] == task_id
    assert body["analyst"]["report"]["plan_id"] == plan_id
    assert body["analyst"]["report"]["findings"][0]["evidence_refs"] == [
        "analyst-api-evidence"
    ]
    assert "prompt" not in response.text.lower()
    assert "reasoning" not in response.text.lower()


def test_diagnostics_exposes_analyst_lifecycle_and_report_identity(api_project_path, db_session):
    with TestClient(app) as client:
        task_id, plan_id = create_terminal_task(client, api_project_path)
        response = client.get("/diagnostics")

    assert response.status_code == 200
    analyst = response.json()["analyst"]
    assert analyst["status"] == "SUCCEEDED"
    assert analyst["task_id"] == task_id
    assert analyst["plan_id"] == plan_id
    assert analyst["plan_version"] == 1
    assert analyst["provider"] == "mock"
    assert analyst["model"] == "deterministic-mock"
    assert analyst["artifact_path"]
    assert len(analyst["content_hash"]) == 64
    assert "prompt" not in response.text.lower()
    assert "reasoning" not in response.text.lower()


def test_legacy_task_report_is_readable_without_pretending_analysis(api_project_path, db_session):
    with TestClient(app) as client:
        project_id = create_project(client, api_project_path)
        task = client.post(
            "/tasks",
            json={
                "title": "Legacy report task",
                "goal": "Read historical execution facts",
                "project_id": project_id,
            },
        ).json()
        response = client.get(f"/tasks/{task['id']}/report")

    assert response.status_code == 200
    assert response.json()["analyst"] == {
        "status": "NOT_REQUESTED",
        "report": None,
        "failure_category": None,
        "provider": None,
        "model": None,
        "plan_id": None,
        "plan_version": None,
        "artifact_path": None,
        "content_hash": None,
        "generated_at": None,
    }


def test_tampered_analyst_artifact_is_not_served_as_success(api_project_path, db_session):
    with TestClient(app) as client:
        task_id, _ = create_terminal_task(client, api_project_path)
        with SessionLocal() as session:
            success = AnalystService(session, MockLLMProvider()).get_read_model(task_id)
            assert success.artifact_path
            Path(success.artifact_path).write_text("{}", encoding="utf-8")
        response = client.get(f"/tasks/{task_id}/report")

    assert response.status_code == 200
    assert response.json()["analyst"]["status"] == "FAILED"
    assert response.json()["analyst"]["report"] is None
    assert response.json()["analyst"]["failure_category"] in {
        "ARTIFACT_HASH_MISMATCH",
        "ARTIFACT_INVALID",
    }
