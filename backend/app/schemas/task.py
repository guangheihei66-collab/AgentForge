"""Task request and response contracts."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..domain.states.task_state import TaskStatus


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, max_length=5000)
    workspace: str = Field(min_length=1, max_length=500)


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    goal: str
    workspace: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
