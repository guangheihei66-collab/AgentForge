"""Strict, bounded contracts for derived Analyst reports.

The provider supplies only ``AnalystDraft``. Server-owned task and plan
identity is injected into ``AnalystReport`` after evidence-reference
validation. This prevents model output from changing report authority.
"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


MAX_FINDINGS = 12
MAX_NEXT_ACTIONS = 12
MAX_LIMITATIONS = 12
MAX_EVIDENCE_REFS = 5

ShortText = Annotated[str, StringConstraints(min_length=1, max_length=1_000)]
TitleText = Annotated[str, StringConstraints(min_length=1, max_length=200)]
LongText = Annotated[str, StringConstraints(min_length=1, max_length=5_000)]
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=128)]
EvidenceReference = Annotated[str, StringConstraints(min_length=1, max_length=128)]


class AnalystSeverity(StrEnum):
    BLOCKER = "BLOCKER"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class OverallStatus(StrEnum):
    HEALTHY = "HEALTHY"
    AT_RISK = "AT_RISK"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class ReleaseRecommendation(StrEnum):
    READY = "READY"
    READY_WITH_CONDITIONS = "READY_WITH_CONDITIONS"
    NOT_READY = "NOT_READY"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class AnalystSynthesisStatus(StrEnum):
    NOT_REQUESTED = "NOT_REQUESTED"
    PENDING = "PENDING"
    GENERATING = "GENERATING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


AnalystCategory = Literal[
    "release", "security", "quality", "operational", "evidence"
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceCoverage(StrictModel):
    available_count: int = Field(ge=0, le=100)
    referenced_count: int = Field(ge=0, le=100)
    truncated: bool
    notes: list[ShortText] = Field(default_factory=list, max_length=8)


class AnalystFinding(StrictModel):
    id: Identifier
    title: TitleText
    severity: AnalystSeverity
    category: AnalystCategory
    statement: LongText
    rationale: LongText
    evidence_refs: list[EvidenceReference] = Field(
        min_length=1, max_length=MAX_EVIDENCE_REFS
    )
    recommended_action: LongText


class AnalystNextAction(StrictModel):
    priority: int = Field(ge=1, le=100)
    action: LongText
    rationale: LongText
    evidence_refs: list[EvidenceReference] = Field(
        min_length=1, max_length=MAX_EVIDENCE_REFS
    )


class AnalystDraft(StrictModel):
    summary: LongText
    overall_status: OverallStatus
    release_recommendation: ReleaseRecommendation
    findings: list[AnalystFinding] = Field(max_length=MAX_FINDINGS)
    next_actions: list[AnalystNextAction] = Field(max_length=MAX_NEXT_ACTIONS)
    limitations: list[ShortText] = Field(max_length=MAX_LIMITATIONS)
    evidence_coverage: EvidenceCoverage


class AnalystReport(AnalystDraft):
    schema_version: Literal[1] = 1
    task_id: Identifier
    plan_id: Identifier
    plan_version: int = Field(ge=1, le=100_000)
    provider: Identifier
    model: Identifier
    generated_at: datetime
