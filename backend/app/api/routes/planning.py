"""Planner endpoint; it does not expose tool execution."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...agents.planner.planner import PlannerAgent
from ...agents.planner.validator import PlanValidationError
from ...agents.providers import (
    LLMProvider,
    LLMRequest,
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


def _build_product_provider() -> LLMProvider:
    return build_provider(load_provider_config(allow_default_mock=False))


def get_llm_provider() -> LLMProvider:
    try:
        return _build_product_provider()
    except ProviderError as exc:
        raise _provider_http_error(exc) from None


class _UnavailablePlanningProvider:
    """Keep PlannerAgent in charge of durable failure handling.

    FastAPI resolves dependencies before entering the route body.  Returning a
    safe provider sentinel lets PlannerAgent record ``LLM_PLAN_REQUESTED`` and
    ``LLM_PLAN_FAILED`` and transition the Task to FAILED even when product
    configuration is unavailable before an HTTP request can be made.
    """

    provider_name = "unconfigured"
    model_name = "not-configured"

    def __init__(self, error: ProviderError) -> None:
        self._category = error.category
        self._retryable = error.retryable
        self._attempt_count = error.attempt_count
        self._duration_ms = error.duration_ms
        self._diagnostics = dict(error.diagnostics)

    def generate_plan(self, request: LLMRequest):
        del request
        raise ProviderError(
            self._category,
            retryable=self._retryable,
            attempt_count=self._attempt_count,
            duration_ms=self._duration_ms,
            diagnostics=self._diagnostics,
        )


def get_planning_provider() -> LLMProvider:
    """Resolve a product provider without bypassing PlannerAgent lifecycle."""

    try:
        return _build_product_provider()
    except ProviderError as exc:
        return _UnavailablePlanningProvider(exc)


@router.post("/{task_id}/plan", response_model=PlanRead, status_code=status.HTTP_201_CREATED)
def create_plan(
    task_id: str,
    payload: PlanRequest,
    db: Session = Depends(get_db),
    provider: LLMProvider = Depends(get_planning_provider),
) -> PlanRead:
    try:
        plan = PlannerAgent(db, provider).create_plan(
            task_id, context=payload.context
        )
        return PlanRead.model_validate(plan, from_attributes=True)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ProviderError as exc:
        raise _provider_http_error(exc) from None
    except (PlanValidationError, ValueError):
        raise HTTPException(status_code=400, detail="LLM planning failed: INVALID_RESPONSE") from None
