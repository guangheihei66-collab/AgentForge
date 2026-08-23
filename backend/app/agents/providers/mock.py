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

    def test_connection(self) -> LLMResponse:
        return LLMResponse(
            payload={"status": "ok"},
            provider=self.provider_name,
            model=self.model_name,
            duration_ms=0,
            attempt_count=1,
        )
