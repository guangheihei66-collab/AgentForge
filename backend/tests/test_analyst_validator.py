import pytest

from app.analyst.validator import AnalystValidationError, validate_draft

from tests.test_analyst_models import valid_draft


def test_validator_accepts_only_known_persisted_evidence_ids():
    draft = validate_draft(valid_draft(), evidence_ids={"evidence-1"})

    assert draft.findings[0].evidence_refs == ["evidence-1"]


@pytest.mark.parametrize(
    "reference",
    ["missing-evidence", "evidence-from-another-task"],
)
def test_validator_rejects_unknown_or_cross_task_evidence(reference):
    payload = valid_draft()
    payload["findings"][0]["evidence_refs"] = [reference]

    with pytest.raises(AnalystValidationError, match="INVALID_EVIDENCE_REFERENCE"):
        validate_draft(payload, evidence_ids={"evidence-1"})


def test_validator_rejects_non_object_provider_payload():
    with pytest.raises(AnalystValidationError, match="MALFORMED_OUTPUT"):
        validate_draft("not-json", evidence_ids={"evidence-1"})


def test_validator_rejects_empty_evidence_reference():
    payload = valid_draft()
    payload["next_actions"][0]["evidence_refs"] = [""]

    with pytest.raises(AnalystValidationError, match="MALFORMED_OUTPUT"):
        validate_draft(payload, evidence_ids={"evidence-1"})
