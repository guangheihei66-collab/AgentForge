# Native Localization zh-CN Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add first-party en-US and zh-CN localization to the AgentForge frontend without changing backend/runtime semantics or translating raw user/runtime content.

**Architecture:** Use i18next/react-i18next as a frontend-only localization boundary, persist explicit locale selection in localStorage, centralize canonical status-to-translation-key mapping, and protect React-managed UI from browser machine translation.

**Tech Stack:** React, TypeScript, Vite, i18next, react-i18next, existing frontend test stack.

**Spec:** docs/superpowers/specs/2026-08-25-native-localization-zh-cn-design.md

## Global Constraints

- Support exactly `en-US` and `zh-CN`; reject other stored values.
- Resolve locale in order: explicit `agentforge.locale`, browser `zh*`, then `en-US`.
- Do not change backend/API/database canonical values or Runtime authority.
- Do not translate user/runtime content: goals, names, evidence, observations, errors, paths, SHAs, model/provider IDs, capability/tool IDs, commands, JSON, or code.
- Use human-written product copy and one consistent terminology glossary.
- Add only `i18next` and `react-i18next`; do not add a browser-language detector.
- Set `document.documentElement.lang` and React root `translate="no"`.
- Every behavior change follows RED, verify RED, minimal implementation, GREEN, regression, commit.
- Do not base implementation on `D:\AgentProjects\AgentForge\.worktrees\v0.1.1-provider-connection-status`.
- Implementation must branch later from a clean, then-current `main` after HUMAN resolves the Provider hotfix.
- Do not version-bump, merge, push, tag, or release.

## Current Frontend Map

- Bootstrap: `frontend/src/main.tsx`.
- Root layout and page routing: `frontend/src/App.tsx`.
- Global header, sidebar, navigation, health/operator chrome: `frontend/src/components/Shell.tsx`.
- Dashboard and shared `PanelTitle`/`Empty`: `frontend/src/pages/Dashboard.tsx`.
- Provider UI: Dashboard Provider panel plus `frontend/src/api/client.ts`, `frontend/src/hooks/useOperations.ts`, and `frontend/src/types/index.ts`.
- Projects/forms: `frontend/src/pages/Projects.tsx`, `frontend/src/pages/ProjectDetail.tsx`.
- Task detail, plan, execution, evidence, audit: `frontend/src/pages/TaskDetail.tsx`, `frontend/src/components/Timeline.tsx`.
- Approval queue and permissions: `frontend/src/pages/Approvals.tsx`.
- Report/evidence/audit summaries: `frontend/src/pages/Report.tsx`.
- Diagnostics/health/provider metadata: `frontend/src/pages/Diagnostics.tsx`.
- Status/risk/permission pills: `frontend/src/components/StatusPill.tsx`.
- Existing tests: `frontend/src/App.test.tsx`, `frontend/src/pages/Diagnostics.test.tsx`; setup: `frontend/src/test/setup.ts`.
- Dependency manifest and commands: `frontend/package.json`; test `npm run test -- --run`, build `npm run build`.

## Planned Files and Interfaces

Create:

- `frontend/src/i18n/locale.ts`: `Locale`, `SUPPORTED_LOCALES`, `LOCALE_STORAGE_KEY`, `resolveLocale(storage, browserLanguage)`, `persistLocale(locale, storage)`, and `setDocumentLocale(locale)`.
- `frontend/src/i18n/resources/en-US.ts`: complete English resource object.
- `frontend/src/i18n/resources/zh-CN.ts`: same-shaped human-written Simplified Chinese resource object.
- `frontend/src/i18n/index.ts`: i18next initialization and React provider exports.
- `frontend/src/i18n/status.ts`: canonical status unions/maps and `statusKey(...)` helpers.
- `frontend/src/components/LanguageSelector.tsx`: accessible selector consuming i18next language state.
- `frontend/src/i18n/*.test.tsx` or `.test.ts`: focused localization tests following existing Vitest conventions.

Modify only the listed frontend components during implementation, plus `frontend/package.json` and its lockfile if the repository has one. Do not modify backend files, API schemas, database code, Runtime, ToolGateway, or Provider hotfix files.

---

### Task 1: Locale infrastructure

**Files:** Create `frontend/src/i18n/locale.ts`, `frontend/src/i18n/locale.test.ts`; modify `frontend/package.json` and the existing package lockfile if present.

**Interfaces:** `resolveLocale(storage: StorageLike, browserLanguage: string | undefined): Locale`; `persistLocale(locale: Locale, storage: StorageLike): void`; `setDocumentLocale(locale: Locale): void`.

- [ ] **Step 1: Write RED tests** for non-Chinese fallback, `zh-CN`/`zh-TW`/`zh` detection, explicit valid preference override, invalid preference fallback, persistence, and document language.
- [ ] **Step 2: Run** `npm run test -- --run src/i18n/locale.test.ts`; expect failure because the module does not exist.
- [ ] **Step 3: Add `i18next` and `react-i18next` only**, then implement the pure resolution/persistence functions with exact `en-US`/`zh-CN` validation and non-throwing storage handling.
- [ ] **Step 4: Run** the targeted test; expect all locale tests PASS.
- [ ] **Step 5: Commit** `feat: add locale resolution infrastructure`.

### Task 2: i18next initialization and typed resources

**Files:** Create `frontend/src/i18n/index.ts`, `frontend/src/i18n/resources/en-US.ts`, `frontend/src/i18n/resources/zh-CN.ts`, and `frontend/src/i18n/resources/resources.test.ts`.

**Interfaces:** `resources` contains exactly `en-US` and `zh-CN`; `I18nProvider` wraps React children; both resource objects have the same key shape.

- [ ] **Step 1: Write RED tests** asserting both locales exist, resource key sets are equal, English fallback is configured, and a missing key returns deterministic English fallback without throwing.
- [ ] **Step 2: Run** `npm run test -- --run src/i18n/resources.test.ts`; expect failure.
- [ ] **Step 3: Implement the i18next instance with `fallbackLng: 'en-US'`, typed resources, and the approved key families: common, shell, navigation, dashboard, projects, tasks, approvals, evidence, audit, reports, diagnostics, provider, and status.
- [ ] **Step 4: Run** the targeted test; expect PASS and no additional language.
- [ ] **Step 5: Commit** `feat: initialize native localization resources`.

### Task 3: Root metadata and browser-translation isolation

**Files:** Modify `frontend/src/main.tsx`, `frontend/src/App.tsx`; create/update `frontend/src/App.localization.test.tsx`.

**Interfaces:** Root React tree is wrapped by `I18nProvider`; application-controlled root receives `translate="no"`; locale changes call `setDocumentLocale`.

- [ ] **Step 1: Write RED tests** rendering the real App path and asserting `translate="no"`, initial `document.documentElement.lang`, and language metadata changes after locale switch.
- [ ] **Step 2: Run** `npm run test -- --run src/App.localization.test.tsx`; expect failure.
- [ ] **Step 3: Add the provider/root boundary and a single locale synchronization effect; never add `_mstmutation` logic or browser-specific translator code.
- [ ] **Step 4: Run targeted tests and `npm run build`; expect PASS.
- [ ] **Step 5: Commit** `feat: isolate native UI from browser translation`.

### Task 4: Language selector and runtime switching

**Files:** Create `frontend/src/components/LanguageSelector.tsx`, `frontend/src/components/LanguageSelector.test.tsx`; modify `frontend/src/components/Shell.tsx`.

**Interfaces:** Selector exposes an accessible label and two options, calls `i18n.changeLanguage(locale)`, persists the exact locale, and does not reload or navigate.

- [ ] **Step 1: Write RED tests** for English render, Chinese render, both switch directions, explicit persistence after remount, keyboard-accessible control, and no navigation/reload calls.
- [ ] **Step 2: Run** `npm run test -- --run src/components/LanguageSelector.test.tsx`; expect failure.
- [ ] **Step 3: Implement the compact header selector near operator/account controls using `useTranslation`; use approved copy such as `中文 | English` without locale ternaries in pages.
- [ ] **Step 4: Run targeted tests and verify `document.documentElement.lang`; expect PASS.
- [ ] **Step 5: Commit** `feat: add application language selector`.

### Task 5: Central canonical status localization

**Files:** Create `frontend/src/i18n/status.ts`, `frontend/src/i18n/status.test.ts`; modify `frontend/src/components/StatusPill.tsx` and `frontend/src/components/Timeline.tsx`.

**Interfaces:** `taskStatusKey(status: TaskStatus | string)`, `approvalStatusKey(status: string)`, `executionStatusKey(status: string)`, `providerStatusKey(status: ProviderConnectionStatus | string)`, `healthStatusKey(status: HealthState | string)`, and `riskKey(status: string)` return translation keys and deterministic unknown fallbacks. Inputs are never mutated.

- [ ] **Step 1: Write RED tests** for `SUCCESS`, `FAILED`, `REJECTED`, `WAITING_APPROVAL`, execution states, Provider `not tested`/`success`/`failed`, all health states, risks, and unknown values in both locales.
- [ ] **Step 2: Run** `npm run test -- --run src/i18n/status.test.ts`; expect failure.
- [ ] **Step 3: Implement exhaustive maps against actual unions in `frontend/src/types/index.ts`; make `StatusPill`/`Timeline` call `t(map(...))` while retaining canonical class/logic values.
- [ ] **Step 4: Run targeted tests; expect canonical inputs unchanged and localized output PASS.
- [ ] **Step 5: Commit** `feat: centralize localized status presentation`.

### Task 6: Global shell and shared copy

**Files:** Modify `frontend/src/components/Shell.tsx`, `frontend/src/App.tsx`, `frontend/src/pages/Dashboard.tsx` shared `PanelTitle`/`Empty` paths; extend shell/localization tests.

- [ ] **Step 1: Write RED tests** for navigation, header, sidebar, system health, operator, loading, error, empty, and action copy in both locales.
- [ ] **Step 2: Run** `npm run test -- --run src/components/Shell.test.tsx src/App.localization.test.tsx`; expect failures for untranslated strings.
- [ ] **Step 3: Move only product-authored strings to resource keys; keep task/user/runtime values as interpolated variables and preserve existing page routing.
- [ ] **Step 4: Run targeted tests; expect English compatibility and Chinese copy PASS.
- [ ] **Step 5: Commit** `feat: localize global application shell`.

### Task 7: Dashboard and Provider presentation

**Files:** Modify `frontend/src/pages/Dashboard.tsx`; extend `frontend/src/App.test.tsx` with localization cases.

- [ ] **Step 1: Write RED tests** for all Dashboard chrome, metric labels, task/approval/risk labels, and Provider states. Assert exact Chinese: `尚未测试连接`, `连接成功`, `连接失败`; assert provider/model identifiers remain unchanged.
- [ ] **Step 2: Run** `npm run test -- --run src/App.test.tsx`; expect failures for Chinese rendering.
- [ ] **Step 3: Replace authored literals with `t(...)` and centralized status helpers; do not change Provider API calls or state ownership.
- [ ] **Step 4: Run the existing Provider race regression plus localization cases; expect PASS.
- [ ] **Step 5: Commit** `feat: localize dashboard and provider states`.

### Task 8: Projects and Project Detail

**Files:** Modify `frontend/src/pages/Projects.tsx`, `frontend/src/pages/ProjectDetail.tsx`; extend App/page tests.

- [ ] **Step 1: Write RED tests** for headings, forms, actions, empty/error/status copy in both locales, while asserting project names, workspace paths, capability IDs, task titles, and goals are unchanged.
- [ ] **Step 2: Run** `npm run test -- --run src/App.test.tsx`; expect failures.
- [ ] **Step 3: Localize authored labels and explanatory copy; interpolate raw project/task values unchanged and keep capability IDs canonical.
- [ ] **Step 4: Run targeted tests; expect PASS.
- [ ] **Step 5: Commit** `feat: localize project surfaces`.

### Task 9: Tasks, plans, executions, evidence, and audit

**Files:** Modify `frontend/src/pages/TaskDetail.tsx`, `frontend/src/components/Timeline.tsx`; extend App tests for raw-content preservation.

- [ ] **Step 1: Write RED tests** for task headings, plan/execution/evidence/audit chrome and localized canonical statuses. Include exact unchanged assertions for Goal, evidence content, paths, SHA, model, capability/tool IDs, command output, JSON/code, observation and audit payloads.
- [ ] **Step 2: Run** `npm run test -- --run src/App.test.tsx`; expect failures.
- [ ] **Step 3: Translate authored labels through resources and status helpers only; never pass raw values through translation keys.
- [ ] **Step 4: Run targeted tests in both locales; expect byte/text-equivalent raw values and localized chrome PASS.
- [ ] **Step 5: Commit** `feat: localize task evidence and audit surfaces`.

### Task 10: Approvals and terminology distinction

**Files:** Modify `frontend/src/pages/Approvals.tsx`; extend page tests.

- [ ] **Step 1: Write RED tests** proving Approval entity is `审批`, Approve action is `批准`, Reject is `拒绝`, waiting state is `等待审批`, and canonical capability IDs/permission values remain unchanged.
- [ ] **Step 2: Run** `npm run test -- --run src/Approvals.test.tsx`; expect failure if the new test file is added.
- [ ] **Step 3: Localize queue, actions, risk, plan, security explanations, and empty/error copy with the glossary terms.
- [ ] **Step 4: Run targeted tests; expect PASS and no API payload changes.
- [ ] **Step 5: Commit** `feat: localize approval workflow copy`.

### Task 11: Reports

**Files:** Modify `frontend/src/pages/Report.tsx`; extend/create `frontend/src/pages/Report.test.tsx`.

- [ ] **Step 1: Write RED tests** for readiness, pass/fail, evidence, audit, execution, summary, and empty copy in both locales; assert summary, evidence content, hashes, and task title remain unchanged.
- [ ] **Step 2: Run** `npm run test -- --run src/pages/Report.test.tsx`; expect failure.
- [ ] **Step 3: Localize only authored report chrome and status presentation.
- [ ] **Step 4: Run targeted tests; expect PASS.
- [ ] **Step 5: Commit** `feat: localize readiness reports`.

### Task 12: Diagnostics

**Files:** Modify `frontend/src/pages/Diagnostics.tsx`; update `frontend/src/pages/Diagnostics.test.tsx`.

- [ ] **Step 1: Write RED tests** for loading/error labels, HEALTHY/DEGRADED/UNHEALTHY/UNKNOWN presentation, backend/database/provider labels, version/revision labels, credentials, and preserved provider/model/revision values.
- [ ] **Step 2: Run** `npm run test -- --run src/pages/Diagnostics.test.tsx`; expect failures.
- [ ] **Step 3: Use centralized health mapping and localized labels while leaving canonical health values and diagnostic payload untouched.
- [ ] **Step 4: Run targeted tests; expect PASS with existing secret non-rendering assertion retained.
- [ ] **Step 5: Commit** `feat: localize diagnostics`.

### Task 13: Copy coverage and hard-coded string audit

**Files:** Modify only missed targeted UI files identified by the audit; add a bounded frontend test or script only if it can reliably distinguish product copy from raw content.

- [ ] **Step 1: Enumerate authored literals** with `rg` over `frontend/src`, classify each as product copy or explicitly exempt raw/runtime content, and record no broad auto-rewrite.
- [ ] **Step 2: Write RED coverage assertions** for every missed authored surface and run the smallest affected test files.
- [ ] **Step 3: Move missed authored strings to existing resource namespaces; do not translate identifiers or raw values.
- [ ] **Step 4: Run the bounded audit and targeted tests; expect no unapproved hardcoded English in targeted chrome.
- [ ] **Step 5: Commit** `refactor: complete localization copy coverage`.

### Task 14: Full frontend regression and build

**Files:** No new product files unless a failed test identifies a concrete gap.

- [ ] **Step 1: Run** `npm run test -- --run` and capture bounded output; require all targeted localization, Provider, Diagnostics, and existing tests PASS.
- [ ] **Step 2: Run** `npm run build`; require TypeScript/Vite production build PASS.
- [ ] **Step 3: Run a repeated deterministic Provider/status test command where supported; require no flaky outcome.
- [ ] **Step 4: Run `git diff --check` and inspect `git diff` for backend/runtime/API changes.
- [ ] **Step 5: Commit** `test: verify native localization frontend regression` only if this task introduced test-only changes; otherwise do not create an empty commit.

### Task 15: Backend, governance, isolation, and secret non-regression

**Files:** No backend source changes permitted.

- [ ] **Step 1: Run** the shared supported interpreter command `D:\AgentProjects\AgentForge\backend\.venv\Scripts\python.exe -m pytest backend\tests -q`; require full backend PASS.
- [ ] **Step 2: Run** `D:\AgentProjects\AgentForge\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_test_database_isolation.py -q`; require isolation PASS.
- [ ] **Step 3: Run** the established focused governance/security set covering capability governance, Provider safety, controlled replan, project authority, workspace security, approval workflow, AgentRuntime, and ToolExecution; require PASS.
- [ ] **Step 4: Query `/health`, `/llm/provider`, and `/diagnostics` without printing credentials; prove localization did not change Provider/API authority or canonical values.
- [ ] **Step 5: Run a bounded secret scan excluding external runtime data; confirm no `.env.local`, API key, authorization value, SQLite/runtime data, debug trace, or build junk is staged.
- [ ] **Step 6: Commit no backend changes; record the non-regression evidence in the final report.

### Task 16: Launcher and HUMAN browser acceptance

**Files:** No product source changes; verification artifacts remain outside the repository.

- [ ] **Step 1: Run the supported launcher from the implementation worktree/configuration and verify startup diagnostics, backend health, frontend health, and diagnostics without exposing secrets.
- [ ] **Step 2: HUMAN selects English and verifies Dashboard, Projects, Tasks, Approvals, Evidence, Audit, Reports, and Diagnostics are English.
- [ ] **Step 3: HUMAN selects `中文` without reload and verifies the same pages are native Simplified Chinese; then switches back to English without reload.
- [ ] **Step 4: HUMAN reloads/revisits and verifies the explicit locale persists; verify `document.documentElement.lang` and application root `translate="no"` in DOM.
- [ ] **Step 5: HUMAN performs the Provider Chinese scenario from clean `not tested`: click once, observe `连接成功` immediately, wait ten seconds, verify it remains, with no navigation/reload and no machine translation.
- [ ] **Step 6: Record actual HUMAN results; any failure keeps the implementation candidate `NO`.

### Task 17: Final verification and branch handoff

**Files:** No implementation changes unless a concrete verification failure requires returning to its owning task.

- [ ] **Step 1: Invoke `superpowers:verification-before-completion` and rerun fresh localization tests, full frontend suite, build, backend, DB isolation, governance/security, launcher, health, Provider, diagnostics, secret scan, and `git diff --check`.
- [ ] **Step 2: Confirm the feature branch is based on then-current clean `main`, no Provider hotfix trace or code was copied, and working tree is clean.
- [ ] **Step 3: Invoke `superpowers:finishing-a-development-branch` and choose KEEP FEATURE BRANCH / WORKTREE FOR HUMAN INTEGRATION REVIEW.
- [ ] **Step 4: Do not merge, push, tag, release, or bump version; report exact branch, worktree, HEAD, test counts, browser results, and remaining issues.

## Self-review Checklist

- [x] Every approved spec section maps to one or more tasks.
- [x] No TODO, TBD, placeholder, or unspecified test command remains.
- [x] Paths match the current repository map.
- [x] Resource key families and status helper interfaces are consistent across tasks.
- [x] Raw-content preservation has explicit tests in Tasks 8, 9, 11, and 12.
- [x] Browser isolation has explicit tests in Task 3 and DOM acceptance in Task 16.
- [x] Provider immediate Chinese status has explicit tests and HUMAN acceptance.
- [x] No task changes backend, API enums, Runtime, governance, or database authority.
- [x] No task installs or uses the temporary Provider hotfix worktree.
- [x] No task includes version, merge, push, tag, or release work.

