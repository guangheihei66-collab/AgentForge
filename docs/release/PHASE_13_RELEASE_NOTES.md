# AgentForge v0.1.0-beta.2

Phase 13 Beta Hardening & Operability prerelease.

## Highlights

- Read-only runtime diagnostics with deterministic `HEALTHY`, `DEGRADED`, `UNHEALTHY`, and `UNKNOWN` health states.
- Runtime version and Git revision identity.
- Launcher startup diagnostics and a minimal frontend Diagnostics status view.
- Bounded and redacted Provider diagnostics.
- Bounded ToolExecution diagnostic aggregation.
- Verified OpenAI-compatible DeepSeek Provider startup and connection behavior.
- Completed production-faithful normal dogfood.
- Completed real semantic failure dogfood: `test_verification` → `unit` → pytest exit 1 → persisted `FAILED` ToolExecution.
- Verified truthful Observation, Evidence, Report, and Diagnostics handling.
- Preserved Approval and ToolGateway security boundaries.
- Preserved test/runtime database isolation.

## Verification

- Backend: 253 passed, 1 warning
- Frontend: 15 passed
- Diagnostics frontend tests: 6 passed
- Frontend production build: PASS
- Launcher smoke: PASS
- DB isolation: PASS
- Provider connection: PASS
- Diagnostics: PASS
- Startup diagnostics: PASS
- Secret scan: PASS
- Security regression: PASS
- P0/P1/P2/P3: 0

## Scope

This remains a private Beta prerelease. It does not add an installer, updater, cloud deployment, arbitrary shell execution, a new Runtime authority model, or expanded autonomous permissions.
