# Deployment Architecture Explanation

```text
                internal operator browser
                         |
                    React / Vite :5173
                         |
                    FastAPI :8000
          +--------------+---------------+
          |                              |
     SQLite database              Tool Gateway
          |                              |
  D:\\AgentProjectData\\AgentForge     approved workspace
  (runtime, audit, evidence)       D:\\AgentProjects\\AgentForge
```

The browser communicates with the FastAPI operations API. The API owns task state, plan versions, approval decisions, tool execution records, evidence references, and audit events. The Tool Gateway is the only execution boundary; agents do not call tools directly.

The source directory is immutable application code. Mutable database files, runtime logs, PID files, evidence references, and synthetic demo artifacts belong in `AGENTFORGE_DATA_ROOT`. In an internal deployment, a reverse proxy can provide TLS and network access control without changing the application boundary.

## Request path

```text
Goal -> Planner -> validated Plan -> Approval -> Tool Gateway
     -> ToolExecution -> Evidence -> AuditEvent -> Report
```

The current package uses SQLite for the single-host MVP and a deterministic mock planner for offline demos. PostgreSQL, external LLM providers, RBAC, and multi-host orchestration remain explicit future phases.
