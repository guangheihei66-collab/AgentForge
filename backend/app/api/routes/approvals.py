"""Approval and audit endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ...approvals.service import ApprovalError, ApprovalService
from ...audit.provenance import (
    APPROVAL_COMMAND_FAILED,
    APPROVAL_COMMAND_SUCCEEDED,
    GLOBAL_APPROVAL_COMMAND_RECEIVED,
    command_correlation_id,
    persist_provenance_event,
    safe_error_category,
)
from ...schemas.approval import (
    ApprovalCreate,
    ApprovalDecision,
    ApprovalRead,
    CancelRequest,
)
from ...schemas.audit import AuditEventRead
from ...schemas.task import TaskRead
from ...storage.database import get_db
from ...storage.orm import ApprovalRecord, AuditEventRecord, PlanRecord, TaskRecord

router = APIRouter(tags=["approvals"])


def _approval_read(approval, db: Session) -> ApprovalRead:
    plan = db.get(PlanRecord, approval.plan_id)
    return ApprovalRead(
        id=approval.id,
        task_id=approval.task_id,
        plan_id=approval.plan_id,
        plan_version=plan.version if plan else 0,
        decision=approval.decision,
        approver=approval.approver,
        reason=approval.reason,
        resolved_snapshot=approval.resolved_snapshot,
        created_at=approval.created_at,
    )


@router.post("/tasks/{task_id}/approval", response_model=ApprovalRead, status_code=201)
def create_approval(
    task_id: str, payload: ApprovalCreate, db: Session = Depends(get_db)
) -> ApprovalRead:
    try:
        approval = ApprovalService(db).create_request(
            task_id=task_id,
            plan_id=payload.plan_id,
            plan_version=payload.plan_version,
            requested_by=payload.requested_by,
        )
        return _approval_read(approval, db)
    except (ApprovalError, LookupError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalRead)
def approve(
    approval_id: str,
    payload: ApprovalDecision,
    request: Request,
    db: Session = Depends(get_db),
) -> ApprovalRead:
    correlation_id = command_correlation_id(request.headers.get("X-Request-ID"))
    context = _approval_context(approval_id, db)
    if context is not None:
        approval_record, task, plan = context
        persist_provenance_event(
            db,
            task_id=task.id,
            event_type=GLOBAL_APPROVAL_COMMAND_RECEIVED,
            actor=payload.actor,
            correlation_id=correlation_id,
            fields={
                "approval_id": approval_record.id,
                "command_kind": "GLOBAL_APPROVAL",
                "outcome": "RECEIVED",
                "plan_id": approval_record.plan_id,
                "plan_version": plan.version if plan is not None else None,
                "task_state": task.status,
            },
        )
    try:
        approval = ApprovalService(db).approve(
            approval_id, actor=payload.actor, reason=payload.reason
        )
        if context is not None:
            _, task, plan = context
            current = db.get(TaskRecord, task.id)
            persist_provenance_event(
                db,
                task_id=task.id,
                event_type=APPROVAL_COMMAND_SUCCEEDED,
                actor=payload.actor,
                correlation_id=correlation_id,
                fields={
                    "approval_id": approval.id,
                    "approval_persistence": "APPROVED",
                    "approval_state": approval.decision,
                    "authority_validation": "PASSED",
                    "command_kind": "GLOBAL_APPROVAL",
                    "outcome": "APPROVAL_PERSISTED",
                    "plan_id": approval.plan_id,
                    "plan_version": plan.version if plan is not None else None,
                    "task_state": current.status if current is not None else task.status,
                },
            )
        return _approval_read(approval, db)
    except (LookupError, ApprovalError, ValueError, PermissionError) as exc:
        _record_global_command_failure(
            db,
            context=context,
            approval_id=approval_id,
            actor=payload.actor,
            correlation_id=correlation_id,
            error=exc,
        )
        if isinstance(exc, LookupError):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        _record_global_command_failure(
            db,
            context=context,
            approval_id=approval_id,
            actor=payload.actor,
            correlation_id=correlation_id,
            error=exc,
        )
        raise


def _approval_context(
    approval_id: str, db: Session
) -> tuple[ApprovalRecord, TaskRecord, PlanRecord | None] | None:
    approval = db.get(ApprovalRecord, approval_id)
    if approval is None:
        return None
    task = db.get(TaskRecord, approval.task_id)
    if task is None:
        return None
    return approval, task, db.get(PlanRecord, approval.plan_id)


def _record_global_command_failure(
    db: Session,
    *,
    context: tuple[ApprovalRecord, TaskRecord, PlanRecord | None] | None,
    approval_id: str,
    actor: str,
    correlation_id: str,
    error: Exception,
) -> None:
    if context is None:
        return
    db.rollback()
    approval, task, plan = context
    current = db.get(TaskRecord, task.id)
    persist_provenance_event(
        db,
        task_id=task.id,
        event_type=APPROVAL_COMMAND_FAILED,
        actor=actor,
        correlation_id=correlation_id,
        fields={
            "approval_id": approval_id,
            "authority_validation": "FAILED",
            "command_kind": "GLOBAL_APPROVAL",
            "error_category": safe_error_category(error),
            "execution_initiation": "NOT_REQUESTED",
            "outcome": "REJECTED",
            "plan_id": approval.plan_id,
            "plan_version": plan.version if plan is not None else None,
            "task_state": current.status if current is not None else task.status,
        },
    )


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalRead)
def reject(
    approval_id: str,
    payload: ApprovalDecision,
    db: Session = Depends(get_db),
) -> ApprovalRead:
    if not payload.reason:
        raise HTTPException(status_code=422, detail="Rejection reason is required")
    try:
        approval = ApprovalService(db).reject(
            approval_id, actor=payload.actor, reason=payload.reason
        )
        return _approval_read(approval, db)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ApprovalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tasks/{task_id}/cancel", response_model=TaskRead)
def cancel_task(
    task_id: str,
    payload: CancelRequest,
    db: Session = Depends(get_db),
) -> TaskRead:
    try:
        task = ApprovalService(db).cancel_task(
            task_id, actor=payload.actor, reason=payload.reason
        )
        return TaskRead.model_validate(task)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ApprovalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tasks/{task_id}/audit", response_model=list[AuditEventRead])
def get_audit(task_id: str, db: Session = Depends(get_db)) -> list[AuditEventRead]:
    events = (
        db.query(AuditEventRecord)
        .filter_by(task_id=task_id)
        .order_by(AuditEventRecord.created_at.asc(), AuditEventRecord.id.asc())
        .all()
    )
    return [AuditEventRead.model_validate(event) for event in events]
