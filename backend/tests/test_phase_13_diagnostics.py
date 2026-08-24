import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.diagnostics.health import classify_overall
from app.identity.service import RuntimeIdentity, _revision
from app.main import app


def test_health_model_is_deterministic():
    assert classify_overall(backend="HEALTHY", database="HEALTHY", provider="HEALTHY") == "HEALTHY"
    assert classify_overall(backend="HEALTHY", database="HEALTHY", provider="UNHEALTHY") == "DEGRADED"
    assert classify_overall(backend="HEALTHY", database="UNHEALTHY", provider="HEALTHY") == "UNHEALTHY"
    assert classify_overall(backend="UNKNOWN", database="HEALTHY", provider="HEALTHY") == "UNKNOWN"


def test_identity_revision_failure_is_safe(monkeypatch):
    monkeypatch.setattr("app.identity.service.subprocess.run", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("no git")))
    assert _revision() is None


def test_identity_contract_has_no_secret_fields():
    value = RuntimeIdentity("AgentForge", "0.1.0-beta.1", None, "beta")
    assert "api_key" not in json.dumps(value.__dict__ if hasattr(value, "__dict__") else {"product": value.product, "version": value.version, "revision": value.revision, "environment": value.environment})


def test_runtime_identity_uses_canonical_beta_version():
    from app.identity.service import get_runtime_identity

    assert get_runtime_identity().version == "0.1.0-beta.2"


def test_diagnostics_endpoint_is_read_only_and_secret_free():
    with TestClient(app) as client:
        response = client.get("/diagnostics")
    assert response.status_code == 200
    payload = response.json()
    serialized = json.dumps(payload)
    assert "api_key" not in serialized.lower()
    assert "authorization" not in serialized.lower()
    assert "SECRET_SENTINEL_DO_NOT_EXPOSE" not in serialized
    assert payload["identity"]["product"] == "AgentForge"


def test_diagnostics_reflects_explicit_provider_success():
    with TestClient(app) as client:
        probe = client.post("/llm/provider/test")
        response = client.get("/diagnostics")
    assert probe.status_code == 200
    assert response.json()["provider"]["connection"] == "SUCCESS"
    assert response.json()["health"]["overall"] == "HEALTHY"
