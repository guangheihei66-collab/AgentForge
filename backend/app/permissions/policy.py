"""Default-deny permission checks independent from tool implementations."""

from typing import Protocol

from ..contracts.permissions import PermissionLevel


class PermissionDefinition(Protocol):
    name: str
    permission_level: PermissionLevel


class PermissionDenied(PermissionError):
    """Raised when a tool request does not have the required permission."""


class PermissionPolicy:
    def check(
        self,
        definition: PermissionDefinition,
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
