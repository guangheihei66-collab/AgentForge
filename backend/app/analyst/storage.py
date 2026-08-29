"""Bounded, hash-verified persistence for derived Analyst artifacts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from .models import AnalystReport


MAX_ARTIFACT_BYTES = 64 * 1024
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class AnalystArtifactError(ValueError):
    """Safe artifact failure category without exposing filesystem details."""

    def __init__(self, category: str):
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, slots=True)
class AnalystArtifactMetadata:
    path: Path
    content_hash: str
    size_bytes: int


class AnalystArtifactStore:
    def __init__(self, data_root: str | Path, *, max_bytes: int = MAX_ARTIFACT_BYTES):
        self.data_root = Path(data_root).resolve()
        self.max_bytes = max_bytes

    def write(self, report: AnalystReport) -> AnalystArtifactMetadata:
        if not _SAFE_COMPONENT.fullmatch(report.task_id):
            raise AnalystArtifactError("ARTIFACT_PATH_INVALID")
        payload = report.model_dump(mode="json")
        content = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        if len(content) > self.max_bytes:
            raise AnalystArtifactError("ARTIFACT_TOO_LARGE")
        path = (
            self.data_root
            / "artifacts"
            / report.task_id
            / f"analyst-report-v{report.plan_version}.json"
        )
        self._assert_contained(path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_bytes(content)
            temporary.replace(path)
        except OSError:
            raise AnalystArtifactError("ARTIFACT_WRITE_FAILED") from None
        return AnalystArtifactMetadata(
            path=path,
            content_hash=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
        )

    def load(
        self,
        path: str | Path,
        *,
        expected_hash: str,
        task_id: str,
        plan_id: str,
        plan_version: int,
    ) -> AnalystReport:
        candidate = Path(path)
        self._assert_contained(candidate)
        if not candidate.is_file():
            raise AnalystArtifactError("ARTIFACT_NOT_FOUND")
        try:
            content = candidate.read_bytes()
        except OSError:
            raise AnalystArtifactError("ARTIFACT_READ_FAILED") from None
        if len(content) > self.max_bytes:
            raise AnalystArtifactError("ARTIFACT_TOO_LARGE")
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash != expected_hash:
            raise AnalystArtifactError("ARTIFACT_HASH_MISMATCH")
        try:
            payload = json.loads(content)
            report = AnalystReport.model_validate(payload)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            raise AnalystArtifactError("ARTIFACT_INVALID") from None
        if (
            report.task_id != task_id
            or report.plan_id != plan_id
            or report.plan_version != plan_version
        ):
            raise AnalystArtifactError("ARTIFACT_BINDING_INVALID")
        return report

    def _assert_contained(self, path: Path) -> None:
        try:
            resolved = path.resolve()
            resolved.relative_to(self.data_root)
        except (OSError, ValueError):
            raise AnalystArtifactError("ARTIFACT_PATH_INVALID") from None
