"""Best-effort, read-only Analyst synthesis after governed execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from ..agents.providers.base import (
    LLMProvider,
    LLMRequest,
    ProviderError,
    ProviderErrorCategory,
)
from ..storage.orm import AuditEventRecord, TaskRecord
from .models import AnalystDraft, AnalystReport, AnalystSynthesisStatus
from .package import EvidencePackageError, build_evidence_package
from .prompts import ANALYST_SYSTEM_INSTRUCTION, build_analyst_prompt
from .read_model import AnalystReadModel, read_analyst_report
from .storage import AnalystArtifactError, AnalystArtifactStore
from .validator import AnalystValidationError, validate_draft


TERMINAL_TASK_STATUSES = {"SUCCESS", "FAILED", "CANCELLED"}
MAX_AUDIT_PAYLOAD_BYTES = 8 * 1024


@dataclass(frozen=True, slots=True)
class AnalystSynthesisResult:
    task_id: str
    plan_id: str
    plan_version: int
    status: AnalystSynthesisStatus
    report: AnalystReport | None = None
    failure_category: str | None = None
    artifact_path: Path | None = None
    content_hash: str | None = None
    provider: str | None = None
    model: str | None = None
    generated_at: datetime | None = None


class AnalystService:
    def __init__(
        self,
        session: Session,
        provider: LLMProvider | None,
        *,
        data_root: str | Path | None = None,
        artifact_store: AnalystArtifactStore | None = None,
    ) -> None:
        self.session = session
        self.provider = provider
        self.artifacts = artifact_store or AnalystArtifactStore(
            data_root or r"D:\AgentProjectData\AgentForge"
        )

    def get_read_model(self, task_id: str) -> AnalystReadModel:
        return read_analyst_report(
            self.session, task_id=task_id, artifact_store=self.artifacts
        )

    def synthesize(
        self,
        *,
        task_id: str,
        plan_id: str,
        plan_version: int,
    ) -> AnalystSynthesisResult:
        task = self.session.get(TaskRecord, task_id)
        if task is None:
            return self._failure(
                task_id, plan_id, plan_version, "TASK_NOT_FOUND", emit_event=False
            )
        if task.status not in TERMINAL_TASK_STATUSES:
            return self._failure(
                task_id, plan_id, plan_version, "TASK_NOT_TERMINAL", emit_event=False
            )

        correlation_id = str(uuid4())
        provider_name, model_name = self._provider_metadata()
        self._audit(
            task_id,
            "ANALYST_SYNTHESIS_REQUESTED",
            correlation_id,
            {
                "plan_id": plan_id,
                "plan_version": plan_version,
                "task_status": task.status,
            },
        )
        self._audit(
            task_id,
            "ANALYST_SYNTHESIS_STARTED",
            correlation_id,
            {
                "plan_id": plan_id,
                "plan_version": plan_version,
                "provider": provider_name,
                "model": model_name,
            },
        )

        try:
            package = build_evidence_package(
                self.session,
                task_id=task_id,
                plan_id=plan_id,
                plan_version=plan_version,
            )
            if self.provider is None:
                raise ProviderError(
                    category=ProviderErrorCategory.NOT_CONFIGURED
                )
            generate = getattr(self.provider, "generate_analyst", None)
            if not callable(generate):
                return self._failure(
                    task_id,
                    plan_id,
                    plan_version,
                    "PROVIDER_UNSUPPORTED",
                    correlation_id=correlation_id,
                    provider=provider_name,
                    model=model_name,
                )
            response = generate(
                LLMRequest(
                    prompt=build_analyst_prompt(package),
                    context={"evidence_package": package.to_dict()},
                    output_schema=AnalystDraft.model_json_schema(),
                    system_instruction=ANALYST_SYSTEM_INSTRUCTION,
                )
            )
            draft = validate_draft(
                response.payload, evidence_ids=set(package.evidence_ids)
            )
            report = self._bind_report(
                draft,
                task_id=task_id,
                plan_id=plan_id,
                plan_version=plan_version,
                provider=provider_name or response.provider,
                model=model_name or response.model,
                package=package,
            )
            metadata = self.artifacts.write(report)
            self._audit(
                task_id,
                "ANALYST_SYNTHESIS_SUCCEEDED",
                correlation_id,
                {
                    "plan_id": plan_id,
                    "plan_version": plan_version,
                    "provider": report.provider,
                    "model": report.model,
                    "artifact_path": str(metadata.path),
                    "content_hash": metadata.content_hash,
                    "report_status": report.overall_status.value,
                    "release_recommendation": report.release_recommendation.value,
                    "finding_count": len(report.findings),
                    "evidence_ref_count": report.evidence_coverage.referenced_count,
                },
            )
            return AnalystSynthesisResult(
                task_id=task_id,
                plan_id=plan_id,
                plan_version=plan_version,
                status=AnalystSynthesisStatus.SUCCEEDED,
                report=report,
                artifact_path=metadata.path,
                content_hash=metadata.content_hash,
                provider=report.provider,
                model=report.model,
                generated_at=report.generated_at,
            )
        except ProviderError as exc:
            return self._failure(
                task_id,
                plan_id,
                plan_version,
                exc.category.value,
                correlation_id=correlation_id,
                provider=provider_name,
                model=model_name,
            )
        except AnalystValidationError as exc:
            return self._failure(
                task_id,
                plan_id,
                plan_version,
                exc.category,
                correlation_id=correlation_id,
                provider=provider_name,
                model=model_name,
            )
        except EvidencePackageError as exc:
            return self._failure(
                task_id,
                plan_id,
                plan_version,
                str(exc),
                correlation_id=correlation_id,
                provider=provider_name,
                model=model_name,
            )
        except AnalystArtifactError as exc:
            return self._failure(
                task_id,
                plan_id,
                plan_version,
                exc.category,
                correlation_id=correlation_id,
                provider=provider_name,
                model=model_name,
            )
        except Exception:
            return self._failure(
                task_id,
                plan_id,
                plan_version,
                "INTERNAL_VALIDATION_ERROR",
                correlation_id=correlation_id,
                provider=provider_name,
                model=model_name,
            )

    def _bind_report(
        self,
        draft: AnalystDraft,
        *,
        task_id: str,
        plan_id: str,
        plan_version: int,
        provider: str,
        model: str,
        package,
    ) -> AnalystReport:
        references = {
            reference
            for finding in draft.findings
            for reference in finding.evidence_refs
        }
        references.update(
            reference
            for action in draft.next_actions
            for reference in action.evidence_refs
        )
        notes = list(dict.fromkeys([*package.limitations, *draft.evidence_coverage.notes]))[:8]
        payload = draft.model_dump()
        payload["evidence_coverage"] = {
            "available_count": len(package.evidence),
            "referenced_count": len(references),
            "truncated": package.truncated,
            "notes": notes,
        }
        payload.update(
            {
                "schema_version": 1,
                "task_id": task_id,
                "plan_id": plan_id,
                "plan_version": plan_version,
                "provider": str(provider)[:128],
                "model": str(model)[:128],
                "generated_at": datetime.now(timezone.utc),
            }
        )
        return AnalystReport.model_validate(payload)

    def _provider_metadata(self) -> tuple[str | None, str | None]:
        if self.provider is None:
            return None, None
        return (
            str(getattr(self.provider, "provider_name", "unknown"))[:128],
            str(getattr(self.provider, "model_name", "unknown"))[:128],
        )

    def _failure(
        self,
        task_id: str,
        plan_id: str,
        plan_version: int,
        category: str,
        *,
        correlation_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        emit_event: bool = True,
    ) -> AnalystSynthesisResult:
        if emit_event:
            self._audit(
                task_id,
                "ANALYST_SYNTHESIS_FAILED",
                correlation_id or str(uuid4()),
                {
                    "plan_id": plan_id,
                    "plan_version": plan_version,
                    "provider": provider,
                    "model": model,
                    "failure_category": str(category)[:64],
                },
            )
        return AnalystSynthesisResult(
            task_id=task_id,
            plan_id=plan_id,
            plan_version=plan_version,
            status=AnalystSynthesisStatus.FAILED,
            failure_category=str(category)[:64],
            provider=provider,
            model=model,
        )

    def _audit(
        self,
        task_id: str,
        event_type: str,
        correlation_id: str,
        fields: dict[str, Any],
    ) -> None:
        payload = {"task_id": task_id}
        payload.update({key: value for key, value in fields.items() if value is not None})
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if len(serialized.encode("utf-8")) > MAX_AUDIT_PAYLOAD_BYTES:
            raise ValueError("Analyst audit payload exceeds the size limit")
        self.session.add(
            AuditEventRecord(
                task_id=task_id,
                event_type=event_type,
                actor="analyst_service",
                payload_summary=serialized,
                correlation_id=correlation_id,
            )
        )
        self.session.commit()
