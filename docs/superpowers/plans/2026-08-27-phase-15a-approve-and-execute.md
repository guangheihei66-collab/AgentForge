# Phase 15A Server-Owned Approval-to-Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the Agent Workspace HUMAN Approval continuation behind one governed backend command so an approved Agent Task cannot be stranded by a browser-owned second request.

**Architecture:** Add one Agent-specific `POST /tasks/{task_id}/approve-and-execute` command. A thin route delegates exact Task/Plan/Approval binding to `AgentApprovalExecutionService`, which calls the existing `ApprovalService` and then the existing `AgentRuntime`/`ToolGateway` path. Global Approvals keeps its approval-only endpoint and semantics; no database schema, capability, permission, Project authority, Runtime, or Replan policy changes are introduced.

**Tech Stack:** Python, FastAPI, SQLAlchemy, existing AgentRuntime and ToolGateway, React, TypeScript, Vite, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-08-27-phase-15a-approve-and-execute-amendment.md`, amending `docs/superpowers/specs/2026-08-26-repository-analyst-agent-design.md`.

## Global Constraints

- Agent Workspace Approve uses one composite command; it must not call `api.approve()` then `refreshTask()` then `api.executeTask()` to start execution.
- Global Approvals continues to call `POST /approvals/{approval_id}/approve` and never starts execution automatically.
- The command accepts only an exact `task_id`, current valid `plan_id`, current `plan_version`, pending `approval_id`, and HUMAN `actor`.
- ApprovalService, CapabilityResolver, AgentRuntime, RuntimeExecutor, ToolGateway, Project authority, evidence, audit, and Controlled Replan remain the existing authorities.
- A duplicate command for a consumed Approval invokes Runtime zero additional times; a v1 Approval never authorizes a successor Plan.
- If Runtime initiation fails after Approval persistence and before any ToolExecution, persist bounded `EXECUTION_INITIATION_FAILED` and transition `RUNNING -> FAILED`; never expose stack traces, secrets, prompts, or hidden reasoning.
- Do not add a database migration, persistent idempotency table, capability, arbitrary shell/write action, frontend dependency, localization code, version change, release metadata, merge, push, tag, or release.
- Historical stuck dogfood Tasks remain untouched and cannot be used as acceptance evidence.

---

### Task 1: Commit the approved architectural amendment and implementation contract

**Files:**
- Modify: `docs/superpowers/specs/2026-08-26-repository-analyst-agent-design.md`
- Create: `docs/superpowers/specs/2026-08-27-phase-15a-approve-and-execute-amendment.md`
- Create: `docs/superpowers/plans/2026-08-27-phase-15a-approve-and-execute.md`

**Interfaces:** The amendment defines `POST /tasks/{task_id}/approve-and-execute`, request fields `approval_id`, `plan_id`, `plan_version`, and `actor`, the existing bounded Runtime result response, duplicate/failure semantics, and the unchanged Global Approval contract. Later tasks implement this exact contract.

- [ ] **Step 1: Review the amendment against the existing design.** Confirm it explicitly replaces browser-owned Agent continuation, preserves all security invariants, names the current state-machine behavior, describes initiation failure without claiming atomicity, and leaves Global Approvals approval-only.
- [ ] **Step 2: Scan the plan for placeholders and contract drift.** Run `$patterns = @('T'+'BD', 'TO'+'DO', 'Similar '+'to', 'handle '+'edge'); Select-String -Path docs/superpowers/plans/2026-08-27-phase-15a-approve-and-execute.md -Pattern $patterns`; expected: no placeholder matches. Verify every later method name and field matches the amendment and current repository types.
- [ ] **Step 3: Commit only the design and plan documents.** Run `git add docs/superpowers/specs/2026-08-26-repository-analyst-agent-design.md docs/superpowers/specs/2026-08-27-phase-15a-approve-and-execute-amendment.md docs/superpowers/plans/2026-08-27-phase-15a-approve-and-execute.md; git commit -m "docs: amend Phase 15A approval orchestration"`.

### Task 2: Add the backend service-level Agent orchestration with TDD

**Files:**
- Create: `backend/app/agents/orchestration/__init__.py`
- Create: `backend/app/agents/orchestration/service.py`
- Create: `backend/tests/test_agent_approval_execution.py`

**Interfaces:** Export `AgentApprovalExecutionService` with:

```python
class AgentApprovalExecutionService:
    def __init__(self, session: Session, runtime_factory: Callable[[str], AgentRuntime]): ...

    def approve_and_execute(
        self, *, task_id: str, approval_id: str, plan_id: str,
        plan_version: int, actor: str,
    ) -> RuntimeResult: ...
```

`runtime_factory(task_id)` is invoked only after the existing `ApprovalService.approve()` succeeds. The service loads the highest current Plan through `PlanRepository`, loads the Approval record, validates exact Task/Plan/version ownership and `PENDING` decision, calls `ApprovalService.approve`, then calls `AgentRuntime.run(task_id=task_id, plan_id=current.id, plan_version=current.version)`.

- [ ] **Step 1: Write the RED service tests.** Use the existing isolated Project/Task fixtures and a fake Runtime with a call counter. Add separate tests for: valid pending Approval calls `approve_and_execute` once and returns its RuntimeResult; cross-Task Approval; older Plan; wrong Plan ID; wrong version; successor current Plan rejecting v1 Approval; rejected/approved Approval; no current valid Plan; duplicate invocation after the first command; Runtime factory/Runtime initiation exception; and a fake Runtime proving the service receives the already-resolved current binding rather than choosing a tool. The rejection cases must assert zero Runtime calls and unchanged non-execution authority.
- [ ] **Step 2: Run the focused tests and verify RED.** Run `D:\AgentProjects\AgentForge\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_agent_approval_execution.py -q`; expected: collection or assertion failures because `AgentApprovalExecutionService` and its contract do not yet exist, not fixture or import errors unrelated to the feature.
- [ ] **Step 3: Implement the smallest service.** Query existing `TaskRecord`, `PlanRecord`, and `ApprovalRecord`; reject missing/cross-bound/stale/non-pending bindings with bounded `ApprovalError`/`LookupError`; delegate decision persistence to `ApprovalService.approve`; lazily obtain `AgentRuntime`; and return its result. On an exception after approval, query `ToolExecutionRecord`; when zero records exist and the Task is `RUNNING`, use `TaskService.transition_task(..., FAILED, actor="agent_orchestration", reason="Execution initiation failed")`, add one bounded `EXECUTION_INITIATION_FAILED` audit event containing only Task/Plan/version and an exception category, commit, and raise a safe orchestration error. Do not call Runtime for a consumed Approval.
- [ ] **Step 4: Run the focused tests and verify GREEN.** Re-run the same pytest command and confirm all service cases pass, including exactly one Runtime call for a valid command and zero for every binding/duplicate case.
- [ ] **Step 5: Commit the backend service.** Run `git add backend/app/agents/orchestration backend/tests/test_agent_approval_execution.py; git commit -m "feat: add governed Agent approval orchestration"`.

### Task 3: Expose the thin FastAPI command and preserve Global Approval semantics

**Files:**
- Modify: `backend/app/api/routes/execution.py`
- Modify: `backend/tests/test_api.py`
- Modify: `backend/tests/test_workspace_security.py` only if a focused route-boundary assertion is needed

**Interfaces:** Add `POST /tasks/{task_id}/approve-and-execute` with request model `ApproveAndExecuteRequest` and the existing `_serialize_result` response. Refactor the existing runtime-construction code into a lazy `_build_runtime(db, task_id)` helper used by both the generic execute route and the new command; the new route must not build or run Runtime before the service validates and persists the HUMAN Approval.

The route returns HTTP 404 for an unknown Task or Approval, HTTP 400 for cross-bound, stale, invalid, rejected, or already-consumed Approval/Plan authority, HTTP 500 with safe detail `Execution initiation failed` when the service records initiation failure, and HTTP 200 with the existing Runtime result on success.

- [ ] **Step 1: Write RED API contract tests.** Add an integration test that creates an isolated Project, Task, valid Plan, and pending Approval, then posts the composite command and expects a terminal Runtime result, Approval `APPROVED`, ToolExecution records, Observation audit, and Evidence. Add status tests for unknown Task, cross-Task Approval, stale Plan/version, non-pending Approval, and initiation failure with safe HTTP detail and persisted `FAILED`/`EXECUTION_INITIATION_FAILED`. Add a duplicate/retry test asserting the second command does not add another ToolExecution. Add a regression that calls the existing Global Approval endpoint and asserts Approval becomes `APPROVED`, Task is unlocked as before, and no ToolExecution is created.
- [ ] **Step 2: Run the focused API tests and verify RED.** Run `D:\AgentProjects\AgentForge\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api.py -k "approve_and_execute or global_approval" -q`; expected: the new route returns 404 or the new assertions fail because the endpoint is absent.
- [ ] **Step 3: Implement the thin route.** Import the service and request schema, pass the request fields unchanged to `AgentApprovalExecutionService`, serialize the returned RuntimeResult with the existing bounded serializer, map missing Task/Approval to 404, authority/binding/duplicate errors to HTTP 400 as the existing Approval route does, and initiation failure to HTTP 500 with safe detail `Execution initiation failed`. Keep `POST /approvals/{approval_id}/approve` unchanged.
- [ ] **Step 4: Run focused API tests and existing execution/approval security tests.** Run the focused command again, then `D:\AgentProjects\AgentForge\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api.py backend\tests\test_agent_runtime.py backend\tests\test_approval_security.py -q`; expected: GREEN and no generic Global Approval test starts Runtime.
- [ ] **Step 5: Commit the route and API contract.** Run `git add backend/app/api/routes/execution.py backend/app/schemas/approval.py backend/tests/test_api.py backend/tests/test_workspace_security.py; git commit -m "feat: expose Agent approve-and-execute command"`.

### Task 4: Add the frontend composite API and hook orchestration with TDD

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/hooks/useOperations.ts`
- Create: `frontend/src/api/client.approve-and-execute.test.ts`
- Modify: `frontend/src/hooks/useOperations.agent.test.tsx`

**Interfaces:** Add:

```typescript
type AgentApprovalCommand = {
  approval_id: string
  plan_id: string
  plan_version: number
  actor: string
}

api.approveAndExecuteTask(taskId: string, command: AgentApprovalCommand): Promise<RuntimeResult>
useOperations().approveAndExecuteAgentTask(item: ApprovalQueueItem): Promise<void>
```

`approveAndExecuteAgentTask` uses the currently selected Task ID, sends exactly one composite API request, then calls `refreshTask` only to render authoritative state. It never calls `act('approve')` or `executeAgentTask` to initiate the command. A ref prevents duplicate in-flight frontend commands; errors are converted to safe Agent Workspace messages.

- [ ] **Step 1: Write RED client and hook tests.** Assert the API method sends one `POST /tasks/task-1/approve-and-execute` with exact JSON `{ approval_id, plan_id, plan_version, actor: 'operator' }` and returns the bounded result. Add hook tests proving a selected Task uses the queue item's exact Approval/Plan binding, calls the composite method once, does not call `api.approve` or `api.executeTask`, and still sends the command when a subsequent refresh rejects. Add latest failure, safe error, and duplicate in-flight cases.
- [ ] **Step 2: Run focused frontend tests and verify RED.** Run `npm test -- --run src/api/client.approve-and-execute.test.ts src/hooks/useOperations.agent.test.tsx`; expected: the new method/tests fail because the composite API and hook method are absent.
- [ ] **Step 3: Implement the API method and hook method.** Add the exact typed request method; add a bounded command-in-flight ref; call the composite API before any refresh; refresh the selected Task after the command response; and map approval/authority, initiation, and generic errors to safe user-facing categories without exposing raw internal text. Preserve the existing generic `act` and explicit approved-plan retry method for their separate semantics.
- [ ] **Step 4: Run focused tests and verify GREEN.** Re-run the client and hook tests, then `npm test -- --run src/App.approval-execution.test.tsx src/pages/AgentWorkspace.test.tsx`; expected: existing tests that still encode the old two-hop path are updated in Task 5, while all current non-approval behavior remains green.
- [ ] **Step 5: Commit the frontend command plumbing.** Run `git add frontend/src/api/client.ts frontend/src/types/index.ts frontend/src/hooks/useOperations.ts frontend/src/api/client.approve-and-execute.test.ts frontend/src/hooks/useOperations.agent.test.tsx; git commit -m "feat: call Agent approval orchestration command"`.

### Task 5: Wire Agent Workspace once, retain Global Approvals approval-only, and test UX boundaries

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/AgentWorkspace.tsx`
- Modify: `frontend/src/components/AgentApprovalCard.tsx`
- Modify: `frontend/src/App.approval-execution.test.tsx`
- Modify: `frontend/src/App.test.tsx`
- Modify: `frontend/src/pages/AgentWorkspace.test.tsx`
- Modify: `frontend/src/components/AgentApprovalCard.test.tsx`

**Interfaces:** Change the Agent Workspace approval callback to receive the complete matching `ApprovalQueueItem`, so the exact `approval_id`, `plan_id`, and `plan_version` travel to `approveAndExecuteAgentTask`. The Agent card disables its Approve/Reject controls while the composite command is in flight. Global `Approvals` continues to receive `onApprove={(id) => void ops.act('approve', id)}`.

- [ ] **Step 1: Write/update RED App-level tests.** Replace the old Agent test that expected `/approvals/{id}/approve` followed by `/execute` with a real App wiring test that provides successful read responses, clicks Agent Workspace Approve once, and asserts exactly one composite request plus zero separate approve/execute requests. Add tests for safe composite failure rendering, refresh failure after command not preventing initiation, double click suppression, reload reconstruction from persisted approved/execution/report responses, and a Replan v2 pending Approval that cannot use v1. Keep/add a Global Approvals test proving it still sends only `/approvals/{id}/approve`.
- [ ] **Step 2: Run the focused App/card tests and verify RED.** Run `npm test -- --run src/App.approval-execution.test.tsx src/App.test.tsx src/pages/AgentWorkspace.test.tsx src/components/AgentApprovalCard.test.tsx`; expected: the updated composite assertions fail against the old App callback and card contract.
- [ ] **Step 3: Implement the smallest UI wiring change.** Replace the Agent callback's `act -> refreshTask -> executeAgentTask` sequence with one `ops.approveAndExecuteAgentTask(item)` call. Keep authoritative refresh/polling as display-only. Add safe error presentation and local action in-flight suppression; do not add a second execution mechanism, change Global Approvals, or expose internal errors.
- [ ] **Step 4: Run the focused tests and verify GREEN.** Re-run the same command and confirm one composite request, zero separate mutation requests for Agent approval, safe errors, duplicate suppression, reload reconstruction, and unchanged Global approval-only behavior.
- [ ] **Step 5: Commit the frontend surface.** Run `git add frontend/src/App.tsx frontend/src/pages/AgentWorkspace.tsx frontend/src/components/AgentApprovalCard.tsx frontend/src/App.approval-execution.test.tsx frontend/src/App.test.tsx frontend/src/pages/AgentWorkspace.test.tsx frontend/src/components/AgentApprovalCard.test.tsx; git commit -m "feat: route Agent approval through backend command"`.

### Task 6: Full security, regression, and lifecycle verification before HUMAN dogfood

**Files:**
- Modify only tests or bounded implementation files if a fresh verification failure proves a defect; do not alter unrelated features.

- [ ] **Step 1: Run targeted backend verification.** Run orchestration, API contract, Approval security, plan-binding, Replan fresh-Approval, duplicate, and initiation-failure tests; capture counts in a bounded log file and inspect only summaries/failures.
- [ ] **Step 2: Run targeted frontend verification.** Run composite API, hook, App, Agent Workspace, Global Approval, polling/concurrency, reload, timeline, evidence, report, and no-CoT tests; confirm no frontend test invokes separate Agent approve then execute mutations.
- [ ] **Step 3: Run all required fresh suites.** Run frontend full suite and production build; backend full suite; DB isolation; governance/security; launcher tests; Provider and Diagnostics regressions; launcher resolution smoke; `git diff --check`; and the existing secret/debug scan. Redirect complete logs to temporary files outside the repository and report only bounded summaries and relevant failures.
- [ ] **Step 4: Review source and persistence boundaries.** Use bounded `git diff --check`, `git status`, and `rg` to prove there is one new Agent endpoint, no DB migration, no new capability, no ToolGateway bypass, no automatic Approval, no CoT/secret output, no localization code, and no changes to historical Tasks or runtime data.
- [ ] **Step 5: Restart only owned feature-worktree services.** Prove the backend/frontend listener PID, executable, command, and source root; stop only the owned feature-worktree processes; start the latest backend/frontend; verify `GET /diagnostics` revision equals the new HEAD and the served frontend source contains the composite callback. Do not restart unrelated services.
- [ ] **Step 6: Create exactly one final real dogfood Task after all checks pass.** Use Project ID `5c4a1ae2-5bb2-4a35-9dfb-cc4df25e6e1d` and the approved release-readiness Goal through the supported Task → Plan → Approval request path. Verify Task `WAITING_APPROVAL`, current Plan version, Task Detail `approval.plan_version`, and Approval `PENDING`; do not call `/execute` or approve it. Return the Task/Plan/Approval IDs and stop for the one HUMAN Agent Workspace click.
- [ ] **Step 7: After the one HUMAN click, verify without rescue.** Read canonical audit/detail/report and prove the composite Agent request caused Approval, initiation, ToolExecution, Observation, Evidence, and terminal Report. Confirm no separate browser-generated approval then execute sequence, Global Approvals remains approval-only, and a Replan successor stops at a fresh Approval gate. If the new command fails before ToolExecution, report the persisted explicit initiation failure; do not create another Task or manually call `/execute`.

## Self-review checklist

- [ ] The amendment explicitly explains the lifecycle-reliability failure of the browser two-hop and the server-owned continuation.
- [ ] The service validates Task, highest current Plan, Approval ownership, exact version, pending decision, Project authority through existing services, and consumed-Approval duplicate behavior.
- [ ] Runtime and ToolGateway remain the only execution authorities; the endpoint does not resolve tools or duplicate runtime logic.
- [ ] Initiation failure is explicit and bounded; no false atomicity or silent `RUNNING + zero execution` state is accepted.
- [ ] Global Approval endpoint remains approval-only and has an explicit regression.
- [ ] Agent Workspace sends exactly one composite mutation and only reads after the command for rendering.
- [ ] Replan successor Approval, reload reconstruction, no-CoT, raw-content, security, DB isolation, Provider, Diagnostics, launcher, and secret verification remain covered.
- [ ] Historical Tasks, Native Localization, Phase 12 worktree, runtime data, version, release metadata, and Git remotes remain untouched.
