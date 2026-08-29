import json

from app.agents.planner.planner import PlannerAgent
from app.agents.providers.mock import MockLLMProvider
from app.analyst.package import MAX_PACKAGE_BYTES, build_evidence_package
from app.storage.orm import AuditEventRecord, EvidenceRecord, ToolExecutionRecord
from tests.project_test_support import create_project_task


def test_package_contains_bounded_allowlisted_facts_only(db_session):
    task = create_project_task(
        db_session,
        title="Analyst package task",
        goal="Assess release readiness from evidence",
    )
    plan = PlannerAgent(db_session, MockLLMProvider()).create_plan(task.id)
    db_session.add(
        ToolExecutionRecord(
            task_id=task.id,
            tool_name="git_read",
            action="status",
            status="SUCCESS",
            result_summary="Working tree is clean.",
            artifact_path="D:/AgentProjectData/AgentForge/artifacts/evidence.json",
            content_hash="a" * 64,
        )
    )
    db_session.add(
        EvidenceRecord(
            id="evidence-1",
            task_id=task.id,
            summary="Repository status was captured.",
            artifact_path="D:/AgentProjectData/AgentForge/artifacts/evidence.json",
            content_hash="a" * 64,
        )
    )
    db_session.add(
        AuditEventRecord(
            task_id=task.id,
            event_type="RUNTIME_OBSERVATION",
            actor="agent_runtime",
            payload_summary=json.dumps(
                {
                    "observation_id": "observation-1",
                    "step_id": "step-1",
                    "capability_id": "repository_state",
                    "tool_id": "git_read",
                    "execution_id": "execution-1",
                    "status": "SUCCESS",
                    "result_summary": "Working tree is clean.",
                    "evidence_refs": ["evidence-1"],
                    "decision": "COMPLETE",
                    "reason_code": "STEP_SUCCEEDED",
                    "retryable": False,
                    "replan_recommended": False,
                }
            ),
            correlation_id="correlation-1",
        )
    )
    db_session.commit()

    package = build_evidence_package(
        db_session, task_id=task.id, plan_id=plan.id, plan_version=plan.version
    )
    payload = package.to_dict()
    serialized = json.dumps(payload, ensure_ascii=False)

    assert payload["task"]["id"] == task.id
    assert payload["plan"]["version"] == 1
    assert payload["executions"][0]["status"] == "SUCCESS"
    assert payload["observations"][0]["evidence_refs"] == ["evidence-1"]
    assert payload["evidence"][0]["id"] == "evidence-1"
    assert package.evidence_ids == frozenset({"evidence-1"})
    assert "raw_output" not in serialized
    assert "prompt" not in payload
    assert "reasoning" not in serialized.lower()
    assert len(serialized.encode("utf-8")) <= MAX_PACKAGE_BYTES


def test_package_caps_records_and_marks_truncation(db_session):
    task = create_project_task(
        db_session,
        title="Analyst package cap task",
        goal="Assess bounded package behavior",
    )
    plan = PlannerAgent(db_session, MockLLMProvider()).create_plan(task.id)
    for index in range(40):
        db_session.add(
            EvidenceRecord(
                id=f"evidence-{index}",
                task_id=task.id,
                summary="bounded evidence",
                artifact_path=None,
                content_hash=None,
            )
        )
    db_session.commit()

    package = build_evidence_package(
        db_session, task_id=task.id, plan_id=plan.id, plan_version=plan.version
    )

    assert package.truncated is True
    assert len(package.to_dict()["evidence"]) < 40
    assert package.to_dict()["limitations"]


def test_package_rejects_wrong_plan_binding(db_session):
    task = create_project_task(
        db_session,
        title="Analyst binding task",
        goal="Assess plan binding",
    )
    plan = PlannerAgent(db_session, MockLLMProvider()).create_plan(task.id)

    try:
        build_evidence_package(
            db_session, task_id=task.id, plan_id=plan.id, plan_version=99
        )
    except ValueError as exc:
        assert "plan" in str(exc).lower()
    else:
        raise AssertionError("wrong plan binding must be rejected")
