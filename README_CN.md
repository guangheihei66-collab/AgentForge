# AgentForge 中文说明

AgentForge 是一个自托管企业级 AI Agent 治理平台，面向需要安全执行工程任务的团队。

它不是聊天机器人，而是一个可审计的 Agent Operations Console：用户提交目标，Planner 生成计划，人工审批后才能执行受控工具，系统收集证据并生成审计记录。

## 核心链路

```text
用户目标
  ↓
Planner Agent
  ↓
Plan Validator
  ↓
Approval Gateway
  ↓
Tool Gateway
  ↓
Evidence + Audit
  ↓
最终报告
```

## 技术重点

- 使用自定义状态机表达 CREATED、PLANNING、WAITING_APPROVAL、RUNNING、SUCCESS、FAILED、CANCELLED。
- Planner 只能生成结构化计划，不能直接调用工具。
- PermissionPolicy 默认拒绝，并与 Tool Gateway 解耦，避免循环依赖。
- 工具必须经过注册、权限、工作区和审批检查。
- 工具执行结果写入 ToolExecution、Evidence 和 AuditEvent。
- 前端展示“Agent 准备执行什么”，而不是模拟聊天。
- demo 数据是本地合成数据，不包含真实公司、密钥或个人隐私。

## 面试讲解路线

1. 先说明为什么直接让 LLM 执行 shell 不安全。
2. 解释 Planner、Approval Gateway 和 Tool Gateway 的职责边界。
3. 演示一个计划如何从 CREATED 进入 WAITING_APPROVAL。
4. 展示人工审批如何绑定 Task、Plan ID 和 Plan Version。
5. 展示工具执行后的 Evidence 和 Audit Timeline。
6. 说明权限层与工具实现解耦后，如何避免循环导入和架构耦合。

Windows 下双击 `start\start_agentforge.bat` 启动演示，双击 `start\stop_agentforge.bat` 停止 AgentForge 进程。
