# Capability-Based Tool Selection Design

## Goal

Phase 11.2 introduces a deterministic, application-owned capability resolver.
Planner output describes the semantic capability required by each step. The
application resolves that capability to exactly one registered and validated
concrete tool before human approval. AgentRuntime then consumes the approved
resolved snapshot and continues to use the existing ToolGateway as the final
execution boundary.

The flow is:

```text
User Goal
  -> Planner
  -> Capability Requirement
  -> Plan Validator
  -> Capability Resolver
  -> Resolved Execution Snapshot
  -> Approval
  -> AgentRuntime
  -> RuntimeExecutor adapter
  -> ToolGateway
  -> Permission / Workspace / Execution
  -> Evidence + Audit
  -> Observation
```

This is a design specification only. It does not authorize production code,
database migrations, dependency changes, or runtime-data changes.

## Current Architecture

The current MVP has:

- `PlanStep` fields `step_id`, concrete `tool`, `action`, `risk_level`, and
  `permission_level`.
- `PlanValidator` validating the concrete tool against a locally constructed
  `ToolRegistry` and a hard-coded action map.
- `ToolDefinition` containing identity, risk, permission, allowed actions,
  executor, and enabled state.
- `ToolRegistry` containing explicitly registered tools: `git_read`,
  `file_read`, and `test_run`.
- `RuntimeExecutor` translating a validated concrete plan step into a
  `ToolExecutionRequest`.
- `ToolGateway` performing the final registry, action, permission, approval,
  workspace, execution, evidence, and audit checks.
- `PlanRecord.plan_json` storing the validated plan and `ApprovalRecord`
  binding task ID, plan ID, and plan version.

## Current Limitation

Concrete tool identity is currently part of planner output and plan execution.
That makes the model-shaped plan appear to select an executor. It also leaves
approval unable to show or bind normalized execution parameters and registry
semantics. A future runtime must not accept a new plan step containing only
`tool = "test_run"` and treat that as resolved authority.

The existing ToolGateway is the correct execution boundary and must remain so.
Phase 11.2 adds a resolution and binding layer before it; it does not create a
second executor or allow RuntimeExecutor to resolve tools independently.

## Architectural Decision

Use Option A: a deterministic capability resolver owned by the application.

The planner emits semantic capability requirements. `CapabilityRegistry` owns
semantic capability definitions and is independent from `ToolRegistry`, which
owns concrete executable tools. `CapabilityResolver` is the only component
allowed to convert a capability into a concrete tool for the new execution
path.

There is no LLM ranking, priority field, implicit tie-break, autonomous tool
discovery, or direct model-selected execution. The resolver fails closed unless
exactly one candidate is valid.

## Capability Model

The minimum capability requirement is:

```text
CapabilityRequirement
  capability_id
  requested_parameters
```

The minimum capability definition is:

```text
CapabilityDefinition
  id
  description
  risk_level
  required_permission
  candidate_tool_ids
  parameter_schema
```

The initial capability set is intentionally small:

| Capability | Concrete mapping | Parameters |
| --- | --- | --- |
| `repository_state` | `git_read` | no arbitrary parameters; operation is defined by the capability contract |
| `project_metadata` | `file_read` | bounded metadata file selection, validated against the file tool contract |
| `test_verification` | `test_run` | `profile`, allowed values `unit` or `smoke` |

The capability contract must not accept shell commands, executable paths,
arbitrary action names, or arbitrary subprocess parameters.

## CapabilityRegistry

`CapabilityRegistry` is application-owned and independent of `ToolRegistry`.
It registers immutable `CapabilityDefinition` values and rejects duplicate
capability IDs. It does not execute tools and does not decide whether a tool
is currently registered or enabled.

The registry supplies the semantic requirement and candidate tool IDs to the
resolver. Concrete tool metadata remains in `ToolRegistry`.

## CapabilityResolver

`CapabilityResolver` receives a capability requirement, the capability
registry, the concrete tool registry, and the requested permission context. It
returns a normalized `ResolvedExecutionSnapshot` only after all checks pass.

The resolver must be the sole resolver for the new runtime path. Planner,
RuntimeExecutor, AgentRuntime, and the model provider must not independently
choose or substitute a concrete tool.

## Resolution Algorithm

For each capability requirement:

1. Look up the capability ID. Unknown IDs fail closed.
2. Validate and normalize parameters against the capability parameter schema.
3. Enumerate only the explicitly listed candidate tool IDs.
4. Reject candidates that are missing, disabled, unavailable, or not
   registered in `ToolRegistry`.
5. Reject candidates whose permission level is incompatible with the
   capability and request.
6. Reject candidates that do not expose the required validated action and
   parameter contract.
7. Compute the registry fingerprint from execution/security-relevant
   semantics.
8. Resolve only when exactly one candidate remains.

Candidate cardinality is strict:

```text
0 valid candidates  -> FAIL CLOSED
1 valid candidate   -> resolve
>1 valid candidates -> FAIL CLOSED
```

There is no priority, first-match behavior, default tool, model tie-break, or
fallback to the legacy concrete-tool field.

## Resolved Execution Snapshot

The resolver returns an immutable structured value, not a second task or
execution model:

```text
ResolvedExecutionSnapshot
  task_id
  plan_id
  plan_version
  step_id
  capability_id
  resolved_tool_id
  normalized_parameters
  registry_fingerprint
```

The snapshot is created before approval and is the exact execution intent shown
to the human. Runtime receives the approved snapshot, verifies its binding,
and passes its resolved tool/action data through the existing adapter and
ToolGateway. Runtime must reject unresolved requirements, missing snapshots,
or modified parameters.

The snapshot is immutable by policy. A changed plan version requires a new
resolution and new approval.

## Plan Schema Compatibility Strategy

Use explicit schema versioning plus a deliberately limited legacy parser.

- Introduce a new capability-first plan schema version for Phase 11.2. New
  steps contain a `capability` requirement and do not accept concrete `tool`
  selection as execution authority.
- Keep a legacy parser for existing persisted MVP plans so historical data can
  be displayed and audited.
- Mark legacy plans as legacy/unresolved for the new runtime path. They may not
  be approved or executed by the Phase 11.2 runtime until re-planned into the
  capability schema and resolved.
- Migrate deterministic fixtures and planner tests to the capability schema
  when implementation begins. Do not silently transform a legacy concrete
  tool into an approved capability snapshot.

This removes the unsafe bypass: a new runtime request containing
`tool = "test_run"` alone is invalid because it has no capability resolution,
normalized snapshot, or resolver-produced fingerprint.

## Approval Binding

Approval binds the existing identifiers plus the exact resolved execution
semantics:

```text
Task ID
+ Plan ID
+ Plan Version
+ Capability ID
+ Resolved Concrete Tool ID
+ Normalized Parameters
+ Registry Fingerprint
```

The approval UI and API must expose the resolved capability, concrete tool, and
normalized parameters so the human can approve what will actually execute.

At execution time, all values must match the approved snapshot. A new plan
version, changed capability, changed tool, changed parameters, or changed
fingerprint invalidates the approval.

## Registry Fingerprint

The fingerprint is a deterministic SHA-256 digest of canonical JSON containing
only the selected capability mapping and concrete execution/security semantics:

```text
{
  "capability_id": "...",
  "tool_id": "...",
  "enabled": true,
  "permission_level": "...",
  "risk_level": "...",
  "allowed_actions": [sorted strings],
  "parameter_schema": canonical object,
  "execution_contract_version": "..."
}
```

The implementation should add explicit, stable capability mapping,
parameter-schema, and execution-contract fields to the registry definitions;
the current `ToolDefinition` does not yet contain all of them. Canonical JSON
uses sorted object keys, deterministic list ordering where order is not
semantic, UTF-8 encoding, no whitespace, and SHA-256.

Do not include timestamps, runtime counters, UI wording, executor object
addresses, or unrelated registry entries. A meaningful change to permission,
enabled state, capability mapping, allowed action, parameter schema, or
execution contract must change the fingerprint. Cosmetic description changes
must not unnecessarily invalidate approval.

## Runtime Integration

Phase 11.1 remains structurally intact:

```text
Plan -> AgentRuntime -> RuntimeExecutor -> ToolGateway -> Observation
```

Phase 11.2 changes the input contract to:

```text
Capability Plan Step
  -> CapabilityResolver
  -> Approved Resolved Snapshot
  -> AgentRuntime
  -> Executor Adapter
  -> ToolGateway
  -> Observation
  -> CONTINUE / COMPLETE / FAIL
```

AgentRuntime consumes already-resolved snapshots. It must not inspect
candidate lists, select a tool, re-resolve parameters, or call an executor
directly. ToolGateway remains responsible for final registration, permission,
approval, workspace, and execution checks. Observation remains responsible
for the existing deterministic CONTINUE / COMPLETE / FAIL behavior. Replanning
is out of scope.

## Persistence Strategy

Do not add a new database table. Extend existing plan and approval persistence
minimally:

- Store the capability-first plan and per-step resolved snapshot references in
  the existing `PlanRecord.plan_json`, with an explicit schema version.
- Add a structured JSON `resolved_snapshot` field to `ApprovalRecord` (or an
  equivalent typed JSON column in the existing approval model). This is the
  approval-bound immutable copy, not a free-form audit message.
- Keep `ToolExecutionRecord` for actual concrete execution metadata and keep
  Evidence and AuditEvent as existing downstream records.

The approval snapshot is necessary because a mutable plan JSON alone cannot
prove what was approved after resolution. No separate task or execution model
is introduced. A production implementation must provide a migration for the
minimal approval-column extension before using the new schema with existing
databases.

## Audit Model

Use the existing `AuditEventRecord` conventions and bounded structured JSON
payloads. Add events for:

- `CAPABILITY_REQUESTED`: task, plan, plan version, step, capability ID, and
  normalized requirement summary.
- `CAPABILITY_RESOLVED`: capability ID, resolved tool ID, normalized
  parameters, and registry fingerprint.
- `EXECUTION_SNAPSHOT_APPROVED`: approval ID, task/plan/version, capability,
  resolved tool, normalized parameters, and fingerprint.
- `RUNTIME_EXECUTION`: snapshot identifiers, concrete action, execution ID,
  result status, and bounded execution metadata.

Together with existing evidence and observation events, the audit trail must
reconstruct why a capability was required, which tool was authorized, which
parameters were approved, which registry semantics were in force, and what
actually executed. Do not persist hidden chain-of-thought or unrestricted
provider output.

## Fail-Closed Behavior

| Condition | Required result |
| --- | --- |
| Unknown capability | Reject resolution |
| Zero valid candidates | Reject resolution |
| Multiple valid candidates | Reject resolution |
| Disabled candidate | Exclude; reject if no unique candidate remains |
| Unregistered candidate | Exclude; reject if no unique candidate remains |
| Permission mismatch | Exclude/reject |
| Invalid parameters | Reject before approval |
| Plan ID mismatch | Reject approval or runtime |
| Plan version mismatch | Reject approval or runtime |
| Approval snapshot mismatch | Reject runtime |
| Tool removed after approval | Reject fingerprint/registry validation |
| Execution semantics changed | Reject fingerprint validation |
| Registry fingerprint mismatch | Reject runtime |
| Runtime receives unresolved input | Reject runtime |
| Runtime receives modified parameters | Reject runtime |
| ToolGateway bypass attempt | Reject by architecture and tests; no alternate executor |

Never fall back to legacy concrete-tool input, a default tool, arbitrary shell,
the first candidate, or a model-selected unvalidated tool.

## Test Strategy

The implementation must add deterministic tests for:

1. `repository_state` -> `git_read`.
2. `project_metadata` -> `file_read`.
3. `test_verification` -> `test_run`.
4. Unknown capability rejection.
5. Zero valid candidates rejection.
6. Multiple valid candidates rejection.
7. Disabled candidate rejection.
8. Unregistered candidate rejection.
9. Permission mismatch rejection.
10. Invalid parameter rejection.
11. Stable normalized parameters across approval and execution.
12. Plan ID mismatch rejection.
13. Plan version mismatch rejection.
14. Registry fingerprint mismatch rejection.
15. Tool removal after approval rejection.
16. Runtime rejection of unresolved input.
17. Runtime inability to bypass the resolver.
18. Runtime inability to bypass ToolGateway.
19. Multi-step plans resolving different capabilities.
20. Phase 11.1 success behavior preservation.
21. Phase 11.1 failure behavior preservation.
22. Existing regression suite remaining green.

The future lightweight metric is Tool Selection Accuracy. A full evaluation
framework is not part of Phase 11.2.

## Security Properties

- The model proposes semantic intent but never receives final executor
  authority.
- Only explicitly registered, enabled, mapped, permission-compatible, and
  parameter-valid tools can be resolved.
- Human approval binds the concrete execution snapshot and registry semantics.
- Runtime cannot drift from the approved capability, tool, parameters, plan,
  or registry fingerprint.
- ToolGateway remains the final permission and workspace boundary.
- No arbitrary shell, hidden chain-of-thought, or autonomous tool discovery is
  introduced.
- Audit and evidence records remain bounded and reconstructable.

## Out of Scope

- Direct LLM tool selection or candidate ranking.
- Observation-driven replanning.
- RAG, MCP, Multi-Agent, login, RBAC, Docker, Kubernetes, PostgreSQL, or local
  models.
- Arbitrary shell execution.
- A full evaluation platform.
- Production implementation, migration execution, or dependency changes in
  this design-only phase.

## Future Evolution

Later phases may add more capabilities or a deliberately governed multi-tool
resolution policy. Such changes must preserve application ownership of
authority, explicit candidate mappings, approval binding, deterministic audit,
and the ToolGateway boundary. Any move from unique-candidate resolution to
priority or policy-based selection requires a separate reviewed design.

## Expected Files Affected

Implementation is expected to touch only existing ownership areas:

- `backend/app/agents/planner/schemas.py` and `validator.py` for the new plan
  contract and legacy parser.
- `backend/app/tools/models.py`, `registry.py`, and a new capability registry/
  resolver module under the existing `backend/app/tools` or `agents` boundary.
- `backend/app/approvals/service.py` and existing approval schema/model for
  snapshot binding.
- `backend/app/agent_runtime/runtime.py` and `executor.py` to consume, not
  resolve, snapshots.
- Existing audit, plan, approval, execution, and test modules as needed.
- Frontend approval/task detail schemas only when the approved snapshot must be
  displayed.

No new top-level repository directory, parallel gateway, or unrelated
infrastructure is required.

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Legacy concrete-tool plans remain executable | Version them, parse for reading only, and reject them in the new runtime |
| Approval drifts from runtime | Persist and compare the immutable snapshot and fingerprint |
| Registry fingerprint is noisy | Hash only canonical security/execution semantics |
| Resolver becomes a hidden executor | Keep resolution pure and require ToolGateway for execution |
| Multiple tools become ambiguous | Fail closed; do not add priority or tie-breaks in 11.2 |
| Parameters are changed after approval | Normalize before approval and compare exact structured values at runtime |
| Audit exposes private reasoning | Persist only structured intent, resolution, execution, evidence, and bounded summaries |
| Minimal persistence extension is skipped | Treat the approval snapshot column as required before production use |
