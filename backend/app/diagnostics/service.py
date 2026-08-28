import json
import os
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..analyst.read_model import AnalystReadModel, read_analyst_report
from ..analyst.storage import AnalystArtifactStore
from ..agents.providers.config import load_provider_config
from ..identity import get_runtime_identity
from ..schemas.diagnostics import AnalystDiagnosticsRead, CommandProvenanceRead, DiagnosticsRead, ExecutionCountsRead, HealthRead, RecentTaskRead, RuntimeIdentityRead
from ..storage.orm import ApprovalRecord, AuditEventRecord, EvidenceRecord, PlanRecord, TaskRecord, ToolExecutionRecord
from .health import classify_overall


def _provider() -> tuple[dict[str, object], str]:
    try:
        config = load_provider_config()
        from ..api.routes.providers import connection_state

        snapshot = connection_state.get()
        if not config.configured:
            return {"provider": config.provider, "model": config.model or "deterministic-mock", "structured_output_mode": config.structured_output_mode.value, "credential_configured": config.credential_configured, "connection": "NOT_CONFIGURED"}, "DEGRADED"
        connection = {"success": "SUCCESS", "failed": "FAILED"}.get(snapshot.status, "UNKNOWN")
        state = "HEALTHY" if snapshot.status == "success" else ("DEGRADED" if snapshot.status == "failed" else "UNKNOWN")
        return {"provider": config.provider, "model": config.model or "deterministic-mock", "structured_output_mode": config.structured_output_mode.value, "credential_configured": config.credential_configured, "connection": connection}, state
    except Exception:
        return {"provider": "UNKNOWN", "model": "UNKNOWN", "structured_output_mode": "UNKNOWN", "credential_configured": False, "connection": "UNKNOWN"}, "UNKNOWN"


_COMMAND_RECEIVED_EVENTS = {
    "GLOBAL_APPROVAL_COMMAND_RECEIVED",
    "AGENT_APPROVE_AND_EXECUTE_COMMAND_RECEIVED",
}
_INITIATION_EVENTS = {
    "EXECUTION_INITIATION_REQUESTED",
    "EXECUTION_INITIATION_STARTED",
    "EXECUTION_INITIATION_FAILED",
}


def _payload(event: AuditEventRecord) -> dict[str, object]:
    try:
        value = json.loads(event.payload_summary)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _text(value: object, *, limit: int = 200) -> str | None:
    return value[:limit] if isinstance(value, str) else None


def _command_provenance(
    session: Session, task: TaskRecord
) -> CommandProvenanceRead | None:
    events = session.scalars(
        select(AuditEventRecord)
        .where(AuditEventRecord.task_id == task.id)
        .order_by(AuditEventRecord.created_at.asc(), AuditEventRecord.id.asc())
    ).all()
    received_indexes = [
        index for index, event in enumerate(events)
        if event.event_type in _COMMAND_RECEIVED_EVENTS
    ]
    if not received_indexes:
        return None

    received_index = received_indexes[-1]
    received = events[received_index]
    received_payload = _payload(received)
    window = events[received_index:]
    command_kind = _text(received_payload.get("command_kind")) or (
        "AGENT_APPROVE_AND_EXECUTE"
        if received.event_type == "AGENT_APPROVE_AND_EXECUTE_COMMAND_RECEIVED"
        else "GLOBAL_APPROVAL"
    )
    approval_id = _text(received_payload.get("approval_id"))
    approval = session.get(ApprovalRecord, approval_id) if approval_id else None
    failure_category = None
    authority_validation = None
    approval_persistence = None
    initiation = "NOT_REQUESTED"
    for event in window:
        payload = _payload(event)
        if isinstance(payload.get("authority_validation"), str):
            authority_validation = _text(payload["authority_validation"])
        if isinstance(payload.get("approval_persistence"), str):
            approval_persistence = _text(payload["approval_persistence"])
        if event.event_type in _INITIATION_EVENTS:
            if event.event_type == "EXECUTION_INITIATION_FAILED":
                initiation = "FAILED"
            elif initiation != "FAILED" and event.event_type == "EXECUTION_INITIATION_STARTED":
                initiation = "STARTED"
            elif initiation == "NOT_REQUESTED":
                initiation = "REQUESTED"
        if event.event_type in {"APPROVAL_COMMAND_FAILED", "EXECUTION_INITIATION_FAILED"}:
            failure_category = _text(payload.get("error_category"))

    last = window[-1]
    plan_id = _text(received_payload.get("plan_id"))
    plan_version = received_payload.get("plan_version")
    if not isinstance(plan_version, int):
        plan_version = None
    return CommandProvenanceRead(
        command_kind=command_kind,
        task_id=task.id,
        task_state=task.status,
        plan_id=plan_id,
        plan_version=plan_version,
        approval_id=approval_id,
        approval_state=approval.decision if approval is not None else None,
        authority_validation=authority_validation,
        approval_persistence=approval_persistence,
        execution_initiation=initiation,
        last_checkpoint=last.event_type[:64],
        correlation_id=received.correlation_id,
        failure_category=failure_category,
    )


def _analyst_snapshot(session: Session, task_id: str) -> AnalystDiagnosticsRead:
    data_root = Path(
        os.getenv("AGENTFORGE_DATA_ROOT", r"D:\AgentProjectData\AgentForge")
    )
    read_model: AnalystReadModel = read_analyst_report(
        session,
        task_id=task_id,
        artifact_store=AnalystArtifactStore(data_root),
    )
    return AnalystDiagnosticsRead(
        status=read_model.status.value,
        task_id=task_id,
        plan_id=read_model.plan_id,
        plan_version=read_model.plan_version,
        provider=read_model.provider,
        model=read_model.model,
        artifact_path=read_model.artifact_path,
        content_hash=read_model.content_hash,
        generated_at=read_model.generated_at,
        failure_category=read_model.failure_category,
    )


def diagnostics_snapshot(session: Session) -> DiagnosticsRead:
    identity = get_runtime_identity()
    provider, provider_state = _provider()
    database_state = "HEALTHY"
    try:
        session.execute(select(func.count()).select_from(TaskRecord)).scalar_one()
    except Exception:
        database_state = "UNHEALTHY"
    backend_state = "HEALTHY"
    recent = session.scalars(select(TaskRecord).order_by(TaskRecord.updated_at.desc()).limit(1)).first()
    recent_task = None
    analyst = AnalystDiagnosticsRead(status="NOT_REQUESTED")
    command_provenance = None
    if recent:
        plan = session.scalars(select(PlanRecord).where(PlanRecord.task_id == recent.id).order_by(PlanRecord.version.desc()).limit(1)).first()
        approval = session.scalars(select(ApprovalRecord).where(ApprovalRecord.task_id == recent.id).order_by(ApprovalRecord.created_at.desc()).limit(1)).first()
        execution_counts = dict(session.execute(select(ToolExecutionRecord.status, func.count()).where(ToolExecutionRecord.task_id == recent.id).group_by(ToolExecutionRecord.status)).all())
        success = execution_counts.get("SUCCESS", 0)
        failed = execution_counts.get("FAILED", 0)
        rejected = execution_counts.get("REJECTED", 0)
        recent_task = RecentTaskRead(id=recent.id, state=recent.status, plan_version=plan.version if plan else None, approval=approval.decision if approval else None, executions=ExecutionCountsRead(total=sum(execution_counts.values()), success=success, failed=failed, rejected=rejected), evidence_count=session.scalar(select(func.count()).select_from(EvidenceRecord).where(EvidenceRecord.task_id == recent.id)) or 0, observation_count=session.scalar(select(func.count()).select_from(AuditEventRecord).where(AuditEventRecord.task_id == recent.id, AuditEventRecord.event_type.ilike("%observation%"))) or 0, replan_count=session.scalar(select(func.count()).select_from(AuditEventRecord).where(AuditEventRecord.task_id == recent.id, AuditEventRecord.event_type.ilike("%replan%"))) or 0)
        analyst = _analyst_snapshot(session, recent.id)
        command_provenance = _command_provenance(session, recent)
    return DiagnosticsRead(identity=RuntimeIdentityRead(**identity.__dict__) if hasattr(identity, "__dict__") else RuntimeIdentityRead(product=identity.product, version=identity.version, revision=identity.revision, environment=identity.environment), health=HealthRead(overall=classify_overall(backend=backend_state, database=database_state, provider=provider_state), backend=backend_state, database=database_state, provider=provider_state), provider=provider, recent_task=recent_task, analyst=analyst, command_provenance=command_provenance, recent_errors=[])
