# AgentForge Project Context

## Product goal

Build a portfolio-grade self-hosted enterprise Agent workflow platform that demonstrates planning, approval, governed tool execution, evidence collection, auditability, and evaluation.

## Demo scenario

Release Verification Agent: determine whether version 2.0 is ready for release.

## Technical boundaries

- Backend: Python + FastAPI.
- Frontend: React + TypeScript.
- MVP database: SQLite.
- Workflow: custom state machine.
- Agent: API-based model only.
- Tools: Git read, File read, and predefined Test profiles.
- No arbitrary shell, destructive actions, local models, Docker, Kubernetes, RAG, or vector database in MVP.

## Storage rules

- Source: `D:\AgentProjects\AgentForge\`.
- Mutable data: `D:\AgentProjectData\AgentForge\`.
- Do not store models, Docker data, large logs, runtime artifacts, or temporary data in source.
- Any operation expected to exceed 1 GiB requires explicit approval.
- Keep output bounded and never commit secrets or runtime data.

## Current status

Phase 0 storage policy approved. Phase 1.1 architecture and Phase 1.2 MVP scope freeze approved. Phase 2 foundation, Phase 3 backend foundation, Phase 4 Tool Gateway foundation, Phase 5 Approval Gateway and Audit Query, and Phase 6 Planner Agent with Mock LLM integration are complete. Real external LLM integration, frontend, Docker, PostgreSQL, RBAC, and write-capable tools have not started.
