"""Planner orchestration: generate, validate, persist, then request approval."""

from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from ...domain.states.task_state import TaskStatus
from ...services.plan_repository import PlanRepository
from ...services.task_service import TaskService
from ...storage.orm import AuditEventRecord
from ...workspace.validator import WorkspaceValidator
from ..providers.base import LLMProvider
from .prompts import build_planning_prompt
from .validator import PlanValidator


class PlannerAgent:
    def __init__(self, session: Session, provider: LLMProvider, workspace_root: str):
        self.session = session
        self.provider = provider
        self.workspace_validator = WorkspaceValidator(workspace_root)
        self.validator = PlanValidator(self.workspace_validator)
        self.tasks = TaskService(session)
        self.plans = PlanRepository(session)

    def create_plan(
        self, task_id: str, *, context: dict[str, Any] | None = None
    ):
        task = self.tasks.get_task(task_id)
        if task is None:
            raise LookupError(f"Task not found: {task_id}")
        if task.status != TaskStatus.CREATED:
            raise ValueError(f"Task is not ready for planning: {task.status}")

        self.tasks.transition_task(task_id, TaskStatus.PLANNING, reason="Planner started")
        raw = self.provider.generate_plan(
            build_planning_prompt(task.goal, context), context or {}
        )
        plan = self.validator.validate(raw, task.workspace)
        record = self.plans.create(
            task_id=task_id,
            version=self.plans.next_version(task_id),
            plan_json=plan.model_dump(mode="json"),
            validation_status="VALID",
        )
        self.session.add(
            AuditEventRecord(
                task_id=task_id,
                event_type="PLAN_CREATED",
                actor="planner",
                payload_summary=f"Validated plan version {record.version}",
                correlation_id=str(uuid4()),
            )
        )
        self.session.commit()
        self.tasks.transition_task(
            task_id,
            TaskStatus.WAITING_APPROVAL,
            reason=f"Plan version {record.version} validated",
        )
        return record
