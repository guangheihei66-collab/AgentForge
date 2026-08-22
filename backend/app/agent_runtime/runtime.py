"""Deterministic Agent Runtime execution loop."""

from dataclasses import dataclass
import json
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from ..approvals.service import ApprovalService
from ..domain.states.task_state import TaskStatus
from ..services.task_service import TaskService
from ..storage.orm import AuditEventRecord, PlanRecord, TaskRecord
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


class AgentRuntime:
    """Run one approved plan through ToolGateway and observe each result."""

    def __init__(
        self,
        session: Session,
        executor: RuntimeExecutor,
        observer: RuntimeObserver | None = None,
    ):
        self.session = session
        self.executor = executor
        self.observer = observer or RuntimeObserver()

    def run(self, *, task_id: str, plan_id: str, plan_version: int) -> RuntimeResult:
        task = self.session.get(TaskRecord, task_id)
        plan = self.session.get(PlanRecord, plan_id)
        if task is None:
            raise LookupError(f"Task not found: {task_id}")
        if plan is None or plan.task_id != task_id:
            raise ValueError("Plan is not bound to this task")
        if plan.version != plan_version or plan.validation_status != "VALID":
            raise ValueError("Runtime requires the current valid plan version")

        # This check intentionally applies to every runtime plan, including SAFE_READ steps.
        ApprovalService(self.session).assert_execution_allowed(
            task_id=task_id,
            plan_id=plan_id,
            plan_version=plan_version,
        )
        if task.status != TaskStatus.RUNNING.value:
            raise ValueError(f"Runtime requires a RUNNING task: {task.status}")

        steps = list(plan.plan_json.get("steps", []))
        snapshot = RuntimeSnapshot()
        observations: list[RuntimeObservation] = []
        self._transition(snapshot, task_id, RuntimeState.RUNNING, "Runtime started for approved plan")

        for index, step in enumerate(steps):
            snapshot.current_step_id = str(step["step_id"])
            remaining = len(steps) - index - 1
            try:
                result = self.executor.execute(
                    task_id=task_id,
                    plan_id=plan_id,
                    plan_version=plan_version,
                    workspace=task.workspace,
                    step=step,
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
                snapshot,
                task_id,
                RuntimeState.OBSERVING,
                f"Observing result for step {step['step_id']}",
            )
            self._audit_observation(task_id, snapshot, step, result)
            observation = self.observer.observe(
                step=step,
                result=result,
                remaining_steps=remaining,
            )
            observations.append(observation)
            self._audit_decision(task_id, snapshot, observation)

            if observation.decision == RuntimeDecision.CONTINUE:
                snapshot.completed_steps += 1
                self._transition(
                    snapshot,
                    task_id,
                    RuntimeState.RUNNING,
                    observation.decision_summary,
                )
                continue

            if observation.decision == RuntimeDecision.COMPLETE:
                snapshot.completed_steps += 1
                TaskService(self.session).transition_task(
                    task_id,
                    TaskStatus.SUCCESS,
                    actor="agent_runtime",
                    reason=observation.decision_summary,
                )
                self._transition(
                    snapshot,
                    task_id,
                    RuntimeState.COMPLETED,
                    observation.decision_summary,
                )
                return RuntimeResult(
                    task_id=task_id,
                    plan_id=plan_id,
                    plan_version=plan_version,
                    state=snapshot.state,
                    decision=observation.decision,
                    completed_steps=snapshot.completed_steps,
                    observations=tuple(observations),
                )

            TaskService(self.session).transition_task(
                task_id,
                TaskStatus.FAILED,
                actor="agent_runtime",
                reason=observation.decision_summary,
            )
            self._transition(
                snapshot,
                task_id,
                RuntimeState.FAILED,
                observation.decision_summary,
            )
            return RuntimeResult(
                task_id=task_id,
                plan_id=plan_id,
                plan_version=plan_version,
                state=snapshot.state,
                decision=observation.decision,
                completed_steps=snapshot.completed_steps,
                observations=tuple(observations),
            )

        # Plan validation requires at least one step, but keep the invariant explicit.
        raise ValueError("Runtime cannot complete an empty plan")

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

    def _audit_observation(self, task_id: str, snapshot: RuntimeSnapshot, step, result) -> None:
        payload = {
            "step_id": str(step["step_id"]),
            "tool_name": str(step["tool"]),
            "execution_id": result.execution_id,
            "status": result.status,
            "tool_result_summary": (result.summary or "")[:2_000],
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
