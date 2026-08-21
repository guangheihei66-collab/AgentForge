"""Permission levels used by the Tool Gateway."""

from enum import StrEnum


class PermissionLevel(StrEnum):
    SAFE_READ = "SAFE_READ"
    APPROVED_EXEC = "APPROVED_EXEC"
    DENIED = "DENIED"
