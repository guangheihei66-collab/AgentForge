"""LLM provider interfaces and test-safe implementations."""

from .base import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ProviderError,
    ProviderErrorCategory,
    StructuredOutputMode,
)
from .config import ProviderConfig, build_provider, load_provider_config


def __getattr__(name: str):
    """Keep optional HTTP transport imports out of lightweight launcher paths."""

    if name == "MockLLMProvider":
        from .mock import MockLLMProvider

        return MockLLMProvider
    if name == "OpenAICompatibleProvider":
        from .openai_compatible import OpenAICompatibleProvider

        return OpenAICompatibleProvider
    raise AttributeError(name)

__all__ = [
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "MockLLMProvider",
    "OpenAICompatibleProvider",
    "ProviderConfig",
    "ProviderError",
    "ProviderErrorCategory",
    "StructuredOutputMode",
    "build_provider",
    "load_provider_config",
]
