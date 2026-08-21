"""Approval lifecycle and protected execution authorization."""

from datetime import datetime, timezone
import json
from uuid import uuid4

from sqlalchemy.orm import Session

from ..domain.states.task_state import TaskStatus
from ..services.task_service import TaskService
from ..storage.orm import ApprovalRecord, AuditEventRecord, PlanRecord, TaskRecord


class ApprovalError(PermissionError):
    """Raised when an approval cannot be created or used."""


class ApprovalService:
    def __init__(self, session: Session):
        self.session = session

    def create_request(
        self,
        *,
        task_id: str,
        plan_id: str,
        plan_version: int,
        requested_by: str = "system",
    ) -> ApprovalRecord:
        task, plan = self._validate_binding(task_id, plan_id, plan_version)
        if task.status == TaskStatus.CANCELLED.value:
            raise ApprovalError("Cancelled task cannot request approval")
        if task.status not in {
            TaskStatus.PLANNING.value,
            TaskStatus.WAITING_APPROVAL.value,
        }:
            raise ApprovalError(f"Task is not ready for approval: {task.status}")

        existing = (
            self.session.query(ApprovalRecord)
            .filter_by(task_id=task_id, plan_id=plan_id)
            .filter(ApprovalRecord.decision.in_(["PENDING", "APPROVED"]))
            .first()
        )
        if existing is not None:
            raise ApprovalError("An active approval already exists for this plan")

        if task.status == TaskStatus.PLANNING.value:
            TaskService(self.session).transition_task(
                task_id,
                TaskStatus.WAITING_APPROVAL,
                actor=requested_by,
                reason="Approval requested for validated plan",
            )

        approval = ApprovalRecord(
            task_id=task_id,
            plan_id=plan.id,
            decision="PENDING",
            approver="pending",
            reason=None,
        )
        self.session.add(approval)
        self.session.flush()
        self._audit(
            task_id,
            "APPROVAL_CREATED",
            requested_by,
            plan_id,
            plan.version,
            "PENDING",
            "Approval request created",
        )
        self.session.commit()
        return approval

    def approve(self, approval_id: str, *, actor: str, reason: str = "") -> ApprovalRecord:
        approval, task, plan = self._get_approval_binding(approval_id)
        if task.status == TaskStatus.CANCELLED.value:
            raise ApprovalError("Cancelled task cannot be approved")
        if approval.decision != "PENDING":
            raise ApprovalError(f"Approval is already decided: {approval.decision}")

        if task.status == TaskStatus.WAITING_APPROVAL.value:
            TaskService(self.session).transition_task(
                task.id,
                TaskStatus.RUNNING,
                actor=actor,
                reason="Approval granted; execution unlocked",
            )

        approval.decision = "APPROVED"
        approval.approver = actor
        approval.reason = reason or None
        self._audit(
            task.id,
            "APPROVED",
            actor,
            plan.id,
            plan.version,
            "APPROVED",
            reason or "Approval granted",
        )
        self.session.commit()
        return approval

    def reject(self, approval_id: str, *, actor: str, reason: str) -> ApprovalRecord:
        approval, task, plan = self._get_approval_binding(approval_id)
        if task.status == TaskStatus.CANCELLED.value:
            raise ApprovalError("Cancelled task cannot be rejected")
        if approval.decision != "PENDING":
            raise ApprovalError(f"Approval is already decided: {approval.decision}")

        approval.decision = "REJECTED"
        approval.approver = actor
        approval.reason = reason
        self._audit(
            task.id,
            "REJECTED",
            actor,
            plan.id,
            plan.version,
            "REJECTED",
            reason,
        )
        self.session.commit()
        return approval

    def cancel_task(self, task_id: str, *, actor: str, reason: str = "") -> TaskRecord:
        task = self.session.get(TaskRecord, task_id)
        if task is None:
            raise LookupError(f"Task not found: {task_id}")
        if task.status in {
            TaskStatus.SUCCESS.value,
            TaskStatus.FAILED.value,
        }:
            raise ApprovalError(f"Terminal task cannot be cancelled: {task.status}")
        if task.status != TaskStatus.CANCELLED.value:
            TaskService(self.session).transition_task(
                task_id,
                TaskStatus.CANCELLED,
                actor=actor,
                reason=reason or "Task cancelled",
            )
        pending = (
            self.session.query(ApprovalRecord)
            .filter_by(task_id=task_id, decision="PENDING")
            .all()
        )
        for approval in pending:
            approval.decision = "CANCELLED"
            approval.approver = actor
            approval.reason = reason or "Task cancelled"
        self._audit(
            task_id,
            "CANCELLED",
            actor,
            None,
            None,
            "CANCELLED",
            reason or "Task cancelled",
        )
        self.session.commit()
        return self.session.get(TaskRecord, task_id)

    def assert_execution_allowed(
        self,
        *,
        task_id: str,
        plan_id: str | None,
        plan_version: int | None,
    ) -> None:
        """Authorize an APPROVED_EXEC tool against an immutable plan version."""

        if not plan_id or plan_version is None:
            raise ApprovalError("Protected tool execution requires an approved plan")
        task, plan = self._validate_binding(task_id, plan_id, plan_version)
        if task.status == TaskStatus.CANCELLED.value:
            raise ApprovalError("Cancelled task cannot execute tools")
        approval = (
            self.session.query(ApprovalRecord)
            .filter_by(task_id=task_id, plan_id=plan_id, decision="APPROVED")
            .order_by(ApprovalRecord.created_at.desc())
            .first()
        )
        if approval is None:
            raise ApprovalError("No approved approval exists for this plan")
        if task.status != TaskStatus.RUNNING.value:
            raise ApprovalError(f"Task is not executable: {task.status}")

    def _validate_binding(
        self, task_id: str, plan_id: str, plan_version: int
    ) -> tuple[TaskRecord, PlanRecord]:
        task = self.session.get(TaskRecord, task_id)
        if task is None:
            raise LookupError(f"Task not found: {task_id}")
        plan = self.session.get(PlanRecord, plan_id)
        if plan is None or plan.task_id != task_id:
            raise ApprovalError("Plan is not bound to this task")
        if plan.version != plan_version:
            raise ApprovalError("Plan version does not match the approved plan")
        if plan.validation_status != "VALID":
            raise ApprovalError("Only a valid plan can be approved")
        return task, plan

    def _get_approval_binding(
        self, approval_id: str
    ) -> tuple[ApprovalRecord, TaskRecord, PlanRecord]:
        approval = self.session.get(ApprovalRecord, approval_id)
        if approval is None:
            raise LookupError(f"Approval not found: {approval_id}")
        task = self.session.get(TaskRecord, approval.task_id)
        if task is None:
            raise ApprovalError("Approval task no longer exists")
        plan = self.session.get(PlanRecord, approval.plan_id)
        if plan is None or plan.task_id != task.id:
            raise ApprovalError("Approval plan binding is invalid")
        return approval, task, plan

    def _audit(
        self,
        task_id: str,
        event_type: str,
        actor: str,
        plan_id: str | None,
        plan_version: int | None,
        decision: str,
        summary: str,
    ) -> None:
        payload = json.dumps(
            {
                "task_id": task_id,
                "plan_id": plan_id,
                "plan_version": plan_version,
                "decision": decision,
                "summary": summary[:2_000],
            },
            ensure_ascii=False,
        )
        self.session.add(
            AuditEventRecord(
                task_id=task_id,
                event_type=event_type,
                actor=actor,
                payload_summary=payload,
                correlation_id=str(uuid4()),
                created_at=datetime.now(timezone.utc),
            )
        )
