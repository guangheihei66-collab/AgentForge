"""Safe, durable command provenance built on the existing AuditEvent record."""

from datetime import datetime, timezone
import json
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from ..storage.orm import AuditEventRecord


GLOBAL_APPROVAL_COMMAND_RECEIVED = "GLOBAL_APPROVAL_COMMAND_RECEIVED"
AGENT_APPROVE_AND_EXECUTE_COMMAND_RECEIVED = "AGENT_APPROVE_AND_EXECUTE_COMMAND_RECEIVED"
APPROVAL_COMMAND_SUCCEEDED = "APPROVAL_COMMAND_SUCCEEDED"
APPROVAL_COMMAND_FAILED = "APPROVAL_COMMAND_FAILED"
EXECUTION_INITIATION_REQUESTED = "EXECUTION_INITIATION_REQUESTED"
EXECUTION_INITIATION_STARTED = "EXECUTION_INITIATION_STARTED"
EXECUTION_INITIATION_FAILED = "EXECUTION_INITIATION_FAILED"

_SAFE_FIELDS = {
    "approval_id",
    "approval_persistence",
    "approval_state",
    "authority_validation",
    "command_kind",
    "error_category",
    "execution_count_after",
    "execution_count_before",
    "execution_initiation",
    "outcome",
    "plan_id",
    "plan_version",
    "summary",
    "task_id",
    "task_state",
}
_MAX_PAYLOAD_BYTES = 8 * 1024


def command_correlation_id(request_id: str | None = None) -> str:
    """Use a valid request UUID when supplied, otherwise create one locally."""

    if request_id:
        try:
            return str(UUID(request_id))
        except (AttributeError, TypeError, ValueError):
            pass
    return str(uuid4())


def persist_provenance_event(
    session: Session,
    *,
    task_id: str,
    event_type: str,
    actor: str,
    correlation_id: str,
    fields: dict[str, object] | None = None,
) -> AuditEventRecord:
    """Persist one bounded, allowlisted factual event and make it durable."""

    payload: dict[str, object] = {"task_id": task_id}
    for key, value in (fields or {}).items():
        if key in _SAFE_FIELDS and value is not None:
            payload[key] = value
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if len(serialized.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
        raise ValueError("Command provenance payload exceeds the size limit")

    event = AuditEventRecord(
        task_id=task_id,
        event_type=event_type,
        actor=actor[:200],
        payload_summary=serialized,
        correlation_id=correlation_id,
        created_at=datetime.now(timezone.utc),
    )
    session.add(event)
    session.commit()
    return event


def safe_error_category(error: BaseException, *, initiation: bool = False) -> str:
    """Map internal exception shapes to a stable operator-safe category."""

    name = type(error).__name__
    if initiation:
        if name in {"RuntimeError", "AgentExecutionInitiationError"}:
            return "RUNTIME_START_FAILED"
        if name in {"ApprovalError", "PermissionError"}:
            return "AUTHORITY_REJECTED"
        if name == "LookupError":
            return "RESOURCE_NOT_FOUND"
        if name == "ValueError":
            return "RUNTIME_VALIDATION_FAILED"
        return "EXECUTION_INITIATION_ERROR"
    if name in {"ApprovalError", "PermissionError"}:
        return "AUTHORITY_REJECTED"
    if name == "LookupError":
        return "RESOURCE_NOT_FOUND"
    if name == "ValueError":
        return "VALIDATION_REJECTED"
    return "APPROVAL_COMMAND_ERROR"
