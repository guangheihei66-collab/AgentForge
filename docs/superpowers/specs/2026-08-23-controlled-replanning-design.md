# Controlled Re-planning Design

## Goal

Add controlled hybrid re-planning to AgentForge so execution evidence can revise the remaining capability-first plan without granting the model execution or authorization power. Phase 13 adds `REPLAN` to the runtime decision vocabulary while preserving Plan validation, deterministic capability resolution, approval snapshots, AgentRuntime, and ToolGateway as authoritative boundaries.

## Current Limitation

`RuntimeObserver` currently converts each bounded tool result into `CONTINUE`, `COMPLETE`, or `FAIL`. Any failed tool result becomes `FAIL`, even when a bounded diagnostic capability could productively explain the failure. The runtime executes one immutable approved plan version and has no service for creating a successor plan from observations.

The repository already has the required foundations: bounded tool summaries, evidence references, immutable `PlanRecord` versions, `PlanContract`, `PlanValidator`, `CapabilityRegistry`, `CapabilityResolver`, resolved snapshots, plan-bound approvals, audit records, and the Phase 12 provider boundary. Phase 13 evolves these components rather than creating parallel observation, planning, provider, or authorization systems.

## Architectural Decision

Use controlled hybrid re-planning:

```text
Execute -> Structured Observation -> ReplanPolicy
  CONTINUE | COMPLETE | FAIL | REPLAN

REPLAN -> ReplanningService -> Replanner -> untrusted ReplanProposal
       -> PlanContract -> PlanValidator -> CapabilityResolver
       -> immutable Plan vN+1 + resolved snapshots
       -> approval decision -> AgentRuntime -> ToolGateway
```

`ReplanPolicy` is deterministic application logic. The Replanner is model-assisted and proposes only revised remaining capability steps. `ReplanningService` owns orchestration, stale checks, budgets, canonical comparison, validation, persistence, approval routing, and audit. AgentRuntime calls this focused service and does not absorb provider prompts, plan persistence, approval policy, or capability resolution.

## Authority Model

Application-owned authority decides whether re-planning is permitted, all budgets, proposal validity, concrete tool resolution, approval requirements, the authoritative plan version, and whether execution resumes. It also rejects stale, duplicate, escalating, or unverifiable proposals.

The LLM may propose a concise decision summary and revised remaining steps containing only `step_id`, `capability_id`, and bounded capability parameters. It cannot choose tools, commands, permissions, approvals, workspaces, paths outside capability parameter rules, retries, budgets, or execution behavior. It never decides whether its proposal is authorized.

ToolGateway remains the only tool execution boundary. CapabilityResolver remains the only capability-to-tool selection authority.

## Structured Observation

Evolve the existing immutable `RuntimeObservation`; do not introduce a second observation store. The Phase 13 contract contains:

- `step_id`, `execution_id`, `capability_id`, and resolved `tool_id` for traceability;
- normalized `status` and bounded `result_summary`;
- zero or more stable `evidence_refs`;
- application-owned `reason_code` from a closed enum;
- `retryable` and `replan_recommended` hints produced by deterministic adapters, not by the LLM;
- `created_at` and the runtime decision.

The result summary remains at most 2,000 characters. At most five evidence references are retained; prompt-facing evidence summaries are separately capped at 500 characters each. Raw tool output, full artifact content, secrets, and hidden reasoning are excluded. Existing `ToolExecutionRecord`, `EvidenceRecord`, and audit events remain the durable source records; the structured observation is serialized into a bounded audit event.

Initial reason codes are deliberately small: `STEP_SUCCEEDED`, `TEST_FAILED_DIAGNOSTIC_AVAILABLE`, `NON_REPLANNABLE_TOOL_FAILURE`, `POLICY_DENIED`, `INVALID_RESULT`, and `BUDGET_EXHAUSTED`. New codes require application logic and tests.

## Runtime Decisions

- `CONTINUE`: the latest step succeeded and the current approved remaining plan is still valid.
- `COMPLETE`: the goal is satisfactorily concluded and no approved remaining step is needed.
- `FAIL`: execution cannot safely or productively continue, or any required invariant cannot be proven.
- `REPLAN`: the current remaining plan is no longer sufficient, a recognized reason code permits revision, useful bounded evidence exists, and all replan/step/progress budgets allow one proposal attempt.

`REPLAN` is not a softer `FAIL`. It is allowed only when `ReplanPolicy` identifies a specific permitted diagnostic path and remaining budget. Provider errors, policy denials, malformed observations, missing evidence, authorization failures, and exhausted budgets are `FAIL`, not `REPLAN`.

## ReplanPolicy

`ReplanPolicy.evaluate()` receives current runtime state, latest structured observation, completed and attempted step summaries, current plan ID/version, replan count, total-step budget, remaining-plan fingerprint, and progress fingerprint. It returns a bounded decision plus a closed reason code and concise summary.

For the MVP, `REPLAN` is possible only when all conditions hold:

1. task and runtime are active and not cancelled;
2. observation is valid and has `TEST_FAILED_DIAGNOSTIC_AVAILABLE`;
3. at least one stable evidence reference or persisted failed execution exists;
4. current plan/version and registry fingerprints are fresh;
5. fewer than two replans have been created;
6. fewer than twelve total steps have been attempted or proposed across versions;
7. the same capability, normalized parameters, and reason have not already failed twice;
8. the progress fingerprint differs from the previous replan boundary.

Policy evaluation performs no network call. A `replan_recommended` observation hint is an input, never sufficient authority by itself.

## Replanner Contract

`ReplanContext` is an immutable bounded input containing: user goal; original and current plan identifiers; current version; concise remaining-plan summary; at most twelve completed/attempted step summaries; latest observation; at most five evidence references/summaries; allowed capability descriptions and parameter constraints; remaining step budget; and remaining replan budget.

`ReplanProposal` contains `decision_summary` (maximum 500 characters) and `revised_remaining_steps`. Each step uses the existing `CapabilityPlanStep` shape. Extra fields are forbidden. The proposal contains no lineage, tool IDs, approval fields, permission fields, workspace overrides, or executable instructions; the application adds lineage only after validation.

The Replanner is a small boundary used by `ReplanningService`. The deterministic Mock implementation returns the one approved demo proposal. Real-provider output remains untrusted.

## Provider Integration

Extend the existing `LLMProvider` protocol with a narrowly typed re-planning operation, using `LLMRequest` and `LLMResponse` transport metadata already established in Phase 12. Both Mock and OpenAI-compatible providers implement initial planning and re-planning; no second HTTP client or configuration source is introduced.

The OpenAI-compatible implementation reuses the existing timeout, three-attempt transient retry bound, redirect prohibition, 64 KiB response limit, safe error mapping, and structured JSON response mode. A selected real provider failure never falls back to Mock. Automated tests use mocked transport only.

## Prompt Boundary

Use a dedicated re-planning prompt because its authority and context differ from initial planning. It receives only the bounded `ReplanContext`, semantic capability catalog, and the strict proposal schema. The prompt states that the output revises remaining capability requirements and has no execution authority.

Serialized replan context is capped at 8 KiB and the complete generated prompt at 12 KiB. Oversize context fails before any provider call. It excludes repository dumps, audit history, raw tool output, source code, credentials, environment values, Authorization headers, ToolGateway internals, concrete tool catalogs, and hidden reasoning.

## Plan Versioning

Plans are immutable. A successful replan creates the next task-scoped `PlanRecord` version; Plan v1 is never overwritten or deleted. Provider output is first validated as a normal schema-v2 capability plan. The application then enriches the persisted `plan_json` with server-owned `replan_lineage`:

- previous plan ID and version;
- triggering execution/step and observation event ID;
- closed reason code and concise reason summary;
- canonical remaining-plan fingerprint and progress fingerprint;
- replan ordinal and creation timestamp.

Plan v2 contains only the revised remaining steps, not already completed v1 steps. Execution and observation audit records retain the completed history. The service verifies `next_version()` against the current highest version in the same transaction and rejects stale requests or competing successors. Plan selection always uses an explicitly supplied task-bound ID/version; “latest” is discovery information, not execution authority.

## Approval Semantics

Choose policy C: safe-read-only revisions may eventually continue automatically only when they are provably within an unchanged, previously approved authority envelope; any capability, permission, parameter, resolved snapshot, or execution-risk expansion requires approval.

The current approval model binds one plan ID/version and exact resolved snapshots. It has no cross-version authority envelope. Therefore the Phase 13 MVP implements policy C conservatively: every valid replan version requires a new human approval. No Plan v1 approval is reused for Plan v2, including safe-read-only revisions. This is preferable to inventing an implicit shortcut. A future explicit envelope may enable the safe-read branch of policy C without changing its principle.

## Resolved Snapshot Interaction

Every proposed step passes CapabilityRegistry, parameter validation, permission compatibility, CapabilityResolver, and registry fingerprint generation. Plan v2 receives new snapshots bound to its own task, plan ID, version, step IDs, capabilities, normalized parameters, resolved tools, actions, and fingerprints.

Plan v1 snapshots cannot authorize Plan v2. ApprovalService creates a fresh snapshot document from Plan v2 and AgentRuntime verifies the exact snapshot and current registry semantics before each execution. Stale fingerprints, changed candidates, zero candidates, multiple candidates, and mismatched approval snapshots fail closed.

## Validation Pipeline

The authoritative pipeline is:

```text
provider response size guard -> JSON extraction -> ReplanProposal schema
-> PlanContract -> PlanValidator -> Replan budget and lineage checks
-> deterministic canonicalization -> duplicate/no-progress checks
-> CapabilityRegistry -> CapabilityResolver -> resolved snapshots
-> approval requirement -> AgentRuntime -> ToolGateway
```

Validation forbids unknown capabilities, invalid or unbounded parameters, duplicate step IDs, more steps than remaining budget, legacy concrete-tool fields, command fields, workspace overrides, permission or approval fields, unexpected dependencies, and extra top-level fields. HTTP 200 and schema-valid JSON alone never authorize persistence or execution.

## Loop Safety

MVP limits are:

- maximum replans per task: 2;
- maximum total attempted plus newly proposed steps across all versions: 12;
- maximum steps in one replan proposal: the smaller of 10 and remaining total-step budget;
- provider attempts per replan call: existing maximum of 3 total attempts;
- one provider call per accepted `REPLAN` decision; no model self-repair loop;
- maximum two failures of the same canonical capability request for the same reason;
- one pending replan approval at a time.

Replan count is based on persisted successor plans, not transient calls. Failed provider calls do not loop automatically; an operator must initiate a new task/run after terminal failure. Cancellation is checked before provider invocation, before persistence, before approval creation, and before resume.

## Duplicate and No-Progress Detection

Canonicalize each remaining plan as ordered capability IDs plus resolver-normalized, key-sorted parameters; exclude generated step IDs and prose summaries. Serialize with stable JSON separators and hash with SHA-256.

Reject a proposal when its fingerprint equals the current failed/remaining-plan fingerprint or any prior replan fingerprint for the task. Also compute a progress fingerprint from completed capability requests, latest reason code, relevant evidence IDs/content hashes, and current remaining-plan fingerprint. Reject when a new replan boundary repeats the previous progress fingerprint, or when the same canonical capability request has already failed twice for the same reason. Phase 13 uses no semantic embeddings or fuzzy similarity.

## Fail-Closed Behavior

Invalid proposal, unknown capability, invalid parameters, ambiguous or missing tool candidate, stale plan/version, stale registry fingerprint, permission escalation, missing approval, exhausted budget, duplicate plan, no progress, provider timeout/auth/network/malformed output, missing evidence, malformed observation, and cancellation all prevent execution.

If the old remaining plan was declared insufficient, AgentForge never silently resumes it. A selected real provider never falls back to Mock. Validation or authorization failures create bounded audit events and move the task to `FAILED` unless cancellation already made it `CANCELLED`. No raw upstream response or secret is stored.

## Runtime Integration

Add `REPLAN` to `RuntimeDecision`, not to ToolGateway. `RuntimeObserver` constructs the structured observation; `ReplanPolicy` makes the deterministic decision. On `REPLAN`, AgentRuntime stops iterating the old plan and calls `ReplanningService` with identifiers and bounded observation data. The service returns either a successor awaiting approval, a successor ready for an explicitly authorized resume, or a safe terminal failure.

Phase 13 adds a focused `backend/app/agents/replanning/` package with at most `models.py`, `policy.py`, `prompts.py`, and `service.py`. Provider protocol changes remain under the existing provider package. Runtime receives the orchestration service by dependency injection. Prompting, validation, versioning, resolution, and approval calculations do not move into `runtime.py`.

## Persistence Impact

No database schema change is required. Reuse:

- immutable `PlanRecord` rows and `version` for Plan v1 -> v2;
- server-owned `replan_lineage` inside existing `plan_json`;
- existing `ApprovalRecord` and `resolved_snapshot` for each new version;
- existing execution/evidence records;
- bounded `AuditEventRecord.payload_summary` for observations and decisions.

No provider configuration, credential, prompt, raw response, or Chain of Thought is persisted. Implementation must query the task’s maximum plan version and reject stale concurrent creation. The live SQLite database requires no migration.

## Recovery Semantics

No new persistent `REPLANNING` task status is added. Re-planning is a short internal runtime substate represented by audit events. Replan requiring approval uses the existing `WAITING_APPROVAL` status; the state machine minimally permits `RUNNING -> WAITING_APPROVAL -> RUNNING`. ApprovalService is extended to accept a validated successor from `RUNNING` and still binds approval to that exact version.

Recovery uses explicit records:

- `REPLAN_REQUESTED` without a later valid successor is incomplete and fails closed on restart; the old plan does not resume automatically.
- a validated Plan v2 with pending approval is authoritative and remains `WAITING_APPROVAL`.
- an approved Plan v2 is authoritative and may resume only after the normal snapshot and registry checks.
- cancellation at any point wins and prevents persistence, approval, or resume.
- multiple valid successors for the same previous version are an integrity error and fail closed.

This provides unambiguous restart behavior without adding a distributed workflow engine or durable provider-call state.

## Audit and Observability

Use only events needed to reconstruct behavior: `RUNTIME_OBSERVATION`, `REPLAN_REQUESTED`, `REPLAN_PROPOSED`, `REPLAN_REJECTED`, `PLAN_VERSION_CREATED`, `REPLAN_APPROVAL_REQUIRED`, and `REPLAN_RESUMED`. Existing runtime decision and approval events remain authoritative, so separate “validated” events are unnecessary when `PLAN_VERSION_CREATED` records validation success.

Safe payloads contain IDs/versions, triggering step and reason code, proposed capability IDs, canonical fingerprints, validation outcome, approval requirement, provider/model, duration, attempts, and safe token counts. Replan audit payloads are capped at 8 KiB. They never include credentials, full prompts, raw responses, raw tool output, artifact bodies, or hidden reasoning.

## Deterministic Demo

Goal: “Check whether version 2.0 is ready for release.”

Plan v1 runs `repository_state` then `test_verification`. The test execution returns a deterministic failed result with evidence. The observation adapter assigns `TEST_FAILED_DIAGNOSTIC_AVAILABLE`; ReplanPolicy returns `REPLAN`. Mock Replanner proposes one `project_metadata` step. The application validates and resolves Plan v2, records lineage to v1 and the triggering observation, and requests a new approval. After approval, Runtime executes the exact v2 snapshot. The metadata evidence identifies a version/configuration problem and the task concludes `NOT READY` with both test-failure and configuration evidence.

The scenario is reproducible without network access. A real provider may later exercise the same contracts manually.

## Low-Overhead Test Strategy

Use one main feature file: `backend/tests/test_phase_13_controlled_replanning.py`. Add tests incrementally for the observation contract; all four runtime decisions; policy conditions; replan and total-step budgets; canonical duplicate/no-progress detection; deterministic Mock Replanner; mocked real-provider contract; v1-to-v2 lineage; approval invalidation and conservative policy-C behavior; resolver and stale-fingerprint enforcement; Runtime `REPLAN`; provider/validation failures; cancellation/recovery; and the deterministic demo.

Normal tests make no real network calls and use the existing test database isolation. Run the Phase 13 file during development and full regression only near completion. No separate policy, provider, runtime, approval, or versioning test packages are planned.

## Resource Bounds

- 2 replans per task and 12 total attempted/proposed steps;
- maximum 10 steps per proposal, further limited by remaining budget;
- 3 provider attempts per call under the existing transient retry policy;
- 12 completed/attempted step summaries, each at most 500 characters;
- latest observation summary at most 2,000 characters;
- 5 evidence references/summaries, each summary at most 500 characters;
- replan context at most 8 KiB and complete prompt at most 12 KiB;
- proposal summary at most 500 characters;
- replan audit payload at most 8 KiB;
- no audit-history replay or full artifact/tool-output accumulation.

## Security Properties

- LLM output remains untrusted planning data.
- Concrete tools are selected only by CapabilityResolver.
- Every execution uses an exact resolved snapshot checked by ApprovalService, Runtime, and ToolGateway.
- Plan v1 approval never implicitly authorizes Plan v2.
- Real-provider errors never switch to Mock.
- Base URL, credentials, retries, and transport bounds remain process-owned.
- Duplicate, no-progress, and budget guards are deterministic and application-owned.
- Secrets, raw outputs, and Chain of Thought are neither prompted unnecessarily nor persisted.
- Cancellation and stale state fail closed at every side-effect boundary.

## Expected Files Affected

Future implementation is expected to affect the existing runtime state/observer/runtime modules, provider protocol and implementations, planning/approval services, task transition rules, package composition, documentation, and the single Phase 13 feature test. It may add only the focused `backend/app/agents/replanning/` package described above. No migration, dependency, ToolGateway, frontend, or database schema file is expected for the MVP.

## Risks and Mitigations

- Replan loops: fixed budgets, canonical fingerprints, repeated-failure guards, and no self-repair loop.
- Approval bypass: new version/snapshot always requires fresh MVP approval.
- Ambiguous recovery: immutable lineage, explicit audit boundaries, highest-version stale checks, and fail-closed restart reconciliation.
- Context growth: strict summary/count/byte limits and stable evidence references.
- Model authority creep: capability-only schema and application-owned policy/resolution/approval.
- Concurrent successors: transactional next-version check and rejection of more than one successor for the same parent.
- Over-abstraction: reuse Phase 12 provider contracts and existing persistence; one small replanning package only.

## Out of Scope

Project Workspace, RBAC/login, Multi-Agent, RAG or long-term memory, MCP, PostgreSQL, Redis, queues/workers, distributed execution, arbitrary shell, permission escalation, generic workflow languages, self-modifying prompts, recursive agents, evaluation platforms, real API-key setup, and automatic safe-read approval envelopes are excluded.

## Future Evolution

A future version may add an explicit signed authority envelope that safely enables policy C auto-continuation for unchanged safe-read scope, durable distributed orchestration, richer reason-code adapters, and production concurrency controls. These changes require separate design and must not weaken the Phase 13 exact-version approval and ToolGateway boundaries.
