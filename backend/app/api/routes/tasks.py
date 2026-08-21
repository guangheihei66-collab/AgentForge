"""Task endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...schemas.task import TaskCreate, TaskRead
from ...services.task_service import TaskService
from ...storage.database import get_db

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)) -> TaskRead:
    task = TaskService(db).create_task(
        title=payload.title,
        goal=payload.goal,
        workspace=payload.workspace,
    )
    return TaskRead.model_validate(task)


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: str, db: Session = Depends(get_db)) -> TaskRead:
    task = TaskService(db).get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskRead.model_validate(task)
