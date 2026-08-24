from fastapi.testclient import TestClient
from pathlib import Path
import shutil
import subprocess
import tempfile

import pytest

from app.main import app
from app.storage.database import SessionLocal
from app.storage.orm import AuditEventRecord


@pytest.fixture()
def api_project_path():
    parent = Path(r"D:\VSCodeData\AgentDev\Temp")
    parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="agentforge-api-project-", dir=parent))
    subprocess.run(["git", "init", "--quiet", str(root)], check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    yield root
    shutil.rmtree(root, ignore_errors=True)


def create_api_project(client: TestClient, root: Path) -> str:
    response = client.post("/projects", json={
        "name": f"API Project {root.name}",
        "workspace_root": str(root),
        "environment": "test",
        "allowed_capability_ids": [
            "project_metadata", "repository_state", "test_verification"
        ],
    })
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_endpoint():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "name": "AgentForge",
        "service": "AI Agent Operations Platform",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
    }


def test_local_frontend_origin_is_allowed():
    with TestClient(app) as client:
        response = client.get(
            "/health",
            headers={"Origin": "http://localhost:5173"},
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_create_task_endpoint(api_project_path):
    with TestClient(app) as client:
        project_id = create_api_project(client, api_project_path)
        response = client.post(
            "/tasks",
            json={
                "title": "Release v2.0 verification",
                "goal": "Check release readiness",
                "project_id": project_id,
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Release v2.0 verification"
    assert body["status"] == "CREATED"
    assert body["id"]


def test_audit_query_endpoint(api_project_path):
    with TestClient(app) as client:
        project_id = create_api_project(client, api_project_path)
        response = client.post(
            "/tasks",
            json={
                "title": "Audit query task",
                "goal": "Verify audit retrieval",
                "project_id": project_id,
            },
        )
        task_id = response.json()["id"]
        with SessionLocal() as session:
            session.add(
                AuditEventRecord(
                    task_id=task_id,
                    event_type="APPROVAL_CREATED",
                    actor="tester",
                    payload_summary='{"plan_version": 1}',
                    correlation_id="audit-test",
                )
            )
            session.commit()
        audit = client.get(f"/tasks/{task_id}/audit")

    assert audit.status_code == 200
    assert any(event["event_type"] == "APPROVAL_CREATED" for event in audit.json())


def test_create_plan_endpoint(api_project_path):
    with TestClient(app) as client:
        project_id = create_api_project(client, api_project_path)
        task_response = client.post(
            "/tasks",
            json={
                "title": "Planner API task",
                "goal": "Check release readiness",
                "project_id": project_id,
            },
        )
        task_id = task_response.json()["id"]
        response = client.post(f"/tasks/{task_id}/plan", json={"context": {"release": "2.0"}})

    assert response.status_code == 201
    assert response.json()["validation_status"] == "VALID"
    assert response.json()["plan_json"]["steps"][0]["capability_id"] == "repository_state"
    assert response.json()["plan_json"]["resolved_steps"][0]["resolved_tool_id"] == "git_read"


def test_operations_read_endpoints_expose_console_data(api_project_path):
    with TestClient(app) as client:
        project_id = create_api_project(client, api_project_path)
        task_response = client.post(
            "/tasks",
            json={
                "title": "Operations API task",
                "goal": "Verify console read models",
                "project_id": project_id,
            },
        )
        task_id = task_response.json()["id"]
        plan = client.post(f"/tasks/{task_id}/plan", json={}).json()
        approval = client.post(
            f"/tasks/{task_id}/approval",
            json={"plan_id": plan["id"], "plan_version": plan["version"], "requested_by": "test"},
        )

        tasks = client.get("/tasks")
        pending = client.get("/approvals/pending")
        detail = client.get(f"/tasks/{task_id}/detail")
        report = client.get(f"/tasks/{task_id}/report")

    assert approval.status_code == 201
    assert any(item["id"] == task_id for item in tasks.json())
    assert pending.json()[0]["task_id"] == task_id
    assert detail.json()["task"]["id"] == task_id
    assert report.json()["readiness"] == "PENDING"


def test_execute_endpoint_runs_only_an_approved_plan(api_project_path):
    with TestClient(app) as client:
        project_id = create_api_project(client, api_project_path)
        task = client.post(
            "/tasks",
            json={
                "title": "Runtime API task",
                "goal": "Exercise the approved runtime path",
                "project_id": project_id,
            },
        ).json()
        plan = client.post(f"/tasks/{task['id']}/plan", json={}).json()
        approval = client.post(
            f"/tasks/{task['id']}/approval",
            json={"plan_id": plan["id"], "plan_version": 1, "requested_by": "test"},
        ).json()
        approved = client.post(
            f"/approvals/{approval['id']}/approve",
            json={"actor": "operator"},
        )
        response = client.post(f"/tasks/{task['id']}/execute")

    assert approved.status_code == 200
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"] == "COMPLETE"
    assert body["state"] == "COMPLETED"
    assert body["completed_steps"] == len(plan["plan_json"]["steps"])
