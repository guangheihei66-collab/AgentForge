"""Compose HUMAN approval and governed Agent Runtime execution."""

from collections.abc import Callable

from sqlalchemy.orm import Session

from ...agent_runtime import AgentRuntime, RuntimeResult
from ...approvals.service import ApprovalError, ApprovalService
from ...audit.provenance import (
    AGENT_APPROVE_AND_EXECUTE_COMMAND_RECEIVED,
    APPROVAL_COMMAND_FAILED,
    APPROVAL_COMMAND_SUCCEEDED,
    EXECUTION_INITIATION_FAILED,
    EXECUTION_INITIATION_REQUESTED,
    EXECUTION_INITIATION_STARTED,
    command_correlation_id,
    persist_provenance_event,
    safe_error_category,
)
from ...domain.states.task_state import TaskStatus
from ...services.plan_repository import PlanRepository
from ...services.task_service import TaskService
from ...storage.orm import AuditEventRecord, ApprovalRecord, TaskRecord, ToolExecutionRecord


class AgentExecutionInitiationError(RuntimeError):
    """Raised after a persisted Approval cannot start governed Runtime work."""


_COMPOSITE_PROVENANCE_EVENTS = {
    AGENT_APPROVE_AND_EXECUTE_COMMAND_RECEIVED,
    EXECUTION_INITIATION_REQUESTED,
    EXECUTION_INITIATION_STARTED,
    EXECUTION_INITIATION_FAILED,
}


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
        correlation_id: str | None = None,
    ) -> RuntimeResult:
        correlation_id = command_correlation_id(correlation_id)
        command_task = self.session.get(TaskRecord, task_id)
        prior_composite_attempt = (
            command_task is not None and self._has_composite_provenance(task_id)
        )
        if command_task is not None:
            persist_provenance_event(
                self.session,
                task_id=task_id,
                event_type=AGENT_APPROVE_AND_EXECUTE_COMMAND_RECEIVED,
                actor=actor,
                correlation_id=correlation_id,
                fields={
                    "approval_id": approval_id,
                    "command_kind": "AGENT_APPROVE_AND_EXECUTE",
                    "outcome": "RECEIVED",
                    "plan_id": plan_id,
                    "plan_version": plan_version,
                    "task_state": command_task.status,
                },
            )
        try:
            task, plan, approval, approval_reused = self._validate_command(
                task_id=task_id,
                approval_id=approval_id,
                plan_id=plan_id,
                plan_version=plan_version,
                prior_composite_attempt=prior_composite_attempt,
            )
        except Exception as exc:
            self._record_command_failure(
                task=command_task,
                approval_id=approval_id,
                plan_id=plan_id,
                plan_version=plan_version,
                actor=actor,
                correlation_id=correlation_id,
                error=exc,
            )
            raise

        if not approval_reused:
            try:
                ApprovalService(self.session).approve(approval.id, actor=actor)
            except Exception as exc:
                self._record_command_failure(
                    task=command_task,
                    approval_id=approval_id,
                    plan_id=plan_id,
                    plan_version=plan_version,
                    actor=actor,
                    correlation_id=correlation_id,
                    error=exc,
                )
                raise

        self._record_command_succeeded(
            task=task,
            approval=approval,
            plan_id=plan.id,
            plan_version=plan.version,
            actor=actor,
            correlation_id=correlation_id,
            approval_reused=approval_reused,
        )
        self._record_initiation_requested(
            task=task,
            approval_id=approval.id,
            plan_id=plan.id,
            plan_version=plan.version,
            correlation_id=correlation_id,
        )
        execution_count_before = (
            self.session.query(ToolExecutionRecord)
            .filter_by(task_id=task.id)
            .count()
        )
        try:
            runtime = self.runtime_factory(task.id)
            self._record_initiation_started(
                task=task,
                approval_id=approval.id,
                plan_id=plan.id,
                plan_version=plan.version,
                correlation_id=correlation_id,
            )
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
                approval_id=approval.id,
                correlation_id=correlation_id,
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
        prior_composite_attempt: bool,
    ) -> tuple[TaskRecord, object, ApprovalRecord, bool]:
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
        if approval.decision == "PENDING":
            return task, plan, approval, False
        if approval.decision != "APPROVED":
            raise ApprovalError(f"Approval is already decided: {approval.decision}")
        if task.status != TaskStatus.RUNNING.value:
            raise ApprovalError(f"Approval is already decided: {approval.decision}")
        if self.session.query(ToolExecutionRecord).filter_by(task_id=task_id).first() is not None:
            raise ApprovalError(f"Approval is already decided: {approval.decision}")
        if prior_composite_attempt:
            raise ApprovalError(f"Approval is already decided: {approval.decision}")
        document = approval.resolved_snapshot
        if not isinstance(document, dict):
            raise ApprovalError("Approval has no Project execution authority")
        from ...projects.service import ProjectService
        try:
            ProjectService(self.session).assert_authority(
                task.project_id, document.get("project_authority")
            )
        except (PermissionError, ValueError, TypeError) as exc:
            raise ApprovalError(
                "Archived or changed Project cannot resume approved execution"
            ) from exc
        return task, plan, approval, True

    def _has_composite_provenance(self, task_id: str) -> bool:
        return self.session.query(AuditEventRecord).filter(
            AuditEventRecord.task_id == task_id,
            AuditEventRecord.event_type.in_(_COMPOSITE_PROVENANCE_EVENTS),
        ).first() is not None

    def _record_initiation_failure(
        self,
        *,
        task: TaskRecord,
        plan_id: str,
        plan_version: int,
        execution_count_before: int,
        execution_count_after: int,
        approval_id: str,
        correlation_id: str,
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
            "approval_id": approval_id,
            "command_kind": "AGENT_APPROVE_AND_EXECUTE",
            "error_category": safe_error_category(error, initiation=True),
            "execution_count_before": execution_count_before,
            "execution_count_after": execution_count_after,
            "execution_initiation": "FAILED",
            "outcome": "FAILED",
            "plan_id": plan_id,
            "plan_version": plan_version,
            "summary": "Execution initiation failed",
            "task_id": task.id,
            "task_state": self.session.get(TaskRecord, task.id).status,
        }
        persist_provenance_event(
            self.session,
            task_id=task.id,
            event_type=EXECUTION_INITIATION_FAILED,
            actor="agent_orchestration",
            correlation_id=correlation_id,
            fields=payload,
        )

    def _record_command_failure(
        self,
        *,
        task: TaskRecord | None,
        approval_id: str,
        plan_id: str,
        plan_version: int,
        actor: str,
        correlation_id: str,
        error: Exception,
    ) -> None:
        if task is None:
            return
        self.session.rollback()
        current = self.session.get(TaskRecord, task.id)
        persist_provenance_event(
            self.session,
            task_id=task.id,
            event_type=APPROVAL_COMMAND_FAILED,
            actor=actor,
            correlation_id=correlation_id,
            fields={
                "approval_id": approval_id,
                "authority_validation": "FAILED",
                "command_kind": "AGENT_APPROVE_AND_EXECUTE",
                "error_category": safe_error_category(error),
                "execution_initiation": "NOT_REQUESTED",
                "outcome": "REJECTED",
                "plan_id": plan_id,
                "plan_version": plan_version,
                "task_state": current.status if current is not None else task.status,
            },
        )

    def _record_command_succeeded(
        self,
        *,
        task: TaskRecord,
        approval: ApprovalRecord,
        plan_id: str,
        plan_version: int,
        actor: str,
        correlation_id: str,
        approval_reused: bool,
    ) -> None:
        persist_provenance_event(
            self.session,
            task_id=task.id,
            event_type=APPROVAL_COMMAND_SUCCEEDED,
            actor=actor,
            correlation_id=correlation_id,
            fields={
                "approval_id": approval.id,
                "approval_persistence": "ALREADY_APPROVED" if approval_reused else "APPROVED",
                "approval_state": approval.decision,
                "authority_validation": "PASSED",
                "command_kind": "AGENT_APPROVE_AND_EXECUTE",
                "outcome": "APPROVAL_REUSED" if approval_reused else "APPROVAL_PERSISTED",
                "plan_id": plan_id,
                "plan_version": plan_version,
                "task_state": task.status,
            },
        )

    def _record_initiation_started(
        self,
        *,
        task: TaskRecord,
        approval_id: str,
        plan_id: str,
        plan_version: int,
        correlation_id: str,
    ) -> None:
        persist_provenance_event(
            self.session,
            task_id=task.id,
            event_type=EXECUTION_INITIATION_STARTED,
            actor="agent_orchestration",
            correlation_id=correlation_id,
            fields={
                "approval_id": approval_id,
                "command_kind": "AGENT_APPROVE_AND_EXECUTE",
                "execution_initiation": "STARTED",
                "outcome": "STARTED",
                "plan_id": plan_id,
                "plan_version": plan_version,
                "task_state": task.status,
            },
        )

    def _record_initiation_requested(
        self,
        *,
        task: TaskRecord,
        approval_id: str,
        plan_id: str,
        plan_version: int,
        correlation_id: str,
    ) -> None:
        persist_provenance_event(
            self.session,
            task_id=task.id,
            event_type=EXECUTION_INITIATION_REQUESTED,
            actor="agent_orchestration",
            correlation_id=correlation_id,
            fields={
                "approval_id": approval_id,
                "command_kind": "AGENT_APPROVE_AND_EXECUTE",
                "execution_initiation": "REQUESTED",
                "outcome": "REQUESTED",
                "plan_id": plan_id,
                "plan_version": plan_version,
                "task_state": task.status,
            },
        )
