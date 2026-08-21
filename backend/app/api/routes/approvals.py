"""Approval and audit endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...approvals.service import ApprovalError, ApprovalService
from ...schemas.approval import (
    ApprovalCreate,
    ApprovalDecision,
    ApprovalRead,
    CancelRequest,
)
from ...schemas.audit import AuditEventRead
from ...schemas.task import TaskRead
from ...storage.database import get_db
from ...storage.orm import AuditEventRecord

router = APIRouter(tags=["approvals"])


def _approval_read(approval, db: Session) -> ApprovalRead:
    from ...storage.orm import PlanRecord

    plan = db.get(PlanRecord, approval.plan_id)
    return ApprovalRead(
        id=approval.id,
        task_id=approval.task_id,
        plan_id=approval.plan_id,
        plan_version=plan.version if plan else 0,
        decision=approval.decision,
        approver=approval.approver,
        reason=approval.reason,
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
    db: Session = Depends(get_db),
) -> ApprovalRead:
    try:
        approval = ApprovalService(db).approve(
            approval_id, actor=payload.actor, reason=payload.reason
        )
        return _approval_read(approval, db)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ApprovalError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
