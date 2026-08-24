# AgentForge Phase 13 Beta Hardening & Operability Design

Status:
Proposed

Baseline release:
v0.1.0-beta.1

Baseline commit:
51fe068fd7ed48dee737afb8c8ecd7a52dcd467f

## 1. Purpose

Phase 13 is not a feature-expansion phase. It hardens the released Beta through diagnostics, observability, reproducible operation, real-world dogfood, and regression-driven fixes.

The primary success criterion is that a Beta user or operator can determine what version is running, whether AgentForge is healthy, why startup failed, why the Provider failed, why a Task failed, and what recent governed execution occurred without forensic investigation across unrelated logs.

Phase 13 is architectural in scope because it crosses backend, frontend, launcher, diagnostics, runtime observability, and release identity. It does not redesign the governed Agent architecture from Phase 12.

## 2. Architecture freeze

The following components are frozen by default:

- Planner
- Plan Validation
- Capability Resolver
- Human Approval
- Approval Snapshot
- Project Authority
- AgentRuntime
- ToolGateway
- Observation
- Evidence
- Audit
- Controlled Replan

Any change to a frozen component requires all of the following:

1. A concrete defect is reproduced.
2. Root-cause analysis proves the component is responsible.
3. A regression test exists and fails before the fix.
4. A minimal fix preserves the established security invariants.

Opportunistic refactoring is prohibited during Phase 13.

## 3. Scope and workstreams

### A. Runtime diagnostics

Provide a safe, bounded, read-only diagnostics surface containing:

- AgentForge version and Git/build revision where available
- Backend and frontend health
- Database reachability
- Provider type, model, structured output mode, and credential-configured boolean
- Recent Task state and Plan version
- Approval state where applicable
- ToolExecution counts for `SUCCESS`, `FAILED`, and `REJECTED`
- Evidence, Observation, and controlled Replan counts
- At most 20 recent bounded errors

Diagnostics are operational summaries, not unrestricted log export. They must never expose API keys, Authorization headers, raw secrets, full environment dumps, chain-of-thought, unbounded Provider bodies, runtime database contents, or private file contents. Sensitive values are redacted or represented as booleans.

### B. Startup diagnostics

The supported `Start-AgentForge.bat` and `Stop-AgentForge.bat` entry points remain authoritative. Startup output should make each readiness boundary visible:

```text
AgentForge starting...
Backend ........ OK
Frontend ....... OK
Database ....... OK
Provider ....... OK

AgentForge Ready
http://localhost:5173
```

Failures must identify the failed component and deterministic classification without printing secrets. For example, a Provider failure reports `Provider ........ FAILED`, its classification such as `INVALID_RESPONSE`, the Provider type, model, and structured output mode, but no credential value.

Phase 13 does not introduce an installer.

### C. Version and build identity

Expose one canonical product identity to both backend and frontend:

- product: `AgentForge`
- version: `0.1.0-beta.1` or a subsequent release version
- build/revision: Git commit when reliably available
- environment: `development` or `beta` where already modeled

The existing canonical package version in `frontend/package.json` and `frontend/package-lock.json` is the starting point. Before implementation, determine whether it can be consumed without duplication or whether a small dependency-neutral metadata source is justified. The decision must be evidence-based; two independent version sources must not be allowed to drift.

## 4. Diagnostics boundary

Diagnostics are strictly read-only. They must not approve Tasks, execute Plans, run arbitrary tools, mutate Tasks or Project authority, mutate Provider settings, bypass ToolGateway, execute user-supplied shell commands, or expose workspace files.

Persisted data is queried through bounded projections. Recent-history fields have explicit limits; recent errors default to no more than 20 records, and complete Audit history is never returned by default. The frontend consumes a backend diagnostics contract and never accesses the database directly.

## 5. Deterministic health model

Health classification is deterministic and never delegated to an LLM. The vocabulary is:

- `HEALTHY`: required runtime state is reachable; backend and database are available; Provider is configured and its connection check succeeds.
- `DEGRADED`: the backend and database are available, but a non-essential or configured external dependency such as the Provider is unavailable.
- `UNHEALTHY`: the backend cannot initialize or reach required runtime state, including an unavailable database.
- `UNKNOWN`: evidence is insufficient to classify the component safely.

The diagnostics contract reports component states for backend, database, Provider, and runtime, together with an overall state derived by the same fixed rules. No state may be inferred from natural-language Provider output.

## 6. Provider diagnostics

The supported Provider configuration remains:

- provider: `openai-compatible`
- model: `deepseek-v4-flash`
- structured output mode: `json_object`
- credential configured: `true` or `false`

Credential values are never returned. Where evidence permits, connection failures map to `NOT_CONFIGURED`, `AUTH_FAILURE`, `CONNECTION_FAILURE`, `INVALID_RESPONSE`, or `SUCCESS`. Phase 13 does not broaden the Provider protocol or add Provider families unless a proven Beta defect requires it.

## 7. Task diagnostics

Task diagnostics preserve Phase 12 semantics:

- Task state
- Plan version
- Approval state: `PENDING`, `APPROVED`, or `REJECTED` where applicable
- ToolExecution counts separated into `SUCCESS`, `FAILED`, and `REJECTED`
- Controlled Replan count
- Evidence count
- Observation count

A rejected execution must not be reinterpreted as failed, and a semantic test failure must not be reported as success. Existing Phase 12 fixes remain authoritative.

## 8. Bounded support bundle

An optional support bundle may contain a deterministic diagnostic JSON document with version/build identity, health status, bounded recent errors, a bounded recent Task execution summary, and redacted configuration metadata.

By default it contains none of the following: SQLite databases, API credentials, `.env.local`, Authorization headers, full filesystem inventories, source files, arbitrary logs, or user file contents. If file generation is approved during implementation, the schema, size limits, and redaction rules must be defined before implementation and tested at the service boundary. This design does not implement bundle generation.

## 9. Minimal frontend UX

Add only a small system/status or settings/about diagnostics surface. It must show AgentForge version, overall system health, Backend, Database, Provider, Provider model, and connection state. Detailed bounded diagnostics may be opened on demand without overwhelming normal users.

There is no dashboard rewrite and no broad frontend redesign.

## 10. Real Beta dogfood

Real dogfood is a required Phase 13 activity. AgentForge must be used for representative repository-oriented work through the complete governed lifecycle:

`User Goal -> Planner -> Plan Validation -> Capability Resolution -> Human Approval -> Runtime -> ToolGateway -> Observation -> Evidence -> Report`

At least one exercise must naturally test failure handling. Production data must not be intentionally corrupted, and SQLite must not be manually modified. Each observation is classified as P0, P1, P2, or P3 and retains enough evidence to reproduce the issue without exposing secrets.

## 11. Issue and regression discipline

- **P0:** security-boundary failure, authorization bypass, data corruption or loss, or secret exposure.
- **P1:** the core governed workflow cannot complete under supported conditions.
- **P2:** a functional defect with a safe workaround or bounded impact.
- **P3:** UX friction, diagnostics quality, documentation, or convenience.

The bug workflow is:

`REPRODUCE -> SYSTEMATIC DEBUGGING -> ROOT CAUSE -> REGRESSION TEST -> RED -> MINIMAL FIX -> GREEN -> FULL VERIFICATION`

No speculative fixes are accepted. Frozen architecture changes require the evidence gate in Section 2.

## 12. Scope boundaries

The following additions are explicitly allowed because they improve Beta operability without expanding governed Agent autonomy:

- Read-only diagnostics API
- Deterministic health/status API
- Version/build identity API
- Minimal diagnostics/status frontend UI
- Launcher startup diagnostics
- Bounded support-bundle functionality if justified

Phase 13 excludes Phase 12 governed Runtime redesign, new Agent autonomy or capability features, new general-purpose product APIs unrelated to diagnostics or operability, multi-Agent orchestration, long-term Agent memory, background autonomous Agents, arbitrary shell execution, a plugin marketplace, cloud/SaaS architecture, billing, multi-user RBAC, mobile clients, an installer, an automatic updater, an automatic release pipeline, major frontend redesign, and new Provider families unless required by a proven Beta defect. Version bumps and release publication are also out of scope during initial Phase 13 implementation.

## 13. Security invariants

Phase 12 invariants remain unchanged:

- The LLM never decides permissions.
- Capability Resolver remains deterministic.
- Human Approval remains a hard gate.
- Approval Snapshot binds execution authority.
- ToolGateway remains the final execution boundary.
- Workspace containment remains enforced.
- A successor Plan requires fresh approval.
- Diagnostics cannot become a side-channel around these controls.
- Chain-of-thought is neither persisted nor exposed.
- Secrets are never exposed.

## 14. Data and API design principles

Use a dependency-neutral diagnostics domain/service where practical, bounded DTOs, explicit enums, read-only queries, redaction at the service boundary, and deterministic state classification. Do not expose SQLAlchemy ORM objects directly as API schemas. Do not provide direct frontend database access.

## 15. Test strategy

### Backend unit

Test health classification, redaction, version identity, bounded recent-record selection, and Provider diagnostic mapping.

### Backend API

Test the diagnostics endpoint contract, absence of secret leakage, `SUCCESS`/`FAILED`/`REJECTED` counts, empty-database behavior, and Provider-unavailable behavior.

### Launcher

Test startup health output, fresh-shell startup, non-secret configuration loading, and failure classification while preserving the supported batch entry points.

### Frontend

Test version rendering, health rendering, degraded state, and Provider status.

### Regression and dogfood

Run the full existing backend suite, full existing frontend suite, frontend production build, and DB isolation checks. Complete a production-faithful governed Task lifecycle covering approval, execution, Evidence, and controlled Replan behavior.

## 16. Implementation order

1. **Phase 13.1 — Version/build identity foundation:** settle the canonical source first so every later diagnostic and UI contract uses the same identity.
2. **Phase 13.2 — Backend diagnostics domain/API:** establish bounded schemas, deterministic health mapping, redaction, and read-only queries before adding consumers.
3. **Phase 13.3 — Startup diagnostics:** consume the backend contracts from the supported launcher and make startup failures actionable.
4. **Phase 13.4 — Frontend diagnostics/status UI:** consume the stable backend contract with minimal version and health visibility.
5. **Phase 13.5 — Support bundle, if still justified:** add it only after the diagnostic schema and redaction behavior are stable and useful without it has been demonstrated.
6. **Phase 13.6 — Real dogfood and Beta issue triage:** exercise the complete lifecycle, classify evidence, and apply only regression-backed fixes.

## 17. Branch and worktree strategy

The published Beta tag `v0.1.0-beta.1` points to `51fe068fd7ed48dee737afb8c8ecd7a52dcd467f` and remains immutable. The current approved design HEAD on `main` is `6fac7809121eeb2ab5dffe87c6b3cc16601c7618`. Phase 13 implementation must branch from `main` at the latest approved design HEAD, not directly from the old Beta tag, so the implementation branch includes this design specification.

Recommended development branch:

`feature/phase-13-beta-hardening`

Recommended isolated worktree:

`D:\AgentProjects\AgentForge\.worktrees\phase-13-beta-hardening`

At implementation time, use `superpowers:using-git-worktrees`, confirm `main` is clean, confirm tag `v0.1.0-beta.1`, verify `.worktrees` is ignored, create the branch from current `main`, and run clean baseline tests. Do not create the branch or worktree in this design run. Do not move or rewrite the published tag. Do not push this design revision unless HUMAN later authorizes it.

### Implementation gate

Phase 13 implementation may begin only after:

1. This revised design is committed.
2. The working tree is clean.
3. HUMAN approves the revised design.
4. Implementation starts in an isolated worktree.
5. Clean baseline regressions pass.

## 18. Phase 13 exit criteria

The phase may be evaluated only when all of the following pass:

- Runtime diagnostics
- Startup diagnostics
- Version visibility
- Secret redaction
- Backend regression
- Frontend regression
- Frontend build
- DB isolation
- Provider
- Real dogfood
- Approval lifecycle
- Evidence quality
- Controlled Replan
- Repeatable release process

P0 and P1 must be zero. Known P2 and P3 findings must be documented with bounded impact and disposition. A separate decision then determines whether the next release is `v0.1.0-beta.2` or a `v0.1.0` release-candidate evaluation.

## 19. Non-goals for success

Phase 13 success does not require zero P3 findings, an installer, stable `v0.1.0`, a public repository, cloud hosting, or feature expansion. The goal is Beta hardening, not product completion.

## Design self-review

- Placeholder scan: no unresolved or deferred requirement placeholders.
- Architecture scan: Human Approval, Approval Snapshot, Project authority, AgentRuntime, ToolGateway, Evidence, Audit, and Controlled Replan remain frozen by default.
- Boundary scan: diagnostics are read-only, bounded, deterministic, and cannot approve, execute, mutate, bypass ToolGateway, or expose workspace data.
- Security scan: support bundles and diagnostics exclude credentials, `.env.local`, Authorization headers, databases, source files, arbitrary logs, private files, and chain-of-thought.
- Scope scan: the design is limited to Beta hardening, operability, dogfood, and regression discipline.
