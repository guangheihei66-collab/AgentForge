from fastapi.testclient import TestClient

from app.main import app
from app.storage.database import SessionLocal
from app.storage.orm import AuditEventRecord


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
