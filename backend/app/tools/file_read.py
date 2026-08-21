"""Read-only project metadata tool."""

import hashlib
from pathlib import Path
from typing import Any

from .models import ToolDefinition
from ..contracts.permissions import PermissionLevel
from ..workspace.validator import WorkspaceValidator


class FileReadTool:
    ALLOWED_FILES = {
        "README.md",
        "PROJECT_CONTEXT.md",
        "AGENTS.md",
        "requirements.txt",
        "pyproject.toml",
        "package.json",
        "package-lock.json",
        "tsconfig.json",
    }

    def __init__(self, validator: WorkspaceValidator):
        self.validator = validator
        self.definition = ToolDefinition(
            name="file_read",
            description="Read bounded, non-secret project metadata files.",
            risk_level="medium",
            permission_level=PermissionLevel.SAFE_READ,
            allowed_actions=("read_metadata",),
            executor=self,
        )

    def execute(self, action: str, parameters: dict[str, Any], workspace: str) -> dict[str, Any]:
        if action != "read_metadata":
            raise ValueError(f"Unsupported file action: {action}")
        relative_path = parameters.get("relative_path")
        if not isinstance(relative_path, str):
            raise ValueError("relative_path is required")
        if Path(relative_path).name not in self.ALLOWED_FILES:
            raise PermissionError("File is not an allowed metadata file")

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
