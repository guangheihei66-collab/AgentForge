# AgentForge Interview Story

## One-minute explanation

AgentForge is a self-hosted enterprise Agent governance platform for engineering release verification. The user submits a goal, a Planner Agent converts it into a validated structured plan, and the system pauses at a human approval gate. Only after approval can the Tool Gateway execute allowlisted, workspace-scoped tools. Every execution produces evidence and an audit record that the operator can inspect in the dashboard.

## Why governance is the central design problem

An LLM can produce useful plans, but its output should not be treated as authorization. AgentForge separates intent from authority: the Planner proposes, the validator checks, the human approves, and the Tool Gateway enforces the final boundary.

## Engineering trade-offs

- SQLite keeps the MVP portable and easy to demo; PostgreSQL is a later deployment concern.
- A custom state machine keeps transitions explicit and testable.
- MockLLMProvider makes tests deterministic while preserving a provider boundary for future API models.
- Read-safe tools and predefined test profiles demonstrate governance without introducing unrestricted shell execution.
- A neutral contracts module prevents the permission layer from depending on tool implementations and removes circular imports.

## Strong closing point

The project demonstrates that an Agent application is not only about prompting a model. It is about building a reliable control plane around model intent: permissions, approval, state, execution, evidence, and auditability.
