"""Deterministic Agent Runtime execution loop."""

from dataclasses import dataclass, replace
import json
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from ..agents.replanning.models import ReplanOutcomeStatus, StepSummary
from ..agents.replanning.service import ReplanningService
from ..approvals.service import ApprovalService
from ..capabilities.models import ResolvedExecutionSnapshot
from ..capabilities.registry import build_default_capability_registry
from ..capabilities.resolver import CapabilityResolver
from ..domain.states.task_state import TaskStatus
from ..services.task_service import TaskService
from ..storage.orm import AuditEventRecord, PlanRecord, TaskRecord
from ..projects.service import ProjectService
from .executor import RuntimeExecutor
from .observer import RuntimeObservation, RuntimeObserver
from .state import RuntimeDecision, RuntimeSnapshot, RuntimeState


@dataclass(frozen=True, slots=True)
class RuntimeResult:
    task_id: str
    plan_id: str
    plan_version: int
    state: RuntimeState
    decision: RuntimeDecision
    completed_steps: int
    observations: tuple[RuntimeObservation, ...]
    successor_plan_id: str | None = None
    successor_plan_version: int | None = None
    approval_id: str | None = None


class AgentRuntime:
    """Run one approved plan through ToolGateway and observe each result."""

    def __init__(
        self,
        session: Session,
        executor: RuntimeExecutor,
        resolver: CapabilityResolver | None = None,
        observer: RuntimeObserver | None = None,
        replanning_service: ReplanningService | None = None,
    ):
        self.session = session
        self.executor = executor
        self.resolver = resolver or CapabilityResolver(
            build_default_capability_registry(), executor.gateway.registry
        )
        self.observer = observer or RuntimeObserver()
        self.replanning_service = replanning_service

    def run(self, *, task_id: str, plan_id: str, plan_version: int) -> RuntimeResult:
        task = self.session.get(TaskRecord, task_id)
        plan = self.session.get(PlanRecord, plan_id)
        if task is None:
            raise LookupError(f"Task not found: {task_id}")
        if plan is None or plan.task_id != task_id:
            raise ValueError("Plan is not bound to this task")
        if plan.version != plan_version or plan.validation_status != "VALID":
            raise ValueError("Runtime requires the current valid plan version")

        projects = ProjectService(self.session)
        project_context = projects.execution_context_for_task(task_id)
        projects.assert_authority(
            task.project_id, plan.plan_json.get("project_authority")
        )

        payload = plan.plan_json
        if payload.get("schema_version") != 2:
            raise ValueError("Runtime requires a resolved schema version 2 plan")
        steps = payload.get("steps")
        resolved_items = payload.get("resolved_steps")
        if (
            not isinstance(steps, list)
            or not steps
            or not isinstance(resolved_items, list)
            or len(resolved_items) != len(steps)
        ):
            raise ValueError("Runtime requires one resolved snapshot per plan step")
        try:
            resolved = {
                item.step_id: item
                for item in (
                    ResolvedExecutionSnapshot.from_dict(raw)
                    for raw in resolved_items
                )
            }
        except (TypeError, ValueError) as exc:
            raise ValueError("Runtime received an invalid resolved snapshot") from exc
        if len(resolved) != len(resolved_items):
            raise ValueError("Runtime received duplicate resolved step IDs")

        approval_service = ApprovalService(self.session)
        approval_service.assert_execution_allowed(
            task_id=task_id,
            plan_id=plan_id,
            plan_version=plan_version,
        )
        if task.status != TaskStatus.RUNNING.value:
            raise ValueError(f"Runtime requires a RUNNING task: {task.status}")

        ordered: list[tuple[dict[str, Any], ResolvedExecutionSnapshot]] = []
        for step in steps:
            if not isinstance(step, dict) or "tool" in step or "action" in step:
                raise ValueError("Runtime rejects concrete-tool plan input")
            step_id = step.get("step_id")
            resolved_step = resolved.get(step_id)
            if resolved_step is None:
                raise ValueError("Runtime plan step is unresolved")
            if (
                resolved_step.task_id != task_id
                or resolved_step.plan_id != plan_id
                or resolved_step.plan_version != plan_version
                or resolved_step.capability_id != step.get("capability_id")
                or resolved_step.parameters_dict() != step.get("parameters", {})
            ):
                raise ValueError("Runtime resolved snapshot drifted from the plan")
            if resolved_step.capability_id not in project_context.allowed_capability_ids:
                raise PermissionError("Capability is not allowed by the Project")
            approval_service.assert_snapshot_allowed(resolved_step)
            self.resolver.verify(resolved_step)
            ordered.append((step, resolved_step))

        runtime_snapshot = RuntimeSnapshot()
        observations: list[RuntimeObservation] = []
        self._transition(runtime_snapshot, task_id, RuntimeState.RUNNING, "Runtime started for approved plan")
        if isinstance(plan.plan_json.get("replan_lineage"), dict):
            self._audit_event(
                task_id,
                "REPLAN_RESUMED",
                {
                    "plan_id": plan.id,
                    "plan_version": plan.version,
                    "previous_plan_id": plan.plan_json["replan_lineage"].get(
                        "previous_plan_id"
                    ),
                },
            )

        for index, (step, resolved_step) in enumerate(ordered):
            project_context = projects.execution_context_for_task(task_id)
            projects.assert_authority(
                task.project_id, plan.plan_json.get("project_authority")
            )
            runtime_snapshot.current_step_id = resolved_step.step_id
            remaining = len(ordered) - index - 1
            try:
                capability = self.resolver.capabilities.require(
                    resolved_step.capability_id
                )
                result = self.executor.execute(
                    task_id=task_id,
                    plan_id=plan_id,
                    plan_version=plan_version,
                    workspace=project_context.workspace_root,
                    project_authority_fingerprint=project_context.authority_fingerprint,
                    snapshot=resolved_step,
                    granted_permission=capability.required_permission,
                )
            except (PermissionError, LookupError) as exc:
                # Authorization and binding failures must remain visible to the caller.
                raise exc
            except Exception as exc:
                from ..tools.gateway import ToolExecutionResult

                result = ToolExecutionResult(
                    execution_id="",
                    status="FAILED",
                    summary=str(exc)[:2_000],
                )

            self._transition(
                runtime_snapshot,
                task_id,
                RuntimeState.OBSERVING,
                f"Observing result for step {step['step_id']}",
            )
            self._audit_execution(task_id, resolved_step, result)
            observation = self.observer.observe(
                snapshot=resolved_step,
                result=result,
                remaining_steps=remaining,
            )
            lineage = plan.plan_json.get("replan_lineage")
            if (
                observation.decision == RuntimeDecision.COMPLETE
                and isinstance(lineage, dict)
                and lineage.get("reason_code")
                == "TEST_FAILED_DIAGNOSTIC_AVAILABLE"
            ):
                observation = replace(
                    observation,
                    decision=RuntimeDecision.FAIL,
                    decision_summary=(
                        "NOT READY: test failure confirmed by project metadata"
                    ),
                )
            self._audit_observation(task_id, resolved_step, observation)
            observations.append(observation)
            self._audit_decision(task_id, runtime_snapshot, observation)

            if observation.decision == RuntimeDecision.CONTINUE:
                runtime_snapshot.completed_steps += 1
                self._transition(
                    runtime_snapshot,
                    task_id,
                    RuntimeState.RUNNING,
                    observation.decision_summary,
                )
                continue

            if observation.decision == RuntimeDecision.REPLAN:
                if self.replanning_service is None:
                    summary = "Replanning is unavailable"
                    TaskService(self.session).transition_task(
                        task_id,
                        TaskStatus.FAILED,
                        actor="agent_runtime",
                        reason=summary,
                    )
                    self._transition(
                        runtime_snapshot, task_id, RuntimeState.FAILED, summary
                    )
                    return RuntimeResult(
                        task_id,
                        plan_id,
                        plan_version,
                        RuntimeState.FAILED,
                        RuntimeDecision.FAIL,
                        runtime_snapshot.completed_steps,
                        tuple(observations),
                    )
                outcome = self.replanning_service.create_successor(
                    task_id=task_id,
                    current_plan_id=plan_id,
                    current_plan_version=plan_version,
                    observation=observation,
                    completed_steps=self._step_summaries(observations),
                    attempted_steps=index + 1,
                )
                if outcome.status != ReplanOutcomeStatus.WAITING_APPROVAL:
                    self._transition(
                        runtime_snapshot,
                        task_id,
                        RuntimeState.FAILED,
                        outcome.summary,
                    )
                    return RuntimeResult(
                        task_id,
                        plan_id,
                        plan_version,
                        RuntimeState.FAILED,
                        RuntimeDecision.FAIL,
                        runtime_snapshot.completed_steps,
                        tuple(observations),
                    )
                return RuntimeResult(
                    task_id=task_id,
                    plan_id=plan_id,
                    plan_version=plan_version,
                    state=RuntimeState.OBSERVING,
                    decision=RuntimeDecision.REPLAN,
                    completed_steps=runtime_snapshot.completed_steps,
                    observations=tuple(observations),
                    successor_plan_id=outcome.plan_id,
                    successor_plan_version=outcome.plan_version,
                    approval_id=outcome.approval_id,
                )

            if observation.decision == RuntimeDecision.COMPLETE:
                runtime_snapshot.completed_steps += 1
                TaskService(self.session).transition_task(
                    task_id,
                    TaskStatus.SUCCESS,
                    actor="agent_runtime",
                    reason=observation.decision_summary,
                )
                self._transition(
                    runtime_snapshot,
                    task_id,
                    RuntimeState.COMPLETED,
                    observation.decision_summary,
                )
                return RuntimeResult(
                    task_id=task_id,
                    plan_id=plan_id,
                    plan_version=plan_version,
                    state=runtime_snapshot.state,
                    decision=observation.decision,
                    completed_steps=runtime_snapshot.completed_steps,
                    observations=tuple(observations),
                )

            TaskService(self.session).transition_task(
                task_id,
                TaskStatus.FAILED,
                actor="agent_runtime",
                reason=observation.decision_summary,
            )
            self._transition(
                runtime_snapshot,
                task_id,
                RuntimeState.FAILED,
                observation.decision_summary,
            )
            return RuntimeResult(
                task_id=task_id,
                plan_id=plan_id,
                plan_version=plan_version,
                state=runtime_snapshot.state,
                decision=observation.decision,
                completed_steps=runtime_snapshot.completed_steps,
                observations=tuple(observations),
            )

        # Plan validation requires at least one step, but keep the invariant explicit.
        raise ValueError("Runtime cannot complete an empty plan")

    @staticmethod
    def _step_summaries(
        observations: list[RuntimeObservation],
    ) -> tuple[StepSummary, ...]:
        return tuple(
            StepSummary(
                capability_id=item.capability_id,
                parameters=dict(
                    item.execution_metadata.get("normalized_parameters", {})
                ),
                status=item.status,
                reason_code=item.reason_code.value,
                summary=item.result_summary[:500],
                evidence_refs=item.evidence_refs[:5],
            )
            for item in observations[-12:]
        )

    def _transition(
        self,
        snapshot: RuntimeSnapshot,
        task_id: str,
        state: RuntimeState,
        summary: str,
    ) -> None:
        previous = snapshot.state
        snapshot.transition(state, summary)
        payload = {
            "from": previous.value,
            "to": state.value,
            "summary": summary[:2_000],
            "current_step_id": snapshot.current_step_id,
            "completed_steps": snapshot.completed_steps,
        }
        self.session.add(
            AuditEventRecord(
                task_id=task_id,
                event_type="RUNTIME_TRANSITION",
                actor="agent_runtime",
                payload_summary=json.dumps(payload, ensure_ascii=False),
                correlation_id=str(uuid4()),
            )
        )
        self.session.commit()

    def _audit_observation(
        self,
        task_id: str,
        resolved: ResolvedExecutionSnapshot,
        observation: RuntimeObservation,
    ) -> None:
        payload = {
            "observation_id": observation.observation_id,
            "step_id": resolved.step_id,
            "capability_id": resolved.capability_id,
            "tool_id": resolved.resolved_tool_id,
            "registry_fingerprint": resolved.registry_fingerprint,
            "execution_id": observation.execution_id,
            "status": observation.status,
            "result_summary": observation.result_summary[:2_000],
            "evidence_refs": list(observation.evidence_refs[:5]),
            "reason_code": observation.reason_code.value,
            "retryable": observation.retryable,
            "replan_recommended": observation.replan_recommended,
            "decision": observation.decision.value,
            "created_at": observation.created_at.isoformat(),
        }
        self.session.add(
            AuditEventRecord(
                task_id=task_id,
                event_type="RUNTIME_OBSERVATION",
                actor="agent_runtime",
                payload_summary=json.dumps(payload, ensure_ascii=False),
                correlation_id=str(uuid4()),
            )
        )
        self.session.commit()

    def _audit_event(
        self, task_id: str, event_type: str, payload: dict[str, Any]
    ) -> None:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if len(serialized.encode("utf-8")) > 8 * 1024:
            raise ValueError("Runtime audit payload exceeds the size limit")
        self.session.add(
            AuditEventRecord(
                task_id=task_id,
                event_type=event_type,
                actor="agent_runtime",
                payload_summary=serialized,
                correlation_id=str(uuid4()),
            )
        )
        self.session.commit()

    def _audit_execution(
        self, task_id: str, resolved: ResolvedExecutionSnapshot, result
    ) -> None:
        payload = {
            **resolved.to_dict(),
            "execution_id": result.execution_id,
            "status": result.status,
        }
        self.session.add(
            AuditEventRecord(
                task_id=task_id,
                event_type="RUNTIME_EXECUTION",
                actor="agent_runtime",
                payload_summary=json.dumps(payload, ensure_ascii=False)[:20_000],
                correlation_id=str(uuid4()),
            )
        )
        self.session.commit()

    def _audit_decision(
        self, task_id: str, snapshot: RuntimeSnapshot, observation: RuntimeObservation
    ) -> None:
        payload = {
            "decision": observation.decision.value,
            "decision_summary": observation.decision_summary[:2_000],
            "execution_metadata": observation.execution_metadata,
        }
        self.session.add(
            AuditEventRecord(
                task_id=task_id,
                event_type="RUNTIME_DECISION",
                actor="agent_runtime",
                payload_summary=json.dumps(payload, ensure_ascii=False),
                correlation_id=str(uuid4()),
            )
        )
        self.session.commit()
