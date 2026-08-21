# AgentForge 3–5 Minute Demo Script

## 00:00 — Introduce the problem

“Most AI demos stop at generating an answer. Enterprise systems need to control what an Agent is allowed to do, require approval for protected actions, and explain the result later. AgentForge is a self-hosted governance console for that problem.”

## 00:30 — Show the architecture

Point to the flow: User Goal → Planner → Plan Validator → Approval Gateway → Tool Gateway → Evidence + Audit → Report. Emphasize that the Planner proposes intent, while the Tool Gateway enforces authority.

## 01:00 — Show the task and plan

Open Dashboard and select `Release v2.0 Verification`. In Approval Center, show the three allowlisted steps: `git_read`, `file_read`, and `test_run`. Point out the `SAFE_READ` and `APPROVED_EXEC` permission labels and the workspace-only boundary.

## 01:30 — Demonstrate human approval

Say: “This is what the Agent will execute.” Approve the version-bound plan. Explain that the approval is recorded against the Task, Plan ID, and Plan Version; a changed plan would require a new decision.

## 02:30 — Inspect execution and evidence

Open the PASS task in Task Detail. Show the lifecycle timeline, three successful ToolExecution records, the synthetic `test-results.json` evidence reference, and the audit events.

## 03:00 — Show the final report

Open Readiness Report and show `PASS`, three completed checks, zero failures, evidence count, and audit count. Close with: “The value is not only that the Agent can act; it is that the organization can control and explain the action.”

## 04:00 — Optional interview close

Mention the main trade-offs: SQLite keeps the MVP portable, MockLLMProvider keeps tests deterministic, and the custom state machine keeps governance rules explicit. Multi-Agent, RAG, MCP, local models, and Docker are intentionally outside this portfolio MVP.
