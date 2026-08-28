# AgentForge Final Product Integration and Release Freeze

Status: HUMAN-approved implementation scope

Date: 2026-08-28

## Objective

Integrate the existing native `en-US` / `zh-CN` localization work into the
current `main` repository without regressing the Phase 15A Repository Analyst
Agent. Complete a bounded usability pass, remove only proven source-tree
development leftovers, and prepare a reproducible release candidate. The
release candidate stops before publishing and before the final HUMAN test.

## Current baseline

`main` already contains the Phase 15A Agent Workspace, capability-first plan
resolution, HUMAN approval routing, governed execution, durable provenance,
Diagnostics, controlled re-planning, Evidence/Report presentation, and the
terminal recovery CTA fix. The localization branch predates those Agent
surfaces, so its old component revisions are not merge targets.

## Integration design

### Localization boundary

Use the existing localization branch architecture:

- `i18next` with `react-i18next` as the frontend-only presentation boundary.
- In-memory `en-US` and `zh-CN` resources with English fallback.
- Locale resolution from `agentforge.locale`, then browser language, then
  `en-US`.
- A language selector in the existing shell, with document `lang` updates.
- `translate="no"` on the application root to prevent browser DOM translation
  from changing technical values.
- Status, risk, approval, execution, provider, and health mapping helpers.

Only the infrastructure and translations are ported from the localization
branch. Current main components remain authoritative for behavior and layout.
No backend, API, database, Runtime, CapabilityResolver, ToolGateway, approval
security, or re-planning semantics change.

### User-facing coverage

All current authored copy on the Dashboard, Projects, Project Detail, Tasks,
Approvals, Agent Workspace, Agent Plan/Approval/Timeline/Report cards,
Diagnostics, Report, navigation, status pills, loading states, errors, empty
states, and operator actions receive stable translation keys.

Machine facts remain unchanged: IDs, hashes, paths, API paths, Git refs,
capability/tool identifiers, audit event identifiers, raw evidence,
observation payloads, provider/model identifiers, and raw error text. Where
useful, a localized friendly label may appear beside the raw value.

### Agent safety preservation

Localization must preserve the Phase 15A approval distinction:

- Agent-managed approvals show the safety explanation and `Open in Agent
  Workspace`; they never expose generic `Approve only`.
- Non-Agent approvals retain `Approve only`.
- `Approve & Execute` and approved execution recovery remain unchanged in
  behavior and remain gated by the existing backend authority.
- Terminal Tasks do not expose execution or recovery actions.
- Durable provenance and Diagnostics remain factual and machine-readable.

### Bounded UX polish

Review only the existing priority surfaces: Agent Workspace, Dashboard,
Projects, Tasks, Approvals, and Diagnostics. Changes are limited to obvious
clarity or acceptance issues found during implementation, such as stale page
selection or duplicated/ambiguous authored labels. No redesign, new API,
subsystem, database table, capability, Agent type, or execution behavior is
included.

## Source/runtime cleanup policy

The source tree must not gain runtime databases, logs, evidence, screenshots,
temporary probes, or debug output. Runtime data remains under
`D:\AgentProjectData\AgentForge`. Historical audit/evidence data is preserved.
Only artifacts proven to be investigation-only and disposable may be removed;
uncertain files remain and are reported as cleanup candidates.

The Phase 15A feature worktree and Native Localization worktree remain intact
through final verification. The unregistered Phase 12 partial path is read
only; it is not deleted unless a later audit proves it has no unique work and
removal is explicitly safe.

## Release-freeze rules

After localization, bounded UX polish, and cleanup are complete, no new
product scope is accepted. Only P0/P1 release blockers, security regressions,
data-integrity issues, lifecycle failures, localization failures, launcher
failures, or acceptance-blocking UI defects may be fixed.

The release candidate does not add multi-agent behavior, RAG, MCP, arbitrary
shell or write tools, browser automation, Docker/Kubernetes, RBAC, new
provider architecture, or a new workflow system.

## Acceptance criteria

The release candidate is ready for one final HUMAN test when all of the
following are true:

1. `en-US` is the deterministic default and renders all current product
   surfaces without missing critical keys.
2. `zh-CN` renders native, consistent product terminology and preserves raw
   technical values.
3. Switching locale and reloading preserve `agentforge.locale`.
4. Browser-translation protection and document language synchronization pass.
5. Current Agent Workspace behavior, approval routing, terminal recovery
   suppression, Timeline, Evidence/Report, Diagnostics, and reloading remain
   regression-green.
6. Backend security, orchestration, provenance, re-planning, provider, and DB
   isolation suites pass unchanged.
7. Launcher resolution, owned-process lifecycle, and main-repository startup
   smoke pass without affecting unrelated processes.
8. Main has no unintended generated artifacts, secrets, debug markers, or
   source-tree runtime pollution.
9. The main service is running from the current main revision for the HUMAN
   checklist, but no new dogfood Task is created by this implementation pass.
10. Version/tag/release decisions are recommendations only; no version bump,
    tag, push, or publish occurs before HUMAN acceptance.

## Post-release backlog

Ideas requiring new architecture, broader role/tenant controls, additional
Agent types, richer automation, or production deployment infrastructure are
recorded outside this release candidate and are not implemented here.
