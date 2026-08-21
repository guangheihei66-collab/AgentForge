"""Planner endpoint; it does not expose tool execution."""

import os

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...agents.planner.planner import PlannerAgent
from ...agents.planner.validator import PlanValidationError
from ...agents.providers.mock import MockLLMProvider
from ...schemas.plan import PlanRead, PlanRequest
from ...storage.database import get_db

router = APIRouter(prefix="/tasks", tags=["planning"])


@router.post("/{task_id}/plan", response_model=PlanRead, status_code=status.HTTP_201_CREATED)
def create_plan(task_id: str, payload: PlanRequest, db: Session = Depends(get_db)) -> PlanRead:
    workspace_root = os.getenv("AGENTFORGE_WORKSPACE_ROOT", r"D:\AgentProjects\AgentForge")
    try:
        plan = PlannerAgent(db, MockLLMProvider(), workspace_root).create_plan(
            task_id, context=payload.context
        )
        return PlanRead.model_validate(plan, from_attributes=True)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (PlanValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
