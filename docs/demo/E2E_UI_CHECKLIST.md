# End-to-End UI Verification Checklist

This is the repeatable Phase 8.2 browser check for the synthetic `Release v2.0 Verification` scenario. It validates the complete persisted workflow without adding production capabilities or requiring external credentials.

1. Prepare the synthetic fixture explicitly, if this is a fresh demo database, with the documented `scripts/seed_demo.py` command. This is a deliberate demo-data step, not part of launcher startup.
2. Start with `Start-AgentForge.bat`.
3. On **Dashboard**, confirm `Release v2.0 Verification` is `WAITING_APPROVAL` and `Release v2.0 Verification (PASS)` is `SUCCESS`.
4. Open **Approval Center**. Confirm the three-step plan shows `git_read`, `file_read`, and `test_run`, with visible permission and risk labels.
5. Approve the pending request. Confirm the pending count decreases and the decision is recorded.
6. Open the PASS task from **Dashboard** and inspect **Task Detail**. Confirm the timeline, plan, three successful tool executions, evidence reference, and audit history.
7. Open **Readiness Report**. Confirm `PASS`, three completed checks, one evidence artifact, and the audit count.
8. Stop with `Stop-AgentForge.bat` and confirm ports `8000` and `5173` close.

The launcher is infrastructure-only and does not create or mutate the synthetic fixture. The approved pending fixture is intentionally separate from the PASS fixture so the operator can demonstrate the approval gate without mutating the known-good report.
