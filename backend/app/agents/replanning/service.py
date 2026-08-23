"""Governed creation and recovery of immutable successor plan versions."""

from datetime import datetime, timezone
import json
from threading import RLock
from uuid import uuid4

from sqlalchemy.orm import Session
from pydantic import ValidationError

from ...agent_runtime.observer import RuntimeObservation
from ...approvals.service import ApprovalError, ApprovalService
from ...capabilities.models import CapabilityRequest
from ...capabilities.registry import build_default_capability_registry
from ...capabilities.resolver import CapabilityResolutionError, CapabilityResolver
from ...domain.states.task_state import TaskStatus
from ...services.plan_repository import PlanRepository
from ...storage.orm import ApprovalRecord, AuditEventRecord, PlanRecord, TaskRecord
from ...tools.defaults import build_default_registry
from ...workspace.validator import WorkspaceValidator
from ...projects.service import ProjectService
from ..planner.validator import PlanValidationError, PlanValidator
from ..providers.base import LLMProvider, LLMRequest, ProviderError
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
        self, session: Session, provider: LLMProvider
    ) -> None:
        self.session = session
        self.provider = provider
        self.capability_registry = build_default_capability_registry()
        self.projects = ProjectService(session, self.capability_registry)
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
        project_context = self.projects.execution_context_for_task(task_id)
        self.projects.assert_authority(
            task.project_id, current.plan_json.get("project_authority")
        )
        effective_registry = self.capability_registry.subset(
            project_context.allowed_capability_ids
        )
        self.workspace_validator = WorkspaceValidator.for_project(
            project_context.workspace_root
        )
        self.validator = PlanValidator(self.workspace_validator)
        self.resolver = CapabilityResolver(
            effective_registry, build_default_registry(self.workspace_validator)
        )

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
        persisted_step_count = sum(
            len(plan.plan_json.get("steps", []))
            for plan in self.session.query(PlanRecord).filter_by(task_id=task_id).all()
        )
        policy = ReplanPolicy().evaluate(
            ReplanPolicyInput(
                task_status=TaskStatus(task.status),
                observation=observation,
                current_plan_id=current.id,
                current_plan_version=current.version,
                replan_count=self.plans.count_replans(task_id),
                total_steps=max(attempted_steps, persisted_step_count),
                current_plan_fingerprint=current_fingerprint,
                previous_plan_fingerprints=previous_fingerprints,
                current_progress_fingerprint=current_progress,
                previous_progress_fingerprint=previous_progress,
                repeated_failure_count=repeated,
            )
        )
        if policy.decision.value != "REPLAN":
            return self._reject(
                task_id,
                policy.reason_code.value,
                "Replan policy denied request",
                transition_failed=True,
            )

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
        self.session.commit()
        prompt = build_replan_prompt(context, effective_registry)
        try:
            response = self.provider.generate_replan(
                LLMRequest(
                    prompt=prompt,
                    context={},
                    output_schema=ReplanProposal.model_json_schema(),
                )
            )
        except ProviderError as exc:
            return self._reject(
                task_id,
                exc.category.value,
                "Replan provider failed",
                transition_failed=True,
            )
        self.session.expire_all()
        refreshed_task = self.session.get(TaskRecord, task_id)
        if refreshed_task is None or refreshed_task.status == TaskStatus.CANCELLED.value:
            return self._reject(
                task_id,
                "CANCELLED",
                "Task was cancelled during replanning",
                transition_failed=False,
            )
        project_context = self.projects.execution_context_for_task(task_id)
        self.projects.assert_authority(
            refreshed_task.project_id, current.plan_json.get("project_authority")
        )
        try:
            proposal = ReplanProposal.model_validate(dict(response.payload))
            if len(proposal.revised_remaining_steps) > policy.remaining_steps:
                raise ValueError("Replan proposal exceeds remaining step budget")
            validated = self.validator.validate(
                {
                    "schema_version": 2,
                    "summary": proposal.decision_summary,
                    "steps": [
                        step.model_dump(mode="json")
                        for step in proposal.revised_remaining_steps
                    ],
                },
                project_context.workspace_root,
            )
            proposed_requests = [
                CapabilityRequest(step.capability_id, step.parameters)
                for step in validated.steps
            ]
            proposal_fingerprint = canonical_plan_fingerprint(
                proposed_requests, self.resolver
            )
            if (
                proposal_fingerprint == current_fingerprint
                or proposal_fingerprint in previous_fingerprints
            ):
                raise ValueError("Replan proposal is duplicate/no-progress")
        except (
            ValidationError,
            PlanValidationError,
            CapabilityResolutionError,
            LookupError,
            TypeError,
            ValueError,
        ):
            return self._reject(
                task_id,
                "INVALID_RESPONSE",
                "Replan proposal failed validation",
                transition_failed=True,
            )

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
            try:
                resolved = [
                    self.resolver.resolve(
                        task_id=task_id,
                        plan_id=record.id,
                        plan_version=next_version,
                        step_id=step.step_id,
                        request=CapabilityRequest(
                            step.capability_id, step.parameters
                        ),
                    ).to_dict()
                    for step in validated.steps
                ]
            except (CapabilityResolutionError, LookupError, ValueError):
                return self._reject(
                    task_id,
                    "CAPABILITY_RESOLUTION_FAILED",
                    "Replan capability resolution failed",
                    transition_failed=True,
                )
            lineage = {
                "original_plan_id": self._original_plan_id(current),
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
                "project_authority": project_context.authority_snapshot().to_dict(),
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
        project_context = self.projects.execution_context_for_task(task_id)
        self.projects.assert_authority(
            task.project_id, plan.plan_json.get("project_authority")
        )
        effective_registry = self.capability_registry.subset(
            project_context.allowed_capability_ids
        )
        validator = WorkspaceValidator.for_project(project_context.workspace_root)
        self.resolver = CapabilityResolver(
            effective_registry, build_default_registry(validator)
        )
        incomplete_requests = (
            self.session.query(AuditEventRecord)
            .filter_by(task_id=task_id, event_type="REPLAN_REQUESTED")
            .all()
        )
        for event in incomplete_requests:
            try:
                requested = json.loads(event.payload_summary)
            except (TypeError, json.JSONDecodeError):
                raise ValueError("Replan recovery found malformed request state") from None
            if requested.get("plan_id") == plan.id:
                raise ValueError("Replan recovery found an incomplete request")
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
        if executable:
            snapshots = plan.plan_json.get("resolved_steps")
            if not isinstance(snapshots, list) or not snapshots:
                raise ValueError("Authoritative plan has no resolved snapshots")
            from ...capabilities.models import ResolvedExecutionSnapshot

            for raw in snapshots:
                snapshot = ResolvedExecutionSnapshot.from_dict(raw)
                ApprovalService(self.session).assert_snapshot_allowed(snapshot)
                self.resolver.verify(snapshot)
        return AuthoritativePlan(
            plan.id,
            plan.version,
            approval.id if approval else None,
            approval.decision if approval else None,
            executable,
        )

    def _reject(
        self,
        task_id: str,
        reason_code: str,
        summary: str,
        *,
        transition_failed: bool,
    ) -> ReplanOutcome:
        self.session.rollback()
        self._audit(
            task_id,
            "REPLAN_REJECTED",
            {"reason_code": reason_code, "summary": summary[:500]},
        )
        if transition_failed:
            from ...services.task_service import TaskService

            TaskService(self.session).transition_task(
                task_id,
                TaskStatus.FAILED,
                actor="replanning_service",
                reason=f"{summary}: {reason_code}",
            )
        else:
            self.session.commit()
        return ReplanOutcome(
            ReplanOutcomeStatus.FAILED,
            task_id,
            None,
            None,
            None,
            reason_code,
            summary,
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
