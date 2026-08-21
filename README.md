# AgentForge

AgentForge is a self-hosted AI Agent governance platform for controlled engineering workflows.

It is designed as an enterprise operations console, not a chatbot. The operator can see what an Agent plans to do, approve or reject it, inspect governed tool execution, and trace every result back to evidence and audit records.

## Core capability

```text
Agent Planning
      +
Human Approval
      +
Secure Tool Execution
      +
Evidence
      +
Auditability
```

## Architecture

```text
User Goal
    ↓
Planner Agent
    ↓
Plan Validator
    ↓
Approval Gateway
    ↓
Tool Gateway
    ↓
Evidence + Audit
    ↓
Final Report
```

## Demo flow

The synthetic Release Verification Agent demonstrates:

```text
Create Task → Generate Plan → Approve → Execute Tools → Generate Report
```

The controlled tools are `git_read`, `file_read`, and the predefined `test_run` profiles. The permission layer is default-deny and the workspace boundary rejects secret, system, and out-of-scope paths.

## MVP

The primary demonstration is a Release Verification Agent:

```text
Goal -> Plan -> Human Approval -> Tool Gateway -> Evidence -> Audit -> Report
```

The MVP uses Python/FastAPI, React/TypeScript, SQLite, an API-based model, a custom state machine, and three allowlisted tools: Git, File, and Test.

## Technology stack

Backend: Python, FastAPI, SQLAlchemy, SQLite, Pydantic.

Frontend: React, TypeScript, Vite, Tailwind CSS.

Agent boundary: `LLMProvider` interface with a deterministic `MockLLMProvider`; real external LLM integration is intentionally not enabled in this demo package.

## Start the demo

On Windows, double-click [`start/start_agentforge.bat`](start/start_agentforge.bat). It initializes idempotent synthetic demo data under `D:\AgentProjectData\AgentForge\`, starts the backend and frontend, and opens the dashboard.

Stop with [`start/stop_agentforge.bat`](start/stop_agentforge.bat) or [`stop_agentforge.bat`](stop_agentforge.bat). Runtime logs and PID files remain outside the source tree.

Manual checks:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q

cd ..\frontend
npm test
npm run build
```

## Status

Phase 7 enterprise operations console completed. Backend domain persistence, task workflow, validated planning, read-safe tools, permission checks, workspace validation, human approval, audit, evidence, and the React dashboard are implemented. Real external LLM integration, Docker, PostgreSQL, RBAC, and write-capable tools have not started.

Runtime data belongs under `D:\AgentProjectData\AgentForge\`, never in this source tree.

See [README_CN.md](README_CN.md) for Chinese project notes, [docs/demo/DEMO_RUNBOOK.md](docs/demo/DEMO_RUNBOOK.md) for the interview demo sequence, and [docs/interview/PROJECT_STORY.md](docs/interview/PROJECT_STORY.md) for the interview explanation.
