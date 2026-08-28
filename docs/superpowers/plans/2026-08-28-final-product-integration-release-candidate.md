# AgentForge Final Product Integration and Release Candidate Plan

> This plan follows the HUMAN-approved release-freeze scope in
> `docs/superpowers/specs/2026-08-28-final-product-integration-release-freeze-design.md`.

**Goal:** Integrate native `en-US` / `zh-CN` localization into the current
`main` UI, preserve the Phase 15A governed Agent workflow, apply only bounded
UX fixes, clean only proven source-tree leftovers, and leave a verified main
release candidate ready for one final HUMAN test.

**Architecture:** Port the localization branch's frontend-only i18next
boundary, resources, locale persistence, status mapping, language selector,
and tests. Adapt current main components in place so the current Agent
Workspace, Agent approval routing, recovery suppression, Diagnostics, and
controlled re-planning UI remain authoritative. No backend, API, database,
Runtime, CapabilityResolver, ToolGateway, approval, or provider architecture
changes.

**Technology:** React, TypeScript, Vite, Vitest, i18next, react-i18next, Python,
FastAPI, SQLite, existing launcher.

## Global constraints

- Work only in `D:\AgentProjects\AgentForge` on `main`.
- Preserve `feature/native-localization-zh-cn`,
  `feature/repository-analyst-agent`, and the Phase 12 partial path.
- Do not blindly merge the pre-Phase-15A localization UI.
- Do not create a Task, approve a Task, call `/execute`, or mutate historical
  runtime data during implementation or automated verification.
- Do not add new product subsystems, capabilities, APIs, database tables,
  workflow states, Agent types, provider architecture, or security semantics.
- Keep runtime data, logs, PID files, evidence, and temporary output under
  `D:\AgentProjectData\AgentForge` and out of source control.
- Do not delete uncertain files. Any cleanup candidate must be reported.
- Do not push, tag, release, publish, or bump a version.

---

## Task 1: Add the approved localization boundary with TDD

**Files:**

- Create: `frontend/src/i18n/index.ts`
- Create: `frontend/src/i18n/locale.ts`
- Create: `frontend/src/i18n/status.ts`
- Create: `frontend/src/i18n/resources/en-US.ts`
- Create: `frontend/src/i18n/resources/zh-CN.ts`
- Create: `frontend/src/i18n/locale.test.ts`
- Create: `frontend/src/i18n/resources.test.ts`
- Create: `frontend/src/i18n/status.test.ts`
- Create: `frontend/src/i18n/raw-content.test.ts`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

**Contract:** Supported locales are exactly `en-US` and `zh-CN`. Resolve
`agentforge.locale` first, then a Chinese browser language, then `en-US`.
Persist only supported values. Use English fallback. Map known Task,
Approval, Execution, Provider, Health, and Risk values to translation keys;
unknown values map to a safe `Unknown` presentation without mutating the raw
value.

- [ ] Verify current Node/npm versions, the frontend-local install, and the
  configured D-drive npm cache before changing dependencies.
- [ ] Report dependency addition before installing: `i18next` for resource
  resolution and interpolation, and `react-i18next` for React context/hooks;
  use the approved versions from the localization branch and keep installation
  inside `frontend` only.
- [ ] Add the locale/resource/status tests first. Cover exact locale set,
  storage precedence, persistence, document language, matching resource keys,
  fallback, status mappings, and byte-equivalent preservation of raw paths,
  hashes, IDs, provider/model values, commands, JSON, and observation text.
- [ ] Install/update the two approved frontend dependencies with `npm.cmd`
  only after the bounded dependency report; do not use a global install.
- [ ] Implement the i18next instance, `I18nextProvider`, locale helpers, and
  complete typed resources. Keep resources in source and keep secrets out.
- [ ] Run the focused i18n tests and confirm GREEN before adapting components.
- [ ] Commit the foundation as `feat: add native frontend localization`.

## Task 2: Wire the shell and existing product pages without regressing main

**Files:**

- Create: `frontend/src/components/LanguageSelector.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Shell.tsx`
- Modify: `frontend/src/components/StatusPill.tsx`
- Modify: `frontend/src/components/Timeline.tsx`
- Modify: `frontend/src/pages/Dashboard.tsx`
- Modify: `frontend/src/pages/Projects.tsx`
- Modify: `frontend/src/pages/ProjectDetail.tsx`
- Modify: `frontend/src/pages/TaskDetail.tsx`
- Modify: `frontend/src/pages/Approvals.tsx`
- Modify: `frontend/src/pages/Diagnostics.tsx`
- Modify: `frontend/src/pages/Report.tsx`
- Create/modify focused localization tests beside these surfaces.

- [ ] Add tests for the application root's `translate="no"`, document `lang`,
  selector switching, and English reset.
- [ ] Wrap the existing App with the provider and add the shell selector;
  synchronize document language without changing routing or API calls.
- [ ] Replace authored copy with stable keys on Dashboard, Projects, Project
  Detail, Task Detail, Approvals, Diagnostics, Report, navigation, status
  pills, metrics, loading/error/empty states, and action labels.
- [ ] Keep machine facts unchanged: IDs, paths, hashes, capability/tool IDs,
  audit event IDs, provider/model identifiers, raw evidence, raw observation,
  and raw error text.
- [ ] Port the localization branch's tests only where they remain valid, then
  add current-main assertions for both locales and missing-key detection.
- [ ] Verify the Global Approval boundary remains exact: Agent-managed items
  show the safety note and `Open in Agent Workspace`; non-Agent items retain
  `Approve only`.
- [ ] Commit as `feat: localize current operations console`.

## Task 3: Localize current Phase 15A Agent surfaces

**Files:**

- Modify: `frontend/src/pages/AgentWorkspace.tsx`
- Modify: `frontend/src/components/AgentApprovalCard.tsx`
- Modify: `frontend/src/components/AgentPlanCard.tsx`
- Modify: `frontend/src/components/AgentTimeline.tsx`
- Modify: `frontend/src/components/AgentReportCard.tsx`
- Modify: `frontend/src/agent/timeline.ts` only if a presentation-key seam is
  required; never alter event facts or ordering.
- Add/modify: Agent Workspace, approval, timeline, report, and raw-content
  localization tests.

- [ ] Add RED tests for `en-US` and `zh-CN` on Agent Workspace, Goal Composer,
  Current Agent Run, Plan, Approval required, `Approve & Execute`, execution
  recovery, Timeline, Observation, Evidence-backed Report, and terminal
  status/next-action copy.
- [ ] Localize authored labels and explanations while rendering capability/tool
  identifiers and raw technical values unchanged or beside localized friendly
  labels.
- [ ] Preserve `canResumeApprovedExecution`: only an eligible approved RUNNING
  task can show recovery; SUCCESS, FAILED, and CANCELLED never show it.
- [ ] Preserve `AgentApprovalCard` exact binding and composite callback
  behavior; localization must not add approval or execution requests.
- [ ] Verify no Chain-of-Thought, raw provider output, raw tool output, or
  secret material is introduced into the UI.
- [ ] Run the focused Agent/UI tests in both locales and commit as
  `feat: localize governed agent workspace`.

## Task 4: Bounded final UX review and regression fixes

**Scope:** Agent Workspace, Dashboard, Projects, Tasks, Approvals, and
Diagnostics only. This task may modify behavior only when a deterministic test
proves an obvious acceptance issue.

- [ ] Review state/next-action clarity, heading hierarchy, timeline readability,
  approval CTA hierarchy, loading/error/empty states, and terminal presentation
  in both locales.
- [ ] Check current navigation handlers for stale Task/Project selection. If a
  real stale-selection defect is reproduced by an isolated test, fix the
  smallest handler and add the regression test; otherwise leave routing
  behavior unchanged.
- [ ] Ensure no duplicate or raw payload-wall presentation is introduced;
  technical details remain bounded and expandable only where already supported.
- [ ] Run targeted UI tests after each bounded change and commit only proven
  changes as `fix: polish release candidate operations UX` when a fix exists.
- [ ] Record larger redesign ideas as post-release backlog instead of coding
  them.

## Task 5: Audit cleanup and release-facing documentation

**Files:** Review/update only necessary release-facing files, including
`README.md`, `README_CN.md`, existing setup/start documentation, changelog or
release notes if the repository convention requires it, and relevant demo or
interview docs.

- [ ] Audit source trees for runtime DBs, logs, evidence, screenshots,
  temporary probes, debug labels, console diagnostics, and generated build
  output. Remove only artifacts proven investigation-only and disposable;
  preserve uncertain files and all durable audit/evidence data.
- [ ] Inspect `D:\AgentProjects\AgentForge\.worktrees\phase-12-real-llm-provider`
  for registration, unique files, references, and runtime pollution. Do not
  delete it solely because it is unregistered.
- [ ] Keep the Phase 15A and Native Localization worktrees intact through all
  verification; report them as cleanup candidates only after proving clean,
  fully merged, and unused.
- [ ] Update release-facing docs to describe current verified scope: Planner,
  validated Plan, Capability Resolver, HUMAN Approval, ToolGateway, governed
  execution, Observation, controlled Replan, Evidence/Audit, Report,
  Repository Analyst Agent, Diagnostics/provenance, and native `en-US` /
  `zh-CN` UI.
- [ ] Document supported provider configuration and explicitly avoid claims of
  multi-agent, RAG, MCP, arbitrary write automation, browser automation, or
  general shell autonomy.
- [ ] Commit documentation/cleanup changes as `docs: prepare agentforge release candidate`.

## Task 6: Enter release freeze and run fresh automated verification

After Tasks 1–5, accept only P0/P1 release blockers, security regressions,
data-integrity issues, broken lifecycle, broken localization, broken launcher,
or acceptance-blocking UI defects.

- [ ] Run the full frontend suite and production build from `main`.
- [ ] Run localization targeted tests: initialization, resource-key parity,
  en-US rendering, zh-CN rendering, switching, persistence, reload behavior,
  Agent Workspace, Global Approval safety, Diagnostics, terminal recovery,
  Timeline, Evidence/Report, raw-content and no-CoT checks.
- [ ] Run the full backend suite and targeted approval/orchestration,
  provenance/Diagnostics, plan-binding, duplicate/retry, controlled Replan,
  CapabilityResolver, ToolGateway, workspace containment, provider, health,
  and DB-isolation tests. No backend files should change in this effort.
- [ ] Run launcher/isolation tests, Python interpreter resolution, owned-process
  lifecycle, launcher smoke, and main-repository startup resolution.
- [ ] Run `git diff --check`, secret scan, debug marker scan, temporary
  diagnostic scan, translation missing-key scan, and source-tree runtime
  pollution scan. Redirect bulk output to
  `D:\AgentProjectData\AgentForge\runtime\logs`.
- [ ] Record exact pass counts and the one existing Starlette/httpx warning if
  it remains; do not hide failures behind a summary.
- [ ] Inspect versioning and tags. Recommend keeping `0.1.0` or the next
  logically justified candidate, but do not modify version metadata.

## Task 7: Main-repository live smoke and HUMAN final-test gate

- [ ] Identify listeners and command lines on ports 8000/5173. Stop only
  stale AgentForge-owned processes if required; never kill unrelated Python or
  Node processes.
- [ ] Start from `D:\AgentProjects\AgentForge\Start-AgentForge.bat` using the
  main repository and approved interpreter configuration. Verify backend and
  frontend source roots, main revision, one expected listener per port,
  `/health == 200`, healthy database, readable provider status, and no demo
  banner on a healthy backend.
- [ ] Read-only smoke Dashboard, Agent Workspace, Projects, Tasks, Approvals,
  and Diagnostics in both locales. Verify locale switching, reload
  persistence, no obvious console/runtime errors, and terminal recovery CTA
  suppression. Do not create or approve a Task in this autonomous pass.
- [ ] Leave only the main-owned services running for HUMAN testing and provide
  a concise 10–20 minute checklist. The HUMAN, not this pass, creates one
  appropriate Repository Analyst Task, clicks `Approve & Execute` once, and
  confirms ToolExecution, Observation, Evidence-backed Report, and durable
  Diagnostics/provenance.
- [ ] Stop at the HUMAN final-test gate. Do not release, tag, push, publish, or
  bump version after services are prepared.

## Final self-review checklist

- [ ] Current main Agent UI was never replaced by an obsolete localization
  component revision.
- [ ] Localization is frontend-only and has no backend/API/DB/security diff.
- [ ] All authored surfaces have matching en-US/zh-CN keys and raw values are
  preserved.
- [ ] Agent Approval routing and terminal recovery safety remain unchanged.
- [ ] Runtime data and historical audit/evidence were preserved.
- [ ] No new Task, manual `/execute`, remote operation, version bump, tag, or
  release occurred.
- [ ] Final report includes exact verification counts, cleanup candidates,
  main revision/source proof, and the HUMAN checklist.
