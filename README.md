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

Every new Task starts from a local Project. A Project owns one canonical local workspace, an explicit Capability allow-list, status, and execution configuration version. Policy defaults to empty. The application binds Project authority into Plan and Approval snapshots and revalidates it before approval and each Runtime/ToolGateway step; the model never selects workspace or Project authority.

After bounded diagnostic evidence, Runtime may choose one of four decisions: `CONTINUE`, `COMPLETE`, `FAIL`, or `REPLAN`. A `REPLAN` pauses execution and lets the configured provider propose capability-only remaining steps. Application policy, validation, deterministic resolution, and a fresh human approval all run before a successor version can execute; the previous plan and approval never authorize that successor.

## Security Design

- Permission boundary: default-deny policy with explicit `SAFE_READ` and `APPROVED_EXEC` levels.
- Approval requirement: protected execution requires an approved, matching plan version.
- Tool allowlist: only registered Git read, file read, and predefined test-profile tools are available.
- Workspace boundary: system paths, user directories, secrets, and out-of-scope paths are rejected.
- Audit logging: state transitions, approvals, tool executions, and evidence references are recorded with actors and correlation IDs.
- Capability authority: concrete tool selection is deterministic and application-owned; there is no LLM ranking or implicit tie-break.
- Approval drift protection: changed capability, tool, parameters, plan version, or execution-relevant registry semantics invalidates execution.
- Project isolation: ACTIVE Projects cannot share a canonical workspace; remote, UNC, traversal, junction/symlink, and cross-Project escapes are rejected.
- Project lifecycle: archive is one-way and preserves history while blocking Task creation, pending approval, Runtime resume, and Replanning.

## Demo Scenario

The Release Verification Agent answers: “Is Release v2.0 ready for release?” The synthetic demo demonstrates:

```text
Create Task → Generate Plan → Approve → Execute → Collect Evidence → Generate Report
```

The controlled tools are `git_read`, `file_read`, and the predefined `test_run` profiles. The permission layer is default-deny and the workspace boundary rejects secret, system, and out-of-scope paths.

## Technology Stack

Backend: Python, FastAPI, SQLAlchemy, SQLite, Pydantic.

Frontend: React, TypeScript, Vite, Tailwind CSS.

AI boundary: a unified `LLMProvider` interface supports the deterministic mock and a bounded OpenAI-compatible HTTP transport. The model proposes semantic capabilities only; validation, concrete tool resolution, approval, Runtime, and ToolGateway remain application-controlled.

Provider selection is environment-only. The default is `AGENTFORGE_LLM_PROVIDER=mock`. To opt into the OpenAI-compatible transport, set `AGENTFORGE_LLM_PROVIDER=openai-compatible` plus the base URL, model, and API key documented in `.env.example`. Non-local endpoints require HTTPS. Credentials are never returned by the status API or editable in the console, and connection tests run only after an explicit operator action.

The MVP uses a custom state machine and three allowlisted tools: Git read, File read, and predefined Test profiles.

## Quick Start

Windows:

Double-click [`Start-AgentForge.bat`](Start-AgentForge.bat) to start AgentForge.

Double-click [`Stop-AgentForge.bat`](Stop-AgentForge.bat) to stop AgentForge processes.

These root-level files are wrappers around the existing `launcher/` scripts. Runtime logs and PID files remain under `D:\AgentProjectData\AgentForge\runtime`.

The launcher initializes idempotent synthetic demo data under `D:\AgentProjectData\AgentForge\`, starts the backend and frontend, and opens the dashboard. It does not create a Task or execute a tool as part of startup.

Use [`Stop-AgentForge.bat`](Stop-AgentForge.bat) to stop only the AgentForge process tree. Runtime logs and PID files remain outside the source tree.

Use the language selector in the top bar to switch between `en-US` and `zh-CN`. The selected locale is persisted in browser storage; technical identifiers, paths, capability IDs, tool IDs, audit values, evidence references, and provider/model values remain unchanged.

Manual checks:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q

cd ..\frontend
npm test
npm run build
```

## Status and boundaries

Phase 13 controlled re-planning is implemented behind the existing governed planning boundary. It allows at most two replans and twelve total steps across versions, with an 8 KiB context cap and 12 KiB complete-prompt cap. Every successor version, including safe-read-only plans, requires fresh approval of exact resolved snapshots. Plan v1 remains immutable and cannot authorize v2. Audit records contain bounded summaries and references, not Chain of Thought, raw model/tool output, or provider credentials. Mock remains deterministic and offline; a real-provider failure never silently falls back to Mock. Phase 13 requires no database migration or frontend setup. Docker, PostgreSQL, RBAC, and write-capable tools have not started.

Phase 14 local Projects are implemented in the backend and React console. New API Tasks require `project_id`; clients cannot inject workspace or Tool authority. Legacy null-Project history remains readable but non-executable. The schema migration is idempotent and tested only against isolated SQLite files. The live runtime database has not been migrated by this implementation task; that operation requires a separate approved backup and migration.

The current release candidate integrates the native frontend localization surface into the latest Agent Workspace UI. The console keeps the approval-routing safety rule: Agent-managed approvals must be completed from Agent Workspace through the composite approval command, while generic approval remains approval-only. The release candidate also keeps the bounded terminal recovery CTA and hides it after durable execution initiation or terminal completion.

Runtime data belongs under `D:\AgentProjectData\AgentForge\`, never in this source tree.

See [README_CN.md](README_CN.md) for Chinese project notes, [docs/demo/DEMO_RUNBOOK.md](docs/demo/DEMO_RUNBOOK.md) for the interview demo sequence, and [docs/interview/PROJECT_STORY.md](docs/interview/PROJECT_STORY.md) for the interview explanation.

Additional portfolio material is available in [technical_questions.md](docs/interview/technical_questions.md), [resume_material.md](docs/interview/resume_material.md), [demo_script.md](docs/demo/demo_script.md), and [screenshots.md](docs/demo/screenshots.md).
