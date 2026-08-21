"""Construction of the explicitly allowlisted MVP tool registry."""

from .file_read import FileReadTool
from .git_read import GitReadTool
from .registry import ToolRegistry
from .test_tool import TestTool
from ..workspace.validator import WorkspaceValidator


def build_default_registry(validator: WorkspaceValidator) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(GitReadTool().definition)
    registry.register(FileReadTool(validator).definition)
    registry.register(TestTool().definition)
    return registry
