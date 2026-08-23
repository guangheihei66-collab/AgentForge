"""Minimal, secret-free LLM provider status and connection checks."""

from dataclasses import dataclass
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException

from ...agents.providers import (
    LLMProvider,
    ProviderConfig,
    ProviderError,
    ProviderErrorCategory,
    build_provider,
    load_provider_config,
)
from ...schemas.provider import ProviderStatusRead


router = APIRouter(prefix="/llm/provider", tags=["llm-provider"])


@dataclass(frozen=True, slots=True)
class ConnectionSnapshot:
    status: str = "not tested"
    failure_category: ProviderErrorCategory | None = None
    duration_ms: int | None = None


class ConnectionStateStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._snapshot = ConnectionSnapshot()

    def get(self) -> ConnectionSnapshot:
        with self._lock:
            return self._snapshot

    def success(self, duration_ms: int) -> None:
        with self._lock:
            self._snapshot = ConnectionSnapshot("success", None, duration_ms)

    def failure(self, category: ProviderErrorCategory, duration_ms: int = 0) -> None:
        with self._lock:
            self._snapshot = ConnectionSnapshot("failed", category, duration_ms)

    def reset(self) -> None:
        with self._lock:
            self._snapshot = ConnectionSnapshot()


connection_state = ConnectionStateStore()


def _configuration() -> ProviderConfig:
    try:
        return load_provider_config()
    except ProviderError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"LLM provider configuration failed: {exc.category.value}",
        ) from None


def get_status_provider() -> LLMProvider:
    try:
        return build_provider(load_provider_config())
    except ProviderError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"LLM provider connection unavailable: {exc.category.value}",
        ) from None


def _read_status(config: ProviderConfig) -> ProviderStatusRead:
    snapshot = connection_state.get()
    if not config.configured:
        status = "failed"
        category = ProviderErrorCategory.NOT_CONFIGURED
    else:
        status = snapshot.status
        category = snapshot.failure_category
    return ProviderStatusRead(
        provider=config.provider,
        configured=config.configured,
        model=config.model or "deterministic-mock",
        credential_configured=config.credential_configured,
        connection_status=status,
        failure_category=category,
    )


@router.get("", response_model=ProviderStatusRead)
def provider_status() -> ProviderStatusRead:
    return _read_status(_configuration())


@router.post("/test", response_model=ProviderStatusRead)
def test_provider_connection(
    provider: LLMProvider = Depends(get_status_provider),
) -> ProviderStatusRead:
    config = _configuration()
    try:
        response = provider.test_connection()
        connection_state.success(response.duration_ms)
    except ProviderError as exc:
        connection_state.failure(exc.category, exc.duration_ms)
    return _read_status(config)
