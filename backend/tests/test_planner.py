import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.agents.planner.planner import PlannerAgent
from app.metadata_manifest import build_metadata_manifest
from app.agents.planner.validator import PlanValidationError, PlanValidator
from app.agents.providers.base import LLMRequest, LLMResponse
from app.agents.providers.mock import MockLLMProvider
from app.domain.states.task_state import TaskStatus
from app.services.task_service import TaskService
from app.storage.orm import AuditEventRecord, PlanRecord, TaskRecord
from app.workspace.validator import WorkspaceValidator
from tests.project_test_support import create_project_task


REPO_ROOT = r"D:\AgentProjects\AgentForge"


def make_task(session):
    return create_project_task(session,
        title="Planner test",
        goal="Check release readiness",
    )


class FixedProvider:
    provider_name = "fixed"
    model_name = "fixed-test-model"

    def __init__(self, value):
        self.value = value

    def generate_plan(self, request: LLMRequest) -> LLMResponse:
        del request
        return LLMResponse(
            payload=self.value,
            provider=self.provider_name,
            model=self.model_name,
            duration_ms=0,
            attempt_count=1,
        )

    def test_connection(self) -> LLMResponse:
        return LLMResponse(
            payload={"status": "ok"}, provider=self.provider_name,
            model=self.model_name, duration_ms=0, attempt_count=1,
        )


def validator():
    return PlanValidator(WorkspaceValidator(REPO_ROOT))


def test_valid_plan_generated_and_validated(db_session):
    task = make_task(db_session)
    plan = PlannerAgent(db_session, MockLLMProvider()).create_plan(task.id)

    assert plan.version == 1
    assert plan.validation_status == "VALID"
    assert plan.plan_json["steps"][0]["capability_id"] == "repository_state"
    assert plan.plan_json["resolved_steps"][0]["resolved_tool_id"] == "git_read"
    assert db_session.get(TaskRecord, task.id).status == TaskStatus.WAITING_APPROVAL.value
    assert db_session.query(AuditEventRecord).filter_by(
        task_id=task.id, event_type="PLAN_CREATED"
    ).count() == 1


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        {"schema_version": 2, "steps": [{"capability_id": "repository_state"}]},
        {"steps": []},
    ],
)
def test_invalid_json_or_missing_fields_rejected(payload):
    with pytest.raises(PlanValidationError):
        validator().validate(payload, REPO_ROOT)


@pytest.mark.parametrize(
    "step",
    [
        {"step_id": "1", "capability_id": "unknown", "parameters": {}},
        {"step_id": "1", "tool": "git_read", "action": "status"},
        {"step_id": "1", "capability_id": "repository_state", "parameters": {"command": "shell command"}},
        {"step_id": "1", "capability_id": "project_metadata", "parameters": {"relative_path": "write file"}},
        {"step_id": "1", "capability_id": "repository_state", "parameters": {"command": "git push"}},
    ],
)
def test_forbidden_plan_operations_rejected(step):
    with pytest.raises(PlanValidationError):
        validator().validate({"schema_version": 2, "steps": [step]}, REPO_ROOT)


def test_plan_provider_json_string_is_supported():
    raw = json.dumps(
        {"schema_version": 2, "steps": [{"step_id": "1", "capability_id": "repository_state", "parameters": {}}]}
    )
    assert validator().validate(raw, REPO_ROOT).steps[0].capability_id == "repository_state"


def test_planner_integration_saves_plan_and_waits_for_approval(db_session):
    task = make_task(db_session)
    provider = FixedProvider(
        {"schema_version": 2, "steps": [{"step_id": "1", "capability_id": "repository_state", "parameters": {}}]}
    )
    plan = PlannerAgent(db_session, provider).create_plan(task.id, context={"release": "2.0"})

    assert db_session.get(PlanRecord, plan.id).version == 1
    assert db_session.get(TaskRecord, task.id).status == TaskStatus.WAITING_APPROVAL.value


def test_metadata_manifest_contains_only_existing_allowlisted_files(tmp_path):
    manifest = build_metadata_manifest(REPO_ROOT)
    assert "README.md" in manifest
    assert "package.json" not in manifest
    assert "frontend/package.json" in manifest
    assert "backend/requirements.txt" in manifest


def test_plan_validator_rejects_metadata_path_missing_from_manifest(tmp_path):
    validator_with_manifest = PlanValidator(
        WorkspaceValidator(REPO_ROOT), metadata_manifest=build_metadata_manifest(REPO_ROOT)
    )

    with pytest.raises(PlanValidationError, match="manifest"):
        validator_with_manifest.validate(
            {
                "schema_version": 2,
                "steps": [{
                    "step_id": "read-package",
                    "capability_id": "project_metadata",
                    "parameters": {"relative_path": "package.json"},
                }],
            },
            REPO_ROOT,
        )


def test_capability_registry_import_has_no_manifest_import_cycle():
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1])}
    result = subprocess.run(
        [sys.executable, "-c", "from app.capabilities.resolver import CapabilityResolver"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
