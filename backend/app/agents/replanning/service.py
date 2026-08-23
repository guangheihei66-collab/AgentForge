"""Governed creation and recovery of immutable successor plan versions."""

from datetime import datetime, timezone
import json
from threading import RLock
from uuid import uuid4

from sqlalchemy.orm import Session

from ...agent_runtime.observer import RuntimeObservation
from ...approvals.service import ApprovalError, ApprovalService
from ...capabilities.models import CapabilityRequest
from ...capabilities.registry import build_default_capability_registry
from ...capabilities.resolver import CapabilityResolver
from ...domain.states.task_state import TaskStatus
from ...services.plan_repository import PlanRepository
from ...storage.orm import ApprovalRecord, AuditEventRecord, PlanRecord, TaskRecord
from ...tools.defaults import build_default_registry
from ...workspace.validator import WorkspaceValidator
from ..planner.validator import PlanValidator
from ..providers.base import LLMProvider, LLMRequest
from .models import (
    AuthoritativePlan,
    EvidenceSummary,
    ReplanContext,
    ReplanOutcome,
    ReplanOutcomeStatus,
    ReplanPolicyInput,
    ReplanProposal,
    StepSummary,
)
from .policy import ReplanPolicy, canonical_plan_fingerprint, progress_fingerprint
from .prompts import build_replan_prompt


_REPLAN_LOCK = RLock()
MAX_AUDIT_BYTES = 8 * 1024


class ReplanningService:
    def __init__(
        self, session: Session, provider: LLMProvider, workspace_root: str
    ) -> None:
        self.session = session
        self.provider = provider
        self.workspace_validator = WorkspaceValidator(workspace_root)
        self.validator = PlanValidator(self.workspace_validator)
        self.capability_registry = build_default_capability_registry()
        self.resolver = CapabilityResolver(
            self.capability_registry,
            build_default_registry(self.workspace_validator),
        )
        self.plans = PlanRepository(session)

    def create_successor(
        self,
        *,
        task_id: str,
        current_plan_id: str,
        current_plan_version: int,
        observation: RuntimeObservation,
        completed_steps: tuple[StepSummary, ...],
        attempted_steps: int,
    ) -> ReplanOutcome:
        task = self.session.get(TaskRecord, task_id)
        current = self.session.get(PlanRecord, current_plan_id)
        highest = self.plans.highest_for_task(task_id)
        if task is None or current is None or current.task_id != task_id:
            raise ValueError("Replan task/plan binding is invalid")
        if (
            current.version != current_plan_version
            or highest is None
            or highest.id != current.id
        ):
            raise ValueError("Replan request uses a stale plan version")
        if task.status != TaskStatus.RUNNING.value:
            raise ValueError("Replan task is not running")

        current_requests = self._requests(current)
        current_fingerprint = canonical_plan_fingerprint(
            current_requests, self.resolver
        )
        current_progress = progress_fingerprint(
            completed_steps,
            observation.reason_code,
            observation.evidence_refs,
            current_fingerprint,
        )
        previous_fingerprints = tuple(
            plan.plan_json.get("replan_lineage", {}).get("plan_fingerprint", "")
            for plan in self.session.query(PlanRecord).filter_by(task_id=task_id).all()
            if isinstance(plan.plan_json.get("replan_lineage"), dict)
        )
        previous_progress = (
            current.plan_json.get("replan_lineage", {}).get("progress_fingerprint")
            if isinstance(current.plan_json.get("replan_lineage"), dict)
            else None
        )
        repeated = sum(
            step.capability_id == observation.capability_id
            and step.reason_code == observation.reason_code.value
            for step in completed_steps
        )
        policy = ReplanPolicy().evaluate(
            ReplanPolicyInput(
                task_status=TaskStatus(task.status),
                observation=observation,
                current_plan_id=current.id,
                current_plan_version=current.version,
                replan_count=self.plans.count_replans(task_id),
                total_steps=attempted_steps,
                current_plan_fingerprint=current_fingerprint,
                previous_plan_fingerprints=previous_fingerprints,
                current_progress_fingerprint=current_progress,
                previous_progress_fingerprint=previous_progress,
                repeated_failure_count=repeated,
            )
        )
        if policy.decision.value != "REPLAN":
            raise ValueError(f"Replan policy denied request: {policy.reason_code.value}")

        evidence = tuple(
            EvidenceSummary(ref, self._evidence_summary(ref, completed_steps), None)
            for ref in observation.evidence_refs[:5]
        )
        context = ReplanContext.bounded(
            user_goal=task.goal,
            original_plan_id=self._original_plan_id(current),
            current_plan_id=current.id,
            current_plan_version=current.version,
            remaining_plan_summary=(),
            completed_step_summaries=completed_steps,
            latest_observation=observation,
            evidence_summaries=evidence,
            remaining_step_budget=policy.remaining_steps,
            remaining_replan_budget=policy.remaining_replans,
        )
        self._audit(task_id, "REPLAN_REQUESTED", {
            "plan_id": current.id,
            "plan_version": current.version,
            "observation_id": observation.observation_id,
            "reason_code": observation.reason_code.value,
        })
        prompt = build_replan_prompt(context, self.capability_registry)
        response = self.provider.generate_replan(
            LLMRequest(
                prompt=prompt,
                context={},
                output_schema=ReplanProposal.model_json_schema(),
            )
        )
        proposal = ReplanProposal.model_validate(dict(response.payload))
        if len(proposal.revised_remaining_steps) > policy.remaining_steps:
            raise ValueError("Replan proposal exceeds remaining step budget")
        validated = self.validator.validate(
            {
                "schema_version": 2,
                "summary": proposal.decision_summary,
                "steps": [step.model_dump(mode="json") for step in proposal.revised_remaining_steps],
            },
            task.workspace,
        )
        proposed_requests = [
            CapabilityRequest(step.capability_id, step.parameters)
            for step in validated.steps
        ]
        proposal_fingerprint = canonical_plan_fingerprint(
            proposed_requests, self.resolver
        )
        if proposal_fingerprint == current_fingerprint or proposal_fingerprint in previous_fingerprints:
            raise ValueError("Replan proposal is duplicate/no-progress")

        with _REPLAN_LOCK:
            highest = self.plans.highest_for_task(task_id)
            if highest is None or highest.id != current.id:
                raise ValueError("Replan request became stale")
            next_version = current.version + 1
            record = self.plans.create(
                task_id=task_id,
                version=next_version,
                plan_json={**validated.model_dump(mode="json"), "resolved_steps": []},
                validation_status="VALID",
            )
            resolved = [
                self.resolver.resolve(
                    task_id=task_id,
                    plan_id=record.id,
                    plan_version=next_version,
                    step_id=step.step_id,
                    request=CapabilityRequest(step.capability_id, step.parameters),
                ).to_dict()
                for step in validated.steps
            ]
            lineage = {
                "previous_plan_id": current.id,
                "previous_plan_version": current.version,
                "triggering_observation_id": observation.observation_id,
                "triggering_execution_id": observation.execution_id,
                "reason_code": observation.reason_code.value,
                "reason_summary": observation.decision_summary[:500],
                "plan_fingerprint": proposal_fingerprint,
                "progress_fingerprint": current_progress,
                "replan_ordinal": self.plans.count_replans(task_id) + 1,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            record.plan_json = {
                **validated.model_dump(mode="json"),
                "resolved_steps": resolved,
                "replan_lineage": lineage,
            }
            self._audit(task_id, "REPLAN_PROPOSED", {
                "provider": response.provider,
                "model": response.model,
                "capabilities": [step.capability_id for step in validated.steps],
                "duration_ms": response.duration_ms,
                "attempt_count": response.attempt_count,
            })
            self._audit(task_id, "PLAN_VERSION_CREATED", {
                "plan_id": record.id,
                "plan_version": record.version,
                "previous_plan_id": current.id,
                "reason_code": observation.reason_code.value,
            })
            self.session.commit()
            approval = ApprovalService(self.session).create_request(
                task_id=task_id,
                plan_id=record.id,
                plan_version=record.version,
                requested_by="replanning_service",
            )
            self._audit(task_id, "REPLAN_APPROVAL_REQUIRED", {
                "plan_id": record.id,
                "plan_version": record.version,
                "approval_id": approval.id,
            })
            self.session.commit()
        return ReplanOutcome(
            ReplanOutcomeStatus.WAITING_APPROVAL,
            task_id,
            record.id,
            record.version,
            approval.id,
            observation.reason_code.value,
            "Successor plan requires fresh approval",
        )

    def authoritative_plan(self, task_id: str) -> AuthoritativePlan:
        task = self.session.get(TaskRecord, task_id)
        plan = self.plans.highest_for_task(task_id)
        if task is None or plan is None or plan.validation_status != "VALID":
            raise ValueError("No authoritative valid plan exists")
        approval = (
            self.session.query(ApprovalRecord)
            .filter_by(task_id=task_id, plan_id=plan.id)
            .order_by(ApprovalRecord.created_at.desc())
            .first()
        )
        executable = bool(
            approval
            and approval.decision == "APPROVED"
            and task.status == TaskStatus.RUNNING.value
        )
        return AuthoritativePlan(
            plan.id,
            plan.version,
            approval.id if approval else None,
            approval.decision if approval else None,
            executable,
        )

    @staticmethod
    def _requests(plan: PlanRecord) -> list[CapabilityRequest]:
        return [
            CapabilityRequest(step["capability_id"], step.get("parameters", {}))
            for step in plan.plan_json.get("steps", [])
        ]

    @staticmethod
    def _original_plan_id(plan: PlanRecord) -> str:
        lineage = plan.plan_json.get("replan_lineage")
        return lineage.get("original_plan_id", plan.id) if isinstance(lineage, dict) else plan.id

    @staticmethod
    def _evidence_summary(ref: str, steps: tuple[StepSummary, ...]) -> str:
        for step in steps:
            if ref in step.evidence_refs:
                return step.summary[:500]
        return "Referenced execution evidence"

    def _audit(self, task_id: str, event_type: str, payload: dict) -> None:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if len(serialized.encode("utf-8")) > MAX_AUDIT_BYTES:
            raise ValueError("Replan audit payload exceeds the size limit")
        self.session.add(
            AuditEventRecord(
                task_id=task_id,
                event_type=event_type,
                actor="replanning_service",
                payload_summary=serialized,
                correlation_id=str(uuid4()),
            )
        )
