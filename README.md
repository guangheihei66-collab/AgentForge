# AgentForge

## Enterprise AI Agent Governance Platform

AgentForge is a self-hosted control plane for deploying controlled AI Agents in enterprise engineering workflows. It is an operations console, not a chatbot: operators can inspect intent, approve risk, observe execution, and trace results back to evidence and audit records.

## Overview

AgentForge enables enterprises to combine:

- Agent planning
- Human approval
- Secure tool execution
- Evidence tracking
- Auditability

## Problem

Unrestricted autonomous execution is difficult to trust in an enterprise. A model may propose useful actions while still having unclear permissions, unsafe execution paths, incomplete traceability, and poor support for audits or incident review. Prompting alone is not an authorization system.

## Solution

AgentForge separates model intent from execution authority:

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
Execution
    ↓
Evidence + Audit
    ↓
Final Report
```

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
Execution Records
    ↓
Evidence + Audit
    ↓
Final Report
```

The Planner produces semantic capability requirements but cannot choose or execute concrete tools. The application-owned resolver requires exactly one registered, enabled, permission-compatible, parameter-valid candidate and fails closed otherwise. The Approval Gateway binds a human decision to the capability, resolved tool, normalized parameters, registry fingerprint, task, plan, and plan version. AgentRuntime consumes that approved snapshot, while the Tool Gateway remains the final permission and workspace boundary. Operations endpoints expose execution, evidence, and audit records to the React console.

## Security Design

- Permission boundary: default-deny policy with explicit `SAFE_READ` and `APPROVED_EXEC` levels.
- Approval requirement: protected execution requires an approved, matching plan version.
- Tool allowlist: only registered Git read, file read, and predefined test-profile tools are available.
- Workspace boundary: system paths, user directories, secrets, and out-of-scope paths are rejected.
- Audit logging: state transitions, approvals, tool executions, and evidence references are recorded with actors and correlation IDs.
- Capability authority: concrete tool selection is deterministic and application-owned; there is no LLM ranking or implicit tie-break.
- Approval drift protection: changed capability, tool, parameters, plan version, or execution-relevant registry semantics invalidates execution.

## Demo Scenario

The Release Verification Agent answers: “Is Release v2.0 ready for release?” The synthetic demo demonstrates:

```text
Create Task → Generate Plan → Approve → Execute → Collect Evidence → Generate Report
```

The controlled tools are `git_read`, `file_read`, and the predefined `test_run` profiles. The permission layer is default-deny and the workspace boundary rejects secret, system, and out-of-scope paths.

## Technology Stack

Backend: Python, FastAPI, SQLAlchemy, SQLite, Pydantic.

Frontend: React, TypeScript, Vite, Tailwind CSS.

AI boundary: `LLMProvider` interface with a deterministic `MockLLMProvider`; real external LLM integration is intentionally not enabled in this demo package.

The MVP uses a custom state machine and three allowlisted tools: Git read, File read, and predefined Test profiles.

## Quick Start

Windows:

Double-click [`Start-AgentForge.bat`](Start-AgentForge.bat) to start AgentForge.

Double-click [`Stop-AgentForge.bat`](Stop-AgentForge.bat) to stop AgentForge processes.

These root-level files are wrappers around the existing `launcher/` scripts. Runtime logs and PID files remain under `D:\AgentProjectData\AgentForge\runtime`.

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

## Status and boundaries

Phase 11.2 capability-based tool selection is implemented. Backend domain persistence, task workflow, capability-first planning, deterministic resolution, approval-bound execution snapshots, read-safe tools, permission checks, workspace validation, audit, evidence, the React dashboard, and one-click startup are implemented. The initial mappings are `repository_state -> git_read`, `project_metadata -> file_read`, and `test_verification -> test_run`. Legacy concrete-tool plans remain readable but cannot execute through the Phase 11.2 Runtime. Real external LLM integration, Docker, PostgreSQL, RBAC, and write-capable tools have not started.

Runtime data belongs under `D:\AgentProjectData\AgentForge\`, never in this source tree.

See [README_CN.md](README_CN.md) for Chinese project notes, [docs/demo/DEMO_RUNBOOK.md](docs/demo/DEMO_RUNBOOK.md) for the interview demo sequence, and [docs/interview/PROJECT_STORY.md](docs/interview/PROJECT_STORY.md) for the interview explanation.

Additional portfolio material is available in [technical_questions.md](docs/interview/technical_questions.md), [resume_material.md](docs/interview/resume_material.md), [demo_script.md](docs/demo/demo_script.md), and [screenshots.md](docs/demo/screenshots.md).
