# Repository Analyst Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a first-class Repository Analyst Agent workspace that exposes the existing governed AgentForge lifecycle from Goal through Approval, Execution, Replan, Evidence, and Report.

**Architecture:** Compose existing frontend API calls and persisted operations records in one Agent workspace. Add only presentation and polling helpers; preserve the existing FastAPI Runtime, ApprovalService, AgentRuntime, ToolGateway, persistence, and security boundaries.

**Tech Stack:** React, TypeScript, Vite, existing frontend Vitest stack, existing FastAPI APIs and governed Runtime.

**Spec:** docs/superpowers/specs/2026-08-26-repository-analyst-agent-design.md

## Global Constraints

- Reuse the existing governed Runtime; never build a second runtime or duplicate persistence.
- New backend endpoints: NONE. Use existing Task, Plan, Approval, Execute, Detail, Audit, and Report APIs.
- Add no capability, arbitrary shell, file-write, Git-write, commit, push, release, GitHub-write, MCP, memory-agent, or provider architecture behavior.
- Project ID is the only workspace authority input. The LLM never chooses workspace, permissions, or tools.
- Execute only through `POST /tasks/{task_id}/execute`; frontend code never calls tools directly.
- Every successor Plan requires fresh Approval; Plan v1 Approval never authorizes Plan v2.
- Render safe structured records only. Never render Chain-of-Thought, prompts, raw provider responses, credentials, or hidden rationale.
- Preserve raw Goal, Plan technical fields, Observations, Evidence, paths, hashes, IDs, commands, JSON, and code.
- Transient `Planning...` is allowed only while the real `POST /tasks/{task_id}/plan` request is unresolved; it is not a fabricated persisted event.
- Use bounded polling only; stop at terminal Task state and clean up on unmount. Do not add WebSocket/SSE.
- Do not modify or depend on Native Localization; use existing English conventions.
- Every task uses TDD: named RED test, exact RED command, minimal implementation, exact GREEN command, logical commit.

---

### Task 1: Agent presentation contracts and capability copy

**Files:** Create `frontend/src/agent/types.ts`, `frontend/src/agent/capabilities.ts`, `frontend/src/agent/capabilities.test.ts`.

**Interfaces:** Define `AgentTimelineKind` with `GOAL_RECEIVED`, `PLANNING`, `PLAN_CREATED`, `WAITING_APPROVAL`, `APPROVED`, `APPROVAL_REJECTED`, `STEP_STARTED`, `TOOL_EXECUTION_COMPLETED`, `OBSERVATION_RECORDED`, `STEP_FAILED`, `REPLANNING`, `SUCCESSOR_PLAN_CREATED`, `COMPLETED`, `FAILED`; define `AgentTimelineEntry = { id: string; kind: AgentTimelineKind; timestamp: string; planVersion?: number; stepId?: string; status: string; summary: string; raw?: Record<string, unknown> }`; export a pure capability presentation map.

- [ ] Write tests proving `repository_state`, `project_metadata`, and `test_verification` map to `Read repository status`, `Read project metadata`, and `Run project tests`, including explanations that shell is not granted; unknown IDs remain technical.
- [ ] Run `cd frontend; npx vitest run src/agent/capabilities.test.ts`; expect RED because the files do not exist.
- [ ] Implement only the types and static presentation map; do not alter resolver or API values.
- [ ] Run the same command; expect GREEN.
- [ ] Commit `git add frontend/src/agent; git commit -m "feat: add agent workspace presentation contracts"`.

### Task 2: Authoritative timeline projection

**Files:** Create `frontend/src/agent/timeline.ts`, `frontend/src/agent/timeline.test.ts`; modify `frontend/src/types/index.ts` only if an already-returned API field is absent from a type.

**Interfaces:** Export `AgentTimelineInput = { detail: TaskDetail; report: Report; pendingApproval?: ApprovalQueueItem; transientPlanning?: boolean }` and `buildAgentTimeline(input: AgentTimelineInput): AgentTimelineEntry[]`.

**Source mapping:** `TASK_CREATED`/Task `created_at` -> `GOAL_RECEIVED`; transient flag -> transient `PLANNING`; `PLAN_CREATED`/Plan timestamp -> `PLAN_CREATED`; pending Approval or Task `WAITING_APPROVAL` -> `WAITING_APPROVAL`; Approval decisions -> `APPROVED`/`APPROVAL_REJECTED`; terminal ToolExecution -> completion/failure; `RUNTIME_OBSERVATION` -> `OBSERVATION_RECORDED`; `REPLAN_REQUESTED` -> `REPLANNING`; `PLAN_VERSION_CREATED` -> `SUCCESSOR_PLAN_CREATED`; terminal Task state -> `COMPLETED`/`FAILED`. Sort by timestamp, then persisted order and stable source ID. Never infer success from missing errors.

- [ ] Write tests for all mappings, equal-timestamp ordering, transient-versus-persisted Planning, Plan v1/v2 lineage, fresh pending successor Approval, terminal failure, unknown audit events, and exclusion of reasoning/prompt/provider-thinking fields.
- [ ] Run `cd frontend; npx vitest run src/agent/timeline.test.ts`; expect RED because the projection does not exist.
- [ ] Implement the pure projection from existing Task Detail, Report, Approval, Execution, Evidence, and Audit fields only.
- [ ] Run the same command; expect GREEN.
- [ ] Commit `git add frontend/src/agent/timeline.ts frontend/src/agent/timeline.test.ts frontend/src/types/index.ts; git commit -m "feat: project persisted agent timeline"`.

### Task 3: Add the real Planner API client method

**Files:** Modify `frontend/src/api/client.ts`; create `frontend/src/api/client.plan.test.ts`.

**Real contract:** `backend/app/api/routes/planning.py` exposes `POST /tasks/{task_id}/plan`. The request body is `{ context?: Record<string, unknown> }` from `PlanRequest`; the response is `PlanRead` with `id: string`, `task_id: string`, `version: number`, `plan_json: Record<string, unknown>`, and `validation_status: string`. The backend invokes `PlannerAgent.create_plan`, which transitions `CREATED -> PLANNING -> WAITING_APPROVAL` on success, runs Plan Validation and Capability Resolver, and creates no Approval itself. Provider failures map to HTTP 503/429/504/502; invalid response, validation, resolution, and other value failures map to HTTP 400 with `LLM planning failed: INVALID_RESPONSE`; the existing `request<T>` helper propagates these response details as `Error`.

**Interface:** Add `api.createPlan(taskId: string, context: Record<string, unknown> = {}): Promise<Plan>` using `POST /tasks/${taskId}/plan` and JSON `{ context }`. Use the existing frontend `Plan` type and do not invent response fields.

- [ ] Write RED tests proving the API client currently has no supported planning method, then proving the expected request contract and response fixture.
- [ ] Run `cd frontend; npx vitest run src/api/client.plan.test.ts`; expect RED because `api.createPlan` is absent.
- [ ] Implement exactly one POST to `/tasks/{taskId}/plan`, with `{ context }`, returning the real `PlanRead` response and propagating non-2xx errors through `request<T>`.
- [ ] Run the same command; expect GREEN and assert exact task ID propagation.
- [ ] Commit `git add frontend/src/api/client.ts frontend/src/api/client.plan.test.ts; git commit -m "feat: call governed planning endpoint"`.

### Task 4: Agent route and Goal Composer

**Files:** Modify `frontend/src/components/Shell.tsx` and `frontend/src/App.tsx`; create `frontend/src/pages/AgentWorkspace.tsx` and `frontend/src/pages/AgentWorkspace.test.tsx`; modify `frontend/src/api/client.ts` only if an existing method is missing.

**Interfaces:** Add `agent` to the existing `Page` union. `AgentWorkspace` receives existing Project/Task/Detail/Report/Approval data and callbacks. Goal submission calls existing `api.createTask({ project_id, title, goal })` exactly once and preserves raw Goal; it does not display a Plan or Approval until the authoritative planning request resolves.

- [ ] Write RED tests for Agent navigation, empty state, active Project selector, Goal input, required fields, exact raw Goal, duplicate-submit prevention, and transient `Planning...` while the create/plan sequence is unresolved; assert no fake Audit record, Plan, or Approval is created by the frontend.
- [ ] Run `cd frontend; npx vitest run src/pages/AgentWorkspace.test.tsx`; expect RED because route/component are absent.
- [ ] Add one coherent Agent page without replacing admin pages. Use selected Project ID and existing Task creation; keep transient Planning in React state only.
- [ ] Run the same command; expect GREEN.
- [ ] Commit `git add frontend/src/components/Shell.tsx frontend/src/App.tsx frontend/src/pages/AgentWorkspace.tsx frontend/src/pages/AgentWorkspace.test.tsx frontend/src/api/client.ts; git commit -m "feat: add repository analyst agent workspace"`.

### Task 5: Task creation -> real planning orchestration and authoritative refresh

**Files:** Modify `frontend/src/hooks/useOperations.ts`; modify `frontend/src/api/client.ts` and `frontend/src/types/index.ts` only for existing contracts; create `frontend/src/hooks/useOperations.agent.test.tsx`.

**Interfaces:** Preserve existing hook exports. Add `createAgentTask(projectId: string, goal: string): Promise<TaskSummary>` and `createPlan(taskId: string, context?: Record<string, unknown>): Promise<Plan>` plus `refreshTask(taskId: string): Promise<void>`. `createAgentTask` performs exactly: `api.createTask` -> receive `task.id` -> `api.createPlan(task.id)` -> refresh detail/report/pending Approvals. It must not call execute. `refreshTask` reads detail/report/pending Approvals without mutating the backend.

- [ ] Write RED tests for exact Project/Goal payload, one Task create call, then exactly one `/tasks/{task_id}/plan` call using the returned Task ID, real Plan response, authoritative detail/Approval refresh, and network/provider/400 planning failure retaining the created Task without fabricating Plan or Approval. Assert create failure never calls `/plan`, wrong Task IDs are impossible, and successful planning still makes zero execute calls before Approval.
- [ ] Run `cd frontend; npx vitest run src/hooks/useOperations.agent.test.tsx`; expect RED because callbacks are absent.
- [ ] Implement composition over `api.createTask`, `api.createPlan`, `api.getTaskDetail`, `api.getReport`, and `api.getPendingApprovals`; expose transient Planning only while `/plan` is unresolved. A `/plan` failure shows truthful request/backend error and leaves Plan/Approval absent; do not add a facade endpoint, replicate validation/resolution, or make a direct execution call.
- [ ] Run `cd frontend; npx vitest run src/hooks/useOperations.agent.test.tsx src/pages/AgentWorkspace.test.tsx src/api/client.plan.test.ts`; expect GREEN.
- [ ] Commit `git add frontend/src/hooks/useOperations.ts frontend/src/api/client.ts frontend/src/types/index.ts frontend/src/hooks/useOperations.agent.test.tsx frontend/src/pages/AgentWorkspace.test.tsx; git commit -m "feat: compose agent task lifecycle state"`.

### Task 6: Bounded active-task polling

**Files:** Create `frontend/src/agent/polling.ts`, `frontend/src/agent/polling.test.ts`; modify `frontend/src/pages/AgentWorkspace.tsx` and `frontend/src/hooks/useOperations.ts`.

**Interfaces:** Export `isTerminalTaskStatus(status: string): boolean` for `SUCCESS`, `FAILED`, `CANCELLED`; export `useAgentTaskPolling(taskId: string | undefined, status: string | undefined, refresh: (taskId: string) => Promise<void>, intervalMs?: number): { polling: boolean; refreshError: string | null }`.

- [ ] Write fake-timer RED tests for active polling, terminal stop, unmount cleanup, transient network error retention, active reload resume, one in-flight refresh, and proof that polling never invokes approve/execute.
- [ ] Run `cd frontend; npx vitest run src/agent/polling.test.ts`; expect RED because helper/hook is absent.
- [ ] Implement bounded polling of detail/report/approval resources only; ignore stale responses after Task selection changes.
- [ ] Run `cd frontend; npx vitest run src/agent/polling.test.ts src/pages/AgentWorkspace.test.tsx`; expect GREEN.
- [ ] Commit `git add frontend/src/agent/polling.ts frontend/src/agent/polling.test.ts frontend/src/pages/AgentWorkspace.tsx frontend/src/hooks/useOperations.ts; git commit -m "feat: poll active agent tasks safely"`.

### Task 7: Governed Plan and Approval cards

**Files:** Create `frontend/src/components/AgentPlanCard.tsx`, `frontend/src/components/AgentApprovalCard.tsx`, `frontend/src/components/AgentApprovalCard.test.tsx`; modify `frontend/src/pages/AgentWorkspace.tsx` and `frontend/src/hooks/useOperations.ts`.

**Interfaces:** `AgentPlanCard({ plan, rawGoal }: { plan: Plan; rawGoal: string })` renders the actual Plan version, steps, IDs, parameters, summary, and authority. `AgentApprovalCard({ item, onApprove, onReject }: { item: ApprovalQueueItem; onApprove: (approvalId: string) => Promise<void>; onReject: (approvalId: string, reason: string) => Promise<void> })` renders capability copy, risk/scope, and gated actions.

- [ ] Write RED tests for actual Plan rendering, friendly capability descriptions, canonical IDs, selected workspace, no-shell statement, pending actions, rejection with no execution call, no-Approval with no execution action, and approved action using only existing Approval/Execute endpoints.
- [ ] Run `cd frontend; npx vitest run src/components/AgentApprovalCard.test.tsx`; expect RED because cards are absent.
- [ ] Implement presentation-only cards. Show Execute only for authoritative approved current Plan and invoke `POST /tasks/{task_id}/execute` once per explicit action.
- [ ] Run `cd frontend; npx vitest run src/components/AgentApprovalCard.test.tsx src/pages/AgentWorkspace.test.tsx`; expect GREEN.
- [ ] Commit `git add frontend/src/components/AgentPlanCard.tsx frontend/src/components/AgentApprovalCard.tsx frontend/src/components/AgentApprovalCard.test.tsx frontend/src/pages/AgentWorkspace.tsx frontend/src/hooks/useOperations.ts; git commit -m "feat: present governed agent plan and approval"`.

### Task 8: Timeline and governed execution view

**Files:** Create `frontend/src/components/AgentTimeline.tsx`, `frontend/src/components/AgentTimeline.test.tsx`; modify `frontend/src/pages/AgentWorkspace.tsx`.

**Interface:** `AgentTimeline({ entries }: { entries: AgentTimelineEntry[] })` renders the projection in order, showing plan versions, step IDs, safe status labels, ToolExecution, Observation, and Evidence references without object serialization.

- [ ] Write RED tests for Goal, Plan, Approval, execution success/failure, Observation, Replanning, successor Plan, and terminal entries; assert reasoning, thinking, prompts, credentials, and provider hidden fields are absent.
- [ ] Run `cd frontend; npx vitest run src/components/AgentTimeline.test.tsx`; expect RED because component is absent.
- [ ] Implement the safe timeline view over `buildAgentTimeline`; raw technical values remain in separate detail text.
- [ ] Run `cd frontend; npx vitest run src/components/AgentTimeline.test.tsx src/agent/timeline.test.ts src/pages/AgentWorkspace.test.tsx`; expect GREEN.
- [ ] Commit `git add frontend/src/components/AgentTimeline.tsx frontend/src/components/AgentTimeline.test.tsx frontend/src/pages/AgentWorkspace.tsx; git commit -m "feat: show governed agent execution timeline"`.

### Task 9: Evidence-backed Report card

**Files:** Create `frontend/src/components/AgentReportCard.tsx`, `frontend/src/components/AgentReportCard.test.tsx`; modify `frontend/src/pages/AgentWorkspace.tsx`.

**Interface:** `AgentReportCard({ report, detail }: { report: Report; detail: TaskDetail })` renders Conclusion from Report readiness/summary and Evidence from persisted Evidence records, linking execution/observation references only where available.

- [ ] Write RED tests for PASS/FAIL/PENDING distinction, unchanged raw Evidence summary/path/hash, unavailable Evidence, failed execution not appearing all-success, and no fabricated conclusion.
- [ ] Run `cd frontend; npx vitest run src/components/AgentReportCard.test.tsx`; expect RED because component is absent.
- [ ] Implement composition over existing Report and Task Detail responses; do not add a report model or infer evidence.
- [ ] Run `cd frontend; npx vitest run src/components/AgentReportCard.test.tsx src/pages/AgentWorkspace.test.tsx`; expect GREEN.
- [ ] Commit `git add frontend/src/components/AgentReportCard.tsx frontend/src/components/AgentReportCard.test.tsx frontend/src/pages/AgentWorkspace.tsx; git commit -m "feat: show evidence-backed agent report"`.

### Task 10: Reload reconstruction, failure paths, and fresh successor Approval

**Files:** Modify `frontend/src/pages/AgentWorkspace.test.tsx`, `frontend/src/agent/timeline.test.ts`, `frontend/src/agent/polling.test.ts`, and `frontend/src/hooks/useOperations.agent.test.tsx`.

- [ ] Add RED fixtures/tests for planner/provider failure, invalid Plan, resolver failure, rejected Approval, execute failure, semantic Tool failure, Replan/step limits, Replan provider failure, terminal failure, refresh/report failure, and active navigation. The planning failures must assert no fake `PLAN_CREATED`/`WAITING_APPROVAL`, no Approval, and zero execute calls.
- [ ] Add a remount test that discards React timeline state, reloads existing detail/audit/report/Approval responses, and reconstructs equivalent meaningful entries. Add a Replan fixture proving v1 Approval is not reused and v2 pending Approval is shown.
- [ ] Run `cd frontend; npx vitest run src/pages/AgentWorkspace.test.tsx src/agent/timeline.test.ts src/agent/polling.test.ts src/hooks/useOperations.agent.test.tsx`; expect RED before handling is implemented.
- [ ] Implement bounded refresh-error UI that retains last known authoritative state, resumes active polling after remount, selects highest persisted Plan version deterministically, and stops at fresh Approval for a successor.
- [ ] Run the same command; expect GREEN.
- [ ] Commit `git add frontend/src/pages/AgentWorkspace.test.tsx frontend/src/agent/timeline.test.ts frontend/src/agent/polling.test.ts frontend/src/hooks/useOperations.agent.test.tsx; git commit -m "test: cover agent recovery and approval boundaries"`.

### Task 11: Full regression, scope review, and HUMAN dogfood readiness

**Files:** Modify only bounded Phase 15A frontend files if a verification failure proves a defect; do not modify backend production authority. Tests use existing `backend/tests` and frontend tests.

- [ ] Run the full frontend suite and build: `cd frontend; npm run test -- --run; npm run build`.
- [ ] Run backend full suite, DB isolation, governance/security, diagnostics, and launcher regression using the repository Python: `D:\AgentProjects\AgentForge\backend\.venv\Scripts\python.exe -m pytest backend\tests -q`, `D:\AgentProjects\AgentForge\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_test_database_isolation.py -q`, `D:\AgentProjects\AgentForge\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_workspace_security.py backend\tests\test_phase_13_diagnostics.py -q`, and `D:\AgentProjects\AgentForge\backend\.venv\Scripts\python.exe -m pytest tests\test_launcher_process_lifecycle.py tests\test_launcher_controller.py backend\tests\test_launcher_python_selection.py -q`.
- [ ] Run Provider/Diagnostics regression, launcher smoke `.\launcher\start_agentforge.ps1 -ResolvePythonOnly`, `git diff --check`, and the existing bounded secret scan. Do not print credentials; verify no `.env` or runtime data is tracked.
- [ ] Review `git diff` and bounded `rg` to prove no new backend endpoint, capability, persistence, authority change, ToolGateway bypass, CoT rendering, localization dependency, or runtime duplication exists. Every timeline event must map to persisted evidence or explicitly be transient request state.
- [ ] Prepare but do not auto-run HUMAN dogfood: select active AgentForge Project; submit exact Goal; verify `POST /tasks` returns a real Task ID; verify `POST /tasks/{id}/plan` runs the real Planner and returns a real Plan; verify authoritative Approval appears; HUMAN approves; invoke `POST /tasks/{id}/execute`; inspect ToolExecutions, Observations, Report, and Evidence; if natural Replan reaches `WAITING_APPROVAL`, stop for HUMAN approval.
- [ ] Invoke `superpowers:verification-before-completion` before any completion claim and `superpowers:finishing-a-development-branch` only after all tests pass; preserve branch/worktree unless separately authorized. Do not merge, push, tag, release, bump version, or touch Native Localization.
- [ ] Commit only a bounded final test correction if required: `git add frontend/src; git commit -m "test: verify repository analyst agent boundaries"`; otherwise do not create an empty commit.

## Self-review checklist

- [ ] Every spec requirement maps to Tasks 1-10.
- [ ] All paths and APIs named above exist in the current repository or are explicitly new frontend files.
- [ ] No placeholder or silent backend endpoint expansion exists.
- [ ] Timeline source, timestamp, ordering, and failure rules are explicit.
- [ ] Every lifecycle arrow is covered: Project + Goal -> Task -> real planning endpoint -> Planner/Validation/Resolver -> Plan -> Approval -> governed Execute -> ToolExecution/Observation -> Replan/fresh Approval -> Evidence -> Report.
- [ ] Planning API request/response/error contract and exact Task ID propagation are explicit.
- [ ] Transient Planning is separate from persisted timeline records.
- [ ] Fresh successor Approval, reload reconstruction, terminal polling stop, raw-content preservation, and no-CoT tests are explicit.
- [ ] No Runtime, Approval, Project Authority, Capability Resolver, ToolGateway, execution, DB, or Replan policy authority changes are planned.
- [ ] HUMAN dogfood and final acceptance remain separate gates.
