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

Phase 0 storage policy approved. Phase 1.1 architecture and Phase 1.2 MVP scope freeze approved. Phase 2 foundation through Phase 10 release preparation are complete. Phase 11.1 added the deterministic AgentRuntime loop. Phase 11.2 adds capability-first planning, deterministic capability-to-tool resolution, approval-bound execution snapshots, registry fingerprints, and snapshot-only Runtime execution through the existing ToolGateway.

The Phase 11.2 MVP capabilities are `repository_state -> git_read`, `project_metadata -> file_read`, and `test_verification -> test_run`. Resolution fails closed unless exactly one registered, enabled, permission-compatible, parameter-valid candidate exists. Legacy concrete-tool plans remain readable but cannot request Phase 11.2 approval or execute through the new Runtime.

Real external LLM integration, Docker, PostgreSQL, RBAC, and write-capable tools have not started.

## Important design decisions

- CapabilityRegistry is independent from ToolRegistry.
- The application-owned resolver, not the model, selects the concrete tool.
- Approval binds task, plan/version, capability, concrete tool, normalized parameters, action, and registry fingerprint.
- Runtime verifies approved snapshots and cannot resolve or substitute tools.
- ToolGateway remains the only execution boundary.
- Existing SQLite databases receive the nullable approval snapshot column through an idempotent, non-destructive startup migration; live database recreation is forbidden.

## Resolved bugs

- Removed an eager capability-package resolver export that caused an import cycle through ToolGateway and ApprovalService.

## Next work

- Create and verify a D-drive backup before the first upgraded backend launch migrates the live SQLite database.
- Real external LLM integration and production platform capabilities remain future phases.
