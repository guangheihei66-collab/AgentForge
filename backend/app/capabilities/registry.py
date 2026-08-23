"""Independent registry of semantic capabilities."""

from ..contracts.permissions import PermissionLevel
from .models import CapabilityDefinition, ParameterFieldDefinition


class CapabilityNotFound(LookupError):
    """Raised when a capability is not explicitly registered."""


class CapabilityRegistry:
    def __init__(self) -> None:
        self._capabilities: dict[str, CapabilityDefinition] = {}

    def register(self, definition: CapabilityDefinition) -> None:
        if definition.id in self._capabilities:
            raise ValueError(f"Capability already registered: {definition.id}")
        self._capabilities[definition.id] = definition

    def get(self, capability_id: str) -> CapabilityDefinition | None:
        return self._capabilities.get(capability_id)

    def require(self, capability_id: str) -> CapabilityDefinition:
        definition = self.get(capability_id)
        if definition is None:
            raise CapabilityNotFound(f"Unknown capability: {capability_id}")
        return definition

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._capabilities))


def build_default_capability_registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry.register(
        CapabilityDefinition(
            id="repository_state",
            description="Read the current repository state.",
            risk_level="low",
            required_permission=PermissionLevel.SAFE_READ,
            candidate_tool_ids=("git_read",),
            action="status",
            parameter_schema=(),
        )
    )
    registry.register(
        CapabilityDefinition(
            id="project_metadata",
            description="Read bounded project metadata.",
            risk_level="medium",
            required_permission=PermissionLevel.SAFE_READ,
            candidate_tool_ids=("file_read",),
            action="read_metadata",
            parameter_schema=(
                ParameterFieldDefinition(
                    name="relative_path",
                    required=True,
                    allowed_values=(
                        "AGENTS.md",
                        "PROJECT_CONTEXT.md",
                        "README.md",
                        "package-lock.json",
                        "package.json",
                        "pyproject.toml",
                        "requirements.txt",
                        "tsconfig.json",
                    ),
                ),
            ),
        )
    )
    registry.register(
        CapabilityDefinition(
            id="test_verification",
            description="Run one predefined test profile.",
            risk_level="medium",
            required_permission=PermissionLevel.APPROVED_EXEC,
            candidate_tool_ids=("test_run",),
            action="run_profile",
            parameter_schema=(
                ParameterFieldDefinition(
                    name="profile",
                    required=True,
                    allowed_values=("smoke", "unit"),
                ),
            ),
        )
    )
    return registry
