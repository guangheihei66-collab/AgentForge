# AgentForge Native Chinese/English Localization Design

Status: design specification for HUMAN review
Phase: 14.1
Date: 2026-08-25
Base: `main` at `24947120466b76a7c9c06c327d90aed0aa6afb55`

## 1. Problem statement

AgentForge currently ships an English-only React operations console. Edge automatic translation can mutate React-managed DOM nodes after React renders them. The observed Provider incident showed React state and the API result at `success`, while a translated DOM node retained an older visible label until navigation caused a remount. Native application localization is required so AgentForge owns both language selection and dynamic text rendering.

This phase is a frontend product-experience change. The Agent Runtime, governed execution path, backend contracts, and security model remain frozen.

## 2. Incident and root evidence

The live incident included a DOM node with an `_mstmutation` attribute. The application trace simultaneously showed `connection_status = success` and the intended `Connection success` render, but the visible browser text remained stale until navigation. This is evidence of browser-translation interference with a React-managed node, not evidence that backend state or the Provider API contract is wrong.

## 3. Goals

- Provide professional, human-written `en-US` and `zh-CN` UI.
- Add an accessible global language selector near the operator controls.
- Resolve locale from explicit HUMAN preference, then browser language, then `en-US`.
- Persist explicit selection at `localStorage` key `agentforge.locale`.
- Switch language immediately without navigation or reload.
- Set `document.documentElement.lang` to the active locale.
- Mark the React application boundary `translate="no"` so browser translation is not needed.
- Localize all AgentForge-authored UI chrome and presentation statuses while preserving raw runtime content.

## 4. Non-goals

This phase does not add languages beyond `en-US` and `zh-CN`, machine translation, runtime LLM translation, backend language preference, account synchronization, cloud localization, visual redesign, or any Runtime capability. It does not translate user goals, evidence, observations, errors, paths, model names, identifiers, command output, audit payloads, or raw provider content.

## 5. Locale model

The supported locale union is exactly:

```ts
type Locale = 'en-US' | 'zh-CN'
```

Stored values are accepted only when they are one of those two exact values. Invalid or absent stored values are ignored. A browser language whose lower-cased value begins with `zh` resolves to `zh-CN`; all other browser languages resolve to `en-US`.

## 6. Resolution and persistence

Resolution order is deterministic:

1. Read `localStorage.getItem('agentforge.locale')` and accept only a supported value.
2. Otherwise inspect `navigator.language` and choose `zh-CN` for a `zh` prefix.
3. Otherwise choose `en-US`.

The application owns locale state through an i18n provider initialized once at the React root. Selecting a language calls the i18n change operation, writes the supported value to local storage, updates the document language, and rerenders synchronously through React/i18next. Storage failures are treated as non-fatal: the current session still changes language, while the next visit falls back to browser resolution.

## 7. i18n architecture

Because the current frontend has no localization library, use `i18next` and `react-i18next`. Do not build a custom translation framework and do not add `i18next-browser-languagedetector`; the explicit resolution rules are small and must remain application-owned.

The proposed structure is:

```text
frontend/src/i18n/
  index.ts
  locale.ts
  resources/
    en-US.ts
    zh-CN.ts
frontend/src/components/LanguageSelector.tsx
```

`index.ts` initializes i18next with the two resources and the resolved locale. `locale.ts` owns the supported union, storage key, resolution, persistence, and document-language update. Components use `useTranslation()` and `t(...)`; they do not branch on locale or embed translated literals.

## 8. Resource organization

Resources use stable semantic namespaces rather than page-local English strings. The initial key families are:

- `common.actions`, `common.labels`, `common.loading`, `common.errors`, `common.empty`
- `navigation`
- `shell`
- `dashboard`
- `projects`
- `tasks`
- `approvals`
- `evidence`
- `audit`
- `reports`
- `diagnostics`
- `provider`
- `status.task`, `status.approval`, `status.execution`, `status.health`, `status.risk`

English resources retain the current intended product copy, with only grammar or punctuation normalization where needed for a stable key. Chinese resources use concise enterprise-console terminology, not literal machine translation. Resource objects must be type-checked against the English resource shape so missing keys fail during development/build.

## 9. Status localization architecture

Backend values remain canonical and are never translated in API requests, persistence, audit records, or internal comparisons. A centralized presentation module maps each supported canonical union to a translation key and supplies a deterministic fallback for unknown future values.

Required mappings include:

| Canonical value | Translation key |
|---|---|
| `SUCCESS` | `status.task.success` |
| `FAILED` | `status.task.failed` |
| `REJECTED` | `status.task.rejected` |
| `WAITING_APPROVAL` | `status.task.waitingApproval` |
| `HEALTHY` | `status.health.healthy` |
| `DEGRADED` | `status.health.degraded` |
| `UNHEALTHY` | `status.health.unhealthy` |
| `UNKNOWN` | `status.health.unknown` |
| `success` | `provider.connection.success` |
| `not tested` | `provider.connection.notTested` |
| `failed` | `provider.connection.failed` |

`StatusPill`, `Timeline`, Dashboard, Report, and Diagnostics consume these helpers. Unknown values render a safe localized `unknown` label and preserve the raw value only where a diagnostic/raw field is intentionally shown.

## 10. Agent terminology glossary

The glossary is the single source for product copy:

| Concept | English | Simplified Chinese |
|---|---|---|
| Dashboard | Dashboard | 仪表盘 |
| Projects | Projects | 项目 |
| Tasks | Tasks | 任务 |
| Approvals | Approvals | 审批 |
| Evidence | Evidence | 证据 |
| Audit | Audit | 审计 |
| Reports | Reports | 报告 |
| Diagnostics | Diagnostics | 系统诊断 |
| Plan | Plan | 执行计划 |
| Capability | Capability | 能力 |
| Tool | Tool | 工具 |
| Tool Execution | Tool Execution | 工具执行 |
| Observation | Observation | 观察结果 |
| Replan | Replan | 重新规划 |
| Approval Snapshot | Approval Snapshot | 审批快照 |
| Workspace Authority | Workspace Authority | 工作区权限边界 |
| Approval entity/workflow | Approval | 审批 |
| Approve action | Approve | 批准 |
| Reject action | Reject | 拒绝 |
| Authorization/security authority | Authority | 权限 / 授权边界 |
| Resolver | Resolver | 解析器 |

`ToolGateway` remains untranslated as a component name where code/documentation correspondence matters. Technical identifiers are never mechanically translated.

## 11. Raw-content preservation

Only AgentForge-authored labels, headings, actions, explanatory copy, and presentation wrappers are translated. The following values remain byte/text-equivalent across locales: user Goal and Project/Task names, raw LLM output, evidence and observation content, raw error messages, file and repository paths, Git SHAs, model/provider identifiers, capability/tool identifiers, command output, audit payloads, structured JSON, and code. A translated label may surround such content, but must not rewrite it.

## 12. Browser translator isolation

The root application element rendered by `main.tsx` receives `translate="no"`, and `document.documentElement.lang` tracks the selected locale. Native Chinese content therefore does not depend on Edge or Chrome translation. Dynamic Provider status remains a React/i18next render driven by canonical API state; no `_mstmutation` node is part of the expected application DOM. Browser-specific CSS or translator detection is not a substitute for the standards-based boundary.

## 13. Component and page migration scope

Migration covers the current frontend files without changing backend APIs:

- `main.tsx`, `App.tsx`, `components/Shell.tsx`, and the new `LanguageSelector` for root setup, header selector, shell chrome, navigation, health, operator labels, and translation protection.
- `Dashboard.tsx` for headings, metrics, Provider labels/actions/status, task and approval summaries, risk labels, and empty states.
- `Projects.tsx` and `ProjectDetail.tsx` for project/workspace/configuration forms, capability labels, task creation, archive messaging, and project statuses.
- `TaskDetail.tsx`, `Timeline.tsx`, and `StatusPill.tsx` for task states, plan headings, execution/evidence/audit presentation, and status/risk/permission labels.
- `Approvals.tsx` for queue, actions, plan/risk/security copy, permission descriptions, and approval statuses.
- `Report.tsx` for readiness, evidence, audit, execution, and summary labels.
- `Diagnostics.tsx` for loading/errors, health states, provider metadata labels, credentials, revision, and diagnostics headings.
- `useOperations.ts` only where it owns AgentForge-authored fallback/demo copy; user/runtime values remain untouched.

No new page or major visual redesign is included.

## 14. Accessibility

The selector must be keyboard reachable, have an accessible name, expose the active language, and use a native select or equivalent semantic control. Locale changes must not move focus unexpectedly. `document.documentElement.lang` supports assistive technology language selection. Translated labels must preserve existing button semantics, status meaning, contrast, and live-update behavior. Provider status updates should remain discoverable without relying on color alone.

## 15. Error and fallback behavior

Missing translation keys must be detected in tests/build where practical. Runtime missing-key behavior is deterministic: use the English resource fallback and emit a development-visible i18next warning, without throwing or blanking the UI. Invalid locale storage, unavailable storage, unsupported browser language, and failed language persistence do not block application startup. Unknown canonical status values use the localized unknown fallback and do not change the underlying value.

## 16. Testing strategy

TDD is required for every behavioral change. Targeted tests must cover:

1. non-Chinese browser with no preference defaults to `en-US`;
2. `zh-CN` and other `zh` variants default to `zh-CN`;
3. explicit local storage overrides browser language;
4. both language switch directions update immediately;
5. preference survives remount/reload simulation;
6. document language updates;
7. root `translate="no"` exists;
8. Provider `not tested`, `success`, and `failed` presentation;
9. task `SUCCESS`, `FAILED`, `REJECTED`, and `WAITING_APPROVAL` presentation;
10. all health states;
11. raw goals, evidence, paths, model names, and Git SHAs remain unchanged;
12. English resources preserve intended English copy;
13. missing keys have deterministic behavior;
14. targeted application chrome contains no unapproved hardcoded English.

Existing App and Diagnostics tests remain green. The full frontend suite, production build, backend suite, DB isolation, governance/security regression, and secret scan remain required after implementation.

## 17. Real browser acceptance

With the real backend and the native frontend running, select English and verify Dashboard, Projects, Tasks, Approvals, Evidence, Audit, Reports, and Diagnostics use English chrome. Select 中文 and verify the same surfaces use native Simplified Chinese. Switch in both directions without reload.

In Chinese mode, Provider must show `尚未测试连接`, then after one Test Connection click and a canonical successful response show `连接成功` immediately, remain so for at least ten seconds, and require neither navigation nor reload. Browser machine translation must not be enabled or required.

## 18. Security and runtime non-impact

This phase changes only frontend presentation and local browser preference. It does not change Planner authority, Plan Validation, Capability Resolver, Approval security, Approval Snapshots, Project Authority, AgentRuntime, ToolGateway, execution, Observation, Evidence, controlled Replan, database authority, API payloads, or canonical enum values. No credential, raw provider output, or user content is added to localization resources or local storage.

## 19. Migration and rollout

Implementation must branch from a clean, HUMAN-resolved current `main`, not from the Provider hotfix worktree or its temporary trace state. Add dependencies only in the frontend package through the existing project workflow; do not change versions or release metadata in this phase. Roll out the selector and native resources together, validate English as the compatibility default, then validate Chinese in the real browser. Existing users without a preference remain on the resolved English/browser behavior described above.

The implementation is an independent feature branch and worktree. It must not be merged, pushed, tagged, version-bumped, or released automatically.

## 20. Exit criteria

The implementation is eligible for HUMAN review only when:

- both locales and persistence work;
- document language and `translate="no"` are verified;
- all in-scope authored chrome is localized;
- canonical enums and raw runtime content are unchanged;
- centralized status mappings and glossary are used;
- targeted localization tests, full frontend tests, and production build pass;
- backend, DB isolation, governance/security, launcher, health, diagnostics, and secret checks pass;
- real browser English, Chinese, bidirectional switching, and immediate Provider Chinese status acceptance pass;
- no browser machine translation is required;
- the feature worktree is clean and no temporary instrumentation or secrets are present.

The implementation candidate remains `NO` until the HUMAN browser acceptance is complete.
