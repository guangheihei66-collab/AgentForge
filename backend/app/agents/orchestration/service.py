"""Compose HUMAN approval and governed Agent Runtime execution."""

from collections.abc import Callable
from datetime import datetime, timezone
import json
from uuid import uuid4

from sqlalchemy.orm import Session

from ...agent_runtime import AgentRuntime, RuntimeResult
from ...approvals.service import ApprovalError, ApprovalService
from ...domain.states.task_state import TaskStatus
from ...services.plan_repository import PlanRepository
from ...services.task_service import TaskService
from ...storage.orm import ApprovalRecord, AuditEventRecord, TaskRecord, ToolExecutionRecord


class AgentExecutionInitiationError(RuntimeError):
    """Raised after a persisted Approval cannot start governed Runtime work."""


class AgentApprovalExecutionService:
    """Own the Agent Workspace Approval-to-Runtime continuation on the server."""

    def __init__(
        self,
        session: Session,
        runtime_factory: Callable[[str], AgentRuntime],
    ):
        self.session = session
        self.runtime_factory = runtime_factory

    def approve_and_execute(
        self,
        *,
        task_id: str,
        approval_id: str,
        plan_id: str,
        plan_version: int,
        actor: str,
    ) -> RuntimeResult:
        task, plan, approval = self._validate_command(
            task_id=task_id,
            approval_id=approval_id,
            plan_id=plan_id,
            plan_version=plan_version,
        )

        ApprovalService(self.session).approve(approval.id, actor=actor)
        execution_count_before = (
            self.session.query(ToolExecutionRecord)
            .filter_by(task_id=task.id)
            .count()
        )
        try:
            runtime = self.runtime_factory(task.id)
            return runtime.run(
                task_id=task.id,
                plan_id=plan.id,
                plan_version=plan.version,
            )
        except Exception as exc:
            execution_count_after = (
                self.session.query(ToolExecutionRecord)
                .filter_by(task_id=task.id)
                .count()
            )
            self._record_initiation_failure(
                task=task,
                plan_id=plan.id,
                plan_version=plan.version,
                execution_count_before=execution_count_before,
                execution_count_after=execution_count_after,
                error=exc,
            )
            raise AgentExecutionInitiationError(
                "Execution initiation failed"
            ) from None

    def _validate_command(
        self,
        *,
        task_id: str,
        approval_id: str,
        plan_id: str,
        plan_version: int,
    ) -> tuple[TaskRecord, object, ApprovalRecord]:
        task = self.session.get(TaskRecord, task_id)
        if task is None:
            raise LookupError(f"Task not found: {task_id}")

        plan = PlanRepository(self.session).highest_for_task(task_id)
        if plan is None or plan.validation_status != "VALID":
            raise LookupError("No valid current Plan exists for task")
        if plan.id != plan_id or plan.version != plan_version:
            raise ApprovalError("Approval does not match the current Plan")

        approval = self.session.get(ApprovalRecord, approval_id)
        if approval is None:
            raise LookupError(f"Approval not found: {approval_id}")
        if approval.task_id != task_id or approval.plan_id != plan.id:
            raise ApprovalError("Approval is not bound to this Task and current Plan")
        if approval.decision != "PENDING":
            raise ApprovalError(f"Approval is already decided: {approval.decision}")
        return task, plan, approval

    def _record_initiation_failure(
        self,
        *,
        task: TaskRecord,
        plan_id: str,
        plan_version: int,
        execution_count_before: int,
        execution_count_after: int,
        error: Exception,
    ) -> None:
        if (
            task.status == TaskStatus.RUNNING.value
            and execution_count_after == execution_count_before == 0
        ):
            TaskService(self.session).transition_task(
                task.id,
                TaskStatus.FAILED,
                actor="agent_orchestration",
                reason="Execution initiation failed",
            )
        payload = {
            "task_id": task.id,
            "plan_id": plan_id,
            "plan_version": plan_version,
            "error_category": type(error).__name__[:100],
            "execution_count_before": execution_count_before,
            "execution_count_after": execution_count_after,
            "summary": "Execution initiation failed",
        }
        self.session.add(
            AuditEventRecord(
                task_id=task.id,
                event_type="EXECUTION_INITIATION_FAILED",
                actor="agent_orchestration",
                payload_summary=json.dumps(payload, ensure_ascii=False),
                correlation_id=str(uuid4()),
                created_at=datetime.now(timezone.utc),
            )
        )
        self.session.commit()
