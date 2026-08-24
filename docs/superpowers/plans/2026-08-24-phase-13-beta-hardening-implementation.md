# Phase 13 Beta Hardening & Operability Implementation Plan

Baseline: `main` at `440303673bc954df0b593254a3801fed1ab092a7`
Published Beta: `v0.1.0-beta.1` at `51fe068fd7ed48dee737afb8c8ecd7a52dcd467f`

## Task 1 — Version/build identity foundation

Add a dependency-neutral backend identity service under `backend/app/identity/`, deriving the product version from the existing frontend package metadata without duplicating a literal release version. Resolve the Git revision from repository metadata only, returning `UNKNOWN` when unavailable; never accept shell input from callers.

Files: `backend/app/identity/`, `backend/app/schemas/identity.py`, `backend/app/main.py`, `backend/tests/test_identity.py`, and the existing frontend API/type files only where the contract requires it.

Tests: version, revision available, revision unavailable, and source archive/no repository metadata.

## Task 2 — Deterministic health model

Add a pure health domain module under `backend/app/diagnostics/health.py` with `HEALTHY`, `DEGRADED`, `UNHEALTHY`, and `UNKNOWN`. Encode the exact overall rules in unit tests. Passive health must not call the LLM; the existing explicit `POST /llm/provider/test` remains the only active Provider probe.

Files: `backend/app/diagnostics/health.py`, `backend/tests/test_health_model.py`, and `backend/app/api/routes/health.py`.

## Task 3 — Read-only backend diagnostics service/API

Add bounded DTOs and a diagnostics service that uses existing ORM records (`TaskRecord`, `PlanRecord`, `ApprovalRecord`, `ToolExecutionRecord`, `EvidenceRecord`, `ObservationRecord`, and `AuditEventRecord`) through bounded queries. Expose only read-only `GET` identity, health, and diagnostics routes following existing FastAPI conventions. Limit recent errors to 20 and omit full Audit, Evidence, Tool output, database, and workspace payloads.

Files: `backend/app/diagnostics/`, `backend/app/schemas/diagnostics.py`, `backend/app/api/routes/diagnostics.py`, `backend/app/main.py`, and `backend/tests/test_diagnostics_api.py`.

Tests: empty DB, recent task, SUCCESS/FAILED/REJECTED counts, bounded errors, and no mutation side effects.

## Task 4 — Provider diagnostic mapping and redaction

Map current `ProviderErrorCategory` and `ConnectionStateStore` state to bounded diagnostic values: `NOT_CONFIGURED`, `AUTH_FAILURE`, `CONNECTION_FAILURE`, `INVALID_RESPONSE`, `SUCCESS`, or `UNKNOWN`. Return only provider metadata, model, structured output mode, and a credential boolean. Add sentinel-secret serialization tests; do not add a passive completion call or broaden the Provider protocol.

Files: `backend/app/diagnostics/provider.py`, existing provider schemas/routes only as needed, and `backend/tests/test_diagnostics_provider.py`.

## Task 5 — Startup/launcher diagnostics

Extend the existing `launcher/start_agentforge.ps1` with bounded readiness/status classification using the existing loopback health endpoints and explicit Provider test endpoint. Preserve `Start-AgentForge.bat` and `Stop-AgentForge.bat`, fresh-shell behavior, timeout/retry bounds, and secret-free output. Add a testable helper script or functions rather than an installer or release system.

Files: `launcher/start_agentforge.ps1`, `launcher/README.md`, and `backend/tests/test_launcher_diagnostics.py` or a repository-supported launcher test fixture.

Tests: healthy, backend unavailable, DB unhealthy, Provider unconfigured/invalid response, timeout, and sentinel redaction.

## Task 6 — Minimal frontend diagnostics/status UI

Extend the existing `Shell`/`App` page model with the least invasive status page. Add typed diagnostics API calls in `frontend/src/api/client.ts`, types in `frontend/src/types/index.ts`, and a focused `frontend/src/pages/Diagnostics.tsx` plus styles. Render loading, API failure, all four health states, optional revision, Provider model/status, and configured/not configured without exposing raw payloads or credentials.

Tests: extend `frontend/src/App.test.tsx` or add focused page tests for loading, healthy, degraded, unhealthy, unknown, API failure, and missing revision. Run the production build.

## Task 7 — Support bundle decision

After the diagnostics contract is stable, evaluate whether its bounded JSON already supplies safe support data. Default decision is to defer duplicate file export because the contract contains identity, health, redacted Provider metadata, bounded errors, and governed execution summary. Implement no ZIP or file export unless a verified gap remains and the smallest bounded JSON artifact is justified and tested.

## Task 8 — Real dogfood and issue triage

Use the supported Project, planning, approval, execution, ToolGateway, Evidence, Observation, and report flows for one normal repository-oriented Task and one safe non-success path. Do not manually mutate SQLite or bypass authority. Record P0–P3 findings with root cause, regression evidence, and focused fix commits; use the existing regression suite for controlled replan evidence if no safe natural replan is available.

## Task 9 — Whole-branch regression and security verification

Run backend and frontend full suites, frontend production build, DB isolation, launcher smoke, diagnostics API, provider explicit connection test, and secret scans. Recheck metadata traversal, workspace containment, capability authorization, Approval Snapshot drift, successor-plan approval, truthful FAILED/REJECTED reporting, and ToolGateway boundary. Request code review against this plan and the approved design before final verification.

## Commit discipline

Use focused commits after each RED/GREEN task. Do not change version metadata, create a tag, push, merge to `main`, create a release, or remove this feature worktree in this implementation run.
