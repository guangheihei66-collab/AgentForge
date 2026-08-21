"""Tool contracts. Executors never receive raw shell commands."""

from dataclasses import dataclass
from typing import Any, Protocol

from ..contracts.permissions import PermissionLevel


class ToolExecutor(Protocol):
    def execute(self, action: str, parameters: dict[str, Any], workspace: str) -> dict[str, Any]:
        """Execute one validated action in one validated workspace."""


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    risk_level: str
    permission_level: PermissionLevel
    allowed_actions: tuple[str, ...]
    executor: ToolExecutor
    enabled: bool = True
