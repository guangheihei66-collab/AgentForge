from fastapi.testclient import TestClient

from app.main import app
from app.storage.database import SessionLocal
from app.storage.orm import AuditEventRecord


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


def test_create_task_endpoint():
    with TestClient(app) as client:
        response = client.post(
            "/tasks",
            json={
                "title": "Release v2.0 verification",
                "goal": "Check release readiness",
                "workspace": "fixture-repository",
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Release v2.0 verification"
    assert body["status"] == "CREATED"
    assert body["id"]


def test_audit_query_endpoint():
    with TestClient(app) as client:
        response = client.post(
            "/tasks",
            json={
                "title": "Audit query task",
                "goal": "Verify audit retrieval",
                "workspace": "fixture-repository",
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


def test_create_plan_endpoint():
    with TestClient(app) as client:
        task_response = client.post(
            "/tasks",
            json={
                "title": "Planner API task",
                "goal": "Check release readiness",
                "workspace": r"D:\AgentProjects\AgentForge",
            },
        )
        task_id = task_response.json()["id"]
        response = client.post(f"/tasks/{task_id}/plan", json={"context": {"release": "2.0"}})

    assert response.status_code == 201
    assert response.json()["validation_status"] == "VALID"
    assert response.json()["plan_json"]["steps"][0]["capability_id"] == "repository_state"
    assert response.json()["plan_json"]["resolved_steps"][0]["resolved_tool_id"] == "git_read"


def test_operations_read_endpoints_expose_console_data():
    with TestClient(app) as client:
        task_response = client.post(
            "/tasks",
            json={
                "title": "Operations API task",
                "goal": "Verify console read models",
                "workspace": r"D:\AgentProjects\AgentForge",
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
