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

## Approval command provenance

Approval commands are also recorded in the existing `AuditEvent` timeline. The
following event names are the durable command checkpoints:

| Event | Meaning |
| --- | --- |
| `GLOBAL_APPROVAL_COMMAND_RECEIVED` | The Global Approvals approval-only command entered the backend. |
| `AGENT_APPROVE_AND_EXECUTE_COMMAND_RECEIVED` | The Agent Workspace composite command entered the backend. |
| `APPROVAL_COMMAND_SUCCEEDED` | Authority validation passed and the human Approval was persisted. |
| `APPROVAL_COMMAND_FAILED` | Authority or approval validation rejected the command. |
| `EXECUTION_INITIATION_REQUESTED` | The composite command requested governed execution after approval. |
| `EXECUTION_INITIATION_STARTED` | The server invoked the existing governed Runtime path. |
| `EXECUTION_INITIATION_FAILED` | Runtime setup or initiation failed after the Approval was persisted. |

The command events share one correlation ID and contain only bounded IDs,
versions, states, outcomes, and safe error categories. They never contain
credentials, request headers, raw stack traces, tool output, or hidden model
reasoning. The normal Diagnostics page projects these events; it does not
create a second lifecycle store.

`Task.status = RUNNING` means that a matching human Approval has unlocked the
current Plan and the Task is eligible for governed execution. It is not, by
itself, proof that Runtime or a ToolExecution has started. Use the command
provenance checkpoints and the downstream `ToolExecution`, observation, and
Evidence records to establish that execution actually progressed.

For the synthetic `Release v2.0 Verification (PASS)` fixture, the expected trace includes one validated three-step plan, an approved decision, three successful tool executions, `test-results.json` evidence, and the corresponding audit events.
