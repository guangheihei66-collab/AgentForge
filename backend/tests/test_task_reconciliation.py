"""Regression coverage for historical failed RUNNING task reconciliation."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from fastapi.testclient import TestClient

from app.main import app
from app.services.task_reconciliation import TaskReconciliationService
from app.storage.orm import (
    ApprovalRecord,
    AuditEventRecord,
    EvidenceRecord,
    PlanRecord,
    TaskRecord,
    ToolExecutionRecord,
)


def _historical_failure(db_session, *, pending=False, active=False):
    project = db_session.info["phase14_test_project_factory"]()
    task = TaskRecord(
        project_id=project.id,
        title="Historical failed run",
        goal="Reconcile persisted truth",
        workspace=project.workspace_root,
        status="RUNNING",
    )
    db_session.add(task)
    db_session.flush()
    plan = PlanRecord(
        task_id=task.id,
        version=1,
        plan_json={"schema_version": 2, "steps": []},
        validation_status="VALID",
    )
    db_session.add(plan)
    db_session.flush()
    db_session.add(
        ApprovalRecord(
            task_id=task.id,
            plan_id=plan.id,
            decision="PENDING" if pending else "APPROVED",
            approver="operator",
        )
    )
    statuses = ["SUCCESS"] * 5 + (["RUNNING"] if active else ["FAILED"])
    for index, status in enumerate(statuses):
        db_session.add(
            ToolExecutionRecord(
                task_id=task.id,
                tool_name="test_run",
                action="run_profile",
                status=status,
                result_summary="bounded",
            )
        )
    db_session.add(EvidenceRecord(task_id=task.id, summary="failure evidence"))
    db_session.add_all(
        [
            AuditEventRecord(
                task_id=task.id,
                event_type="REPLAN_REQUESTED",
                actor="replanning_service",
                payload_summary="{}",
                correlation_id="replan-correlation",
            ),
            AuditEventRecord(
                task_id=task.id,
                event_type="EXECUTION_INITIATION_FAILED",
                actor="agent_orchestration",
                payload_summary=json.dumps(
                    {
                        "error_category": "RUNTIME_VALIDATION_FAILED",
                        "execution_count_after": len(statuses),
                        "plan_id": plan.id,
                        "plan_version": 1,
                    }
                ),
                correlation_id="failure-correlation",
            ),
        ]
    )
    db_session.commit()
    return task


def _counts(db_session, task_id):
    return {
        "plans": db_session.query(PlanRecord).filter_by(task_id=task_id).count(),
        "approvals": db_session.query(ApprovalRecord).filter_by(task_id=task_id).count(),
        "executions": db_session.query(ToolExecutionRecord).filter_by(task_id=task_id).count(),
        "evidence": db_session.query(EvidenceRecord).filter_by(task_id=task_id).count(),
        "audit": db_session.query(AuditEventRecord).filter_by(task_id=task_id).count(),
    }


def test_proven_historical_failure_is_eligible_and_reconciles_without_reexecution(db_session):
    task = _historical_failure(db_session)
    before = _counts(db_session, task.id)

    with TestClient(app) as client:
        eligibility = client.get(f"/tasks/{task.id}/reconciliation")
        response = client.post(
            f"/tasks/{task.id}/reconciliation",
            json={"actor": "operator"},
        )

    assert eligibility.status_code == 200
    assert eligibility.json()["eligible"] is True
    assert response.status_code == 200
    assert response.json() == {
        "task_id": task.id,
        "previous_state": "RUNNING",
        "final_state": "FAILED",
        "reconciled": True,
        "eligible": True,
        "reason_code": "HISTORICAL_RUNTIME_FAILURE_RECONCILED",
    }
    db_session.expire_all()
    assert db_session.get(TaskRecord, task.id).status == "FAILED"
    after = _counts(db_session, task.id)
    assert {key: after[key] for key in ("plans", "approvals", "executions", "evidence")} == {
        key: before[key] for key in ("plans", "approvals", "executions", "evidence")
    }
    assert after["audit"] == before["audit"] + 2
    assert [
        event.event_type
        for event in db_session.query(AuditEventRecord).filter_by(task_id=task.id).all()
    ][-2:] == ["TASK_STATE_CHANGED", "TASK_RECONCILED"]


def test_reconciliation_fails_closed_for_ambiguous_pending_or_active_tasks(db_session):
    ambiguous = _historical_failure(db_session)
    db_session.query(AuditEventRecord).filter_by(task_id=ambiguous.id).delete()
    pending = _historical_failure(db_session, pending=True)
    active = _historical_failure(db_session, active=True)
    db_session.commit()

    with TestClient(app) as client:
        cases = {
            ambiguous.id: "NO_TERMINAL_FAILURE_EVIDENCE",
            pending.id: "PENDING_SUCCESSOR_APPROVAL",
            active.id: "ACTIVE_EXECUTION_EXISTS",
        }
        for task_id, reason in cases.items():
            check = client.get(f"/tasks/{task_id}/reconciliation")
            mutation = client.post(
                f"/tasks/{task_id}/reconciliation", json={"actor": "operator"}
            )
            assert check.status_code == 200
            assert check.json() == {"task_id": task_id, "eligible": False, "reason_code": reason}
            assert mutation.status_code == 409
        arbitrary = client.post(
            f"/tasks/{ambiguous.id}/reconciliation",
            json={"actor": "operator", "target_state": "SUCCESS"},
        )
        assert arbitrary.status_code == 422


def test_failed_task_is_idempotent_without_duplicate_audit(db_session):
    task = _historical_failure(db_session)
    with TestClient(app) as client:
        assert client.post(
            f"/tasks/{task.id}/reconciliation", json={"actor": "operator"}
        ).status_code == 200
        audit_after_first = _counts(db_session, task.id)["audit"]
        second = client.post(
            f"/tasks/{task.id}/reconciliation", json={"actor": "operator"}
        )
    assert second.status_code == 200
    assert second.json()["reconciled"] is False
    assert second.json()["reason_code"] == "TASK_ALREADY_RECONCILED"
    assert _counts(db_session, task.id)["audit"] == audit_after_first


def test_runtime_activity_after_historical_failure_refuses_reconciliation(db_session):
    task = _historical_failure(db_session)
    db_session.add(
        AuditEventRecord(
            task_id=task.id,
            event_type="RUNTIME_TRANSITION",
            actor="agent_runtime",
            payload_summary='{"from":"RUNNING","to":"OBSERVING"}',
            correlation_id="later-runtime",
        )
    )
    db_session.commit()
    with TestClient(app) as client:
        response = client.get(f"/tasks/{task.id}/reconciliation")
    assert response.status_code == 200
    assert response.json()["eligible"] is False
    assert response.json()["reason_code"] == "RUNTIME_ACTIVITY_AFTER_FAILURE"


def test_audit_commit_failure_rolls_back_task_state(db_session, monkeypatch):
    task = _historical_failure(db_session)
    before = _counts(db_session, task.id)

    def fail_commit():
        raise RuntimeError("simulated audit persistence failure")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="simulated audit"):
        TaskReconciliationService(db_session).reconcile(task.id, actor="operator")
    db_session.expire_all()
    assert db_session.get(TaskRecord, task.id).status == "RUNNING"
    assert _counts(db_session, task.id) == before


def test_competing_reconciliation_requests_apply_once(db_session):
    task = _historical_failure(db_session)
    before_audit = _counts(db_session, task.id)["audit"]

    def reconcile_once():
        with TestClient(app) as client:
            response = client.post(
                f"/tasks/{task.id}/reconciliation", json={"actor": "operator"}
            )
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: reconcile_once(), range(2)))

    assert [status for status, _ in results] == [200, 200]
    assert sorted(result["reconciled"] for _, result in results) == [False, True]
    db_session.expire_all()
    assert db_session.get(TaskRecord, task.id).status == "FAILED"
    assert _counts(db_session, task.id)["audit"] == before_audit + 2
