"""Registry for explicitly enabled tools."""

from .models import ToolDefinition


class ToolNotFound(LookupError):
    """Raised when a tool is not registered."""


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._tools:
            raise ValueError(f"Tool already registered: {definition.name}")
        self._tools[definition.name] = definition

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def require(self, name: str) -> ToolDefinition:
        definition = self.get(name)
        if definition is None:
            raise ToolNotFound(f"Unknown tool: {name}")
        if not definition.enabled:
            raise PermissionError(f"Tool is disabled: {name}")
        return definition

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))
