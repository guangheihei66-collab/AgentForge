"""Approval lifecycle and protected execution authorization."""

from datetime import datetime, timezone
import json
from uuid import uuid4

from sqlalchemy.orm import Session

from ..capabilities.models import ResolvedExecutionSnapshot
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
            TaskStatus.RUNNING.value,
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

        resolved_snapshot = self._snapshot_document(plan)

        if task.status in {
            TaskStatus.PLANNING.value,
            TaskStatus.RUNNING.value,
        }:
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
            resolved_snapshot=resolved_snapshot,
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
        document = approval.resolved_snapshot
        if not isinstance(document, dict):
            raise ApprovalError("Approval has no Project execution authority")
        from ..projects.service import ProjectService
        try:
            ProjectService(self.session).assert_authority(
                task.project_id, document.get("project_authority")
            )
        except (PermissionError, ValueError, TypeError) as exc:
            raise ApprovalError(
                "Archived or changed Project cannot approve pending execution"
            ) from exc

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
        self._audit_snapshot_approved(task.id, approval, plan)
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

    def assert_snapshot_allowed(
        self, snapshot: ResolvedExecutionSnapshot
    ) -> ApprovalRecord:
        task, _ = self._validate_binding(
            snapshot.task_id, snapshot.plan_id, snapshot.plan_version
        )
        approval = (
            self.session.query(ApprovalRecord)
            .filter_by(
                task_id=snapshot.task_id,
                plan_id=snapshot.plan_id,
                decision="APPROVED",
            )
            .order_by(ApprovalRecord.created_at.desc())
            .first()
        )
        if approval is None or task.status != TaskStatus.RUNNING.value:
            raise ApprovalError("Resolved execution is not approved")
        document = approval.resolved_snapshot
        if not isinstance(document, dict) or document.get("schema_version") != 2:
            raise ApprovalError("Approval has no Project execution authority")
        from ..projects.service import ProjectService
        try:
            ProjectService(self.session).assert_authority(
                task.project_id, document.get("project_authority")
            )
        except (PermissionError, ValueError, TypeError) as exc:
            raise ApprovalError("Project execution authority has drifted") from exc
        approved = self._parse_approved_snapshots(approval)
        matches = [item for item in approved if item.step_id == snapshot.step_id]
        if len(matches) != 1 or matches[0] != snapshot:
            raise ApprovalError("Resolved execution snapshot does not match approval")
        return approval

    def _snapshot_document(self, plan: PlanRecord) -> dict:
        payload = plan.plan_json
        if payload.get("schema_version") != 2:
            raise ApprovalError("Plan has no resolved Phase 11.2 execution snapshot")
        steps = payload.get("steps")
        resolved = payload.get("resolved_steps")
        if not isinstance(steps, list) or not steps:
            raise ApprovalError("Resolved plan must contain steps")
        if not isinstance(resolved, list) or len(resolved) != len(steps):
            raise ApprovalError("Resolved plan snapshot count does not match steps")
        parsed: dict[str, ResolvedExecutionSnapshot] = {}
        try:
            for item in resolved:
                snapshot = ResolvedExecutionSnapshot.from_dict(item)
                if snapshot.step_id in parsed:
                    raise ApprovalError("Resolved plan contains duplicate step IDs")
                parsed[snapshot.step_id] = snapshot
        except ValueError as exc:
            raise ApprovalError(str(exc)) from exc
        ordered: list[dict] = []
        for step in steps:
            if not isinstance(step, dict) or not isinstance(step.get("step_id"), str):
                raise ApprovalError("Resolved plan step is invalid")
            snapshot = parsed.get(step["step_id"])
            if snapshot is None:
                raise ApprovalError("Resolved plan step has no snapshot")
            if (
                snapshot.task_id != plan.task_id
                or snapshot.plan_id != plan.id
                or snapshot.plan_version != plan.version
                or snapshot.capability_id != step.get("capability_id")
                or snapshot.parameters_dict() != step.get("parameters", {})
            ):
                raise ApprovalError("Resolved plan snapshot binding is invalid")
            ordered.append(snapshot.to_dict())
        if len(parsed) != len(ordered):
            raise ApprovalError("Resolved plan contains unmatched snapshots")
        task = self.session.get(TaskRecord, plan.task_id)
        authority = payload.get("project_authority")
        if task is None or not isinstance(authority, dict):
            raise ApprovalError("Plan has no Project execution authority")
        from ..projects.service import ProjectService
        try:
            ProjectService(self.session).assert_authority(task.project_id, authority)
        except (PermissionError, ValueError, TypeError) as exc:
            raise ApprovalError("Plan Project authority is invalid") from exc
        return {"schema_version": 2, "project_authority": authority, "steps": ordered}

    @staticmethod
    def _parse_approved_snapshots(
        approval: ApprovalRecord,
    ) -> tuple[ResolvedExecutionSnapshot, ...]:
        document = approval.resolved_snapshot
        if not isinstance(document, dict) or document.get("schema_version") != 2:
            raise ApprovalError("Approval has no resolved execution snapshot")
        steps = document.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ApprovalError("Approval resolved snapshot is invalid")
        try:
            return tuple(ResolvedExecutionSnapshot.from_dict(item) for item in steps)
        except (TypeError, ValueError) as exc:
            raise ApprovalError("Approval resolved snapshot is invalid") from exc

    def assert_project_execution_allowed(
        self, *, task_id: str, plan_id: str | None, plan_version: int | None,
        workspace: str, authority_fingerprint: str | None,
    ) -> ApprovalRecord:
        if not plan_id or plan_version is None or not authority_fingerprint:
            raise ApprovalError("Project execution requires approved authority")
        task, _ = self._validate_binding(task_id, plan_id, plan_version)
        approval = (
            self.session.query(ApprovalRecord)
            .filter_by(task_id=task_id, plan_id=plan_id, decision="APPROVED")
            .order_by(ApprovalRecord.created_at.desc()).first()
        )
        if approval is None or task.status != TaskStatus.RUNNING.value:
            raise ApprovalError("Project execution is not approved")
        document = approval.resolved_snapshot
        if not isinstance(document, dict) or document.get("schema_version") != 2:
            raise ApprovalError("Approval has no Project authority")
        from ..projects.service import ProjectService
        try:
            context = ProjectService(self.session).assert_authority(
                task.project_id, document.get("project_authority")
            )
        except (PermissionError, ValueError, TypeError) as exc:
            raise ApprovalError("Project execution authority has drifted") from exc
        from ..workspace.validator import WorkspaceValidator
        if (context.authority_fingerprint != authority_fingerprint or
                WorkspaceValidator.authority_path_key(workspace) != context.workspace_authority_key):
            raise ApprovalError("Project workspace authority does not match approval")
        return approval

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

    def _audit_snapshot_approved(
        self, task_id: str, approval: ApprovalRecord, plan: PlanRecord
    ) -> None:
        payload = json.dumps(
            {
                "approval_id": approval.id,
                "task_id": task_id,
                "plan_id": plan.id,
                "plan_version": plan.version,
                "resolved_snapshot": approval.resolved_snapshot,
            },
            ensure_ascii=False,
        )[:20_000]
        self.session.add(
            AuditEventRecord(
                task_id=task_id,
                event_type="EXECUTION_SNAPSHOT_APPROVED",
                actor=approval.approver,
                payload_summary=payload,
                correlation_id=str(uuid4()),
                created_at=datetime.now(timezone.utc),
            )
        )
