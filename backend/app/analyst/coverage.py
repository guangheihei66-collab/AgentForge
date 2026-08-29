"""Deterministic evidence sufficiency assessment for Analyst reports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..contracts.analysis import RELEASE_READINESS_CAPABILITIES, RELEASE_READINESS_PROFILE
from .models import EvidenceSufficiency


@dataclass(frozen=True, slots=True)
class EvidenceCoverageAssessment:
    sufficiency: EvidenceSufficiency
    expected_capabilities: tuple[str, ...]
    covered_capabilities: tuple[str, ...]
    missing_capabilities: tuple[str, ...]
    unauthorized_capabilities: tuple[str, ...]
    missing_plan_capabilities: tuple[str, ...]
    failed_capabilities: tuple[str, ...]
    notes: tuple[str, ...]

    @property
    def has_relevant_failure(self) -> bool:
        return bool(self.failed_capabilities)


def _status(value: Any) -> str:
    return str(value or "").upper()


def _execution_capability(package: dict[str, Any], execution: dict[str, Any]) -> str | None:
    for step in package.get("plan", {}).get("steps", []):
        if not isinstance(step, dict):
            continue
        if (
            step.get("resolved_tool_id") == execution.get("tool_name")
            and step.get("resolved_action") == execution.get("action")
        ):
            value = step.get("capability_id")
            return value if isinstance(value, str) else None
    return None


def assess_evidence_coverage(package) -> EvidenceCoverageAssessment:
    """Classify coverage from dimensions, authority, outcomes, and evidence refs."""

    data = package.to_dict() if hasattr(package, "to_dict") else dict(package)
    plan = data.get("plan", {})
    profile = plan.get("analysis_profile")
    planned = {
        step.get("capability_id")
        for step in plan.get("steps", [])
        if isinstance(step, dict) and isinstance(step.get("capability_id"), str)
    }
    if profile == RELEASE_READINESS_PROFILE:
        expected = set(RELEASE_READINESS_CAPABILITIES)
    else:
        expected = set(planned)
    authorized = {
        value
        for value in data.get("project", {}).get("allowed_capability_ids", [])
        if isinstance(value, str)
    }
    unauthorized = expected - authorized
    missing_plan = (expected & authorized) - planned
    evidence_ids = {
        item.get("id")
        for item in data.get("evidence", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    covered: set[str] = set()
    failed: set[str] = set()
    for observation in data.get("observations", []):
        if not isinstance(observation, dict):
            continue
        capability = observation.get("capability_id")
        if not isinstance(capability, str) or capability not in expected:
            continue
        if _status(observation.get("status")) == "FAILED":
            failed.add(capability)
        refs = observation.get("evidence_refs", [])
        if (
            _status(observation.get("status")) == "SUCCESS"
            and isinstance(refs, list)
            and any(ref in evidence_ids for ref in refs)
        ):
            covered.add(capability)

    # Older persisted terminal runs may not have a RUNTIME_OBSERVATION. The
    # resolved plan still gives a bounded, deterministic execution mapping.
    for execution in data.get("executions", []):
        if not isinstance(execution, dict):
            continue
        capability = _execution_capability(data, execution)
        if capability not in expected:
            continue
        if _status(execution.get("status")) == "FAILED":
            failed.add(capability)
        if _status(execution.get("status")) == "SUCCESS" and evidence_ids:
            covered.add(capability)

    relevant_expected = expected & authorized if profile == RELEASE_READINESS_PROFILE else expected
    missing = relevant_expected - covered
    all_covered = not (
        missing or unauthorized or missing_plan or failed or package.truncated
    ) and covered >= relevant_expected
    if all_covered:
        sufficiency = EvidenceSufficiency.SUFFICIENT
    elif covered:
        sufficiency = EvidenceSufficiency.PARTIAL
    else:
        sufficiency = EvidenceSufficiency.INSUFFICIENT

    notes: list[str] = []
    if profile == RELEASE_READINESS_PROFILE:
        missing_dimensions = sorted(expected - covered)
        if missing_dimensions:
            notes.append(
                "Missing release-readiness evidence: "
                + ", ".join(missing_dimensions)
                + "."
            )
    elif missing:
        notes.append("Missing evidence for planned capabilities: " + ", ".join(sorted(missing)) + ".")
    if unauthorized:
        notes.append(
            "Project authority does not allow: " + ", ".join(sorted(unauthorized)) + "."
        )
    if missing_plan:
        notes.append(
            "Plan does not include authorized release-readiness dimensions: "
            + ", ".join(sorted(missing_plan))
            + "."
        )
    if failed:
        notes.append(
            "Release-readiness verification failed: " + ", ".join(sorted(failed)) + "."
        )
    notes.extend(package.limitations)
    return EvidenceCoverageAssessment(
        sufficiency=sufficiency,
        expected_capabilities=tuple(sorted(expected)),
        covered_capabilities=tuple(sorted(covered)),
        missing_capabilities=tuple(sorted(missing)),
        unauthorized_capabilities=tuple(sorted(unauthorized)),
        missing_plan_capabilities=tuple(sorted(missing_plan)),
        failed_capabilities=tuple(sorted(failed)),
        notes=tuple(dict.fromkeys(notes))[:8],
    )
