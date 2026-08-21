# AgentForge Screenshot Plan

Capture screenshots at a consistent browser size with synthetic data only. Do not include API keys, local user paths beyond the approved demo workspace, terminal output, personal files, or runtime logs.

## 1. Dashboard overview

Show the AgentForge header, task count, pending approvals, PASS summary, and the two `Release v2.0 Verification` fixtures. This establishes the operational-console positioning.

## 2. Approval Center

Show the three plan steps, risk levels, `SAFE_READ` / `APPROVED_EXEC` labels, workspace-only boundary, and Approve/Reject controls. This is the most important governance screenshot.

## 3. Task Detail

Show the task status timeline, validated plan, workspace, and Agent identity. Prefer the PASS task so the full trace is visible.

## 4. Evidence and Audit

Show the `test-results.json` evidence reference, content hash, three successful tool executions, and audit event timeline in one frame if the viewport permits.

## 5. Final Report

Show `PASS`, completed and failed check counts, evidence artifacts, and audit summary. This is the recommended closing image for a portfolio README or interview presentation.

Suggested filenames:

```text
01-dashboard.png
02-approval-center.png
03-task-detail.png
04-evidence-audit.png
05-final-report.png
```
