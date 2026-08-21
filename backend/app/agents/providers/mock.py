"""Deterministic provider used by local development and tests."""

from typing import Any


class MockLLMProvider:
    def generate_plan(self, prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        del prompt, context
        return {
            "steps": [
                {
                    "step_id": "step-1",
                    "tool": "git_read",
                    "action": "check git status",
                    "risk_level": "low",
                    "permission_level": "safe_read",
                }
            ]
        }
