"""Validation for untrusted structured Analyst output."""

import json
from typing import Any, Iterable

from pydantic import ValidationError

from .models import AnalystDraft


class AnalystValidationError(ValueError):
    """Safe validation failure category without retaining provider content."""

    def __init__(self, category: str):
        self.category = category
        super().__init__(category)


def _parse_payload(payload: Any) -> Any:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            raise AnalystValidationError("MALFORMED_OUTPUT") from None
    if not isinstance(payload, dict):
        raise AnalystValidationError("MALFORMED_OUTPUT")
    return payload


def _all_references(draft: AnalystDraft) -> Iterable[str]:
    for finding in draft.findings:
        yield from finding.evidence_refs
    for action in draft.next_actions:
        yield from action.evidence_refs


def validate_draft(
    payload: Any,
    *,
    evidence_ids: set[str],
) -> AnalystDraft:
    """Parse a provider candidate and require references to persisted evidence."""

    candidate = _parse_payload(payload)
    try:
        draft = AnalystDraft.model_validate(candidate)
    except ValidationError:
        raise AnalystValidationError("MALFORMED_OUTPUT") from None

    references = tuple(_all_references(draft))
    if any(reference not in evidence_ids for reference in references):
        raise AnalystValidationError("INVALID_EVIDENCE_REFERENCE")
    if draft.evidence_coverage.referenced_count > draft.evidence_coverage.available_count:
        raise AnalystValidationError("MALFORMED_OUTPUT")
    return draft
