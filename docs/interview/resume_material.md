# AgentForge Resume Material

## 中文简历

### 短版

AgentForge — 企业级 AI Agent 治理平台：设计并实现从 Planner 计划生成、计划校验、人工审批、受控工具执行到 Evidence 与 Audit 的完整 Agent 工作流，使用 FastAPI、SQLite 和 React Operations Console，重点解决 Agent 执行权限与可审计性问题。

### 详细版

AgentForge 是一个自托管企业级 AI Agent 治理平台。项目实现了自定义任务状态机、结构化 Plan Validator、Task/Plan/Plan Version 绑定的 Approval Gateway，以及默认拒绝的 Secure Tool Gateway。工具执行限定在 Git read、File read 和预定义 Test profile，并通过工作区校验拒绝 secret、系统目录和越界路径。每次执行关联 ToolExecution、Evidence 和 AuditEvent，前端以 Operations Console 展示审批、时间线、证据和最终报告。

## English resume

### Short version

AgentForge — Enterprise AI Agent Governance Platform: built an end-to-end governed agent workflow from planning and validation through human approval, secure tool execution, evidence collection, and auditable reporting using FastAPI, SQLite, and React.

### Detailed version

Designed and implemented AgentForge, a self-hosted enterprise AI Agent control plane. Built an explicit task state machine, schema-validated Planner boundary, version-bound Approval Gateway, and default-deny Tool Gateway for workspace-scoped Git read, File read, and predefined Test tools. Connected ToolExecution, Evidence, and AuditEvent records into a traceable operations console with repeatable synthetic release-verification demos. Kept LLM planning separate from execution authority to reduce risk and improve testability.

## Keywords

Agent workflow design · secure execution · approval mechanism · audit trail · evidence system · FastAPI · React · SQLite · state machine · tool permission boundary · enterprise AI platform
