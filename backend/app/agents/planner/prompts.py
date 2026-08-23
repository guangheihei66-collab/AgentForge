"""Prompt construction kept separate from planning orchestration."""


def build_planning_prompt(goal: str, context: dict | None = None) -> str:
    context_text = context or {}
    return (
        "Create a minimal, structured execution plan for this user goal. "
        "Return schema_version 2 steps containing only step_id, capability_id, "
        "and bounded parameters. Allowed capabilities are repository_state, "
        "project_metadata, and test_verification. Never select a concrete tool, "
        "provide a shell command, or execute anything.\n"
        f"Goal: {goal}\nContext: {context_text}"
    )
