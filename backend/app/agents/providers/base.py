"""Provider boundary for plan generation."""

from typing import Any, Protocol


class LLMProvider(Protocol):
    def generate_plan(self, prompt: str, context: dict[str, Any]) -> str | dict[str, Any]:
        """Return a candidate plan payload without executing any tools."""
