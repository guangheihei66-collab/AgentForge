# AgentForge Technical Interview Questions

## 为什么不用 ChatGPT/Codex？

通用 AI 工具主要解决内容生成和交互问题；企业 Agent 还需要解决执行治理问题，包括权限边界、审批、失败处理、证据和审计。AgentForge 的重点是围绕模型意图建立一个可控的执行控制面。

## 为什么需要 Approval？

Approval 保证人在高风险动作前仍然拥有控制权，并把决策绑定到具体 Task、Plan ID 和 Plan Version。计划改变后，旧审批不能继续授权执行。

## 为什么 Planner 和 Executor 分离？

Planner 输出意图和结构化计划，但没有工具执行权限。Executor 只能通过 Tool Gateway 运行注册工具。这样可以避免 LLM 直接拥有文件系统、Shell 或破坏性操作权限。

## 为什么不用 Multi-Agent？

MVP 优先保证可靠性、可验证性和可审计性。增加多个 Agent 会扩大状态、通信、调试和授权边界；当前 Planner + governed Tool Gateway 已经足以展示核心工程能力。

## 为什么使用自定义状态机？

CREATED、PLANNING、WAITING_APPROVAL、RUNNING、SUCCESS、FAILED、CANCELLED 是有限且可审计的业务状态。自定义状态机让非法迁移和恢复规则显式化，便于单元测试与面试解释。

## 为什么 MVP 使用 SQLite？

SQLite 降低本地演示和测试的基础设施成本，同时保留清晰的存储边界。多用户、高并发和生产部署可以在后续阶段迁移到 PostgreSQL，但不应为了展示 Agent 治理而过早引入复杂基础设施。

## 如何证明工具执行是安全的？

请求必须经过 Tool Registry、Permission Policy、Workspace Validator 和 Approval Service。工具是 allowlist，路径拒绝 secrets 和越界目录，Test Tool 只接受预定义 profile，所有结果都有 ToolExecution、Evidence 或 AuditEvent 记录。

## 如何测试 Agent 系统？

使用 MockLLMProvider 保证计划生成确定性；对状态迁移、非法计划、权限拒绝、审批绑定、工作区校验和 API 进行自动化测试；再用合成 Release Verification 场景执行 UI 验证。

## 生产环境还会改进什么？

会优先加入身份认证与 RBAC、PostgreSQL 或其他受管数据库、持久化任务队列、超时与重试策略、集中式日志和指标、密钥管理、网络隔离以及更完整的评估集。核心治理边界会保留：Planner 不直接执行，受保护工具必须经过审批和 Tool Gateway。当前 MVP 有意不引入这些基础设施，以保持可复现和可解释。
