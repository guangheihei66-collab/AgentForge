"""Prompt construction kept separate from planning orchestration."""


def build_planning_prompt(goal: str, context: dict | None = None) -> str:
    context_text = context or {}
    return (
        "Create a minimal, structured execution plan for this user goal. "
        "Use only the allowlisted read-safe tools and never execute anything.\n"
        f"Goal: {goal}\nContext: {context_text}"
    )
