from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import pytest

from app.analyst.models import AnalystReport
from app.analyst.storage import AnalystArtifactError, AnalystArtifactStore
from tests.test_analyst_models import valid_draft


@pytest.fixture()
def artifact_root():
    parent = Path(r"D:\AgentProjectData\AgentForge\test-runs")
    parent.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="analyst-artifact-", dir=parent))
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def valid_report() -> AnalystReport:
    return AnalystReport.model_validate(
        {
            **valid_draft(),
            "schema_version": 1,
            "task_id": "task-1",
            "plan_id": "plan-1",
            "plan_version": 1,
            "provider": "mock",
            "model": "deterministic-mock",
            "generated_at": datetime.now(timezone.utc),
        }
    )


def test_artifact_store_writes_canonical_report_and_verifies_hash(artifact_root):
    store = AnalystArtifactStore(artifact_root)

    metadata = store.write(valid_report())
    loaded = store.load(
        metadata.path,
        expected_hash=metadata.content_hash,
        task_id="task-1",
        plan_id="plan-1",
        plan_version=1,
    )

    assert metadata.path.is_relative_to(artifact_root.resolve())
    assert metadata.content_hash == hashlib.sha256(metadata.path.read_bytes()).hexdigest()
    assert loaded.task_id == "task-1"
    assert json.loads(metadata.path.read_text(encoding="utf-8"))["schema_version"] == 1


def test_artifact_store_rejects_tampering_and_escape(artifact_root):
    store = AnalystArtifactStore(artifact_root)
    metadata = store.write(valid_report())
    metadata.path.write_text("{}", encoding="utf-8")

    with pytest.raises(AnalystArtifactError, match="ARTIFACT_HASH_MISMATCH"):
        store.load(
            metadata.path,
            expected_hash=metadata.content_hash,
            task_id="task-1",
            plan_id="plan-1",
            plan_version=1,
        )

    with pytest.raises(AnalystArtifactError, match="ARTIFACT_PATH_INVALID"):
        store.load(
            artifact_root.parent / "outside.json",
            expected_hash="a" * 64,
            task_id="task-1",
            plan_id="plan-1",
            plan_version=1,
        )
