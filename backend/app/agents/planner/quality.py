"""Profile-scoped quality checks for provider-generated capability plans."""

from collections.abc import Iterable

from ...contracts.analysis import RELEASE_READINESS_CAPABILITIES, RELEASE_READINESS_PROFILE
from .schemas import PlanContract
from .validator import PlanValidationError


def validate_plan_quality(
    plan: PlanContract,
    *,
    analysis_profile: str | None,
    authorized_capability_ids: Iterable[str],
) -> None:
    """Require coverage only for relevant capabilities already authorized.

    This check never adds steps or grants authority. An authority-limited
    project remains limited and the downstream Analyst reports that gap.
    """

    if analysis_profile != RELEASE_READINESS_PROFILE:
        return
    authorized = set(authorized_capability_ids)
    required = authorized.intersection(RELEASE_READINESS_CAPABILITIES)
    planned = {step.capability_id for step in plan.steps}
    missing = sorted(required - planned)
    if missing:
        raise PlanValidationError(
            "Release-readiness plan does not cover authorized evidence dimensions",
            diagnostics={
                "validation_error_count": 1,
                "validation_error_paths": ["steps"],
                "validation_error_types": ["missing_evidence_dimensions"],
                "missing_capabilities": missing,
                "validation_summary_truncated": False,
            },
        )
