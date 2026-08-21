import json

import pytest

from app.agents.planner.planner import PlannerAgent
from app.agents.planner.validator import PlanValidationError, PlanValidator
from app.agents.providers.mock import MockLLMProvider
from app.domain.states.task_state import TaskStatus
from app.services.task_service import TaskService
from app.storage.orm import AuditEventRecord, PlanRecord, TaskRecord
from app.workspace.validator import WorkspaceValidator


REPO_ROOT = r"D:\AgentProjects\AgentForge"


def make_task(session):
    return TaskService(session).create_task(
        title="Planner test",
        goal="Check release readiness",
        workspace=REPO_ROOT,
    )


class FixedProvider:
    def __init__(self, value):
        self.value = value

    def generate_plan(self, prompt, context):
        del prompt, context
        return self.value


def validator():
    return PlanValidator(WorkspaceValidator(REPO_ROOT))


def test_valid_plan_generated_and_validated(db_session):
    task = make_task(db_session)
    plan = PlannerAgent(db_session, MockLLMProvider(), REPO_ROOT).create_plan(task.id)

    assert plan.version == 1
    assert plan.validation_status == "VALID"
    assert plan.plan_json["steps"][0]["tool"] == "git_read"
    assert db_session.get(TaskRecord, task.id).status == TaskStatus.WAITING_APPROVAL.value
    assert db_session.query(AuditEventRecord).filter_by(event_type="PLAN_CREATED").count() == 1


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        {"steps": [{"tool": "git_read"}]},
        {"steps": []},
    ],
)
def test_invalid_json_or_missing_fields_rejected(payload):
    with pytest.raises(PlanValidationError):
        validator().validate(payload, REPO_ROOT)


@pytest.mark.parametrize(
    "step",
    [
        {"step_id": "1", "tool": "unknown", "action": "run", "risk_level": "low", "permission_level": "safe_read"},
        {"step_id": "1", "tool": "git_read", "action": "status", "risk_level": "low", "permission_level": "denied"},
        {"step_id": "1", "tool": "git_read", "action": "shell command", "risk_level": "low", "permission_level": "safe_read"},
        {"step_id": "1", "tool": "file_read", "action": "write file", "risk_level": "medium", "permission_level": "safe_read"},
        {"step_id": "1", "tool": "git_read", "action": "git push", "risk_level": "low", "permission_level": "safe_read"},
    ],
)
def test_forbidden_plan_operations_rejected(step):
    with pytest.raises(PlanValidationError):
        validator().validate({"steps": [step]}, REPO_ROOT)


def test_plan_provider_json_string_is_supported():
    raw = json.dumps(
        {"steps": [{"step_id": "1", "tool": "git_read", "action": "status", "risk_level": "low", "permission_level": "SAFE_READ"}]}
    )
    assert validator().validate(raw, REPO_ROOT).steps[0].tool == "git_read"


def test_planner_integration_saves_plan_and_waits_for_approval(db_session):
    task = make_task(db_session)
    provider = FixedProvider(
        {"steps": [{"step_id": "1", "tool": "git_read", "action": "status", "risk_level": "low", "permission_level": "safe_read"}]}
    )
    plan = PlannerAgent(db_session, provider, REPO_ROOT).create_plan(task.id, context={"release": "2.0"})

    assert db_session.get(PlanRecord, plan.id).version == 1
    assert db_session.get(TaskRecord, task.id).status == TaskStatus.WAITING_APPROVAL.value
