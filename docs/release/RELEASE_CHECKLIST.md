# AgentForge 0.1.0 Release Checklist

Release: `0.1.0`
Tag: `v0.1.0`
Status: Stable
Distribution: source repository + Windows launcher scripts

## Release structure

The repository root is the release package. Its public-facing structure is:

```text
AgentForge/
├── README.md
├── README_CN.md
├── start_agentforge.bat
├── stop_agentforge.bat
├── start/
├── backend/
├── frontend/
├── docs/
├── demo/
└── screenshots/
```

`demo/` and `screenshots/` contain instructions and placeholders only. Binary captures, databases, logs, runtime files, and artifacts remain outside Git.

## Release checks

- [x] Backend tests pass.
- [x] Frontend tests pass.
- [x] Frontend production build passes.
- [x] Startup script starts backend and frontend on the documented loopback ports.
- [x] `/health` returns 200.
- [x] `/` returns service information.
- [x] UI dashboard loads live seeded data.
- [x] Approval Center shows the version-bound plan.
- [x] Task Detail shows execution, evidence, and audit records.
- [x] Report shows the synthetic PASS result.
- [x] No database, `.env`, secret, log, or temporary artifact is tracked.
- [x] Real-provider planning, grounded metadata, approval snapshots, Project authority, governed execution, Evidence, Audit, and controlled replanning are verified.
- [x] Test result and report semantics distinguish SUCCESS, FAILED, and REJECTED.
- [x] Release notes and operator configuration guidance are documented in `PHASE_12_RELEASE_NOTES.md` and `../deployment/OPERATOR_GUIDE.md`.

## Known demo boundary

This is a private stable release. Distribution is source plus the Windows launcher scripts; no installer or automatic updater is provided, and the release pipeline remains manual.

This is a portfolio MVP, not a production deployment. The UI intentionally demonstrates the governed approval and reporting surfaces with idempotent synthetic fixtures. Task creation and planning are backend API operations; execution remains behind the Tool Gateway and is not exposed as an unrestricted UI action. This preserves the security boundary and avoids adding an ungoverned shortcut solely for the demo.

Production follow-up would include a managed database, authentication/RBAC, durable job execution, stronger observability, and a reviewed internal deployment model. Those are future phases, not release blockers for this portfolio package.
