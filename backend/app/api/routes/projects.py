"""Local Project endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from dataclasses import asdict
from sqlalchemy.orm import Session

from ...projects.service import ProjectConflictError, ProjectService
from ...schemas.project import (ArchiveRequest, ProjectCreate, ProjectDetail,
                                ProjectPatch, ProjectRead, WorkspaceValidationRequest)
from ...storage.database import get_db
from ...storage.orm import TaskRecord
from ...workspace.validator import WorkspaceValidationError, WorkspaceValidator

router = APIRouter(prefix="/projects", tags=["projects"])


def _read(project) -> ProjectRead:
    return ProjectRead(**{**asdict(project), "status": project.status.value,
                          "allowed_capability_ids": list(project.allowed_capability_ids)})


@router.get("", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db)):
    return [_read(p) for p in ProjectService(db).list()]


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    try:
        return _read(ProjectService(db).create(
            name=payload.name, description=payload.description,
            workspace_root=payload.workspace_root, environment=payload.environment,
            allowed_capability_ids=tuple(payload.allowed_capability_ids),
        ))
    except ProjectConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (ValueError, WorkspaceValidationError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = ProjectService(db).get(project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    tasks = db.query(TaskRecord).filter_by(project_id=project_id).order_by(TaskRecord.created_at.desc()).limit(20).all()
    return ProjectDetail(**_read(project).model_dump(), recent_tasks=[
        {"id": t.id, "title": t.title, "goal": t.goal, "status": t.status,
         "created_at": t.created_at.isoformat()} for t in tasks
    ])


@router.patch("/{project_id}", response_model=ProjectRead)
def patch_project(project_id: str, payload: ProjectPatch, db: Session = Depends(get_db)):
    try:
        return _read(ProjectService(db).update(
            project_id, expected_config_version=payload.expected_config_version,
            name=payload.name, description=payload.description,
            workspace_root=payload.workspace_root, environment=payload.environment,
            allowed_capability_ids=(None if payload.allowed_capability_ids is None else tuple(payload.allowed_capability_ids)),
        ))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ProjectConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except (ValueError, WorkspaceValidationError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/{project_id}/archive", response_model=ProjectRead)
def archive_project(project_id: str, payload: ArchiveRequest, db: Session = Depends(get_db)):
    try:
        return _read(ProjectService(db).archive(
            project_id, expected_config_version=payload.expected_config_version
        ))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ProjectConflictError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/validate-workspace")
def validate_workspace(payload: WorkspaceValidationRequest):
    try:
        root = WorkspaceValidator.canonicalize_project_root(payload.workspace_root)
        return {"valid": True, "canonical_workspace_root": str(root)}
    except WorkspaceValidationError as exc:
        raise HTTPException(400, str(exc)) from exc
