# Phase 15A Architectural Amendment: Server-Owned Approval-to-Execution

**Status:** HUMAN design approval granted.

**Base design:** `docs/superpowers/specs/2026-08-26-repository-analyst-agent-design.md`

## Decision

Move the Agent Workspace Approval-to-execution continuation behind one explicit
backend command. Add no new capability, permission, persistence model, database
migration, Runtime, ToolGateway, Project Authority, or Replan policy.

The existing browser sequence was:

```text
HUMAN Approve
  -> POST /approvals/{approval_id}/approve
  -> browser refreshes Task Detail
  -> browser decides to POST /tasks/{task_id}/execute
```

Repeated real-browser acceptance proved that the first request could persist
Approval while the second request never happened. The resulting
`APPROVED + RUNNING + zero execution` state was not a Runtime or ToolGateway
authorization failure; it was a lifecycle-reliability gap caused by making the
browser own a security-critical continuation.

## Exact Agent command contract

```text
POST /tasks/{task_id}/approve-and-execute
Content-Type: application/json

{
  "approval_id": "<HUMAN Approval ID>",
  "plan_id": "<current Plan ID>",
  "plan_version": 1,
  "actor": "operator"
}
```

The response reuses the existing bounded Runtime result shape:

```text
task_id
plan_id
plan_version
state
decision
completed_steps
observations
successor_plan_id
successor_plan_version
approval_id
```

No prompt, hidden reasoning, credential, raw provider output, or raw tool output
is returned.

## Server-owned sequence

`AgentApprovalExecutionService.approve_and_execute()` must:

1. Load the Task and highest current Plan.
2. Require supplied `plan_id` and `plan_version` to match that current valid Plan.
3. Load the supplied Approval and require exact Task/Plan/version ownership and
   `PENDING` decision.
4. Persist the HUMAN decision through the existing `ApprovalService.approve()`.
5. Re-read the authoritative approved binding.
6. Invoke the existing `AgentRuntime` through the existing RuntimeExecutor and
   ToolGateway path.

The service must not duplicate resolver or gateway logic. Runtime remains the
authority consumer of the approved snapshot, and ToolGateway remains the final
workspace/capability boundary.

## State and failure semantics

The command is not a claim that SQLite Approval persistence and external tool
execution are one atomic transaction. The server owns the continuation after it
accepts the command. If initiation fails after Approval persistence but before
any ToolExecution exists, the service records bounded factual audit event
`EXECUTION_INITIATION_FAILED` and transitions `RUNNING -> FAILED`. It must not
silently leave an unexplained `APPROVED + RUNNING + zero execution` state.

An Approval is consumptive for this command. A duplicate or retry for the same
Approval is rejected before Runtime invocation, so it cannot create duplicate
Runtime execution. This does not alter the generic Global Approval contract.

## Surface separation

Agent Workspace Approve calls the composite command once. After the response,
the frontend only refreshes authoritative Task Detail/Report data for display;
it does not decide whether execution starts.

Global Approvals remains:

```text
POST /approvals/{approval_id}/approve
  -> persist Approval
  -> no automatic execution
```

Controlled Replan remains unchanged: a successor Plan requires a fresh Approval,
and v1 Approval cannot authorize v2.

## Security invariants

- HUMAN Approval remains mandatory.
- Approval binds to exact Task, Plan ID, and Plan version.
- Only the current valid Plan may be accepted.
- CapabilityResolver remains deterministic and application-owned.
- AgentRuntime and ToolGateway remain the existing governed execution path.
- Project/workspace authority and approval snapshots are revalidated.
- No automatic Approval, arbitrary shell, write capability, or authority bypass.
- No Chain-of-Thought, credentials, or secret data is persisted or exposed.

## Error contract

- Unknown Task or Approval: HTTP 404, matching existing not-found behavior.
- Cross-bound Approval/Plan, stale Plan, non-pending Approval, or invalid
  authority: HTTP 400, matching the existing Approval route; no internal trace.
- Runtime initiation failure before ToolExecution: HTTP 500 with safe detail
  `Execution initiation failed`, plus
  persisted `EXECUTION_INITIATION_FAILED` and terminal Task failure.
- Duplicate command for consumed Approval: HTTP 400 approval error and zero
  Runtime invocation.

## Verification obligations

Backend tests cover valid command, cross-Task Approval, old/current Plan
binding, version mismatch, successor Plan isolation, rejected/consumed Approval,
duplicate command, initiation failure, Global Approval approval-only behavior,
and use of existing Runtime/Gateway authority.

Frontend tests cover one composite Agent request, no separate approve/execute
calls, safe error rendering, duplicate-click suppression, reload reconstruction,
and unchanged Global Approvals behavior.

The final HUMAN dogfood creates one fresh Task only after all automated checks
are green. The feature branch remains unmerged and unpublished.
