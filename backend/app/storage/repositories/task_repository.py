"""Task persistence operations."""

from sqlalchemy.orm import Session

from ...domain.models.entities import Task
from ...domain.states.task_state import TaskStatus
from ..orm import TaskRecord


def to_domain(record: TaskRecord) -> Task:
    return Task(
        id=record.id,
        title=record.title,
        goal=record.goal,
        workspace=record.workspace,
        status=TaskStatus(record.status),
        created_at=record.created_at,
        updated_at=record.updated_at,
        completed_at=record.completed_at,
    )


class TaskRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(self, task: Task) -> Task:
        record = TaskRecord(
            id=task.id,
            title=task.title,
            goal=task.goal,
            workspace=task.workspace,
            status=task.status.value,
            created_at=task.created_at,
            updated_at=task.updated_at,
            completed_at=task.completed_at,
        )
        self.session.add(record)
        self.session.flush()
        return to_domain(record)

    def get_by_id(self, task_id: str) -> Task | None:
        record = self.session.get(TaskRecord, task_id)
        return to_domain(record) if record else None

    def update(self, task: Task) -> Task:
        record = self.session.get(TaskRecord, task.id)
        if record is None:
            raise LookupError(f"Task not found: {task.id}")
        record.title = task.title
        record.goal = task.goal
        record.workspace = task.workspace
        record.status = task.status.value
        record.updated_at = task.updated_at
        record.completed_at = task.completed_at
        self.session.flush()
        return to_domain(record)
