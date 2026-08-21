# AgentForge Execution Trace

Every release-verification run is traceable through these persisted records:

```text
Task
  |
  v
Plan (immutable version)
  |
  v
Approval (bound to task + plan version)
  |
  v
ToolExecution (one record per governed tool call)
  |
  v
Evidence (artifact reference + content hash)
  |
  v
AuditEvent (append-only timeline)
```

## Record relationship

| Record | Responsibility | Linkage |
| --- | --- | --- |
| Task | User goal, workspace, lifecycle status | Root aggregate identified by `task_id` |
| Plan | Validated steps and immutable version | `Plan.task_id`; version checked at approval |
| Approval | Human decision for one plan version | `task_id` + `plan_id` + version binding |
| ToolExecution | Governed tool request and result | `task_id`, tool name, status, artifact reference |
| Evidence | Reusable proof of a result | `task_id`, artifact path, optional content hash |
| AuditEvent | Timeline of state, approval, and execution events | `task_id`, actor, event type, correlation ID |

## Trace rules

- A plan must validate against the tool and workspace allowlists before approval.
- An `APPROVED_EXEC` tool requires an approved, matching plan version and a non-cancelled task.
- A successful tool execution can create evidence; failed execution still creates an audit record.
- Reports aggregate execution, evidence, and audit counts; they do not replace the underlying records.
- The UI reads aggregate detail and report endpoints, while the backend remains the source of truth.

For the synthetic `Release v2.0 Verification (PASS)` fixture, the expected trace includes one validated three-step plan, an approved decision, three successful tool executions, `test-results.json` evidence, and the corresponding audit events.
