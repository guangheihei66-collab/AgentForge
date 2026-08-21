import pytest

from app.permissions.levels import PermissionLevel
from app.tools.models import ToolDefinition
from app.tools.registry import ToolNotFound, ToolRegistry


class FakeExecutor:
    def execute(self, action, parameters, workspace):
        return {"action": action}


def definition(name="fake_read", enabled=True):
    return ToolDefinition(
        name=name,
        description="test tool",
        risk_level="low",
        permission_level=PermissionLevel.SAFE_READ,
        allowed_actions=("read",),
        executor=FakeExecutor(),
        enabled=enabled,
    )


def test_register_tool():
    registry = ToolRegistry()
    registry.register(definition())

    assert registry.require("fake_read").name == "fake_read"


def test_unknown_tool_rejected():
    with pytest.raises(ToolNotFound):
        ToolRegistry().require("missing")


def test_disabled_tool_rejected():
    registry = ToolRegistry()
    registry.register(definition(enabled=False))

    with pytest.raises(PermissionError):
        registry.require("fake_read")
