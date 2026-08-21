"""Default-deny permission checks for registered tools."""

from ..tools.models import ToolDefinition
from .levels import PermissionLevel


class PermissionDenied(PermissionError):
    """Raised when a tool request does not have the required permission."""


class PermissionPolicy:
    def check(
        self,
        definition: ToolDefinition,
        *,
        granted: PermissionLevel | None,
        approved: bool,
    ) -> None:
        if definition.permission_level == PermissionLevel.DENIED:
            raise PermissionDenied(f"Tool is denied: {definition.name}")
        if granted is None or granted == PermissionLevel.DENIED:
            raise PermissionDenied(f"Missing permission: {definition.name}")
        if granted != definition.permission_level:
            raise PermissionDenied(
                f"Incorrect permission for {definition.name}: "
                f"expected {definition.permission_level.value}"
            )
        if (
            definition.permission_level == PermissionLevel.APPROVED_EXEC
            and not approved
        ):
            raise PermissionDenied(f"Approval required: {definition.name}")
