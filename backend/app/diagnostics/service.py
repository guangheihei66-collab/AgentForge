from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..agents.providers.config import load_provider_config
from ..identity import get_runtime_identity
from ..schemas.diagnostics import DiagnosticsRead, ExecutionCountsRead, HealthRead, RecentTaskRead, RuntimeIdentityRead
from ..storage.orm import ApprovalRecord, AuditEventRecord, EvidenceRecord, PlanRecord, TaskRecord, ToolExecutionRecord
from .health import classify_overall


def _provider() -> tuple[dict[str, object], str]:
    try:
        config = load_provider_config()
        if not config.configured:
            return {"provider": config.provider, "model": config.model or "deterministic-mock", "structured_output_mode": config.structured_output_mode.value, "credential_configured": config.credential_configured, "connection": "NOT_CONFIGURED"}, "DEGRADED"
        return {"provider": config.provider, "model": config.model or "deterministic-mock", "structured_output_mode": config.structured_output_mode.value, "credential_configured": config.credential_configured, "connection": "UNKNOWN"}, "UNKNOWN"
    except Exception:
        return {"provider": "UNKNOWN", "model": "UNKNOWN", "structured_output_mode": "UNKNOWN", "credential_configured": False, "connection": "UNKNOWN"}, "UNKNOWN"


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
    if recent:
        plan = session.scalars(select(PlanRecord).where(PlanRecord.task_id == recent.id).order_by(PlanRecord.version.desc()).limit(1)).first()
        approval = session.scalars(select(ApprovalRecord).where(ApprovalRecord.task_id == recent.id).order_by(ApprovalRecord.created_at.desc()).limit(1)).first()
        executions = list(session.scalars(select(ToolExecutionRecord).where(ToolExecutionRecord.task_id == recent.id)))
        statuses = [item.status.upper() for item in executions]
        recent_task = RecentTaskRead(id=recent.id, state=recent.status, plan_version=plan.version if plan else None, approval=approval.decision if approval else None, executions=ExecutionCountsRead(total=len(statuses), success=statuses.count("SUCCESS"), failed=statuses.count("FAILED"), rejected=statuses.count("REJECTED")), evidence_count=session.scalar(select(func.count()).select_from(EvidenceRecord).where(EvidenceRecord.task_id == recent.id)) or 0, observation_count=session.scalar(select(func.count()).select_from(AuditEventRecord).where(AuditEventRecord.task_id == recent.id, AuditEventRecord.event_type.ilike("%observation%"))) or 0, replan_count=session.scalar(select(func.count()).select_from(AuditEventRecord).where(AuditEventRecord.task_id == recent.id, AuditEventRecord.event_type.ilike("%replan%"))) or 0)
    return DiagnosticsRead(identity=RuntimeIdentityRead(**identity.__dict__) if hasattr(identity, "__dict__") else RuntimeIdentityRead(product=identity.product, version=identity.version, revision=identity.revision, environment=identity.environment), health=HealthRead(overall=classify_overall(backend=backend_state, database=database_state, provider=provider_state), backend=backend_state, database=database_state, provider=provider_state), provider=provider, recent_task=recent_task, recent_errors=[])
