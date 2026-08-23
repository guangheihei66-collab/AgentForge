# Local Project Workspace Design

## Goal

Phase 14 lets one local AgentForge installation register multiple local software projects and run each new task only inside its selected project's validated workspace and capability policy. A Project is execution authority, not organizational metadata.

The authority chain is:

```text
Task
-> Project
-> ProjectExecutionContext
-> effective Capability catalog
-> Plan validation and deterministic resolution
-> approval-bound Project authority
-> Runtime
-> ToolGateway
```

## Current Limitation

Tasks currently store a caller-supplied `workspace`. Planner, Runtime, and Replanner consume it directly, while `WorkspaceValidator` checks it against one process-level configured root. This is safe for one fixed workspace but cannot express multiple independently governed projects. The approval JSON binds resolved tools and parameters, but not the project configuration that authorized them.

## Architectural Decision

Add a minimal local `Project` aggregate and make `Task.project_id` the source of project identity. The backend derives an immutable `ProjectExecutionContext` from current persisted Project configuration. Planner, Replanner, approval, Runtime, and ToolGateway receive this application-owned context; requests and models cannot supply or override workspace authority.

The approved choices are:

| Decision | Choice | Reason |
| --- | --- | --- |
| Capability persistence | JSON allow-list | Three current capabilities and no relational policy-query requirement do not justify a join table or generic policy engine. |
| New Project default | Empty explicit allow-list | Even `SAFE_READ` capabilities require an operator selection; future registry additions never gain authority implicitly. |
| Legacy Tasks | Nullable historical Project binding | Existing history stays readable without inventing a silently privileged Legacy Project. |
| Execution config version | Yes | An integer makes stale authority explicit and diagnosable. |
| Hard delete | Not supported | Archive preserves Task, Approval, Evidence, and Audit references. |
| Workspace networking | Local filesystem only | UNC and network roots are outside the local MVP security model. |
| Absolute workspace sent to LLM | No | Planning needs semantic capabilities, not local filesystem authority. |

Organization, user, team, tenant, and RBAC concepts are not introduced.

## Project Domain Model

`Project` has only operationally necessary fields:

- `id`: existing UUID string convention, 36 characters.
- `name`: required operator-facing name, bounded to 200 characters.
- `description`: optional bounded text, at most 2,000 characters.
- `workspace_root`: canonical absolute local directory string, at most 1,000 characters.
- `environment`: bounded operator/planner context such as `development`, at most 64 characters. In Phase 14 it is descriptive, not execution authority.
- `status`: exactly `ACTIVE` or `ARCHIVED`.
- `allowed_capability_ids`: duplicate-free, sorted JSON array of registered semantic Capability IDs.
- `config_version`: positive integer starting at 1.
- `created_at`, `updated_at`: existing UTC datetime convention.

`name`, `description`, and `environment` are editable metadata. They do not increment `config_version` in Phase 14 because they do not affect execution semantics. If a future executor uses environment to alter behavior, that phase must explicitly promote it into execution authority and versioning.

Two ACTIVE Projects may not use the same canonical workspace root under Windows case-insensitive comparison. This avoids ambiguous authority. An archived Project does not grant execution; creating a replacement Project for the same root is allowed, but the archived Project cannot be reactivated in Phase 14.

## Project as Security Boundary

A Project is usable only when it is ACTIVE, its canonical workspace still exists as a local directory, and its capability policy is valid against the global registry. New Tasks bind to exactly one Project at creation. `project_id` is never writable afterward; moving work to another Project requires a new Task.

The LLM cannot emit Project ID, workspace root, current directory, base directory, config version, or authority fingerprint as trusted data. Plan and Replan schemas remain capability-only. Backend request fields that resemble execution authority are rejected as extra fields rather than ignored.

## Workspace Root Rules

Project creation and execution use the existing `WorkspaceValidator`, extended rather than duplicated. A valid root:

- is a non-empty absolute filesystem path;
- has a Windows drive-letter form for the Windows MVP;
- is not a URI, device path, UNC path, mapped network path detected as remote, or path containing userinfo/URL semantics;
- resolves with strict canonicalization to an existing local directory;
- is not a protected user or system root already rejected by `WorkspaceValidator`;
- is stored as the strict resolved native path; a separate authority comparison key is produced with `ntpath.normcase(ntpath.normpath(path))` and used for equality, uniqueness, descendant checks, and fingerprinting;
- is selected by the local operator through Project configuration only.

No Task, Plan, prompt, model response, or tool parameter may override the root.

## Windows Path Safety

`WorkspaceValidator` gains explicit Project-root canonicalization and exact-root descendant checks:

1. Reject relative, UNC (`\\server\share`), extended UNC, device, and remote-drive roots before canonicalization.
2. Resolve `.` and `..`, normalize separators and drive-letter casing, and resolve the root strictly.
3. For each execution target, join only an allowed relative parameter to the approved canonical root, resolve it strictly where the operation requires an existing target, and compare canonical paths with `os.path.normcase` plus `os.path.commonpath` semantics.
4. Reject absolute target injection and any resolved target not equal to or below the canonical root.
5. Resolve symbolic links, junctions, and reparse points before the descendant decision. A nested link resolving outside the root is rejected.
6. Revalidate the Project root and target immediately before each execution; creation-time validation alone is insufficient.

Tests create tiny temporary directories. Junction tests run only where the platform can safely create them; otherwise the same canonical escape contract is covered with symlinks and deterministic unit cases.

## Project Capability Policy

`allowed_capability_ids` stores semantic Capability IDs only. Concrete Tool IDs, actions, permissions, and registry fingerprints are forbidden in Project policy input.

Creation defaults to an empty list. The operator must explicitly select every capability, including `SAFE_READ`. `APPROVED_EXEC` capabilities such as `test_verification` therefore always require explicit Project enablement and still require normal plan approval before execution.

Unknown IDs, duplicates, non-string values, or an unbounded policy are rejected. The Phase 14 bound is 64 capability IDs, each at most 128 characters. Stored IDs are sorted to make comparison and fingerprinting deterministic.

## Default-Deny Semantics

Adding a capability to the global registry does not update any Project. No fallback, implicit SAFE_READ grant, or policy expansion occurs during planning or resolution. Empty-policy Projects may exist and remain useful for configuration, but cannot produce an executable plan until the operator explicitly enables capabilities.

## Effective Capability Intersection

The application derives:

```text
EffectiveCapabilities = registered global capabilities intersect Project.allowed_capability_ids
```

The intersection is represented as a filtered capability catalog preserving the original definitions. Planner and Replanner receive only this filtered catalog. Plan validation and resolution reject any proposed capability absent from it. The global `CapabilityResolver` behavior remains unchanged: it still requires exactly one registered, enabled, permission-compatible concrete Tool candidate.

## Task-to-Project Binding

New `TaskCreate` accepts `project_id`, `title`, and `goal`. It does not accept trusted `workspace`, capability IDs, Tool IDs, config version, fingerprint, or filesystem authority. The backend loads the ACTIVE Project, derives its execution context, and records the canonical workspace in the existing `tasks.workspace` field only as a backward-compatible display snapshot. That column is not an authority source for Phase 14 Tasks.

`Task.project_id` is immutable from creation, including before planning. Plans and successor Plans inherit the Task binding and cannot contain a different Project.

## Legacy Task Compatibility

Existing rows retain `project_id = NULL`. Their current `workspace` value and all Plans, Approvals, Evidence, Audit, reports, and read APIs remain readable. They cannot start new planning, request new approval, resume Runtime, or Replan through Phase 14 execution paths. There is no automatic Legacy Project and no authority inferred from the historical workspace string.

## Project Configuration Versioning

`config_version` starts at 1 and increments atomically on each successful execution-relevant change:

- canonical `workspace_root` change;
- allowed Capability policy change;
- `ACTIVE -> ARCHIVED` status change.

Name, description, and Phase 14 environment edits update `updated_at` but do not increment `config_version`. No-op PATCH requests increment neither. Concurrent updates use an expected `config_version`; stale writes fail with conflict rather than silently overwriting policy.

## Project Authority Fingerprint

The application computes lowercase SHA-256 over canonical UTF-8 JSON with sorted keys and compact separators. The exact document is:

```json
{
  "authority_schema_version": 1,
  "project_id": "<uuid>",
  "config_version": 1,
  "workspace_root": "<case-normalized canonical Windows authority key>",
  "allowed_capability_ids": ["<sorted capability IDs>"],
  "status": "ACTIVE"
}
```

The fingerprint uses the `ntpath.normcase(ntpath.normpath(strictly_resolved_root))` authority key, so drive-letter case, path-component case, and mixed separators cannot create distinct authority on Windows. The stored/display path may preserve the resolved native spelling, but it is never used directly for security comparison. Name, description, environment, timestamps, and UI labels are excluded. Including both the version and values provides a clear stale-version signal and detects malformed or tampered persisted authority.

## Approval Snapshot Binding

Reuse `ApprovalRecord.resolved_snapshot`; no Approval column is added. Phase 14 writes document schema version 2:

```text
schema_version: 2
project_authority:
  project_id
  config_version
  authority_fingerprint
  canonical_workspace_root
steps:
  existing immutable resolved execution snapshots
```

The Plan JSON stores the same bounded `project_authority` block when resolution occurs. Approval creation verifies it against the current Project and then copies it into the approval document. Existing schema-version-1 approval documents remain readable for history but cannot authorize Phase 14 execution.

## Drift Detection

Before approval creation and before every Runtime step, the backend freshly derives `ProjectExecutionContext` and verifies all of the following:

- Task still has the same non-null Project ID;
- Project exists and is ACTIVE;
- Project `config_version` equals the Plan and Approval authority version;
- recomputed authority fingerprint equals the Plan and Approval fingerprint;
- canonical current workspace equals the approved workspace;
- step Capability remains in the effective Project allow-list;
- Task, Plan ID/version, resolved Tool, action, normalized parameters, and registry fingerprint still match the approval snapshot;
- target path remains canonically inside the Project workspace.

Any mismatch fails closed before ToolGateway execution. The system does not regenerate, mutate, or silently reapprove snapshots. A changed Project requires a newly generated plan/version and fresh approval under current authority.

## Project Status and Archive

`ACTIVE` permits Task creation, planning, approval, Replanning, and execution subject to all other checks. `ARCHIVED` permits read-only Project and historical Task/report/audit access but blocks new Tasks, new approvals, pending approvals, Runtime resume, and Replanning.

Phase 14 supports the one-way archive action and no hard-delete or unarchive product endpoint. Internal test fixtures may delete their isolated database rows during cleanup.

## Persistence Design

Add one `projects` table:

- `id VARCHAR(36) PRIMARY KEY`
- `name VARCHAR(200) NOT NULL`
- `description TEXT NULL`
- `workspace_root VARCHAR(1000) NOT NULL`
- `environment VARCHAR(64) NOT NULL`
- `status VARCHAR(32) NOT NULL`
- `allowed_capability_ids JSON NOT NULL`
- `config_version INTEGER NOT NULL`
- `created_at`, `updated_at` timezone-aware datetimes

Add nullable `tasks.project_id VARCHAR(36)` with a foreign key to `projects.id` and an index for Project task queries. Keep `tasks.workspace` non-null for compatibility, but do not use it as execution authority for Project-bound Tasks.

A JSON allow-list is preferable to a join table because policy is loaded and fingerprinted as one small aggregate, capability count is tiny, and no cross-Project capability analytics or RBAC query model exists. A generic policy subsystem is explicitly out of scope.

## Migration Strategy

Future implementation uses the existing bounded SQLite startup migration style:

1. `Base.metadata.create_all` creates `projects` for new or existing databases.
2. An idempotent inspection adds nullable `tasks.project_id` only when absent, then verifies the table and column.
3. No existing Task is updated; all receive implicit SQL `NULL`.
4. No Approval, Plan, Evidence, Audit, or execution row is rewritten.
5. No table is dropped and the database is never recreated.

Before a later live migration, create and verify a timestamped backup under `D:\AgentProjectData\AgentForge\database\backups`. This design task performs neither backup nor migration.

## Backend Boundaries

Use the minimum focused units consistent with the repository:

- `ProjectRepository`: persistence mapping and bounded Project/task queries.
- `ProjectService`: create, edit metadata, update security configuration with optimistic version checks, archive, and derive execution context.
- immutable `ProjectExecutionContext`: Project ID, config version, canonical root, sorted allowed capabilities, status, and authority fingerprint.
- one application-owned fingerprint function colocated with Project authority models.

Planner, Replanner, ApprovalService, and Runtime consume `ProjectExecutionContext` from `ProjectService`; none reconstruct authority from request payloads. `WorkspaceValidator`, `CapabilityResolver`, ApprovalService, RuntimeExecutor, and ToolGateway remain existing enforcement layers with small integration extensions only.

## Project API

Minimal endpoints follow current FastAPI conventions:

- `GET /projects`: bounded Project summaries.
- `POST /projects`: create after workspace and capability validation.
- `GET /projects/{project_id}`: Project details plus bounded recent Tasks.
- `PATCH /projects/{project_id}`: edit metadata or execution configuration; requires `expected_config_version` for security-relevant changes.
- `POST /projects/{project_id}/archive`: one-way archive with expected config version.
- `POST /projects/validate-workspace`: optional validation-only action returning canonical validity, never directory contents.

There is no DELETE endpoint, filesystem browser, repository editor, or Organization surface. PATCH support requires adding only the `PATCH` method to the explicit CORS allow-list.

## Task API Evolution

`POST /tasks` requires `project_id`. The backend rejects legacy `workspace`, workspace root, allowed tools, Tool IDs, capability policy, authority fingerprint, and config version in the payload. `TaskRead` may expose `project_id`, Project name, and canonical workspace for operator clarity; the displayed workspace is not client authority.

Historical internal fixture helpers may create null-Project Tasks explicitly. The normal API cannot.

## Planner Integration

Planner loads the Task's current `ProjectExecutionContext`, verifies ACTIVE status, and builds a filtered effective Capability catalog. The prompt may include bounded Project name, environment, and short description, but not the absolute workspace root, Project authority fingerprint, config version, Tool IDs, or approval data.

After provider response, application validation checks every Capability against the same effective catalog and resolves against the Project-scoped validator. The Plan stores Project authority before approval can be requested.

## Replanner Integration

Replanner reloads authority for the unchanged `Task.project_id`, verifies it against the current Plan/Approval context, and uses the same effective Capability intersection. `ReplanProposal` retains its strict capability-only schema and cannot change Project, workspace, policy, or authority fields. Every successor Plan records the same current Project identity and requires fresh approval. Project drift during Replanning fails the attempt; it never expands policy or switches Project.

## Runtime and ToolGateway Integration

Runtime no longer uses `task.workspace` as trusted authority for Project-bound Tasks. It reloads and verifies `ProjectExecutionContext`, approval authority, resolved snapshots, and effective capabilities before each step. RuntimeExecutor receives the application-injected canonical workspace and sends it with the already approved snapshot to ToolGateway.

ToolGateway and `WorkspaceValidator` remain mandatory. ToolGateway revalidates the exact Project root and target path immediately before the executor adapter runs. Neither Resolver nor Runtime may bypass it.

## Cross-Project Isolation

With Project A rooted at `D:\Test\ProjectA` and Project B at `D:\Test\ProjectB`, Task A fails closed for:

- `..\ProjectB` traversal;
- an absolute Project B path;
- a junction or symlink resolving into Project B;
- a Project B resolved or approval snapshot;
- Task `project_id` substitution;
- Project B capability-policy or authority-fingerprint substitution;
- a stale Project A approval after workspace or policy change.

There is no cross-project fallback. Matching capability IDs do not imply shared workspace authority.

## Frontend Experience

Add a small Projects navigation surface using the existing React structure:

- Projects list with name, environment, status, workspace, and recent Task count.
- Project creation form with absolute-path text input, optional Validate Workspace action, and explicit capability checkboxes grouped by permission level.
- Project detail with status, canonical workspace, environment, allowed capabilities, config version, recent Tasks, and Create Task action.
- Task creation starts from a Project and sends only Project ID, title, and goal.
- Archived Project detail remains readable while creation and execution actions are disabled with a clear explanation.

Do not add a file picker, filesystem explorer, IDE, analytics platform, Organization dashboard, users, teams, or billing.

## Dogfood Scenario

Manual smoke testing later registers:

```text
Project: AgentForge
Workspace: D:\AgentProjects\AgentForge
Environment: development
Capabilities: repository_state, project_metadata, test_verification
Task: Check whether the current AgentForge version is ready for release.
```

This is an explicitly triggered manual dogfood flow. Automated tests never operate against the real AgentForge working tree.

## Low-Overhead Test Strategy

Use one primary backend feature file: `backend/tests/test_phase_14_local_project_workspace.py`. Tiny temporary directories and isolated SQLite sessions cover model validation, API creation, canonicalization, missing/file/relative/UNC roots, traversal and link escape, ACTIVE/ARCHIVED behavior, capability policy validation and default deny, Task binding and legacy reads, authority version/fingerprint drift, approval invalidation, Planner/Replanner catalog restriction, Runtime/ToolGateway enforcement, and deterministic local fixture flow.

Use the existing frontend test setup only for Project list/detail, creation validation state, Project-scoped Task creation, capability display, and archived behavior. No real LLM call, unrelated project access, large fixture repository, or new test framework is required. Run focused suites during implementation and one full regression near completion.

## Resource Safety

Implementation remains in the existing development worktree and project-local dependency environments. It requires no package install, Docker, model download, external service, real provider call, drive scan, large log, or runtime data in Git. Test workspaces stay tiny and temporary. A future live migration requires separate approval and backup.

## Security Properties

1. The validated local operator Project configuration chooses workspace.
2. The LLM cannot change workspace.
3. A Task cannot request another workspace.
4. A Plan cannot specify another Project.
5. Replanning cannot change Project.
6. A Project cannot use an unregistered or non-allowed Capability.
7. Future capabilities are not automatically enabled.
8. Execution-relevant Project changes invalidate old approvals.
9. Project A cannot execute against Project B.
10. Archived Projects cannot begin or continue new execution.

## Expected Files Affected

Future implementation is expected to affect narrowly scoped Project domain/repository/service/schema/routes, ORM and idempotent migration files, Task creation contracts, Project-aware Planner/Replanner/Approval/Runtime integration, `WorkspaceValidator`, existing frontend navigation/API/types/pages/tests, the single Phase 14 backend test file, and required operational documentation. It must not add a second ToolGateway, generic policy framework, one test package per component, or unrelated platform modules.

## Risks and Mitigations

- **Path alias or reparse escape:** strict canonicalization at registration and every execution target; reject remote and escaped resolved paths.
- **Stale Project authority:** version plus canonical fingerprint in Plan and Approval JSON, recomputed before every step.
- **Future capability privilege growth:** empty explicit default and intersection-only catalog.
- **Legacy authority grant:** nullable historical binding and execution denial, never automatic Project creation.
- **Client/model authority injection:** strict request and proposal schemas; all execution context loaded server-side.
- **Cosmetic-edit approval churn:** fingerprint and config version exclude non-execution metadata.
- **Scope creep:** two statuses, JSON allow-list, no delete/unarchive, no Organization/RBAC or generic policy system.

## Out of Scope

Organization, Team, users, login, RBAC, SSO, LDAP/OIDC, billing, tenants, cloud repository hosting or cloning, GitHub/GitLab integration, remote/UNC/NAS workspaces, Docker or VM sandboxing, PostgreSQL, workers, queues, multi-agent, RAG, MCP, long-term memory, enterprise secret management, filesystem browsing, and source editing are excluded.

## Future Evolution

A later phase may add managed remote workspaces, relational capability policy, Project reactivation, environment-specific execution semantics, stronger OS sandboxing, or multi-user authorization only after concrete product requirements justify their additional authority model and migrations. None is implied by Phase 14.

## Database Impact

- New table required: **YES** (`projects`).
- Task column change required: **YES** (nullable `tasks.project_id`).
- Approval table column change required: **NO** (reuse versioned `resolved_snapshot` JSON).
- Expected live migration required later: **YES**.
