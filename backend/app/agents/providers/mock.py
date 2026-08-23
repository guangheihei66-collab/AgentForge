"""Deterministic provider used by local development and tests."""

from .base import LLMRequest, LLMResponse


class MockLLMProvider:
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
            provider="mock",
            model="deterministic-mock",
            duration_ms=0,
            attempt_count=1,
        )

    def test_connection(self) -> LLMResponse:
        return LLMResponse(
            payload={"status": "ok"},
            provider="mock",
            model="deterministic-mock",
            duration_ms=0,
            attempt_count=1,
        )
