# AgentForge Deployment Guide

This guide describes the supported Phase 8.2 deployment shapes. AgentForge is a self-hosted control console: the source tree contains code and documentation, while SQLite, runtime logs, PID files, and demo artifacts stay under `AGENTFORGE_DATA_ROOT`.

## Local Windows deployment

Requirements:

- Python with `backend/.venv` already provisioned
- Node.js and npm available on `PATH`
- Ports `8000` and `5173` available
- At least the approved project-drive storage headroom from Phase 0

1. Copy `.env.example` to `.env` only if custom paths are needed. Keep real credentials outside the repository.
2. Double-click `start/start_agentforge.bat`.
3. Open `http://localhost:5173` and follow `docs/demo/DEMO_RUNBOOK.md`.
4. Stop only the recorded AgentForge process trees with `start/stop_agentforge.bat`.

The launcher initializes the database, seeds idempotent synthetic demo records, starts the backend on `127.0.0.1:8000`, starts Vite on `127.0.0.1:5173`, and opens the browser. It does not pull images, download models, or install dependencies.

## Internal server deployment

For an internal Windows or Linux host:

1. Provision the Python virtual environment and frontend dependencies during a controlled build step.
2. Set `AGENTFORGE_DATA_ROOT` to a dedicated writable data volume and `AGENTFORGE_WORKSPACE_ROOT` to the approved workspace.
3. Set `AGENTFORGE_DATABASE_URL` to the host-local SQLite path for a single-operator demo. Use a managed database only after a separately approved persistence phase.
4. Bind the API and frontend to private network interfaces only; place TLS and access control at the internal reverse proxy.
5. Run the backend and frontend under separate service identities with least-privilege filesystem access.
6. Rotate runtime logs and back up the data root according to the internal retention policy.

The current package is a single-host demonstration deployment. It is not yet a horizontally scaled or RBAC-enabled production service.

The local launcher allows only the two loopback frontend origins by default. For an internal reverse proxy, set `AGENTFORGE_ALLOWED_ORIGINS` to an explicit comma-separated allowlist; do not use a wildcard with credentials.

## Configuration and secrets

Use [.env.example](../../.env.example) as the documented variable list. `.env` is ignored by Git. API keys, tokens, and certificates must be injected by the host secret manager or service environment and must never be copied into source, demo data, or logs.

## Operational boundary

The deployment exposes a read-safe Tool Gateway with approval authorization. It does not permit arbitrary shell commands, destructive file operations, Git writes, local model downloads, or Docker runtime management.
