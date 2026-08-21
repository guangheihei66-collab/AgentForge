# AgentForge

AgentForge is a self-hosted enterprise Agent execution platform for controlled engineering workflows.

## MVP

The first demonstration is a Release Verification Agent:

```text
Goal -> Plan -> Human Approval -> Tool Gateway -> Evidence -> Audit -> Report
```

The MVP uses Python/FastAPI, React/TypeScript, SQLite, an API-based model, a custom state machine, and three allowlisted tools: Git, File, and Test.

## Status

Phase 6 Planner Agent and Mock LLM integration completed. Backend domain persistence, task workflow, validated planning, read-safe tools, permission checks, workspace validation, human approval, audit, and evidence are implemented. Real external LLM integration, frontend, Docker, PostgreSQL, RBAC, and write-capable tools have not started.

Runtime data belongs under `D:\AgentProjectData\AgentForge\`, never in this source tree.
