"""Thin adapter from resolved execution snapshots to the Tool Gateway."""

from ..capabilities.models import ResolvedExecutionSnapshot
from ..contracts.permissions import PermissionLevel
from ..tools.gateway import ToolExecutionRequest, ToolExecutionResult, ToolGateway


class RuntimeExecutor:
    """Pass already-resolved execution data through the existing gateway."""

    def __init__(self, gateway: ToolGateway):
        self.gateway = gateway

    def execute(
        self,
        *,
        task_id: str,
        plan_id: str,
        plan_version: int,
        workspace: str,
        snapshot: ResolvedExecutionSnapshot,
        granted_permission: PermissionLevel,
    ) -> ToolExecutionResult:
        return self.gateway.execute(
            ToolExecutionRequest(
                task_id=task_id,
                tool_name=snapshot.resolved_tool_id,
                action=snapshot.resolved_action,
                workspace=workspace,
                parameters=snapshot.parameters_dict(),
                granted_permission=granted_permission,
                approved=True,
                plan_id=plan_id,
                plan_version=plan_version,
            )
        )
