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

Phase 0 storage policy approved. Phase 1.1 architecture and Phase 1.2 MVP scope freeze approved. Phase 2 foundation through Phase 10 release preparation are complete. Phase 11.1 added the deterministic AgentRuntime loop. Phase 11.2 added capability-first planning and approval-bound resolution. Phase 12 added the bounded OpenAI-compatible provider. Phase 13 added controlled hybrid re-planning. Phase 14 adds local Projects as execution-security boundaries: every new Task belongs to one ACTIVE Project with a canonical local workspace and an explicit semantic Capability allow-list. Phase 15A is complete on main: the current Agent Workspace preserves the approval safety boundary, native en-US/zh-CN localization is integrated across the product surfaces, and the release candidate is frozen pending one final human workflow test. The `feature/evidence-ai-analyst-report` branch adds the final downstream evidence-grounded AI Analyst report capability without changing those execution authorities. The same branch now includes a native Windows single-instance, windowless desktop launcher with tray controls and external runtime logs; it is ready for final HUMAN desktop acceptance.

The Phase 11.2 MVP capabilities are `repository_state -> git_read`, `project_metadata -> file_read`, and `test_verification -> test_run`. Resolution fails closed unless exactly one registered, enabled, permission-compatible, parameter-valid candidate exists. Legacy concrete-tool plans remain readable but cannot request Phase 11.2 approval or execute through the new Runtime.

The real provider is opt-in through explicit process configuration or the compact launcher AI Provider Settings flow. Product mode fails closed when invalid and cannot select concrete tools or bypass validation, approval, Runtime, or ToolGateway. Non-secret provider metadata is persisted in a user-local configuration outside the repository; the API key is protected with Windows user-scoped DPAPI, injected only into the AgentForge-owned backend child, and never exposed through the API. Docker, PostgreSQL, RBAC, and write-capable tools have not started.

Re-planning is limited to two successor attempts and twelve total steps across plan versions. Replan context is capped at 8 KiB and the complete prompt at 12 KiB. Every successor version, including safe-read-only plans, requires a fresh approval bound to its exact resolved snapshots. Plan v1 remains immutable and its approval cannot authorize v2. Only bounded summaries, fingerprints, reason codes, and evidence references are audited; Chain of Thought, raw provider output, raw tool output, and provider credentials are not stored. Mock re-planning is deterministic and offline, and real-provider failures never silently fall back to Mock.

Project Capability policy defaults to empty and future registry additions are never inherited. Plan and approval snapshots carry application-owned Project authority. Planner, Replanner, ApprovalService, Runtime, and ToolGateway revalidate it; SAFE_READ does not bypass it. Workspace, capability, version, fingerprint, and status drift invalidate earlier approvals. Name, description, and environment remain descriptive in Phase 14. Archived Projects and legacy null-Project Tasks remain readable but cannot start or continue execution.

## Important design decisions

- CapabilityRegistry is independent from ToolRegistry.
- The application-owned resolver, not the model, selects the concrete tool.
- Approval binds task, plan/version, capability, concrete tool, normalized parameters, action, and registry fingerprint.
- Runtime verifies approved snapshots and cannot resolve or substitute tools.
- ToolGateway remains the only execution boundary.
- Existing SQLite databases receive the nullable approval snapshot column through an idempotent, non-destructive startup migration; live database recreation is forbidden.
- LLM transport is bounded by timeout, response-size and output-token limits; retries apply only to transient failures and never persist secrets.
- Re-planning pauses the current version, creates an immutable successor only after policy and application validation, and requires new human approval before Runtime can resume.
- Phase 13 adds no database migration, persistent status vocabulary, dependency, or frontend setup.
- Phase 14 adds `projects` and nullable `tasks.project_id` through an idempotent, non-destructive migration. Applying it to the live database requires a separately approved backup-and-migration operation.
- Project roots must be existing local directories; remote/UNC/device roots and traversal, sibling-prefix, symlink, junction, reparse, or cross-Project escapes fail closed.
- Native localization uses the approved i18next/react-i18next boundary. `agentforge.locale` stores only the selected locale, while goals, paths, identifiers, provider values, capability values, audit data, evidence references, and other machine/runtime values remain unchanged.
- Dashboard and project selection await data loading without overriding the user's navigation target; this keeps the current Agent Workspace reachable during asynchronous hydration.
- The AI Analyst receives only a bounded persisted EvidencePackage after terminal Runtime facts are committed. Strict schema and same-task evidence-reference validation run before a canonical hash-verified external report artifact is accepted; Analyst status and safe metadata reuse AuditEvent without a new database table.
- Analyst recommendations are informational and never authorize execution. Provider failure, malformed output, invalid evidence references, or artifact tampering preserve the authoritative Task, ToolExecution, Observation, Evidence, and Audit facts.
- The launcher uses a root-scoped native Mutex/Event boundary, hidden process-owned service children, and external runtime logs; normal startup never seeds business data and never terminates foreign Python, Node, or port owners.
- The launcher AI Provider Settings flow uses an atomic process-override-or-saved-config precedence, real-provider-only connection probes, masked secret input, DPAPI user-local storage, and controlled restart of only AgentForge-owned services.

## Resolved bugs

- Removed an eager capability-package resolver export that caused an import cycle through ToolGateway and ApprovalService.

## Next work

- v0.2.1 maintenance is in progress on `fix/v0.2.1-task-reconciliation`: a server-owned, fail-closed reconciliation operation identifies only proven historical Runtime/Replan failures, transitions eligible `RUNNING` Tasks to `FAILED` through the lifecycle service, appends audit evidence, and performs no execution. Task Details exposes the action only when the backend declares eligibility. Live historical repair and release remain gated on full verification.

- Run the separately approved live Phase 14 database backup and migration before using Projects with the existing runtime database.
- Production platform capabilities such as managed persistence, RBAC, and write-capable tools remain future phases.
- Final release gate: run the documented human smoke test on the running RC, including locale switching and one Repository Analyst Task. Do not create or execute that Task automatically; release/tag/version decisions require the human result.
- Final AI Analyst gate on this feature branch: start services from the feature worktree and let the HUMAN create exactly one Repository Analyst Task for Project `Phase 13 Dogfood`; verify the real actionable report, evidence citations, limitations, and release recommendation. Do not create or execute that Task automatically; release/tag/version decisions require the human result.
