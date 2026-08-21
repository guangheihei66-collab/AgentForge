"""Task application service and audited state transitions."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from ..domain.models.entities import Task
from ..domain.states.task_state import TaskStatus, transition_task
from ..storage.orm import AuditEventRecord
from ..storage.repositories.task_repository import TaskRepository


class TaskService:
    def __init__(self, session: Session):
        self.session = session
        self.tasks = TaskRepository(session)

    def create_task(self, *, title: str, goal: str, workspace: str) -> Task:
        now = datetime.now(timezone.utc)
        task = Task(
            id=str(uuid4()),
            title=title,
            goal=goal,
            workspace=workspace,
            status=TaskStatus.CREATED,
            created_at=now,
            updated_at=now,
        )
        created = self.tasks.create(task)
        self._audit(created.id, "TASK_CREATED", "user", "Task created")
        self.session.commit()
        return created

    def get_task(self, task_id: str) -> Task | None:
        return self.tasks.get_by_id(task_id)

    def transition_task(
        self,
        task_id: str,
        target: TaskStatus,
        *,
        actor: str = "system",
        reason: str = "",
    ) -> Task:
        task = self.tasks.get_by_id(task_id)
        if task is None:
            raise LookupError(f"Task not found: {task_id}")

        previous = task.status
        transition_task(previous, target)
        now = datetime.now(timezone.utc)
        task.status = target
        task.updated_at = now
        if target in {TaskStatus.SUCCESS, TaskStatus.FAILED, TaskStatus.CANCELLED}:
            task.completed_at = now

        updated = self.tasks.update(task)
        self._audit(
            task.id,
            "TASK_STATE_CHANGED",
            actor,
            f"{previous.value} -> {target.value}; {reason}".strip(),
        )
        self.session.commit()
        return updated

    def _audit(
        self, task_id: str, event_type: str, actor: str, payload_summary: str
    ) -> None:
        self.session.add(
            AuditEventRecord(
                task_id=task_id,
                event_type=event_type,
                actor=actor,
                payload_summary=payload_summary,
                correlation_id=str(uuid4()),
            )
        )
