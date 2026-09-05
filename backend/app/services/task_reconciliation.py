"""Fail-closed reconciliation of proven historical failed executions."""

import json
from dataclasses import dataclass
from threading import Lock

from sqlalchemy.orm import Session

from ..domain.states.task_state import TaskStatus
from ..storage.orm import ApprovalRecord, AuditEventRecord, PlanRecord, TaskRecord, ToolExecutionRecord
from .task_service import TaskService


RECONCILED = "HISTORICAL_RUNTIME_FAILURE_RECONCILED"
_locks_guard = Lock()
_task_locks: dict[str, Lock] = {}


@dataclass(frozen=True)
class ReconciliationStatus:
    task_id: str
    eligible: bool
    reason_code: str


class ReconciliationConflict(RuntimeError):
    def __init__(self, status: ReconciliationStatus):
        self.status = status
        super().__init__(status.reason_code)


def _lock_for(task_id: str) -> Lock:
    with _locks_guard:
        return _task_locks.setdefault(task_id, Lock())


class TaskReconciliationService:
    TERMINAL_EXECUTIONS = {"SUCCESS", "FAILED", "REJECTED", "CANCELLED"}

    def __init__(self, session: Session):
        self.session = session

    def eligibility(self, task_id: str) -> ReconciliationStatus:
        task = self.session.get(TaskRecord, task_id)
        if task is None:
            raise LookupError(f"Task not found: {task_id}")
        if task.status == TaskStatus.FAILED.value and self._was_reconciled(task_id):
            return ReconciliationStatus(task_id, False, "TASK_ALREADY_RECONCILED")
        if task.status != TaskStatus.RUNNING.value:
            return ReconciliationStatus(task_id, False, "TASK_NOT_RUNNING")

        executions = self.session.query(ToolExecutionRecord).filter_by(task_id=task_id).all()
        if any(item.status not in self.TERMINAL_EXECUTIONS for item in executions):
            return ReconciliationStatus(task_id, False, "ACTIVE_EXECUTION_EXISTS")
        if not executions or not any(item.status == "FAILED" for item in executions):
            return ReconciliationStatus(task_id, False, "NO_FAILED_EXECUTION")
        if self.session.query(ApprovalRecord).filter_by(task_id=task_id, decision="PENDING").count():
            return ReconciliationStatus(task_id, False, "PENDING_SUCCESSOR_APPROVAL")

        terminal_failure = self._terminal_failure(task_id)
        if terminal_failure is None:
            return ReconciliationStatus(task_id, False, "NO_TERMINAL_FAILURE_EVIDENCE")
        failure_event, failure_plan_version = terminal_failure
        later_activity = (
            self.session.query(AuditEventRecord)
            .filter(AuditEventRecord.task_id == task_id)
            .filter(AuditEventRecord.created_at > failure_event.created_at)
            .filter(
                AuditEventRecord.event_type.in_(
                    (
                        "RUNTIME_TRANSITION",
                        "RUNTIME_EXECUTION",
                        "RUNTIME_OBSERVATION",
                        "RUNTIME_DECISION",
                        "TOOL_EXECUTION",
                        "REPLAN_REQUESTED",
                    )
                )
            )
            .count()
        )
        if later_activity:
            return ReconciliationStatus(task_id, False, "RUNTIME_ACTIVITY_AFTER_FAILURE")
        if not self._has_replan_request(task_id):
            return ReconciliationStatus(task_id, False, "NO_REPLAN_FAILURE_EVIDENCE")
        successor = (
            self.session.query(PlanRecord)
            .filter(PlanRecord.task_id == task_id)
            .filter(PlanRecord.validation_status == "VALID")
            .filter(PlanRecord.version > failure_plan_version)
            .first()
        )
        if successor is not None:
            return ReconciliationStatus(task_id, False, "SUCCESSOR_PLAN_AWAITING_APPROVAL")
        return ReconciliationStatus(task_id, True, "ELIGIBLE_HISTORICAL_RUNTIME_FAILURE")

    def reconcile(self, task_id: str, *, actor: str) -> dict[str, object]:
        with _lock_for(task_id):
            status = self.eligibility(task_id)
            if status.reason_code == "TASK_ALREADY_RECONCILED":
                return self._result(task_id, "FAILED", "FAILED", False, status.reason_code)
            if not status.eligible:
                raise ReconciliationConflict(status)
            try:
                TaskService(self.session).transition_task(
                    task_id,
                    TaskStatus.FAILED,
                    actor=actor,
                    reason="Historical runtime failure reconciliation",
                    commit=False,
                )
                self.session.add(
                    AuditEventRecord(
                        task_id=task_id,
                        event_type="TASK_RECONCILED",
                        actor=actor,
                        payload_summary=json.dumps(
                            {
                                "previous_state": "RUNNING",
                                "new_state": "FAILED",
                                "reason_code": "HISTORICAL_RUNTIME_FAILURE_RECONCILIATION",
                                "source": "operator_maintenance",
                            },
                            sort_keys=True,
                        ),
                        correlation_id=self._correlation_id(task_id),
                    )
                )
                self.session.commit()
            except Exception:
                self.session.rollback()
                raise
            return self._result(task_id, "RUNNING", "FAILED", True, RECONCILED)

    def _terminal_failure(self, task_id: str) -> tuple[AuditEventRecord, int] | None:
        events = self.session.query(AuditEventRecord).filter_by(
            task_id=task_id, event_type="EXECUTION_INITIATION_FAILED"
        ).all()
        for event in reversed(events):
            try:
                payload = json.loads(event.payload_summary)
            except (TypeError, json.JSONDecodeError):
                continue
            if payload.get("error_category") == "RUNTIME_VALIDATION_FAILED" and int(payload.get("execution_count_after", 0)) > 0:
                version = payload.get("plan_version")
                if isinstance(version, int):
                    return event, version
        return None

    def _has_replan_request(self, task_id: str) -> bool:
        return self.session.query(AuditEventRecord).filter_by(
            task_id=task_id, event_type="REPLAN_REQUESTED"
        ).count() > 0

    def _was_reconciled(self, task_id: str) -> bool:
        return self.session.query(AuditEventRecord).filter_by(
            task_id=task_id, event_type="TASK_RECONCILED"
        ).count() > 0

    def _correlation_id(self, task_id: str) -> str:
        from uuid import uuid4
        return str(uuid4())

    @staticmethod
    def _result(task_id: str, previous: str, final: str, reconciled: bool, reason: str):
        return {"task_id": task_id, "previous_state": previous, "final_state": final,
                "reconciled": reconciled, "eligible": True, "reason_code": reason}
