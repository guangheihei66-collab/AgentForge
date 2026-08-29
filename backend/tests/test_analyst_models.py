import pytest
from pydantic import ValidationError

from app.analyst.models import (
    AnalystDraft,
    AnalystFinding,
    AnalystNextAction,
    AnalystReport,
    AnalystSeverity,
    EvidenceCoverage,
    OverallStatus,
    ReleaseRecommendation,
)


def evidence_coverage() -> dict:
    return {
        "available_count": 1,
        "referenced_count": 1,
        "truncated": False,
        "notes": [],
    }


def valid_draft() -> dict:
    return {
        "summary": "The release verification produced bounded evidence.",
        "overall_status": "HEALTHY",
        "release_recommendation": "READY",
        "findings": [
            {
                "id": "finding-1",
                "title": "Verification completed",
                "severity": "INFO",
                "category": "quality",
                "statement": "The approved verification step completed.",
                "rationale": "The persisted execution evidence reports success.",
                "evidence_refs": ["evidence-1"],
                "recommended_action": "Continue with the release checklist.",
            }
        ],
        "next_actions": [
            {
                "priority": 1,
                "action": "Review the evidence before release.",
                "rationale": "A human should confirm the release decision.",
                "evidence_refs": ["evidence-1"],
            }
        ],
        "limitations": [],
        "evidence_coverage": evidence_coverage(),
    }


def test_valid_analyst_draft_has_controlled_values():
    draft = AnalystDraft.model_validate(valid_draft())

    assert draft.overall_status is OverallStatus.HEALTHY
    assert draft.release_recommendation is ReleaseRecommendation.READY
    assert draft.findings[0].severity is AnalystSeverity.INFO
    assert draft.evidence_coverage == EvidenceCoverage.model_validate(evidence_coverage())


def test_server_bound_report_adds_task_and_plan_identity():
    report = AnalystReport.model_validate(
        {
            **valid_draft(),
            "schema_version": 1,
            "task_id": "task-1",
            "plan_id": "plan-1",
            "plan_version": 2,
            "provider": "mock",
            "model": "deterministic-mock",
            "generated_at": "2026-08-28T12:00:00Z",
        }
    )

    assert report.task_id == "task-1"
    assert report.plan_version == 2


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: {**value, "unexpected": "must fail"},
        lambda value: {**value, "findings": [{**value["findings"][0], "evidence_refs": []}]},
        lambda value: {**value, "overall_status": "invented"},
        lambda value: {**value, "summary": "x" * 5001},
        lambda value: {**value, "findings": value["findings"] * 13},
        lambda value: {**value, "reasoning": "chain of thought must not be accepted"},
    ],
)
def test_unsafe_or_invalid_report_fields_are_rejected(mutator):
    with pytest.raises(ValidationError):
        AnalystDraft.model_validate(mutator(valid_draft()))


def test_material_finding_fields_are_bounded_and_strict():
    with pytest.raises(ValidationError):
        AnalystFinding.model_validate(
            {
                "id": "finding-1",
                "title": "x" * 201,
                "severity": "HIGH",
                "category": "release",
                "statement": "supported",
                "rationale": "supported",
                "evidence_refs": ["evidence-1"],
                "recommended_action": "bounded",
            }
        )


def test_next_actions_require_evidence_reference():
    with pytest.raises(ValidationError):
        AnalystNextAction.model_validate(
            {
                "priority": 1,
                "action": "Act",
                "rationale": "Reason",
                "evidence_refs": [],
            }
        )
