"""Planner orchestration: generate, validate, persist, then request approval."""

import json
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from ...capabilities.models import CapabilityRequest
from ...capabilities.registry import build_default_capability_registry
from ...capabilities.resolver import CapabilityResolver
from ...domain.states.task_state import TaskStatus
from ...services.plan_repository import PlanRepository
from ...services.task_service import TaskService
from ...storage.orm import AuditEventRecord
from ...tools.defaults import build_default_registry
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
        self.resolver = CapabilityResolver(
            build_default_capability_registry(),
            build_default_registry(self.workspace_validator),
        )
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
            plan_json={**plan.model_dump(mode="json"), "resolved_steps": []},
            validation_status="VALID",
        )
        resolved_steps = []
        for step in plan.steps:
            request_payload = {
                "step_id": step.step_id,
                "capability_id": step.capability_id,
                "parameters": step.parameters,
            }
            self.session.add(
                AuditEventRecord(
                    task_id=task_id,
                    event_type="CAPABILITY_REQUESTED",
                    actor="planner",
                    payload_summary=json.dumps(request_payload, ensure_ascii=False),
                    correlation_id=str(uuid4()),
                )
            )
            snapshot = self.resolver.resolve(
                task_id=task_id,
                plan_id=record.id,
                plan_version=record.version,
                step_id=step.step_id,
                request=CapabilityRequest(step.capability_id, step.parameters),
            )
            serialized = snapshot.to_dict()
            resolved_steps.append(serialized)
            self.session.add(
                AuditEventRecord(
                    task_id=task_id,
                    event_type="CAPABILITY_RESOLVED",
                    actor="capability_resolver",
                    payload_summary=json.dumps(serialized, ensure_ascii=False),
                    correlation_id=str(uuid4()),
                )
            )
        record.plan_json = {
            **plan.model_dump(mode="json"),
            "resolved_steps": resolved_steps,
        }
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
