"""Audit query response contract."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    event_type: str
    actor: str
    payload_summary: str
    correlation_id: str
    created_at: datetime
