"""Production entry point for executing an approved Task plan."""

from dataclasses import asdict
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...agent_runtime import AgentRuntime, RuntimeExecutor
from ...analyst.service import AnalystService
from ...agents.orchestration.service import (
    AgentApprovalExecutionService,
    AgentExecutionInitiationError,
)
from ...agents.replanning.service import ReplanningService
from ...agents.providers import build_provider, load_provider_config
from ...approvals.service import ApprovalError
from ...projects.service import ProjectService
from ...schemas.approval import ApproveAndExecuteRequest
from ...services.plan_repository import PlanRepository
from ...storage.database import get_db
from ...tools.defaults import build_default_registry
from ...tools.gateway import ToolGateway
from ...workspace.validator import WorkspaceValidator

router = APIRouter(tags=["execution"])


def _serialize_result(result) -> dict:
    return {
        "task_id": result.task_id,
        "plan_id": result.plan_id,
        "plan_version": result.plan_version,
        "state": result.state.value,
        "decision": result.decision.value,
        "completed_steps": result.completed_steps,
        "observations": [asdict(item) for item in result.observations],
        "successor_plan_id": result.successor_plan_id,
        "successor_plan_version": result.successor_plan_version,
        "approval_id": result.approval_id,
    }


def _build_runtime(db: Session, task_id: str) -> AgentRuntime:
    context = ProjectService(db).execution_context_for_task(task_id)
    validator = WorkspaceValidator.for_project(context.workspace_root)
    registry = build_default_registry(validator)
    data_root = Path(os.getenv("AGENTFORGE_DATA_ROOT", r"D:\AgentProjectData\AgentForge"))
    gateway = ToolGateway(
        db,
        registry,
        validator,
        data_root / "artifacts" / task_id,
    )
    provider = build_provider(load_provider_config(allow_default_mock=False))
    return AgentRuntime(
        db,
        RuntimeExecutor(gateway),
        replanning_service=ReplanningService(db, provider),
        analyst_service=AnalystService(db, provider, data_root=data_root),
    )


@router.post("/tasks/{task_id}/execute")
def execute_task(task_id: str, db: Session = Depends(get_db)) -> dict:
    try:
        runtime = _build_runtime(db, task_id)
        plan = PlanRepository(db).highest_for_task(task_id)
        if plan is None:
            raise LookupError("No valid plan exists for task")
        result = runtime.run(task_id=task_id, plan_id=plan.id, plan_version=plan.version)
        return _serialize_result(result)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ApprovalError, PermissionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tasks/{task_id}/approve-and-execute")
def approve_and_execute_task(
    task_id: str,
    payload: ApproveAndExecuteRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        result = AgentApprovalExecutionService(
            db,
            runtime_factory=lambda current_task_id: _build_runtime(db, current_task_id),
        ).approve_and_execute(
            task_id=task_id,
            approval_id=payload.approval_id,
            plan_id=payload.plan_id,
            plan_version=payload.plan_version,
            actor=payload.actor,
            language=payload.language,
        )
        return _serialize_result(result)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AgentExecutionInitiationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from None
    except (ApprovalError, PermissionError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

