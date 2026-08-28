"""Durable read projection for Analyst synthesis state and artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any

from sqlalchemy.orm import Session

from ..storage.orm import AuditEventRecord, TaskRecord
from .models import AnalystReport, AnalystSynthesisStatus
from .storage import AnalystArtifactError, AnalystArtifactStore


@dataclass(frozen=True, slots=True)
class AnalystReadModel:
    status: AnalystSynthesisStatus
    report: AnalystReport | None = None
    failure_category: str | None = None
    provider: str | None = None
    model: str | None = None
    plan_id: str | None = None
    plan_version: int | None = None
    artifact_path: str | None = None
    content_hash: str | None = None
    generated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "report": self.report,
            "failure_category": self.failure_category,
            "provider": self.provider,
            "model": self.model,
            "plan_id": self.plan_id,
            "plan_version": self.plan_version,
            "artifact_path": self.artifact_path,
            "content_hash": self.content_hash,
            "generated_at": self.generated_at,
        }


def _safe_str(value: Any, limit: int = 128) -> str | None:
    return value[:limit] if isinstance(value, str) and value else None


def _safe_version(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 1 else None


def _payload(event: AuditEventRecord) -> dict[str, Any]:
    try:
        payload = json.loads(event.payload_summary)
    except (TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def read_analyst_report(
    session: Session,
    *,
    task_id: str,
    artifact_store: AnalystArtifactStore,
) -> AnalystReadModel:
    task = session.get(TaskRecord, task_id)
    if task is None:
        raise LookupError("Task not found")
    events = (
        session.query(AuditEventRecord)
        .filter(
            AuditEventRecord.task_id == task_id,
            AuditEventRecord.event_type.in_(
                {
                    "ANALYST_SYNTHESIS_REQUESTED",
                    "ANALYST_SYNTHESIS_STARTED",
                    "ANALYST_SYNTHESIS_SUCCEEDED",
                    "ANALYST_SYNTHESIS_FAILED",
                }
            ),
        )
        .order_by(AuditEventRecord.created_at.asc(), AuditEventRecord.id.asc())
        .all()
    )
    if not events:
        return AnalystReadModel(AnalystSynthesisStatus.NOT_REQUESTED)

    event = events[-1]
    payload = _payload(event)
    provider = _safe_str(payload.get("provider"))
    model = _safe_str(payload.get("model"))
    plan_id = _safe_str(payload.get("plan_id"))
    plan_version = _safe_version(payload.get("plan_version"))
    if event.event_type == "ANALYST_SYNTHESIS_REQUESTED":
        return AnalystReadModel(
            AnalystSynthesisStatus.PENDING,
            provider=provider,
            model=model,
            plan_id=plan_id,
            plan_version=plan_version,
        )
    if event.event_type == "ANALYST_SYNTHESIS_STARTED":
        return AnalystReadModel(
            AnalystSynthesisStatus.GENERATING,
            provider=provider,
            model=model,
            plan_id=plan_id,
            plan_version=plan_version,
        )
    if event.event_type == "ANALYST_SYNTHESIS_FAILED":
        return AnalystReadModel(
            AnalystSynthesisStatus.FAILED,
            failure_category=_safe_str(payload.get("failure_category"), 64)
            or "SYNTHESIS_FAILED",
            provider=provider,
            model=model,
            plan_id=plan_id,
            plan_version=plan_version,
        )

    artifact_path = _safe_str(payload.get("artifact_path"), 1_000)
    content_hash = _safe_str(payload.get("content_hash"), 128)
    if not artifact_path or not content_hash or not plan_id or plan_version is None:
        return AnalystReadModel(
            AnalystSynthesisStatus.FAILED,
            failure_category="ARTIFACT_METADATA_INVALID",
            provider=provider,
            model=model,
            plan_id=plan_id,
            plan_version=plan_version,
        )
    try:
        report = artifact_store.load(
            artifact_path,
            expected_hash=content_hash,
            task_id=task_id,
            plan_id=plan_id,
            plan_version=plan_version,
        )
    except AnalystArtifactError as exc:
        return AnalystReadModel(
            AnalystSynthesisStatus.FAILED,
            failure_category=exc.category,
            provider=provider,
            model=model,
            plan_id=plan_id,
            plan_version=plan_version,
        )
    return AnalystReadModel(
        AnalystSynthesisStatus.SUCCEEDED,
        report=report,
        provider=report.provider,
        model=report.model,
        plan_id=report.plan_id,
        plan_version=report.plan_version,
        artifact_path=artifact_path,
        content_hash=content_hash,
        generated_at=report.generated_at,
    )
