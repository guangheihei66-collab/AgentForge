"""Deterministic provider used by local development and tests."""

from typing import Any


class MockLLMProvider:
    def generate_plan(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        del prompt, context
        return {
            "schema_version": 2,
            "steps": [
                {
                    "step_id": "step-1",
                    "capability_id": "repository_state",
                    "parameters": {},
                }
            ]
        }
