# Architecture Documentation

AgentForge separates model intent from application-owned execution authority:

```text
Project (canonical workspace + explicit Capability policy)
  -> Task -> Planner/Replanner -> validated semantic Plan
  -> Project authority snapshot -> human Approval
  -> AgentRuntime -> ToolGateway -> Evidence/Audit
```

`ProjectExecutionContext` is derived from persisted Project state and is never supplied by the model or Task payload. It contains Project ID, config version, canonical workspace key, sorted allowed Capability IDs, ACTIVE status, and a deterministic SHA-256 fingerprint. Name, description, environment, labels, and timestamps are not execution authority in Phase 14.

Planner and Replanner receive only the intersection of the global Capability registry and the Project's explicit allow-list. Empty policy is valid and default-deny. Plan JSON and approval snapshot schema version 2 carry the same Project authority. ApprovalService, Runtime, and ToolGateway revalidate it, including for SAFE_READ, so stale policy, workspace, status, fingerprint, Project substitution, and cross-Project execution fail closed.

Workspace roots are strict existing local directories. UNC/device/remote roots, user/system roots, traversal, sibling-prefix paths, and resolved symlink/junction/reparse escapes are rejected. ToolGateway remains the only execution path. Phase 14 adds no arbitrary command, write tool, hard delete, unarchive, Organization, RBAC, file browser, Docker, model download, or network workspace.

SQLite gains a `projects` table and nullable indexed `tasks.project_id`. Null preserves historical records only; new Task creation requires an ACTIVE Project. Migration is idempotent and non-destructive, but live database application is a separately approved operational task with backup.
