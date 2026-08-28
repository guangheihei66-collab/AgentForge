# AgentForge Final 5-Minute Presentation

## 0:00–1:00 — Business problem

“Enterprise teams cannot give an AI Agent unrestricted shell or filesystem access. A model may generate a useful plan, but the organization still needs clear permissions, human control, traceable execution, and evidence for audits. AgentForge is a self-hosted AI Agent governance platform built around that control problem.”

Show the Dashboard and point out that this is an operations console, not a chat window.

## 1:00–2:00 — Architecture

Show the architecture diagram and explain each boundary:

```text
Planner → Validator → Approval Gateway → Tool Gateway
                                      ↓
                              Evidence + Audit → Report
```

The Planner proposes a structured plan. The Validator checks schema, tools, actions, permissions, and workspace. Approval binds a human decision to a plan version. The Tool Gateway is the only execution boundary.

## 2:00–4:00 — Live demo

1. Start AgentForge with `Start-AgentForge.bat` and open the Dashboard.
2. Select the seeded `Release v2.0 Verification` task and open Approval Center.
3. Show `git_read`, `file_read`, and predefined `test_run`, including risk and permission labels.
4. Approve the plan and point out that the decision is recorded.
5. Open the separate synthetic PASS fixture in Task Detail. Show the lifecycle timeline, three successful ToolExecution records, `test-results.json`, and audit history.
6. Open the Readiness Report and show `PASS`, three completed checks, zero failures, evidence, and audit counts.

The packaged UI intentionally uses repeatable synthetic fixtures for the visual demo. Task creation and plan generation are available through the backend API; arbitrary execution is not exposed as a UI shortcut and remains governed by the Tool Gateway.

## 4:00–5:00 — Engineering decisions

- Security: default-deny permissions, allowlisted tools, workspace validation, and approval-bound execution.
- Reliability: explicit state machine, deterministic MockLLMProvider, SQLite portability, and bounded synthetic data.
- Auditability: Task → Plan → Approval → ToolExecution → Evidence → AuditEvent → Report.
- Scope discipline: Multi-Agent, RAG, MCP, Docker, Kubernetes, local models, and write-capable tools are intentionally outside this MVP.

Closing line: “AgentForge demonstrates that an enterprise Agent is not only a model that can act; it is a controlled system that can explain and defend every action.”
