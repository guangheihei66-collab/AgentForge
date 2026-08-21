"""Add synthetic, idempotent AgentForge demo records to the external data root."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import os
from uuid import uuid4

from app.storage.database import SessionLocal, init_db
from app.storage.orm import (
    ApprovalRecord,
    AuditEventRecord,
    EvidenceRecord,
    PlanRecord,
    TaskRecord,
    ToolExecutionRecord,
)


DATA_ROOT = Path(os.getenv("AGENTFORGE_DATA_ROOT", r"D:\AgentProjectData\AgentForge"))
WORKSPACE = r"D:\AgentProjects\AgentForge"


def add_audit(session, task_id: str, event_type: str, actor: str, summary: str, created_at: datetime) -> None:
    session.add(AuditEventRecord(
        task_id=task_id,
        event_type=event_type,
        actor=actor,
        payload_summary=summary,
        correlation_id=str(uuid4()),
        created_at=created_at,
    ))


def build_plan(task_id: str, version: int, created_at: datetime) -> PlanRecord:
    return PlanRecord(
        task_id=task_id,
        version=version,
        plan_json={"steps": [
            {"step_id": "step-1", "tool": "git_read", "action": "check git status", "risk_level": "low", "permission_level": "SAFE_READ"},
            {"step_id": "step-2", "tool": "file_read", "action": "read project metadata", "risk_level": "low", "permission_level": "SAFE_READ"},
            {"step_id": "step-3", "tool": "test_run", "action": "run smoke tests", "risk_level": "medium", "permission_level": "APPROVED_EXEC"},
        ]},
        validation_status="VALID",
        created_at=created_at,
    )


def seed() -> None:
    init_db()
    with SessionLocal() as session:
        if session.query(TaskRecord).filter(TaskRecord.title.like("Release v2.0 Verification%")).count():
            print("AgentForge demo data already exists; nothing changed.")
            return

        now = datetime.now(timezone.utc).replace(microsecond=0)
        pending_task = TaskRecord(
            title="Release v2.0 Verification",
            goal="Verify whether Release v2.0 is ready for release.",
            workspace=WORKSPACE,
            status="WAITING_APPROVAL",
            created_at=now - timedelta(minutes=18),
            updated_at=now - timedelta(minutes=4),
        )
        passed_task = TaskRecord(
            title="Release v2.0 Verification (PASS)",
            goal="Completed synthetic release readiness verification.",
            workspace=WORKSPACE,
            status="SUCCESS",
            created_at=now - timedelta(hours=2),
            updated_at=now - timedelta(hours=1),
            completed_at=now - timedelta(hours=1),
        )
        session.add_all([pending_task, passed_task])
        session.flush()

        pending_plan = build_plan(pending_task.id, 1, now - timedelta(minutes=14))
        passed_plan = build_plan(passed_task.id, 1, now - timedelta(hours=1, minutes=55))
        session.add_all([pending_plan, passed_plan])
        session.flush()
        session.add(ApprovalRecord(
            task_id=pending_task.id,
            plan_id=pending_plan.id,
            decision="PENDING",
            approver="planner-agent",
            reason=None,
            created_at=now - timedelta(minutes=4),
        ))
        session.add(ApprovalRecord(
            task_id=passed_task.id,
            plan_id=passed_plan.id,
            decision="APPROVED",
            approver="operator",
            reason="Synthetic demo approval",
            created_at=now - timedelta(hours=1, minutes=50),
        ))
        for index, tool in enumerate(("git_read", "file_read", "test_run")):
            started = now - timedelta(hours=1, minutes=45-index*5)
            session.add(ToolExecutionRecord(
                task_id=passed_task.id,
                tool_name=tool,
                action="run_profile" if tool == "test_run" else "status",
                status="SUCCESS",
                result_summary=f"Synthetic {tool} execution completed successfully.",
                artifact_path=str(DATA_ROOT / "demo-artifacts" / f"{tool}-summary.json"),
                content_hash="demo-content-hash",
                started_at=started,
                finished_at=started + timedelta(seconds=8),
            ))
        session.add(EvidenceRecord(
            task_id=passed_task.id,
            summary="Synthetic test results for Release v2.0",
            artifact_path=str(DATA_ROOT / "demo-artifacts" / "test-results.json"),
            content_hash="demo-test-results-hash",
            created_at=now - timedelta(hours=1),
        ))
        add_audit(session, pending_task.id, "APPROVAL_CREATED", "planner-agent", json.dumps({"plan_version": 1, "summary": "Synthetic approval request"}), now - timedelta(minutes=4))
        add_audit(session, passed_task.id, "APPROVED", "operator", "Synthetic demo approval", now - timedelta(hours=1, minutes=50))
        add_audit(session, passed_task.id, "TOOL_EXECUTION", "tool-gateway", "Three synthetic tool executions succeeded", now - timedelta(hours=1))
        session.commit()
        print(f"Synthetic demo data added under {DATA_ROOT}.")


if __name__ == "__main__":
    seed()
