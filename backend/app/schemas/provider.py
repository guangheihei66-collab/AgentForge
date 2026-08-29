"""Secret-free operator contracts for the selected LLM provider."""

from typing import Literal

from pydantic import BaseModel

from ..agents.providers.base import ProviderErrorCategory


class ProviderStatusRead(BaseModel):
    provider: Literal["mock", "openai-compatible", "unconfigured"]
    configured: bool
    model: str
    credential_configured: bool
    structured_output_mode: Literal["json_schema", "json_object"]
    connection_status: Literal["not tested", "success", "failed"]
    failure_category: ProviderErrorCategory | None = None
