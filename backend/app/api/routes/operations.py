"""Read-only aggregate endpoints for the enterprise operations console."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...approvals.service import ApprovalError, ApprovalService
from ...domain.states.task_state import TaskStatus
from ...schemas.operations import (
    ApprovalQueueRead,
    ReportRead,
    TaskDetailRead,
    TaskSummaryRead,
)
from ...storage.database import get_db
from ...storage.orm import (
    ApprovalRecord,
    AuditEventRecord,
    EvidenceRecord,
    PlanRecord,
    ProjectRecord,
    TaskRecord,
    ToolExecutionRecord,
)

router = APIRouter(tags=["operations"])


def _task_or_404(task_id: str, db: Session) -> TaskRecord:
    task = db.get(TaskRecord, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/tasks", response_model=list[TaskSummaryRead])
def list_tasks(db: Session = Depends(get_db)) -> list[TaskSummaryRead]:
    tasks = db.query(TaskRecord).order_by(TaskRecord.created_at.desc()).all()
    return [TaskSummaryRead.model_validate(task) for task in tasks]


@router.get("/approvals/pending", response_model=list[ApprovalQueueRead])
def pending_approvals(db: Session = Depends(get_db)) -> list[ApprovalQueueRead]:
    rows = (
        db.query(ApprovalRecord, TaskRecord, PlanRecord)
        .join(TaskRecord, TaskRecord.id == ApprovalRecord.task_id)
        .join(PlanRecord, PlanRecord.id == ApprovalRecord.plan_id)
        .join(ProjectRecord, ProjectRecord.id == TaskRecord.project_id)
        .filter(ApprovalRecord.decision == "PENDING")
        .filter(ProjectRecord.status == "ACTIVE")
        .order_by(ApprovalRecord.created_at.asc())
        .all()
    )
    queue = [
        ApprovalQueueRead(
            id=approval.id,
            approval_id=approval.id,
            task_id=task.id,
            task_title=task.title,
            plan_id=plan.id,
            plan_version=plan.version,
            decision=approval.decision,
            requested_by=approval.approver,
            created_at=approval.created_at,
            plan_json=plan.plan_json,
            resolved_snapshot=approval.resolved_snapshot,
        )
        for approval, task, plan in rows
    ]

    pending_task_ids = {approval.task_id for approval, _, _ in rows}
    candidates = (
        db.query(TaskRecord, PlanRecord)
        .join(PlanRecord, PlanRecord.task_id == TaskRecord.id)
        .join(ProjectRecord, ProjectRecord.id == TaskRecord.project_id)
        .filter(TaskRecord.status == TaskStatus.WAITING_APPROVAL.value)
        .filter(PlanRecord.validation_status == "VALID")
        .filter(ProjectRecord.status == "ACTIVE")
        .order_by(TaskRecord.created_at.asc(), PlanRecord.version.desc())
        .all()
    )
    seen_task_ids: set[str] = set()
    for task, plan in candidates:
        if task.id in pending_task_ids or task.id in seen_task_ids:
            continue
        seen_task_ids.add(task.id)
        try:
            snapshot = ApprovalService(db)._snapshot_document(plan)
        except ApprovalError:
            continue
        queue.append(
            ApprovalQueueRead(
                id=task.id,
                approval_id=None,
                task_id=task.id,
                task_title=task.title,
                plan_id=plan.id,
                plan_version=plan.version,
                decision="PENDING",
                requested_by="planner",
                created_at=plan.created_at,
                plan_json=plan.plan_json,
                resolved_snapshot=snapshot,
            )
        )
    return queue


@router.get("/tasks/{task_id}/detail", response_model=TaskDetailRead)
def task_detail(task_id: str, db: Session = Depends(get_db)) -> TaskDetailRead:
    task = _task_or_404(task_id, db)
    plans = db.query(PlanRecord).filter_by(task_id=task_id).order_by(PlanRecord.version.desc()).all()
    plan_versions = {plan.id: plan.version for plan in plans}
    approvals = db.query(ApprovalRecord).filter_by(task_id=task_id).order_by(ApprovalRecord.created_at.asc()).all()
    executions = db.query(ToolExecutionRecord).filter_by(task_id=task_id).order_by(ToolExecutionRecord.started_at.asc()).all()
    evidence = db.query(EvidenceRecord).filter_by(task_id=task_id).order_by(EvidenceRecord.created_at.asc()).all()
    audit = db.query(AuditEventRecord).filter_by(task_id=task_id).order_by(AuditEventRecord.created_at.asc()).all()
    return TaskDetailRead(
        task=TaskSummaryRead.model_validate(task),
        plans=[{"id": p.id, "version": p.version, "plan_json": p.plan_json, "validation_status": p.validation_status, "created_at": p.created_at} for p in plans],
        approvals=[{"id": a.id, "plan_id": a.plan_id, "plan_version": plan_versions.get(a.plan_id), "decision": a.decision, "approver": a.approver, "reason": a.reason, "resolved_snapshot": a.resolved_snapshot, "created_at": a.created_at} for a in approvals],
        executions=[{"id": e.id, "tool_name": e.tool_name, "action": e.action, "status": e.status, "result_summary": e.result_summary, "artifact_path": e.artifact_path, "content_hash": e.content_hash, "started_at": e.started_at, "finished_at": e.finished_at} for e in executions],
        evidence=[{"id": e.id, "summary": e.summary, "artifact_path": e.artifact_path, "content_hash": e.content_hash, "created_at": e.created_at} for e in evidence],
        audit=[{"id": e.id, "event_type": e.event_type, "actor": e.actor, "payload_summary": e.payload_summary, "correlation_id": e.correlation_id, "created_at": e.created_at} for e in audit],
    )


@router.get("/tasks/{task_id}/report", response_model=ReportRead)
def task_report(task_id: str, db: Session = Depends(get_db)) -> ReportRead:
    task = _task_or_404(task_id, db)
    executions = db.query(ToolExecutionRecord).filter_by(task_id=task_id).all()
    evidence = db.query(EvidenceRecord).filter_by(task_id=task_id).all()
    audit_count = db.query(AuditEventRecord).filter_by(task_id=task_id).count()
    completed = sum(1 for item in executions if item.status == "SUCCESS")
    failed = sum(1 for item in executions if item.status == "FAILED")
    rejected = sum(1 for item in executions if item.status == "REJECTED")
    readiness = "PASS" if task.status == "SUCCESS" and failed == 0 else "FAIL" if task.status == "FAILED" or failed else "PENDING"
    return ReportRead(
        task=TaskSummaryRead.model_validate(task),
        readiness=readiness,
        summary=f"{completed} successful; {failed} failed; {rejected} rejected.",
        completed_steps=completed,
        failed_steps=failed,
        rejected_steps=rejected,
        evidence=[{"id": e.id, "summary": e.summary, "artifact_path": e.artifact_path, "content_hash": e.content_hash, "created_at": e.created_at} for e in evidence],
        audit_count=audit_count,
        execution_count=len(executions),
    )
