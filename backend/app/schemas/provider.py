"""Secret-free operator contracts for the selected LLM provider."""

from typing import Literal

from pydantic import BaseModel

from ..agents.providers.base import ProviderErrorCategory


class ProviderStatusRead(BaseModel):
    provider: Literal["mock", "openai-compatible"]
    configured: bool
    model: str
    credential_configured: bool
    connection_status: Literal["not tested", "success", "failed"]
    failure_category: ProviderErrorCategory | None = None
