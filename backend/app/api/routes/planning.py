"""Planner endpoint; it does not expose tool execution."""

import os

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...agents.planner.planner import PlannerAgent
from ...agents.planner.validator import PlanValidationError
from ...agents.providers import (
    LLMProvider,
    ProviderError,
    ProviderErrorCategory,
    build_provider,
    load_provider_config,
)
from ...schemas.plan import PlanRead, PlanRequest
from ...storage.database import get_db

router = APIRouter(prefix="/tasks", tags=["planning"])


def _provider_http_error(exc: ProviderError) -> HTTPException:
    status_code = {
        ProviderErrorCategory.NOT_CONFIGURED: 503,
        ProviderErrorCategory.RATE_LIMITED: 429,
        ProviderErrorCategory.TIMEOUT: 504,
    }.get(exc.category, 502)
    return HTTPException(
        status_code=status_code,
        detail=f"LLM planning failed: {exc.category.value}",
    )


def get_llm_provider() -> LLMProvider:
    try:
        return build_provider(load_provider_config())
    except ProviderError as exc:
        raise _provider_http_error(exc) from None


@router.post("/{task_id}/plan", response_model=PlanRead, status_code=status.HTTP_201_CREATED)
def create_plan(
    task_id: str,
    payload: PlanRequest,
    db: Session = Depends(get_db),
    provider: LLMProvider = Depends(get_llm_provider),
) -> PlanRead:
    workspace_root = os.getenv("AGENTFORGE_WORKSPACE_ROOT", r"D:\AgentProjects\AgentForge")
    try:
        plan = PlannerAgent(db, provider, workspace_root).create_plan(
            task_id, context=payload.context
        )
        return PlanRead.model_validate(plan, from_attributes=True)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProviderError as exc:
        raise _provider_http_error(exc) from None
    except (PlanValidationError, ValueError):
        raise HTTPException(status_code=400, detail="LLM planning failed: INVALID_RESPONSE") from None
