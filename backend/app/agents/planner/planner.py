"""Planner orchestration: generate, validate, persist, then request approval."""

import json
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from ...capabilities.models import CapabilityRequest
from ...capabilities.registry import build_default_capability_registry
from ...capabilities.resolver import CapabilityResolutionError, CapabilityResolver
from ...domain.states.task_state import TaskStatus
from ...services.plan_repository import PlanRepository
from ...services.task_service import TaskService
from ...storage.orm import AuditEventRecord
from ...tools.defaults import build_default_registry
from ...workspace.validator import WorkspaceValidator
from ..providers.base import (
    LLMProvider,
    LLMRequest,
    ProviderError,
    ProviderErrorCategory,
)
from .prompts import build_planning_prompt
from .schemas import PlanContract
from .validator import PlanValidationError, PlanValidator


class PlannerAgent:
    def __init__(self, session: Session, provider: LLMProvider, workspace_root: str):
        self.session = session
        self.provider = provider
        self.workspace_validator = WorkspaceValidator(workspace_root)
        self.validator = PlanValidator(self.workspace_validator)
        self.capability_registry = build_default_capability_registry()
        self.resolver = CapabilityResolver(
            self.capability_registry,
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
        self._audit_llm(
            task_id,
            "LLM_PLAN_REQUESTED",
            {
                "provider": self.provider.provider_name,
                "model": self.provider.model_name,
            },
        )
        self.session.commit()
        stage = "provider"
        try:
            request = LLMRequest(
                prompt=build_planning_prompt(
                    task.goal, self.capability_registry, context or {}
                ),
                context=context or {},
                output_schema=PlanContract.model_json_schema(),
            )
            response = self.provider.generate_plan(request)
            stage = "plan_validation"
            plan = self.validator.validate(dict(response.payload), task.workspace)
            stage = "capability_resolution"
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
            self._audit_llm(
                task_id,
                "LLM_PLAN_SUCCEEDED",
                {
                    "provider": response.provider,
                    "model": response.model,
                    "duration_ms": response.duration_ms,
                    "attempt_count": response.attempt_count,
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                    "validation_outcome": "VALID",
                },
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
        except (ProviderError, PlanValidationError, CapabilityResolutionError, ValueError) as exc:
            self.session.rollback()
            category = (
                exc.category
                if isinstance(exc, ProviderError)
                else ProviderErrorCategory.INVALID_RESPONSE
            )
            self._audit_llm(
                task_id,
                "LLM_PLAN_FAILED",
                {
                    "provider": self.provider.provider_name,
                    "model": self.provider.model_name,
                    "failure_category": category.value,
                    "validation_stage": stage,
                    "attempt_count": getattr(exc, "attempt_count", 1),
                    "duration_ms": getattr(exc, "duration_ms", 0),
                },
            )
            self.tasks.transition_task(
                task_id,
                TaskStatus.FAILED,
                actor="planner",
                reason=f"Planning failed: {category.value}",
            )
            raise
        self.tasks.transition_task(
            task_id,
            TaskStatus.WAITING_APPROVAL,
            reason=f"Plan version {record.version} validated",
        )
        return record

    def _audit_llm(self, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        self.session.add(
            AuditEventRecord(
                task_id=task_id,
                event_type=event_type,
                actor="planner",
                payload_summary=json.dumps(payload, ensure_ascii=False),
                correlation_id=str(uuid4()),
            )
        )
