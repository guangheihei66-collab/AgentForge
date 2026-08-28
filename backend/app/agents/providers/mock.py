"""Deterministic provider used by local development and tests."""

from .base import LLMRequest, LLMResponse


class MockLLMProvider:
    provider_name = "mock"
    model_name = "deterministic-mock"

    def generate_plan(self, request: LLMRequest) -> LLMResponse:
        del request
        return LLMResponse(
            payload={
                "schema_version": 2,
                "summary": "Inspect the repository state.",
                "steps": [
                    {
                        "step_id": "step-1",
                        "capability_id": "repository_state",
                        "parameters": {},
                    }
                ],
            },
            provider=self.provider_name,
            model=self.model_name,
            duration_ms=0,
            attempt_count=1,
        )

    def generate_replan(self, request: LLMRequest) -> LLMResponse:
        del request
        return LLMResponse(
            payload={
                "decision_summary": "Inspect bounded project metadata.",
                "revised_remaining_steps": [
                    {
                        "step_id": "replan-1-step-1",
                        "capability_id": "project_metadata",
                        "parameters": {"relative_path": "PROJECT_CONTEXT.md"},
                    }
                ],
            },
            provider=self.provider_name,
            model=self.model_name,
            duration_ms=0,
            attempt_count=1,
        )

    def generate_analyst(self, request: LLMRequest) -> LLMResponse:
        """Return a deterministic report candidate from bounded input facts."""

        package = request.context.get("evidence_package", {})
        evidence = package.get("evidence", []) if isinstance(package, dict) else []
        executions = package.get("executions", []) if isinstance(package, dict) else []
        evidence = [item for item in evidence if isinstance(item, dict)]
        executions = [item for item in executions if isinstance(item, dict)]
        evidence_ref = evidence[0].get("id") if evidence else None
        failed = any(item.get("status") == "FAILED" for item in executions)

        if not evidence_ref:
            payload = {
                "summary": "No persisted evidence is available for a release assessment.",
                "overall_status": "UNKNOWN",
                "release_recommendation": "INSUFFICIENT_EVIDENCE",
                "findings": [],
                "next_actions": [],
                "limitations": [
                    "The governed run did not produce persisted evidence for analysis."
                ],
                "evidence_coverage": {
                    "available_count": 0,
                    "referenced_count": 0,
                    "truncated": bool(package.get("truncated", False))
                    if isinstance(package, dict)
                    else False,
                    "notes": [],
                },
            }
        elif failed:
            payload = {
                "summary": "The governed run contains a failed execution and is not ready for release.",
                "overall_status": "BLOCKED",
                "release_recommendation": "NOT_READY",
                "findings": [
                    {
                        "id": "finding-execution-failure",
                        "title": "Governed execution failed",
                        "severity": "HIGH",
                        "category": "quality",
                        "statement": "At least one persisted tool execution is marked FAILED.",
                        "rationale": "The execution record is the authoritative release signal for this run.",
                        "evidence_refs": [evidence_ref],
                        "recommended_action": "Investigate the failed execution before considering release.",
                    }
                ],
                "next_actions": [
                    {
                        "priority": 1,
                        "action": "Review the failed execution evidence and rerun the governed verification.",
                        "rationale": "The current evidence does not support release readiness.",
                        "evidence_refs": [evidence_ref],
                    }
                ],
                "limitations": [],
                "evidence_coverage": {
                    "available_count": len(evidence),
                    "referenced_count": 1,
                    "truncated": bool(package.get("truncated", False))
                    if isinstance(package, dict)
                    else False,
                    "notes": [],
                },
            }
        else:
            payload = {
                "summary": "The governed verification completed with persisted evidence.",
                "overall_status": "HEALTHY",
                "release_recommendation": "READY",
                "findings": [
                    {
                        "id": "finding-verification-complete",
                        "title": "Verification completed",
                        "severity": "INFO",
                        "category": "quality",
                        "statement": "The available governed execution evidence reports successful verification.",
                        "rationale": "The report is grounded in the persisted evidence package.",
                        "evidence_refs": [evidence_ref],
                        "recommended_action": "Complete the remaining human release checks.",
                    }
                ],
                "next_actions": [
                    {
                        "priority": 1,
                        "action": "Review the evidence references before release.",
                        "rationale": "A human remains responsible for the final release decision.",
                        "evidence_refs": [evidence_ref],
                    }
                ],
                "limitations": [],
                "evidence_coverage": {
                    "available_count": len(evidence),
                    "referenced_count": 1,
                    "truncated": bool(package.get("truncated", False))
                    if isinstance(package, dict)
                    else False,
                    "notes": [],
                },
            }
        return LLMResponse(
            payload=payload,
            provider=self.provider_name,
            model=self.model_name,
            duration_ms=0,
            attempt_count=1,
        )

    def test_connection(self) -> LLMResponse:
        return LLMResponse(
            payload={"status": "ok"},
            provider=self.provider_name,
            model=self.model_name,
            duration_ms=0,
            attempt_count=1,
        )
