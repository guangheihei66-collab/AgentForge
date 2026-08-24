"""The only execution path for AgentForge tools."""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from ..approvals.service import ApprovalService
from ..contracts.permissions import PermissionLevel
from ..permissions.policy import PermissionPolicy
from ..storage.orm import (
    AuditEventRecord,
    EvidenceRecord,
    TaskRecord,
    ToolExecutionRecord,
)
from ..workspace.validator import WorkspaceValidator
from .models import ToolDefinition
from .registry import ToolRegistry


@dataclass(frozen=True, slots=True)
class ToolExecutionRequest:
    task_id: str
    tool_name: str
    action: str
    workspace: str
    parameters: dict[str, Any]
    project_authority_fingerprint: str | None = None
    granted_permission: PermissionLevel | None = None
    approved: bool = False
    plan_id: str | None = None
    plan_version: int | None = None


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    execution_id: str
    status: str
    summary: str
    artifact_path: str | None = None
    content_hash: str | None = None
    evidence_id: str | None = None


class ToolGateway:
    def __init__(
        self,
        session: Session,
        registry: ToolRegistry,
        workspace_validator: WorkspaceValidator,
        artifact_root: str | Path,
        permission_policy: PermissionPolicy | None = None,
    ):
        self.session = session
        self.registry = registry
        self.workspace_validator = workspace_validator
        self.artifact_root = Path(artifact_root).resolve()
        data_root = Path(
            os.getenv("AGENTFORGE_DATA_ROOT", r"D:\AgentProjectData\AgentForge")
        ).resolve()
        try:
            self.artifact_root.relative_to(data_root)
        except ValueError as exc:
            raise ValueError("Artifact root must be inside the AgentForge data root") from exc
        self.permission_policy = permission_policy or PermissionPolicy()

    def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        task = self.session.get(TaskRecord, request.task_id)
        if task is None:
            raise LookupError(f"Task not found: {request.task_id}")

        execution = ToolExecutionRecord(
            task_id=request.task_id,
            tool_name=request.tool_name,
            action=request.action,
            status="REQUESTED",
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(execution)
        self.session.flush()

        try:
            ApprovalService(self.session).assert_project_execution_allowed(
                task_id=request.task_id,
                plan_id=request.plan_id,
                plan_version=request.plan_version,
                workspace=request.workspace,
                authority_fingerprint=request.project_authority_fingerprint,
            )
            definition = self.registry.require(request.tool_name)
            if request.action not in definition.allowed_actions:
                raise PermissionError(
                    f"Action is not allowed for {request.tool_name}: {request.action}"
                )
            self.permission_policy.check(
                definition,
                granted=request.granted_permission,
                approved=request.approved,
            )
            if definition.permission_level == PermissionLevel.APPROVED_EXEC:
                ApprovalService(self.session).assert_execution_allowed(
                    task_id=request.task_id,
                    plan_id=request.plan_id,
                    plan_version=request.plan_version,
                )
            workspace = self.workspace_validator.validate_workspace(request.workspace)
            result = definition.executor.execute(
                request.action, request.parameters, str(workspace)
            )
            artifact_path, content_hash = self._write_artifact(execution.id, result)
            summary = self._summary(result)
            status = self._classify_result(definition, result)
            execution.status = status
            execution.result_summary = summary
            execution.artifact_path = artifact_path
            execution.content_hash = content_hash
            execution.finished_at = datetime.now(timezone.utc)
            evidence = EvidenceRecord(
                task_id=request.task_id,
                summary=summary,
                artifact_path=artifact_path,
                content_hash=content_hash,
            )
            self.session.add(evidence)
            self.session.flush()
            self._audit(request, status, summary)
            self.session.commit()
            return ToolExecutionResult(
                execution_id=execution.id,
                status=status,
                summary=summary,
                artifact_path=artifact_path,
                content_hash=content_hash,
                evidence_id=evidence.id,
            )
        except (PermissionError, ValueError, LookupError, FileNotFoundError) as exc:
            execution.status = "REJECTED"
            execution.result_summary = str(exc)[:2_000]
            execution.finished_at = datetime.now(timezone.utc)
            self._audit(request, "REJECTED", str(exc)[:2_000])
            self.session.commit()
            raise
        except Exception as exc:
            summary = str(exc)[:2_000]
            execution.status = "FAILED"
            execution.result_summary = summary
            execution.finished_at = datetime.now(timezone.utc)
            self._audit(request, "FAILED", summary)
            self.session.commit()
            return ToolExecutionResult(
                execution_id=execution.id,
                status="FAILED",
                summary=summary,
            )

    @staticmethod
    def _classify_result(definition: ToolDefinition, result: dict[str, Any]) -> str:
        classifier = getattr(definition.executor, "classify_result", None)
        if classifier is None:
            return "SUCCESS"
        status = classifier(result)
        if status not in {"SUCCESS", "FAILED"}:
            raise ValueError("Tool result classifier returned an unsupported status")
        return status

    def _audit(self, request: ToolExecutionRequest, result: str, summary: str) -> None:
        payload = json.dumps(
            {
                "task_id": request.task_id,
                "tool_name": request.tool_name,
                "action": request.action,
                "result": result,
                "summary": summary[:2_000],
            },
            ensure_ascii=False,
        )
        self.session.add(
            AuditEventRecord(
                task_id=request.task_id,
                event_type="TOOL_EXECUTION",
                actor="tool_gateway",
                payload_summary=payload,
                correlation_id=str(uuid4()),
            )
        )

    def _write_artifact(self, execution_id: str, result: dict[str, Any]) -> tuple[str, str]:
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(result, ensure_ascii=False, indent=2)[:100_000]
        content = payload.encode("utf-8")
        digest = hashlib.sha256(content).hexdigest()
        path = self.artifact_root / f"{execution_id}.json"
        path.write_bytes(content)
        return str(path), digest

    @staticmethod
    def _summary(result: dict[str, Any]) -> str:
        return json.dumps(result, ensure_ascii=False)[:2_000]
