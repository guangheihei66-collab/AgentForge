"""Read-only project metadata tool."""

import hashlib
from typing import Any

from .models import ToolDefinition
from ..contracts.permissions import PermissionLevel
from ..workspace.validator import WorkspaceValidator
from ..metadata_manifest import METADATA_MANIFEST_FILES, normalize_metadata_relative_path


class FileReadTool:
    ALLOWED_FILES = set(METADATA_MANIFEST_FILES)

    def __init__(self, validator: WorkspaceValidator):
        self.validator = validator
        self.definition = ToolDefinition(
            name="file_read",
            description="Read bounded, non-secret project metadata files.",
            risk_level="medium",
            permission_level=PermissionLevel.SAFE_READ,
            allowed_actions=("read_metadata",),
            executor=self,
            execution_contract_version="1",
        )

    def execute(self, action: str, parameters: dict[str, Any], workspace: str) -> dict[str, Any]:
        if action != "read_metadata":
            raise ValueError(f"Unsupported file action: {action}")
        relative_path = parameters.get("relative_path")
        if not isinstance(relative_path, str):
            raise ValueError("relative_path is required")
        try:
            relative_path = normalize_metadata_relative_path(relative_path)
        except ValueError as exc:
            raise PermissionError(str(exc)) from exc

        path = self.validator.validate_relative_file(workspace, relative_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(relative_path)
        if path.stat().st_size > 100_000:
            raise ValueError("Metadata file exceeds the read limit")

        content = path.read_text(encoding="utf-8", errors="replace")
        return {
            "relative_path": relative_path,
            "size": path.stat().st_size,
            "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "content": content[:20_000],
        }
