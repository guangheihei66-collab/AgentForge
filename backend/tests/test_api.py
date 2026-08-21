from fastapi.testclient import TestClient

from app.main import app


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
