# AgentForge Demo Runbook

## Scenario

Verify whether Release v2.0 is ready for release.

All records created by the explicit seed script are synthetic and stored under `D:\AgentProjectData\AgentForge\`. Normal launcher startup never runs that script.

## Start

1. Double-click `Start-AgentForge.bat`.
2. Confirm the browser opens at `http://localhost:5173`.
3. Confirm the backend status is available at `http://127.0.0.1:8000/health`.

## Optional synthetic fixture preparation

For the seeded dashboard variant, run `scripts/seed_demo.py` explicitly from
the approved backend environment before starting the launcher. This step is
deliberate demo preparation and is not part of one-click startup.

## Demonstration sequence

1. Dashboard: show total tasks, pending approvals, and the Release v2.0 task.
2. Switch `en-US` → `zh-CN` → `en-US` once to show native localization and reload persistence.
3. Approval Center: open the pending plan.
4. Explain each step: `git_read`, `file_read`, and `test_run`.
5. Point out `SAFE_READ` versus `APPROVED_EXEC`.
6. Emphasize the message: “This is what the Agent will execute.”
7. Approve or reject the plan to demonstrate the human control gate.
8. Task Detail: inspect the lifecycle timeline, tool executions, evidence, and audit events.
9. Report: show the synthetic PASS task and its `test-results.json` evidence reference.

## Talking points

- The Planner does not have direct tool access.
- The PermissionPolicy does not import Tool Gateway or tool implementations.
- Approval is version-bound; a changed plan requires a new approval.
- Evidence and audit records provide a traceable explanation of the result.

## Stop

Double-click `Stop-AgentForge.bat`. This stops only process IDs recorded by AgentForge under the external runtime directory.
