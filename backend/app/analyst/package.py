"""Build the bounded, read-only fact package supplied to the Analyst."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import re
from typing import Any, Callable

from sqlalchemy.orm import Session

from ..storage.orm import (
    AuditEventRecord,
    EvidenceRecord,
    PlanRecord,
    ProjectRecord,
    TaskRecord,
    ToolExecutionRecord,
)


MAX_PACKAGE_BYTES = 32 * 1024
MAX_RECORDS = 24
MAX_PLAN_STEPS = 24
MAX_TEXT = 1_000
MAX_GOAL = 3_000

_SENSITIVE_KEY = re.compile(
    r"(?:api[_-]?key|authorization|cookie|password|secret|token)", re.IGNORECASE
)
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)(api[_-]?key|authorization|cookie|password|secret|token)\s*[:=]\s*[^\s,;]+"
)


class EvidencePackageError(ValueError):
    """A safe failure while assembling bounded persisted facts."""


def _redact_text(value: Any, limit: int = MAX_TEXT) -> str:
    if value is None:
        return ""
    text = str(value)
    text = _SENSITIVE_ASSIGNMENT.sub(r"\1=[REDACTED]", text)
    return text[:limit]


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _safe_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 3:
        return "[TRUNCATED]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _redact_text(value, 500)
    if isinstance(value, list):
        return [_safe_value(item, depth=depth + 1) for item in value[:16]]
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in list(value.items())[:16]:
            if not isinstance(key, str) or _SENSITIVE_KEY.search(key):
                continue
            safe[key[:128]] = _safe_value(item, depth=depth + 1)
        return safe
    return _redact_text(value, 500)


def _parse_payload(value: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _bounded_records(
    records: list[Any], mapper: Callable[[Any], dict[str, Any] | None]
) -> tuple[list[dict[str, Any]], bool]:
    ordered = records[-MAX_RECORDS:]
    result = [mapped for record in ordered if (mapped := mapper(record)) is not None]
    return result, len(records) > MAX_RECORDS


@dataclass(frozen=True, slots=True)
class EvidencePackage:
    task: dict[str, Any]
    project: dict[str, Any]
    plan: dict[str, Any]
    executions: tuple[dict[str, Any], ...]
    observations: tuple[dict[str, Any], ...]
    evidence: tuple[dict[str, Any], ...]
    lifecycle: dict[str, Any]
    limitations: tuple[str, ...]
    truncated: bool

    @property
    def evidence_ids(self) -> frozenset[str]:
        return frozenset(item["id"] for item in self.evidence)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "project": self.project,
            "plan": self.plan,
            "executions": list(self.executions),
            "observations": list(self.observations),
            "evidence": list(self.evidence),
            "lifecycle": self.lifecycle,
            "limitations": list(self.limitations),
            "truncated": self.truncated,
        }

    def serialized(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


def _map_execution(record: ToolExecutionRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "tool_name": record.tool_name,
        "action": record.action,
        "status": record.status,
        "result_summary": _redact_text(record.result_summary),
        "artifact_path": _redact_text(record.artifact_path, 500) or None,
        "content_hash": _redact_text(record.content_hash, 128) or None,
        "started_at": _iso(record.started_at),
        "finished_at": _iso(record.finished_at),
    }


def _map_evidence(record: EvidenceRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "summary": _redact_text(record.summary),
        "artifact_path": _redact_text(record.artifact_path, 500) or None,
        "content_hash": _redact_text(record.content_hash, 128) or None,
        "created_at": _iso(record.created_at),
    }


def _map_observation(record: AuditEventRecord) -> dict[str, Any] | None:
    payload = _parse_payload(record.payload_summary)
    if payload is None:
        return None
    refs = payload.get("evidence_refs")
    refs = [str(item)[:128] for item in refs[:5] if isinstance(item, str)] if isinstance(refs, list) else []
    return {
        "id": _redact_text(payload.get("observation_id"), 128),
        "step_id": _redact_text(payload.get("step_id"), 128),
        "capability_id": _redact_text(payload.get("capability_id"), 128),
        "tool_id": _redact_text(payload.get("tool_id"), 128),
        "execution_id": _redact_text(payload.get("execution_id"), 128),
        "status": _redact_text(payload.get("status"), 32),
        "result_summary": _redact_text(payload.get("result_summary")),
        "evidence_refs": refs,
        "reason_code": _redact_text(payload.get("reason_code"), 64),
        "decision": _redact_text(payload.get("decision"), 32),
        "retryable": bool(payload.get("retryable", False)),
        "replan_recommended": bool(payload.get("replan_recommended", False)),
        "created_at": _iso(record.created_at),
    }


def _map_transition(record: AuditEventRecord) -> dict[str, Any] | None:
    payload = _parse_payload(record.payload_summary)
    if payload is None:
        return None
    return {
        "from": _redact_text(payload.get("from"), 32),
        "to": _redact_text(payload.get("to"), 32),
        "summary": _redact_text(payload.get("summary")),
        "completed_steps": payload.get("completed_steps", 0)
        if isinstance(payload.get("completed_steps", 0), int)
        else 0,
        "created_at": _iso(record.created_at),
    }


def _map_plan(plan: PlanRecord) -> dict[str, Any]:
    raw = plan.plan_json if isinstance(plan.plan_json, dict) else {}
    steps: list[dict[str, Any]] = []
    resolved_by_step = {
        item.get("step_id"): item
        for item in raw.get("resolved_steps", [])
        if isinstance(item, dict) and isinstance(item.get("step_id"), str)
    }
    for item in raw.get("steps", [])[:MAX_PLAN_STEPS]:
        if not isinstance(item, dict):
            continue
        resolved = resolved_by_step.get(item.get("step_id"), {})
        steps.append(
            {
                "step_id": _redact_text(item.get("step_id"), 128),
                "capability_id": _redact_text(item.get("capability_id"), 128),
                "parameters": _safe_value(item.get("parameters", {})),
                "resolved_tool_id": _redact_text(resolved.get("resolved_tool_id"), 128),
                "resolved_action": _redact_text(resolved.get("resolved_action"), 128),
                "registry_fingerprint": _redact_text(
                    resolved.get("registry_fingerprint"), 128
                ),
            }
        )
    return {
        "id": plan.id,
        "version": plan.version,
        "validation_status": plan.validation_status,
        "summary": _redact_text(raw.get("summary")),
        "steps": steps,
    }


def build_evidence_package(
    session: Session,
    *,
    task_id: str,
    plan_id: str,
    plan_version: int,
) -> EvidencePackage:
    """Collect bounded persisted facts for one authoritative terminal plan."""

    task = session.get(TaskRecord, task_id)
    plan = session.get(PlanRecord, plan_id)
    if task is None:
        raise EvidencePackageError("TASK_NOT_FOUND")
    if plan is None or plan.task_id != task_id or plan.version != plan_version:
        raise EvidencePackageError("PLAN_BINDING_INVALID")
    if plan.validation_status != "VALID":
        raise EvidencePackageError("PLAN_NOT_VALID")
    project = session.get(ProjectRecord, task.project_id) if task.project_id else None
    if project is None:
        raise EvidencePackageError("PROJECT_NOT_FOUND")

    executions = (
        session.query(ToolExecutionRecord)
        .filter_by(task_id=task_id)
        .order_by(ToolExecutionRecord.started_at, ToolExecutionRecord.id)
        .all()
    )
    evidence_records = (
        session.query(EvidenceRecord)
        .filter_by(task_id=task_id)
        .order_by(EvidenceRecord.created_at, EvidenceRecord.id)
        .all()
    )
    observation_records = (
        session.query(AuditEventRecord)
        .filter_by(task_id=task_id, event_type="RUNTIME_OBSERVATION")
        .order_by(AuditEventRecord.created_at, AuditEventRecord.id)
        .all()
    )
    transition_records = (
        session.query(AuditEventRecord)
        .filter_by(task_id=task_id, event_type="RUNTIME_TRANSITION")
        .order_by(AuditEventRecord.created_at, AuditEventRecord.id)
        .all()
    )

    bounded_executions, execution_truncated = _bounded_records(
        executions, lambda record: _map_execution(record)
    )
    bounded_evidence, evidence_truncated = _bounded_records(
        evidence_records, lambda record: _map_evidence(record)
    )
    bounded_observations, observation_truncated = _bounded_records(
        observation_records, _map_observation
    )
    bounded_transitions, transition_truncated = _bounded_records(
        transition_records, _map_transition
    )
    limitations: list[str] = []
    if execution_truncated:
        limitations.append("Tool execution history was bounded to the latest records.")
    if evidence_truncated:
        limitations.append("Evidence history was bounded to the latest records.")
    if observation_truncated:
        limitations.append("Observation history was bounded to the latest records.")
    if transition_truncated:
        limitations.append("Runtime transition history was bounded to the latest records.")

    package = EvidencePackage(
        task={
            "id": task.id,
            "project_id": task.project_id,
            "title": _redact_text(task.title, 200),
            "goal": _redact_text(task.goal, MAX_GOAL),
            "workspace": _redact_text(task.workspace, 500),
            "status": task.status,
            "created_at": _iso(task.created_at),
            "updated_at": _iso(task.updated_at),
            "completed_at": _iso(task.completed_at),
        },
        project={
            "id": project.id,
            "name": _redact_text(project.name, 200),
            "environment": _redact_text(project.environment, 64),
            "status": project.status,
            "workspace_root": _redact_text(project.workspace_root, 500),
            "config_version": project.config_version,
            "allowed_capability_ids": [
                _redact_text(item, 128)
                for item in (project.allowed_capability_ids or [])[:64]
                if isinstance(item, str)
            ],
        },
        plan=_map_plan(plan),
        executions=tuple(bounded_executions),
        observations=tuple(bounded_observations),
        evidence=tuple(bounded_evidence),
        lifecycle={
            "task_status": task.status,
            "runtime_transitions": bounded_transitions,
            "terminal": task.status in {"SUCCESS", "FAILED", "CANCELLED"},
        },
        limitations=tuple(limitations),
        truncated=bool(limitations),
    )
    serialized = package.serialized()
    if len(serialized.encode("utf-8")) > MAX_PACKAGE_BYTES:
        compact = _compact_package(package)
        if len(compact.serialized().encode("utf-8")) > MAX_PACKAGE_BYTES:
            raise EvidencePackageError("PACKAGE_TOO_LARGE")
        return compact
    return package


def _compact_package(package: EvidencePackage) -> EvidencePackage:
    """Apply a deterministic second bound while retaining recent facts."""

    def compact_records(values: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
        compacted = []
        for value in values[-8:]:
            item = dict(value)
            for key in ("summary", "result_summary", "rationale", "statement"):
                if isinstance(item.get(key), str):
                    item[key] = item[key][:256]
            compacted.append(item)
        return tuple(compacted)

    limitations = tuple(
        list(package.limitations) + ["Analyst input was compacted to the byte limit."]
    )[:8]
    return EvidencePackage(
        task=package.task,
        project=package.project,
        plan=package.plan,
        executions=compact_records(package.executions),
        observations=compact_records(package.observations),
        evidence=compact_records(package.evidence),
        lifecycle=package.lifecycle,
        limitations=limitations,
        truncated=True,
    )
