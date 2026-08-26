# Phase 15A: Repository Analyst Agent MVP

## 1. Problem statement

AgentForge already implements planning, deterministic capability resolution, human approval, governed execution, observations, controlled replanning, evidence, audit, and reporting. Its current console exposes these records as separate operations pages, but it does not yet present them as one understandable Agent experience. A normal operator should be able to provide a repository-analysis goal and follow the governed lifecycle without mistaking the product for an unrestricted chatbot or a second autonomous runtime.

## 2. User outcome

From an explicitly selected Project, a HUMAN enters a repository-analysis goal such as “Check whether this project is ready to release.” The user sees the task move through planning, plan review, approval, execution, observations, possible controlled replanning, and an evidence-backed report. The UI must make the source and authority of each state clear and must preserve raw repository and evidence content exactly.

## 3. Existing Runtime capabilities reused

Phase 15A reuses the existing application-owned path:

```text
TaskService / POST /tasks
  -> PlannerAgent / POST /tasks/{task_id}/plan
  -> PlanValidator + CapabilityResolver
  -> ApprovalService / POST /tasks/{task_id}/approval
  -> POST /approvals/{approval_id}/approve|reject
  -> POST /tasks/{task_id}/execute
  -> AgentRuntime -> ToolGateway
  -> ToolExecution, RuntimeObservation, Evidence, Audit, Report
```

The supported semantic capabilities remain `repository_state`, `project_metadata`, and `test_verification`, resolved respectively to the existing `git_read`, `file_read`, and predefined `test_run` tools. The model proposes semantic capability requests only; it does not choose tools, permissions, workspace roots, or approval decisions.

## 4. Repository findings and current API map

The current `backend/app/api/routes` modules provide:

| Need | Existing contract | Authority |
|---|---|---|
| Select Project | `GET /projects`, `GET /projects/{project_id}` | `ProjectService`, active Project policy |
| Create Task | `POST /tasks` with `project_id`, `title`, `goal` | `TaskService` binds canonical Project workspace |
| Create Plan | `POST /tasks/{task_id}/plan` | `PlannerAgent`, manifest, validator, resolver |
| Inspect pending approval | `GET /approvals/pending` | persisted Approval + validated Plan snapshot |
| Create/decide approval | `POST /tasks/{task_id}/approval`, approve/reject routes | `ApprovalService` |
| Execute | `POST /tasks/{task_id}/execute` | `AgentRuntime`, `ToolGateway`, fresh approval checks |
| Reconstruct lifecycle records | `GET /tasks/{task_id}/detail`, `/audit`, `/report` | persisted Task, Plan, Approval, Execution, Evidence, Audit |

`PlannerAgent.create_plan` transitions `CREATED -> PLANNING -> WAITING_APPROVAL`, creates immutable Plan v1, records capability requests/resolution, and preserves Project authority in the Plan. `AgentRuntime` persists runtime transitions, execution records, observations, decisions, and evidence references. `ReplanningService` creates an immutable successor Plan and a new Approval requirement; it never authorizes a successor with the prior Approval.

The frontend currently has a `useOperations` hook that composes these APIs and pages for Dashboard, Projects, Task Detail, Approvals, and Report. It does not have an Agent page, task planning action, bounded active-task polling, or a complete authoritative event projection.

## 5. Architecture decision

**Decision: A — zero new backend endpoints.**

The existing contracts cleanly express the MVP lifecycle. The Agent Workspace can create a Task, call the existing planning endpoint, read the Task Detail and pending Approval data, call the existing Approval and execution endpoints, and refresh the same Task Detail/Report. A new aggregate endpoint would duplicate a read-only join that already exists in `/tasks/{task_id}/detail` plus `/tasks/{task_id}/report`; a task-creation facade would duplicate `POST /tasks`, which already requires the selected Project and raw Goal.

The frontend may add a small projection function that maps persisted detail/audit records to safe timeline items. This is presentation logic, not a new persistence model or runtime.

## 6. Agent Workspace UX

Add one first-class `Agent` entry point and one coherent workspace. The workspace contains:

1. Goal Composer: active Project selector, raw Goal textarea, and Start Agent action.
2. Agent Timeline: safe structured lifecycle events derived from authoritative Task and Audit records.
3. Plan/Approval Card: human-readable plan summary, capability presentation, risk, workspace scope, and approve/reject controls when approval is pending.
4. Execution/Evidence area: step status, observations, evidence references, and final Report with Conclusion separated from Evidence.

Existing administrative Projects, Tasks, Approvals, Evidence, Audit, and Reports remain available for inspection. The Agent page is the orchestration projection over them, not a replacement for them.

The Agent page must show an explicit selected Project and its canonical workspace scope. It must not silently fall back to an arbitrary workspace. Raw Goal, task titles, stored descriptions, paths, commands, identifiers, and Evidence remain raw content; only product-authored labels and explanations are localized or reformatted.

## 7. Goal Composer

The Project selector lists only active Projects returned by `GET /projects`. The selected Project ID is sent unchanged to `POST /tasks`. The Goal is sent unchanged as the Task `goal`; a UI title may be generated from a bounded user-visible field or use a fixed product-authored title, but the raw Goal must remain the canonical Task Goal.

On submit:

1. Create the Task with Project ID and Goal.
2. Immediately show `Goal received` and `Planning...`.
3. Call `POST /tasks/{task_id}/plan` with the existing planning context contract.
4. On success, display the persisted Plan and wait for Approval.
5. On provider, validation, or resolution failure, show a terminal planning failure reconstructed from the Task state and safe error category; never show success.

The composer is disabled while the request is in flight and must not create duplicate Tasks on repeated clicks.

## 8. Timeline event model

The UI exposes safe structured state, never Chain-of-Thought or raw provider prompts/responses. Timeline items are a projection with:

```text
{ id, kind, occurred_at, status, plan_version?, step_id?, summary?, raw_refs? }
```

The projection maps persisted records as follows:

| User-visible event | Authoritative source |
|---|---|
| Goal received | `TASK_CREATED` audit + Task `created_at` |
| Planning | Task `PLANNING` transition / `TASK_STATE_CHANGED` |
| Plan created | `PLAN_CREATED` audit + Plan record |
| Requested capability / resolved tool | `CAPABILITY_REQUESTED` and `CAPABILITY_RESOLVED` audit, shown with friendly capability copy and safe technical IDs where useful |
| Waiting for approval | Task state + pending Approval/validated Plan |
| Approved / rejected | Approval record and approval audit |
| Step started / execution completed | Runtime transitions, `ToolExecutionRecord`, `RUNTIME_EXECUTION` audit |
| Observation recorded | `RUNTIME_OBSERVATION` audit and persisted observation/evidence references |
| Replanning | `REPLAN_REQUESTED`, `REPLAN_PROPOSED`, `PLAN_VERSION_CREATED`, `REPLAN_APPROVAL_REQUIRED` |
| Completed / failed | terminal Task state, Runtime decision, and Report |

The projection must tolerate older records and unknown event types by showing a safe generic audit event. It must not infer success from a missing record.

## 9. Approval UX

Approval remains authoritative in `ApprovalService` and the existing approval endpoints. The Agent card presents:

- Plan summary and version.
- Friendly capability labels: `Read repository status`, `Read project metadata`, `Run project tests`.
- Resolved tool and normalized parameters in an expandable technical section.
- Risk and permission boundary.
- Selected Project and canonical workspace scope.
- Explicit statement that arbitrary shell, file writes, Git writes, commits, pushes, and releases are not granted.
- Approve and Reject actions.

Canonical IDs remain unchanged in API payloads and persisted records. Approval failure, stale snapshot, Project drift, or rejected Approval is displayed as a blocked/failed state. The UI must never call execution after rejection or before a matching approved snapshot exists.

## 10. Execution lifecycle

After Approval, the Agent Workspace invokes only `POST /tasks/{task_id}/execute`. It must not call tools directly or select a tool from the plan. The backend revalidates Task, Plan version, Approval snapshot, Project authority, registry, workspace, and runtime limits before each governed step.

The UI refreshes Task Detail and Report after the execution response and during active execution. A successful HTTP response is not itself a success claim; the displayed result comes from the persisted Task state, ToolExecution statuses, observations, evidence, and Report.

## 11. Controlled Replan UX

When persisted records show a controlled replan, display an explicit sequence:

```text
Plan v1 -> failed/observed step -> Replanning -> Plan v2 -> NEW approval required
```

The successor Plan version, lineage, triggering observation/execution, reason code, and fresh Approval are shown from the existing Plan JSON and audit records. The Agent Workspace must stop at `WAITING_APPROVAL` for the successor. It must never auto-approve, auto-execute, or present Plan v2 as covered by Plan v1 Approval. Replan-limit, step-limit, duplicate/no-progress, provider, or validation rejection is terminally displayed with its persisted reason.

## 12. Evidence/Report UX

The final area separates:

**Conclusion** — the existing Report readiness and summary, clearly marked as PASS, FAIL, or PENDING.

**Evidence** — persisted Evidence rows and safe references to the ToolExecution/Observation that produced them where current records provide the linkage. Evidence summaries, paths, hashes, commands, and raw output-derived content are not translated or fabricated.

No Evidence means the UI says that no Evidence was recorded; it does not manufacture a recommendation. A failed ToolExecution or failed Task cannot render an all-success conclusion.

## 13. Backend/API approach

No backend endpoint or schema change is required for the MVP. The frontend composes:

```text
POST /tasks
POST /tasks/{id}/plan
GET /tasks/{id}/detail
GET /approvals/pending
POST /tasks/{id}/approval
POST /approvals/{id}/approve|reject
POST /tasks/{id}/execute
GET /tasks/{id}/report
GET /tasks/{id}/audit
```

The existing API has one minor product-experience consideration for implementation: the current execution response is a bounded summary, while authoritative detail is persisted and available through the read endpoints. The Agent page should therefore refresh/read after each mutation rather than treat the response as the complete timeline.

## 14. Persistence strategy

Do not add Agent, Timeline, Plan, Approval, Execution, Observation, Evidence, or Report tables. Task, Plan, Approval, ToolExecution, Audit, Evidence, and existing runtime observation records remain canonical. The frontend stores only transient view state: selected Project/Task, request-in-flight state, and polling timer state.

Refresh/reload reconstructs the workspace from the Task ID, Task Detail, Report, pending Approvals, and Audit endpoints. A browser refresh must not lose the Goal, Plan version, Approval decision, execution status, Replan lineage, or Evidence references.

## 15. Polling/refresh strategy

No WebSocket or SSE infrastructure is justified by the current repository. Use bounded polling for the selected active Task:

- Begin after Task creation/planning or when the selected Task is non-terminal.
- Refresh Task Detail and Report at a bounded interval, with one request in flight at a time.
- Stop on `SUCCESS`, `FAILED`, or `CANCELLED`.
- Continue through `PLANNING`, `WAITING_APPROVAL`, and `RUNNING` as needed, while Approval actions can trigger immediate refresh.
- Stop and surface a bounded network error after repeated failures; never turn a stale view into SUCCESS.
- Cancel/ignore stale responses when the user changes Project or Task.

Polling is a UI concern only. It does not advance runtime state or execute tools.

## 16. Project authority

The selected Project ID is the only authority input from the Goal Composer. The backend derives the canonical workspace through `ProjectService`; the model never receives permission to choose a workspace. Existing project capability allow-lists, active/archived rules, authority snapshots, containment validation, config-version checks, and approval drift protection remain unchanged.

## 17. Security invariants

- New capabilities: none.
- Arbitrary shell: none.
- File writes: none.
- Git writes, commits, pushes, releases, and GitHub writes: none.
- LLM permission selection: none.
- Capability resolution: deterministic application-owned resolver only.
- Final authority: ToolGateway.
- Approval: required and bound to exact Task/Plan/version/snapshot.
- Replan: successor requires a fresh Approval.
- Project/workspace containment: unchanged.
- Runtime, replan, total-step, timeout, output-size, and context limits: unchanged.
- Chain-of-Thought, raw provider prompts/responses, credentials, and secrets: never rendered or persisted by this feature.

## 18. Failure handling

The UI must have deterministic tests and explicit states for:

- Task creation/network failure.
- Planner/provider failure.
- Invalid Plan or capability-resolution failure.
- Approval pending, rejected, stale, or drift-invalidated.
- ToolExecution failure and semantic test failure.
- Controlled Replan and fresh successor Approval.
- Replan limit and total-step limit.
- Provider failure during Replan.
- Terminal Task failure.
- Refresh/navigation during active execution.
- Polling timeout or reload reconstruction.

Every failure state is sourced from a persisted status/reason or an explicit bounded request error. No failure may be mapped to SUCCESS merely because a request returned HTTP 200.

## 19. Testing strategy

Frontend tests must use the real Agent Workspace composition and deterministic API mocks. Required cases are:

1. Create Agent Task from Project and raw Goal.
2. Planning state is visible and duplicate submit is prevented.
3. Valid Plan is displayed after creation.
4. Approval requirement, capabilities, risk, and scope are visible.
5. Rejected Approval prevents execution.
6. Approved Task calls only the governed execution endpoint.
7. ToolExecution appears in the timeline.
8. Observation and Evidence become visible.
9. Semantic Tool failure appears as failure.
10. Replan sequence and Plan v2 are visible.
11. Successor Plan requires fresh Approval and cannot execute under v1.
12. Completion produces a Report.
13. Report references real Evidence.
14. Project authority remains the selected Project.
15. Raw Goal remains unchanged.
16. Raw Evidence remains unchanged.
17. No Chain-of-Thought is rendered.
18. Refresh/reload reconstructs from persisted authoritative responses.
19. Polling stops at terminal state and ignores stale responses.
20. Existing backend governance, security, runtime, provider, diagnostics, and isolation suites remain green.

Backend regression coverage should remain unchanged unless repository evidence identifies an API contract gap. If implementation discovers that a required authoritative field cannot be reconstructed from current responses, first add the narrowest contract test and revisit the zero-endpoint decision before adding an endpoint.

## 20. HUMAN dogfood scenario

1. Start the existing AgentForge backend/frontend with the approved runtime configuration.
2. Open Agent.
3. Select the active AgentForge Project.
4. Enter: `Check whether this project is ready to release.`
5. Start Agent and observe Goal received, Planning, and Plan v1.
6. Review requested read-only capabilities and workspace scope.
7. HUMAN approves through the normal Approval flow.
8. Observe governed ToolExecution, Observation, and Evidence updates.
9. If a real semantic failure causes Controlled Replan, verify Plan v2 stops at Waiting for Approval and ask the HUMAN to approve it; never auto-approve.
10. Review the final Conclusion and trace each Evidence item to persisted execution/observation data.
11. Reload during active work and confirm the timeline reconstructs without false success.

Dogfood must not use arbitrary shell, file editing, Git writes, automatic release actions, or credentials exposed in the UI.

## 21. Non-goals

Phase 15A does not include multi-agent collaboration, swarms, marketplaces, long-running autonomous agents, browser automation, arbitrary shell, file editing, code modification, commits, pushes, releases, GitHub write actions, memory agents, MCP expansion, agent-to-agent delegation, voice control, or a new provider architecture. It does not merge Native Localization or depend on the localization worktree; localization remains a separate product branch and acceptance gate.

## Exit criteria

- One coherent Agent Workspace exists over the existing governed runtime.
- Project + raw Goal creates exactly one Task and enters Planning visibly.
- Plan, Approval, execution, Observation, Replan, Evidence, Audit, and Report states are reconstructed from authoritative existing records.
- Rejected and failed paths never display success or execute without Approval.
- Successor Plans always require fresh Approval.
- Raw Goal and Evidence remain unchanged; no Chain-of-Thought is exposed.
- Frontend deterministic lifecycle/polling tests and existing backend security/runtime suites pass.
- No new capability, ToolGateway permission, persistence model, backend endpoint, localization dependency, or release behavior is introduced without a separately approved design change.
- HUMAN can complete the bounded dogfood scenario and inspect the final evidence-backed Report.
